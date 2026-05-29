"""
fix_cheflola_mapping.py
=======================
Resolves the remaining unmatched cheflolaskitchen.com ingredients.

The WPRM scraper attaches preparation notes to ingredient names
("onion diced", "garlic minced", "chicken bouillon powder or 2 cubes"),
so the cleaner and fuzzy matcher leave them unresolved.

This script uses keyword-containment rules:
  - If the ingredient name CONTAINS a key word (e.g. "onion"), it maps
    to the appropriate USDA FDC ID.
  - Rules are checked in priority order — more specific rules first.

Run from african_recipes_nutrition/:
    py fix_cheflola_mapping.py
"""

import csv
import os
import re

BASE         = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')

# ── Keyword rules (checked in order, first match wins) ────────────────────────
# Format: (keyword_or_keywords, fdc_id, usda_food_name)
# Use a tuple of strings for multiple keywords (ALL must be present).
# Use a single string to match anywhere in the name.

KEYWORD_RULES = [
    # ── Negligible / zero-calorie items ──────────────────────────────────────
    # Checked first so "salt and pepper" doesn't get matched to pepper below
    ('salt',                 None,    'negligible'),
    ('water',                None,    'negligible'),
    ('toothpick',            None,    'negligible'),
    ('tooth pick',           None,    'negligible'),

    # ── Spice blends & paste ──────────────────────────────────────────────────
    ('berbere',              2710093, 'Hot pepper sauce'),          # ethiopian spice base
    ('suya spice',           2710093, 'Hot pepper sauce'),
    ('harissa',              2710093, 'Hot pepper sauce'),

    # ── Bouillon / stock (liquid / powder) ────────────────────────────────────
    ('bouillon',             2707132, 'Soup, broth'),
    ('stock powder',         2707132, 'Soup, broth'),
    ('chicken stock',        2707132, 'Soup, broth'),
    ('beef stock',           2707132, 'Soup, broth'),
    ('chicken broth',        2707132, 'Soup, broth'),

    # ── Oils ──────────────────────────────────────────────────────────────────
    ('palm oil',             2710197, 'Palm oil'),
    ('coconut oil',          2710191, 'Coconut oil'),
    ('olive oil',            2710192, 'Olive oil'),
    ('peanut oil',           2710189, 'Canola oil'),
    ('vegetable oil',        2710189, 'Canola oil'),
    ('oil',                  2710189, 'Canola oil'),               # catch-all for remaining oils

    # ── Onion family ──────────────────────────────────────────────────────────
    ('green onion',          2709795, 'Onions, raw'),
    ('red onion',            2709795, 'Onions, raw'),
    ('onion',                2709795, 'Onions, raw'),

    # ── Garlic & ginger ───────────────────────────────────────────────────────
    ('garlic',               2110003, 'Garlic, raw'),
    ('ginger',               2710082, 'Ginger root, pickled'),

    # ── Tomatoes ─────────────────────────────────────────────────────────────
    ('tomato',               2709797, 'Tomatoes, red, ripe, raw'),

    # ── Bell / sweet peppers ──────────────────────────────────────────────────
    ('bell pepper',          2709801, 'Peppers, sweet, red, raw'),
    ('red pepper',           2709801, 'Peppers, sweet, red, raw'),
    ('green pepper',         2709800, 'Peppers, sweet, green, raw'),
    ('mixed pepper',         2709801, 'Peppers, sweet, red, raw'),

    # ── Hot peppers ───────────────────────────────────────────────────────────
    ('scotch bonnet',        2710093, 'Hot pepper sauce'),
    ('habanero',             2710093, 'Hot pepper sauce'),
    ('chili flake',          2710093, 'Hot pepper sauce'),
    ('red chili',            2710093, 'Hot pepper sauce'),
    ('hot pepper',           2710093, 'Hot pepper sauce'),
    ('chili powder',         2710093, 'Hot pepper sauce'),
    ('chile',                2710093, 'Hot pepper sauce'),
    ('chili',                2710093, 'Hot pepper sauce'),
    ('pepper',               2709799, 'Peppers, raw, NFS'),        # catch-all pepper

    # ── Dried/ground spices (negligible amounts) ──────────────────────────────
    ('thyme',                None,    'negligible'),
    ('rosemary',             None,    'negligible'),
    ('oregano',              None,    'negligible'),
    ('cinnamon',             None,    'negligible'),
    ('nutmeg',               None,    'negligible'),
    ('cardamom',             None,    'negligible'),
    ('fenugreek',            None,    'negligible'),
    ('clove',                None,    'negligible'),
    ('cumin',                None,    'negligible'),
    ('coriander',            None,    'negligible'),
    ('curry',                2709767, 'Vegetable curry'),
    ('paprika',              2710093, 'Hot pepper sauce'),
    ('ajwain',               None,    'negligible'),
    ('sacred basil',         None,    'negligible'),
    ('besobela',             None,    'negligible'),
    ('koseret',              None,    'negligible'),
    ('korerima',             None,    'negligible'),
    ('abish',                None,    'negligible'),
    ('tikur',                None,    'negligible'),

    # ── Protein ───────────────────────────────────────────────────────────────
    ('chicken thigh',        2705929, 'Chicken, NS as to part and cooking method, NS as to skin eaten'),
    ('chicken quarter',      2705929, 'Chicken, NS as to part and cooking method, NS as to skin eaten'),
    ('chicken',              2705929, 'Chicken, NS as to part and cooking method, NS as to skin eaten'),
    ('turkey',               2705953, 'Turkey, NS as to part, roasted, skin not eaten'),
    ('beef',                 2105822, 'Beef, NFS'),
    ('goat',                 2105828, 'Lamb or mutton, NFS'),
    ('fish',                 2706240, 'Fish, cod, NFS'),
    ('mackerel',             2706240, 'Fish, cod, NFS'),
    ('crayfish',             2707132, 'Soup, broth'),               # dried crayfish used as seasoning

    # ── Dairy & eggs ──────────────────────────────────────────────────────────
    ('butter',               2710154, 'Butter, NFS'),
    ('milk',                 2705384, 'Milk, NFS'),
    ('cream',                2705405, 'Cream, NFS'),
    ('egg',                  2108064, 'Egg, whole, boiled or poached'),
    ('parmesan',             2705540, 'Cheese, parmesan, NFS'),

    # ── Starches & grains ─────────────────────────────────────────────────────
    ('rice',                 2708403, 'Rice, white, cooked, NS as to fat'),
    ('spaghetti',            2708357, 'Pasta, cooked'),
    ('pasta',                2708357, 'Pasta, cooked'),
    ('flour',                2708157, 'Crackers, flatbread'),
    ('bread crumb',          2707838, 'Bread, rye'),
    ('fonio',                2708377, 'Millet'),
    ('cornmeal',             2708363, 'Grits, NFS'),
    ('polenta',              2708363, 'Grits, NFS'),
    ('garri',                2709564, 'Cassava, cooked'),
    ('yam',                  2710794, 'Sweet potato, cooked, as ingredient'),
    ('plantain',             2709559, 'Plantain, cooked with oil'),
    ('potato',               2709423, 'Potato, boiled, NFS'),

    # ── Legumes ───────────────────────────────────────────────────────────────
    ('black eyed pea',       2707414, 'Chickpeas, NFS'),
    ('black-eyed pea',       2707414, 'Chickpeas, NFS'),
    ('honey bean',           2707414, 'Chickpeas, NFS'),
    ('bean',                 2707423, 'Lentils, NFS'),
    ('pea',                  2707423, 'Lentils, NFS'),
    ('lentil',               2707423, 'Lentils, NFS'),

    # ── Vegetables ────────────────────────────────────────────────────────────
    ('carrot',               2709660, 'Carrots, raw'),
    ('spinach',              2709605, 'Spinach, raw'),
    ('kale',                 2709600, 'Kale, fresh, cooked, no added fat'),
    ('cabbage',              2709644, 'Cabbage, raw'),
    ('eggplant',             2709785, 'Eggplant, raw'),
    ('corn',                 2709933, 'Hominy, cooked'),
    ('sweet potato',         2710794, 'Sweet potato, cooked, as ingredient'),
    ('pumpkin',              2709693, 'Winter squash, raw'),
    ('mango',                2109236, 'Mango, raw'),
    ('pineapple',            2709226, 'Pineapple, raw'),
    ('banana',               2709197, 'Banana, raw'),
    ('cranberr',             2709203, 'Date'),                      # cranberry proxy to sweet dried fruit

    # ── Nuts & seeds ──────────────────────────────────────────────────────────
    ('peanut',               2707519, 'Peanuts, dry roasted, unsalted'),
    ('locust bean',          2707519, 'Peanuts, dry roasted, unsalted'),  # locust beans (dawadawa) — fermented, used for flavor
    ('sesame',               2710193, 'Sesame oil'),

    # ── Sweeteners ────────────────────────────────────────────────────────────
    ('honey',                2710260, 'Sugar, brown'),
    ('sugar',                2710257, 'Sugar, NFS'),

    # ── Lemon / citrus juice ──────────────────────────────────────────────────
    ('lemon juice',          2109239, 'Lemon juice, 100%, freshly squeezed'),
    ('lemon',                2109242, 'Lemon, raw'),

    # ── Coconut (non-oil) ─────────────────────────────────────────────────────
    ('coconut milk',         2705421, 'Coconut milk, canned'),
    ('coconut',              2707500, 'Coconut, raw'),

    # ── Baked beans / canned items ────────────────────────────────────────────
    ('baked bean',           2707414, 'Chickpeas, NFS'),
]


