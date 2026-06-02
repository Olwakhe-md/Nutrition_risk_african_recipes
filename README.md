# Nutritional Risk Analysis of African Recipes

A full end-to-end data science project that collects African recipes from multiple sources,
maps their ingredients to USDA nutritional data, calculates per-serving nutrition, scores
each recipe for nutritional risk against WHO dietary guidelines, and provides a live recipe
analyser — all presented in an interactive Streamlit dashboard.

---

## Key Results

| Metric | Value |
|---|---|
| Recipes in dataset | 1 188 |
| Recipes successfully scored | 1 133 (95 %) |
| Insufficient data (unscored) | 55 |
| Average weighted risk score | ~22 / 100 |
| High or Very High risk recipes | ~122 (11 %) |

**Risk distribution (weighted score method)**

| Risk Level | Recipes |
|---|---|
| Low (0–25) | ~853 |
| Medium (25–50) | ~158 |
| High (50–75) | ~95 |
| Very High (75–100) | ~27 |

**Key finding:** Sodium is the dominant risk driver. Many traditional stews and one-pot dishes
exceed the per-serving sodium threshold (700 mg) largely due to bouillon cube usage.
High-calorie, high-fat dishes cluster around West and Central African peanut-based recipes.

---

## Project Overview

African cuisines are under-represented in global nutritional databases, making it difficult
to assess the dietary risk associated with traditional meal patterns.
This project addresses that gap by:

1. Assembling a dataset of **1 188 African recipes** spanning West, East, North, Southern, and
   Central African cuisines — scraped from four websites and supplemented with a curated collection.
2. Mapping every ingredient to the **USDA FoodData Central** database using a multi-stage
   matching pipeline (African proxy table → manual mappings → fuzzy matching → full USDA search).
3. Computing **per-serving nutritional values** (energy, protein, fat, carbohydrates, sugars, sodium).
4. Scoring each recipe for **nutritional risk** using two complementary methods:
   - *Flag count* — counts nutrients in the "high-risk" zone.
   - *Weighted score* — a 0–100 composite with sodium weighted at 30 % to reflect the
     high hypertension burden in African populations.
5. Presenting everything in an **interactive Streamlit dashboard** with two modes:
   - *Dataset Explorer* — browse, filter, and inspect all 1 188 recipes.
   - *Analyse a Recipe* — paste any ingredient list and get instant nutrition + risk scores.

---

## Data Sources

