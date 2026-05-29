"""
config.py — Database connection configuration.

Set credentials via environment variables (recommended) or edit the
defaults below for local development.

For PostgreSQL, create a .env file in the project root:
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=your_database
    DB_USER=your_user
    DB_PASSWORD=your_password
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── PostgreSQL ─────────────────────────────────────────────────────────────────
POSTGRES = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "nutrition_db"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

def postgres_url() -> str:
    p = POSTGRES
    return (
        f"postgresql+psycopg2://{p['user']}:{p['password']}"
        f"@{p['host']}:{p['port']}/{p['dbname']}"
    )

# ── File paths ─────────────────────────────────────────────────────────────────
import pathlib
BASE_DIR = pathlib.Path(__file__).parent

DATA_DIR              = BASE_DIR / "data"
NUTRIENT_CSV          = DATA_DIR / "nutrient.csv"
ORIGINAL_MAPPING_CSV  = DATA_DIR / "ingredient_mapping_original.csv"
CLEANED_MAPPING_CSV   = DATA_DIR / "ingredient_mapping_cleaned.csv"