def apply_keyword_rule(name):
    """
    Returns (fdc_id_or_None, food_name_or_'negligible') for the first
    keyword rule that matches, or (None, None) if no rule matches.
    """
    lower = name.lower()
    for rule in KEYWORD_RULES:
        keyword, fdc_id, food_name = rule
        if isinstance(keyword, tuple):
            if all(k in lower for k in keyword):
                return fdc_id, food_name
        else:
            if keyword in lower:
                return fdc_id, food_name
    return None, None


def main():
    print("Fix Chef Lola Ingredient Mappings (keyword rules)")
    print("=" * 50)

    with open(MAPPING_FILE, newline='', encoding='utf-8') as f:
        reader     = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows       = list(reader)

    target = [r for r in rows
              if r['match_status'].strip() == 'skip'
              and 'cheflola' in r.get('notes', '')]
    print(f"Unmatched cheflola ingredients : {len(target)}")

    keyword_matched  = 0
    negligible_marked = 0
    still_unmatched  = 0

    for row in rows:
        if row['match_status'].strip() != 'skip':
            continue
        if 'cheflola' not in row.get('notes', ''):
            continue

        name = row['recipe_ingredient_name'].strip()
        fdc_id, food_name = apply_keyword_rule(name)

        if food_name == 'negligible':
            row['match_status'] = 'skip'
            row['match_type']   = 'negligible'
            row['notes']        = 'Negligible: spice/flavouring/water with <5 kcal contribution per serving'
            negligible_marked += 1

        elif fdc_id is not None:
            row['matched_fdc_id']    = fdc_id
            row['matched_food_name'] = food_name
            row['match_status']      = 'matched'
            row['match_type']        = 'keyword_rule'
            row['notes']             = f'Keyword rule: matched to USDA "{food_name}"'
            keyword_matched += 1

        else:
            still_unmatched += 1

    with open(MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone!")
    print(f"  Keyword matched    : {keyword_matched}")
    print(f"  Negligible marked  : {negligible_marked}")
    print(f"  Still unmatched    : {still_unmatched}")

    if still_unmatched:
        remaining = [r['recipe_ingredient_name'] for r in rows
                     if r['match_status'].strip() == 'skip'
                     and 'cheflola' in r.get('notes', '')]
        print(f"\n  Remaining unmatched:")
        for n in sorted(remaining):
            print(f"    - {n}")

    print(f"\nNext: run calculate_nutrition.py")


if __name__ == '__main__':
    main()
