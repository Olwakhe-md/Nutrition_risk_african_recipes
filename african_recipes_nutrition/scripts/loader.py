"""
scripts/loader.py
=================
Orchestrates the full pipeline:
  load CSVs → clean → match → insert into DB

Supports PostgreSQL and SQLite.

Usage (called by run_pipeline.py — you rarely need to import this directly):
    from scripts.loader import run
    run(engine, create_tables=True)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .cleaner import (
    AFRICAN_PROXIES,
    AFRICAN_PROXY_REGIONS,
    clean_ingredient,
    is_instruction_fragment,
    normalize_text
)
from .matcher import Matcher
from ..config import NUTRIENT_CSV, ORIGINAL_MAPPING_CSV

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = PROJECT_ROOT / "migrations" / "001_create_tables.sql"

def _is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"

def _read_schema_sql(pg: bool = True) -> list[str]:
    """Reads the SQL migration file and returns executable statements."""
    if not SCHEMA_PATH.exists():
        logger.warning("Schema file not found at %s. Skipping auto-creation.", SCHEMA_PATH)
        return []
    
    with open(SCHEMA_PATH, "r") as f:
        content = f.read()
    
    if not pg:
        # Quick translation for SQLite compatibility
        content = content.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        content = content.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TEXT DEFAULT (datetime('now'))")
    
    # Split by semicolon, filtering out empty blocks or comments
    return [s.strip() for s in content.split(";") if s.strip() and not s.strip().startswith("--")]

def create_tables(engine: Engine) -> None:
    """Create all tables if they don't already exist."""
    pg = _is_postgres(engine)
    statements = _read_schema_sql(pg)
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    logger.info("Tables created (or already exist).")


def _load_nutrients(engine: Engine) -> int:
    """Load nutrient.csv into the nutrients table. Returns rows inserted."""
    df = pd.read_csv(NUTRIENT_CSV)
    df.to_sql("nutrients", engine, if_exists="replace", index=False)
    logger.info("nutrients: %d rows loaded.", len(df))
    return len(df)

