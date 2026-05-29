"""
scrape_cheflola.py
==================
Scrapes the 44 cheflolaskitchen.com recipes that have only 1 ingredient
in the pipeline (recipe IDs 182-225).

The site uses WP Recipe Maker (WPRM), which stores each ingredient in
separate labelled spans — amount, unit, name, notes — inside:
  <li class="wprm-recipe-ingredient">

Selectors used:
  li.wprm-recipe-ingredient         → one ingredient row
  span.wprm-recipe-ingredient-amount → quantity  e.g. "2", "½", "14-16"
  span.wprm-recipe-ingredient-unit   → unit      e.g. "cups", "tablespoon"
  span.wprm-recipe-ingredient-name   → name      e.g. "flour", "onion"
  span.wprm-recipe-ingredient-notes  → notes     e.g. "drained", "optional"
  span.wprm-recipe-servings          → servings count

Output: cheflola_scraped.csv  (same format as african_recipes_dataset.csv
        but with an extra recipe_id column for direct pipeline mapping)

Run from african_recipes_nutrition/:
    py scrape_cheflola.py
"""

import csv
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE, 'data', 'scraped', 'cheflola_scraped.csv')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0 Safari/537.36'
    )
}

COOKING_METHODS = [
    'boil', 'bake', 'fry', 'deep fry', 'deep-fry', 'steam', 'grill',
    'roast', 'simmer', 'stew', 'poach', 'braise', 'smoke', 'toast',
    'saute', 'sauté', 'microwave', 'pressure cook', 'slow cook',
    'blend', 'marinate', 'broil', 'knead', 'stir-fry',
]

# Unicode fraction characters → ASCII equivalents
UNICODE_FRACTIONS = {
    '¼': '1/4', '½': '1/2', '¾': '3/4',
    '⅓': '1/3', '⅔': '2/3', '⅛': '1/8',
    '⅜': '3/8', '⅝': '5/8', '⅞': '7/8',
}

