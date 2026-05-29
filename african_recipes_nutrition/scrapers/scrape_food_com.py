"""
scrape_food_com.py
==================
Scrapes African recipe pages from food.com using the list of URLs
previously collected by collect_urls.py (food_com_urls.txt).

food.com embeds recipe data as JSON-LD structured data
(<script type="application/ld+json">) using the schema.org/Recipe format.
This is more reliable than CSS selectors because it is the canonical
machine-readable data the site exposes for SEO.

Fields extracted from the JSON-LD:
  name              → recipe_title
  recipeYield       → servings  (e.g. "6 servings" → "6")
  recipeIngredient  → list of ingredient strings
  recipeInstructions → list of step objects or plain strings
                       used only to detect cooking methods

Output: data/scraped/food_com_scraped.csv
  columns: recipe_title, servings, ingredients, cooking_methods, source_url

Run from african_recipes_nutrition/:
    py scrapers/scrape_food_com.py
"""

import csv
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URLS_FILE   = os.path.join(BASE, 'scrapers', 'food_com_urls.txt')
OUTPUT_FILE = os.path.join(BASE, 'data', 'scraped', 'food_com_scraped.csv')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

COOKING_METHODS = [
    'boil', 'bake', 'fry', 'deep fry', 'deep-fry', 'steam', 'grill',
    'roast', 'simmer', 'stew', 'poach', 'braise', 'smoke', 'toast',
    'saute', 'sauté', 'microwave', 'pressure cook', 'slow cook',
    'blend', 'marinate', 'broil', 'knead', 'stir-fry',
]

UNICODE_FRACTIONS = {
    '¼': '1/4', '½': '1/2', '¾': '3/4',
    '⅓': '1/3', '⅔': '2/3', '⅛': '1/8',
    '⅜': '3/8', '⅝': '5/8', '⅞': '7/8',
}


def normalize_fractions(text):
    for uc, asc in UNICODE_FRACTIONS.items():
        text = text.replace(uc, asc)
    return text


def extract_cooking_methods(text):
    found = set()
    lower = text.lower()
    for method in COOKING_METHODS:
        if method in lower:
            found.add(method)
    return ', '.join(sorted(found))


def find_recipe_jsonld(soup):
    """
    Search all <script type="application/ld+json"> blocks for a
    schema.org/Recipe object. Returns the dict or None.
    """
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both bare objects and @graph arrays
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            if '@graph' in data:
                candidates = data['@graph']
            else:
                candidates = [data]

        for obj in candidates:
            type_val = obj.get('@type', '')
            types = type_val if isinstance(type_val, list) else [type_val]
            if 'Recipe' in types:
                return obj

    return None


def parse_servings(yield_val):
    """
    recipeYield can be a string like "6 servings", a plain int, or a list.
    Return just the numeric part as a string.
    """
    if isinstance(yield_val, list):
        yield_val = yield_val[0] if yield_val else ''
    text = str(yield_val)
    m = re.search(r'\d+', text)
    return m.group(0) if m else text.strip()


def parse_instructions(instructions_val):
    """
    recipeInstructions can be:
      - a plain string
      - a list of strings
      - a list of HowToStep dicts  {"@type": "HowToStep", "text": "..."}
      - a list of HowToSection dicts with nested itemListElement
    Returns a single concatenated string for cooking-method detection.
    """
    if not instructions_val:
        return ''
    if isinstance(instructions_val, str):
        return instructions_val

    parts = []
    for item in instructions_val:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            if item.get('@type') == 'HowToSection':
                for step in item.get('itemListElement', []):
                    parts.append(step.get('text', ''))
            else:
                parts.append(item.get('text', ''))
    return ' '.join(parts)


def scrape_recipe(url, session):
    """
    Fetch one food.com page, extract the JSON-LD recipe block, and return
    a row dict for the output CSV. Returns None on failure.
    """
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            print(f'  HTTP {resp.status_code}')
            return None

        soup = BeautifulSoup(resp.text, 'lxml')
        recipe = find_recipe_jsonld(soup)

        if not recipe:
            print('  No JSON-LD Recipe block found — skipping')
            return None

        # ── Title ──────────────────────────────────────────────────────────────
        title = str(recipe.get('name', '')).strip()

        # ── Servings ───────────────────────────────────────────────────────────
        servings = parse_servings(recipe.get('recipeYield', ''))

        # ── Ingredients ────────────────────────────────────────────────────────
        raw_ingredients = recipe.get('recipeIngredient', [])
        if not raw_ingredients:
            print('  Empty ingredient list — skipping')
            return None

        ingredients = [
            normalize_fractions(re.sub(r'\s+', ' ', str(ing).strip()))
            for ing in raw_ingredients
            if str(ing).strip()
        ]

        # ── Cooking methods ────────────────────────────────────────────────────
        instruction_text = parse_instructions(recipe.get('recipeInstructions', ''))
        cooking_methods  = extract_cooking_methods(instruction_text)

        return {
            'recipe_title'  : title,
            'servings'      : servings,
            'ingredients'   : ' | '.join(ingredients),
            'cooking_methods': cooking_methods,
            'source_url'    : url,
        }

    except Exception as exc:
        print(f'  Error: {exc}')
        return None


def main():
    with open(URLS_FILE, encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f'Food.com Scraper — {len(urls)} URLs')
    print('=' * 50)

    results = []
    failed  = []

    session = requests.Session()
    session.headers.update(HEADERS)

    for i, url in enumerate(urls, start=1):
        slug = url.rstrip('/').split('/')[-1]
        print(f'[{i:>3}/{len(urls)}] {slug}')
        data = scrape_recipe(url, session)
        if data:
            n_ing = len(data['ingredients'].split(' | '))
            print(f'         {data["recipe_title"][:55]}  ->  {n_ing} ingredients')
            results.append(data)
        else:
            failed.append(url)

        time.sleep(1.5)

    fieldnames = ['recipe_title', 'servings', 'ingredients', 'cooking_methods', 'source_url']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print()
    print('=' * 50)
    print(f'Scraped successfully : {len(results)}')
    print(f'Failed / no recipe  : {len(failed)}')
    print(f'Saved to            : {OUTPUT_FILE}')
    if failed:
        failed_path = os.path.join(BASE, 'scrapers', 'food_com_failed.txt')
        with open(failed_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(failed))
        print(f'Failed URLs written : {failed_path}')


if __name__ == '__main__':
    main()
