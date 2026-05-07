import re
import pandas as pd
from pathlib import Path

RAW_PATH = Path(r"C:\Users\mdumiseni\Documents\data science assignements\data-science-portfolio\nutrition-risk-african-recipes\raw_data\merged_recipes_updated.csv")
OUT_DIR = Path("data_clean")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OVERRIDES_PATH = OUT_DIR / "ingredient_overrides.csv"

# --- helpers ---
LEADING_UNITS = {
    "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
    "teaspoons", "ml", "l", "g", "kg", "oz", "lb", "lbs", "gram", "grams",
    "kilogram", "kilograms", "pinch", "pinches", "dash", "clove", "cloves",
    "can", "cans", "slice", "slices", "piece", "pieces"
}

FILLER_TOKENS = {
    "to", "taste", "optional", "for", "serving", "plus", "more", "needed",
    "and", "or", "of", "the", "a", "an", "into", "in", "with", "without",
    "from", "on", "at", "it", "its"
}

SIZE_TOKENS = {"large", "medium", "small"}

PREP_TOKENS = {
    "chopped", "minced", "diced", "sliced", "crushed", "freshly", "roughly",
    "finely", "thinly", "thickly", "grated", "peeled", "rinsed", "drained",
    "divided", "halved", "quartered", "cubed", "cut", "soaked", "torn",
    "softened", "melted", "beaten", "mashed"
}

FORM_TOKEN_MAP = {
    "fresh": "fresh",
    "powder": "powder",
    "powdered": "powder",
    "ground": "ground",
    "dried": "dried",
    "dry": "dried",
    "paste": "paste",
    "puree": "puree",
    "pureed": "puree",
    "canned": "canned",
    "can": "canned",
    "tinned": "canned",
    "stock": "stock",
    "broth": "stock",
    "bouillon": "bouillon",
    "cube": "cube",
    "granules": "granulated",
    "granulated": "granulated",
    "flake": "flakes",
    "flakes": "flakes",
    "flak": "flakes",
    "whole": "whole",
    "frozen": "frozen",
    "smoked": "smoked",
    "toasted": "toasted",
    "roasted": "roasted",
    "infused": "infused",
    "parboiled": "parboiled"
}

FRESH_DEFAULT_BASES = {
    "garlic", "onion", "tomato", "ginger", "pepper", "chili", "chilli"
}

GARLIC_FRESH_HINTS = {"clove", "cloves", "head"}
NON_INGREDIENT_PHRASES = {
    "on the other hand", "growing up", "i love", "my mum", "my dad",
    "when i was", "relationship with", "spent a lot of time"
}

NON_INGREDIENT_TOKENS = {
    "i", "my", "we", "our", "you", "me", "love", "relationship",
    "growing", "when", "while"
}

UNCOUNTABLE_PLURALS = {"couscous", "molasses", "bass"}

def normalize_text(s: str) -> str:
    if pd.isna(s):
        return ""
    s = s.lower().strip()
    s = re.sub(r"\([^)]*\)", " ", s)           # remove parentheses
    s = re.sub(r"[^a-z\s\-]", " ", s)          # keep letters/spaces/hyphen
    s = re.sub(r"\s+", " ", s).strip()
    return s

def singularize(token: str) -> str:
    if token in UNCOUNTABLE_PLURALS:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token

def strip_leading_qty_and_units(s: str) -> str:
    s = re.sub(r"^\d+(\.\d+)?(\s+\d+\/\d+)?\s*", "", s)
    s = re.sub(r"^(one|two|three|four|five|six|seven|eight|nine|ten)\s+", "", s)
    tokens = s.split()
    while tokens and tokens[0] in LEADING_UNITS:
        tokens = tokens[1:]
    return " ".join(tokens)

def detect_form(tokens: list[str], text: str) -> str:
    for token in tokens:
        if token in FORM_TOKEN_MAP:
            return FORM_TOKEN_MAP[token]
    if "garlic" in tokens and any(t in GARLIC_FRESH_HINTS for t in tokens):
        return "fresh"
    if "fresh" in tokens:
        return "fresh"
    return "unspecified"

