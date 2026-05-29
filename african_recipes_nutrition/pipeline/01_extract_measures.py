"""
extract_measures.py
===================
Reads the original ingredient lines from merged_recipes_updated.csv and
extracts a gram weight for every ingredient in every recipe.

It also parses the number of servings for each recipe so that the
nutrition calculator can divide totals by servings to get per-serving values.

The extraction works in priority order — it always tries the most
accurate method first and falls back to estimates:

  Priority 1 — Bracketed metric already in the line
      "1 cup (211 g) basmati rice"        → 211 g
      "2 tbsp (30 ml) olive oil"          → 30 g  (ml treated as g)
      "3 lb (1.4 kg) chicken"             → 1400 g
      "1 (16-oz [448-g]) can tomatoes"    → 448 g

  Priority 2 — Leading metric (no brackets)
      "200g/7oz cherry tomatoes"          → 200 g
      "325ml/11oz vegetable oil"          → 325 g
      "1kg/2lb sweet potatoes"            → 1000 g

  Priority 3 — Pound/lb in text
      "1 pound ground beef"               → 454 g
      "2½ lb sirloin steak"              → 1134 g

  Priority 4 — Volume unit conversion
      "2 tsp salt"                        → 10 g   (2 × 5)
      "1 tbsp olive oil"                  → 15 g
      "2 cups rice"                       → 480 g

  Priority 5 — Count with size word
      "1 large onion"                     → 150 g
      "2 cloves garlic"                   → 6 g

  No match — weight is left blank (these are things like "to taste",
             "as needed", bouillon cubes, garnishes)

INPUT  : merged_recipes_updated.csv
         recipe_ingredient_final.csv
         recipes_clean.csv
OUTPUT : ingredient_measures.csv
"""

import csv
import re
import os

# ── File paths ────────────────────────────────────────────────────────────────
BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW     = os.path.join(BASE, 'data', 'raw')
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')

MERGED_FILE  = os.path.join(DATA_RAW,     'merged_recipes_updated.csv')
RIF_FILE     = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
CLEAN_FILE   = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
OUTPUT_FILE  = os.path.join(DATA_INTERIM, 'ingredient_measures.csv')

# ── Unit conversion table (unit → grams) ─────────────────────────────────────
# These are cooking averages. Volumes assume ~1g per ml (water-like density).
UNIT_GRAMS = {
    "tsp": 5,    "teaspoon": 5,   "teaspoons": 5,
    "tbsp": 15,  "tablespoon": 15, "tablespoons": 15,
    "cup": 240,  "cups": 240,
    "ml": 1,
    "l": 1000,   "litre": 1000,   "liter": 1000,
    "oz": 28.35,
    "pound": 454, "pounds": 454, "lb": 454, "lbs": 454,
}

# Count-based items: when a recipe says "1 large onion", "2 cloves garlic"
# these are the gram estimates per single item
COUNT_GRAMS = {
    "large":    150,
    "medium":   110,
    "small":    70,
    "clove":    4,
    "cloves":   4,
    "piece":    100,
    "pieces":   100,
    "slice":    30,
    "slices":   30,
    "punnet":   200,
    "bunch":    100,
    "sprig":    5,
    "sprigs":   5,
    "leaf":     2,
    "leaves":   3,
    "stalk":    40,
    "stalks":   40,
    "head":     200,
    "can":      400,
    "tin":      400,
    "packet":   7,
    "egg":      55,
    "eggs":     55,
}

# Unicode fractions → float
UNICODE_FRACTIONS = {
    "¼": 0.25, "½": 0.5, "¾": 0.75,
    "⅓": 0.333, "⅔": 0.667,
    "⅛": 0.125,
}

# ── Helper: parse a leading number (handles "2", "1.5", "½", "2½", "1 1/2") ──
def parse_leading_number(text):
    """
    Reads the number at the start of a string.
    Handles: integers, decimals, unicode fractions, slash fractions, mixed numbers.
    Returns (float_value, remaining_text) or (None, original_text) on failure.
    """
    text = text.strip()

    # Replace unicode fractions with their decimal strings
    for uc, val in UNICODE_FRACTIONS.items():
        text = text.replace(uc, f" {val} ")
    text = re.sub(r'\s+', ' ', text).strip()

    # Pattern: optional whole number, optional fraction (e.g. "1 1/2" or "0.5" or "2")
    m = re.match(
        r'^(\d+\.?\d*)\s+(\d+)/(\d+)\s*(.*)',  # "1 1/2 cups"
        text
    )
    if m:
        whole = float(m.group(1))
        frac  = float(m.group(2)) / float(m.group(3))
        return whole + frac, m.group(4).strip()

    m = re.match(r'^(\d+)/(\d+)\s*(.*)', text)   # "1/2 cup"
    if m:
        return float(m.group(1)) / float(m.group(2)), m.group(3).strip()

    m = re.match(r'^(\d+\.?\d*)\s*(.*)', text)   # "2" or "1.5"
    if m:
        return float(m.group(1)), m.group(2).strip()

    # Check if text starts with a decimal fraction we replaced
    m = re.match(r'^(0\.\d+)\s*(.*)', text)
    if m:
        return float(m.group(1)), m.group(2).strip()

    return None, text


