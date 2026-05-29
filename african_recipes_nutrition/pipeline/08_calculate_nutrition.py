"""
calculate_nutrition.py
======================
Calculates per-serving nutrition for every recipe.

It combines four data sources:

  1. ingredient_measures.csv       — gram weights we just extracted from the
                                     original recipe text (covers 68 recipes)
  2. recipe_ingredient_final.csv   — covers all 277 recipes; has ingredient_id
                                     links and fallback measures
  3. ingredient_mapping_final.csv  — connects ingredient names → USDA fdc_id
  4. food_nutrient.csv             — USDA nutrition per 100g of food
  5. recipes_clean.csv             — servings count per recipe

For each recipe the output shows PER SERVING values for:
  energy (kcal), protein (g), fat (g), carbohydrates (g),
  sugars (g), sodium (mg)

How the maths works (explained simply):
  ─────────────────────────────────────────────────────────────────
  USDA stores all nutrients as "amount per 100g of food".

  So for an ingredient where we used 200g:
    nutrient_contribution = (200 ÷ 100) × nutrient_per_100g
                          = 2 × nutrient_per_100g

  We sum those contributions for every ingredient in the recipe
  to get the TOTAL nutrient amount for the whole recipe.

  Then we divide by servings to get the PER SERVING amount:
    per_serving = total_recipe_nutrient ÷ servings
  ─────────────────────────────────────────────────────────────────

OUTPUT : recipe_nutrition.csv

How to run:
    python calculate_nutrition.py
"""

import csv
import re
import os

# ── File paths ────────────────────────────────────────────────────────────────
BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
DATA_RAW     = os.path.join(BASE, 'data', 'raw')
DATA_OUTPUT  = os.path.join(BASE, 'data', 'outputs')

MEASURES_FILE  = os.path.join(DATA_INTERIM, 'ingredient_measures.csv')
RIF_FILE       = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
MAPPING_FILE   = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')
NUTRIENT_FILE  = os.path.join(DATA_RAW,     'food_nutrient.csv')
MASTER_FILE    = os.path.join(DATA_INTERIM, 'ingredients_master.csv')
RECIPES_FILE   = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
OUTPUT_FILE    = os.path.join(DATA_OUTPUT,  'recipe_nutrition.csv')

# ── USDA nutrient IDs ─────────────────────────────────────────────────────────
NUTRIENT_IDS = {
    203: "protein_g",
    204: "fat_g",
    205: "carbohydrate_g",
    208: "energy_kcal",
    269: "sugars_g",
    307: "sodium_mg",
}

# ── Unit → grams fallback conversion (used for rif rows without gram data) ───
UNIT_GRAMS = {
    "tsp": 5,    "teaspoon": 5,    "teaspoons": 5,
    "tbsp": 15,  "tablespoon": 15, "tablespoons": 15,
    "cup": 240,  "cups": 240,
    "ml": 1,
    "l": 1000,
}

UNICODE_FRACTIONS = {
    "¼": "0.25", "½": "0.5", "¾": "0.75",
    "⅓": "0.333", "⅔": "0.667",
}

COUNT_GRAMS = {
    "large": 150, "medium": 110, "small": 70,
    "clove": 4,   "cloves": 4,
    "piece": 100, "pieces": 100,
    "slice": 30,  "slices": 30,
    "egg": 55,    "eggs": 55,
    "bunch": 100, "head": 200,
}


# ── Servings parser ───────────────────────────────────────────────────────────
def parse_servings(raw):
    """
    Reads a servings string and returns an integer.
    "MAKES 4 TO 6 SERVINGS" → 5  (midpoint)
    "6 servings"             → 6
    "4"                      → 4
    Garbage / blank          → 4  (safe default)
    """
    if not raw or not raw.strip():
        return 4
    text = raw.strip().upper()

    m = re.search(r'(\d+)\s*TO\s*(\d+)', text)
    if m:
        return round((int(m.group(1)) + int(m.group(2))) / 2)

    m = re.search(r'(\d+)\s*[–\-]\s*(\d+)', text)
    if m:
        return int(m.group(1))

    m = re.search(r'(\d+)', text)
    if m:
        val = int(m.group(1))
        if 'LOAF' in text or 'CUP' in text:
            return 8
        if 1 <= val <= 50:
            return val

    return 4


