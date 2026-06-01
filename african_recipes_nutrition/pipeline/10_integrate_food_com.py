"""
10_integrate_food_com.py
========================
Integrates the 784 scraped food.com recipes into the nutrition pipeline.

  1. Reads food_com_scraped.csv
  2. Parses each pipe-delimited ingredient line (quantity, unit, name)
  3. Cleans ingredient names through scripts/cleaner.py
  4. Matches cleaned names to USDA FDC IDs via scripts/matcher.py
  5. Assigns new recipe IDs starting from 517 (after africanbites 338-516)
  6. Appends new rows to:
       data/interim/recipes_clean.csv
       data/interim/ingredients_master.csv
       data/interim/recipe_ingredient_final.csv
       data/interim/ingredient_mapping_final.csv

Run AFTER 09_integrate_africanbites.py.

Run from african_recipes_nutrition/:
    py pipeline/10_integrate_food_com.py
"""

import csv
import os
import re
import sys

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
DATA_RAW     = os.path.join(BASE, 'data', 'raw')
DATA_SCRAPED = os.path.join(BASE, 'data', 'scraped')
sys.path.insert(0, BASE)

SCRAPED_FILE  = os.path.join(DATA_SCRAPED, 'food_com_scraped.csv')
RECIPES_FILE  = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
MASTER_FILE   = os.path.join(DATA_INTERIM, 'ingredients_master.csv')
RIF_FILE      = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
MAPPING_FILE  = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')
MAPPING_REF   = os.path.join(DATA_RAW,     'ingredient_mapping_original.csv')

FIRST_NEW_RECIPE_ID = 517

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
    m = re.match(r'^(\d+\.?\d*)\s*[-]\s*(\d+\.?\d*)$', s)
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
    text = raw.strip()

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

    m = re.match(
        rf'^(\d+\s+\d+/\d+|\d+/\d+|\d+\.?\d*[-]\d+\.?\d*|\d+\.?\d*)\s+({_UNIT_RE})\b\s*(.*)',
        text, re.IGNORECASE
    )
    if m:
        qty_str = m.group(1).strip()
        unit    = m.group(2).lower()
        rest    = m.group(3).strip()
        qty     = _parse_number(qty_str)
        grams   = bracketed_grams if bracketed_grams else (
            round(qty * UNIT_GRAMS[unit], 2) if qty and unit in UNIT_GRAMS else None
        )
        return f"{qty_str} {unit}", grams, rest

    m = re.match(r'^(\d+\.?\d*|\d+/\d+|\d+[-]\d+)\s+(.*)', text, re.IGNORECASE)
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


def load_csv(filepath):
    with open(filepath, newline='', encoding='utf-8-sig') as f:
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


