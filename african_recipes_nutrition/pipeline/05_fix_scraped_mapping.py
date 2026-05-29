"""
fix_scraped_mapping.py
======================
Resolves the 101 unmatched ingredients from the 59 scraped allrecipes recipes.

Three passes over the unmatched rows:

  Pass 1 — PROXY_FDC_MAP (from fix_ingredient_mapping.py)
      Catches ingredient names that are themselves proxy food names
      (e.g. "moroccan spice blend", "indian spice blend").

  Pass 2 — DIRECT_MAP
      Manual FDC ID assignments for significant ingredients that the
      fuzzy matcher missed (e.g. "eggs", "cod fillets", "dry couscous").

  Pass 3 — NEGLIGIBLE / ARTIFACTS
      Marks pure spices, salts, water, and parsing artifacts as
      match_status='skip' with a descriptive note.  These contribute
      negligible calories (< 5 kcal per serving) and are intentionally
      excluded from the nutrition calculation.

Run from african_recipes_nutrition/:
    py fix_scraped_mapping.py
"""

import csv
import os

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING_FILE = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')

# ── Pass 1: PROXY_FDC_MAP (copied from fix_ingredient_mapping.py) ──────────────
# These are ingredient names that ARE proxy food names — they appear in the
# unmatched list because the cleaner returned the name as-is (no further proxy
# lookup was done on outputs of the African proxy table).

PROXY_FDC_MAP = {
    "whole wheat flatbread"   : (2708157, "Crackers, flatbread"),
    "flatbread"               : (2708157, "Crackers, flatbread"),
    "millet"                  : (2708377, "Millet"),
    "pearl millet"            : (2708377, "Millet"),
    "finger millet"           : (2708377, "Millet"),
    "sorghum grain"           : (2708377, "Millet"),
    "sorghum porridge"        : (2708363, "Grits, NFS"),
    "white rice"              : (2708403, "Rice, white, cooked, NS as to fat"),
    "hominy corn"             : (2709933, "Hominy, cooked"),
    "corn on the cob"         : (2709933, "Hominy, cooked"),
    "cassava flour"           : (2709564, "Cassava, cooked"),
    "butternut squash"        : (2709693, "Winter squash, raw"),
    "african eggplant"        : (2709785, "Eggplant, raw"),
    "sweet potato leaves"     : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "amaranth leaves"         : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "hibiscus leaves"         : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "dried cowpea leaves"     : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "fresh tomato onion salad": (2709795, "Onions, raw"),
    "green onion"             : (2709795, "Onions, raw"),
    "yam tuber"               : (2710794, "Sweet potato, cooked, as ingredient"),
    "habanero pepper"         : (2710093, "Hot pepper sauce"),
    "hot chili pepper"        : (2710093, "Hot pepper sauce"),
    "serrano pepper"          : (2710093, "Hot pepper sauce"),
    "ethiopian spice blend"   : (2710093, "Hot pepper sauce"),
    "indian spice blend"      : (2710093, "Hot pepper sauce"),
    "moroccan spice blend"    : (2710093, "Hot pepper sauce"),
    "chili spice paste"       : (2710093, "Hot pepper sauce"),
    "ground peanuts"          : (2707519, "Peanuts, dry roasted, unsalted"),
    "unrefined cane sugar"    : (2710260, "Sugar, brown"),
    "sweet white wine"        : (2710687, "Wine, sparkling"),
    "semolina flour"          : (2708157, "Crackers, flatbread"),
}

# ── Pass 2: DIRECT_MAP ──────────────────────────────────────────────────────────
# Manual FDC assignments for common allrecipes ingredients not in the
# African-recipe reference pool.  Proxy notes explain non-exact matches.

