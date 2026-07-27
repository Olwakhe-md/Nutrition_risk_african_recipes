"""
Tests for editable-match support (Phase 2B): candidate search, per-ingredient
overrides in analyse(), and the confidence helper.

Run from african_recipes_nutrition/:
    py -m pytest tests/test_matches.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pipeline.live_analysis import LiveAnalyser, match_confidence


@pytest.fixture(scope="module")
def analyser():
    return LiveAnalyser()


# ─────────────────────────────────────────────────────────────────────────────
# match_confidence — pure mapping, no data needed
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("match_type, expected", [
    ("manual_match",  "high"),
    ("user_override", "custom"),
    ("usda_search",   "medium"),
    ("wafct",         "medium"),
    ("fuzzy_90%",     "medium"),
    ("fuzzy_70%",     "low"),
    ("no_match",      "none"),
    (None,            "none"),
])
def test_match_confidence(match_type, expected):
    assert match_confidence(match_type) == expected


# ─────────────────────────────────────────────────────────────────────────────
# search_candidates
# ─────────────────────────────────────────────────────────────────────────────
def test_candidates_returns_relevant_ranked_list(analyser):
    cands = analyser._usda_index.search_candidates("rice", n=5)
    assert 1 <= len(cands) <= 5
    # every candidate description should mention the query word
    assert all("rice" in desc.lower() for _, desc in cands)
    # a simple cooked-rice food should surface near the top, not only compounds
    assert any("rice" in desc.lower() and "," in desc for _, desc in cands)


def test_candidates_empty_for_nonsense(analyser):
    assert analyser._usda_index.search_candidates("zzxqwv", n=5) == []


def test_describe_roundtrips(analyser):
    fdc_id, desc = analyser._usda_index.search_candidates("rice", 1)[0]
    assert analyser._usda_index.describe(fdc_id) == desc


# ─────────────────────────────────────────────────────────────────────────────
# analyse() overrides
# ─────────────────────────────────────────────────────────────────────────────
def test_override_changes_the_matched_food(analyser):
    baseline = analyser.analyse(["2 cups rice"], 1)
    original_fdc = baseline["ingredients"][0]["fdc_id"]

    # pick a different rice candidate and force it
    candidates = analyser._usda_index.search_candidates("rice", 5)
    alt = next(fid for fid, _ in candidates if fid != original_fdc)

    overridden = analyser.analyse(["2 cups rice"], 1, overrides={0: alt})
    ing = overridden["ingredients"][0]
    assert ing["fdc_id"] == alt
    assert ing["match_type"] == "user_override"
    assert ing["status"] == "matched"


def test_override_index_targets_the_right_ingredient(analyser):
    lines = ["2 cups rice", "1 tbsp palm oil"]
    alt = analyser._usda_index.search_candidates("oil", 3)[0][0]
    result = analyser.analyse(lines, 1, overrides={1: alt})
    assert result["ingredients"][1]["fdc_id"] == alt
    assert result["ingredients"][1]["match_type"] == "user_override"
    # first ingredient untouched
    assert result["ingredients"][0]["match_type"] != "user_override"


def test_empty_overrides_is_noop(analyser):
    a = analyser.analyse(["2 cups rice"], 1)
    b = analyser.analyse(["2 cups rice"], 1, overrides={})
    assert a["ingredients"][0]["fdc_id"] == b["ingredients"][0]["fdc_id"]
