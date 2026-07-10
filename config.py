"""
Configuration settings for the scraper.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///klauzule_niedozwolone.db")

# UOKiK registry URL (old site)
UOKIK_BASE_URL = "https://rejestr.uokik.gov.pl"
UOKIK_MAIN_PAGE = f"{UOKIK_BASE_URL}/index.php"

# UOKiK decisions URL (new site - Lotus Notes/Domino)
DECYZJE_BASE_URL = "https://decyzje.uokik.gov.pl"
DECYZJE_FORM_URL = f"{DECYZJE_BASE_URL}/bp/dec_prez.nsf/UOKiK?OpenForm"
DECYZJE_FORM_POST_URL = f"{DECYZJE_BASE_URL}/bp/dec_prez.nsf/UOKiK?OpenForm&Seq=1"
DECYZJE_DETAIL_URL = f"{DECYZJE_BASE_URL}/bp/dec_prez.nsf/1"

# Scraper settings
REQUEST_TIMEOUT = 30
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ---------------------------------------------------------------------------
# PDF parser backend selection
# ---------------------------------------------------------------------------
# Supported backends:
#   "rule_based"  – offline heuristic extraction (default, no API keys)
#   "ollama"      – local LLM via Ollama (requires Ollama running locally)
#   "gemini"      – Google Gemini API (requires GEMINI_API_KEY)
#   "openai"      – OpenAI GPT API (requires OPENAI_API_KEY)
#   "claude"      – Anthropic Claude API (requires CLAUDE_API_KEY)
PARSER_BACKEND = os.getenv("PARSER_BACKEND", "rule_based")

# Ollama (local LLM) configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# External API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

# OCR settings
OCR_DPI = int(os.getenv("OCR_DPI", "300"))  # DPI for PDF->image conversion
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes")