def is_non_ingredient_text(text: str, tokens: list[str]) -> bool:
    if not tokens:
        return True
    if len(tokens) >= 25:
        return True
    if any(phrase in text for phrase in NON_INGREDIENT_PHRASES):
        return True
    if len(tokens) >= 12 and sum(t in NON_INGREDIENT_TOKENS for t in tokens) >= 2:
        return True
    return False

def extract_ingredient_fields(line_raw: str) -> dict:
    raw = "" if pd.isna(line_raw) else str(line_raw).strip()
    text = normalize_text(raw)
    text = strip_leading_qty_and_units(text)
    tokens = text.split()

    if is_non_ingredient_text(text, tokens):
        return {
            "ingredient_name_clean": "",
            "base_ingredient": "",
            "form": "unspecified",
            "prep": "",
            "nutrition_lookup_key": "",
            "parse_status": "drop",
            "review_reason": "non_ingredient_text"
        }

    prep_tokens = [t for t in tokens if t in PREP_TOKENS]
    form = detect_form(tokens, text)

    base_tokens = []
    for token in tokens:
        if token in FILLER_TOKENS or token in SIZE_TOKENS:
            continue
        if token in PREP_TOKENS:
            continue
        if token in FORM_TOKEN_MAP:
            continue
        if token in LEADING_UNITS:
            continue
        if token in GARLIC_FRESH_HINTS and "garlic" in tokens:
            continue
        base_tokens.append(singularize(token))

    # Remove accidental trailing one-letter tokens after cleanup.
    base_tokens = [t for t in base_tokens if len(t) > 1]
    base_ingredient = " ".join(base_tokens).strip()

    if not base_ingredient:
        return {
            "ingredient_name_clean": "",
            "base_ingredient": "",
            "form": form,
            "prep": " ".join(sorted(set(prep_tokens))),
            "nutrition_lookup_key": "",
            "parse_status": "drop",
            "review_reason": "empty_base_after_cleaning"
        }

    if form == "unspecified" and base_ingredient in FRESH_DEFAULT_BASES:
        form = "fresh"

    ingredient_name_clean = base_ingredient if form == "unspecified" else f"{base_ingredient} ({form})"
    nutrition_lookup_key = f"{base_ingredient}|{form}"

    review_reasons = []
    if len(base_tokens) >= 5:
        review_reasons.append("long_base_phrase")
    if "salt" in base_tokens and "pepper" in base_tokens:
        review_reasons.append("mixed_seasoning")
    if len(tokens) >= 10:
        review_reasons.append("long_raw_phrase")
    if any(t in {"or", "and"} for t in tokens):
        review_reasons.append("contains_conjunction")

    parse_status = "review" if review_reasons else "ok"
    return {
        "ingredient_name_clean": ingredient_name_clean,
        "base_ingredient": base_ingredient,
        "form": form,
        "prep": " ".join(sorted(set(prep_tokens))),
        "nutrition_lookup_key": nutrition_lookup_key,
        "parse_status": parse_status,
        "review_reason": ";".join(review_reasons)
    }

# --- load ---
df = pd.read_csv(RAW_PATH)
# --- FIX / ENSURE RECIPE IDs ---
# Keep original IDs as numeric so we can detect truly missing recipe blocks.
df["recipe_id_raw"] = pd.to_numeric(df["recipe_id"], errors="coerce")

# Build recipe blocks from title changes.
df["recipe_title"] = df["recipe_title"].fillna("")
new_recipe_block = df["recipe_title"].ne(df["recipe_title"].shift()).fillna(True)
df["recipe_block"] = new_recipe_block.cumsum()

# Use the first non-null raw ID per block; assign new IDs to blocks with no ID.
block_id_map = df.groupby("recipe_block", sort=False)["recipe_id_raw"].first()
max_id = int(block_id_map.dropna().max()) if block_id_map.notna().any() else 0
missing_blocks = block_id_map.isna()
block_id_map.loc[missing_blocks] = range(max_id + 1, max_id + 1 + int(missing_blocks.sum()))

df["recipe_id"] = df["recipe_block"].map(block_id_map).astype(int)

