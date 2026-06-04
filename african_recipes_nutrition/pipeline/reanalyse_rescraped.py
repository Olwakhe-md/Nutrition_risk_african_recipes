"""
pipeline/reanalyse_rescraped.py
================================
Clean and re-analyse the re-scraped insufficient_data recipes, then update
their rows in recipe_risk_scores.csv.

WHY THIS SCRIPT EXISTS
----------------------
55 recipes were labelled 'insufficient_data' because the original scrape
produced garbled or incomplete ingredient text — missing quantities, mixed-in
instruction text, or partial scrapes.  We re-scraped them from their source
URLs and now have clean ingredient lists.  This script runs those clean lists
through the same LiveAnalyser pipeline that powers the live dashboard tab,
and writes the results back into the master scores CSV.

WHAT CHANGES IN recipe_risk_scores.csv
---------------------------------------
  - Recipes where coverage > 0 get updated nutrition + risk values
  - data_status changes from 'insufficient_data' to 'calculated' when
    energy_kcal > 0 (i.e. at least one caloric ingredient matched USDA)
  - Recipes that still return all-zero nutrition keep 'insufficient_data'

WHAT DOES NOT CHANGE
---------------------
  - recipe_id, recipe_name, servings — preserved from the original row
  - Recipes not in the re-scraped file — untouched

Run from african_recipes_nutrition/:
    py pipeline/reanalyse_rescraped.py
"""

import html
import os
import re
import sys

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.stdout.reconfigure(encoding='utf-8')

RESCRAPED_FILE = os.path.join(BASE, 'data', 'scraped',  'rescraped_insufficient.csv')
SCORES_FILE    = os.path.join(BASE, 'data', 'outputs',  'recipe_risk_scores.csv')

# Roundup page — not a real recipe; always excluded
ROUNDUP_IDS = {214}

# Only update rows whose coverage clears this bar
MIN_COVERAGE_TO_UPDATE = 0.0   # any match is better than nothing


# ── Ingredient string cleaning ────────────────────────────────────────────────

