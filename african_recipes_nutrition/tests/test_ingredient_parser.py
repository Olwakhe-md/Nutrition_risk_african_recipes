"""
Unit tests for parse_ingredient_line — the riskiest, most format-sensitive
code in the pipeline. These lock the parsing contract (quantity / unit / name
extraction) so future changes to the gram-conversion logic can't silently
regress how ingredient lines are read.

Run from african_recipes_nutrition/:
    py -m pytest tests/test_ingredient_parser.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pipeline.live_analysis import parse_ingredient_line


# ─────────────────────────────────────────────────────────────────────────────
# Quantity extraction
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line, expected_qty", [
    ("2 cups rice",        2.0),
    ("500g chicken",       500.0),
    ("3.5 cups water",     3.5),
    ("1/2 cup oil",        0.5),
    ("2 1/2 cups water",   2.5),
    ("2½ cups flour",      2.5),   # unicode fraction glued to a whole number
    ("½ cup sugar",        0.5),   # standalone unicode fraction
    ("1 onion",            1.0),
    ("salt to taste",      0.0),   # no quantity at all
    ("",                   0.0),
])
def test_quantity(line, expected_qty):
    assert parse_ingredient_line(line)["qty"] == pytest.approx(expected_qty)


# ─────────────────────────────────────────────────────────────────────────────
# Unit extraction
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line, expected_unit", [
    ("2 cups rice",        "cups"),
    ("500g chicken",       "g"),
    ("1 kg beef",          "kg"),
    ("1 tbsp palm oil",    "tbsp"),
    ("1 tsp curry powder", "tsp"),
    ("3 cloves garlic",    "cloves"),
    ("6 garlic cloves",    "cloves"),   # trailing count unit
    ("1 can tomatoes",     "can"),
    ("Pinch of cayenne",   "pinch"),    # unit with no leading number
    ("1 onion, chopped",   ""),         # bare count, no unit
])
def test_unit(line, expected_unit):
    assert parse_ingredient_line(line)["unit"] == expected_unit


# ─────────────────────────────────────────────────────────────────────────────
# Name cleaning
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line, expected_name", [
    ("2 cups rice",                     "rice"),
    ("500g chicken thighs",             "chicken thighs"),
    ("1 onion, chopped",                "onion"),          # comma prep-note stripped
    ("parsley or cilantro",             "parsley"),        # 'or' alternative -> first
    ("cayenne (optional)",              "cayenne"),        # parenthetical stripped
    ("Pinch of cayenne",                "cayenne"),        # leading 'of' stripped
    ("6 garlic cloves",                 "garlic"),         # trailing unit removed
    ("15 oz can of cannellini beans",   "can of cannellini beans"),  # 'oz' taken as unit; 'can of' kept
])
def test_name(line, expected_name):
    assert parse_ingredient_line(line)["name_raw"] == expected_name


# ─────────────────────────────────────────────────────────────────────────────
# Gram conversion — density-independent cases only (weight units, counts, water).
# Volumetric non-water cases (flour, oil, rice) are covered separately once the
# ingredient-aware density conversion lands, since those values change by design.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line, expected_grams", [
    ("500g chicken",     500.0),    # weight unit — density irrelevant
    ("1 kg beef",        1000.0),
    ("2 oz butter",      56.7),
    ("3 cloves garlic",  12.0),     # count unit
    ("1 can tomatoes",   400.0),
    ("1 onion",          150.0),    # bare count fallback
    ("2 cups water",     480.0),    # water: density 1.0, unchanged
])
def test_grams_density_independent(line, expected_grams):
    assert parse_ingredient_line(line)["grams"] == pytest.approx(expected_grams)


# ─────────────────────────────────────────────────────────────────────────────
# Robustness — parser must never raise on messy input
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line", [
    "", "   ", "!!!", "12345", "a lot of salt", "🌶️ pepper", "1/0 cup broken",
])
def test_no_crash_on_garbage(line):
    result = parse_ingredient_line(line)
    assert set(result) == {"raw", "qty", "unit", "volume_ml", "name_raw", "grams"}
