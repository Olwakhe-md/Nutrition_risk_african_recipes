"""
scripts/cleaner.py
==================
Cleans raw recipe ingredient strings into lean, matchable names.

Three-stage pipeline per ingredient:
  1. African proxy check  — catches regional names before any stripping
  2. Brand prefix strip   — removes product brand noise
  3. Noise word removal   — strips prep instructions, quantity descriptors, etc.

Usage (standalone):
    from scripts.cleaner import clean_ingredient, AFRICAN_PROXIES

    cleaned, tag, display = clean_ingredient("real premium spice paprika")
    # → ('Hot pepper sauce', 'manual_match', 'Hot pepper sauce')

    cleaned, tag, display = clean_ingredient("bondwe leave")
    # → ('amaranth leaves', 'african_proxy', 'bondwe leaves')
"""

import re
from typing import Any
import pandas as pd

# ── Cleaning Constants (Consolidated from root scripts) ───────────────────────
LEADING_UNITS = {
    "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
    "teaspoons", "ml", "l", "g", "kg", "oz", "lb", "lbs", "gram", "grams",
    "kilogram", "kilograms", "pinch", "pinches", "dash", "clove", "cloves",
    "can", "cans", "slice", "slices", "piece", "pieces"
}

FILLER_TOKENS = {
    "to", "taste", "optional", "for", "serving", "plus", "more", "needed",
    "and", "or", "of", "the", "a", "an", "into", "in", "with", "without",
    "from", "on", "at", "it", "its"
}

SIZE_TOKENS = {"large", "medium", "small"}

PREP_TOKENS = {
    "chopped", "minced", "diced", "sliced", "crushed", "freshly", "roughly",
    "finely", "thinly", "thickly", "grated", "peeled", "rinsed", "drained",
    "divided", "halved", "quartered", "cubed", "cut", "soaked", "torn",
    "softened", "melted", "beaten", "mashed"
}

FORM_TOKEN_MAP = {
    "fresh": "fresh", "powder": "powder", "powdered": "powder", "ground": "ground",
    "dried": "dried", "dry": "dried", "paste": "paste", "puree": "puree",
    "canned": "canned", "can": "canned", "tinned": "canned", "whole": "whole",
    "frozen": "frozen", "smoked": "smoked", "toasted": "toasted"
}

UNCOUNTABLE_PLURALS = {"couscous", "molasses", "bass"}

FRESH_DEFAULT_BASES = {
    "garlic", "onion", "tomato", "ginger", "pepper", "chili", "chilli"
}

# ── African / regional ingredient proxy table ──────────────────────────────────
# Keys   = lowercased raw ingredient strings (or after brand strip)
# Values = (proxy_for_nutrition, display_name)
#
# proxy_for_nutrition : the closest Western/USDA nutritional equivalent
# display_name        : human-readable local name to store in the DB
AFRICAN_PROXIES: dict[str, tuple[str, str]] = {
    "bondwe":                               ("amaranth leaves",          "bondwe leaves"),
    "bondwe leave":                         ("amaranth leaves",          "bondwe leaves"),
    "garri":                                ("cassava flour",            "garri"),
    "fonio":                                ("millet",                   "fonio"),
    "kapenta":                              ("dried anchovies",          "kapenta"),
    "egusi seed":                           ("pumpkin seeds",            "egusi seeds"),
    "sadza remhunga":                       ("sorghum porridge",         "sadza remhunga"),
    "mufushwa wemunyemba":                  ("dried cowpea leaves",      "mufushwa"),
    "ewedu leave":                          ("jute leaves",              "ewedu leaves"),
    "impwa":                                ("african eggplant",         "impwa"),
    "kalembula":                            ("sweet potato leaves",      "kalembula"),
    "lumanda leave":                        ("hibiscus leaves",          "lumanda leaves"),
    "grain hub mhunga":                     ("pearl millet",             "mhunga"),
    "grain hub mupunga":                    ("white rice",               "mupunga"),
    "grain hub sorghum":                    ("sorghum grain",            "sorghum"),
    "grain hub zviyo":                      ("finger millet",            "zviyo"),
    "samp":                                 ("hominy corn",              "samp"),
    "aish baladi":                          ("whole wheat flatbread",    "aish baladi"),
    "berbere spice mix":                    ("ethiopian spice blend",    "berbere"),
    "harissa spice mix":                    ("chili spice paste",        "harissa"),
    "ras el hanout":                        ("moroccan spice blend",     "ras el hanout"),
    "garam masala":                         ("indian spice blend",       "garam masala"),
    "organic jaggery":                      ("unrefined cane sugar",     "jaggery"),
    "pounded groundnut":                    ("ground peanuts",           "pounded groundnut"),
    "butternut":                            ("butternut squash",         "butternut squash"),
    "yam":                                  ("yam tuber",                "yam"),
    "yam tuber":                            ("yam tuber",                "yam"),
    "moscato":                              ("sweet white wine",         "moscato"),
    "chapati":                              ("flatbread",                "chapati"),
    "pili pili":                            ("hot chili pepper",         "pili pili"),
    "kachumbari":                           ("fresh tomato onion salad", "kachumbari"),
    "semolina":                             ("semolina flour",           "semolina"),
    "scotch bonnet chilli":                 ("habanero pepper",          "scotch bonnet"),
    "scotch bonnet chile habanero chile":   ("habanero pepper",          "scotch bonnet"),
    "habanero chile":                       ("habanero pepper",          "habanero"),
    "habanero chile seeded":                ("habanero pepper",          "habanero"),
    "habanero chile stem removed":          ("habanero pepper",          "habanero"),
    "serrano chile":                        ("serrano pepper",           "serrano"),
    "cob sweetcorn":                        ("corn on the cob",          "sweetcorn"),
    "scallion":                             ("green onion",              "scallion"),
}