# ── Fallback gram parser for rif rows ────────────────────────────────────────
def parse_grams_fallback(actual_measure, measure_only):
    """
    Used for recipes not in ingredient_measures.csv.
    Tries actual_measure first (e.g. "211 g"), then measure_only ("1 cup").
    Returns float or None.
    """
    # Try actual_measure
    if actual_measure and actual_measure.strip():
        m = re.match(r'^([\d\.]+)\s*(g|ml)\b', actual_measure.strip(), re.IGNORECASE)
        if m:
            return float(m.group(1))

    # Try measure_only
    if not measure_only or not measure_only.strip():
        return None

    text = measure_only.strip().lower()
    for uc, dec in UNICODE_FRACTIONS.items():
        text = text.replace(uc, dec)

    # Parse leading number
    m = re.match(r'^(\d+\.?\d*)\s+(\d+)/(\d+)\s*(.*)', text)
    if m:
        qty  = float(m.group(1)) + float(m.group(2)) / float(m.group(3))
        rest = m.group(4)
    else:
        m = re.match(r'^(\d+)/(\d+)\s*(.*)', text)
        if m:
            qty  = float(m.group(1)) / float(m.group(2))
            rest = m.group(3)
        else:
            m = re.match(r'^(\d+\.?\d*)\s*(.*)', text)
            if m:
                qty  = float(m.group(1))
                rest = m.group(2)
            else:
                return None

    unit = rest.split()[0].rstrip('.,') if rest.split() else ''

    if unit in UNIT_GRAMS:
        return qty * UNIT_GRAMS[unit]
    if unit in COUNT_GRAMS:
        return qty * COUNT_GRAMS[unit]

    return None


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_measures(filepath):
    """
    Returns { (recipe_id, ingredient_index) : grams_per_serving_float }
    Only includes rows where grams_per_serving is not blank.
    """
    measures = {}
    if not os.path.exists(filepath):
        return measures
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            gps = row['grams_per_serving'].strip()
            if gps:
                key = (row['recipe_id'].strip(), row['ingredient_index'].strip())
                measures[key] = float(gps)
    return measures


