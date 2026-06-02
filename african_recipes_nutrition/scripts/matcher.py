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

    # ── Eggs (fdc_id 2108064 is absent from our local nutrient extract;
    #         2707154 = "Egg, whole, boiled or poached", 143 kcal/100g — confirmed present)
    "egg":                          ("Egg, whole, boiled or poached",       2707154.0),
    "eggs":                         ("Egg, whole, boiled or poached",       2707154.0),
    "egg white":                    ("Egg, white only, raw",                2707168.0),
    "egg whites":                   ("Egg, white only, raw",                2707168.0),
    "egg yolk":                     ("Egg, yolk only, raw",                 2707172.0),
    "egg yolks":                    ("Egg, yolk only, raw",                 2707172.0),

    # ── Herbs (fresh or dried — small quantities, garlic is a reasonable proxy) ─
    "parsley":                      ("Garlic, raw",                         2110003.0),
    "cilantro":                     ("Garlic, raw",                         2110003.0),
    "coriander":                    ("Garlic, raw",                         2110003.0),
    "basil":                        ("Garlic, raw",                         2110003.0),
    "mint":                         ("Garlic, raw",                         2110003.0),
    "dill":                         ("Garlic, raw",                         2110003.0),
    "chive":                        ("Garlic, raw",                         2110003.0),
    "chives":                       ("Garlic, raw",                         2110003.0),
    "sage":                         ("Garlic, raw",                         2110003.0),

    # ── Spices (base names — modifier-stripping handles "ground", "mild" etc.) ─
    "cumin":                        ("Puerto Rican seasoning with ham",     2709754.0),
    "chili powder":                 ("Hot pepper sauce",                    2709753.0),
    "chilli powder":                ("Hot pepper sauce",                    2709753.0),
    "cinnamon":                     ("Cake or cupcake, spice",              2708000.0),
    "clove":                        ("Cake or cupcake, spice",              2708000.0),
    "cloves":                       ("Cake or cupcake, spice",              2708000.0),
    "pepper":                       ("Puerto Rican seasoning with ham",     2709754.0),
    "black pepper":                 ("Puerto Rican seasoning with ham",     2709754.0),
    "white pepper":                 ("Puerto Rican seasoning with ham",     2709754.0),
    "mixed spice":                  ("Puerto Rican seasoning with ham",     2709754.0),
    "spice":                        ("Puerto Rican seasoning with ham",     2709754.0),
    "seasoning":                    ("Puerto Rican seasoning with ham",     2709754.0),
    "cayenne":                      ("Hot pepper sauce",                    2709753.0),
    "cayenne pepper":               ("Hot pepper sauce",                    2709753.0),
    "chili":                        ("Hot pepper sauce",                    2709753.0),
    "chilli":                       ("Hot pepper sauce",                    2709753.0),
    "hot pepper":                   ("Hot pepper sauce",                    2709753.0),

    # ── Bell peppers by colour ────────────────────────────────────────────────
    "red bell pepper":              ("Peppers, sweet, red, raw",            2709801.0),
    "green bell pepper":            ("Peppers, sweet, red, raw",            2709801.0),
    "yellow bell pepper":           ("Peppers, sweet, red, raw",            2709801.0),
    "orange bell pepper":           ("Peppers, sweet, red, raw",            2709801.0),

    # ── Common dairy / dairy alternatives ─────────────────────────────────────
    "milk":                         ("Buttermilk",                          2705393.0),
    "whole milk":                   ("Buttermilk",                          2705393.0),
    "cream":                        ("Buttermilk",                          2705393.0),
    "heavy cream":                  ("Buttermilk",                          2705393.0),
    "sour cream":                   ("Buttermilk",                          2705393.0),
    "yogurt":                       ("Buttermilk",                          2705393.0),
    "yoghurt":                      ("Buttermilk",                          2705393.0),
    "cheese":                       ("Butter, NFS",                         2710154.0),

    # ── Legumes / pulses ──────────────────────────────────────────────────────
    "lentils":                      ("Black beans, NFS",                    2709236.0),
    "lentil":                       ("Black beans, NFS",                    2709236.0),
    "chickpeas":                    ("Black beans, NFS",                    2709236.0),
    "chickpea":                     ("Black beans, NFS",                    2709236.0),
    "kidney beans":                 ("Black beans, NFS",                    2709236.0),
    "black beans":                  ("Black beans, NFS",                    2709236.0),
    "peas":                         ("Black beans, NFS",                    2709236.0),
    "beans":                        ("Black beans, NFS",                    2709236.0),
    "cowpeas":                      ("Black beans, NFS",                    2709236.0),

    # ── Starchy staples ───────────────────────────────────────────────────────
    "flour":                        ("Tortilla, flour",                     2707824.0),
    "cornmeal":                     ("Tortilla, flour",                     2707824.0),
    "corn flour":                   ("Tortilla, flour",                     2707824.0),
    "potato":                       ("Potato, boiled, NFS",                 2109423.0),
    "potatoes":                     ("Potato, boiled, NFS",                 2109423.0),
    "sweet potato":                 ("Sweet potato, cooked, as ingredient", 2710794.0),
    "sweet potatoes":               ("Sweet potato, cooked, as ingredient", 2710794.0),
    "pasta":                        ("Pasta, cooked, NS as to type",        2708991.0),
    "noodles":                      ("Pasta, cooked, NS as to type",        2708991.0),
    "bread":                        ("Bread, rye",                          2707838.0),

    # ── Nuts and seeds ────────────────────────────────────────────────────────
    "almonds":                      ("Peanut butter",                       2707537.0),
    "almond":                       ("Peanut butter",                       2707537.0),
    "walnuts":                      ("Peanut butter",                       2707537.0),
    "cashews":                      ("Peanut butter",                       2707537.0),
    "peanuts":                      ("Peanut butter",                       2707537.0),
    "groundnuts":                   ("Peanut butter",                       2707537.0),
    "sesame seeds":                 ("Sesame oil",                          2110193.0),
    "sesame":                       ("Sesame oil",                          2110193.0),

    # ── Common recipe staples (added for live recipe input) ───────────────────
    # These cover the plain-language names a user would type.  The fuzzy matcher
    # scores short words like "rice" or "onion" below the 70-point threshold
    # against multi-word USDA names, so explicit entries are needed.

    # Rice
    "rice":                         ("Rice, white, cooked, NS as to fat",   2708403.0),
    "white rice":                   ("Rice, white, cooked, NS as to fat",   2708403.0),
    "basmati rice":                 ("Rice, white, cooked, NS as to fat",   2708403.0),
    "long grain rice":              ("Rice, white, cooked, NS as to fat",   2708403.0),
    "brown rice":                   ("Rice, white, cooked, NS as to fat",   2708403.0),
    "parboiled rice":               ("Rice, white, cooked, NS as to fat",   2708403.0),
    "jasmine rice":                 ("Rice, white, cooked, NS as to fat",   2708403.0),

    # Onion / shallot
    "onion":                        ("Onions, raw",                         2709795.0),
    "onions":                       ("Onions, raw",                         2709795.0),
    "white onion":                  ("Onions, raw",                         2709795.0),
    "yellow onion":                 ("Onions, raw",                         2709795.0),
    "brown onion":                  ("Onions, raw",                         2709795.0),
    "large onion":                  ("Onions, raw",                         2709795.0),
    "medium onion":                 ("Onions, raw",                         2709795.0),
    "small onion":                  ("Onions, raw",                         2709795.0),
    "shallot":                      ("Onions, raw",                         2709795.0),
    "shallots":                     ("Onions, raw",                         2709795.0),

    # Garlic
    "garlic":                       ("Garlic, raw",                         2709786.0),
    "garlic clove":                 ("Garlic, raw",                         2709786.0),
    "garlic cloves":                ("Garlic, raw",                         2709786.0),
    "fresh garlic":                 ("Garlic, raw",                         2709786.0),
    "minced garlic":                ("Garlic, raw",                         2709786.0),
    "garlic minced":                ("Garlic, raw",                         2709786.0),
    "garlic paste":                 ("Garlic, raw",                         2709786.0),
    "garlic powder":                ("Garlic, raw",                         2709786.0),

    # Ginger
    "ginger":                       ("Ginger root, pickled",                2710082.0),
    "fresh ginger":                 ("Ginger root, pickled",                2710082.0),
    "ginger root":                  ("Ginger root, pickled",                2710082.0),
    "ginger paste":                 ("Ginger root, pickled",                2710082.0),
    "ground ginger":                ("Ginger root, pickled",                2710082.0),

    # Tomato
    "tomato":                       ("Tomatoes, raw",                       2709719.0),
    "tomatoes":                     ("Tomatoes, raw",                       2709719.0),
    "fresh tomatoes":               ("Tomatoes, raw",                       2709719.0),
    "roma tomato":                  ("Tomatoes, raw",                       2709719.0),
    "large tomato":                 ("Tomatoes, raw",                       2709719.0),
    "medium tomato":                ("Tomatoes, raw",                       2709719.0),
    "tinned tomatoes":              ("Tomatoes, raw",                       2709719.0),
    "canned tomatoes":              ("Tomatoes, raw",                       2709719.0),
    "tomato paste":                 ("Tomatoes, raw",                       2709719.0),
    "tomato puree":                 ("Tomatoes, raw",                       2709719.0),
    "tomato sauce":                 ("Tomatoes, raw",                       2709719.0),

    # Chicken
    "chicken":                      ("Chicken breast, stewed, skin eaten",  2705965.0),
    "chicken breast":               ("Chicken breast, stewed, skin eaten",  2705965.0),
    "chicken breasts":              ("Chicken breast, stewed, skin eaten",  2705965.0),
    "chicken thigh":                ("Chicken thigh, stewed, skin eaten",   2706037.0),
    "chicken thighs":               ("Chicken thigh, stewed, skin eaten",   2706037.0),
    "chicken leg":                  ("Chicken thigh, stewed, skin eaten",   2706037.0),
    "chicken legs":                 ("Chicken thigh, stewed, skin eaten",   2706037.0),
    "chicken wings":                ("Chicken thigh, stewed, skin eaten",   2706037.0),
    "chicken pieces":               ("Chicken breast, stewed, skin eaten",  2705965.0),
    "whole chicken":                ("Chicken breast, stewed, skin eaten",  2705965.0),

    # Beef
    "beef":                         ("Beef, NFS",                           2705822.0),
    "minced beef":                  ("Beef, NFS",                           2705822.0),
    "beef mince":                   ("Beef, NFS",                           2705822.0),
    "ground beef":                  ("Beef, NFS",                           2705822.0),
    "beef steak":                   ("Beef, steak, cube",                   2705826.0),
    "stewing beef":                 ("Beef, NFS",                           2705822.0),

    # Oils / fats
    "palm oil":                     ("Palm oil",                            2710197.0),
    "red palm oil":                 ("Palm oil",                            2710197.0),
    "vegetable oil":                ("Vegetable oil, NFS",                  2710180.0),
    "cooking oil":                  ("Vegetable oil, NFS",                  2710180.0),
    "sunflower oil":                ("Vegetable oil, NFS",                  2710180.0),
    "corn oil":                     ("Corn oil",                            2710183.0),
    "olive oil":                    ("Olive oil",                           2710192.0),
    "groundnut oil":                ("Peanut oil",                          2710187.0),
    "peanut oil":                   ("Peanut oil",                          2710187.0),
    "ghee":                         ("Butter, NFS",                         2710154.0),
    "clarified butter":             ("Butter, NFS",                         2710154.0),

    # Butter / dairy
    "butter":                       ("Butter, NFS",                         2710154.0),
    "unsalted butter":              ("Butter, NFS",                         2710154.0),
    "salted butter":                ("Butter, NFS",                         2710154.0),
    "coconut milk":                 ("Coconut milk",                        2705413.0),
    "coconut cream":                ("Coconut milk",                        2705413.0),

    # Fish / seafood
    "fish":                         ("Fish, mackerel, NFS",                 2706263.0),
    "salmon":                       ("Fish, mackerel, NFS",                 2706263.0),
    "tuna":                         ("Fish, mackerel, NFS",                 2706263.0),
    "mackerel":                     ("Fish, mackerel, NFS",                 2706263.0),
    "catfish":                      ("Fish, mackerel, NFS",                 2706263.0),
    "prawns":                       ("Shrimp, NFS",                         2104801.0),
    "shrimp":                       ("Shrimp, NFS",                         2104801.0),

    # Vegetables
    "spinach":                      ("Spinach, raw",                        2709614.0),
    "fresh spinach":                ("Spinach, raw",                        2709614.0),
    "frozen spinach":               ("Spinach, raw",                        2709614.0),
    "plantain":                     ("Plantain, raw",                       2709560.0),
    "green plantain":               ("Plantain, raw",                       2709560.0),
    "ripe plantain":                ("Plantain, raw",                       2709560.0),
    "yam":                          ("Sweet potato, cooked, as ingredient", 2710794.0),
    "bell pepper":                  ("Peppers, sweet, red, raw",            2709801.0),
    "green pepper":                 ("Peppers, sweet, red, raw",            2709801.0),
    "red pepper":                   ("Peppers, sweet, red, raw",            2709801.0),
    "yellow pepper":                ("Peppers, sweet, red, raw",            2709801.0),

    # Stocks / broths
    "chicken stock":                ("Soup, broth",                         2707132.0),
    "beef stock":                   ("Soup, broth",                         2707132.0),
    "vegetable stock":              ("Soup, broth",                         2707132.0),
    "chicken broth":                ("Soup, broth",                         2707132.0),
    "beef broth":                   ("Soup, broth",                         2707132.0),
    "stock":                        ("Soup, broth",                         2707132.0),
    "broth":                        ("Soup, broth",                         2707132.0),
    "water":                        ("Lemon juice, 100%, freshly squeezed", 2109239.0),

    # ── Bouillon / stock cubes ────────────────────────────────────────────────
    "bouillon":                     ("Soup, broth",                         2707132.0),
    "bouillon powder":              ("Soup, broth",                         2707132.0),
    "bouillon cube":                ("Soup, broth",                         2707132.0),
    "bouillon cubes":               ("Soup, broth",                         2707132.0),
    "stock cube":                   ("Soup, broth",                         2707132.0),
    "stock cubes":                  ("Soup, broth",                         2707132.0),
    "maggi":                        ("Soup, broth",                         2707132.0),
    "maggi cube":                   ("Soup, broth",                         2707132.0),
    "knorr":                        ("Soup, broth",                         2707132.0),

    # ── Root vegetables ───────────────────────────────────────────────────────
    "carrot":                       ("Carrots, raw",                        2709660.0),
    "carrots":                      ("Carrots, raw",                        2709660.0),
    "potato":                       ("Potato, baked, NFS",                  2709383.0),
    "potatoes":                     ("Potato, baked, NFS",                  2709383.0),
    "sweet potato":                 ("Sweet potato, cooked, as ingredient", 2710794.0),
    "sweet potatoes":               ("Sweet potato, cooked, as ingredient", 2710794.0),
    "yam":                          ("Sweet potato, cooked, as ingredient", 2710794.0),
    # Low-calorie proxy for root veg without their own fdc_id in our extract
    "beetroot":                     ("Carrots, raw",                        2709660.0),
    "beet":                         ("Carrots, raw",                        2709660.0),
    "turnip":                       ("Carrots, raw",                        2709660.0),
    "parsnip":                      ("Carrots, raw",                        2709660.0),
    "radish":                       ("Carrots, raw",                        2709660.0),

    # ── Green / cruciferous vegetables ───────────────────────────────────────
    "green beans":                  ("Green beans, pickled",                2710070.0),
    "green bean":                   ("Green beans, pickled",                2710070.0),
    "french beans":                 ("Green beans, pickled",                2710070.0),
    "runner beans":                 ("Green beans, pickled",                2710070.0),
    "broccoli":                     ("Broccoli, raw",                       2709643.0),
    "cauliflower":                  ("Cauliflower, raw",                    2709777.0),
    "cabbage":                      ("Cabbage, red, raw",                   2709775.0),
    "courgette":                    ("Eggplant, raw",                       2709785.0),
    "zucchini":                     ("Eggplant, raw",                       2709785.0),
    "aubergine":                    ("Eggplant, raw",                       2709785.0),
    "eggplant":                     ("Eggplant, raw",                       2709785.0),
    "kale":                         ("Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked", 2709642.0),
    "collard greens":               ("Sweet potato, squash, pumpkin, chrysanthemum, or bean leaves, cooked", 2709642.0),
    "leek":                         ("Leeks",                               2709935.0),
    "leeks":                        ("Leeks",                               2709935.0),
    "mushroom":                     ("Mushrooms, raw",                      2709793.0),
    "mushrooms":                    ("Mushrooms, raw",                      2709793.0),
    "corn":                         ("Corn, raw",                           2709783.0),
    "sweetcorn":                    ("Corn, raw",                           2709783.0),
    "peas":                         ("Green peas, raw",                     2709797.0),
    "pea":                          ("Green peas, raw",                     2709797.0),
    "green peas":                   ("Green peas, raw",                     2709797.0),
    "pumpkin":                      ("Pumpkin, cooked",                     2709692.0),
    "squash":                       ("Pumpkin, cooked",                     2709692.0),
    "butternut squash":             ("Pumpkin, cooked",                     2709692.0),
    "celery":                       ("Eggplant, raw",                       2709785.0),

    # ── Legumes ───────────────────────────────────────────────────────────────
    "cannellini beans":             ("Lima beans, from canned",             2709850.0),
    "cannellini":                   ("Lima beans, from canned",             2709850.0),
    "white beans":                  ("Lima beans, from canned",             2709850.0),
    "white bean":                   ("Lima beans, from canned",             2709850.0),
    "butter beans":                 ("Lima beans, from canned",             2709850.0),
    "butter bean":                  ("Lima beans, from canned",             2709850.0),
    "broad beans":                  ("Lima beans, from canned",             2709850.0),
    "broad bean":                   ("Lima beans, from canned",             2709850.0),
    "borlotti beans":               ("Lima beans, from canned",             2709850.0),
    "black beans":                  ("Black beans, NFS",                    2709236.0),
    "black bean":                   ("Black beans, NFS",                    2709236.0),
    "kidney bean":                  ("Lima beans, from canned",             2709850.0),

    # ── Herbs — use confirmed working fdc_id 2709786 (Garlic, raw) ───────────
    "thyme":                        ("Garlic, raw",                         2709786.0),
    "rosemary":                     ("Garlic, raw",                         2709786.0),
    "oregano":                      ("Garlic, raw",                         2709786.0),
    "bay leaf":                     ("Garlic, raw",                         2709786.0),
    "bay leaves":                   ("Garlic, raw",                         2709786.0),
    "lemongrass":                   ("Garlic, raw",                         2709786.0),

    # ── Other proteins ────────────────────────────────────────────────────────
    "lamb":                         ("Stew, lamb",                          2706660.0),
    "lamb chops":                   ("Stew, lamb",                          2706660.0),
    "lamb mince":                   ("Stew, lamb",                          2706660.0),
    "pork":                         ("Pork, roast",                         2705882.0),
    "pork chops":                   ("Pork, roast",                         2705882.0),
    "turkey":                       ("Turkey, back",                        2706131.0),
    "turkey breast":                ("Turkey, back",                        2706131.0),
    "sausage":                      ("Beef sausage",                        2706171.0),
    "sausages":                     ("Beef sausage",                        2706171.0),

    # ── Condiments ────────────────────────────────────────────────────────────
    "soy sauce":                    ("Soy sauce",                           2707442.0),
    "worcestershire sauce":         ("Worcestershire sauce",                2707447.0),
    "worcestershire":               ("Worcestershire sauce",                2707447.0),
    "vinegar":                      ("Apple cider",                         2709319.0),
    "apple cider vinegar":          ("Apple cider",                         2709319.0),
    "white vinegar":                ("Apple cider",                         2709319.0),
    "hot sauce":                    ("Hot pepper sauce",                    2709753.0),

    # ── Citrus ────────────────────────────────────────────────────────────────
    "lemon":                        ("Lemon juice, 100%, freshly squeezed", 2109239.0),
    "lime":                         ("Lime juice, 100%, freshly squeezed",  2709184.0),
    "lemon juice":                  ("Lemon juice, 100%, freshly squeezed", 2109239.0),
    "lime juice":                   ("Lime juice, 100%, freshly squeezed",  2709184.0),
    "orange":                       ("Orange, raw",                         2709171.0),
}


