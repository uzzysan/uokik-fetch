"""
Configuration settings for the scraper.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///klauzule_niedozwolone.db")

# UOKiK registry URL
UOKIK_BASE_URL = "https://rejestr.uokik.gov.pl"
UOKIK_MAIN_PAGE = f"{UOKIK_BASE_URL}/index.php"

# Scraper settings
REQUEST_TIMEOUT = 30
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