def clean_ingredient_string(raw: str) -> str:
    """
    Clean a single ingredient string coming out of the scraper.

    Four things to fix:
      1. HTML tags  — food.com embeds <a href="...">recipe name</a> inside
         ingredient strings when linking to sub-recipes.
         e.g. '1 cup <a href="...">Niter Kibbeh</a> butter' → '1 cup Niter Kibbeh butter'

      2. HTML entities — &amp; &otilde; &apos; etc.
         e.g. 'Camar&otilde;es' → 'Camarões'

      3. Dual-measurement format — BBC Food and some food.com recipes write
         quantities as "120g/4½oz" (metric / imperial side by side).
         The parser requires a space after the unit, so "120g/4oz" fails to
         detect 'g' as the unit and falls back to treating 120 as a plain
         count (120 items × 150g = 18 000g), massively inflating calories.
         Fix: keep only the first measurement, discard everything after '/'.
         e.g. "120g/4½oz onion"  → "120 g onion"
              "100ml/3fl oz milk" → "100 ml milk"

      4. Whitespace normalisation — collapse multiple spaces.
    """
    # Strip HTML tags first, keeping inner text
    text = re.sub(r'<[^>]+>', '', raw)
    # Decode HTML entities (&amp; → &, &otilde; → õ, etc.)
    text = html.unescape(text)
    # Normalise dual-measurement: "200g/7oz" → "200 g", "100ml/3fl oz" → "100 ml"
    text = re.sub(r'(\d+\.?\d*)\s*(g|kg|ml|l)/[^\s]*', r'\1 \2', text, flags=re.IGNORECASE)
    # Normalise range quantities: "80 -100 g" or "80-100 g" → "80 g"
    # Range formats break the parser — it reads the first number as a plain count
    # and never finds the unit, so "80" becomes 80 items × 150g = 12 000g.
    # We take the lower bound of the range; it's a closer estimate than 12 000g.
    text = re.sub(
        r'(\d+\.?\d*)\s*[-–]\s*\d+\.?\d*\s+(g|kg|ml|l|oz|tbsp?|tsp?|cups?)',
        r'\1 \2', text, flags=re.IGNORECASE
    )
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_ingredient_lines(ing_str: str) -> list[str]:
    """
    Split the pipe-delimited ingredient string into individual lines
    and clean each one.
    """
    lines = []
    for part in str(ing_str).split(' | '):
        cleaned = clean_ingredient_string(part.strip())
        if cleaned:
            lines.append(cleaned)
    return lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    from pipeline.live_analysis import LiveAnalyser

    # ── Load files ────────────────────────────────────────────────────────────
    rescraped = pd.read_csv(RESCRAPED_FILE, encoding='utf-8-sig')
    scores    = pd.read_csv(SCORES_FILE)

    # Drop known roundup pages
    rescraped = rescraped[~rescraped['recipe_id'].isin(ROUNDUP_IDS)].copy()
    print(f'Recipes to re-analyse: {len(rescraped)}  (roundup IDs excluded: {ROUNDUP_IDS})')
    print('=' * 60)

    # ── Load LiveAnalyser once (heavy: loads ~150 MB USDA data) ──────────────
    print('Loading USDA data (this takes ~3 seconds)...')
    analyser = LiveAnalyser()
    print('Ready.\n')

    # ── Iterate and analyse ───────────────────────────────────────────────────
    updated   = []
    skipped   = []

    for _, row in rescraped.iterrows():
        recipe_id   = int(row['recipe_id'])
        recipe_name = str(row['recipe_name'])

        # Get servings — use re-scraped value, fall back to original
        try:
            servings = int(float(str(row['servings'])))
            if servings < 1:
                servings = 4
        except (ValueError, TypeError):
            orig = scores[scores['recipe_id'] == recipe_id]
            servings = int(orig['servings'].iloc[0]) if len(orig) else 4

        # Build ingredient lines
        lines = split_ingredient_lines(row['ingredients'])
        if not lines:
            print(f'  [SKIP] ID {recipe_id}: no ingredient lines after cleaning')
            skipped.append(recipe_id)
            continue

        # Run analysis
        result   = analyser.analyse(lines, servings=servings)
        nutrition = result['nutrition']
        risk      = result['risk']
        coverage  = result['coverage']

        n_matched = sum(1 for i in result['ingredients'] if i['status'] == 'matched')
        status    = 'calculated' if nutrition['energy_kcal'] > 0 else 'insufficient_data'

        print(f'  ID {recipe_id:>4} | {recipe_name[:40]:<40} | '
              f'cov={coverage:>5.1f}%  kcal={nutrition["energy_kcal"]:>6.0f}  '
              f'[{n_matched}/{len(lines)}]  → {status}')

        if coverage < MIN_COVERAGE_TO_UPDATE and nutrition['energy_kcal'] == 0:
            skipped.append(recipe_id)
            continue

        # Build the updated row values
        updates = {
            'energy_kcal':             nutrition['energy_kcal'],
            'protein_g':               nutrition['protein_g'],
            'fat_g':                   nutrition['fat_g'],
            'carbohydrate_g':          nutrition['carbohydrate_g'],
            'sugars_g':                nutrition['sugars_g'],
            'sodium_mg':               nutrition['sodium_mg'],
            'ingredient_coverage_pct': coverage,
            'energy_risk':             risk['energy_risk'],
            'sodium_risk':             risk['sodium_risk'],
            'fat_risk':                risk['fat_risk'],
            'sugar_risk':              risk['sugar_risk'],
            'protein_risk':            risk['protein_risk'],
            'flag_count':              risk['flag_count'],
            'flag_risk_level':         risk['flag_risk_level'],
            'weighted_risk_score':     risk['weighted_risk_score'],
            'weighted_risk_level':     risk['weighted_risk_level'],
            'data_status':             status,
        }

        # Update the row in the scores DataFrame
        mask = scores['recipe_id'] == recipe_id
        if mask.sum() == 0:
            print(f'    WARNING: recipe_id {recipe_id} not found in scores file — skipping')
            skipped.append(recipe_id)
            continue

        for col, val in updates.items():
            scores.loc[mask, col] = val

        updated.append(recipe_id)

    # ── Write updated scores back ─────────────────────────────────────────────
    scores.to_csv(SCORES_FILE, index=False, encoding='utf-8')

    # ── Summary ───────────────────────────────────────────────────────────────
    n_calculated = sum(
        1 for rid in updated
        if scores.loc[scores['recipe_id'] == rid, 'data_status'].iloc[0] == 'calculated'
    )
    n_still_insuf = len(updated) - n_calculated

    print()
    print('=' * 60)
    print(f'Rows updated in recipe_risk_scores.csv : {len(updated)}')
    print(f'  → now "calculated"                   : {n_calculated}')
    print(f'  → still "insufficient_data"           : {n_still_insuf}')
    print(f'Skipped (no usable ingredients)         : {len(skipped)}')
    print(f'Saved to: {SCORES_FILE}')


if __name__ == '__main__':
    main()