# ── PRIORITY 1: Extract from bracketed metric "(211 g)" or "[448-g]" ──────────
def extract_bracketed_metric(raw):
    """
    Finds a bracketed gram or ml value and returns grams.
    Handles: (211 g), (480 ml), (1.4 kg), [448-g], [7-g]
    """
    # Pattern: (number unit) — parentheses style
    m = re.search(r'\(\s*([\d\.]+)\s*(g|ml|kg|l)\s*\)', raw, re.IGNORECASE)
    if m:
        val  = float(m.group(1))
        unit = m.group(2).lower()
        if unit == 'g':   return val
        if unit == 'ml':  return val         # 1ml ≈ 1g for water-based
        if unit == 'kg':  return val * 1000
        if unit == 'l':   return val * 1000

    # Pattern: [448-g] or [7-g] — square bracket style from can descriptions
    m = re.search(r'\[\s*(\d+)-?g\s*\]', raw, re.IGNORECASE)
    if m:
        return float(m.group(1))

    return None


# ── PRIORITY 2: Extract leading metric "200g/7oz" or "325ml" ─────────────────
def extract_leading_metric(raw):
    """
    Handles lines that start directly with a number+unit:
    "200g/7oz cherry tomatoes" → 200
    "325ml/11oz vegetable oil" → 325
    "1kg/2lb lamb"             → 1000
    """
    text = raw.strip()
    m = re.match(r'^([\d\.]+)\s*(g|ml|kg|l)\b', text, re.IGNORECASE)
    if m:
        val  = float(m.group(1))
        unit = m.group(2).lower()
        if unit == 'g':   return val
        if unit == 'ml':  return val
        if unit == 'kg':  return val * 1000
        if unit == 'l':   return val * 1000

    return None


# ── PRIORITY 3: Extract pound/lb ──────────────────────────────────────────────
def extract_pounds(raw):
    """
    Handles "3 lb chicken", "2½ lb steak", "1 pound beef".
    Returns grams (1 lb = 454g).
    """
    text = raw.strip()
    qty, rest = parse_leading_number(text)
    if qty is None:
        return None

    first_word = rest.split()[0].lower() if rest.split() else ''
    if first_word in ('lb', 'lbs', 'pound', 'pounds'):
        return qty * 454

    return None


# ── PRIORITY 4: Volume unit conversion ───────────────────────────────────────
def extract_volume_unit(raw):
    """
    Handles "2 tsp salt", "1 tbsp olive oil", "2 cups rice", "400ml milk".
    """
    text = raw.strip()
    qty, rest = parse_leading_number(text)
    if qty is None:
        return None

    first_word = rest.split()[0].lower().rstrip('.,') if rest.split() else ''
    if first_word in UNIT_GRAMS:
        return qty * UNIT_GRAMS[first_word]

    return None


# ── PRIORITY 5: Count with size/item word ────────────────────────────────────
def extract_count_item(raw):
    """
    Handles "1 large onion", "2 cloves garlic", "3 eggs".
    """
    text = raw.strip()
    qty, rest = parse_leading_number(text)
    if qty is None:
        return None

    first_word = rest.split()[0].lower().rstrip('.,') if rest.split() else ''
    if first_word in COUNT_GRAMS:
        return qty * COUNT_GRAMS[first_word]

    return None


# ── Main extractor: tries all priorities in order ────────────────────────────
def extract_grams(raw):
    """
    Tries each extraction method in priority order.
    Returns (grams, method_name) or (None, 'no_match').
    """
    if not raw or not raw.strip():
        return None, 'blank'

    result = extract_bracketed_metric(raw)
    if result is not None:
        return result, 'bracketed_metric'

    result = extract_leading_metric(raw)
    if result is not None:
        return result, 'leading_metric'

    result = extract_pounds(raw)
    if result is not None:
        return result, 'pound_conversion'

    result = extract_volume_unit(raw)
    if result is not None:
        return result, 'volume_unit'

    result = extract_count_item(raw)
    if result is not None:
        return result, 'count_estimate'

    return None, 'no_match'


