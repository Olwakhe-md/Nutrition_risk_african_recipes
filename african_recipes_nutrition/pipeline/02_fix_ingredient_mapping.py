"""
fix_ingredient_mapping.py
=========================
Fixes two problems in ingredient_mapping_cleaned.csv:

  1. PROXY ingredients — 37 African/regional ingredients that have a suggested
     proxy food name but no fdc_id yet. This script assigns the best available
     USDA fdc_id for each proxy.

  2. BAD MATCHES — a few ingredients that the fuzzy matcher linked to the wrong
     USDA food. For example, "all purpose flour" was matched to "Taco shell, flour".
     This script corrects those to better options.

INPUT  : ingredient_mapping_cleaned.csv   (your fuzzy-matched file)
OUTPUT : ingredient_mapping_final.csv     (ready for the nutrition calculator)

How to run:
    python fix_ingredient_mapping.py
"""

import csv
import os

# ── File paths ────────────────────────────────────────────────────────────────
BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_INTERIM = os.path.join(BASE, 'data', 'interim')

INPUT_FILE   = os.path.join(DATA_INTERIM, 'ingredient_mapping_cleaned.csv')
OUTPUT_FILE  = os.path.join(DATA_INTERIM, 'ingredient_mapping_final.csv')

# ── SECTION 1: Proxy fdc_id assignments ───────────────────────────────────────
# These are the 37 African/regional ingredients that had no direct USDA match.
# We assign the closest available fdc_id from the USDA database.
# Format: "proxy food name" : (fdc_id, "USDA food description")
#
# Note: Where the USDA database has no close match (e.g. sorghum, yam),
# we use the nearest nutritionally similar food and flag it in the notes.

PROXY_FDC_MAP = {
    # Grains & flours
    "whole wheat flatbread"  : (2708157, "Crackers, flatbread"),
    "flatbread"              : (2708157, "Crackers, flatbread"),
    "millet"                 : (2708377, "Millet"),
    "pearl millet"           : (2708377, "Millet"),
    "finger millet"          : (2708377, "Millet"),
    "sorghum grain"          : (2708377, "Millet"),           # closest grain available
    "sorghum porridge"       : (2708363, "Grits, NFS"),       # porridge equivalent
    "white rice"             : (2708403, "Rice, white, cooked, NS as to fat"),
    "hominy corn"            : (2709933, "Hominy, cooked"),
    "corn on the cob"        : (2709933, "Hominy, cooked"),   # both are whole corn
    "cassava flour"          : (2709564, "Cassava, cooked"),

    # Vegetables & leaves
    "butternut squash"       : (2709693, "Winter squash, raw"),
    "african eggplant"       : (2709785, "Eggplant, raw"),
    "sweet potato leaves"    : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "amaranth leaves"        : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "hibiscus leaves"        : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "dried cowpea leaves"    : (2709642, "Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked"),
    "fresh tomato onion salad": (2709795, "Onions, raw"),     # closest simple salad base
    "green onion"            : (2709795, "Onions, raw"),
    "yam tuber"              : (2710794, "Sweet potato, cooked, as ingredient"), # closest root veg

    # Peppers & hot sauces
    "habanero pepper"        : (2710093, "Hot pepper sauce"),
    "hot chili pepper"       : (2710093, "Hot pepper sauce"),
    "serrano pepper"         : (2710093, "Hot pepper sauce"),

    # Spice blends (used in small amounts — low nutrition impact)
    "ethiopian spice blend"  : (2710093, "Hot pepper sauce"),  # berbere base is chili
    "indian spice blend"     : (2710093, "Hot pepper sauce"),  # garam masala base
    "moroccan spice blend"   : (2710093, "Hot pepper sauce"),  # ras el hanout base
    "chili spice paste"      : (2710093, "Hot pepper sauce"),  # harissa base

    # Nuts & sweeteners
    "ground peanuts"         : (2707519, "Peanuts, dry roasted, unsalted"),
    "unrefined cane sugar"   : (2710260, "Sugar, brown"),

    # Drinks
    "sweet white wine"       : (2710687, "Wine, sparkling"),
    "semolina flour"         : (2708157, "Crackers, flatbread"),  # closest flour-based
}