# Cleanup temporary columns
df = df.drop(columns=["recipe_id_raw", "recipe_block"])

# --- parse ingredients with form-aware cleaning ---
if "ingredient_name" not in df.columns:
    df["ingredient_name"] = ""

source_line = df["ingredient_line_raw"].fillna(df["ingredient_name"]).fillna("")
parsed = source_line.apply(extract_ingredient_fields).apply(pd.Series)
df = pd.concat([df, parsed], axis=1)

# Optional manual overrides keyed on ingredient_line_raw.
if OVERRIDES_PATH.exists():
    overrides = pd.read_csv(OVERRIDES_PATH)
    if "ingredient_line_raw" in overrides.columns:
        df = df.merge(overrides, on="ingredient_line_raw", how="left", suffixes=("", "_override"))
        for col in ["ingredient_name_clean", "base_ingredient", "form", "prep", "nutrition_lookup_key", "parse_status", "review_reason"]:
            override_col = f"{col}_override"
            if override_col in df.columns:
                df[col] = df[override_col].fillna(df[col])
                df = df.drop(columns=[override_col])

# --- recipes table (one row per recipe_id) ---
recipes_cols = ["recipe_id", "recipe_title", "country", "servings_raw", "recipe_url"]
recipes_cols = [c for c in recipes_cols if c in df.columns]

recipes_clean = (
    df[recipes_cols + (["instructions"] if "instructions" in df.columns else [])]
    .drop_duplicates(subset=["recipe_id"])
    .rename(columns={"recipe_title": "recipe_name", "country": "cuisine"})
)

# --- ingredients master ---
valid_ingredients = df[df["parse_status"] != "drop"].copy()
ingredients_master = (
    valid_ingredients[["nutrition_lookup_key", "ingredient_name_clean", "base_ingredient", "form"]]
    .dropna()
    .drop_duplicates()
)
ingredients_master = ingredients_master[ingredients_master["ingredient_name_clean"].str.len() > 0].copy()
ingredients_master = ingredients_master.sort_values(by=["base_ingredient", "form", "ingredient_name_clean"])
ingredients_master["ingredient_id"] = range(1, len(ingredients_master) + 1)
ingredients_master = ingredients_master.rename(columns={"ingredient_name_clean": "ingredient_name"})

# --- recipe_ingredients (link table) ---
recipe_ingredients = df[df["parse_status"] != "drop"][
    ["recipe_id", "ingredient_index", "ingredient_line_raw", "qty_value", "unit", "nutrition_lookup_key", "parse_status", "review_reason"]
].copy()
recipe_ingredients = recipe_ingredients.merge(
    ingredients_master[["ingredient_id", "nutrition_lookup_key"]],
    on="nutrition_lookup_key",
    how="left"
)

# Keep a default portion_factor for now
recipe_ingredients["portion_factor"] = 1.0

# --- review queue ---
ingredient_review_queue = df[df["parse_status"].isin(["review", "drop"])][
    ["recipe_id", "ingredient_index", "ingredient_line_raw", "ingredient_name_clean", "base_ingredient", "form", "parse_status", "review_reason"]
].copy()
ingredient_review_queue = ingredient_review_queue.sort_values(by=["parse_status", "review_reason", "ingredient_line_raw"])

# --- save outputs ---
recipes_clean.to_csv(OUT_DIR / "recipes_clean.csv", index=False)
ingredients_master[["ingredient_id", "ingredient_name", "base_ingredient", "form", "nutrition_lookup_key"]].to_csv(
    OUT_DIR / "ingredients_master.csv", index=False
)
recipe_ingredients[["recipe_id", "ingredient_id", "ingredient_index", "qty_value", "unit", "portion_factor", "ingredient_line_raw", "parse_status", "review_reason"]].to_csv(
    OUT_DIR / "recipe_ingredients.csv", index=False
)
ingredient_review_queue.to_csv(OUT_DIR / "ingredient_review_queue.csv", index=False)

print("Saved:")
print(" - data_clean/recipes_clean.csv")
print(" - data_clean/ingredients_master.csv")
print(" - data_clean/recipe_ingredients.csv")
print(" - data_clean/ingredient_review_queue.csv")
