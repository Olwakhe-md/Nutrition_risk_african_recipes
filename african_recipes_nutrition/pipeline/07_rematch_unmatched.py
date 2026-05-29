"""
rematch_unmatched.py
====================
Re-matches ingredients that have no USDA FDC ID by fuzzy-matching them
against the FULL USDA food.csv database (5,432 foods) instead of the
small ~300-entry reference pool used by the original matcher.

Specifically targets:
  - Rows in ingredient_mapping_final.csv where match_status == 'skip'
    AND notes contains 'scraped' (new ingredients from the 59 scraped recipes)

Updates ingredient_mapping_final.csv in place.

Run from african_recipes_nutrition/:
    py rematch_unmatched.py
"""

import csv
import os

from rapidfuzz import process, fuzz

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CLEAN  = os.path.join(BASE, 'data_clean')

FOOD_FILE    = os.path.join(DATA_RAW, 'food.csv')
MAPPING_FILE = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')

FUZZY_THRESHOLD = 65


def load_usda_foods(filepath):
    """
    Returns (food_ids, food_descs_lower, food_descs_original).
    food_descs_lower is used for matching; food_descs_original is stored in output.
    """
    food_ids   = []
    food_lower = []
    food_orig  = []
    with open(filepath, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            fdc_id = row['fdc_id'].strip()
            desc   = row['description'].strip()
            if fdc_id and desc:
                food_ids.append(fdc_id)
                food_lower.append(desc.lower())
                food_orig.append(desc)
    return food_ids, food_lower, food_orig


def main():
    print("Re-match Unmatched Ingredients Against Full USDA Database")
    print("=" * 57)

    # Load USDA food pool
    print("\nLoading USDA food database...")
    food_ids, food_descs_lower, food_descs_orig = load_usda_foods(FOOD_FILE)
    print(f"  {len(food_ids)} USDA foods loaded")

    # Load current mapping
    print("Loading ingredient mappings...")
    with open(MAPPING_FILE, newline='', encoding='utf-8') as f:
        reader    = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows       = list(reader)

    unmatched = [
        r for r in rows
        if r['match_status'].strip() == 'skip'
        and 'scraped' in r.get('notes', '')
    ]
    print(f"  {len(rows)} total mapping rows")
    print(f"  {len(unmatched)} unmatched scraped ingredients to re-match")

    # Re-match
    print("\nFuzzy matching against USDA database...")
    updated_count  = 0
    still_unmatched = 0

    for row in rows:
        if row['match_status'].strip() != 'skip':
            continue
        if 'scraped' not in row.get('notes', ''):
            continue

        ingredient = row['recipe_ingredient_name'].strip().lower()

        result = process.extractOne(
            ingredient,
            food_descs_lower,
            scorer=fuzz.token_sort_ratio,
        )

        if result and result[1] >= FUZZY_THRESHOLD:
            best_lower = result[0]
            score      = int(result[1])
            idx        = food_descs_lower.index(best_lower)
            best_fdc   = food_ids[idx]
            best_desc  = food_descs_orig[idx]

            row['matched_fdc_id']    = best_fdc
            row['matched_food_name'] = best_desc
            row['match_status']      = 'matched'
            row['match_type']        = f'fuzzy_usda_{score}%'
            row['notes']             = 'Added from scraped allrecipes data; rematched vs full USDA'
            updated_count += 1
        else:
            still_unmatched += 1

    # Write back
    with open(MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDONE")
    print(f"  Newly matched    : {updated_count}")
    print(f"  Still unmatched  : {still_unmatched}")
    print(f"  Mapping file updated: {MAPPING_FILE}")
    print(f"\nNext step: re-run calculate_nutrition.py to refresh recipe_nutrition.csv")


if __name__ == '__main__':
    main()
