"""
score_nutrition_risk.py
=======================
Scores every recipe in recipe_nutrition.csv for nutritional risk.

Reference standard : WHO dietary guidelines, expressed per serving
                     (assuming 1 serving ≈ 1/3 of a 2 000 kcal/day diet)

Two scoring methods are produced:

  Method 1 — FLAG COUNT
  ─────────────────────
  Each nutrient is independently classified Low / Medium / High.
  The number of High flags is summed into an overall risk level:
    0 flags  → Low
    1–2 flags → Medium
    3+ flags  → High

  Method 2 — WEIGHTED SCORE  (0–100)
  ────────────────────────────────────
  Each nutrient gets a continuous 0–1 score then multiplied by its
  weight.  Sodium is weighted highest (30 %) given the burden of
  hypertension in African populations.

  Weights:
    Sodium    30 %   (hypertension — leading NCD risk in Africa)
    Energy    25 %   (obesity / overweight)
    Fat       20 %   (cardiovascular disease)
    Sugar     15 %   (diabetes / metabolic syndrome)
    Protein   10 %   (malnutrition / deficiency — inverted: low = risky)

  Risk levels for weighted score:
     0 – 25   Low
    25 – 50   Medium
    50 – 75   High
    75 – 100  Very High

Recipes with energy_kcal == 0 are marked data_status = 'insufficient_data'
and are excluded from scoring.

OUTPUT : recipe_risk_scores.csv

Run from african_recipes_nutrition/:
    py score_nutrition_risk.py
"""

import csv
import os

BASE            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM    = os.path.join(BASE, 'data', 'interim')
DATA_OUTPUT     = os.path.join(BASE, 'data', 'outputs')

NUTRITION_FILE  = os.path.join(DATA_OUTPUT,  'recipe_nutrition.csv')
RECIPES_FILE    = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
OUTPUT_FILE     = os.path.join(DATA_OUTPUT,  'recipe_risk_scores.csv')

# ── Per-serving risk thresholds (WHO / dietary guidelines) ────────────────────
# Each nutrient has a medium-risk and high-risk threshold.
# Protein is inverted: low intake = high risk.

THRESHOLDS = {
    #  nutrient          medium  high
    'energy_kcal' : dict(medium=500,  high=800),   # kcal   — ⅓ of 2 000 kcal/day
    'sodium_mg'   : dict(medium=400,  high=700),   # mg     — ⅓ of WHO 2 000 mg/day limit
    'fat_g'       : dict(medium=15,   high=25),    # g      — ⅓ of 65 g/day
    'sugars_g'    : dict(medium=12,   high=20),    # g      — ⅓ of WHO 50 g/day free-sugar limit
    'protein_g'   : dict(medium=15,   high=8),     # g      — INVERTED: medium=15, high-risk below 8
}