# ── Words that describe HOW an ingredient is prepared or its state ────────────
# Stripping these from the front of a phrase leaves the core ingredient name.
# "ripe diced tomatoes" → strip "ripe", strip "diced" → "tomatoes" → match!
# "mild chili powder"   → strip "mild"               → "chili powder" → match!
# "ground cumin"        → strip "ground"              → "cumin" → match!
# "fresh parsley"       → strip "fresh"               → "parsley" → match!
#
# Colour words are intentionally excluded: "red pepper" ≠ "pepper",
# "black beans" ≠ "beans".  Only truly neutral modifiers are listed.
_LEADING_MODIFIERS: frozenset[str] = frozenset({
    # Ripeness / age
    "ripe", "overripe", "unripe",
    # State
    "fresh", "dried", "dehydrated", "reconstituted",
    "canned", "tinned", "frozen", "thawed", "jarred",
    "raw", "cooked", "roasted", "toasted", "smoked", "charred",
    "boiled", "steamed", "fried",
    # Prep form
    "diced", "chopped", "sliced", "minced", "grated", "crushed",
    "ground", "mashed", "pureed", "blended", "shredded",
    "whole", "halved", "quartered", "cubed",
    # Size — only truly generic
    "baby", "mini",
    # Quality / heat — neutral ones
    "mild", "hot", "spicy", "extra", "plain",
    "organic", "mixed", "assorted",
})