# Region hints — used to populate the african_ingredient_proxies.region column
AFRICAN_PROXY_REGIONS: dict[str, str] = {
    "bondwe":               "Southern Africa",
    "bondwe leave":         "Southern Africa",
    "garri":                "West Africa",
    "fonio":                "West Africa",
    "kapenta":              "Southern Africa",
    "egusi seed":           "West Africa",
    "sadza remhunga":       "Southern Africa",
    "mufushwa wemunyemba":  "Southern Africa",
    "ewedu leave":          "West Africa",
    "impwa":                "Southern Africa",
    "kalembula":            "Southern Africa",
    "lumanda leave":        "Southern Africa",
    "grain hub mhunga":     "Southern Africa",
    "grain hub mupunga":    "Southern Africa",
    "grain hub sorghum":    "Southern Africa",
    "grain hub zviyo":      "Southern Africa",
    "samp":                 "Southern Africa",
    "aish baladi":          "North Africa",
    "berbere spice mix":    "East Africa",
    "harissa spice mix":    "North Africa",
    "ras el hanout":        "North Africa",
    "pili pili":            "Central/East Africa",
    "kachumbari":           "East Africa",
    "scotch bonnet chilli": "West Africa",
    "pounded groundnut":    "West Africa",
}

# ── Brand prefixes to strip before matching ────────────────────────────────────
_BRAND_PREFIXES: list[str] = [
    r"^real premium spice\s+",
    r"^zimspice\s+",
    r"^mr sauce\s+",
    r"^grain hub\s+",
    r"^aunty bernie\s+",
]

# ── Noise patterns — recipe instructions, quantity words, prep descriptors ─────
_NOISE_PATTERNS: list[str] = [
    # explicit instruction phrases
    r"\bcover bowl clean kitchen\b",
    r"\bhot water soften thoroughly\b",
    r"\benough water (go just below potato|make)\b",
    r"\bgo just below potato\b",
    r"\bnonstick skillet over\b",
    r"\blet marinate\b",
    r"\brefrigerator\b",
    r"\bwarm oil dutch oven other heavy\b",
    r"\bfull-fat unsweetened (reserved bone|other heavy pot)\b",
    r"\bsqueezed refrigerator\b",
    r"\bfat ghee egg yolk will start\b",
    r"\bpestle mortar\b",
    r"\bseed removed strip\b",
    r"\bgutted scaled\b",
    r"\bwashed cleaned thoroughly\b",
    r"\bde-seeded bite-sized chunk\b",
    r"\bbite-sized? chunk\b",
    r"\bbite-size\b",
    r"\bpili pili store-?bought\b",
    # prep adjectives
    r"\bcoarsely\b",
    r"\bjulienned\b",
    r"\btrimmed\b",
    r"\bsifted\b",
    r"\bde-seeded\b",
    r"\bseeded\b",
    r"\bpitted\b",
    r"\bstem removed\b",
    r"\bsome stem attached\b",
    r"\bgutted\b",
    r"\bscaled\b",
    r"\bthawed\b",
    r"\bsoften\b",
    r"\bthoroughly\b",
    r"\bhandheld\b",
    r"\bpancake batter\b",
    r"\bboneles\b",
    r"\bbatter\b",
    r"\bsplit half lightly\b",
    r"\btoasted\b",
    r"\bhomemade shop bought\b",
    r"\bshop bought\b",
    r"\bready-rolled\b",
    # quantity / container words
    r"\bsheet\b",
    r"\bpacket\b",
    r"\bbunch\b",
    r"\bsprig\b",
    r"\bpunnet\b",
    r"\bpint\b",
    r"\bhandful\b",
    r"\bheaped\b",
    r"\bassorted\b",
    r"\bjarre?d\b",
    r"\bfree-range\b",
    r"\bextremely ripe\b",
    r"\bsized\b",
    r"\bgrille?d\b",
    r"\bparsley garnishing\b",
    r"\bgreen tip\b",
    r"\bwhole\b",
    r"\bleft\b",
    r"\bsqueezed\b",
    r"\breserved bone\b",
    r"\bother heavy (pot|pan)?\b",
    r"\bover\b$",
    r"\bif desired\b",
    r"\bextra if desired\b",
    r"\bgenerou\b",    # typo for "generous"
    r"\bkitchen\b",
    r"\bbowl\b",
    r"\bstart\b$",
    r"\band\b$",
    r"\bthe\b",
    r"\bsome\b",
    r"\bjust\b",
    r"\bbelow\b",
    r"\bpound\b",
    # size descriptors
    r"-inch (round|cube|thick|strip|piece|chunk)?",
    r"\b\d+(-\d+)? inch\b",
    r"\b-inch\b",
]

