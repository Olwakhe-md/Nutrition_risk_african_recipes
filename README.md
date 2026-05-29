# Nutritional Risk Analysis of African Recipes

A full end-to-end data science project that collects African recipes from multiple sources,
maps their ingredients to USDA nutritional data, calculates per-serving nutrition, and scores
each recipe for nutritional risk against WHO dietary guidelines — all presented in an interactive
Streamlit dashboard.

---

## Key Results

| Metric | Value |
|---|---|
| Recipes in dataset | 278 |
| Recipes successfully scored | 267 (96 %) |
| Unique ingredients identified | 1 168 |
| Ingredients matched to USDA | 1 080 (92 %) |
| Average weighted risk score | 22.5 / 100 |
| Highest-risk recipe | West African Peanut Stew (84.0 / 100) |

**Risk distribution (flag-count method)**

| Risk Level | Recipes |
|---|---|
| Low (0 high-risk nutrients) | 29 |
| Medium (1–2 high-risk nutrients) | 204 |
| High (3+ high-risk nutrients) | 34 |

**Key finding:** Sodium is the dominant risk driver. Many traditional stews and one-pot dishes
exceed the per-serving sodium threshold (700 mg) largely due to bouillon cube usage.
High-calorie, high-fat dishes cluster around West and Central African peanut-based recipes.

---

## Project Overview

African cuisines are under-represented in global nutritional databases, making it difficult
to assess the dietary risk associated with traditional meal patterns.
This project addresses that gap by:

1. Assembling a dataset of **278 African recipes** spanning West, East, North, Southern, and
   Horn of Africa cuisines.
2. Mapping every ingredient to the **USDA FoodData Central** database using a multi-stage
   matching pipeline (African proxy table → manual mappings → fuzzy matching).
3. Computing **per-serving nutritional values** (energy, protein, fat, carbohydrates,
   sugars, sodium).
4. Scoring each recipe for **nutritional risk** using two complementary methods:
   - *Flag count* — counts nutrients in the "high-risk" zone.
   - *Weighted score* — a 0–100 composite with sodium weighted at 30 % to reflect the
     high hypertension burden in African populations.
5. Presenting everything in an **interactive Streamlit dashboard**.

---

## Data Sources