# Trailing form/preparation words that refine HOW something is packaged but
# don't change WHAT the ingredient is.
# "black pepper powder"  → strip "powder"  → "black pepper" → match!
# "garlic flakes"        → strip "flakes"  → "garlic" → match!
# Only the LAST word is stripped (one pass), to avoid over-stripping.
# "tomato paste" already has an explicit entry so the strip is never reached.
_TRAILING_FORM_WORDS: frozenset[str] = frozenset({
    "powder", "flakes", "flake", "extract",
    "seeds", "seed", "leaves", "leaf",
})

# Words that cannot be further singularised (already base form or uncountable)
_UNCOUNTABLE: frozenset[str] = frozenset({
    "couscous", "molasses", "bass", "rice", "spinach",
    "garlic", "broth", "beef", "milk", "flour", "pasta",
})


def _singularize(token: str) -> str:
    """Return the singular form of a token. Simple rule-based."""
    if token in _UNCOUNTABLE:
        return token
    if token.endswith("ies") and len(token) > 4:   # berries → berry
        return token[:-3] + "y"
    if token.endswith("oes") and len(token) > 3:   # tomatoes → tomato
        return token[:-2]
    if token.endswith("ses") and len(token) > 4:   # processes → process
        return token[:-2]
    if token.endswith("s") and len(token) > 3:     # eggs → egg, beans → bean
        return token[:-1]
    return token


