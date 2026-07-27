"""
Tests for ingredient-aware volume->weight conversion (Phase 1.3).

Covers the density-resolution priority (real USDA density -> category fallback
-> water) and the end-to-end effect on analyse(): a cup of flour must weigh far
less than a cup of water.

Run from african_recipes_nutrition/:
    py -m pytest tests/test_density.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pipeline.live_analysis import LiveAnalyser


@pytest.fixture(scope="module")
def analyser():
    """One LiveAnalyser for the whole module (loading USDA data is ~3s)."""
    return LiveAnalyser()


# ─────────────────────────────────────────────────────────────────────────────
# _density_for — resolution priority
# ─────────────────────────────────────────────────────────────────────────────
def test_real_usda_density_used_when_available(analyser):
    # Pick any fdc_id that actually has a derived density and confirm it wins.
    fdc_id, g_per_ml = next(iter(analyser._density.items()))
    assert analyser._density_for(fdc_id, "anything") == pytest.approx(g_per_ml)


def test_category_fallback_for_unknown_food(analyser):
    # fdc_id not in the density table -> category keyword decides.
    assert analyser._density_for(None, "cassava flour")   == pytest.approx(0.53)
    assert analyser._density_for(None, "palm oil")        == pytest.approx(0.91)
    assert analyser._density_for(None, "granulated sugar") == pytest.approx(0.85)
    assert analyser._density_for(None, "chopped spinach") == pytest.approx(0.20)
    assert analyser._density_for(None, "raw honey")       == pytest.approx(1.42)


def test_water_default_when_no_category_matches(analyser):
    assert analyser._density_for(None, "zxqw nonsense") == pytest.approx(1.0)


def test_wafct_string_code_skips_to_category(analyser):
    # WAFCT codes are non-integer, so int() fails and we fall to category.
    assert analyser._density_for("WA0123", "maize flour") == pytest.approx(0.53)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end effect on analyse()
# ─────────────────────────────────────────────────────────────────────────────
def _grams(analyser, line):
    return analyser.analyse([line], 1)["ingredients"][0]["grams"]


def test_flour_weighs_less_than_water(analyser):
    # A cup of flour must be much lighter than the 240 g water-equivalent.
    flour_g = _grams(analyser, "1 cup flour")
    assert flour_g is not None
    assert flour_g < 200


def test_weight_units_unaffected_by_density(analyser):
    # Grams in -> grams out, regardless of the food's density.
    assert _grams(analyser, "500g flour") == pytest.approx(500.0)


def test_count_units_unaffected_by_density(analyser):
    assert _grams(analyser, "3 cloves garlic") == pytest.approx(12.0)
