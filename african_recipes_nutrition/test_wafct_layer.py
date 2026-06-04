"""
Quick test — run the LiveAnalyser on the previously unmatched African staples
to verify the WAFCT Layer 3 is working correctly.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.live_analysis import LiveAnalyser

TEST_RECIPES = [
    ("Pounded Yam",         ["500g pounded yam"],                    4),
    ("Plantain Flour",      ["2 cups plantain flour"],               4),
    ("Ugali (Corn Fufu)",   ["2 cups maize flour", "3 cups water"],  4),
    ("Egusi Pudding",       ["200g egusi seeds", "1 onion", "2 tbsp palm oil"], 4),
    ("Fufu",                ["500g cassava fufu"],                   4),
    ("Fonio Porridge",      ["1 cup fonio", "2 cups water", "1 tsp salt"], 2),
    ("Achu Soup test",      ["200g cocoyam", "1 tbsp palm oil", "1 tsp limestone"], 4),
]

print("Loading LiveAnalyser (USDA + WAFCT)...")
analyser = LiveAnalyser()
print("Ready.\n")

for recipe_name, lines, servings in TEST_RECIPES:
    result = analyser.analyse(lines, servings)
    print(f"=== {recipe_name} ===")
    for ing in result["ingredients"]:
        status = ing["status"]
        match  = ing["match_type"] or "—"
        food   = (ing["food_name"] or "no match")[:45]
        print(f"  [{match:<12}] {ing['raw'][:35]:<35} → {food}  ({status})")
    n = result["nutrition"]
    print(f"  Coverage: {result['coverage']:.0f}%  |  "
          f"kcal={n['energy_kcal']:.0f}  protein={n['protein_g']:.1f}g  "
          f"fat={n['fat_g']:.1f}g  sodium={n['sodium_mg']:.0f}mg")
    print()
