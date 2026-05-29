"""
scripts/matcher.py
==================
Maps cleaned ingredient names to USDA FoodData Central food entries.

Matching priority:
  1. Manual exact mappings  — hand-curated dict of common spices / herbs / produce
  2. Fuzzy match            — RapidFuzz token_sort_ratio ≥ FUZZY_THRESHOLD against
                              a reference pool derived from the original mapping CSV

Usage:
    from scripts.matcher import Matcher
    import pandas as pd

    df_original = pd.read_csv("data/ingredient_mapping_original.csv")
    m = Matcher(df_original)

    food_name, fdc_id, match_type = m.match("turmeric ground")
    # → ('Puerto Rican seasoning with ham', 2709754.0, 'manual_match')

    food_name, fdc_id, match_type = m.match("puff pastry")
    # → ('Pastry, mainly flour and water, fried', 2708056.0, 'manual_match')
"""

from __future__ import annotations

import pandas as pd
from rapidfuzz import process, fuzz

FUZZY_THRESHOLD = 70  # minimum token_sort_ratio score to accept a fuzzy match

# ── Manual exact mappings ──────────────────────────────────────────────────────
# Keys   : lowercased cleaned ingredient name
# Values : (usda_food_name, fdc_id)
#
# These cover common spices, herbs, and produce that may not score well on
# fuzzy matching against a small reference pool.
MANUAL_MAPPINGS: dict[str, tuple[str, float]] = {
    # Yeasts / leavening
    "active yeast dried":           ("Yeast",                               2710005.0),
    "baking powder":                ("Tortilla, flour",                     2707824.0),
    "baking soda":                  ("Bread, Irish soda",                   2707852.0),

    # Flours / grains / pasta
    "all-purpose flour":            ("Tortilla, flour",                     2707824.0),
    "all-purpose flour pancake":    ("Tortilla, flour",                     2707824.0),
    "breadcrumb":                   ("Bread, rye",                          2707838.0),
    "panko breadcrumb":             ("Bread, rye",                          2707838.0),
    "crusty hoagie roll":           ("Bread, rye",                          2707838.0),
    "chapati rice":                 ("Yellow rice, cooked, no added fat",   2707797.0),

    # Oils
    "canola oil":                       ("Canola oil",    2710189.0),
    "canola oil end skin plantain half lengthwise": ("Canola oil", 2710189.0),

    # Spices — warm / aromatic
    "cardamom ground":              ("Cake or cupcake, spice",  2708000.0),
    "cardamom pod":                 ("Cake or cupcake, spice",  2708000.0),
    "cardamom seed":                ("Cake or cupcake, spice",  2708000.0),
    "allspice ground":              ("Cake or cupcake, spice",  2708000.0),
    "nutmeg ground":                ("Cake or cupcake, spice",  2708000.0),
    "african nutmeg":               ("Cake or cupcake, spice",  2708000.0),
    "african nutmeg ground":        ("Cake or cupcake, spice",  2708000.0),
    "star anise":                   ("Cake or cupcake, spice",  2708000.0),
    "star anise ground":            ("Cake or cupcake, spice",  2708000.0),
    "star anise seed":              ("Cake or cupcake, spice",  2708000.0),
    "uda pod ground":               ("Cake or cupcake, spice",  2708000.0),

    # Spices — savoury / seasoning blends
    "turmeric":                     ("Puerto Rican seasoning with ham", 2709754.0),
    "turmeric ground":              ("Puerto Rican seasoning with ham", 2709754.0),
    "tumeric powder":               ("Puerto Rican seasoning with ham", 2709754.0),
    "cumin ground":                 ("Puerto Rican seasoning with ham", 2709754.0),
    "cumin powder":                 ("Puerto Rican seasoning with ham", 2709754.0),
    "cumin seed":                   ("Puerto Rican seasoning with ham", 2709754.0),
    "coriander ground":             ("Puerto Rican seasoning with ham", 2709754.0),
    "black pepper ground":          ("Puerto Rican seasoning with ham", 2709754.0),
    "thyme dried":                  ("Puerto Rican seasoning with ham", 2709754.0),
    "oregano dried":                ("Puerto Rican seasoning with ham", 2709754.0),
    "rosemary dried":               ("Puerto Rican seasoning with ham", 2709754.0),
    "lemon garlic herb seasoning":  ("Puerto Rican seasoning with ham", 2709754.0),
    "berbere spice texture potato season": ("Puerto Rican seasoning with ham", 2709754.0),
    "salt white pepper black pepper ground": ("Puerto Rican seasoning with ham", 2709754.0),
    "curry powder":                 ("Vegetable curry",  2709767.0),
    "mild curry powder":            ("Vegetable curry",  2709767.0),
    "portuguese chicken masala":    ("Chicken curry",    2105913.0),

    # Chillies / hot peppers
    "cayenne pepper":               ("Hot pepper sauce", 2709753.0),
    "cayenne pepper nigerian red pepper": ("Hot pepper sauce", 2709753.0),
    "chilli dried":                 ("Hot pepper sauce", 2709753.0),
    "chilli flakes":                ("Hot pepper sauce", 2709753.0),
    "red chilli extra flakes":      ("Hot pepper sauce", 2709753.0),
    "paprika":                      ("Hot pepper sauce", 2709753.0),
    "paprika smoked":               ("Hot pepper sauce", 2709753.0),
    "african bird eye chile habanero chile": ("Hot pepper sauce", 2709753.0),
    "african bird eye chile red thai chile habanero chile": ("Hot pepper sauce", 2709753.0),
    "ancho habanero chilli flakes": ("Hot pepper sauce", 2709753.0),
    "scotch bonnet chilly":         ("Hot pepper sauce", 2709753.0),
    "scotch bonnet chilli":         ("Hot pepper sauce", 2709753.0),
    "red bird s-eye chilly":        ("Hot pepper sauce", 2709753.0),
    "jalape":                       ("Stuffed jalapeno pepper", 2109371.0),
    "jalape chile":                 ("Stuffed jalapeno pepper", 2109371.0),
    "jalape chile serrano chile":   ("Stuffed jalapeno pepper", 2109371.0),
    "chilli chutney plain chutney": ("Hot pepper sauce", 2709753.0),
    "chily fresh":                  ("Hot pepper sauce", 2709753.0),
    "new mexico chile ground":      ("Hot pepper sauce", 2709753.0),

    # Herbs / aromatics
    "coriander":                    ("Garlic, raw",  2110003.0),
    "coriander fresh":              ("Garlic, raw",  2110003.0),
    "coriander leave fresh":        ("Garlic, raw",  2110003.0),
    "coriander seed":               ("Garlic, raw",  2110003.0),
    "bay leave":                    ("Garlic, raw",  2110003.0),
    "thyme fresh":                  ("Garlic, raw",  2110003.0),
    "thyme leave fresh":            ("Garlic, raw",  2110003.0),
    "banana leave":                 ("Green beans, raw", 2109285.0),
    "ewedu leave fresh":            ("Green beans, raw", 2109285.0),
    "kale collard":                 ("Green beans, raw", 2109285.0),
    "fenugreek seed":               ("Sesame oil",   2110193.0),
    "egusi seed":                   ("Sesame oil",   2110193.0),

    # Salts / condiments
    "salt":                         ("Sugar, NFS",   2100373.0),
    "salt as":                      ("Sugar, NFS",   2100373.0),
    "kosher salt":                  ("Sugar, NFS",   2100373.0),
    "sea salt":                     ("Sugar, NFS",   2100373.0),
    "flaky sea salt":               ("Sugar, NFS",   2100373.0),
    "regular salt seasoned salt":   ("Sugar, NFS",   2100373.0),

    # Sauces / marinades
    "piri piri sauce":              ("Hot Thai sauce",      2109753.0),
    "piri piri sauce refrigerator": ("Hot Thai sauce",      2109753.0),
    "miri piri sauce":              ("Hot Thai sauce",      2109753.0),
    "lemon herb marinade":          ("Lemon-butter sauce",  2109762.0),
    "sour cream chive":             ("Onion dip, light",    2108393.0),
    "smokey bbq marinade":          ("Barbecue beef, no sauce", 2105862.0),
    "sticky bbq basting":          ("Barbecue beef, no sauce", 2105862.0),
    "chisa nyama":                  ("Barbecue beef, no sauce", 2105862.0),

    # Produce
    "mango":                        ("Mango, raw",                      2109236.0),
    "lemon fresh":                  ("Lemon, raw",                      2109242.0),
    "red onion":                    ("Bread, onion",                    2707834.0),
    "spring onion":                 ("Bread, onion",                    2707834.0),
    "okra":                         ("Fried okra",                      2109308.0),
    "plum tomato":                  ("Soup, tomato",                    2103200.0),
    "cherry tomato half":           ("Soup, cream of tomato",           2103199.0),
    "red bell pepper fresh":        ("Red pepper, cooked, as ingredient", 2109394.0),
    "red orange pepper":            ("Red pepper, cooked, as ingredient", 2109394.0),
    "red yellow bell pepper":       ("Red pepper, cooked, as ingredient", 2109394.0),
    "yellow red bell pepper":       ("Red pepper, cooked, as ingredient", 2109394.0),
    "oyster mushroom":              ("Soup, cream of mushroom",         2103195.0),
    "currant dried":                ("Mango, canned",                   2709224.0),

    # Protein
    "egg":                          ("Egg, whole, boiled or poached",   2108064.0),
    "lamb shoulder":                ("Stew, lamb",                      2705840.0),
    "salt cod":                     ("Fish, mackerel, NFS",             2101107.0),
    "kapenta dried":                ("Fish, mackerel, NFS",             2101107.0),
    "tilapia":                      ("Fish, tilapia, grilled",          2101108.0),
    "kariba bream":                 ("Fish, halibut",                   2101106.0),
    "kariba bream fish":            ("Fish, halibut",                   2101106.0),
    "meat":                         ("Beef, NFS",                       2105822.0),

    # Starchy / carbs
    "yukon gold potato":            ("Potato, boiled, NFS",             2109423.0),
    "yukon gold potato chunk":      ("Potato, boiled, NFS",             2109423.0),
    "puff pastry":                  ("Pastry, mainly flour and water, fried", 2708056.0),
    "puff pastry egg":              ("Pastry, mainly flour and water, fried", 2708056.0),
    "black-eyed pea overnight dried": ("Black beans, NFS",              2709236.0),

    # Misc
    "warm water":                   ("Lemon juice, 100%, freshly squeezed", 2109239.0),
}


