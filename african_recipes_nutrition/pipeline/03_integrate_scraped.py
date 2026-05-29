"""
integrate_scraped.py
====================
Integrates the 59 scraped allrecipes.com recipes into the nutrition pipeline.

What this script does:
  1. Reads african_recipes_dataset.csv (59 scraped recipes)
  2. Parses each pipe-delimited ingredient line:
       - extracts the leading quantity  → stored in measure_only / actual_measure
       - extracts the ingredient name   → cleaned through scripts/cleaner.py
  3. Matches cleaned names to USDA FDC IDs via scripts/matcher.py
  4. Assigns new recipe IDs (279–337) and ingredient IDs (from 672 onward)
  5. Appends new rows to:
       data_clean/recipes_clean.csv          (59 new recipe rows)
       data_clean/ingredients_master.csv     (new unique ingredients only)
       data_clean/recipe_ingredient_final.csv
       ingredient_mapping_final.csv          (new mappings only)

After this script finishes, run calculate_nutrition.py to produce
recipe_nutrition.csv for all 336 recipes.

Run from african_recipes_nutrition/:
    py integrate_scraped.py
"""

import csv
import os
import re
import sys

# ── Paths ──────────────────────────────────────────────────────────────────────

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
DATA_RAW     = os.path.join(BASE, 'data', 'raw')
DATA_SCRAPED = os.path.join(BASE, 'data', 'scraped')
DATA_OUTPUT  = os.path.join(BASE, 'data', 'outputs')
sys.path.insert(0, BASE)

SCRAPED_FILE  = os.path.join(DATA_SCRAPED, 'african_recipes_dataset.csv')
RECIPES_FILE  = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
MASTER_FILE   = os.path.join(DATA_INTERIM, 'ingredients_master.csv')
RIF_FILE      = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
MAPPING_FILE  = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')
MAPPING_REF   = os.path.join(DATA_RAW,  'ingredient_mapping_original.csv')

FIRST_NEW_RECIPE_ID = 279

# ── Unit → grams conversion ────────────────────────────────────────────────────

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

# Build unit regex (longest first avoids prefix shadowing)
_UNIT_RE = '|'.join(sorted(UNIT_GRAMS.keys(), key=len, reverse=True))


# ── Ingredient line parser ─────────────────────────────────────────────────────

