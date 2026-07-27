"""
live_analysis.py
================
Ad-hoc nutrition analysis for a single recipe entered by the user.

WHAT THIS FILE DOES (plain English)
─────────────────────────────────────
The existing pipeline works in batch mode: it reads hundreds of recipes from
CSV files and writes results to CSV files.  For Phase 1 (live recipe input)
we need a version that can analyse *one* recipe typed by the user, without
touching any CSV files.

Three steps:
  1. parse_ingredient_line("2 cups rice") → qty=2.0, unit="cups", grams=480
  2. LiveAnalyser.analyse(lines, servings) → match each ingredient to USDA,
     scale by gram weight, sum to get per-serving totals
  3. Score the totals using the same rules as score_nutrition_risk.py

Used by: dashboard.py — "Analyse a Recipe" tab
"""

from __future__ import annotations

import csv
import os
import re

import pandas as pd

# ── Paths to reference data ───────────────────────────────────────────────────
# These are the same files the batch pipeline uses.
BASE             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING_REF_FILE = os.path.join(BASE, 'data', 'raw',  'ingredient_mapping_original.csv')
NUTRIENT_FILE    = os.path.join(BASE, 'data', 'raw',  'food_nutrient.csv')
FOOD_CSV         = os.path.join(BASE, 'data', 'raw',  'food.csv')
WAFCT_CSV        = os.path.join(BASE, 'data', 'raw',  'wafct_foods.csv')
DENSITY_CSV      = os.path.join(BASE, 'data', 'interim', 'food_density.csv')

# ── USDA nutrient IDs we care about ──────────────────────────────────────────
# The food_nutrient.csv file has hundreds of nutrient types.
# Each one is identified by a numeric ID.  We only need these six.
NUTRIENT_IDS = {
    203: "protein_g",
    204: "fat_g",
    205: "carbohydrate_g",
    208: "energy_kcal",
    269: "sugars_g",
    307: "sodium_mg",
}

# ── Unit → grams conversion table ─────────────────────────────────────────────
# WHY WE NEED THIS:
#   USDA nutrition data is expressed as "amount per 100 grams of food".
#   So "2 cups rice" = 2 × 240g = 480g.  We need 480g to calculate:
#     protein_contribution = (480 / 100) × protein_per_100g_of_rice
#
# Weight units — multiply quantity by the gram value
UNIT_GRAMS: dict[str, float] = {
    "g": 1.0,       "gram": 1.0,     "grams": 1.0,
    "kg": 1000.0,   "kilogram": 1000.0,
    "oz": 28.35,    "ounce": 28.35,  "ounces": 28.35,
    "lb": 453.6,    "lbs": 453.6,    "pound": 453.6,   "pounds": 453.6,
    "ml": 1.0,      "l": 1000.0,     "litre": 1000.0,
    "tsp": 5.0,     "teaspoon": 5.0,  "teaspoons": 5.0,
    "ts":  5.0,     # non-standard abbreviation (typo variant of tsp)
    "tbsp": 15.0,   "tablespoon": 15.0, "tablespoons": 15.0,
    "tbs": 15.0,    # non-standard abbreviation (typo variant of tbsp)
    "cup": 240.0,   "cups": 240.0,
    # Small measures — appear constantly in recipes as "to taste" alternatives
    "pinch": 0.35,  "pinches": 0.35,   # ~1/16 tsp
    "dash":  0.6,   "dashes":  0.6,    # ~1/8 tsp
    "drop":  0.05,  "drops":   0.05,
}

# Volumetric units — millilitres per unit. These need an ingredient DENSITY to
# become grams (a cup of oil weighs far less than a cup of honey), so they are
# handled separately from the weight units above: the parser records the volume
# in ml here, and LiveAnalyser.analyse() converts it to grams once the food (and
# therefore its density) is known. See _density_for().
VOLUME_ML: dict[str, float] = {
    "ml": 1.0,      "l": 1000.0,       "litre": 1000.0,  "liter": 1000.0,
    "tsp": 5.0,     "teaspoon": 5.0,   "teaspoons": 5.0,  "ts": 5.0,
    "tbsp": 15.0,   "tablespoon": 15.0, "tablespoons": 15.0, "tbs": 15.0,
    "cup": 240.0,   "cups": 240.0,
}

# Fallback density (grams per millilitre) by ingredient category, used when the
# matched food has no real USDA portion. Keyword match on the cleaned name, first
# hit wins, so ORDER MATTERS: more specific categories come before broader ones.
# Reference densities: water 1.0, oils ~0.91, granulated sugar ~0.85, wheat flour
# ~0.53, dry rice/grain ~0.85, chopped leafy greens ~0.2, honey/syrup ~1.4.
CATEGORY_DENSITY: list[tuple[tuple[str, ...], float]] = [
    (("oil", "butter", "ghee", "margarine", "lard", "shortening", "dripping"), 0.91),
    (("honey", "syrup", "molasses", "treacle", "golden syrup"),                1.42),
    (("flour", "cornmeal", "cornflour", "semolina", "besan", "starch"),        0.53),
    (("sugar", "icing", "confectioner"),                                        0.85),
    (("rice", "couscous", "bulgur", "fonio", "millet", "quinoa", "oats",
      "oatmeal", "cornmeal", "sorghum", "semolina"),                            0.85),
    (("spinach", "kale", "cabbage", "lettuce", "greens", "leaf", "leaves",
      "ugu", "herb", "parsley", "cilantro", "coriander", "basil", "mint"),      0.20),
    (("water", "milk", "broth", "stock", "juice", "vinegar", "wine",
      "beer", "cream", "sauce", "puree", "yoghurt", "yogurt", "coconut milk"),  1.00),
]