def main():
    print('Integrate Food.com Recipes (IDs 517+)')
    print('=' * 50)

    for path in [SCRAPED_FILE, RECIPES_FILE, MASTER_FILE, RIF_FILE, MAPPING_FILE, MAPPING_REF]:
        if not os.path.exists(path):
            print(f'ERROR: missing file -> {path}')
            sys.exit(1)

    from scripts.cleaner import clean_ingredient, extract_base_ingredient
    import pandas as pd
    from scripts.matcher import Matcher

    _, scraped_rows = load_csv(SCRAPED_FILE)
    print(f'Scraped recipes to integrate : {len(scraped_rows)}')

    recipes_fn,  recipes_rows                        = load_csv(RECIPES_FILE)
    rif_fn,      rif_rows                            = load_csv(RIF_FILE)
    master_fn,   master_rows, master_idx, max_ing_id = load_master(MASTER_FILE)
    mapping_fn,  mapping_rows, mapping_idx           = load_mapping(MAPPING_FILE)

    df_ref  = pd.read_csv(MAPPING_REF)
    matcher = Matcher(df_ref)

    # Guard: abort if IDs 517+ already exist
    existing_ids = {r['recipe_id'] for r in recipes_rows}
    if str(FIRST_NEW_RECIPE_ID) in existing_ids:
        print(f'ERROR: recipe_id {FIRST_NEW_RECIPE_ID} already exists — script may have already run.')
        sys.exit(1)

    # Also check that africanbites was integrated first
    if str(FIRST_NEW_RECIPE_ID - 1) not in existing_ids:
        print(f'ERROR: recipe_id {FIRST_NEW_RECIPE_ID - 1} not found.')
        print('Run 09_integrate_africanbites.py first.')
        sys.exit(1)

    print(f'Existing recipes             : {len(recipes_rows)}')
    print(f'Existing ingredients         : {len(master_rows)}')

    new_recipe_rows  = []
    new_rif_rows     = []
    new_master_rows  = []
    new_mapping_rows = []

    next_recipe_id = FIRST_NEW_RECIPE_ID
    next_ing_id    = max_ing_id + 1

    stats = {
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

    for i, scraped_recipe in enumerate(scraped_rows, start=1):
        recipe_id = str(next_recipe_id)
        next_recipe_id += 1

        if i % 100 == 0:
            print(f'  Processing {i}/{len(scraped_rows)}...')

        new_recipe_rows.append({
            'recipe_id'   : recipe_id,
            'recipe_name' : scraped_recipe['recipe_title'].strip().upper(),
            'cuisine'     : '',
            'servings_raw': scraped_recipe['servings'].strip(),
            'recipe_url'  : scraped_recipe['source_url'].strip(),
            'instructions': '',
        })

        raw_ingredients = [
            x.strip() for x in scraped_recipe['ingredients'].split('|') if x.strip()
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
            stats['has_grams' if grams is not None else 'no_grams'] += 1

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

            new_rif_rows.append({
                'recipe_id'       : recipe_id,
                'ingredient_id'   : ingredient_id,
                'ingredient_index': str(ing_index),
                'portion_factor'  : '1',
                'actual_measure'  : actual_measure,
                'measure_only'    : measure_only,
            })

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
                'notes'                  : 'Added from food.com scraped data',
            }
            mapping_idx[name_key] = mapping_row
            mapping_rows.append(mapping_row)
            new_mapping_rows.append(mapping_row)
            stats['mapping_matched' if fdc_id else 'mapping_no_match'] += 1

    print('\nWriting updated files...')

    with open(RECIPES_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=recipes_fn)
        writer.writerows(new_recipe_rows)
    print(f'  recipes_clean.csv           +{len(new_recipe_rows)} rows')

    with open(MASTER_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=master_fn)
        writer.writerows(new_master_rows)
    print(f'  ingredients_master.csv      +{len(new_master_rows)} new ingredients')

    with open(RIF_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rif_fn)
        writer.writerows(new_rif_rows)
    print(f'  recipe_ingredient_final.csv +{len(new_rif_rows)} rows')

    with open(MAPPING_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=mapping_fn)
        writer.writerows(new_mapping_rows)
    print(f'  ingredient_mapping_final.csv+{len(new_mapping_rows)} new mappings')

    print(f"\n{'=' * 50}")
    print(f'Recipes added               : {len(new_recipe_rows)}')
    print(f'Recipe IDs assigned         : {FIRST_NEW_RECIPE_ID} - {next_recipe_id - 1}')
    print(f'Ingredient lines parsed     : {stats["ingredients_parsed"]}')
    print(f'Ingredient lines skipped    : {stats["ingredients_skip"]}')
    print(f'New ingredients in master   : {stats["master_new"]}')
    print(f'Reused existing master      : {stats["master_reused"]}')
    print(f'New mappings matched        : {stats["mapping_matched"]}')
    print(f'New mappings unmatched      : {stats["mapping_no_match"]}')
    print(f'Ingredient rows with grams  : {stats["has_grams"]}')
    print(f'Ingredient rows no grams    : {stats["no_grams"]}')
    print(f'\nNext: run 08_calculate_nutrition.py to refresh recipe_nutrition.csv')


if __name__ == '__main__':
    main()