| Source | Recipes | Method |
|---|---|---|
| African recipe books & curated collection | ~175 | Pre-compiled CSV |
| [AllRecipes.com](https://www.allrecipes.com) — African cuisine section | 59 | Web scraping (BeautifulSoup) |
| [Chef Lola's Kitchen](https://cheflolaskitchen.com) | 44 | Web scraping (WPRM plugin selectors) |
| [AfricanBites.com](https://www.africanbites.com) | ~126 | Web scraping (JSON-LD structured data) |
| [Food.com](https://www.food.com) — African recipes | ~784 | Web scraping (JSON-LD structured data) |
| **Total** | **1 188** | |

**Nutritional reference:** USDA FoodData Central — FNDDS 2022 survey foods
(5 432 food items, 6 key nutrients tracked).

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
    │   │   └── ingredient_mapping_original.csv Initial ingredient-USDA pairs
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
    │   │   └── food_com_scraped.csv           Food.com African recipes
    │   │
    │   └── outputs/                  ← Final analysis results
    │       ├── recipe_nutrition.csv           Per-serving nutrition (1 188 recipes)
    │       └── recipe_risk_scores.csv         Risk scores + flags (1 188 recipes)
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
    │   └── live_analysis.py          Live ingredient matching + nutrition engine
    │
    ├── scripts/                      ← Reusable library modules
    │   ├── cleaner.py                Ingredient name cleaning + African proxy table
    │   ├── matcher.py                Multi-layer USDA matching (7-stage pipeline)
    │   └── loader.py                 DB loader
    │
    ├── scrapers/                     ← Web scraping scripts
    │   ├── scrape_cheflola.py        Scraper for cheflolaskitchen.com
    │   ├── scrape_africanbites.py    Scraper for africanbites.com (JSON-LD)
    │   ├── scrape_food_com.py        Scraper for food.com (JSON-LD)
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

## Pipeline Walkthrough

The batch pipeline runs in 11 numbered steps, each building on the previous.

### Steps 1–8 — Core pipeline (original 278 recipes)

**Step 1** (`01_extract_measures.py`) — Parses raw ingredient lines into gram weights using a
5-priority hierarchy: bracketed metrics → leading metrics → pounds → volume units → count estimates.

**Step 2** (`02_fix_ingredient_mapping.py`) — Applies hand-curated corrections: assigns USDA FDC IDs
to African proxy ingredients (bondwe → amaranth, garri → cassava flour, samp → hominy corn) and
corrects known bad fuzzy matches.

**Steps 3 & 4** — Integrate AllRecipes (59 recipes) and Chef Lola's Kitchen (44 recipes) with full
ingredient lists.

**Steps 5 & 6** — Resolve unmatched ingredients from scraped recipes via proxy map, direct map,
and keyword rules.

**Step 7** (`07_rematch_unmatched.py`) — Final fuzzy-match pass against the full 5 432-entry USDA
food.csv at 65 % similarity threshold.

**Step 8** (`08_calculate_nutrition.py`) — Calculates per-serving nutrition:
```
nutrient_per_serving = (gram_weight_per_serving / 100) × USDA_nutrient_per_100g
```

### Steps 9–11 — Dataset expansion (AfricanBites + Food.com)

**Step 9** (`09_integrate_africanbites.py`) — Integrates ~126 AfricanBites.com recipes scraped
using JSON-LD structured data.

**Step 10** (`10_integrate_food_com.py`) — Integrates ~784 Food.com African recipes scraped using
JSON-LD structured data, bringing the total to over 1 000 recipes.

**Step 11** (`11_deduplicate_recipes.py`) — Removes duplicate recipes identified across sources
using fuzzy name matching.

---

## Ingredient Matching Pipeline

The `scripts/matcher.py` module uses a **7-layer matching strategy** to handle the wide variety
of ingredient name formats users type:

| Layer | Strategy | Example |
|---|---|---|
| 1 | Exact key lookup in MANUAL_MAPPINGS | `"palm oil"` → Palm oil |
| 2 | Singularise last token | `"eggs"` → `"egg"` → match |
| 3 | Token-sort (word order) | `"ground cumin"` → `"cumin ground"` → match |
| 4 | Strip leading modifiers | `"ripe diced tomatoes"` → `"tomatoes"` → match |
| 5 | Strip trailing form words | `"black pepper powder"` → `"black pepper"` → match |
| 6 | Fuzzy against MANUAL_MAPPINGS keys | near-miss catch |
| 7 | Fuzzy against USDA food names | original fallback |

The `pipeline/live_analysis.py` module adds an eighth layer: **full USDA food search** via
`USDAFoodIndex`, which searches all 5 432 foods in `food.csv` automatically. Ingredients not found
here are genuinely absent from the USDA database.

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
- **0 flags → Low · 1–2 flags → Medium · 3+ flags → High**

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

## Setup & Running

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

### 5. Run the full batch pipeline (from scratch)
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

## Dashboard Features

### Tab 1 — Dataset Explorer
- **KPI cards** — total recipes, scored count, average weighted score, high-risk count.
- **Risk distribution** — donut charts for flag-count and weighted-score levels; histogram with threshold lines.
- **Per-nutrient breakdown** — stacked bar showing Low / Medium / High counts per nutrient.
- **Energy vs Sodium scatter** — interactive bubble chart (size = fat); hover for full details.
- **Top 10 charts** — highest weighted score, sodium, and calories.
- **Flag co-occurrence heatmap** — which risk flags tend to appear together.
- **Recipe explorer** — searchable, filterable table with radar chart and risk gauge per recipe.

### Tab 2 — Analyse a Recipe *(Phase 1)*
- Paste any ingredient list with quantities (one ingredient per line).
- Ingredients are parsed, cleaned, and matched to USDA via the 8-layer matching pipeline.
- Returns per-serving nutrition totals, a weighted risk score, a radar chart, and a per-ingredient
  breakdown table showing which USDA food each ingredient was matched to.
- Coverage indicator warns when fewer than 30 % of ingredients matched (unreliable result).

---

## Tech Stack

| Category | Libraries / Tools |
|---|---|
| Data wrangling | pandas, csv |
| Ingredient matching | RapidFuzz (fuzzy string matching) |
| Web scraping | requests, BeautifulSoup4 |
| Visualisation | Plotly, Streamlit |
| Nutritional reference | USDA FoodData Central — FNDDS 2022 |

Python 3.12 · Windows 10

---

## Limitations & Future Work

- **USDA proxy matching:** African-specific ingredients (bondwe, kapenta, egusi, sadza) are mapped
  to nutritionally similar Western equivalents — this introduces approximation error.
- **Gram weight coverage:** A portion of ingredient instances use volume-unit estimates rather than
  exact gram weights extracted from recipe text.
- **Future — Phase 2:** FDA-style nutrition label renderer in the live analysis tab.
- **Future — Phase 3:** ML risk classifier trained on the 1 188 scored recipes to predict risk
  directly from ingredient lists, without requiring full USDA matching.
- **Future — Phase 5:** Incorporate African-specific food composition tables (e.g. AFROFOODS/FAO)
  to replace USDA proxies for region-specific ingredients.

---

## Data Attribution

- **USDA FoodData Central** (fdc.nal.usda.gov) — FoodData Central, 2022.
  Food and Nutrient Database for Dietary Studies (FNDDS).
- **AllRecipes.com**, **Chef Lola's Kitchen**, **AfricanBites.com**, **Food.com** —
  recipe data scraped for research and educational use only.