def _parse_number(s):
    """'1', '1/2', '1 1/2', '1.5'  →  float or None."""
    s = s.strip()
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
    Split a raw ingredient string into its quantity and ingredient parts.

    Examples:
      "1/2 cup vegetable oil for frying"
          → measure_only="1/2 cup"  grams=120.0  remainder="vegetable oil for frying"
      "3 pounds cod fillets, cut into portions"
          → measure_only="3 pounds" grams=1362.0 remainder="cod fillets, cut into portions"
      "2 large onions, sliced"
          → measure_only="2 large"  grams=300.0  remainder="onions, sliced"
      "salt to taste"
          → measure_only=""          grams=None   remainder="salt to taste"

    Returns (measure_only, grams_total, remainder).
    """
    text = raw.strip()

    # Extract and use bracketed metric weight if present: "(14 oz)", "(480 ml)", "(400 g)"
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

    # Pattern A: "number [fraction] UNIT ingredient"
    m = re.match(
        rf'^(\d+\s+\d+/\d+|\d+/\d+|\d+\.?\d*)\s+({_UNIT_RE})\b\s*(.*)',
        text, re.IGNORECASE
    )
    if m:
        qty_str  = m.group(1).strip()
        unit     = m.group(2).lower()
        rest     = m.group(3).strip()
        qty      = _parse_number(qty_str)
        if bracketed_grams:
            grams = bracketed_grams
        elif qty and unit in UNIT_GRAMS:
            grams = round(qty * UNIT_GRAMS[unit], 2)
        else:
            grams = None
        return f"{qty_str} {unit}", grams, rest

    # Pattern B: plain number only (count items: "2 eggs", "1 onion")
    m = re.match(r'^(\d+\.?\d*|\d+/\d+)\s+(.*)', text, re.IGNORECASE)
    if m:
        qty_str = m.group(1)
        rest    = m.group(2).strip()
        return qty_str, bracketed_grams, rest

    # No quantity: "salt to taste"
    return '', bracketed_grams, text


def extract_name_from_remainder(remainder):
    """
    'vegetable oil for frying'  →  'vegetable oil'
    'cod fillets, cut into 2 to 3 ounce portions'  →  'cod fillets'
    'onions, peeled and sliced into rings'  →  'onions'
    """
    name = remainder.split(',')[0].strip()
    name = re.sub(r'\s+for\s+.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(to\s+taste|as\s+needed|if\s+desired)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s{2,}', ' ', name).strip(' .,')
    return name


# ── Data loaders ───────────────────────────────────────────────────────────────

def load_recipes(filepath):
    """Returns {recipe_id_str: row} from recipes_clean.csv."""
    with open(filepath, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    return {r['recipe_id']: r for r in rows}, rows


def load_master(filepath):
    """Returns ({name_lower: row}, rows, max_id)."""
    with open(filepath, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    index = {r['ingredient_name'].strip().lower(): r for r in rows}
    max_id = max(int(r['ingredient_id']) for r in rows) if rows else 0
    return index, rows, max_id


def load_rif(filepath):
    """Returns list of all rows from recipe_ingredient_final.csv."""
    with open(filepath, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_mapping(filepath):
    """Returns ({name_lower: row}, rows) from ingredient_mapping_final.csv."""
    with open(filepath, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    index = {r['recipe_ingredient_name'].strip().lower(): r for r in rows}
    return index, rows


def load_scraped(filepath):
    """Returns list of scraped recipe dicts."""
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


# ── Helpers ────────────────────────────────────────────────────────────────────

def extract_form(name):
    """Pull the first form descriptor from a name ('ground', 'dried', etc.)."""
    from scripts.cleaner import FORM_TOKEN_MAP
    for token in name.lower().split():
        if token in FORM_TOKEN_MAP:
            return FORM_TOKEN_MAP[token]
    return ''


def build_nutrition_key(base, form):
    return f"{base}|{form}" if form else base


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("African Recipes — Integrate 59 Scraped Recipes")
    print("=" * 50)

    # Verify required files
    for path in [SCRAPED_FILE, RECIPES_FILE, MASTER_FILE, RIF_FILE, MAPPING_FILE, MAPPING_REF]:
        if not os.path.exists(path):
            print(f"ERROR: missing file → {path}")
            sys.exit(1)

    # ── Import pipeline modules ────────────────────────────────────────────────
    from scripts.cleaner import clean_ingredient, extract_base_ingredient
    import pandas as pd
    from scripts.matcher import Matcher

    print("\nLoading existing pipeline data...")
    _, existing_recipe_rows,  = load_recipes(RECIPES_FILE)
    existing_recipe_ids       = {r['recipe_id'] for r in existing_recipe_rows}

    master_index, master_rows, max_ing_id = load_master(MASTER_FILE)
    rif_rows                              = load_rif(RIF_FILE)
    mapping_index, mapping_rows           = load_mapping(MAPPING_FILE)

    df_ref  = pd.read_csv(MAPPING_REF)
    matcher = Matcher(df_ref)

    scraped = load_scraped(SCRAPED_FILE)

    print(f"  Existing recipes          : {len(existing_recipe_ids)}")
    print(f"  Existing ingredients      : {len(master_rows)}")
    print(f"  Existing RIF rows         : {len(rif_rows)}")
    print(f"  Existing mapping entries  : {len(mapping_rows)}")
    print(f"  Scraped recipes to add    : {len(scraped)}")

    # ── Build new rows ─────────────────────────────────────────────────────────
    new_recipe_rows  = []
    new_master_rows  = []
    new_rif_rows     = []
    new_mapping_rows = []

    next_recipe_id = FIRST_NEW_RECIPE_ID
    next_ing_id    = max_ing_id + 1

    stats = {
        'ingredients_parsed'    : 0,
        'ingredients_skipped'   : 0,
        'master_reused'         : 0,
        'master_new'            : 0,
        'mapping_reused'        : 0,
        'mapping_new_matched'   : 0,
        'mapping_new_no_match'  : 0,
        'has_grams'             : 0,
        'no_grams'              : 0,
    }

    for scraped_recipe in scraped:
        recipe_id   = str(next_recipe_id)
        next_recipe_id += 1

        title    = scraped_recipe['recipe_title'].strip()
        servings = scraped_recipe['servings'].strip()
        url      = scraped_recipe['source_url'].strip()

        new_recipe_rows.append({
            'recipe_id'   : recipe_id,
            'recipe_name' : title.upper(),
            'cuisine'     : '',
            'servings_raw': servings,
            'recipe_url'  : url,
            'instructions': '',
        })

        raw_ingredients = [
            x.strip()
            for x in scraped_recipe['ingredients'].split('|')
            if x.strip()
        ]

        for ing_index, raw_line in enumerate(raw_ingredients, start=1):
            stats['ingredients_parsed'] += 1

            # ── Parse measure and name ────────────────────────────────────────
            measure_only, grams, remainder = parse_ingredient_line(raw_line)
            raw_name = extract_name_from_remainder(remainder)

            if not raw_name or len(raw_name) < 2:
                stats['ingredients_skipped'] += 1
                continue

            # ── Clean through pipeline cleaner ────────────────────────────────
            cleaned_name, tag, display_name = clean_ingredient(raw_name)

            if not cleaned_name or len(cleaned_name) < 2:
                stats['ingredients_skipped'] += 1
                continue

            # ── actual_measure (gram string for fallback in calculator) ───────
            if grams is not None:
                actual_measure = f"{grams} g"
                stats['has_grams'] += 1
            else:
                actual_measure = ''
                stats['no_grams'] += 1

            # ── Get or create ingredient_id ───────────────────────────────────
            name_key = cleaned_name.lower()

            if name_key in master_index:
                ingredient_id = master_index[name_key]['ingredient_id']
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
                master_index[name_key] = new_row
                master_rows.append(new_row)
                new_master_rows.append(new_row)
                stats['master_new'] += 1

            # ── Add recipe_ingredient_final row ───────────────────────────────
            new_rif_rows.append({
                'recipe_id'      : recipe_id,
                'ingredient_id'  : ingredient_id,
                'ingredient_index': str(ing_index),
                'portion_factor' : '1',
                'actual_measure' : actual_measure,
                'measure_only'   : measure_only,
            })

            # ── Get or create USDA mapping ────────────────────────────────────
            if name_key in mapping_index:
                stats['mapping_reused'] += 1
                continue

            # Match via pipeline matcher
            food_name, fdc_id, match_type = matcher.match(cleaned_name)

            # Override match_type for African proxies
            effective_match_type = 'african_proxy' if tag == 'african_proxy' else match_type

            mapping_row = {
                'recipe_ingredient_name' : cleaned_name,
                'cleaned_ingredient_name': display_name,
                'matched_fdc_id'         : fdc_id if fdc_id is not None else '',
                'matched_food_name'      : food_name if food_name else '',
                'match_status'           : 'matched' if fdc_id else 'skip',
                'match_type'             : effective_match_type,
                'notes'                  : 'Added from scraped allrecipes data',
            }
            mapping_index[name_key] = mapping_row
            mapping_rows.append(mapping_row)
            new_mapping_rows.append(mapping_row)

            if fdc_id:
                stats['mapping_new_matched'] += 1
            else:
                stats['mapping_new_no_match'] += 1

    # ── Write all files ────────────────────────────────────────────────────────
    print("\nWriting updated files...")

    # recipes_clean.csv — append
    recipes_fieldnames = ['recipe_id', 'recipe_name', 'cuisine', 'servings_raw', 'recipe_url', 'instructions']
    with open(RECIPES_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=recipes_fieldnames)
        writer.writerows(new_recipe_rows)
    print(f"  recipes_clean.csv          +{len(new_recipe_rows)} rows")

    # ingredients_master.csv — append
    master_fieldnames = ['ingredient_id', 'ingredient_name', 'base_ingredient', 'form', 'nutrition_lookup_key']
    with open(MASTER_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=master_fieldnames)
        writer.writerows(new_master_rows)
    print(f"  ingredients_master.csv     +{len(new_master_rows)} rows")

    # recipe_ingredient_final.csv — append
    rif_fieldnames = ['recipe_id', 'ingredient_id', 'ingredient_index', 'portion_factor', 'actual_measure', 'measure_only']
    with open(RIF_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rif_fieldnames)
        writer.writerows(new_rif_rows)
    print(f"  recipe_ingredient_final.csv+{len(new_rif_rows)} rows")

    # ingredient_mapping_final.csv — append
    mapping_fieldnames = ['recipe_ingredient_name', 'cleaned_ingredient_name', 'matched_fdc_id',
                          'matched_food_name', 'match_status', 'match_type', 'notes']
    with open(MAPPING_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=mapping_fieldnames)
        writer.writerows(new_mapping_rows)
    print(f"  ingredient_mapping_final.csv+{len(new_mapping_rows)} rows")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print("DONE")
    print(f"  Recipes added             : {len(new_recipe_rows)}")
    print(f"  Ingredient lines parsed   : {stats['ingredients_parsed']}")
    print(f"  Ingredient lines skipped  : {stats['ingredients_skipped']}")
    print(f"  New ingredients in master : {stats['master_new']}")
    print(f"  Reused existing master    : {stats['master_reused']}")
    print(f"  New mappings matched      : {stats['mapping_new_matched']}")
    print(f"  New mappings unmatched    : {stats['mapping_new_no_match']}")
    print(f"  Ingredient rows with grams: {stats['has_grams']}")
    print(f"  Ingredient rows no grams  : {stats['no_grams']}")
    print(f"\nNext step: run calculate_nutrition.py to get nutrition for all 336 recipes.")


if __name__ == '__main__':
    main()