def load_rif(filepath):
    """Returns list of all recipe-ingredient rows."""
    with open(filepath, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_ingredient_mapping(filepath):
    """Returns { ingredient_name_lower : fdc_id_int }"""
    mapping = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['match_status'].strip() != 'matched':
                continue
            fdc_raw = row['matched_fdc_id'].strip()
            if not fdc_raw or fdc_raw.lower() in ('nan', 'null', 'none', ''):
                continue
            try:
                fdc_id = int(float(fdc_raw))
                name   = row['recipe_ingredient_name'].strip().lower()
                mapping[name] = fdc_id
            except ValueError:
                continue
    return mapping


def load_master(filepath):
    """Returns { ingredient_id_int : ingredient_name_lower }"""
    master = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                ing_id = int(row['ingredient_id'].strip())
                master[ing_id] = row['ingredient_name'].strip().lower()
            except (ValueError, KeyError):
                continue
    return master


def load_food_nutrients(filepath):
    """
    Returns { fdc_id_int : { nutrient_id_int : amount_per_100g } }
    Only loads the 6 nutrients we need to keep it fast.
    """
    nutrients = {}
    target_ids = set(NUTRIENT_IDS.keys())
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                nutrient_id = int(float(row.get('nutrient_id', '').strip()))
            except ValueError:
                continue
            if nutrient_id not in target_ids:
                continue
            try:
                fdc_id = int(float(row.get('fdc_id', '').strip()))
                amount = float(row.get('amount', '0') or 0)
            except ValueError:
                continue
            nutrients.setdefault(fdc_id, {})[nutrient_id] = amount
    return nutrients


def load_servings(filepath):
    """Returns { recipe_id_str : servings_int }"""
    servings = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rid = row['recipe_id'].strip()
            servings[rid] = parse_servings(row['servings_raw'].strip())
    return servings


# ── Core calculation ──────────────────────────────────────────────────────────

def calculate(rif_rows, measures, master, mapping, food_nutrients, servings_map):
    """
    For each recipe, loops through its ingredients and calculates
    total nutrients, then divides by servings for per-serving values.

    Returns list of result dicts.
    """
    # Group rif rows by recipe_id
    recipes = {}
    for row in rif_rows:
        recipes.setdefault(row['recipe_id'].strip(), []).append(row)

    results        = []
    skip_no_grams  = 0
    skip_no_fdc    = 0
    skip_no_usda   = 0
    used_extracted = 0
    used_fallback  = 0

    for recipe_id, ingredients in recipes.items():
        servings = servings_map.get(recipe_id, 4)

        # Accumulate raw totals for the WHOLE recipe
        totals = {col: 0.0 for col in NUTRIENT_IDS.values()}
        used   = 0

        for row in ingredients:
            ing_index = row['ingredient_index'].strip()
            key = (recipe_id, ing_index)

            # ── Step A: get gram weight per serving ──────────────────────────
            # First choice: use the extracted value (grams_per_serving)
            # from ingredient_measures.csv — this came directly from the
            # original recipe text and is already divided by servings.
            if key in measures:
                grams_per_serving = measures[key]
                used_extracted += 1

            else:
                # Fallback: use recipe_ingredient_final measures and
                # divide by servings ourselves
                raw_grams = parse_grams_fallback(
                    row.get('actual_measure', ''),
                    row.get('measure_only', '')
                )
                if raw_grams is None:
                    skip_no_grams += 1
                    continue
                grams_per_serving = raw_grams / servings
                used_fallback += 1

            # ── Step B: look up this ingredient's USDA fdc_id ────────────────
            try:
                ing_id = int(row['ingredient_id'].strip())
            except ValueError:
                skip_no_fdc += 1
                continue

            ing_name = master.get(ing_id)
            if ing_name is None:
                skip_no_fdc += 1
                continue

            fdc_id = mapping.get(ing_name)
            if fdc_id is None:
                skip_no_fdc += 1
                continue

            # ── Step C: get USDA nutrient data ───────────────────────────────
            food_data = food_nutrients.get(fdc_id)
            if food_data is None:
                skip_no_usda += 1
                continue

            # ── Step D: scale nutrients by gram weight ───────────────────────
            #
            # The formula:
            #   nutrient_per_serving = (grams_per_serving ÷ 100) × nutrient_per_100g
            #
            # Why ÷ 100?
            #   Because USDA lists nutrients per 100g.
            #   If we have 50g of an ingredient, we use 50% of the
            #   per-100g values → multiply by (50 ÷ 100) = 0.5
            #
            scale = grams_per_serving / 100.0
            for nutrient_id, col_name in NUTRIENT_IDS.items():
                totals[col_name] += scale * food_data.get(nutrient_id, 0.0)

            used += 1

        results.append({
            'recipe_id'         : recipe_id,
            'servings'          : servings,
            'ingredients_total' : len(ingredients),
            'ingredients_used'  : used,
            # Round to sensible precision
            'energy_kcal'       : round(totals['energy_kcal'],    1),
            'protein_g'         : round(totals['protein_g'],      1),
            'fat_g'             : round(totals['fat_g'],          1),
            'carbohydrate_g'    : round(totals['carbohydrate_g'], 1),
            'sugars_g'          : round(totals['sugars_g'],       1),
            'sodium_mg'         : round(totals['sodium_mg'],      1),
        })

    print(f"\n  Used extracted measures  : {used_extracted}")
    print(f"  Used fallback measures   : {used_fallback}")
    print(f"  Skipped (no gram weight) : {skip_no_grams}")
    print(f"  Skipped (no fdc mapping) : {skip_no_fdc}")
    print(f"  Skipped (no USDA data)   : {skip_no_usda}")

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':

    required = [RIF_FILE, MAPPING_FILE, NUTRIENT_FILE, MASTER_FILE, RECIPES_FILE]
    print("African Recipes — Nutrition Calculator (per serving)")
    print("=" * 52)

    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        for f in missing:
            print(f"  ERROR: missing file → {f}")
        exit(1)

    print("\nLoading data...")
    measures       = load_measures(MEASURES_FILE)
    rif_rows       = load_rif(RIF_FILE)
    mapping        = load_ingredient_mapping(MAPPING_FILE)
    master         = load_master(MASTER_FILE)
    food_nutrients = load_food_nutrients(NUTRIENT_FILE)
    servings_map   = load_servings(RECIPES_FILE)

    print(f"  ingredient measures      : {len(measures)} rows (from original text)")
    print(f"  rif rows                 : {len(rif_rows)}")
    print(f"  ingredient mappings      : {len(mapping)}")
    print(f"  USDA foods with data     : {len(food_nutrients)}")

    print("\nCalculating nutrition per serving...")
    results = calculate(rif_rows, measures, master, mapping, food_nutrients, servings_map)

    # Write CSV
    fieldnames = [
        'recipe_id', 'servings', 'ingredients_total', 'ingredients_used',
        'energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'sugars_g', 'sodium_mg'
    ]
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Coverage stat
    coverage_vals = [
        r['ingredients_used'] / r['ingredients_total']
        for r in results if r['ingredients_total'] > 0
    ]
    avg_coverage = sum(coverage_vals) / len(coverage_vals) * 100 if coverage_vals else 0

    print(f"\nDone! {len(results)} recipes calculated")
    print(f"  Average ingredient coverage : {avg_coverage:.0f}%")
    print(f"  Output saved to             : {OUTPUT_FILE}")

    # Print preview table
    print(f"\n{'':>2} {'Recipe':>8} | {'Serv':>4} | {'kcal':>7} | {'Protein':>7} | {'Fat':>6} | {'Carbs':>7} | {'Cov%':>5}")
    print("  " + "-" * 58)
    for r in results[:8]:
        cov = r['ingredients_used'] / r['ingredients_total'] * 100 if r['ingredients_total'] else 0
        print(f"  {r['recipe_id']:>8} | {r['servings']:>4} | "
              f"{r['energy_kcal']:>7.0f} | {r['protein_g']:>6.1f}g | "
              f"{r['fat_g']:>5.1f}g | {r['carbohydrate_g']:>6.1f}g | {cov:>4.0f}%")