# ── Weights for the weighted score (must sum to 1.0) ──────────────────────────
WEIGHTS = {
    'sodium_mg'   : 0.30,
    'energy_kcal' : 0.25,
    'fat_g'       : 0.20,
    'sugars_g'    : 0.15,
    'protein_g'   : 0.10,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ── Per-nutrient classification ───────────────────────────────────────────────

def classify_nutrient(nutrient, value):
    """
    Returns 'low' | 'medium' | 'high' for a single nutrient value.
    Protein is inverted (high value = low risk).
    """
    t = THRESHOLDS[nutrient]

    if nutrient == 'protein_g':
        # High protein (>= medium threshold) = low risk
        if value >= t['medium']:
            return 'low'
        elif value >= t['high']:
            return 'medium'
        else:
            return 'high'
    else:
        if value < t['medium']:
            return 'low'
        elif value < t['high']:
            return 'medium'
        else:
            return 'high'


# ── Continuous nutrient score (0–1) for the weighted score ───────────────────

def nutrient_score(nutrient, value):
    """
    Returns a continuous 0–1 risk score for one nutrient.

    For excess nutrients (energy, sodium, fat, sugar):
      0.0 → at or below the medium threshold  (low risk)
      0.5 → at the high threshold             (high risk boundary)
      1.0 → at 2× the high threshold          (very high; capped)

    For protein (inverted):
      0.0 → at or above the medium threshold  (low risk)
      0.5 → at the high-risk threshold (8g)
      1.0 → at 0g protein                     (maximum risk; capped)
    """
    t = THRESHOLDS[nutrient]

    if nutrient == 'protein_g':
        medium_t = t['medium']   # 15 g  — above this = no risk
        high_t   = t['high']     # 8 g   — below this = high risk

        if value >= medium_t:
            return 0.0
        elif value >= high_t:
            # 0.0 at medium_t → 0.5 at high_t
            return 0.5 * (medium_t - value) / (medium_t - high_t)
        else:
            # 0.5 at high_t → 1.0 at 0g (capped)
            return 0.5 + min(0.5 * (high_t - value) / high_t, 0.5)

    else:
        medium_t = t['medium']
        high_t   = t['high']

        if value <= medium_t:
            return 0.0
        elif value <= high_t:
            # 0.0 at medium_t → 0.5 at high_t
            return 0.5 * (value - medium_t) / (high_t - medium_t)
        else:
            # 0.5 at high_t → 1.0 at 2× high_t (capped)
            return 0.5 + min(0.5 * (value - high_t) / high_t, 0.5)


# ── Weighted score ────────────────────────────────────────────────────────────

def weighted_score(nutrients):
    """
    nutrients : dict {nutrient_name: float_value}
    Returns a 0–100 weighted risk score.
    """
    return round(sum(
        nutrient_score(n, nutrients[n]) * w
        for n, w in WEIGHTS.items()
    ) * 100, 1)


def weighted_risk_level(score):
    if score < 25:
        return 'Low'
    elif score < 50:
        return 'Medium'
    elif score < 75:
        return 'High'
    else:
        return 'Very High'


# ── Flag count ────────────────────────────────────────────────────────────────

def flag_count_risk_level(n_flags):
    if n_flags == 0:
        return 'Low'
    elif n_flags <= 2:
        return 'Medium'
    else:
        return 'High'


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("African Recipes - Nutritional Risk Scoring")
    print("=" * 44)

    # Load recipe names
    with open(RECIPES_FILE, encoding='utf-8') as f:
        recipe_names = {r['recipe_id']: r['recipe_name'] for r in csv.DictReader(f)}

    # Load nutrition data
    with open(NUTRITION_FILE, encoding='utf-8') as f:
        nutrition_rows = list(csv.DictReader(f))

    results          = []
    scored           = 0
    insufficient     = 0

    for row in nutrition_rows:
        rid    = row['recipe_id']
        name   = recipe_names.get(rid, '?')
        kcal   = float(row['energy_kcal'])
        ingr_used  = int(row['ingredients_used'])
        ingr_total = int(row['ingredients_total'])
        coverage   = round(ingr_used / ingr_total * 100, 1) if ingr_total > 0 else 0.0

        # ── Insufficient data ─────────────────────────────────────────────────
        if kcal == 0:
            results.append({
                'recipe_id'            : rid,
                'recipe_name'          : name,
                'servings'             : row['servings'],
                'energy_kcal'          : kcal,
                'protein_g'            : row['protein_g'],
                'fat_g'                : row['fat_g'],
                'carbohydrate_g'       : row['carbohydrate_g'],
                'sugars_g'             : row['sugars_g'],
                'sodium_mg'            : row['sodium_mg'],
                'ingredient_coverage_pct': coverage,
                'energy_risk'          : 'n/a',
                'sodium_risk'          : 'n/a',
                'fat_risk'             : 'n/a',
                'sugar_risk'           : 'n/a',
                'protein_risk'         : 'n/a',
                'flag_count'           : 'n/a',
                'flag_risk_level'      : 'n/a',
                'weighted_risk_score'  : 'n/a',
                'weighted_risk_level'  : 'n/a',
                'data_status'          : 'insufficient_data',
            })
            insufficient += 1
            continue

        # ── Parse nutrients ───────────────────────────────────────────────────
        nutrients = {
            'energy_kcal' : kcal,
            'sodium_mg'   : float(row['sodium_mg']),
            'fat_g'       : float(row['fat_g']),
            'sugars_g'    : float(row['sugars_g']),
            'protein_g'   : float(row['protein_g']),
        }

        # ── Per-nutrient classification ───────────────────────────────────────
        energy_risk  = classify_nutrient('energy_kcal', nutrients['energy_kcal'])
        sodium_risk  = classify_nutrient('sodium_mg',   nutrients['sodium_mg'])
        fat_risk     = classify_nutrient('fat_g',       nutrients['fat_g'])
        sugar_risk   = classify_nutrient('sugars_g',    nutrients['sugars_g'])
        protein_risk = classify_nutrient('protein_g',   nutrients['protein_g'])

        # ── Flag count ────────────────────────────────────────────────────────
        flags = sum([
            energy_risk  == 'high',
            sodium_risk  == 'high',
            fat_risk     == 'high',
            sugar_risk   == 'high',
            protein_risk == 'high',
        ])

        # ── Weighted score ────────────────────────────────────────────────────
        w_score = weighted_score(nutrients)
        w_level = weighted_risk_level(w_score)

        results.append({
            'recipe_id'            : rid,
            'recipe_name'          : name,
            'servings'             : row['servings'],
            'energy_kcal'          : round(kcal, 1),
            'protein_g'            : round(nutrients['protein_g'], 1),
            'fat_g'                : round(nutrients['fat_g'], 1),
            'carbohydrate_g'       : round(float(row['carbohydrate_g']), 1),
            'sugars_g'             : round(nutrients['sugars_g'], 1),
            'sodium_mg'            : round(nutrients['sodium_mg'], 1),
            'ingredient_coverage_pct': coverage,
            'energy_risk'          : energy_risk,
            'sodium_risk'          : sodium_risk,
            'fat_risk'             : fat_risk,
            'sugar_risk'           : sugar_risk,
            'protein_risk'         : protein_risk,
            'flag_count'           : flags,
            'flag_risk_level'      : flag_count_risk_level(flags),
            'weighted_risk_score'  : w_score,
            'weighted_risk_level'  : w_level,
            'data_status'          : 'calculated',
        })
        scored += 1

    # ── Write output ──────────────────────────────────────────────────────────
    fieldnames = [
        'recipe_id', 'recipe_name', 'servings',
        'energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'sugars_g', 'sodium_mg',
        'ingredient_coverage_pct',
        'energy_risk', 'sodium_risk', 'fat_risk', 'sugar_risk', 'protein_risk',
        'flag_count', 'flag_risk_level',
        'weighted_risk_score', 'weighted_risk_level',
        'data_status',
    ]
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # ── Summary ───────────────────────────────────────────────────────────────
    scored_rows = [r for r in results if r['data_status'] == 'calculated']

    flag_dist = {'Low': 0, 'Medium': 0, 'High': 0}
    wt_dist   = {'Low': 0, 'Medium': 0, 'High': 0, 'Very High': 0}
    for r in scored_rows:
        flag_dist[r['flag_risk_level']] += 1
        wt_dist[r['weighted_risk_level']] += 1

    top_sodium  = sorted(scored_rows, key=lambda r: float(r['sodium_mg']),   reverse=True)[:5]
    top_calorie = sorted(scored_rows, key=lambda r: float(r['energy_kcal']), reverse=True)[:5]
    top_score   = sorted(scored_rows, key=lambda r: float(r['weighted_risk_score']), reverse=True)[:5]

    print(f"\nRecipes scored           : {scored}")
    print(f"Insufficient data        : {insufficient}")
    print(f"\nFlag-count risk distribution:")
    for level, count in flag_dist.items():
        bar = '#' * count
        print(f"  {level:<10}: {count:>3}  {bar}")

    print(f"\nWeighted score risk distribution:")
    for level, count in wt_dist.items():
        bar = '#' * count
        print(f"  {level:<12}: {count:>3}  {bar}")

    print(f"\nTop 5 highest sodium (mg/serving):")
    for r in top_sodium:
        print(f"  {r['recipe_id']:>4}  {r['recipe_name'][:45]:<45}  {r['sodium_mg']:>8} mg")

    print(f"\nTop 5 highest calorie (kcal/serving):")
    for r in top_calorie:
        print(f"  {r['recipe_id']:>4}  {r['recipe_name'][:45]:<45}  {r['energy_kcal']:>8} kcal")

    print(f"\nTop 5 highest weighted risk score:")
    for r in top_score:
        print(f"  {r['recipe_id']:>4}  {r['recipe_name'][:45]:<45}  score={r['weighted_risk_score']:>5}  level={r['weighted_risk_level']}")

    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