# Recipes to scrape: id → url
RECIPES = {
    '182': 'https://cheflolaskitchen.com/african-fish-pastry/',
    '183': 'https://cheflolaskitchen.com/african-masa-recipe-hausa-masa/',
    '184': 'https://cheflolaskitchen.com/african-pancakes/',
    '185': 'https://cheflolaskitchen.com/african-spaghetti-sauce-with-meatballs/',
    '186': 'https://cheflolaskitchen.com/african-stew/',
    '187': 'https://cheflolaskitchen.com/african-style-coconut-rice/',
    '188': 'https://cheflolaskitchen.com/amala-recipe/',
    '189': 'https://cheflolaskitchen.com/basmati-jollof-rice-recipe/',
    '190': 'https://cheflolaskitchen.com/berbere-spice/',
    '191': 'https://cheflolaskitchen.com/black-eyed-peas-and-beef/',
    '192': 'https://cheflolaskitchen.com/chakalaka/',
    '193': 'https://cheflolaskitchen.com/chicken-samosa/',
    '194': 'https://cheflolaskitchen.com/coconut-fried-rice/',
    '195': 'https://cheflolaskitchen.com/creamy-fonio-porridge/',
    '196': 'https://cheflolaskitchen.com/creamy-polenta-recipe/',
    '197': 'https://cheflolaskitchen.com/crispy-yuca-fries/',
    '198': 'https://cheflolaskitchen.com/delicious-homemade-sweet-potato-pie/',
    '199': 'https://cheflolaskitchen.com/easy-chicken-peanut-soup/',
    '200': 'https://cheflolaskitchen.com/eggless-nigerian-buns/',
    '201': 'https://cheflolaskitchen.com/fried-plantains/',
    '202': 'https://cheflolaskitchen.com/gbegiri-soup/',
    '203': 'https://cheflolaskitchen.com/grilled-corn-on-the-cob/',
    '204': 'https://cheflolaskitchen.com/grilled-plantains/',
    '205': 'https://cheflolaskitchen.com/harissa-chicken/',
    '206': 'https://cheflolaskitchen.com/how-to-cook-a-super-juicy-turkey/',
    '207': 'https://cheflolaskitchen.com/how-to-make-eba/',
    '208': 'https://cheflolaskitchen.com/ikokore/',
    '209': 'https://cheflolaskitchen.com/indulgent-homemade-pumpkin-pie/',
    '210': 'https://cheflolaskitchen.com/jollof-spaghetti-recipe/',
    '211': 'https://cheflolaskitchen.com/jute-leaves-soup-ewedu-mulukhiyah-or-molokhia/',
    '212': 'https://cheflolaskitchen.com/make-moin-moin-moi-moi/',
    '213': 'https://cheflolaskitchen.com/meat-floss/',
    '214': 'https://cheflolaskitchen.com/nigerian-recipes-you-need-to-try/',
    '215': 'https://cheflolaskitchen.com/niter-kibbeh-ethiopian-clarified-butter/',
    '216': 'https://cheflolaskitchen.com/nyama-choma/',
    '217': 'https://cheflolaskitchen.com/oven-roasted-turkey-breast/',
    '218': 'https://cheflolaskitchen.com/peri-peri-chicken/',
    '219': 'https://cheflolaskitchen.com/peri-peri-sauce/',
    '220': 'https://cheflolaskitchen.com/semolina-flour-masa/',
    '221': 'https://cheflolaskitchen.com/stick-meat/',
    '222': 'https://cheflolaskitchen.com/suya/',
    '223': 'https://cheflolaskitchen.com/sweet-potato-kale-salad/',
    '224': 'https://cheflolaskitchen.com/tropical-mango-pineapple-smoothie/',
    '225': 'https://cheflolaskitchen.com/yam-porridge-pottage/',
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


def scrape_recipe(recipe_id, url):
    """
    Fetch one cheflolaskitchen.com page and extract ingredients + servings.
    Returns a dict ready for the output CSV, or None on failure.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f'  HTTP {resp.status_code}')
            return None

        soup = BeautifulSoup(resp.text, 'lxml')

        # ── Title ──────────────────────────────────────────────────────────────
        title_tag = soup.find('h2', class_='wprm-recipe-name') or soup.find('h1')
        title = title_tag.get_text(' ', strip=True) if title_tag else ''

        # ── Servings ───────────────────────────────────────────────────────────
        serv_tag = soup.find('span', class_='wprm-recipe-servings')
        servings = serv_tag.get_text(strip=True) if serv_tag else ''
        if not servings:
            # Fallback: look for "Servings:" text
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
            unit_text   = unit.get_text(strip=True)   if unit   else ''
            name_text   = name.get_text(strip=True)   if name   else ''
            notes_text  = notes.get_text(strip=True)  if notes  else ''

            # Skip rows with no name
            if not name_text:
                continue

            # Build a single ingredient string: "2 tablespoon butter or margarine"
            parts = [p for p in [amount_text, unit_text, name_text, notes_text] if p]
            ingredients.append(' '.join(parts))

        if not ingredients:
            print(f'  No WPRM ingredients found — page may be a roundup or lacks a recipe card')
            return None

        # ── Instructions → cooking methods ────────────────────────────────────
        instruction_text = ''
        for step in soup.select('div.wprm-recipe-instruction-text'):
            instruction_text += ' ' + step.get_text(' ', strip=True)

        cooking_methods = extract_cooking_methods(instruction_text)

        return {
            'recipe_id'     : recipe_id,
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
    print('Chef Lola\'s Kitchen — Scrape 44 Recipes')
    print('=' * 44)

    results  = []
    failed   = []

    for i, (recipe_id, url) in enumerate(RECIPES.items(), start=1):
        print(f'[{i:>2}/{len(RECIPES)}] ID {recipe_id}  {url}')
        data = scrape_recipe(recipe_id, url)
        if data:
            n_ing = len(data['ingredients'].split(' | '))
            print(f'        {data["recipe_title"][:50]}  ->  {n_ing} ingredients, {data["servings"]} servings')
            results.append(data)
        else:
            print(f'        FAILED — will be skipped')
            failed.append(recipe_id)

        time.sleep(2)   # polite crawl delay

    # Write CSV
    fieldnames = ['recipe_id', 'recipe_title', 'servings', 'ingredients', 'cooking_methods', 'source_url']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print()
    print('=' * 44)
    print(f'Scraped successfully : {len(results)}')
    print(f'Failed / no recipe  : {len(failed)}  {failed}')
    print(f'Saved to            : {OUTPUT_FILE}')
    print()
    print('Next step: run integrate_cheflola.py to push these into the pipeline.')


if __name__ == '__main__':
    main()