# ── Servings parser ───────────────────────────────────────────────────────────
def parse_servings(raw):
    """
    Extracts the number of servings from strings like:
        "MAKES 4 TO 6 SERVINGS"  → 5   (midpoint)
        "MAKES 6 SERVINGS"       → 6
        "6 servings"             → 6
        "4 – 5"                  → 4   (lower bound)
        "4"                      → 4
        "Makes a 900 g loaf"     → 8   (default for a loaf)
        garbage                  → 4   (safe default)
    Returns an integer.
    """
    if not raw or not raw.strip():
        return 4  # default

    text = raw.strip().upper()

    # "MAKES X TO Y SERVINGS" or "X TO Y SERVINGS"
    m = re.search(r'(\d+)\s*TO\s*(\d+)', text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return round((lo + hi) / 2)  # use midpoint

    # "X – Y servings" (dash ranges)
    m = re.search(r'(\d+)\s*[–\-]\s*(\d+)', text)
    if m:
        return int(m.group(1))  # use lower bound

    # Plain number anywhere in string
    m = re.search(r'(\d+)', text)
    if m:
        val = int(m.group(1))
        # Sanity check: ignore if it looks like a weight (e.g. "900 G LOAF")
        if 'LOAF' in text or 'CUP' in text:
            return 8  # a loaf/batch default
        if 1 <= val <= 50:
            return val

    return 4  # safe default


# ── Load data ─────────────────────────────────────────────────────────────────

def load_merged(filepath):
    """Returns list of rows from merged_recipes_updated.csv"""
    with open(filepath, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def load_rif(filepath):
    """
    Returns a lookup dict:
        { (recipe_id, ingredient_index) : row_dict }
    from recipe_ingredient_final.csv
    """
    lookup = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = (row['recipe_id'].strip(), row['ingredient_index'].strip())
            lookup[key] = row
    return lookup

def load_servings(filepath):
    """
    Returns { recipe_id_str : servings_int }
    """
    servings = {}
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rid = row['recipe_id'].strip()
            raw = row['servings_raw'].strip()
            servings[rid] = parse_servings(raw)
    return servings


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Extract Ingredient Measures")
    print("=" * 40)

    for f in [MERGED_FILE, RIF_FILE, CLEAN_FILE]:
        if not os.path.exists(f):
            print(f"ERROR: {f} not found")
            return

    print("\nLoading files...")
    merged_rows  = load_merged(MERGED_FILE)
    rif_lookup   = load_rif(RIF_FILE)
    servings_map = load_servings(CLEAN_FILE)

    print(f"  merged_recipes rows : {len(merged_rows)}")
    print(f"  rif rows            : {len(rif_lookup)}")
    print(f"  recipes with serving: {len(servings_map)}")

    # Track extraction method counts for the summary
    method_counts = {}
    results = []

    print("\nExtracting measures...")

    for row in merged_rows:
        recipe_id  = row['recipe_id'].strip()
        ing_index  = row['ingredient_index'].strip()
        raw_line   = row['ingredient_line_raw'].strip()

        # Skip rows with no recipe_id (header noise or blank rows)
        if not recipe_id:
            continue

        # Look up the ingredient_id from recipe_ingredient_final
        key = (recipe_id, ing_index)
        rif_row = rif_lookup.get(key)
        ingredient_id = rif_row['ingredient_id'] if rif_row else ''

        # Get servings for this recipe
        servings = servings_map.get(recipe_id, 4)

        # Extract gram weight
        grams, method = extract_grams(raw_line)

        # Round to 2 decimal places for cleanliness
        grams_rounded = round(grams, 2) if grams is not None else ''

        # Per-serving weight
        grams_per_serving = round(grams / servings, 2) if grams is not None else ''

        method_counts[method] = method_counts.get(method, 0) + 1

        results.append({
            'recipe_id'         : recipe_id,
            'ingredient_id'     : ingredient_id,
            'ingredient_index'  : ing_index,
            'ingredient_raw'    : raw_line,
            'grams_total'       : grams_rounded,
            'servings'          : servings,
            'grams_per_serving' : grams_per_serving,
            'extraction_method' : method,
        })

    # Write output
    fieldnames = [
        'recipe_id', 'ingredient_id', 'ingredient_index',
        'ingredient_raw', 'grams_total', 'servings',
        'grams_per_serving', 'extraction_method'
    ]
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Summary
    total        = len(results)
    has_weight   = sum(1 for r in results if r['grams_total'] != '')
    no_weight    = total - has_weight

    print(f"\n✓ Done! {total} ingredient lines processed")
    print(f"  Has gram weight : {has_weight}  ({100*has_weight//total}%)")
    print(f"  No weight found : {no_weight}  ({100*no_weight//total}%)")
    print(f"  Saved to        : {OUTPUT_FILE}")

    print(f"\n  Extraction method breakdown:")
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count // total
        print(f"    {method:25s}: {count:4d}  ({pct}%)")


if __name__ == '__main__':
    main()