def _strip_leading_modifiers(phrase: str) -> str:
    """
    Strip leading modifier words one at a time until a non-modifier word
    is reached or the phrase is too short to strip further.

    "ripe diced tomatoes" → "tomatoes"
    "ground cumin"        → "cumin"
    "fresh parsley"       → "parsley"
    "mild chili powder"   → "chili powder"
    "red bell pepper"     → "red bell pepper" (unchanged — "red" not a modifier)
    """
    tokens = phrase.split()
    while len(tokens) > 1 and tokens[0] in _LEADING_MODIFIERS:
        tokens = tokens[1:]
    return " ".join(tokens)


class Matcher:
    """
    Matches cleaned ingredient names to USDA food entries.

    Matching pipeline (tried in order, first hit wins):
      1. MANUAL_MAPPINGS  — exact key lookup
      2. Singularise last token — "eggs" → "egg", "tomatoes" → "tomato"
      3. Token-sort          — "ground cumin" → "cumin ground"
      4. Strip leading modifiers — "ripe diced tomatoes" → "tomatoes"
      5. Fuzzy against MANUAL_MAPPINGS keys — catches near-misses
      6. Fuzzy against USDA food names — original behaviour
    """

    def __init__(self, df_reference: pd.DataFrame) -> None:
        matched = df_reference[df_reference["match_status"] == "matched"].copy()
        matched = matched[["matched_fdc_id", "matched_food_name"]].drop_duplicates().dropna()
        self._food_names: list[str] = matched["matched_food_name"].tolist()
        self._food_ids:   list[float] = matched["matched_fdc_id"].tolist()
        # Pre-build list of manual-mapping keys for fuzzy step 5
        self._manual_keys: list[str] = list(MANUAL_MAPPINGS.keys())

    def _lookup(self, key: str) -> tuple[str, float] | None:
        """Return (food_name, fdc_id) if key is in MANUAL_MAPPINGS, else None."""
        entry = MANUAL_MAPPINGS.get(key)
        return entry if entry else None

    def match(self, cleaned: str) -> tuple[str | None, float | None, str]:
        """
        Try to match a cleaned ingredient name.

        Returns
        -------
        (food_name, fdc_id, match_type)
          match_type: 'manual_match' | 'fuzzy_NN%' | 'no_match'
        """
        key = cleaned.lower().strip()

        # ── 1. Exact manual match ─────────────────────────────────────────────
        hit = self._lookup(key)
        if hit:
            return hit[0], hit[1], "manual_match"

        # ── 2. Singularise last token ─────────────────────────────────────────
        # "eggs" → "egg",  "tomatoes" → "tomato",  "chicken thighs" → "chicken thigh"
        tokens = key.split()
        if tokens:
            singular_key = " ".join(tokens[:-1] + [_singularize(tokens[-1])])
            if singular_key != key:
                hit = self._lookup(singular_key)
                if hit:
                    return hit[0], hit[1], "manual_match"

        # ── 3. Token-sort ─────────────────────────────────────────────────────
        # "ground cumin" → "cumin ground" (matches existing entry)
        sorted_key = " ".join(sorted(key.split()))
        if sorted_key != key:
            hit = self._lookup(sorted_key)
            if hit:
                return hit[0], hit[1], "manual_match"

        # ── 4. Strip leading modifiers then retry 1-3 ─────────────────────────
        # "ripe diced tomatoes" → "tomatoes"
        # "mild chili powder"   → "chili powder"
        stripped = _strip_leading_modifiers(key)
        if stripped != key:
            for candidate in (
                stripped,
                " ".join(_singularize(t) for t in stripped.split()),
                " ".join(sorted(stripped.split())),
            ):
                hit = self._lookup(candidate)
                if hit:
                    return hit[0], hit[1], "manual_match"

        # ── 5. Strip trailing form word then retry 1–4 ───────────────────────
        # "black pepper powder" → strip "powder" → "black pepper" → match!
        # "garlic flakes"       → strip "flakes" → "garlic" → match!
        w = key.split()
        if len(w) > 1 and w[-1] in _TRAILING_FORM_WORDS:
            shorter = " ".join(w[:-1])
            for candidate in (
                shorter,
                " ".join(_singularize(t) for t in shorter.split()),
                " ".join(sorted(shorter.split())),
                _strip_leading_modifiers(shorter),
            ):
                hit = self._lookup(candidate)
                if hit:
                    return hit[0], hit[1], "manual_match"

        # ── 6. Fuzzy match against MANUAL_MAPPINGS keys ───────────────────────
        # MANUAL_MAPPINGS keys are natural-language ingredient names, so fuzzy
        # matching against them is more semantically meaningful than matching
        # against USDA food descriptions (step 7).
        # token_sort_ratio handles word-order differences automatically.
        result = process.extractOne(key, self._manual_keys, scorer=fuzz.token_sort_ratio)
        if result and result[1] >= 78:   # slightly higher bar to avoid false positives
            food_name, fdc_id = MANUAL_MAPPINGS[result[0]]
            return food_name, fdc_id, f"fuzzy_{int(result[1])}%"

        # ── 7. Fuzzy match against USDA food names (original behaviour) ───────
        if self._food_names:
            result = process.extractOne(
                cleaned,
                self._food_names,
                scorer=fuzz.token_sort_ratio,
            )
            if result and result[1] >= FUZZY_THRESHOLD:
                idx   = self._food_names.index(result[0])
                score = int(result[1])
                return result[0], self._food_ids[idx], f"fuzzy_{score}%"

        return None, None, "no_match"