| Source | Recipes | Method |
|---|---|---|
| African recipe books & curated collection | 175 | Pre-compiled CSV |
| [AllRecipes.com](https://www.allrecipes.com) — African cuisine section | 59 | Web scraping (BeautifulSoup) |
| [Chef Lola's Kitchen](https://cheflolaskitchen.com) | 44 | Web scraping (WPRM plugin selectors) |
| **Total** | **278** | |

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
├── .env.example
│
└── african_recipes_nutrition/
    │
    ├── dashboard.py                  ← Streamlit app entry point
    ├── config.py                     ← Database connection config
    │
    ├── data/
    │   ├── raw/                      ← Read-only source data
    │   │   ├── merged_recipes_updated.csv     Original 67 book recipes
    │   │   ├── food.csv                       USDA food descriptions
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
    │   │   ├── african_recipes_dataset.csv    59 AllRecipes.com recipes
    │   │   └── cheflola_scraped.csv           44 Chef Lola's Kitchen recipes
    │   │
    │   └── outputs/                  ← Final analysis results
    │       ├── recipe_nutrition.csv           Per-serving nutrition (278 recipes)
    │       └── recipe_risk_scores.csv         Risk scores + flags (278 recipes)
    │
    ├── pipeline/                     ← Numbered execution scripts (run in order)
    │   ├── 01_extract_measures.py    Extract gram weights from ingredient text
    │   ├── 02_fix_ingredient_mapping.py  Apply proxy + bad-match corrections
    │   ├── 03_integrate_scraped.py   Add 59 AllRecipes recipes to pipeline
    │   ├── 04_integrate_cheflola.py  Add 44 Chef Lola recipes to pipeline
    │   ├── 05_fix_scraped_mapping.py Fix unmatched AllRecipes ingredients
    │   ├── 06_fix_cheflola_mapping.py Fix unmatched Chef Lola ingredients
    │   ├── 07_rematch_unmatched.py   Final fuzzy-match pass vs full USDA DB
    │   └── 08_calculate_nutrition.py Compute per-serving nutrition for all recipes
    │
    ├── scripts/                      ← Reusable library modules
    │   ├── cleaner.py                Ingredient name cleaning + African proxy table
    │   ├── matcher.py                USDA fuzzy matching (RapidFuzz)
    │   └── loader.py                 SQLite/PostgreSQL DB loader
    │
    ├── scrapers/                     ← Web scraping scripts
    │   ├── scrape_cheflola.py        Scraper for cheflolaskitchen.com (WPRM)
    │   └── allrecipes_urls.txt       59 AllRecipes.com URLs
    │
    ├── scoring/
    │   └── score_nutrition_risk.py   WHO-based nutritional risk scorer
    │
    ├── notebooks/                    ← Exploratory analysis
    │   ├── 01_cleaning_tables.ipynb
    │   ├── 02_recipe_web_scraping.ipynb
    │   ├── 03_missing_recipes_scraper.ipynb
    │   └── 04_pdf_recipe_scrapping.ipynb
    │
    └── db/
        ├── nutrition.db              SQLite database
        └── migrations/               SQL schema files
```

---

## Pipeline Walkthrough

The pipeline runs in 8 numbered steps, each building on the previous.

### Step 1 — Extract gram weights (`01_extract_measures.py`)
Parses raw ingredient lines (e.g. `"2 tablespoons olive oil"`, `"1 (400g) can tomatoes"`)
into a standard gram weight using a 5-priority extraction hierarchy:
bracketed metrics → leading metrics → pounds → volume units → count estimates.

### Step 2 — Fix ingredient mapping (`02_fix_ingredient_mapping.py`)
Applies hand-curated corrections to the initial ingredient–USDA mapping:
- Assigns USDA FDC IDs to 37 African/regional proxy ingredients
  (e.g. bondwe → amaranth leaves, garri → cassava flour, samp → hominy corn).
- Corrects known bad fuzzy matches (e.g. all-purpose flour → taco shell).

### Steps 3 & 4 — Integrate scraped recipes
Recipes that had only 1 placeholder ingredient in the pipeline were re-scraped
from the web and integrated with their full ingredient lists:
- **Step 3:** 59 AllRecipes.com recipes using structured HTML (`data-ingredient-*` attributes).
- **Step 4:** 44 Chef Lola's Kitchen recipes using WP Recipe Maker plugin selectors
  (`li.wprm-recipe-ingredient` with separate amount / unit / name spans).

### Steps 5 & 6 — Fix scraped ingredient mappings
Resolves unmatched ingredients from the scraped recipes using three passes:
1. Proxy map — matches proxy food names from the African ingredient table.
2. Direct map — hand-assigned USDA FDC IDs for ~130 common English ingredients
   (chicken, butter, lentils, couscous, etc.).
3. Keyword rules — containment-based matching for descriptive names
   (e.g. `"onion finely chopped"` → Onions, raw).

### Step 7 — Rematch unmatched (`07_rematch_unmatched.py`)
Runs a final fuzzy-match pass against the full 5 432-entry USDA food.csv database
(lowercased for case-insensitive comparison) at a 65 % similarity threshold.
This resolves ingredients the small 300-entry reference pool missed.

### Step 8 — Calculate nutrition (`08_calculate_nutrition.py`)
For each recipe and each ingredient:
```
nutrient_per_serving = (gram_weight_per_serving / 100) × USDA_nutrient_per_100g
```
Totals six nutrients per recipe: energy (kcal), protein, fat, carbohydrates, sugars, sodium.
Uses extracted gram weights where available; falls back to recipe_ingredient_final measures.

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
The number of High flags determines the overall risk level:
- **0 flags → Low**, **1–2 flags → Medium**, **3+ flags → High**

### Method 2 — Weighted score (0–100)
Sodium is weighted most heavily (30 %) to reflect the high hypertension burden
in African populations.

| Nutrient | Weight | Rationale |
|---|---|---|
| Sodium | 30 % | Leading NCD risk in sub-Saharan Africa |
| Energy | 25 % | Obesity and overweight |
| Fat | 20 % | Cardiovascular disease |
| Sugars | 15 % | Diabetes and metabolic syndrome |
| Protein *(deficiency)* | 10 % | Malnutrition risk |

Weighted score thresholds: **< 25 Low · 25–50 Medium · 50–75 High · 75–100 Very High**

---

## Setup & Running

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the full pipeline (from scratch)
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
py scoring/score_nutrition_risk.py
```

### 3. Launch the dashboard
```bash
cd african_recipes_nutrition
streamlit run dashboard.py
```
Opens at **http://localhost:8501**

### 4. Re-scrape Chef Lola recipes (if needed)
```bash
cd african_recipes_nutrition
py scrapers/scrape_cheflola.py
```

---

## Dashboard Features

The Streamlit dashboard (`dashboard.py`) provides:

- **KPI cards** — total recipes, scored count, average weighted score, high-risk count.
- **Risk distribution** — donut charts for flag-count and weighted-score levels;
  histogram of weighted scores with threshold lines.
- **Per-nutrient breakdown** — stacked bar showing Low / Medium / High counts per nutrient.
- **Energy vs Sodium scatter** — interactive bubble chart (bubble size = fat); hover for
  full recipe details.
- **Top 10 charts** — highest weighted score, highest sodium, highest calories.
- **Flag co-occurrence heatmap** — which risk flags tend to appear together.
- **Recipe explorer** — searchable, filterable, sortable table with coverage progress bars.

---

## Tech Stack

| Category | Libraries / Tools |
|---|---|
| Data wrangling | pandas, csv |
| Ingredient matching | RapidFuzz (fuzzy string matching) |
| Web scraping | requests, BeautifulSoup4 |
| Visualisation | Plotly, Streamlit |
| Database | SQLite (via Python `sqlite3`) |
| Nutritional reference | USDA FoodData Central — FNDDS 2022 |

Python 3.12 · Windows 10

---

## Limitations & Future Work

- **Gram weight coverage:** 63 % of ingredient instances have an extracted gram weight;
  the remainder use volume-unit estimates which introduce measurement uncertainty.
- **USDA proxy matching:** African-specific ingredients (bondwe, kapenta, egusi) are mapped
  to nutritionally similar Western equivalents — this introduces approximation error.
- **Ingredient coverage:** 11 recipes (4 %) could not be scored due to insufficient
  ingredient-to-USDA matching.
- **Future:** incorporate African-specific food composition tables (e.g. AFROFOODS) to
  replace USDA proxies; add micronutrient analysis (iron, vitamin A, zinc).

---

## Data Attribution

- **USDA FoodData Central** (fdc.nal.usda.gov) — FoodData Central, 2022.
  Food and Nutrient Database for Dietary Studies (FNDDS).
- **AllRecipes.com** — recipe data scraped for research/educational use.
- **Chef Lola's Kitchen** (cheflolaskitchen.com) — recipe data scraped for
  research/educational use.