def _prepare_recipe_data(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures recipe_ids and blocks are correctly assigned from the raw data."""
    logger.info("Input CSV columns found: %s", df.columns.tolist())
    df = df.copy()
    
    # Fallback if 'recipe_title' is missing but 'recipe_name' or 'title' exists
    if "recipe_title" not in df.columns:
        for alt in ["recipe_name", "title", "recipe"]:
            if alt in df.columns:
                df["recipe_title"] = df[alt]
                break

    if "recipe_title" not in df.columns:
        logger.warning("Column 'recipe_title' not found. Using 'Unknown Recipe' for all rows.")
        df["recipe_title"] = "Unknown Recipe"

    df["recipe_title"] = df["recipe_title"].fillna("Unknown Recipe")
    
    # Build blocks based on title changes
    new_recipe_block = df["recipe_title"].ne(df["recipe_title"].shift()).fillna(True)
    df["recipe_block"] = new_recipe_block.cumsum()
    
    # Assign or forward-fill IDs
    if "recipe_id" not in df.columns or df["recipe_id"].isnull().all():
        df["recipe_id"] = df["recipe_block"]
    else:
        df["recipe_id"] = pd.to_numeric(df["recipe_id"], errors="coerce").ffill().astype(int)
        
    return df


def _build_ingredient_rows(df_original: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Run the full clean → match pipeline over every row in the original CSV.
    Returns a list of dicts ready for pd.DataFrame / to_sql.
    """
    matcher = Matcher(df_original)
    rows: list[dict[str, Any]] = []

    for _, row in df_original.iterrows():
        orig: str = row["recipe_ingredient_name"]
        original_status: str = row["match_status"]
        original_notes = row.get("notes", "")
        original_notes = "" if pd.isna(original_notes) else str(original_notes)

        # ── Already matched — keep as-is ──────────────────────────────────────
        if original_status == "matched":
            rows.append({
                "recipe_ingredient_name":  orig,
                "cleaned_ingredient_name": orig,
                "matched_fdc_id":          row["matched_fdc_id"],
                "matched_food_name":       row["matched_food_name"],
                "match_status":            "matched",
                "match_type":              "original",
                "notes":                   original_notes,
            })
            continue

        # ── Clean ─────────────────────────────────────────────────────────────
        cleaned, tag, display = clean_ingredient(orig)

        # ── African proxy ─────────────────────────────────────────────────────
        if tag == "african_proxy":
            rows.append({
                "recipe_ingredient_name":  orig,
                "cleaned_ingredient_name": display,
                "matched_fdc_id":          None,
                "matched_food_name":       cleaned,   # proxy description
                "match_status":            "african_proxy",
                "match_type":              "african_proxy",
                "notes": (
                    f"Regional ingredient — no direct USDA match. "
                    f"Suggested nutritional proxy: {cleaned}"
                ),
            })
            continue

        # ── Instruction fragment — skip ───────────────────────────────────────
        if is_instruction_fragment(cleaned):
            rows.append({
                "recipe_ingredient_name":  orig,
                "cleaned_ingredient_name": display,
                "matched_fdc_id":          None,
                "matched_food_name":       None,
                "match_status":            "skip",
                "match_type":              "skip",
                "notes":                   "Entry is a recipe instruction fragment, not an ingredient.",
            })
            continue

        # ── Match ─────────────────────────────────────────────────────────────
        food_name, fdc_id, match_type = matcher.match(cleaned)

        if match_type != "no_match":
            rows.append({
                "recipe_ingredient_name":  orig,
                "cleaned_ingredient_name": cleaned,
                "matched_fdc_id":          fdc_id,
                "matched_food_name":       food_name,
                "match_status":            "matched",
                "match_type":              match_type,
                "notes":                   "Matched after cleaning ingredient name.",
            })
        else:
            rows.append({
                "recipe_ingredient_name":  orig,
                "cleaned_ingredient_name": cleaned,
                "matched_fdc_id":          None,
                "matched_food_name":       None,
                "match_status":            "still_unmatched",
                "match_type":              "no_match",
                "notes":                   "No USDA match found after cleaning.",
            })

    return rows


def _load_ingredient_mappings(engine: Engine, rows: list[dict[str, Any]]) -> int:
    df = pd.DataFrame(rows)
    df.to_sql("ingredient_mappings", engine, if_exists="replace", index=False)
    logger.info("ingredient_mappings: %d rows loaded.", len(df))
    return len(df)


def _load_african_proxies(engine: Engine) -> int:
    """Populate the african_ingredient_proxies reference table."""
    proxy_rows = []
    for local_name, (proxy_desc, display_name) in AFRICAN_PROXIES.items():
        proxy_rows.append({
            "local_name":        local_name,
            "display_name":      display_name,
            "proxy_description": proxy_desc,
            "region":            AFRICAN_PROXY_REGIONS.get(local_name, "Africa"),
            "notes":             None,
        })
    df = pd.DataFrame(proxy_rows).drop_duplicates(subset="local_name")
    df.to_sql("african_ingredient_proxies", engine, if_exists="replace", index=False)
    logger.info("african_ingredient_proxies: %d rows loaded.", len(df))
    return len(df)


def run(engine: Engine, create_tables_first: bool = False) -> dict[str, int]:
    """
    Run the full pipeline.

    Parameters
    ----------
    engine              : SQLAlchemy engine (PostgreSQL or SQLite)
    create_tables_first : if True, CREATE TABLE IF NOT EXISTS before loading

    Returns
    -------
    dict with row counts per table
    """
    if create_tables_first:
        create_tables(engine)

    df_raw = pd.read_csv(ORIGINAL_MAPPING_CSV)
    logger.info("Loaded original mapping CSV: %d rows.", len(df_raw))
    df_prepared = _prepare_recipe_data(df_raw)

    n_nutrients = _load_nutrients(engine)
    rows        = _build_ingredient_rows(df_prepared)
    n_mappings  = _load_ingredient_mappings(engine, rows)
    n_proxies   = _load_african_proxies(engine)

    summary = {
        "nutrients":                  n_nutrients,
        "ingredient_mappings":        n_mappings,
        "african_ingredient_proxies": n_proxies,
    }
    logger.info("Pipeline complete. Summary: %s", summary)
    return summary
