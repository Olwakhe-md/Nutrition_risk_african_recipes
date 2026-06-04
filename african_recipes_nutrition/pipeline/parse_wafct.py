"""
pipeline/parse_wafct.py
========================
Parse the WAFCT 2019 Excel file into a clean CSV for use by WAFCTFoodIndex.

WHY THIS SCRIPT EXISTS
----------------------
The WAFCT (West African Food Composition Table) 2019 published by FAO/INFOODS
contains 1 028 African foods with nutrient data per 100g edible portion.
It covers foods that the USDA database lacks: fufu, pounded yam, egusi,
fonio, baobab, dawadawa, African leafy vegetables, etc.

We extract the 5 nutrients our pipeline tracks:
  energy_kcal, protein_g, fat_g, carbohydrate_g, sodium_mg

Note: WAFCT does not include total sugars — that column will be set to 0.
      Values in brackets like [0.2] are imputed estimates; we use them but
      preserve an 'imputed' flag.

Input : data/raw/WAFCT_2019.xlsx  (Sheet "03 NV_sum_39 (per 100g EP)")
Output: data/raw/wafct_foods.csv

Column mapping (1-based, Sheet 03):
  col 1  → code           (WAFCT food code e.g. "01_172")
  col 2  → food_name_en   (English name)
  col 3  → food_name_fr   (French name)
  col 8  → energy_kcal    (ENERC, kcal per 100g)
  col 10 → protein_g      (PROTCNT, g per 100g)
  col 11 → fat_g          (FAT, g per 100g)
  col 12 → carbohydrate_g (CHOAVLDF, g per 100g)
  col 20 → sodium_mg      (NA, mg per 100g)

Run from african_recipes_nutrition/:
    py pipeline/parse_wafct.py
"""

import csv
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
import openpyxl

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(BASE, 'data', 'raw', 'WAFCT_2019.xlsx')
OUTPUT_CSV = os.path.join(BASE, 'data', 'raw', 'wafct_foods.csv')

# 0-based column indices in Sheet 03
COL_CODE   = 0
COL_NAME_EN = 1
COL_NAME_FR = 2
COL_KCAL   = 7   # Energy (kcal)
COL_PROT   = 9   # Protein (g)
COL_FAT    = 10  # Fat (g)
COL_CARB   = 11  # Carbohydrate (g)
COL_NA     = 19  # Sodium (mg)

# Data starts at row index 4 (rows 0-3 are bilingual headers + tagname row + blank)
DATA_START_ROW = 4


def parse_value(raw) -> float | None:
    """
    Convert a WAFCT cell value to float.

    Handles:
      [0.2]  → 0.2    (imputed value, brackets stripped)
      [tr]   → 0.0    (trace amount)
      tr     → 0.0    (trace amount)
      —      → None   (missing data)
      empty  → None
      12.3   → 12.3
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in ('—', '-', 'n.d.', 'nd', 'n/a'):
        return None
    # Strip brackets for imputed values: [0.2] → 0.2
    text = text.strip('[]')
    # Trace amounts
    if text.lower() in ('tr', 'trace'):
        return 0.0
    # Strip any trailing asterisks or annotations
    text = re.sub(r'[*†‡§#].*$', '', text).strip()
    try:
        return float(text.replace(',', '.'))
    except ValueError:
        return None


def is_category_row(row_vals) -> bool:
    """
    Return True if the row is a food-group header rather than a food entry.
    Category rows have text in col 0 (code) but no numeric data in nutrient cols,
    OR have a code that doesn't match the WAFCT "##_###" pattern.
    """
    code = str(row_vals[COL_CODE] or '').strip()
    if not code:
        return True
    # WAFCT food codes look like "01_172", "05_021", etc.
    if not re.match(r'^\d{2}_\d+', code):
        return True
    return False


def main():
    print(f'Parsing {INPUT_FILE}')
    wb = openpyxl.load_workbook(INPUT_FILE, read_only=True, data_only=True)
    ws = wb['03 NV_sum_39 (per 100g EP)']

    fieldnames = [
        'code', 'food_name_en', 'food_name_fr',
        'energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'sodium_mg',
    ]

    foods = []
    skipped_category = 0
    skipped_no_name  = 0
    skipped_no_kcal  = 0

    for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if row_idx < DATA_START_ROW:
            continue

        if is_category_row(row):
            skipped_category += 1
            continue

        code     = str(row[COL_CODE] or '').strip()
        name_en  = str(row[COL_NAME_EN] or '').strip()
        name_fr  = str(row[COL_NAME_FR] or '').strip()

        if not name_en:
            skipped_no_name += 1
            continue

        kcal = parse_value(row[COL_KCAL])
        prot = parse_value(row[COL_PROT])
        fat  = parse_value(row[COL_FAT])
        carb = parse_value(row[COL_CARB])
        na   = parse_value(row[COL_NA])

        # Must have at least energy to be useful
        if kcal is None:
            skipped_no_kcal += 1
            continue

        foods.append({
            'code':           code,
            'food_name_en':   name_en,
            'food_name_fr':   name_fr,
            'energy_kcal':    kcal if kcal is not None else 0.0,
            'protein_g':      prot if prot is not None else 0.0,
            'fat_g':          fat  if fat  is not None else 0.0,
            'carbohydrate_g': carb if carb is not None else 0.0,
            'sodium_mg':      na   if na   is not None else 0.0,
        })

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(foods)

    print(f'Foods written    : {len(foods)}')
    print(f'Category rows    : {skipped_category}')
    print(f'No name skipped  : {skipped_no_name}')
    print(f'No kcal skipped  : {skipped_no_kcal}')
    print(f'Output           : {OUTPUT_CSV}')
    print()
    print('Sample (first 5 foods):')
    for f in foods[:5]:
        print(f'  {f["code"]:8}  {f["food_name_en"][:45]:<45}  '
              f'kcal={f["energy_kcal"]:>6.1f}  na={f["sodium_mg"]:>6.1f}mg')


if __name__ == '__main__':
    main()
