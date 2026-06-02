"""
add_recipe.py
=============
Add a single recipe to the project database.

HOW IT WORKS
─────────────
1. You define the recipe at the bottom of this file (RECIPE dict).
2. The script runs the live analyser on the ingredient list.
3. It appends one row to each of the three CSV files the dashboard reads:
     data/interim/recipes_clean.csv      — recipe name, cuisine, servings
     data/outputs/recipe_nutrition.csv   — calculated per-serving nutrition
     data/outputs/recipe_risk_scores.csv — risk scores (what the dashboard shows)
4. It auto-assigns the next available recipe_id so there are no conflicts.

TO ADD A NEW RECIPE
───────────────────
Edit the RECIPE dict at the bottom:
  - name       : recipe name in CAPS (matches the style of existing recipes)
  - cuisine    : optional — e.g. "North Africa", "West Africa", "East Africa"
  - servings   : integer — how many servings the recipe makes
  - url        : optional source URL
  - ingredients: list of strings, one per line with quantities

Then run:
    py pipeline/add_recipe.py

To undo an accidental add, open recipe_risk_scores.csv and delete the last row,
then do the same in recipes_clean.csv and recipe_nutrition.csv.
"""

import csv
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from pipeline.live_analysis import LiveAnalyser

# ── File paths ─────────────────────────────────────────────────────────────────
RECIPES_FILE   = os.path.join(BASE, "data", "interim",  "recipes_clean.csv")
NUTRITION_FILE = os.path.join(BASE, "data", "outputs",  "recipe_nutrition.csv")
SCORES_FILE    = os.path.join(BASE, "data", "outputs",  "recipe_risk_scores.csv")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_next_id(filepath: str) -> int:
    """Read the highest recipe_id in the file and return the next integer."""
    with open(filepath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 1
    return max(int(r["recipe_id"]) for r in rows) + 1


def append_row(filepath: str, fieldnames: list, row: dict) -> None:
    """Append one row to a CSV file without rewriting the whole file."""
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(row)


# ── Main ──────────────────────────────────────────────────────────────────────

def add_recipe(recipe: dict) -> None:
    """
    Analyse a recipe and persist it to the three database CSV files.

    Parameters
    ----------
    recipe : dict with keys
        name        str   — recipe name
        cuisine     str   — region (optional, can be empty)
        servings    int   — number of servings
        url         str   — source URL (optional, can be empty)
        ingredients list  — ingredient lines with quantities
    """
    print(f"\nAdding recipe: {recipe['name']}")
    print("=" * 50)

    # ── Step 1: Determine the next recipe_id ──────────────────────────────────
    new_id = get_next_id(SCORES_FILE)
    print(f"  Assigned recipe_id = {new_id}")

    # ── Step 2: Run the live analyser ─────────────────────────────────────────
    print("  Running nutrition analysis...")
    analyser = LiveAnalyser()
    result   = analyser.analyse(recipe["ingredients"], servings=recipe["servings"])

    nutrition = result["nutrition"]
    risk      = result["risk"]
    n_matched = sum(1 for i in result["ingredients"] if i["status"] == "matched")
    n_total   = len(result["ingredients"])

    print(f"  Coverage  : {result['coverage']}%  ({n_matched}/{n_total} ingredients matched)")
    print(f"  Energy    : {nutrition['energy_kcal']} kcal/serving")
    print(f"  Risk      : {risk['weighted_risk_level']} (score {risk['weighted_risk_score']})")

    if result["coverage"] < 30:
        print("  WARNING: coverage below 30% — nutrition totals may be unreliable.")

    # ── Step 3: Append to recipes_clean.csv ──────────────────────────────────
    append_row(
        RECIPES_FILE,
        fieldnames=["recipe_id", "recipe_name", "cuisine", "servings_raw", "recipe_url", "instructions"],
        row={
            "recipe_id":    new_id,
            "recipe_name":  recipe["name"].upper(),
            "cuisine":      recipe.get("cuisine", ""),
            "servings_raw": f"MAKES {recipe['servings']} SERVINGS",
            "recipe_url":   recipe.get("url", ""),
            "instructions": "",
        },
    )
    print("  OK  recipes_clean.csv")

    # ── Step 4: Append to recipe_nutrition.csv ────────────────────────────────
    append_row(
        NUTRITION_FILE,
        fieldnames=[
            "recipe_id", "servings", "ingredients_total", "ingredients_used",
            "energy_kcal", "protein_g", "fat_g", "carbohydrate_g", "sugars_g", "sodium_mg",
        ],
        row={
            "recipe_id":         new_id,
            "servings":          recipe["servings"],
            "ingredients_total": n_total,
            "ingredients_used":  n_matched,
            "energy_kcal":       nutrition["energy_kcal"],
            "protein_g":         nutrition["protein_g"],
            "fat_g":             nutrition["fat_g"],
            "carbohydrate_g":    nutrition["carbohydrate_g"],
            "sugars_g":          nutrition["sugars_g"],
            "sodium_mg":         nutrition["sodium_mg"],
        },
    )
    print("  OK  recipe_nutrition.csv")

    # ── Step 5: Append to recipe_risk_scores.csv ──────────────────────────────
    append_row(
        SCORES_FILE,
        fieldnames=[
            "recipe_id", "recipe_name", "servings",
            "energy_kcal", "protein_g", "fat_g", "carbohydrate_g", "sugars_g", "sodium_mg",
            "ingredient_coverage_pct",
            "energy_risk", "sodium_risk", "fat_risk", "sugar_risk", "protein_risk",
            "flag_count", "flag_risk_level",
            "weighted_risk_score", "weighted_risk_level",
            "data_status",
        ],
        row={
            "recipe_id":               new_id,
            "recipe_name":             recipe["name"].upper(),
            "servings":                recipe["servings"],
            "energy_kcal":             nutrition["energy_kcal"],
            "protein_g":               nutrition["protein_g"],
            "fat_g":                   nutrition["fat_g"],
            "carbohydrate_g":          nutrition["carbohydrate_g"],
            "sugars_g":                nutrition["sugars_g"],
            "sodium_mg":               nutrition["sodium_mg"],
            "ingredient_coverage_pct": result["coverage"],
            "energy_risk":             risk["energy_risk"],
            "sodium_risk":             risk["sodium_risk"],
            "fat_risk":                risk["fat_risk"],
            "sugar_risk":              risk["sugar_risk"],
            "protein_risk":            risk["protein_risk"],
            "flag_count":              risk["flag_count"],
            "flag_risk_level":         risk["flag_risk_level"],
            "weighted_risk_score":     risk["weighted_risk_score"],
            "weighted_risk_level":     risk["weighted_risk_level"],
            "data_status":             "calculated",
        },
    )
    print("  OK  recipe_risk_scores.csv")

    print(f"\n  Done: '{recipe['name']}' saved as ID {new_id}.")
    print("  Restart the dashboard to see it in the Dataset Explorer.")


# ── Recipe to add ─────────────────────────────────────────────────────────────
# Edit this dict to add any recipe. Then run:  py pipeline/add_recipe.py

RECIPE = {
    "name":     "SHAKSHUKA",
    "cuisine":  "North Africa",
    "servings": 4,
    "url":      "",
    "ingredients": [
        "1 tablespoon olive oil",
        "1/2 onion, peeled and diced",
        "1 clove garlic, minced",
        "1 red bell pepper, seeded and chopped",
        "4 cups ripe diced tomatoes",
        "2 tablespoons tomato paste",
        "1 teaspoon mild chili powder",
        "1 teaspoon ground cumin",
        "1 teaspoon paprika",
        "Pinch of cayenne pepper",
        "6 large eggs",
        "1/2 tablespoon fresh parsley",
    ],
}


if __name__ == "__main__":
    add_recipe(RECIPE)