# ── Compiled regex objects (compiled once at import time) ──────────────────────
_RE_BRAND   = [re.compile(p, re.IGNORECASE) for p in _BRAND_PREFIXES]
_RE_NOISE   = [re.compile(p, re.IGNORECASE) for p in _NOISE_PATTERNS]
_RE_PARENS  = re.compile(r"\(([^)]+)\)")
_RE_SPACES  = re.compile(r"\s{2,}")

def singularize(token: str) -> str:
    if token in UNCOUNTABLE_PLURALS:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token

def normalize_text(s: str) -> str:
    if pd.isna(s):
        return ""
    s = s.lower().strip()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_brands(name: str) -> str:
    for pat in _RE_BRAND:
        name = pat.sub("", name)
    return name.strip()


def _strip_noise(name: str) -> str:
    for pat in _RE_NOISE:
        name = pat.sub(" ", name)
    return name.strip()


def _unwrap_parentheticals(name: str) -> str:
    """'allspice (ground)' → 'allspice ground'"""
    return _RE_PARENS.sub(r"\1", name).strip()


def _finalise(name: str) -> str:
    name = _RE_SPACES.sub(" ", name)
    return name.strip(" .,_-")


def clean_ingredient(raw: str) -> tuple[str, str, str]:
    """
    Clean a single raw ingredient string.

    Returns
    -------
    (result, tag, display_name)

    result       : cleaned string ready for DB matching
    tag          : 'african_proxy' | 'cleaned'
    display_name : human-friendly label (same as result for cleaned;
                   local name for african_proxy)
    """
    name = raw.lower().strip()

    # ── Stage 1: African proxy (raw) ──
    if name in AFRICAN_PROXIES:
        proxy, display = AFRICAN_PROXIES[name]
        return proxy, "african_proxy", display

    # ── Stage 2: Brand strip ──
    name = _strip_brands(name)

    # ── Stage 1b: African proxy (after brand strip) ──
    if name in AFRICAN_PROXIES:
        proxy, display = AFRICAN_PROXIES[name]
        return proxy, "african_proxy", display

    # ── Stage 3: Noise removal ──
    name = _strip_noise(name)
    name = _unwrap_parentheticals(name)
    name = _finalise(name)

    return name, "cleaned", name


def is_instruction_fragment(cleaned: str) -> bool:
    """Return True if the cleaned string is too short / empty to be an ingredient."""
    return len(cleaned) < 2

def extract_base_ingredient(name: str) -> str:
    """
    Extracts the core ingredient name by singularizing and removing form/prep noise.
    """
    tokens = normalize_text(name).split()
    base_tokens = []
    for t in tokens:
        if t in FORM_TOKEN_MAP or t in PREP_TOKENS or t in LEADING_UNITS or t in FILLER_TOKENS:
            continue
        base_tokens.append(singularize(t))
    
    # Remove small noise tokens
    base_tokens = [t for t in base_tokens if len(t) > 1]
    return " ".join(base_tokens).strip()