DIRECT_MAP = {
    # Grains & starches
    "dry couscous"               : (2708441, "Couscous, plain, cooked"),
    "pearl israeli couscous"     : (2708441, "Couscous, plain, cooked"),
    "vermicelli pasta"           : (2708357, "Pasta, cooked"),
    "1/2 long vermicelli"        : (2708357, "Pasta, cooked"),
    "uncooked elbow macaroni"    : (2708357, "Pasta, cooked"),
    "uncooked brown rice"        : (2708409, "Rice, brown, cooked, NS as to fat"),
    "egyptian rice short-grain rice": (2708403, "Rice, white, cooked, NS as to fat"),
    "brown teff flour"           : (2708377, "Millet"),             # closest grain in USDA subset

    # Legumes
    "dried lentils"              : (2707423, "Lentils, NFS"),
    "beluga lentils"             : (2707423, "Lentils, NFS"),
    "dried red lentils"          : (2707423, "Lentils, NFS"),
    "garbanzo beans"             : (2707414, "Chickpeas, NFS"),
    "low-sodium chickpeas"       : (2707414, "Chickpeas, NFS"),
    "canned chickpeas"           : (2707414, "Chickpeas, NFS"),
    "cannellini beans"           : (2707353, "White beans, NFS"),

    # Proteins
    "eggs"                       : (2108064, "Egg, whole, boiled or poached"),
    "egg yolks"                  : (2707172, "Egg, yolk only, raw"),
    "cod fillets"                : (2706240, "Fish, cod, NFS"),
    "lamb meat"                  : (2705840, "Stew, lamb"),
    "boneless lamb shoulder"     : (2705840, "Stew, lamb"),
    "mutton chops"               : (2705840, "Stew, lamb"),
    "bone-in chicken breast halves": (2705929, "Chicken, NS as to part and cooking method, NS as to skin eaten"),
    "boneless pork loin roast"   : (2705862, "Pork, NFS"),

    # Dairy & fats
    "butter or margarine"        : (2710154, "Butter, NFS"),

    # Vegetables
    "onion"                      : (2709795, "Onions, raw"),
    "yellow onion"               : (2709795, "Onions, raw"),
    "sweet onion"                : (2709795, "Onions, raw"),
    "chopped onion"              : (2709795, "Onions, raw"),
    "shallot"                    : (2709795, "Onions, raw"),
    "ribs celery with leaves"    : (2709778, "Celery, raw"),
    "thinly sliced bell peppers" : (2709801, "Peppers, sweet, red, raw"),
    "finely shredded kale"       : (2709600, "Kale, fresh, cooked, no added fat"),
    "yucca cassava roots"        : (2709564, "Cassava, cooked"),

    # Spice blends → hot pepper sauce proxy (same logic as original African proxies)
    "berbere seasoning"          : (2710093, "Hot pepper sauce"),
    "harissa"                    : (2710093, "Hot pepper sauce"),
    "cumin"                      : (2709754, "Puerto Rican seasoning with ham"),
    "anaheim chile peppers"      : (2710093, "Hot pepper sauce"),
    "mild to medium hot red chile peppers": (2710093, "Hot pepper sauce"),

    # Nuts & dried fruit
    "blanched almonds"           : (2707485, "Almonds, NFS"),
    "chopped pecans"             : (2707521, "Pecans, NFS"),
    "chopped walnuts"            : (2707531, "Walnuts, excluding honey roasted"),
    "chopped dates"              : (2709203, "Date"),

    # Sweeteners
    "superfine sugar"            : (2710257, "Sugar, NFS"),

    # Leavening
    "active dry yeast"           : (2710005, "Yeast"),

    # Pastry & wrappers
    "frozen puff pastry sheets"  : (2708056, "Pastry, mainly flour and water, fried"),
    "spring roll wrappers"       : (2708056, "Pastry, mainly flour and water, fried"),
    "texas toast thick-sliced bread": (2707838, "Bread, rye"),

    # Broth & bouillon (mostly water, small caloric contribution)
    "chicken bouillon granules"  : (2707132, "Soup, broth"),
    "cube beef bouillon cube"    : (2707132, "Soup, broth"),
    "cubes chicken bouillon"     : (2707132, "Soup, broth"),
    "low-sodium beef broth"      : (2707132, "Soup, broth"),
    "homemade chicken broth or low-sodium canned broth": (2707132, "Soup, broth"),

    # Fresh herbs
    "chopped fresh cilantro"          : (2709782, "Cilantro, raw"),
    "chopped fresh parsley"           : (2709796, "Parsley, raw"),
    "chopped fresh flat-leaf parsley" : (2709796, "Parsley, raw"),
    "fresh parsley"                   : (2709796, "Parsley, raw"),
    "chopped fresh mint"              : (2709796, "Parsley, raw"),   # closest green herb
    "thinly sliced fresh mint"        : (2709796, "Parsley, raw"),
    "fresh dill"                      : (2709796, "Parsley, raw"),
    "dried parsley flakes"            : (2709796, "Parsley, raw"),

    # Fresh ginger (small amounts; pickled ginger is closest USDA entry)
    "chopped fresh ginger"       : (2710082, "Ginger root, pickled"),
    "grated fresh ginger"        : (2710082, "Ginger root, pickled"),
    "freshly grated ginger"      : (2710082, "Ginger root, pickled"),
    "minced fresh ginger"        : (2710082, "Ginger root, pickled"),
    "ginger-garlic paste"        : (2110003, "Garlic, raw"),         # garlic-dominant paste

    # Misc
    "quart oil"                  : (2710189, "Canola oil"),           # oil proxy
}

# Substring rules for ingredients with trademark symbols or long suffixes
# Format: (substring_to_check, fdc_id, food_name)
SUBSTRING_RULES = [
    ("maggi",      2707132, "Soup, broth"),
    ("uncle ben",  2708403, "Rice, white, cooked, NS as to fat"),
]

# ── Pass 3: NEGLIGIBLE ──────────────────────────────────────────────────────────
# Pure spices, whole seasoning seeds, salts, water, and flavouring extracts.
# Typical serving contribution < 5 kcal — intentionally excluded from nutrition.