# Any density outside this band is treated as a bad USDA portion and ignored in
# favour of the category fallback (mirrors the build-time sanity filter).
MIN_DENSITY, MAX_DENSITY = 0.1, 2.0

# Count units — "3 cloves garlic": 3 × 4g = 12g
COUNT_GRAMS: dict[str, float] = {
    "clove": 4.0,   "cloves": 4.0,
    "piece": 100.0, "pieces": 100.0,
    "slice": 30.0,  "slices": 30.0,
    "egg": 55.0,    "eggs": 55.0,
    "bunch": 100.0, "head": 200.0,
    "large": 150.0, "medium": 110.0, "small": 70.0,
    "stalk": 40.0,  "stalks": 40.0,
    "sprig": 5.0,   "sprigs": 5.0,
    "can": 400.0,   "cans": 400.0,
    "tin": 400.0,   "tins": 400.0,
}

# Unicode fractions the user might type or paste
# Words that appear at the END of an ingredient name but are actually the unit.
# "6 garlic cloves" → "garlic" is the ingredient, "cloves" is the unit (4g each).
# Limited set to avoid false positives — "eggs", "bunch", "head" are intentionally
# excluded because "hard boiled eggs" should not become unit="eggs", name="hard boiled".
_TRAILING_UNIT_WORDS: frozenset[str] = frozenset({
    "cloves", "clove",
    "pieces", "piece",
    "slices", "slice",
    "cans", "can",
    "tins", "tin",
    "stalks", "stalk",
    "sprigs", "sprig",
})

# Map each glyph to its "numerator/denominator" form (not a decimal) so the
# fraction handling below reads it. Keeping the n/d form lets "2½" become
# "2 1/2" and flow through the mixed-number parser instead of gluing into
# "20.5" (which previously turned 2½ cups into 20.5 cups).
UNICODE_FRACTIONS: dict[str, str] = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅛": "1/8",
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Ingredient line parser
# ─────────────────────────────────────────────────────────────────────────────
#
# TEACHING NOTE:
#   This is the trickiest part.  Recipe ingredient lines come in many formats:
#     "2 cups rice"          → qty=2.0,   unit="cups",   name="rice"
#     "500g chicken"         → qty=500.0, unit="g",      name="chicken"
#     "1 tbsp palm oil"      → qty=1.0,   unit="tbsp",   name="palm oil"
#     "3 cloves garlic"      → qty=3.0,   unit="cloves", name="garlic"
#     "1 onion, chopped"     → qty=1.0,   unit="",       name="onion"
#     "salt to taste"        → qty=0.0,   unit="",       name="salt to taste"
#     "2½ cups flour"        → qty=2.5,   unit="cups",   name="flour"
#     "2 1/2 cups water"     → qty=2.5,   unit="cups",   name="water"
#
#   We parse left-to-right in three stages:
#     Stage A: pull off the leading number (whole, fraction, or combined)
#     Stage B: check if the next word is a known unit
#     Stage C: everything left = ingredient name