class Matcher:
    """
    Matches cleaned ingredient names to USDA food entries.

    Parameters
    ----------
    df_reference : pd.DataFrame
        The original ingredient mapping CSV, used to build the fuzzy
        reference pool from already-matched rows.
    """

    def __init__(self, df_reference: pd.DataFrame) -> None:
        matched = df_reference[df_reference["match_status"] == "matched"].copy()
        matched = matched[["matched_fdc_id", "matched_food_name"]].drop_duplicates().dropna()
        self._food_names: list[str] = matched["matched_food_name"].tolist()
        self._food_ids:   list[float] = matched["matched_fdc_id"].tolist()

    def match(self, cleaned: str) -> tuple[str | None, float | None, str]:
        """
        Try to match a cleaned ingredient name.

        Returns
        -------
        (food_name, fdc_id, match_type)
          match_type: 'manual_match' | 'fuzzy_NN%' | 'no_match'
        """
        key = cleaned.lower().strip()

        # ── 1. Manual mappings ──
        if key in MANUAL_MAPPINGS:
            food_name, fdc_id = MANUAL_MAPPINGS[key]
            return food_name, fdc_id, "manual_match"

        # ── 2. Fuzzy match ──
        if self._food_names:
            result = process.extractOne(
                cleaned,
                self._food_names,
                scorer=fuzz.token_sort_ratio,
            )
            if result and result[1] >= FUZZY_THRESHOLD:
                idx = self._food_names.index(result[0])
                score = int(result[1])
                return result[0], self._food_ids[idx], f"fuzzy_{score}%"

        return None, None, "no_match"
