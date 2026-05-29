"""
integrate_cheflola.py
=====================
Integrates the 44 scraped cheflolaskitchen.com recipes into the pipeline.

Unlike integrate_scraped.py (which added NEW recipe IDs 279-337), these
recipes ALREADY EXIST in the pipeline as IDs 182-225 but with only 1
placeholder ingredient each.  This script:

  1. Replaces the existing single-ingredient rows for IDs 182-225 in
     recipe_ingredient_final.csv with the full scraped ingredient lists.
  2. Updates the servings in recipes_clean.csv from the scraped values.
  3. Adds any new ingredients to ingredients_master.csv.
  4. Adds any new mappings to ingredient_mapping_final.csv.

Recipe 214 ("60 Nigerian Recipes You Need To Try") is a roundup post —
it has no real recipe card.  It is skipped.

After this script, re-run calculate_nutrition.py to refresh recipe_nutrition.csv.

Run from african_recipes_nutrition/:
    py integrate_cheflola.py
"""

import csv
import os
import re
import sys

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
DATA_RAW     = os.path.join(BASE, 'data', 'raw')
DATA_SCRAPED = os.path.join(BASE, 'data', 'scraped')
DATA_OUTPUT  = os.path.join(BASE, 'data', 'outputs')
sys.path.insert(0, BASE)

SCRAPED_FILE  = os.path.join(DATA_SCRAPED, 'cheflola_scraped.csv')
RECIPES_FILE  = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
MASTER_FILE   = os.path.join(DATA_INTERIM, 'ingredients_master.csv')
RIF_FILE      = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
MAPPING_FILE  = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')
MAPPING_REF   = os.path.join(DATA_RAW,  'ingredient_mapping_original.csv')

# Recipe 214 is a roundup post — skip it
SKIP_IDS = {'214'}

# ── Reuse the same ingredient-line parser from integrate_scraped.py ───────────

UNIT_GRAMS = {
    'tsp': 5,    'teaspoon': 5,    'teaspoons': 5,
    'tbsp': 15,  'tablespoon': 15, 'tablespoons': 15,
    'cup': 240,  'cups': 240,
    'oz': 28.35, 'ounce': 28.35,  'ounces': 28.35,
    'pound': 454, 'pounds': 454,  'lb': 454, 'lbs': 454,
    'g': 1,      'gram': 1,       'grams': 1,
    'ml': 1,     'l': 1000,       'kg': 1000,
    'clove': 4,  'cloves': 4,
    'large': 150, 'medium': 110,  'small': 70,
    'can': 400,  'cans': 400,
    'piece': 100, 'pieces': 100,
    'slice': 30, 'slices': 30,
    'bunch': 100, 'head': 200,    'heads': 200,
    'sprig': 5,  'sprigs': 5,
    'pinch': 0.5, 'dash': 0.5,
    'handful': 30,
    'package': 100, 'packages': 100,
    'packet': 100,  'packets': 100,
    'stalk': 40,    'stalks': 40,
}

_UNIT_RE = '|'.join(sorted(UNIT_GRAMS.keys(), key=len, reverse=True))


