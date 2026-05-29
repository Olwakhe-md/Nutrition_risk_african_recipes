"""
collect_urls.py
===============
Collects recipe URLs from africanbites.com and food.com and saves
them to text files for use by the scrapers.

africanbites.com  — paginates /category/african-recipes/
food.com          — filters all 5 gzipped sitemaps by African keywords

Run from african_recipes_nutrition/:
    py scrapers/collect_urls.py
"""

import gzip
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRAPERS_DIR = os.path.join(BASE, 'scrapers')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}

# ── African-specific keywords for food.com URL filtering ──────────────────────
# These match recipe URL slugs — intentionally specific to avoid false positives
FOOD_COM_AFRICAN_KW = [
    'african', 'nigerian', 'nigeri', 'ethiopian', 'moroccan', 'ghanaian',
    'kenyan', 'senegalese', 'senegal', 'liberian', 'rwandan', 'cameroonian',
    'ugandan', 'tanzanian', 'somali', 'sudanese', 'ivorian', 'congolese',
    'mozambican', 'zimbabwean', 'zambian',
    'jollof', 'egusi', 'fufu', 'injera', 'tagine', 'suya', 'peri-peri',
    'piri-piri', 'bobotie', 'bunny-chow', 'biltong', 'chakalaka', 'vetkoek',
    'moin-moin', 'moimoi', 'akara', 'puff-puff', 'ogbono', 'oha',
    'jolof', 'kenkey', 'kelewele', 'waakye',
    'berbere', 'doro-wat', 'kitfo', 'tibs',
    'shakshuka', 'harissa', 'ras-el-hanout', 'bastilla', 'kefta',
    'nyama-choma', 'ugali', 'sukuma', 'matoke',
    'sadza', 'nshima',
    'maafe', 'thieboudienne', 'thiebou', 'yassa', 'mafe',
    'couscous', 'merguez', 'briouat', 'chermoula', 'zaalouk',
    'groundnut-soup', 'peanut-soup', 'egusi-soup', 'okra-soup',
    'plantain-stew', 'plantain-porridge',
]


# ── Africanbites.com URL collection ──────────────────────────────────────────

def collect_africanbites_urls():
    """
    Paginates /category/african-recipes/ and returns a list of recipe URLs.
    """
    base_cat = 'https://www.africanbites.com/category/african-recipes/'
    all_urls = set()
    page = 1

    print('Collecting africanbites.com URLs...')
    while True:
        url = base_cat if page == 1 else f'{base_cat}page/{page}/'
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except Exception as e:
            print(f'  Page {page}: request error — {e}')
            break

        if r.status_code == 404:
            print(f'  Page {page}: 404 — end of pages')
            break
        if r.status_code != 200:
            print(f'  Page {page}: HTTP {r.status_code} — stopping')
            break

        soup = BeautifulSoup(r.text, 'lxml')

        # Article links: depth-4 URLs (https://domain/slug/)
        new = set()
        for a in soup.select('article a[href*="africanbites.com"]'):
            href = a.get('href', '')
            if href.count('/') == 4 and not any(
                x in href for x in ['/category/', '/tag/', '/author/', '/page/']
            ):
                new.add(href)

        if not new:
            print(f'  Page {page}: no new links — stopping')
            break

        all_urls |= new
        print(f'  Page {page}: {len(new)} links  |  running total: {len(all_urls)}')
        page += 1
        time.sleep(1)

    return sorted(all_urls)


# ── food.com URL collection ───────────────────────────────────────────────────

def collect_food_com_urls():
    """
    Downloads and filters all 5 gzipped food.com sitemaps.
    Returns URLs whose slug contains at least one African keyword.
    """
    all_urls = set()
    print('\nCollecting food.com URLs from sitemaps...')

    for i in range(1, 6):
        sitemap_url = f'https://www.food.com/sitemap-{i}.xml.gz'
        try:
            r = requests.get(sitemap_url, headers=HEADERS, timeout=60, stream=True)
            if r.status_code != 200:
                print(f'  sitemap-{i}: HTTP {r.status_code}')
                continue
            xml    = gzip.decompress(r.content).decode('utf-8')
            urls   = re.findall(r'<loc>(https://www\.food\.com/recipe/[^<]+)</loc>', xml)
            african = [u for u in urls if any(kw in u.lower() for kw in FOOD_COM_AFRICAN_KW)]
            all_urls.update(african)
            print(f'  sitemap-{i}: {len(urls):>6} total  |  {len(african):>4} African matches')
        except Exception as e:
            print(f'  sitemap-{i}: error — {e}')

    return sorted(all_urls)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('African Recipes — URL Collector')
    print('=' * 40)

    # africanbites
    ab_urls = collect_africanbites_urls()
    ab_path = os.path.join(SCRAPERS_DIR, 'africanbites_urls.txt')
    with open(ab_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ab_urls))
    print(f'\nAfricanbites: {len(ab_urls)} URLs saved to {ab_path}')

    # food.com
    fc_urls = collect_food_com_urls()
    fc_path = os.path.join(SCRAPERS_DIR, 'food_com_urls.txt')
    with open(fc_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fc_urls))
    print(f'food.com:     {len(fc_urls)} URLs saved to {fc_path}')

    print(f'\nTotal URLs collected: {len(ab_urls) + len(fc_urls)}')


if __name__ == '__main__':
    main()
