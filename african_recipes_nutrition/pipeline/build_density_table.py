"""
build_density_table.py
=======================
One-time build step: derive a per-food density (grams per millilitre) for every
USDA/FNDDS food from its household-measure portions, so the live analyser can
convert a *volume* (e.g. "2 cups flour") into a realistic *weight* instead of
assuming everything weighs the same as water (240 g/cup).

WHY THIS EXISTS:
    FNDDS records portions as free text — "1 cup", "1 tablespoon", "1 cup, NFS",
    "1 fl oz" — each with a real gram_weight. The numeric amount lives inside
    that text (the `amount` column is empty in the FNDDS file), so we parse the
    leading number out of the description. Density is a property of the food, so
    ANY one volumetric portion gives us grams-per-millilitre:

        density (g/ml) = gram_weight / (amount × millilitres_of_that_measure)

    From that single number every volumetric unit follows (1 cup = 240 ml,
    1 tbsp = 15 ml, 1 tsp = 5 ml), because they differ only by volume.

OUTPUT: data/interim/food_density.csv  (fdc_id, g_per_ml, source_portion)

Run from african_recipes_nutrition/:
    py pipeline/build_density_table.py
"""

import os
import re

import pandas as pd

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTION_CSV = os.path.join(BASE, 'data', 'raw', 'food_portion.csv')
OUTPUT_CSV  = os.path.join(BASE, 'data', 'interim', 'food_density.csv')

# Millilitres per household volume measure, matched against the free-text
# portion_description. Ordered longest-first so "fluid ounce" wins over "ounce".
VOLUME_MEASURES = [
    ('fluid ounce', 29.5735), ('fl oz', 29.5735),
    ('tablespoon', 15.0), ('teaspoon', 5.0),
    ('milliliter', 1.0), ('millilitre', 1.0),
    ('cubic inch', 16.387),
    ('gallon', 3785.41), ('quart', 946.35), ('pint', 473.18),
    ('liter', 1000.0), ('litre', 1000.0),
    ('cup', 240.0),
]

# Densities outside this range are almost certainly a mis-parsed portion
# (e.g. "1 cup" of a whole item). Water is 1.0; oils ~0.9; syrups ~1.4.
MIN_DENSITY, MAX_DENSITY = 0.1, 2.0


def _millilitres(description: str):
    """Return the ml a portion describes, or None if it isn't volumetric."""
    d = str(description).lower()
    for keyword, ml in VOLUME_MEASURES:
        if re.search(r'\b' + re.escape(keyword), d):
            return ml
    return None


def _leading_amount(description: str) -> float:
    """Parse the count at the start of a portion ("2 tablespoons" -> 2.0,
    "1 1/2 cups" -> 1.5). Defaults to 1.0 when no number is present."""
    d = str(description).strip()
    m = re.match(r'^(\d+)\s+(\d+)/(\d+)\b', d)      # mixed: "1 1/2"
    if m and int(m.group(3)):
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.match(r'^(\d+)/(\d+)\b', d)              # fraction: "1/2"
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    m = re.match(r'^(\d+(?:\.\d+)?)', d)            # integer/decimal: "1", "1.5"
    if m:
        return float(m.group(1))
    return 1.0


def _preference_rank(description: str) -> int:
    """Lower = cleaner/more generic portion, preferred when a food has several.

    A plain "1 cup" / "1 cup, NFS" reflects the food as typically measured;
    prep-qualified ones ("1 cup, shredded/melted/sifted") pack differently.
    """
    d = str(description).lower()
    if re.fullmatch(r'\d*\s*cup(, nfs)?', d.strip()):
        return 0
    if 'cup' in d:
        return 1
    return 2


def main():
    fp = pd.read_csv(PORTION_CSV)
    fp['gram_weight'] = pd.to_numeric(fp['gram_weight'], errors='coerce').astype('float64')
    # The FNDDS `amount` column is empty — the count is embedded in the text.
    fp['amount'] = fp['portion_description'].map(_leading_amount).astype('float64')

    fp['ml']   = fp['portion_description'].map(_millilitres).astype('float64')
    rows = fp[(fp['gram_weight'] > 0) & (fp['amount'] > 0) & fp['ml'].notna()].copy()

    rows['g_per_ml'] = rows['gram_weight'] / (rows['amount'] * rows['ml'])
    rows = rows[(rows['g_per_ml'] >= MIN_DENSITY) & (rows['g_per_ml'] <= MAX_DENSITY)]

    rows['rank'] = rows['portion_description'].map(_preference_rank)
    rows = rows.sort_values(['fdc_id', 'rank'])

    best = rows.groupby('fdc_id', as_index=False).first()
    out = best[['fdc_id', 'g_per_ml', 'portion_description']].rename(
        columns={'portion_description': 'source_portion'})
    out['fdc_id']   = out['fdc_id'].astype('int64')
    out['g_per_ml'] = out['g_per_ml'].round(4)

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False)

    print(f"Wrote {len(out)} food densities -> {OUTPUT_CSV}")
    print(f"  median density : {out['g_per_ml'].median():.3f} g/ml")
    print(f"  range          : {out['g_per_ml'].min():.3f} - {out['g_per_ml'].max():.3f} g/ml")


if __name__ == '__main__':
    main()