def parse_ingredient_line(line: str) -> dict:
    """
    Parse a single ingredient line into its components.

    Returns a dict with keys:
      raw          — original line as typed
      qty          — float quantity (0.0 if none found)
      unit         — unit string (empty string if none)
      name_raw     — ingredient name before cleaning, commas stripped
      grams        — float gram equivalent (None if can't convert)
    """
    raw = line.strip()
    if not raw:
        return {"raw": raw, "qty": 0.0, "unit": "", "volume_ml": None,
                "name_raw": raw, "grams": None}

    # Expand unicode fractions into "n/d" text the numeric parser understands.
    # A glyph glued to a whole number ("2½") gets a space inserted so it becomes
    # a mixed number ("2 1/2"); a standalone glyph ("½") expands in place.
    text = raw
    for char, frac in UNICODE_FRACTIONS.items():
        text = re.sub(r'(?<=\d)' + re.escape(char), ' ' + frac, text)
        text = text.replace(char, frac)
    text = text.strip()

    qty  = 0.0
    unit = ""
    rest = text

    # ── Stage A: extract leading number ──────────────────────────────────────
    # Four sub-patterns in order of specificity:
    #   A1: "500g" — number glued to a weight unit like g/kg/ml/l
    #   A2: "2 1/2" — whole number followed by a fraction
    #   A3: "1/2"  — just a fraction
    #   A4: "2.5"  — decimal or integer

    # A1: number immediately followed by a weight symbol (e.g. "500g", "1.5kg")
    m = re.match(r'^(\d+\.?\d*)(g|kg|ml|l)\s+(.*)', text, re.IGNORECASE)
    if m:
        qty  = float(m.group(1))
        unit = m.group(2).lower()
        rest = m.group(3).strip()
    else:
        # A2: whole number + space + fraction  (e.g. "2 1/2")
        m = re.match(r'^(\d+)\s+(\d+)/(\d+)\s*(.*)', text)
        if m and int(m.group(3)) != 0:
            qty  = float(m.group(1)) + float(m.group(2)) / float(m.group(3))
            rest = m.group(4).strip()
        else:
            # A3: pure fraction  (e.g. "1/2 cup") — guard against a zero
            # denominator like "1/0" so a garbage line can't divide by zero.
            m = re.match(r'^(\d+)/(\d+)\s*(.*)', text)
            if m and int(m.group(2)) != 0:
                qty  = float(m.group(1)) / float(m.group(2))
                rest = m.group(3).strip()
            else:
                # A4: plain number  (e.g. "2 cups", "1 onion", "3.5")
                m = re.match(r'^(\d+\.?\d*)\s*(.*)', text)
                if m:
                    qty  = float(m.group(1))
                    rest = m.group(2).strip()

    # ── Stage B: check if the next word is a known unit ───────────────────────
    # We only try this step if we haven't already captured a unit in A1.
    # Also handles lines that start with the unit and no number, e.g.:
    #   "Pinch of cayenne" — no leading digit, but "pinch" is a unit.
    #   In that case rest still equals the full original text.
    if not unit and rest:
        words = rest.split(None, 1)
        candidate = words[0].lower().rstrip('.,')
        if candidate in UNIT_GRAMS or candidate in COUNT_GRAMS:
            unit = candidate
            rest = words[1].strip() if len(words) > 1 else ""

    # ── Stage C: clean up the ingredient name ─────────────────────────────────
    #
    # Three things to strip from the ingredient text before matching:
    #
    #   1. "of" connector  — "Pinch of cayenne" → after extracting "pinch" as the
    #      unit, rest = "of cayenne pepper". Strip the leading "of ".
    #
    #   2. Prep notes after a comma — "onion, finely chopped" → "onion"
    #
    #   3. "or Y" alternatives — "parsley or cilantro" → "parsley"
    #      Recipes often offer substitutes. We take the first option.

    # Strip leading "of" connector
    if rest.lower().startswith("of "):
        rest = rest[3:].strip()

    # Split on comma, then on " or ", take first option only
    # "onion, finely chopped" → "onion"
    # "parsley or cilantro"   → "parsley"
    name_raw = rest.split(",")[0].split(" or ")[0].strip() if rest else raw

    # ── Name cleanup ─────────────────────────────────────────────────────────

    # 1. Strip parenthetical annotations anywhere in the name.
    #    "cayenne (optional)" → "cayenne"
    #    "thyme (fresh or dried)" → "thyme"
    name_raw = re.sub(r'\s*\([^)]*\)', '', name_raw).strip()

    # 2. Strip a leading "NUMBER UNIT" that leaked from a compound quantity.
    #    "15 oz can of cannellini beans" → "can of cannellini beans"
    #    Happens when user writes "1 15 oz can of X" (the 15 oz stays in name).
    m_leak = re.match(r'^(\d+\.?\d*)\s*(oz|fl\s*oz|g|kg|ml|l)\s+(.*)', name_raw, re.IGNORECASE)
    if m_leak:
        name_raw = m_leak.group(3).strip()
        # Also strip a leading "can of" / "tin of" / "jar of" container phrase
        name_raw = re.sub(r'^(can|tin|jar|bottle|bag|packet)\s+of\s+', '', name_raw, flags=re.IGNORECASE).strip()

    # 3. Trailing COUNT unit word: "garlic cloves" → unit="cloves", name="garlic"
    #    Only for unambiguous container/count words (see _TRAILING_UNIT_WORDS).
    if not unit and name_raw:
        words = name_raw.split()
        if len(words) > 1 and words[-1].lower() in _TRAILING_UNIT_WORDS:
            unit     = words[-1].lower()
            name_raw = " ".join(words[:-1])

    # If no quantity was given but a small-measure unit was found (e.g. "pinch",
    # "dash"), assume 1 unit so the ingredient still contributes to nutrition.
    if qty == 0 and unit in UNIT_GRAMS:
        qty = 1.0

    # ── Gram conversion ───────────────────────────────────────────────────────
    # Volumetric units record their volume in ml and get a PROVISIONAL gram
    # value at water density (1 g/ml). analyse() refines this to the real weight
    # using the matched food's density; callers that use the parser standalone
    # (e.g. tests) still get a sensible water-equivalent estimate.
    grams     = None
    volume_ml = None
    if unit in VOLUME_ML and qty > 0:
        volume_ml = qty * VOLUME_ML[unit]
        grams     = volume_ml                      # provisional (water density)
    elif unit in UNIT_GRAMS and qty > 0:
        grams = qty * UNIT_GRAMS[unit]
    elif unit in COUNT_GRAMS and qty > 0:
        grams = qty * COUNT_GRAMS[unit]
    elif qty > 0 and not unit:
        # e.g. "1 onion" with no unit — assume a medium-sized item (~150g)
        grams = qty * 150.0

    return {
        "raw":       raw,
        "qty":       qty,
        "unit":      unit,
        "volume_ml": volume_ml,
        "name_raw": name_raw,
        "grams":    grams,
    }


def match_confidence(match_type: str | None) -> str:
    """Map an ingredient's match_type to a confidence bucket for the UI:
    'high' | 'medium' | 'low' | 'custom' | 'none'.

      manual_match   curated mapping           -> high
      user_override  the user picked it        -> custom
      usda_search    fuzzy search of food.csv  -> medium
      wafct          West African food table   -> medium
      fuzzy_NN%      fuzzy MANUAL_MAPPINGS key  -> medium if NN>=85 else low
      no_match / other                          -> none
    """
    mt = (match_type or "").lower()
    if mt == "manual_match":
        return "high"
    if mt == "user_override":
        return "custom"
    if mt in ("usda_search", "wafct"):
        return "medium"
    if mt.startswith("fuzzy_"):
        m = re.search(r'(\d+)', mt)
        return "medium" if (m and int(m.group(1)) >= 85) else "low"
    return "none"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — LiveAnalyser class
