"""
decision_extractor.py — extract decision-level metadata AND all prohibited
clauses from a UOKiK decision's text using the configured Gemini model.

Used by the manual ingest web app (fairpact.pl/ingest). Kept separate from
llm_extractor.py (single-clause extractor) to avoid touching the existing
scraping pipeline.
"""
from __future__ import annotations
import json
import re
from typing import Dict, List

from config import GEMINI_API_KEY, GEMINI_MODEL

try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except Exception:
    genai = None
    _HAS_GEMINI = False

PROMPT_HEADER = (
    "Jesteś ekspertem polskiego prawa konsumenckiego. Przeanalizuj tekst decyzji "
    "Prezesa UOKiK i zwróć WYŁĄCZNIE obiekt JSON (bez komentarzy, bez znaczników ```), "
    "dokładnie w tym formacie:\n"
    '{\n'
    '  "sygnatura": "sygnatura akt decyzji",\n'
    '  "data_decyzji": "data wydania w formacie YYYY-MM-DD",\n'
    '  "numer_decyzji": "numer decyzji",\n'
    '  "pozwany": "przedsiębiorca, którego dotyczy decyzja",\n'
    '  "powod": "podmiot wnoszący (domyślnie Prezes UOKiK)",\n'
    '  "branza": "branża lub sektor",\n'
    '  "region": "województwo/region jeśli podano",\n'
    '  "klauzule": [\n'
    '    {"postanowienie_niedozwolone": "pełna treść zakwestionowanego postanowienia",\n'
    '     "numer_postanowienia": "numer/oznaczenie jeśli jest",\n'
    '     "zagadnienie": "krótko czego dotyczy"}\n'
    '  ]\n'
    '}\n'
    "Wypisz WSZYSTKIE zakwestionowane postanowienia (często jest ich kilka). "
    'Jeśli pola nie ma w tekście, użyj pustego łańcucha "". Nie zmyślaj treści.\n\n'
    "TEKST DECYZJI:\n"
)
MAX_CHARS = 120000

def is_available() -> bool:
    return bool(_HAS_GEMINI and GEMINI_API_KEY)

def _s(v) -> str:
    return str(v).strip() if v is not None else ""

def extract_decision(text: str) -> Dict:
    """Return decision fields + list of clauses. Raises RuntimeError if Gemini unavailable."""
    if not is_available():
        raise RuntimeError("Gemini niedostępny (brak pakietu google-generativeai lub GEMINI_API_KEY).")
    prompt = PROMPT_HEADER + (text or "")[:MAX_CHARS]
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt, generation_config={"temperature": 0.1})
    raw = (getattr(resp, "text", "") or "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    payload = m.group(0) if m else raw
    try:
        data = json.loads(payload)
    except Exception:
        data = {}
    klauzule: List[Dict] = []
    for c in (data.get("klauzule") or []):
        if not isinstance(c, dict):
            continue
        tresc = _s(c.get("postanowienie_niedozwolone") or c.get("klauzula") or c.get("clause"))
        if not tresc:
            continue
        klauzule.append({
            "postanowienie_niedozwolone": tresc,
            "numer_postanowienia": _s(c.get("numer_postanowienia")),
            "zagadnienie": _s(c.get("zagadnienie")),
        })
    return {
        "sygnatura": _s(data.get("sygnatura") or data.get("sygnatura_akt")),
        "data_decyzji": _s(data.get("data_decyzji") or data.get("data_wydania") or data.get("data")),
        "numer_decyzji": _s(data.get("numer_decyzji")),
        "pozwany": _s(data.get("pozwany") or data.get("przedsiebiorca") or data.get("firma")),
        "powod": _s(data.get("powod")) or "Prezes UOKiK",
        "branza": _s(data.get("branza")),
        "region": _s(data.get("region")),
        "klauzule": klauzule,
    }
