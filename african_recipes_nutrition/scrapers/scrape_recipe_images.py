"""
scrape_recipe_images.py
========================
One-time job: fetch a representative photo for every recipe in
recipes_clean.csv and commit it into the repo, so the Explore-recipes
card grid never depends on hotlinking the original source site.

For each recipe_url we try, in order:
  1. schema.org Recipe JSON-LD  "image" field   (most reliable — this is
     what Google itself uses for recipe rich snippets)
  2. <meta property="og:image">  /  <meta name="og:image">
  3. <meta name="twitter:image">

The downloaded image is saved as assets/photos/{recipe_id}.jpg and the
outcome for every recipe (including failures) is recorded in
assets/photos/manifest.csv so the dashboard can look up a recipe's photo
— or know there isn't one — without touching the network.

Resumable: recipes already present in manifest.csv are skipped, so a
run interrupted partway through can just be re-run.

Run from african_recipes_nutrition/:
    py scrapers/scrape_recipe_images.py
"""

import csv
import io
import json
import os
import re
import time

import requests
from PIL import Image

BASE         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_FILE = os.path.join(BASE, 'data', 'interim', 'recipes_clean.csv')
PHOTOS_DIR   = os.path.join(BASE, 'assets', 'photos')
MANIFEST     = os.path.join(PHOTOS_DIR, 'manifest.csv')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

REQUEST_DELAY  = 1.0     # seconds between page fetches — stay polite
MAX_IMAGE_SIDE = 800      # downscale large photos before committing to the repo
JPEG_QUALITY   = 82

JSONLD_RE  = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
OGIMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
OGIMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']', re.I
)
TWIMAGE_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', re.I
)


def _find_jsonld_image(html):
    for m in JSONLD_RE.finditer(html):
        try:
            data = json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            graph = item.get('@graph')
            nodes = graph if isinstance(graph, list) else [item]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get('@type') not in ('Recipe', ['Recipe']):
                    continue
                image = node.get('image')
                if isinstance(image, str):
                    return image
                if isinstance(image, list) and image:
                    first = image[0]
                    return first if isinstance(first, str) else first.get('url')
                if isinstance(image, dict):
                    return image.get('url')
    return None


def find_image_url(html):
    url = _find_jsonld_image(html)
    if url:
        return url
    m = OGIMAGE_RE.search(html) or OGIMAGE_RE2.search(html)
    if m:
        return m.group(1)
    m = TWIMAGE_RE.search(html)
    if m:
        return m.group(1)
    return None


def download_and_save(image_url, dest_path):
    resp = requests.get(image_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert('RGB')
    if max(img.size) > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    img.save(dest_path, 'JPEG', quality=JPEG_QUALITY)


def load_existing_manifest():
    if not os.path.exists(MANIFEST):
        return {}
    with open(MANIFEST, newline='', encoding='utf-8') as f:
        return {row['recipe_id']: row for row in csv.DictReader(f)}


def main():
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    import pandas as pd
    recipes = pd.read_csv(RECIPES_FILE)

    done = load_existing_manifest()
    fieldnames = ['recipe_id', 'recipe_name', 'local_path', 'source_url', 'status']
    write_header = not os.path.exists(MANIFEST)

    n_ok = n_skip = n_fail = n_nourl = 0

    with open(MANIFEST, 'a', newline='', encoding='utf-8') as mf:
        writer = csv.DictWriter(mf, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()

        for _, row in recipes.iterrows():
            recipe_id = str(row['recipe_id'])
            recipe_name = row['recipe_name']

            if recipe_id in done:
                n_skip += 1
                continue

            url = row.get('recipe_url')
            if not isinstance(url, str) or not url.strip():
                writer.writerow({
                    'recipe_id': recipe_id, 'recipe_name': recipe_name,
                    'local_path': '', 'source_url': '', 'status': 'no_url',
                })
                mf.flush()
                n_nourl += 1
                continue

            status, local_path = 'failed', ''
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                image_url = find_image_url(resp.text)
                if not image_url:
                    status = 'no_image_found'
                else:
                    filename = f"{recipe_id}.jpg"
                    dest = os.path.join(PHOTOS_DIR, filename)
                    download_and_save(image_url, dest)
                    local_path = f"assets/photos/{filename}"
                    status = 'ok'
                    n_ok += 1
            except Exception as e:
                status = f"error: {e}"[:200]
                n_fail += 1

            writer.writerow({
                'recipe_id': recipe_id, 'recipe_name': recipe_name,
                'local_path': local_path, 'source_url': url, 'status': status,
            })
            mf.flush()

            if status != 'no_url':
                time.sleep(REQUEST_DELAY)

            done_count = n_ok + n_fail + n_nourl
            if done_count % 25 == 0:
                print(f"...{done_count} processed (ok={n_ok}, failed={n_fail}, no_url={n_nourl})")

    print(f"Done. ok={n_ok}  failed={n_fail}  no_url={n_nourl}  already_done={n_skip}")


if __name__ == '__main__':
    main()
