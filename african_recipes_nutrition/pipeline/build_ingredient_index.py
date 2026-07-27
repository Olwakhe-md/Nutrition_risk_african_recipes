"""
build_ingredient_index.py
=========================
One-time build step: assemble a per-recipe ingredient-text index so the Explore
page can offer a "contains ingredient" filter (e.g. show every recipe with
egusi) without reconciling several source files at runtime.

Per-recipe ingredients live in a few places, so we union them:
  1. scraped CSVs (data/scraped/*.csv) — an `ingredients` column keyed by the
     source URL, joined back to recipe_id via recipes_clean.csv's recipe_url.
  2. data/interim/recipe_ingredients.csv — parsed ingredient lines keyed by
     recipe_id.

OUTPUT: data/interim/recipe_ingredient_index.csv  (recipe_id, ingredients_text)
        one lowercase, space-joined blob of ingredient text per recipe.

Run from african_recipes_nutrition/:
    py pipeline/build_ingredient_index.py
"""

import glob
import os
import re

import pandas as pd

BASE          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_CLEAN = os.path.join(BASE, 'data', 'interim', 'recipes_clean.csv')
RECIPE_INGS   = os.path.join(BASE, 'data', 'interim', 'recipe_ingredients.csv')
SCRAPED_GLOB  = os.path.join(BASE, 'data', 'scraped', '*.csv')
OUTPUT        = os.path.join(BASE, 'data', 'interim', 'recipe_ingredient_index.csv')


def _norm_url(u: str) -> str:
    return (str(u).strip().rstrip('/').lower()
            .replace('https://', '').replace('http://', '').replace('www.', ''))


def _clean_text(s: str) -> str:
    """Lowercase, replace separators with spaces, collapse whitespace."""
    s = re.sub(r'[|\n\r\t]+', ' ', str(s))
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()


def main():
    per_recipe: dict[int, list[str]] = {}

    def add(recipe_id, text):
        if pd.isna(recipe_id) or not str(text).strip():
            return
        per_recipe.setdefault(int(recipe_id), []).append(_clean_text(text))

    # ── Source 1: scraped ingredients joined by URL ───────────────────────────
    rc = pd.read_csv(RECIPES_CLEAN)[['recipe_id', 'recipe_url']].dropna(subset=['recipe_url'])
    url2id = {_norm_url(u): rid for rid, u in zip(rc['recipe_id'], rc['recipe_url'])}

    for path in glob.glob(SCRAPED_GLOB):
        df = pd.read_csv(path)
        url_cols = [c for c in df.columns if 'url' in c.lower()]
        if not url_cols or 'ingredients' not in df.columns:
            continue
        for url, ings in zip(df[url_cols[0]], df['ingredients']):
            add(url2id.get(_norm_url(url)), ings)

    # ── Source 2: parsed ingredient lines keyed by recipe_id ──────────────────
    if os.path.exists(RECIPE_INGS):
        ri = pd.read_csv(RECIPE_INGS)
        if 'ingredient_line_raw' in ri.columns:
            for rid, line in zip(ri['recipe_id'], ri['ingredient_line_raw']):
                add(rid, line)

    rows = [
        {'recipe_id': rid, 'ingredients_text': ' '.join(sorted(set(parts)))}
        for rid, parts in per_recipe.items()
    ]
    out = pd.DataFrame(rows).sort_values('recipe_id')
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    out.to_csv(OUTPUT, index=False)

    print(f"Wrote ingredient text for {len(out):,} recipes -> {OUTPUT}")


if __name__ == '__main__':
    main()
