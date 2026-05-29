"""
scrape_africanbites.py
======================
Scrapes African recipe pages from africanbites.com using the list of URLs
previously collected by collect_urls.py (africanbites_urls.txt).

africanbites.com uses WP Recipe Maker (WPRM) — the same plugin as
cheflolaskitchen.com — so the same selectors apply:

  li.wprm-recipe-ingredient          → one ingredient row
  span.wprm-recipe-ingredient-amount → quantity   e.g. "2", "1/2"
  span.wprm-recipe-ingredient-unit   → unit       e.g. "cups", "tbsp"
  span.wprm-recipe-ingredient-name   → name       e.g. "palm oil"
  span.wprm-recipe-ingredient-notes  → notes      e.g. "drained"
  span.wprm-recipe-servings          → servings count
  h2.wprm-recipe-name                → recipe title (falls back to h1)

Output: data/scraped/africanbites_scraped.csv
  columns: recipe_title, servings, ingredients, cooking_methods, source_url

Run from african_recipes_nutrition/:
    py scrapers/scrape_africanbites.py
"""

import csv
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URLS_FILE   = os.path.join(BASE, 'scrapers', 'africanbites_urls.txt')
OUTPUT_FILE = os.path.join(BASE, 'data', 'scraped', 'africanbites_scraped.csv')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.africanbites.com/',
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


def scrape_recipe(url, session):
    """
    Fetch one africanbites.com page and extract recipe data via WPRM selectors.
    Returns a dict ready for the output CSV, or None on failure.
    """
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            print(f'  HTTP {resp.status_code}')
            return None

        soup = BeautifulSoup(resp.text, 'lxml')

        # ── Title ──────────────────────────────────────────────────────────────
        title_tag = (
            soup.find('h2', class_='wprm-recipe-name')
            or soup.find('h1', class_='wprm-recipe-name')
            or soup.find('h1')
        )
        title = title_tag.get_text(' ', strip=True) if title_tag else ''

        # ── Servings ───────────────────────────────────────────────────────────
        serv_tag = soup.find('span', class_='wprm-recipe-servings')
        servings = serv_tag.get_text(strip=True) if serv_tag else ''
        if not servings:
            m = re.search(r'(\d+)\s+servings?', resp.text, re.IGNORECASE)
            servings = m.group(1) if m else ''

        # ── Ingredients ────────────────────────────────────────────────────────
        ingredients = []
        for li in soup.select('li.wprm-recipe-ingredient'):
            amount = li.find('span', class_='wprm-recipe-ingredient-amount')
            unit   = li.find('span', class_='wprm-recipe-ingredient-unit')
            name   = li.find('span', class_='wprm-recipe-ingredient-name')
            notes  = li.find('span', class_='wprm-recipe-ingredient-notes')

            amount_text = normalize_fractions(amount.get_text(strip=True)) if amount else ''
            unit_text   = unit.get_text(strip=True)  if unit  else ''
            name_text   = name.get_text(strip=True)  if name  else ''
            notes_text  = notes.get_text(strip=True) if notes else ''

            if not name_text:
                continue

            parts = [p for p in [amount_text, unit_text, name_text, notes_text] if p]
            ingredients.append(' '.join(parts))

        if not ingredients:
            print('  No WPRM ingredients — skipping (roundup or non-recipe page)')
            return None

        # ── Instructions → cooking methods ────────────────────────────────────
        instruction_text = ' '.join(
            div.get_text(' ', strip=True)
            for div in soup.select('div.wprm-recipe-instruction-text')
        )
        cooking_methods = extract_cooking_methods(instruction_text)

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
    # Load URL list
    with open(URLS_FILE, encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f'AfricanBites Scraper — {len(urls)} URLs')
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

    # Write CSV
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
        print('\nFailed URLs:')
        for u in failed:
            print(f'  {u}')


if __name__ == '__main__':
    main()