def _parse_number(s):
    s = s.strip()
    # Handle range like "14-16" → take the midpoint
    m = re.match(r'^(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)$', s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    m = re.match(r'^(\d+)\s+(\d+)/(\d+)$', s)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    m = re.match(r'^(\d+)/(\d+)$', s)
    if m:
        return float(m.group(1)) / float(m.group(2))
    try:
        return float(s)
    except ValueError:
        return None


def parse_ingredient_line(raw):
    """
    Parse "2 tablespoon butter or margarine" into
    (measure_only, grams_total, ingredient_remainder).
    """
    text = raw.strip()

    # Extract bracketed metric weight if present
    bracketed_grams = None
    m = re.search(
        r'\(\s*([\d\.]+)\s*(g|ml|oz|ounce|ounces|kg|lb|lbs|pound|pounds)\s*\)',
        text, re.IGNORECASE
    )
    if m:
        val  = float(m.group(1))
        unit = m.group(2).lower()
        if unit in UNIT_GRAMS:
            bracketed_grams = round(val * UNIT_GRAMS[unit], 2)
        text = re.sub(r'\s*\([^)]*\)', '', text).strip()

    # Pattern A: number UNIT ingredient
    m = re.match(
        rf'^(\d+\s+\d+/\d+|\d+/\d+|\d+\.?\d*[-–]\d+\.?\d*|\d+\.?\d*)\s+({_UNIT_RE})\b\s*(.*)',
        text, re.IGNORECASE
    )
    if m:
        qty_str = m.group(1).strip()
        unit    = m.group(2).lower()
        rest    = m.group(3).strip()
        qty     = _parse_number(qty_str)
        if bracketed_grams:
            grams = bracketed_grams
        elif qty and unit in UNIT_GRAMS:
            grams = round(qty * UNIT_GRAMS[unit], 2)
        else:
            grams = None
        return f"{qty_str} {unit}", grams, rest

    # Pattern B: plain number (count items)
    m = re.match(r'^(\d+\.?\d*|\d+/\d+|\d+[-–]\d+)\s+(.*)', text, re.IGNORECASE)
    if m:
        return m.group(1), bracketed_grams, m.group(2).strip()

    return '', bracketed_grams, text


def extract_name_from_remainder(remainder):
    name = remainder.split(',')[0].strip()
    name = re.sub(r'\s+for\s+.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(to\s+taste|as\s+needed|if\s+desired|optional)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\([^)]+\)', '', name).strip()
    return name.strip(' .,')


def extract_form(name):
    from scripts.cleaner import FORM_TOKEN_MAP
    for token in name.lower().split():
        if token in FORM_TOKEN_MAP:
            return FORM_TOKEN_MAP[token]
    return ''


def build_nutrition_key(base, form):
    return f"{base}|{form}" if form else base


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_csv(filepath):
    # utf-8-sig handles files written with BOM (like cheflola_scraped.csv)
    enc = 'utf-8-sig' if 'cheflola' in filepath else 'utf-8'
    with open(filepath, newline='', encoding=enc) as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def load_master(filepath):
    fieldnames, rows = load_csv(filepath)
    index  = {r['ingredient_name'].strip().lower(): r for r in rows}
    max_id = max(int(r['ingredient_id']) for r in rows) if rows else 0
    return fieldnames, rows, index, max_id


def load_mapping(filepath):
    fieldnames, rows = load_csv(filepath)
    index = {r['recipe_ingredient_name'].strip().lower(): r for r in rows}
    return fieldnames, rows, index


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Integrate Chef Lola's Kitchen Recipes (182-225)")
    print('=' * 50)

    from scripts.cleaner import clean_ingredient, extract_base_ingredient
    import pandas as pd
    from scripts.matcher import Matcher

    # Load scraped data
    _, scraped_rows = load_csv(SCRAPED_FILE)
    scraped = {r['recipe_id']: r for r in scraped_rows if r['recipe_id'] not in SKIP_IDS}
    print(f"Scraped recipes to integrate : {len(scraped)}")
    if SKIP_IDS:
        print(f"Skipped (roundup/no card)    : {SKIP_IDS}")

    # Load pipeline files
    recipes_fn,  recipes_rows               = load_csv(RECIPES_FILE)
    rif_fn,      rif_rows                   = load_csv(RIF_FILE)
    master_fn,   master_rows, master_idx, max_ing_id = load_master(MASTER_FILE)
    mapping_fn,  mapping_rows, mapping_idx  = load_mapping(MAPPING_FILE)

    df_ref  = pd.read_csv(MAPPING_REF)
    matcher = Matcher(df_ref)

    print(f"Existing RIF rows            : {len(rif_rows)}")
    print(f"Existing ingredients         : {len(master_rows)}")

    # ── Step 1: Remove old single-ingredient RIF rows for 182-225 ─────────────
    target_ids   = set(scraped.keys())
    rif_kept     = [r for r in rif_rows if r['recipe_id'] not in target_ids]
    removed_rows = len(rif_rows) - len(rif_kept)
    print(f"\nOld placeholder RIF rows removed : {removed_rows}")

    # ── Step 2: Build new RIF rows and any new master/mapping entries ──────────
    new_rif_rows     = []
    new_master_rows  = []
    new_mapping_rows = []
    next_ing_id      = max_ing_id + 1

    stats = {
        'recipes_done'      : 0,
        'ingredients_parsed': 0,
        'ingredients_skip'  : 0,
        'master_reused'     : 0,
        'master_new'        : 0,
        'mapping_reused'    : 0,
        'mapping_matched'   : 0,
        'mapping_no_match'  : 0,
        'has_grams'         : 0,
        'no_grams'          : 0,
    }

    for recipe_id, scraped_recipe in scraped.items():
        raw_ingredients = [
            x.strip()
            for x in scraped_recipe['ingredients'].split(' | ')
            if x.strip()
        ]

        for ing_index, raw_line in enumerate(raw_ingredients, start=1):
            stats['ingredients_parsed'] += 1

            measure_only, grams, remainder = parse_ingredient_line(raw_line)
            raw_name = extract_name_from_remainder(remainder)

            if not raw_name or len(raw_name) < 2:
                stats['ingredients_skip'] += 1
                continue

            cleaned_name, tag, display_name = clean_ingredient(raw_name)

            if not cleaned_name or len(cleaned_name) < 2:
                stats['ingredients_skip'] += 1
                continue

            actual_measure = f"{grams} g" if grams is not None else ''
            if grams is not None:
                stats['has_grams'] += 1
            else:
                stats['no_grams'] += 1

            # Get or create ingredient_id
            name_key = cleaned_name.lower()
            if name_key in master_idx:
                ingredient_id = master_idx[name_key]['ingredient_id']
                stats['master_reused'] += 1
            else:
                ingredient_id = str(next_ing_id)
                next_ing_id  += 1
                base_ing = extract_base_ingredient(cleaned_name)
                form     = extract_form(cleaned_name)
                new_row  = {
                    'ingredient_id'       : ingredient_id,
                    'ingredient_name'     : cleaned_name,
                    'base_ingredient'     : base_ing,
                    'form'                : form,
                    'nutrition_lookup_key': build_nutrition_key(base_ing, form),
                }
                master_idx[name_key] = new_row
                master_rows.append(new_row)
                new_master_rows.append(new_row)
                stats['master_new'] += 1

            # RIF row
            new_rif_rows.append({
                'recipe_id'       : recipe_id,
                'ingredient_id'   : ingredient_id,
                'ingredient_index': str(ing_index),
                'portion_factor'  : '1',
                'actual_measure'  : actual_measure,
                'measure_only'    : measure_only,
            })

            # Get or create USDA mapping
            if name_key in mapping_idx:
                stats['mapping_reused'] += 1
                continue

            food_name, fdc_id, match_type = matcher.match(cleaned_name)
            effective_type = 'african_proxy' if tag == 'african_proxy' else match_type
            mapping_row = {
                'recipe_ingredient_name' : cleaned_name,
                'cleaned_ingredient_name': display_name,
                'matched_fdc_id'         : fdc_id if fdc_id is not None else '',
                'matched_food_name'      : food_name if food_name else '',
                'match_status'           : 'matched' if fdc_id else 'skip',
                'match_type'             : effective_type,
                'notes'                  : 'Added from cheflola scraped data',
            }
            mapping_idx[name_key] = mapping_row
            mapping_rows.append(mapping_row)
            new_mapping_rows.append(mapping_row)
            if fdc_id:
                stats['mapping_matched'] += 1
            else:
                stats['mapping_no_match'] += 1

        stats['recipes_done'] += 1

    # ── Step 3: Update servings in recipes_clean.csv ───────────────────────────
    def parse_servings(raw):
        if not raw or not raw.strip():
            return None
        m = re.search(r'(\d+)', raw)
        return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 100 else None

    servings_updated = 0
    for row in recipes_rows:
        rid = row['recipe_id']
        if rid in scraped:
            new_serv = parse_servings(scraped[rid].get('servings', ''))
            if new_serv:
                row['servings_raw'] = str(new_serv)
                servings_updated += 1

    # ── Step 4: Write all files ────────────────────────────────────────────────
    print('\nWriting updated files...')

    # recipes_clean.csv (rewrite with updated servings)
    with open(RECIPES_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=recipes_fn)
        writer.writeheader()
        writer.writerows(recipes_rows)
    print(f"  recipes_clean.csv          servings updated for {servings_updated} recipes")

    # recipe_ingredient_final.csv (kept + new)
    final_rif = rif_kept + new_rif_rows
    with open(RIF_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rif_fn)
        writer.writeheader()
        writer.writerows(final_rif)
    print(f"  recipe_ingredient_final.csv removed {removed_rows} old rows, added {len(new_rif_rows)} new rows")

    # ingredients_master.csv (append new)
    with open(MASTER_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=master_fn)
        writer.writerows(new_master_rows)
    print(f"  ingredients_master.csv     +{len(new_master_rows)} new ingredients")

    # ingredient_mapping_final.csv (append new)
    with open(MAPPING_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=mapping_fn)
        writer.writerows(new_mapping_rows)
    print(f"  ingredient_mapping_final.csv+{len(new_mapping_rows)} new mappings")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"Recipes integrated        : {stats['recipes_done']}")
    print(f"Ingredient rows added     : {len(new_rif_rows)}")
    print(f"Ingredient rows skipped   : {stats['ingredients_skip']}")
    print(f"New master entries        : {stats['master_new']}")
    print(f"Reused master entries     : {stats['master_reused']}")
    print(f"New mappings matched      : {stats['mapping_matched']}")
    print(f"New mappings unmatched    : {stats['mapping_no_match']}")
    print(f"Ingredient rows w/ grams  : {stats['has_grams']}")
    print(f"Ingredient rows no grams  : {stats['no_grams']}")
    print(f"\nNext: run fix_scraped_mapping.py then calculate_nutrition.py")


if __name__ == '__main__':
    main()
