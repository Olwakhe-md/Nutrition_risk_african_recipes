"""
11_deduplicate_recipes.py
=========================
Removes duplicate recipes that were introduced when merging data from
multiple sources (allrecipes, cheflola, africanbites, food.com).

Strategy:
  - Normalise each recipe name (lowercase, collapse whitespace, strip
    trailing punctuation and trailing 's').
  - For each group of duplicates keep the version with the most ingredient
    rows in recipe_ingredient_final.csv (most complete nutritional data).
  - Remove the rest from recipes_clean.csv and recipe_ingredient_final.csv.
  - The ingredients_master and ingredient_mapping tables are NOT pruned —
    those entries are harmless even if no recipe currently references them.

Writes:
  data/interim/recipes_clean.csv          (deduplicated)
  data/interim/recipe_ingredient_final.csv (deduplicated)
  data/interim/dedup_removed.csv           (audit log of removed recipes)

Run from african_recipes_nutrition/:
    py pipeline/11_deduplicate_recipes.py
"""

import csv
import os
import re
import sys
from collections import defaultdict

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')
sys.path.insert(0, BASE)

RECIPES_FILE = os.path.join(DATA_INTERIM, 'recipes_clean.csv')
RIF_FILE     = os.path.join(DATA_INTERIM, 'recipe_ingredient_final.csv')
REMOVED_LOG  = os.path.join(DATA_INTERIM, 'dedup_removed.csv')


def norm_name(name):
    """Normalise a recipe name for duplicate comparison."""
    n = name.lower().strip().strip('"').strip("'")
    n = re.sub(r'\s+', ' ', n)
    n = n.rstrip('s')          # "soups" -> "soup", "recipes" -> "recipe"
    n = re.sub(r'[^\w\s]', '', n)  # strip punctuation
    return n.strip()


def load_csv(filepath):
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def main():
    print('Deduplicate Recipes')
    print('=' * 50)

    recipes_fn, recipes_rows = load_csv(RECIPES_FILE)
    rif_fn,     rif_rows     = load_csv(RIF_FILE)

    print(f'Recipes before dedup : {len(recipes_rows)}')
    print(f'RIF rows before dedup: {len(rif_rows)}')

    # Count ingredients per recipe_id
    ing_count = defaultdict(int)
    for row in rif_rows:
        ing_count[row['recipe_id']] += 1

    # Group recipes by normalised name
    groups = defaultdict(list)
    for row in recipes_rows:
        key = norm_name(row['recipe_name'])
        groups[key].append(row)

    keep_ids   = set()
    remove_ids = set()
    removed_recipes = []

    for key, group in groups.items():
        if len(group) == 1:
            keep_ids.add(group[0]['recipe_id'])
            continue

        # Keep the one with the most ingredients; break ties by lowest recipe_id
        best = max(group, key=lambda r: (ing_count.get(r['recipe_id'], 0), -int(r['recipe_id'])))
        keep_ids.add(best['recipe_id'])

        for row in group:
            if row['recipe_id'] != best['recipe_id']:
                remove_ids.add(row['recipe_id'])
                removed_recipes.append({
                    'recipe_id'   : row['recipe_id'],
                    'recipe_name' : row['recipe_name'],
                    'recipe_url'  : row.get('recipe_url', ''),
                    'kept_id'     : best['recipe_id'],
                    'kept_name'   : best['recipe_name'],
                    'reason'      : f'duplicate of kept_id={best["recipe_id"]} (norm_key="{key}")',
                })

    print(f'\nDuplicate groups found : {sum(1 for g in groups.values() if len(g) > 1)}')
    print(f'Recipes to remove      : {len(remove_ids)}')
    print(f'Recipes to keep        : {len(keep_ids)}')

    # Filter tables
    recipes_kept = [r for r in recipes_rows if r['recipe_id'] in keep_ids]
    rif_kept     = [r for r in rif_rows     if r['recipe_id'] in keep_ids]

    # Write deduplicated files
    with open(RECIPES_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=recipes_fn)
        writer.writeheader()
        writer.writerows(recipes_kept)

    with open(RIF_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rif_fn)
        writer.writeheader()
        writer.writerows(rif_kept)

    # Write audit log
    if removed_recipes:
        log_fn = ['recipe_id', 'recipe_name', 'recipe_url', 'kept_id', 'kept_name', 'reason']
        with open(REMOVED_LOG, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=log_fn)
            writer.writeheader()
            writer.writerows(removed_recipes)

    print(f'\nRecipes after dedup  : {len(recipes_kept)}')
    print(f'RIF rows after dedup : {len(rif_kept)}')
    print(f'Removed recipes log  : {REMOVED_LOG}')
    print(f'\nNext: run 08_calculate_nutrition.py')


if __name__ == '__main__':
    main()