NEGLIGIBLE = {
    # Whole & cracked pepper
    "allspice berries", "black peppercorns", "white peppercorns",
    "multi-colored peppercorns", "cracked black pepper",
    "freshly ground black pepper", "ground black pepper", "ground white pepper",

    # Dried ground spices (< 1 tsp per serving)
    "ground cardamom", "ground cayenne pepper", "ground cloves",
    "ground coriander", "ground coriander seed", "ground cumin seeds",
    "ground dried new mexico chiles", "ground fenugreek", "ground ginger",
    "smoked paprika", "caraway seeds",

    # Chilli powders & blends used in tsp quantities
    "chili powder optional", "hot chili powder", "red pepper flakes optional",
    "herbes de provence",

    # Whole aromatics removed before eating
    "bay leaves", "saffron",

    # Salt & combined salt/pepper
    "salt and ground black pepper", "onion powder",

    # Flavouring liquids & extracts (< 1 tbsp)
    "orange-flower water", "vanilla",

    # Water (zero calories)
    "warm water 115 degrees f/46 degrees c",

    # Zests & citrus flavourings (< 1g, negligible)
    "grated zest of one orange",
}

# ── Parsing artefacts (stray words from the ingredient line parser) ─────────────
ARTIFACTS = {"chopped", "red", "skinless", "cornstarch optional"}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Fix Scraped Ingredient Mappings")
    print("=" * 40)

    with open(MAPPING_FILE, newline='', encoding='utf-8') as f:
        reader     = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows       = list(reader)

    unmatched = [r for r in rows if r['match_status'].strip() == 'skip'
                 and 'scraped' in r.get('notes', '')]
    print(f"Unmatched scraped ingredients to fix: {len(unmatched)}")

    proxy_fixed    = 0
    direct_fixed   = 0
    substring_fixed= 0
    negligible_marked = 0
    artifact_marked   = 0
    still_unmatched   = 0

    for row in rows:
        if row['match_status'].strip() != 'skip':
            continue
        if 'scraped' not in row.get('notes', ''):
            continue

        name = row['recipe_ingredient_name'].strip().lower()

        # ── Pass 1: proxy map (by ingredient name directly) ───────────────────
        if name in PROXY_FDC_MAP:
            fdc_id, food_name = PROXY_FDC_MAP[name]
            row['matched_fdc_id']    = fdc_id
            row['matched_food_name'] = food_name
            row['match_status']      = 'matched'
            row['match_type']        = 'proxy_fix'
            row['notes']             = f'Proxy resolved: matched to USDA "{food_name}"'
            proxy_fixed += 1
            continue

        # ── Pass 2: direct manual map ─────────────────────────────────────────
        if name in DIRECT_MAP:
            fdc_id, food_name = DIRECT_MAP[name]
            row['matched_fdc_id']    = fdc_id
            row['matched_food_name'] = food_name
            row['match_status']      = 'matched'
            row['match_type']        = 'manual_fix'
            row['notes']             = f'Manual fix: matched to USDA "{food_name}"'
            direct_fixed += 1
            continue

        # ── Pass 2b: substring rules for trademark-symbol names ───────────────
        matched_by_substr = False
        for substr, fdc_id, food_name in SUBSTRING_RULES:
            if substr in name:
                row['matched_fdc_id']    = fdc_id
                row['matched_food_name'] = food_name
                row['match_status']      = 'matched'
                row['match_type']        = 'manual_fix'
                row['notes']             = f'Manual fix (substring "{substr}"): matched to USDA "{food_name}"'
                substring_fixed += 1
                matched_by_substr = True
                break
        if matched_by_substr:
            continue

        # ── Pass 3a: negligible spices / seasonings ───────────────────────────
        if name in NEGLIGIBLE:
            row['match_status'] = 'skip'
            row['match_type']   = 'negligible'
            row['notes']        = 'Negligible: spice/flavouring with <5 kcal contribution per serving'
            negligible_marked += 1
            continue

        # ── Pass 3b: parsing artefacts ────────────────────────────────────────
        if name in ARTIFACTS:
            row['match_status'] = 'skip'
            row['match_type']   = 'artifact'
            row['notes']        = 'Parsing artefact: not a real ingredient'
            artifact_marked += 1
            continue

        still_unmatched += 1

    # ── Write ──────────────────────────────────────────────────────────────────
    with open(MAPPING_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── Summary ────────────────────────────────────────────────────────────────
    total_fixed = proxy_fixed + direct_fixed + substring_fixed
    print(f"\nDone!")
    print(f"  Proxy map resolved    : {proxy_fixed}")
    print(f"  Direct map resolved   : {direct_fixed}")
    print(f"  Substring resolved    : {substring_fixed}")
    print(f"  Negligible marked     : {negligible_marked}")
    print(f"  Artefacts marked      : {artifact_marked}")
    print(f"  Total newly matched   : {total_fixed}")
    print(f"  Still unmatched       : {still_unmatched}")

    if still_unmatched:
        remaining = [r['recipe_ingredient_name'] for r in rows
                     if r['match_status'].strip() == 'skip'
                     and 'scraped' in r.get('notes', '')]
        print(f"\n  Remaining unmatched ingredients:")
        for n in sorted(remaining):
            print(f"    - {n}")

    print(f"\nNext step: re-run calculate_nutrition.py")


if __name__ == '__main__':
    main()
