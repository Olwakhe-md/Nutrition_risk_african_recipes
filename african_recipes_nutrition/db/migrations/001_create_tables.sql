-- migrations/001_create_tables.sql
-- Run once to set up the nutrition database schema.
--
-- PostgreSQL:
--   psql -U youruser -d yourdb -f migrations/001_create_tables.sql
--
-- SQLite: handled automatically by loader.py when --create-tables is passed.

-- ── 1. nutrients ───────────────────────────────────────────────────────────────
-- USDA nutrient definitions sourced from nutrient.csv
CREATE TABLE IF NOT EXISTS nutrients (
    id           INTEGER PRIMARY KEY,   -- USDA nutrient ID
    name         TEXT    NOT NULL,
    unit_name    TEXT    NOT NULL,
    nutrient_nbr REAL,
    rank         REAL
);

-- ── 2. ingredient_mappings ─────────────────────────────────────────────────────
-- One row per recipe ingredient string, cleaned and mapped to a USDA food entry.
-- match_status values:
--   matched        — successfully mapped to a USDA food ID
--   african_proxy  — regional ingredient; no direct USDA match, proxy suggested
--   skip           — entry was a recipe instruction fragment, not an ingredient
CREATE TABLE IF NOT EXISTS ingredient_mappings (
    id                      SERIAL PRIMARY KEY,   -- use INTEGER for SQLite
    recipe_ingredient_name  TEXT    NOT NULL,      -- original raw string
    cleaned_ingredient_name TEXT,                  -- after cleaning pipeline
    matched_fdc_id          REAL,                  -- USDA FDC food ID (nullable)
    matched_food_name       TEXT,                  -- USDA food name or proxy label
    match_status            TEXT    NOT NULL
                            CHECK (match_status IN ('matched','african_proxy','skip','still_unmatched')),
    match_type              TEXT,                  -- original / manual_match / fuzzy / african_proxy / skip
    notes                   TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookups by ingredient name or USDA food ID
CREATE INDEX IF NOT EXISTS idx_im_fdc_id   ON ingredient_mappings (matched_fdc_id);
CREATE INDEX IF NOT EXISTS idx_im_status   ON ingredient_mappings (match_status);

-- ── 3. african_ingredient_proxies ──────────────────────────────────────────────
-- Reference table for African / regional ingredients that have no USDA entry.
-- Each row stores the local name and the closest nutritional proxy to use.
CREATE TABLE IF NOT EXISTS african_ingredient_proxies (
    id                  SERIAL PRIMARY KEY,
    local_name          TEXT NOT NULL UNIQUE,  -- e.g. 'bondwe'
    display_name        TEXT,                  -- e.g. 'bondwe leaves'
    proxy_description   TEXT,                  -- e.g. 'amaranth leaves'
    region              TEXT,                  -- e.g. 'Southern Africa'
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