# ── SECTION 2: Bad match corrections ─────────────────────────────────────────
# These ingredients were given a wrong fdc_id by the fuzzy matcher.
# We fix them here by specifying the correct fdc_id and food name.
# Format: "recipe_ingredient_name" : (fdc_id, "correct USDA food name", "reason for change")

BAD_MATCH_FIXES = {
    # Plantains were matched to "Fried eggplant" — completely wrong
    "boiled fried plantain": (
        2709559,
        "Plantain, cooked with oil",
        "Corrected: was matched to fried eggplant"
    ),
    "green ripe plantain": (
        2709560,
        "Plantain, raw",
        "Corrected: was matched to Puerto Rican plantain pie"
    ),
    # All-purpose flour was matched to "Taco shell, flour" (has added fat)
    "all purpose flour": (
        2708157,
        "Crackers, flatbread",
        "Corrected: taco shell has added fat — flatbread is closer to plain flour"
    ),
    "all-purpose flour": (
        2708157,
        "Crackers, flatbread",
        "Corrected: taco shell has added fat — flatbread is closer to plain flour"
    ),
    "all-purpose flour as": (
        2708157,
        "Crackers, flatbread",
        "Corrected: taco shell has added fat — flatbread is closer to plain flour"
    ),
    "heaped flour": (
        2708157,
        "Crackers, flatbread",
        "Corrected: taco shell has added fat — flatbread is closer to plain flour"
    ),
    # African nutmeg matched to "Cake or cupcake, spice" — not specific enough
    # Note: no plain nutmeg exists in this USDA subset, so we keep spice but note it
    "african nutmeg": (
        2707885,
        "Cake or cupcake, spice",
        "Best available — no plain nutmeg in USDA subset; used in small amounts"
    ),
    "african nutmeg (ground)": (
        2707885,
        "Cake or cupcake, spice",
        "Best available — no plain nutmeg in USDA subset; used in small amounts"
    ),
}


# ── Main logic ────────────────────────────────────────────────────────────────

def fix_mapping(input_file, output_file):
    """Read the mapping CSV, apply fixes, and write the final version."""

    if not os.path.exists(input_file):
        print(f"ERROR: Could not find '{input_file}'")
        print("Make sure you run this script from the same folder as your CSV files.")
        return

    rows = []
    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    proxy_fixed   = 0
    bad_fixed     = 0
    still_missing = []

    for row in rows:
        ingredient = row["recipe_ingredient_name"].strip()
        match_type = row["match_type"].strip()
        proxy_name = row["matched_food_name"].strip().lower()

        # ── Fix 1: Assign fdc_id to proxy ingredients ──────────────────────
        if match_type == "african_proxy":
            if proxy_name in PROXY_FDC_MAP:
                fdc_id, food_name = PROXY_FDC_MAP[proxy_name]
                row["matched_fdc_id"]   = fdc_id
                row["matched_food_name"] = food_name
                row["match_status"]     = "matched"
                row["notes"]            = f"African proxy resolved: '{proxy_name}' → USDA '{food_name}'"
                proxy_fixed += 1
            else:
                still_missing.append(ingredient)

        # ── Fix 2: Correct bad fuzzy matches ──────────────────────────────
        if ingredient in BAD_MATCH_FIXES:
            fdc_id, food_name, reason = BAD_MATCH_FIXES[ingredient]
            row["matched_fdc_id"]    = fdc_id
            row["matched_food_name"] = food_name
            row["notes"]             = reason
            bad_fixed += 1

    # Write the fixed file
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n✓ Done!")
    print(f"  Proxy fdc_ids resolved : {proxy_fixed}")
    print(f"  Bad matches corrected  : {bad_fixed}")
    print(f"  Output saved to        : {output_file}")

    if still_missing:
        print(f"\n⚠  {len(still_missing)} proxy ingredient(s) still have no fdc_id:")
        for name in still_missing:
            print(f"   - {name}")
        print("  These will be skipped in the nutrition calculation.")

    # Count final status
    matched = sum(1 for r in rows if r["match_status"].strip() == "matched")
    skipped = sum(1 for r in rows if r["match_status"].strip() == "skip")
    total   = len(rows)
    print(f"\n  Final mapping: {matched}/{total} matched, {skipped} skipped")


if __name__ == "__main__":
    fix_mapping(INPUT_FILE, OUTPUT_FILE)
