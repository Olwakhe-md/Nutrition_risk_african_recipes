"""
Tests for recipe URL import (Phase 2A). The HTML parsing is pure and tested on
inline samples; URL validation is tested without hitting the network.

Run from african_recipes_nutrition/:
    py -m pytest tests/test_url_import.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pipeline.recipe_url_import import (
    extract_ingredients_from_html,
    fetch_ingredients,
    RecipeImportError,
)


JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Test Jollof",
 "recipeYield":"4 servings",
 "recipeIngredient":["2 cups rice","1 tbsp palm oil","2 tsp salt"]}
</script>
</head><body>...</body></html>
"""

JSONLD_GRAPH_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebPage","name":"blog"},
  {"@type":["Recipe"],"name":"Graph Recipe","recipeYield":[6],
   "recipeIngredient":["500g beef","<span>1 onion</span>"]}
]}
</script>
</head><body>...</body></html>
"""

WPRM_PAGE = """
<html><body>
<h2 class="wprm-recipe-name">WPRM Dish</h2>
<ul>
  <li class="wprm-recipe-ingredient">3 ripe plantains</li>
  <li class="wprm-recipe-ingredient">1/2 cup palm oil</li>
</ul>
</body></html>
"""

NO_RECIPE_PAGE = "<html><body><p>Just a blog post, no recipe.</p></body></html>"


# ─────────────────────────────────────────────────────────────────────────────
# JSON-LD extraction
# ─────────────────────────────────────────────────────────────────────────────
def test_jsonld_basic():
    r = extract_ingredients_from_html(JSONLD_PAGE)
    assert r["source"] == "json-ld"
    assert r["ingredients"] == ["2 cups rice", "1 tbsp palm oil", "2 tsp salt"]
    assert r["title"] == "Test Jollof"
    assert r["servings"] == 4


def test_jsonld_graph_and_html_is_stripped():
    r = extract_ingredients_from_html(JSONLD_GRAPH_PAGE)
    assert r["ingredients"] == ["500g beef", "1 onion"]   # <span> stripped
    assert r["title"] == "Graph Recipe"
    assert r["servings"] == 6


# ─────────────────────────────────────────────────────────────────────────────
# Fallback markup + failure
# ─────────────────────────────────────────────────────────────────────────────
def test_wprm_fallback_when_no_jsonld():
    r = extract_ingredients_from_html(WPRM_PAGE)
    assert r["source"] == "wprm"
    assert r["ingredients"] == ["3 ripe plantains", "1/2 cup palm oil"]
    assert r["title"] == "WPRM Dish"


def test_no_recipe_raises():
    with pytest.raises(RecipeImportError):
        extract_ingredients_from_html(NO_RECIPE_PAGE)


# ─────────────────────────────────────────────────────────────────────────────
# URL validation / SSRF guards (no network for the rejects)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "",                                        # empty
    "http://localhost:8501/",                  # loopback
    "http://127.0.0.1/",                       # loopback
    "http://169.254.169.254/latest/meta-data", # cloud metadata
    "http://192.168.1.1/",                     # private
])
def test_fetch_rejects_bad_or_private_urls(url):
    with pytest.raises(RecipeImportError):
        fetch_ingredients(url)
