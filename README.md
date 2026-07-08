# African Recipes — Nutritional Risk Analyser & Explorer

A full end-to-end data science project that collects African recipes from multiple sources,
maps their ingredients to USDA and West African nutritional databases, calculates per-serving
nutrition, scores each recipe for nutritional risk against WHO dietary guidelines, trains ML
classifiers to identify risk drivers, and presents everything in an interactive Streamlit dashboard.

**Live app:** [olwakhe-nutrition-risk.streamlit.app](https://olwakhe-nutrition-risk.streamlit.app/)

---

## Key Results

| Metric | Value |
|---|---|
| Recipes in dataset | 1 188 |
| Recipes successfully scored | 1 179 (99.2 %) |
| Insufficient data (unscored) | 9 |
| Average weighted risk score | ~22 / 100 |
| High or Very High risk recipes | ~132 (11 %) |

**Risk distribution (weighted score method)**

| Risk Level | Score range | Recipes |
|---|---|---|
| Low | 0–25 | 879 |
| Medium | 25–50 | 168 |
| High | 50–75 | 100 |
| Very High | 75–100 | 32 |

**Key findings:**

- **Energy density is the strongest driver of High risk** — ahead of sodium. This was confirmed independently by both ML models (Logistic Regression and Random Forest).
- **Sodium and fat are nearly equal drivers of Very High risk.** The 30 % sodium weighting in the rule-based scorer is validated at the extreme end of the scale.
- **Carbohydrates are the weakest risk predictor** despite being the dietary staple of African cuisine. Risk comes from what accompanies the carbohydrate base (fats, salt, sugar), not the staple itself.
- **74 % of recipes score Low risk** — traditional African cooking is not inherently high-risk. High-risk recipes cluster around specific preparation patterns: deep-frying, heavy bouillon cube usage, and large portions of red meat.

---

## Project Overview

African cuisines are under-represented in global nutritional databases, making it difficult
to assess the dietary risk associated with traditional meal patterns.
This project addresses that gap by:

1. Assembling a dataset of **1 188 African recipes** spanning West, East, North, Southern, and
   Central African cuisines — scraped from four websites and supplemented with a curated collection.
2. Mapping every ingredient through a **three-layer matching pipeline**:
   - Layer 1: Curated African proxy mappings + 7-stage fuzzy matching
   - Layer 2: Full USDA FoodData Central search (5 432 foods)
   - Layer 3: FAO/INFOODS West African Food Composition Table — WAFCT 2019 (1 028 foods)
3. Computing **per-serving nutritional values** (energy, protein, fat, carbohydrates, sugars, sodium).
4. Scoring each recipe for **nutritional risk** using two complementary methods:
   - *Flag count* — counts nutrients in the "high-risk" zone.
   - *Weighted score* — a 0–100 composite with sodium weighted at 30 % to reflect the
     high hypertension burden in African populations.
5. Presenting everything in an **interactive Streamlit dashboard** with two modes:
   - *Dataset Explorer* — browse, filter, and inspect all 1 188 recipes.
   - *Analyse a Recipe* — paste any ingredient list and get instant nutrition + risk scores
     including an FDA-style Nutrition Facts label.
6. Training **ML risk classifiers** (Logistic Regression and Random Forest) to identify which
   nutritional features drive risk across African recipes.

---

## Data Sources

| Source | Recipes | Method |
|---|---|---|
| African recipe books & curated collection | ~175 | Pre-compiled CSV |
| [AllRecipes.com](https://www.allrecipes.com) — African cuisine section | 59 | Web scraping (BeautifulSoup) |
| [Chef Lola's Kitchen](https://cheflolaskitchen.com) | 44 | Web scraping (WPRM plugin selectors) |
| [AfricanBites.com](https://www.africanbites.com) | ~126 | Web scraping (WPRM plugin selectors) |
| [Food.com](https://www.food.com) — African recipes | ~784 | Web scraping (JSON-LD structured data) |
| **Total** | **1 188** | |

**Nutritional reference databases:**
- **USDA FoodData Central** — FNDDS 2022 survey foods (5 432 food items)
- **FAO/INFOODS WAFCT 2019** — West African Food Composition Table (1 028 African foods)
  covering fufu, pounded yam, fonio, egusi, dawadawa, cocoyam, African leafy vegetables, and more.

**Risk scoring reference:** WHO dietary guidelines expressed per serving,
assuming one meal ≈ ⅓ of the 2 000 kcal/day adult requirement.

---

## Repository Structure

```
Nutrition_risk_african_recipes/
├── README.md
├── requirements.txt
├── .gitignore
│
└── african_recipes_nutrition/
    │
    ├── dashboard.py                  ← Streamlit app entry point (2 tabs)
    ├── config.py                     ← Database connection config
    │
    ├── data/
    │   ├── raw/                      ← Read-only source data
    │   │   ├── merged_recipes_updated.csv     Original curated recipes
    │   │   ├── food.csv                       USDA food descriptions (5 432 foods)
    │   │   ├── food_nutrient.csv              USDA nutrient values per food
    │   │   ├── nutrient.csv                   USDA nutrient definitions
    │   │   ├── ingredient_mapping_original.csv Initial ingredient-USDA pairs
    │   │   ├── WAFCT_2019.xlsx                FAO/INFOODS West African food composition table
    │   │   └── wafct_foods.csv               Parsed WAFCT data (1 028 foods, 5 nutrients)
    │   │
    │   ├── interim/                  ← Pipeline-generated working files
    │   │   ├── recipes_clean.csv              Recipe metadata + servings
    │   │   ├── ingredients_master.csv         Deduplicated ingredient list
    │   │   ├── recipe_ingredient_final.csv    Recipe ↔ ingredient links + gram weights
    │   │   ├── ingredient_mapping_final.csv   Ingredient → USDA FDC ID mapping
    │   │   └── ingredient_measures.csv        Extracted gram weights per ingredient line
    │   │
    │   ├── scraped/                  ← Web-scraped recipe datasets
    │   │   ├── african_recipes_dataset.csv    AllRecipes.com recipes
    │   │   ├── cheflola_scraped.csv           Chef Lola's Kitchen recipes
    │   │   ├── africanbites_scraped.csv       AfricanBites.com recipes
    │   │   ├── food_com_scraped.csv           Food.com African recipes
    │   │   └── rescraped_insufficient.csv     Re-scraped formerly-unscored recipes
    │   │
    │   └── outputs/                  ← Final analysis results
    │       ├── recipe_nutrition.csv                    Per-serving nutrition (1 188 recipes)
    │       ├── recipe_risk_scores.csv                  Risk scores + flags (1 188 recipes)
    │       └── insufficient_data_recipes_inspection.csv Inspection file for unscored recipes
    │
    ├── pipeline/                     ← Numbered build scripts + utilities
    │   ├── 01_extract_measures.py    Extract gram weights from ingredient text
    │   ├── 02_fix_ingredient_mapping.py  Apply proxy + bad-match corrections
    │   ├── 03_integrate_scraped.py   Add AllRecipes recipes to pipeline
    │   ├── 04_integrate_cheflola.py  Add Chef Lola recipes to pipeline
    │   ├── 05_fix_scraped_mapping.py Fix unmatched AllRecipes ingredients
    │   ├── 06_fix_cheflola_mapping.py Fix unmatched Chef Lola ingredients
    │   ├── 07_rematch_unmatched.py   Final fuzzy-match pass vs full USDA DB
    │   ├── 08_calculate_nutrition.py Compute per-serving nutrition for all recipes
    │   ├── 09_integrate_africanbites.py  Add AfricanBites recipes to pipeline
    │   ├── 10_integrate_food_com.py  Add Food.com recipes to pipeline
    │   ├── 11_deduplicate_recipes.py Remove duplicate recipes across sources
    │   ├── add_recipe.py             Add a single new recipe to the database
    │   ├── live_analysis.py          Live ingredient matching + nutrition engine (3-layer)
    │   ├── parse_wafct.py            Parse WAFCT 2019 Excel → wafct_foods.csv
    │   ├── reanalyse_rescraped.py    Re-analyse rescued recipes with WAFCT layer active
    │   ├── train_risk_classifier.py  Phase 3 — Logistic Regression risk classifier
    │   └── train_random_forest.py    Phase 3 — Random Forest risk classifier
    │
    ├── models/                       ← Trained ML model artifacts
    │   ├── logistic_regression.pkl         Trained Logistic Regression model
    │   ├── feature_scaler.pkl              StandardScaler (required with LR model)
    │   ├── logistic_regression_report.txt  LR evaluation results + coefficients
    │   ├── random_forest.pkl               Trained Random Forest model (best params)
    │   └── random_forest_report.txt        RF evaluation results + feature importance
    │
    ├── scripts/                      ← Reusable library modules
    │   ├── cleaner.py                Ingredient name cleaning + African proxy table
    │   ├── matcher.py                Multi-layer USDA matching (7-stage pipeline)
    │   └── loader.py                 DB loader
    │
    ├── scrapers/                     ← Web scraping scripts
    │   ├── scrape_cheflola.py        Scraper for cheflolaskitchen.com (WPRM)
    │   ├── scrape_africanbites.py    Scraper for africanbites.com (WPRM)
    │   ├── scrape_food_com.py        Scraper for food.com (JSON-LD)
    │   ├── rescrape_insufficient.py  Targeted re-scraper for unscored recipes
    │   └── collect_urls.py           URL collection helpers
    │
    ├── scoring/
    │   └── score_nutrition_risk.py   WHO-based nutritional risk scorer
    │
    └── notebooks/                    ← Exploratory analysis
        ├── 01_cleaning_tables.ipynb
        ├── 02_recipe_web_scraping.ipynb
        ├── 03_missing_recipes_scraper.ipynb
        └── 04_pdf_recipe_scrapping.ipynb
```

---

## Ingredient Matching Pipeline

The three-layer matching pipeline achieves **~99 % recipe coverage** across 1 188 recipes.

### Layer 1 — Curated mappings + fuzzy matching (`scripts/matcher.py`)

A 7-stage strategy handles the wide variety of ingredient name formats:

| Stage | Strategy | Example |
|---|---|---|
| 1 | Exact key lookup in MANUAL_MAPPINGS | `"palm oil"` → Palm oil |
| 2 | Singularise last token | `"eggs"` → `"egg"` → match |
| 3 | Token-sort (word order) | `"ground cumin"` → `"cumin ground"` → match |
| 4 | Strip leading modifiers | `"ripe diced tomatoes"` → `"tomatoes"` → match |
| 5 | Strip trailing form words | `"black pepper powder"` → `"black pepper"` → match |
| 6 | Fuzzy against MANUAL_MAPPINGS keys | near-miss catch |
| 7 | Fuzzy against USDA food names | original fallback |

### Layer 2 — USDA full search (`USDAFoodIndex`)

Searches all 5 432 foods in `food.csv` automatically using an inverted word index + fuzzy
scoring with a compound-dish penalty. Finds any ingredient in the USDA database without
needing it pre-mapped in MANUAL_MAPPINGS.

### Layer 3 — West African Food Composition Table (`WAFCTFoodIndex`)

When USDA has no match, searches the **FAO/INFOODS WAFCT 2019** (1 028 West African foods).
Covers ingredients absent from USDA: fufu, pounded yam, cocoyam, fonio, plantain flour,
dawadawa, African leafy vegetables, and regional staples.

Uses `partial_ratio` scoring (better than `token_sort_ratio` for WAFCT's verbose food names)
and falls back to the original ingredient name when the cleaner has proxy-substituted it
(e.g. fonio → millet).

**Note:** WAFCT does not include total sugars data. Sugars are set to 0 for WAFCT-matched
ingredients — an honest limitation noted in the dashboard.

---

## Nutritional Risk Scoring

Scoring is done by `scoring/score_nutrition_risk.py` against WHO dietary guidelines,
expressed per serving (⅓ of daily intake).

### Per-serving thresholds

| Nutrient | Medium risk | High risk |
|---|---|---|
| Energy | > 500 kcal | > 800 kcal |
| Sodium | > 400 mg | > 700 mg |
| Fat | > 15 g | > 25 g |
| Sugars | > 12 g | > 20 g |
| Protein *(inverted)* | < 15 g | < 8 g |

### Method 1 — Flag count
Each nutrient is independently classified Low / Medium / High.
**0 flags → Low · 1–2 flags → Medium · 3+ flags → High**

### Method 2 — Weighted score (0–100)

| Nutrient | Weight | Rationale |
|---|---|---|
| Sodium | 30 % | Leading NCD risk in sub-Saharan Africa |
| Energy | 25 % | Obesity and overweight |
| Fat | 20 % | Cardiovascular disease |
| Sugars | 15 % | Diabetes and metabolic syndrome |
| Protein *(deficiency)* | 10 % | Malnutrition risk |

Thresholds: **< 25 Low · 25–50 Medium · 50–75 High · 75–100 Very High**

---

## ML Risk Classifiers (Phase 3)

Two classifiers were trained on the 1 179 scored recipes to identify which nutritional
features drive risk in African cuisine.

### Logistic Regression baseline (`pipeline/train_risk_classifier.py`)

| Setting | Value |
|---|---|
| Classes | Low / Medium / High / Very High (4 classes) |
| Features | 7 nutritional features, StandardScaler applied |
| class_weight | balanced |
| Primary metric | Macro-F1 (averages F1 equally across all classes) |
| **Macro-F1** | **0.797** |

Coefficients are directly interpretable: a large positive value means that feature
strongly pushes the prediction towards that risk class.

### Random Forest (`pipeline/train_random_forest.py`)

| Setting | Value |
|---|---|
| Classes | Low / Medium / Elevated (High + Very High merged — 132 examples) |
| Features | 7 nutritional features, no scaling needed |
| class_weight | balanced |
| Tuning | RandomizedSearchCV (30 combinations × 5-fold CV, scoring=f1_macro) |
| **Macro-F1** | **0.854** |

High and Very High were merged into "Elevated" because 32 Very High examples alone
is too few to train a reliable separate class.

### Cross-model feature importance findings

Both models independently rank the same top three features in the same order:

| Rank | Feature | RF importance | LR coef (High) |
|---|---|---|---|
| 1 | energy_kcal | 0.372 | +1.726 |
| 2 | sodium_mg | 0.204 | +1.538 |
| 3 | fat_g | 0.193 | +1.318 |

Agreement across two completely different algorithms validates the finding:
**energy density, not sodium, is the primary driver of High risk in African recipes.**
Sodium and fat are nearly equal drivers at the Very High level.

Saved model artifacts are in `models/`. Human-readable result reports are saved alongside
each model as `*_report.txt`.

---

## Dashboard Features

### Tab 1 — Dataset Explorer
- **KPI cards** — total recipes, scored count, average weighted score, high-risk count.
- **Risk distribution** — donut charts for flag-count and weighted-score levels; histogram with threshold lines.
- **Per-nutrient breakdown** — stacked bar showing Low / Medium / High counts per nutrient.
- **Energy vs Sodium scatter** — interactive bubble chart (size = fat); hover for full details.
- **Top 10 charts** — highest weighted score, sodium, and calories.
- **Flag co-occurrence heatmap** — which risk flags tend to appear together.
- **Recipe explorer** — searchable, filterable table with radar chart and risk gauge per recipe.

### Tab 2 — Analyse a Recipe
- Paste any ingredient list with quantities (one ingredient per line).
- Ingredients matched through the 3-layer pipeline (MANUAL_MAPPINGS → USDA → WAFCT).
- Returns per-serving nutrition totals, a weighted risk score, a radar chart, and an
  **FDA-style Nutrition Facts label** with traffic-light risk indicators (green / amber / red).
- Per-ingredient breakdown table shows which database each ingredient was matched to
  (`manual_match`, `usda_search`, or `wafct`).
- Coverage indicator warns when fewer than 30 % of ingredients matched.

---

## Setup & Running

The dashboard is deployed live on Streamlit Community Cloud at
**[olwakhe-nutrition-risk.streamlit.app](https://olwakhe-nutrition-risk.streamlit.app/)** —
no installation needed to explore it. To run it locally instead:

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the dashboard
```bash
cd african_recipes_nutrition
py -m streamlit run dashboard.py
```
Opens at **http://localhost:8501**

### 3. Analyse a new recipe (live)
Open the dashboard → click **Analyse a Recipe** tab → paste an ingredient list with quantities
(one per line) → set servings → click **Analyse ▶**.

### 4. Add an analysed recipe to the database
Edit the `RECIPE` dict in `pipeline/add_recipe.py`, then run:
```bash
py pipeline/add_recipe.py
```
The script auto-assigns the next recipe ID and appends to all three database CSVs.

### 5. Re-train ML models
```bash
py pipeline/train_risk_classifier.py   # Logistic Regression
py pipeline/train_random_forest.py     # Random Forest
```
Results and model files are saved to `models/`.

### 6. Run the full batch pipeline (from scratch)
```bash
cd african_recipes_nutrition
py pipeline/01_extract_measures.py
py pipeline/02_fix_ingredient_mapping.py
py pipeline/03_integrate_scraped.py
py pipeline/04_integrate_cheflola.py
py pipeline/05_fix_scraped_mapping.py
py pipeline/06_fix_cheflola_mapping.py
py pipeline/07_rematch_unmatched.py
py pipeline/08_calculate_nutrition.py
py pipeline/09_integrate_africanbites.py
py pipeline/10_integrate_food_com.py
py pipeline/11_deduplicate_recipes.py
py scoring/score_nutrition_risk.py
```

---

## Tech Stack

| Category | Libraries / Tools |
|---|---|
| Data wrangling | pandas, numpy, csv |
| Ingredient matching | RapidFuzz (fuzzy string matching) |
| Web scraping | requests, BeautifulSoup4 |
| Excel parsing | openpyxl |
| ML models | scikit-learn |
| Model serialisation | joblib |
| Visualisation | Plotly, Streamlit |
| Nutritional reference (global) | USDA FoodData Central — FNDDS 2022 |
| Nutritional reference (African) | FAO/INFOODS WAFCT 2019 |

Python 3.12 · Windows 10

---

## Limitations

- **WAFCT sugars gap:** The West African Food Composition Table does not include total sugars.
  Sugars are set to 0 for WAFCT-matched ingredients, so sugar risk is underestimated for
  African staple ingredients.
- **Cooking method not modelled:** Boiling reduces sodium and fat; deep-frying adds fat.
  The pipeline calculates nutrition from raw ingredient weights and does not adjust for
  preparation method.
- **Gram weight estimation:** Ingredients without explicit gram weights use volume-to-gram
  estimates (e.g. 1 cup = 240 g). Unusual units fall back to a default item weight.
- **9 unresolved recipes:** Three Zimbo Kitchen recipes (no JSON-LD/WPRM — unscrapable),
  one roundup page, one recipe with no URL, and four with ingredient names absent from
  both USDA and WAFCT.

---

## Data Attribution

- **USDA FoodData Central** (fdc.nal.usda.gov) — FoodData Central, 2022.
  Food and Nutrient Database for Dietary Studies (FNDDS).
- **FAO/INFOODS** — West African Food Composition Table (WAFCT 2019).
  Vincent A. et al. FAO, Rome, 2019.
- **AllRecipes.com**, **Chef Lola's Kitchen**, **AfricanBites.com**, **Food.com** —
  recipe data scraped for research and educational use only.