# ─────────────────────────────────────────────────────────────────────────────
#
# TEACHING NOTE:
#   We load the USDA database once when the class is created (it's ~150 MB so
#   we don't want to reload it on every button click — Streamlit's
#   @st.cache_resource handles this).
#
#   For each ingredient:
#     1. clean_ingredient("garlic, minced") → "garlic"     (strips prep noise)
#     2. matcher.match("garlic")            → fdc_id=2110003 (USDA food ID)
#     3. food_nutrients[fdc_id][203]        → 6.4 g protein per 100g garlic
#     4. (grams / 100) × 6.4               → contribution for this ingredient
#   Sum across all ingredients → divide by servings → per-serving totals.


# ─────────────────────────────────────────────────────────────────────────────
# USDA full-text search index
# ─────────────────────────────────────────────────────────────────────────────
#
# TEACHING NOTE — why this is better than MANUAL_MAPPINGS alone:
#   MANUAL_MAPPINGS is a hand-written dictionary: if an ingredient is missing,
#   we get "no match". USDAFoodIndex loads food.csv (5 432 foods) and searches
#   ALL of them automatically.  When it still fails, the answer is honest —
#   the ingredient genuinely isn't in the USDA data we have.
#
# Ranking problem:
#   food.csv is dominated by compound dishes ("Beef with mushroom sauce").
#   We need simple foods ("Mushrooms, raw") to win.  The scoring below solves
#   this:
#     base_score   = fuzzy match score (0–100)          — short names match best
#     raw_bonus    = +20 if ", raw" in description      — prefer unprocessed
#     nfs_bonus    = +10 if description ends with NFS   — "not further specified"
#     compound_pen = −20 if description contains a      — penalise mixed dishes
#                    compound-dish word not in the query
#     length_pen   = −0.4 per character                 — prefer shorter names
#
# Example — user types "carrot":
#   "Carrots, raw"                                  score ≈ 75 + 20 − 9  = 86  ✓
#   "Beef, potatoes, and vegetables incl. carrots"  score ≈ 15 − 20 − 30 = −35 ✗

from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz

# Words that appear in compound-dish descriptions.  When the user's query
# does NOT contain one of these words, we penalise descriptions that do.
_COMPOUND_DISH_WORDS: frozenset[str] = frozenset({
    "cake", "pie", "stew", "casserole", "sandwich", "burger", "pizza",
    "muffin", "cookie", "pudding", "pastry", "biscuit",
    "salad", "dip", "spread", "dressing",
    "soup",   # unless user asks for soup
    "fried",  # unless user asks for fried
    "sauce",  # unless user asks for sauce
    "gravy", "stuffed", "filled", "mixed", "combination", "blend",
    "roll", "wrap", "taco", "burrito", "dumpling",
})


