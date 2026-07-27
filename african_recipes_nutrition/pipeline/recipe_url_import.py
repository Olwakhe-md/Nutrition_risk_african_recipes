"""
recipe_url_import.py
====================
Import a recipe's ingredient list from any recipe URL, so the user doesn't have
to retype it into the analyser.

Strategy (most universal first):
  1. schema.org/Recipe JSON-LD  — the structured data Google reads for recipe
     rich-cards. Present on the majority of modern recipe sites, so this alone
     covers most URLs, not just the handful we scraped for the dataset.
  2. WPRM / microdata fallback  — for WordPress-recipe-plugin and itemprop
     markup when JSON-LD is missing or has no ingredients.
  3. Graceful failure           — raise RecipeImportError so the UI can say
     "couldn't read that page, paste manually" (paywalls, JS-only sites, 403s).

The parsing (extract_ingredients_from_html) is pure and unit-tested on saved
HTML; fetch_ingredients adds a size-capped, SSRF-guarded network fetch.
"""

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

TIMEOUT_SECONDS = 15
MAX_BYTES       = 4_000_000    # stop reading after ~4 MB — recipe pages are small
MAX_INGREDIENTS = 100


class RecipeImportError(Exception):
    """Raised when a recipe's ingredients can't be read from a URL."""


# ─────────────────────────────────────────────────────────────────────────────
# Parsing (pure — no network, unit-tested on saved HTML)
# ─────────────────────────────────────────────────────────────────────────────
def _iter_jsonld_objects(html: str):
    """Yield every JSON object found in <script type="application/ld+json">
    blocks, flattening @graph arrays and top-level lists."""
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S | re.I,
    ):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                if '@graph' in node:
                    graph = node['@graph']
                    stack.extend(graph if isinstance(graph, list) else [graph])


def _is_recipe(node: dict) -> bool:
    t = node.get('@type')
    if isinstance(t, list):
        return any(str(x).lower() == 'recipe' for x in t)
    return str(t).lower() == 'recipe'


def _clean_lines(values) -> list[str]:
    """Normalise a list of ingredient strings: strip tags/whitespace, drop blanks."""
    out = []
    for v in values or []:
        if not isinstance(v, str):
            continue
        text = re.sub(r'<[^>]+>', ' ', v)              # strip any stray HTML
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            out.append(text)
    return out[:MAX_INGREDIENTS]


def _parse_servings(recipe_yield) -> int | None:
    """Pull a serving count out of schema.org recipeYield ("4", "4 servings",
    ["4 servings"], 4)."""
    if recipe_yield is None:
        return None
    if isinstance(recipe_yield, list):
        recipe_yield = recipe_yield[0] if recipe_yield else None
    m = re.search(r'\d+', str(recipe_yield or ''))
    return int(m.group()) if m else None


def _from_jsonld(html: str):
    for node in _iter_jsonld_objects(html):
        if _is_recipe(node) and node.get('recipeIngredient'):
            ingredients = _clean_lines(node['recipeIngredient'])
            if ingredients:
                return {
                    'ingredients': ingredients,
                    'title':       (node.get('name') or None),
                    'servings':    _parse_servings(node.get('recipeYield')),
                    'source':      'json-ld',
                }
    return None


def _from_html_markup(html: str):
    """Fallback: WordPress Recipe Maker list items or schema.org microdata."""
    soup = BeautifulSoup(html, 'lxml')

    # WPRM plugin (africanbites, cheflola, many food blogs)
    wprm = []
    for li in soup.select('li.wprm-recipe-ingredient'):
        text = li.get_text(' ', strip=True)
        if text:
            wprm.append(text)
    if wprm:
        title = soup.find(class_='wprm-recipe-name')
        return {
            'ingredients': _clean_lines(wprm),
            'title':       title.get_text(strip=True) if title else None,
            'servings':    None,
            'source':      'wprm',
        }

    # Generic microdata: itemprop="recipeIngredient" (or legacy "ingredients")
    micro = [
        el.get_text(' ', strip=True)
        for el in soup.select('[itemprop="recipeIngredient"], [itemprop="ingredients"]')
    ]
    micro = _clean_lines(micro)
    if micro:
        return {'ingredients': micro, 'title': None, 'servings': None, 'source': 'microdata'}

    return None


def extract_ingredients_from_html(html: str) -> dict:
    """Extract a recipe's ingredients from a page's HTML.

    Returns {ingredients: list[str], title: str|None, servings: int|None,
    source: str}. Raises RecipeImportError if no ingredients can be found.
    """
    result = _from_jsonld(html) or _from_html_markup(html)
    if not result:
        raise RecipeImportError(
            "Couldn't find a recipe ingredient list on that page."
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fetching (network — SSRF-guarded, size-capped)
# ─────────────────────────────────────────────────────────────────────────────
def _validate_public_url(url: str) -> None:
    """Reject anything but public http(s) URLs, to avoid being used to reach
    internal/localhost services (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise RecipeImportError("Please enter a full http(s) recipe URL.")
    host = parsed.hostname
    if not host:
        raise RecipeImportError("That doesn't look like a valid URL.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise RecipeImportError("Couldn't reach that address.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise RecipeImportError("That URL points to a non-public address.")


def fetch_ingredients(url: str) -> dict:
    """Fetch a recipe URL and extract its ingredients. Raises RecipeImportError
    on any failure (bad URL, network error, no recipe found)."""
    url = (url or "").strip()
    if not url:
        raise RecipeImportError("Please enter a recipe URL.")
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url          # be forgiving of a missing scheme

    _validate_public_url(url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, stream=True)
        resp.raise_for_status()
        chunks, total = [], 0
        for chunk in resp.iter_content(64_000):
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                break
        html = b''.join(chunks).decode(resp.encoding or 'utf-8', 'ignore')
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else '?'
        raise RecipeImportError(
            f"That site returned an error ({code}). Some sites block automated "
            "reads — paste the ingredients manually instead."
        )
    except requests.RequestException:
        raise RecipeImportError("Couldn't load that page. Check the URL and try again.")

    return extract_ingredients_from_html(html)
