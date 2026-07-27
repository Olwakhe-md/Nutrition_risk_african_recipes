"""
build_nutrient_table.py
=======================
One-time build step: pre-filter the 19 MB USDA food_nutrient.csv down to just
the six nutrients the app scores on, and save it as a small parquet file.

WHY:
    LiveAnalyser needs {fdc_id: {nutrient_id: amount_per_100g}} for six
    nutrients. Building that from food_nutrient.csv at runtime means parsing
    ~9 million CSV rows every cold start (~2 s), which is paid again each time
    Streamlit Cloud wakes the app from sleep. The filtered data is only ~48k
    rows; as parquet it loads in a fraction of the time.

OUTPUT: data/interim/food_nutrients.parquet  (columns: fdc_id, nutrient_id, amount)

Run from african_recipes_nutrition/:
    py pipeline/build_nutrient_table.py
"""

import os

import pandas as pd

from live_analysis import NUTRIENT_FILE, NUTRIENT_IDS  # reuse the same paths/IDs

BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT     = os.path.join(BASE, 'data', 'interim', 'food_nutrients.parquet')
TARGET_IDS = set(NUTRIENT_IDS.keys())


def main():
    # Read only the three columns we need — much faster than the full file.
    df = pd.read_csv(NUTRIENT_FILE, usecols=['fdc_id', 'nutrient_id', 'amount'])

    df = df[df['nutrient_id'].isin(TARGET_IDS)].copy()
    df['fdc_id']      = pd.to_numeric(df['fdc_id'],      errors='coerce').astype('Int64')
    df['nutrient_id'] = pd.to_numeric(df['nutrient_id'], errors='coerce').astype('Int64')
    df['amount']      = pd.to_numeric(df['amount'],      errors='coerce').fillna(0.0)
    df = df.dropna(subset=['fdc_id', 'nutrient_id'])
    df['fdc_id']      = df['fdc_id'].astype('int64')
    df['nutrient_id'] = df['nutrient_id'].astype('int64')

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    df.to_parquet(OUTPUT, index=False)

    print(f"Wrote {len(df):,} rows for {df['fdc_id'].nunique():,} foods -> {OUTPUT}")
    size_mb = os.path.getsize(OUTPUT) / 1e6
    print(f"  parquet size: {size_mb:.2f} MB (source CSV is ~19 MB)")


if __name__ == '__main__':
    main()