class USDAFoodIndex:
    """
    Loads food.csv once and provides fuzzy ingredient-name search against all
    USDA food descriptions.

    Used as a fallback when MANUAL_MAPPINGS has no entry for an ingredient.

    Parameters
    ----------
    food_csv_path  : path to food.csv  (fdc_id, description columns required)
    threshold      : minimum fuzzy score to accept a match (default 60)
    """

    def __init__(self, food_csv_path: str, threshold: int = 60) -> None:
        self._threshold = threshold
        self._foods: list[tuple[int, str]] = []       # (fdc_id, description)
        self._desc_lower: list[str] = []               # pre-lowercased for speed
        self._desc_by_fdc: dict[int, str] = {}         # fdc_id → description
        # Inverted word index: token → list of indices in _foods
        self._index: dict[str, list[int]] = {}

        with open(food_csv_path, encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    fdc_id = int(float(row["fdc_id"]))
                except (ValueError, KeyError):
                    continue
                desc = row.get("description", "").strip()
                if not desc:
                    continue
                idx = len(self._foods)
                self._foods.append((fdc_id, desc))
                self._desc_by_fdc[fdc_id] = desc
                dl = desc.lower()
                self._desc_lower.append(dl)
                # Index every meaningful token (>2 chars)
                for token in re.split(r'[\s,;/]+', dl):
                    token = token.strip("().'-")
                    if len(token) > 2:
                        self._index.setdefault(token, []).append(idx)
                        # Also index the singularised form so "carrot" hits "carrots"
                        if token.endswith("s") and len(token) > 3:
                            self._index.setdefault(token[:-1], []).append(idx)

    def search(self, cleaned_name: str, query_words: set[str] | None = None) -> tuple[int, str] | None:
        """
        Find the best USDA food match for a cleaned ingredient name.

        Parameters
        ----------
        cleaned_name : the ingredient name after cleaning (e.g. "carrots")
        query_words  : set of words from the original query (used for compound
                       penalty check). If None, derived from cleaned_name.

        Returns
        -------
        (fdc_id, food_description)  or  None if no confident match found.
        """
        if not cleaned_name or not cleaned_name.strip():
            return None

        query = cleaned_name.lower().strip()
        if query_words is None:
            query_words = set(re.split(r'\s+', query))

        # ── Step 1: gather candidate indices via the inverted word index ──────
        # Find all USDA entries that share at least one word with the query.
        candidate_indices: set[int] = set()
        for word in query_words:
            for idx in self._index.get(word, []):
                candidate_indices.add(idx)
            # Also try singular form
            if word.endswith("s") and len(word) > 3:
                for idx in self._index.get(word[:-1], []):
                    candidate_indices.add(idx)

        if not candidate_indices:
            return None  # no word overlap with any USDA food

        # ── Step 2: score each candidate ─────────────────────────────────────
        scored = self._score_candidates(query, query_words, candidate_indices)
        if not scored:
            return None

        _, fdc_id, desc = scored[0]
        return fdc_id, desc

    def _score_candidates(self, query, query_words, candidate_indices):
        """Rank candidate foods by relevance. Returns [(score, fdc_id, desc), ...]
        sorted best-first, keeping only entries above the fuzzy threshold."""
        scored: list[tuple[float, int, str]] = []
        for idx in candidate_indices:
            fdc_id, desc = self._foods[idx]
            dl = self._desc_lower[idx]

            # Base: fuzzy token-sort ratio (handles word-order variations)
            fuzzy = _rf_fuzz.token_sort_ratio(query, dl)
            if fuzzy < self._threshold:
                continue

            score = float(fuzzy)

            # Prefer simple/raw foods
            if ", raw" in dl:
                score += 20
            elif dl.endswith("nfs") or ", nfs" in dl:
                score += 10

            # Penalise compound dishes when the user didn't ask for one
            for compound in _COMPOUND_DISH_WORDS:
                if compound in dl and compound not in query_words:
                    score -= 20
                    break   # one penalty per entry is enough

            # Prefer shorter descriptions (fewer comma-separated parts = simpler food)
            score -= len(dl) * 0.4

            scored.append((score, fdc_id, desc))

        scored.sort(key=lambda t: t[0], reverse=True)
        return scored

    def search_candidates(self, cleaned_name: str, n: int = 8) -> list[tuple[int, str]]:
        """Return up to N ranked (fdc_id, description) candidates for a name, so a
        user can pick a better match than the automatic one.

        Uses partial_ratio (rewards the query appearing inside the description)
        rather than search()'s token_sort_ratio, because for a *browsable* list
        we want simple foods with long official names — "Rice, cooked, NFS" —
        to rank highly, which token_sort_ratio penalises. Empty list if the name
        shares no words with any USDA food."""
        if not cleaned_name or not cleaned_name.strip():
            return []
        query = cleaned_name.lower().strip()
        query_words = set(re.split(r'\s+', query))

        candidate_indices: set[int] = set()
        for word in query_words:
            candidate_indices.update(self._index.get(word, []))
            if word.endswith("s") and len(word) > 3:
                candidate_indices.update(self._index.get(word[:-1], []))

        scored: list[tuple[float, int, str]] = []
        for idx in candidate_indices:
            fdc_id, desc = self._foods[idx]
            dl = self._desc_lower[idx]
            score = float(_rf_fuzz.partial_ratio(query, dl))
            if ", raw" in dl:
                score += 15
            elif dl.endswith("nfs") or ", nfs" in dl:
                score += 8
            for compound in _COMPOUND_DISH_WORDS:
                if compound in dl and compound not in query_words:
                    score -= 15
                    break
            score -= len(dl) * 0.2
            scored.append((score, fdc_id, desc))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [(fdc_id, desc) for _, fdc_id, desc in scored[:n]]

    def describe(self, fdc_id: int) -> str | None:
        """Return the USDA description for an fdc_id, or None if unknown."""
        return self._desc_by_fdc.get(int(fdc_id)) if fdc_id is not None else None


class WAFCTFoodIndex:
    """
    Loads wafct_foods.csv (1 028 West African foods from FAO/INFOODS WAFCT 2019)
    and provides fuzzy food-name search.

    WHY A SEPARATE CLASS?
    The USDA database is strong on globally common foods but almost entirely
    lacks traditional African ingredients: fufu, pounded yam, egusi, fonio,
    dawadawa, African leafy vegetables, etc.  WAFCT fills exactly that gap.

    This class is Layer 3 in the matching pipeline:
      Layer 1: MANUAL_MAPPINGS (curated overrides)
      Layer 2: USDAFoodIndex   (5 432 USDA foods)
      Layer 3: WAFCTFoodIndex  (1 028 West African foods)  ← this class

    Both English and French food names are indexed, because many West
    African ingredients are better known by their French names (Francophone
    countries make up the majority of the WAFCT coverage).

    NOTE on sugars: WAFCT does not include total sugars data.  Sugars are
    set to 0.0 for all WAFCT-matched ingredients.  This means WAFCT-matched
    foods will not trigger the sugar risk flag — an honest limitation.
    """

    def __init__(self, wafct_csv_path: str, threshold: int = 55) -> None:
        self._threshold = threshold
        # Each entry: (code, name_en, name_fr, nutrients_dict)
        self._foods: list[tuple] = []
        # Inverted word index: token → set of indices in _foods
        self._index: dict[str, set[int]] = {}

        if not os.path.exists(wafct_csv_path):
            return  # graceful degradation — wafct CSV not yet generated

        with open(wafct_csv_path, encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                name_en = row.get('food_name_en', '').strip()
                name_fr = row.get('food_name_fr', '').strip()
                if not name_en:
                    continue

                try:
                    nutrients = {
                        'energy_kcal':    float(row.get('energy_kcal')    or 0),
                        'protein_g':      float(row.get('protein_g')      or 0),
                        'fat_g':          float(row.get('fat_g')          or 0),
                        'carbohydrate_g': float(row.get('carbohydrate_g') or 0),
                        'sugars_g':       0.0,   # not measured in WAFCT
                        'sodium_mg':      float(row.get('sodium_mg')      or 0),
                    }
                except ValueError:
                    continue

                idx = len(self._foods)
                self._foods.append((row['code'], name_en, name_fr, nutrients))

                # Index both English and French names
                for name in [name_en, name_fr]:
                    for token in re.split(r'[\s,;/()\-]+', name.lower()):
                        token = token.strip("'.:*[]")
                        if len(token) > 2:
                            self._index.setdefault(token, set()).add(idx)
                            if token.endswith('s') and len(token) > 3:
                                self._index.setdefault(token[:-1], set()).add(idx)

    def search(self, query_name: str) -> tuple[str, str, dict] | None:
        """
        Find the best WAFCT food match for a cleaned ingredient name.

        Returns (wafct_code, food_name_en, nutrients_dict) or None.

        WHY partial_ratio instead of token_sort_ratio?
        WAFCT food names are long and descriptive:
          "Cocoyam, tuber, white, raw"
          "Maize, white, refined flour (special), unfortified"
        token_sort_ratio("cocoyam", "cocoyam raw tuber white") ≈ 45 — too low.
        partial_ratio finds the best matching WINDOW inside the longer string,
        so "cocoyam" against "Cocoyam, tuber, white, raw" scores ~100.

        Scoring:
          base  = max(partial_ratio_en, partial_ratio_fr)
          bonus = +15 if ALL query words appear in the candidate name
          bonus = +10 for basic preparations (raw, dried, flour, fresh)
          No length penalty — WAFCT names are intentionally verbose.
        """
        if not query_name or not self._foods:
            return None

        query = query_name.lower().strip()
        query_words = [w for w in re.split(r'\s+', query) if len(w) > 2]

        # Gather candidates via inverted word index
        candidates: set[int] = set()
        for word in query_words:
            for idx in self._index.get(word, set()):
                candidates.add(idx)
            if word.endswith('s') and len(word) > 3:
                for idx in self._index.get(word[:-1], set()):
                    candidates.add(idx)

        if not candidates:
            return None

        best_score = -999
        best_idx   = -1

        for idx in candidates:
            code, name_en, name_fr, nutrients = self._foods[idx]
            en_l = name_en.lower()
            fr_l = name_fr.lower()

            # partial_ratio: score of best substring match — handles long names
            score_en = float(_rf_fuzz.partial_ratio(query, en_l))
            score_fr = float(_rf_fuzz.partial_ratio(query, fr_l)) if fr_l else 0.0
            base     = max(score_en, score_fr)

            if base < self._threshold:
                continue

            score = base

            # Bonus: all query words present in candidate (strong signal)
            if all(w in en_l or w in fr_l for w in query_words):
                score += 15

            # Prefer basic / raw preparations over compound dishes
            if any(w in en_l for w in ('raw', 'dried', 'flour', 'fresh', 'boiled')):
                score += 10

            # Light penalty for very long names that are complex dishes
            # (not as aggressive as USDA — long names are normal in WAFCT)
            if len(name_en) > 60:
                score -= 5

            if score > best_score:
                best_score = score
                best_idx   = idx

        if best_idx < 0:
            return None

        code, name_en, name_fr, nutrients = self._foods[best_idx]
        return code, name_en, nutrients


class LiveAnalyser:
    """
    Loads reference data once; analyses ad-hoc recipes on demand.

    Usage:
        analyser = LiveAnalyser()                    # loads USDA data (~3s)
        result   = analyser.analyse(lines, servings) # instant
    """

    def __init__(
        self,
        mapping_ref_file: str = MAPPING_REF_FILE,
        nutrient_file:    str = NUTRIENT_FILE,
        food_csv:         str = FOOD_CSV,
    ) -> None:
        # Layer 1: MANUAL_MAPPINGS — curated overrides (African ingredients,
        # known-good proxies).  Always checked first.
        df_ref        = pd.read_csv(mapping_ref_file)
        from scripts.matcher import Matcher
        self._matcher = Matcher(df_ref)

        # Layer 2: USDAFoodIndex — searches all 5 432 foods in food.csv
        # automatically.  Used when MANUAL_MAPPINGS has no entry.
        self._usda_index = USDAFoodIndex(food_csv)

        # Layer 3: WAFCTFoodIndex — 1 028 West African foods from FAO/INFOODS.
        # Used when USDA has no match (African staples, local varieties).
        self._wafct_index = WAFCTFoodIndex(WAFCT_CSV)

        # Nutrient lookup table: {fdc_id: {nutrient_id: amount_per_100g}}
        self._food_nutrients = self._load_nutrients(nutrient_file)

        # Per-food density {fdc_id: g_per_ml}, derived from USDA portions by
        # pipeline/build_density_table.py. Used to turn a volume ("2 cups flour")
        # into a realistic weight. Optional — falls back to category densities.
        self._density = self._load_density(DENSITY_CSV)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def candidate_foods(self, cleaned_name: str, n: int = 8) -> list[tuple[int, str]]:
        """Top-N alternative USDA foods for an ingredient name, for the UI's
        'change this match' dropdown. Thin wrapper over USDAFoodIndex."""
        return self._usda_index.search_candidates(cleaned_name, n)

    @staticmethod
    def _load_density(filepath: str) -> dict[int, float]:
        """Load {fdc_id: g_per_ml}. Returns {} if the table hasn't been built."""
        if not os.path.exists(filepath):
            return {}
        df = pd.read_csv(filepath)
        return {int(fid): float(g) for fid, g in zip(df['fdc_id'], df['g_per_ml'])}

    def _density_for(self, fdc_id, cleaned_name: str) -> float:
        """Grams per millilitre for an ingredient, best source first:
          1. the matched food's real USDA density (if fdc_id is an integer
             food id present in the table and within a sane range),
          2. a category density keyed on the ingredient name,
          3. water (1.0) as a last resort.
        WAFCT matches use non-integer codes, so they skip straight to step 2.
        """
        try:
            dens = self._density.get(int(fdc_id))
        except (TypeError, ValueError):
            dens = None
        if dens is not None and MIN_DENSITY <= dens <= MAX_DENSITY:
            return dens

        name = (cleaned_name or "").lower()
        for keywords, category_density in CATEGORY_DENSITY:
            if any(kw in name for kw in keywords):
                return category_density
        return 1.0

    @staticmethod
    def _load_nutrients(filepath: str) -> dict[int, dict[int, float]]:
        """
        Read food_nutrient.csv and keep only the six nutrients we care about.

        WHY filter early?
        The file has ~9 million rows (every food × every nutrient).
        Loading all of it would waste RAM.  By filtering to just our 6
        nutrient IDs we keep the footprint small.
        """
        target_ids = set(NUTRIENT_IDS.keys())
        nutrients: dict[int, dict[int, float]] = {}

        with open(filepath, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    nid = int(float(row["nutrient_id"].strip()))
                except (ValueError, KeyError):
                    continue
                if nid not in target_ids:
                    continue
                try:
                    fdc_id = int(float(row["fdc_id"].strip()))
                    amount = float(row.get("amount", 0) or 0)
                except ValueError:
                    continue
                nutrients.setdefault(fdc_id, {})[nid] = amount

        return nutrients

    # ── Public interface ──────────────────────────────────────────────────────

    def analyse(self, ingredient_lines: list[str], servings: int = 4,
                overrides: dict[int, int] | None = None) -> dict:
        """
        Analyse a recipe from a list of raw ingredient strings.

        Parameters
        ----------
        ingredient_lines : list of strings, one ingredient per entry
        servings         : number of servings the recipe makes
        overrides        : optional {ingredient_index: fdc_id} — force a specific
                           USDA food for an ingredient (index into the returned
                           "ingredients" list), bypassing automatic matching. Lets
                           the user correct a wrong match and re-score.

        Returns
        -------
        {
          "ingredients": list of per-ingredient detail dicts,
          "nutrition":   per-serving totals dict,
          "risk":        risk scoring dict,
          "coverage":    float (0–100), % of ingredients successfully matched
        }
        """
        from scripts.cleaner import clean_ingredient
        from scoring.score_nutrition_risk import (
            classify_nutrient,
            weighted_score,
            weighted_risk_level,
            flag_count_risk_level,
        )

        # Guard: servings drives a per-serving division, so it must be >= 1.
        try:
            servings = max(1, int(servings))
        except (TypeError, ValueError):
            servings = 1

        # Guard: accept only a list of strings; ignore blanks/non-strings.
        if isinstance(ingredient_lines, str):
            ingredient_lines = ingredient_lines.splitlines()
        ingredient_lines = [ln for ln in (ingredient_lines or []) if isinstance(ln, str)]

        overrides = overrides or {}
        ingredients_detail = []
        totals = {col: 0.0 for col in NUTRIENT_IDS.values()}
        n_matched = 0
        ing_index = -1   # position in ingredients_detail (skips blank lines)

        for line in ingredient_lines:
            if not line.strip():
                continue
            ing_index += 1

            # ── Parse the line ────────────────────────────────────────────────
            parsed = parse_ingredient_line(line)

            # ── Clean the ingredient name ─────────────────────────────────────
            # clean_ingredient strips prep words ("minced", "chopped"),
            # brand names, etc. and handles African ingredient proxies.
            cleaned, tag, display = clean_ingredient(parsed["name_raw"])

            wafct_nutrients = None

            # ── User override: force a specific USDA food, skip auto-matching ──
            # Everything downstream (density, nutrient lookup, scoring) is shared.
            if ing_index in overrides and overrides[ing_index] is not None:
                fdc_id     = int(overrides[ing_index])
                food_name  = self._usda_index.describe(fdc_id) or f"USDA {fdc_id}"
                match_type = "user_override"
            else:
                # ── Match to USDA/WAFCT — three layers ───────────────────────
                # Layer 1: MANUAL_MAPPINGS + fuzzy pool (Matcher)
                food_name, fdc_id, match_type = self._matcher.match(cleaned)

                # Layer 2: if still no match, search food.csv directly.
                if fdc_id is None:
                    query_words = set(cleaned.lower().split())
                    usda_hit = self._usda_index.search(cleaned, query_words)
                    if usda_hit:
                        fdc_id, food_name = usda_hit
                        match_type = "usda_search"

                # Layer 3: if USDA still has nothing, try the West African Food
                # Composition Table (FAO/INFOODS WAFCT 2019). Covers African
                # staples absent from USDA: fufu, pounded yam, egusi, fonio, etc.
                # We also try name_raw because the cleaner proxy-substitutes some
                # African ingredients (fonio→millet); WAFCT has the real one.
                if fdc_id is None:
                    wafct_hit = self._wafct_index.search(cleaned)
                    if wafct_hit is None and parsed["name_raw"].lower() != cleaned.lower():
                        wafct_hit = self._wafct_index.search(parsed["name_raw"])
                    if wafct_hit:
                        wafct_code, food_name, wafct_nutrients = wafct_hit
                        fdc_id     = wafct_code
                        match_type = "wafct"

            # ── Ingredient-aware weight ───────────────────────────────────────
            # Now that we know which food this is, convert a VOLUME ("2 cups
            # flour") into a realistic weight using that food's density, instead
            # of the flat water-equivalent the parser assumed. Weight and count
            # units already have a real gram value and are left untouched.
            if parsed["volume_ml"] is not None:
                density = self._density_for(fdc_id, cleaned)
                parsed["grams"] = round(parsed["volume_ml"] * density, 1)

            detail = {
                "raw":          line.strip(),
                "name_raw":     parsed["name_raw"],
                "name_cleaned": cleaned,
                "qty":          parsed["qty"],
                "unit":         parsed["unit"],
                "grams":        parsed["grams"],
                "food_name":    food_name,
                "fdc_id":       fdc_id,
                "match_type":   match_type,
                "status":       None,       # filled in below
                "nutrition":    {},         # filled in below
            }

            # ── Guard: need grams and a valid USDA match ──────────────────────
            if parsed["grams"] is None or parsed["grams"] == 0:
                detail["status"] = "no_grams"
                ingredients_detail.append(detail)
                continue

            if fdc_id is None:
                detail["status"] = "no_usda_match"
                ingredients_detail.append(detail)
                continue

            # ── Nutrient lookup — USDA path or WAFCT path ────────────────────
            #
            # USDA stores nutrients by numeric ID (e.g. 208 = energy_kcal).
            # WAFCT returns a dict already keyed by our column names.
            # We resolve both paths to a common {col_name: value} dict.
            if wafct_nutrients is not None:
                # WAFCT match — nutrients already in our column-name format
                resolved_nutrients = wafct_nutrients
            else:
                # USDA match — look up by integer fdc_id, then map nutrient IDs
                try:
                    usda_data = self._food_nutrients.get(int(fdc_id))
                except (ValueError, TypeError):
                    usda_data = None
                if usda_data is None:
                    detail["status"] = "no_usda_data"
                    ingredients_detail.append(detail)
                    continue
                resolved_nutrients = {col: usda_data.get(nid, 0.0)
                                      for nid, col in NUTRIENT_IDS.items()}

            # ── Calculate nutrient contribution ───────────────────────────────
            grams_per_serving = parsed["grams"] / servings
            scale             = grams_per_serving / 100.0

            contrib: dict[str, float] = {}
            for col in NUTRIENT_IDS.values():
                value        = scale * resolved_nutrients.get(col, 0.0)
                contrib[col] = round(value, 2)
                totals[col] += value

            detail["status"]    = "matched"
            detail["nutrition"] = contrib
            n_matched += 1
            ingredients_detail.append(detail)

        # ── Per-serving totals (rounded) ──────────────────────────────────────
        per_serving = {k: round(v, 1) for k, v in totals.items()}

        # ── Coverage: how many ingredients contributed to the score ───────────
        total_lines = len([l for l in ingredient_lines if l.strip()])
        coverage    = round(n_matched / total_lines * 100, 1) if total_lines else 0.0

        # ── Risk scoring (same formulas as score_nutrition_risk.py) ───────────
        nutrients_for_scoring = {
            "energy_kcal": per_serving["energy_kcal"],
            "sodium_mg":   per_serving["sodium_mg"],
            "fat_g":       per_serving["fat_g"],
            "sugars_g":    per_serving["sugars_g"],
            "protein_g":   per_serving["protein_g"],
        }

        risk = {
            "energy_risk":  classify_nutrient("energy_kcal", nutrients_for_scoring["energy_kcal"]),
            "sodium_risk":  classify_nutrient("sodium_mg",   nutrients_for_scoring["sodium_mg"]),
            "fat_risk":     classify_nutrient("fat_g",       nutrients_for_scoring["fat_g"]),
            "sugar_risk":   classify_nutrient("sugars_g",    nutrients_for_scoring["sugars_g"]),
            "protein_risk": classify_nutrient("protein_g",   nutrients_for_scoring["protein_g"]),
        }

        flags          = sum(v == "high" for v in risk.values())
        w_score        = weighted_score(nutrients_for_scoring)
        risk["flag_count"]           = flags
        risk["flag_risk_level"]      = flag_count_risk_level(flags)
        risk["weighted_risk_score"]  = w_score
        risk["weighted_risk_level"]  = weighted_risk_level(w_score)

        return {
            "ingredients": ingredients_detail,
            "nutrition":   per_serving,
            "risk":        risk,
            "coverage":    coverage,
        }
