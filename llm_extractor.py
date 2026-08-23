"""
LLM extractor module for extracting unfair contract clauses from UOKiK
decision PDFs using various LLM backends.

Supported backends:
    - ollama   : local models (llama3.1, qwen2.5, mistral, …)
    - gemini   : Google Gemini API
    - openai   : OpenAI GPT API
    - claude   : Anthropic Claude API

Usage:
    from llm_extractor import extract_clause_with_llm, is_backend_available
    result = extract_clause_with_llm(pdf_text, backend="ollama")
    # result = {
    #     "postanowienie_niedozwolone": "...",
    #     "powod": "Prezes UOKiK",
    #     "pozwany": "Firma Sp. z o.o.",
    #     "confidence": 0.92,
    #     "method": "ollama:llama3.1"
    # }

Each backend is imported optionally so missing packages do not break the module.
"""

import json
import re
import warnings
from typing import Dict, Optional

from config import (
    PARSER_BACKEND,
    OLLAMA_URL,
    OLLAMA_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENAI_API_KEY,
    CLAUDE_API_KEY,
)

# ---------------------------------------------------------------------------
# Optional backend imports
# ---------------------------------------------------------------------------

try:
    import ollama as _ollama_lib
    HAS_OLLAMA = True
except Exception as _exc_ollama:  # noqa: F841
    HAS_OLLAMA = False

try:
    import google.generativeai as _genai
    HAS_GEMINI = True
except Exception as _exc_gemini:  # noqa: F841
    HAS_GEMINI = False

try:
    import openai as _openai_lib
    HAS_OPENAI = True
except Exception as _exc_openai:  # noqa: F841
    HAS_OPENAI = False

try:
    import anthropic as _anthropic_lib
    HAS_ANTHROPIC = True
except Exception as _exc_anthropic:  # noqa: F841
    HAS_ANTHROPIC = False


__all__ = [
    "is_backend_available",
    "extract_clause_with_llm",
    "LLM_PROMPT_PL",
]


# ---------------------------------------------------------------------------
# Prompt (Polish) — shared across all backends
# ---------------------------------------------------------------------------

LLM_PROMPT_PL = """Jesteś ekspertem w polskim prawie konsumenckim. Twoim zadaniem jest wyciągnięcie z poniższego tekstu decyzji Prezesa UOKiK **treści klauzuli niedozwolonej** (zakazanego postanowienia umownego).

Z tekstu wyciągnij:
1. **postanowienie_niedozwolone** — dokładne brzmienie klauzuli niedozwolonej. Jeśli jest kilka, podaj najważniejszą lub wszystkie w jednym polu, rozdzielone średnikiem.
2. **powod** — kto wszczął postępowanie (zazwyczaj "Prezes UOKiK" lub "Urząd Ochrony Konkurencji i Konsumentów").
3. **pozwany** — nazwa firmy, przeciwko której wydano decyzję (pełna nazwa przedsiębiorcy).
4. **paragraf** — numer paragrafu, artykułu lub sekcji w decyzji, w której znajduje się klauzula (np. "§ 5", "art. 4", puste jeśli brak).
5. **punkt** — numer punktu, ustępu, litery — jeśli jest podany (puste jeśli brak).

Odpowiedz **WYŁĄCZNIE** w formacie JSON, bez dodatkowego komentarza, markdown ani kodu. Przykład:
{
  "postanowienie_niedozwolone": "Zakazane jest postanowienie umowne zwalniające przedsiębiorcę z odpowiedzialności za szkody wyrządzone konsumentowi.",
  "powod": "Prezes UOKiK",
  "pozwany": "Przykładowa Spółka z o.o.",
  "paragraf": "§ 5",
  "punkt": "ust. 2"
}

Jeśli nie możesz znaleźć któregoś pola, użyj wartości null.

--- TEKST DECYZJI ---
{text}
--- KONIEC TEKSTU ---
"""


# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------

def is_backend_available(backend: str) -> bool:
    """Return True if the requested backend is importable and configured."""
    backend = backend.lower().strip()
    if backend == "ollama":
        return HAS_OLLAMA
    if backend == "gemini":
        return HAS_GEMINI and bool(GEMINI_API_KEY)
    if backend == "openai":
        return HAS_OPENAI and bool(OPENAI_API_KEY)
    if backend == "claude":
        return HAS_ANTHROPIC and bool(CLAUDE_API_KEY)
    return False


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> Optional[Dict]:
    """Try to extract a JSON object from a markdown / plain text response."""
    # 1. Try fenced code block
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Try first standalone JSON object
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _normalise_llm_result(raw: Dict, backend_name: str) -> Dict:
    """Normalise the LLM response to the unified schema."""
    result = {
        "postanowienie_niedozwolone": raw.get("postanowienie_niedozwolone") or raw.get("klauzula") or raw.get("clause") or raw.get("treść") or None,
        "powod": raw.get("powod") or raw.get("plaintiff") or raw.get("wnioskodawca") or "Prezes UOKiK",
        "pozwany": raw.get("pozwany") or raw.get("defendant") or raw.get("przedsiębiorca") or raw.get("firma") or None,
        "paragraf": raw.get("paragraf") or raw.get("paragraph") or raw.get("artykuł") or raw.get("art") or None,
        "punkt": raw.get("punkt") or raw.get("point") or raw.get("ustęp") or raw.get("letter") or None,
        "confidence": 0.90,
        "method": backend_name,
    }

    # Confidence heuristics based on data quality
    if not result["postanowienie_niedozwolone"]:
        result["confidence"] = 0.10
    elif len(result["postanowienie_niedozwolone"]) < 30:
        result["confidence"] = 0.40
    elif len(result["postanowienie_niedozwolone"]) > 300:
        result["confidence"] = 0.95

    return result


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _ollama_extract(text: str) -> Dict:
    """Call a local Ollama model."""
    if not HAS_OLLAMA:
        raise RuntimeError("ollama package is not installed.")

    prompt = LLM_PROMPT_PL.format(text=text[:12000])  # generous context window

    try:
        client = _ollama_lib.Client(host=OLLAMA_URL)
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        content = response.get("message", {}).get("content", "")
    except Exception as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    raw = _extract_json_from_text(content)
    if not raw:
        return {
            "postanowienie_niedozwolone": None,
            "powod": "Prezes UOKiK",
            "pozwany": None,
            "paragraf": None,
            "punkt": None,
            "confidence": 0.0,
            "method": f"ollama:{OLLAMA_MODEL}",
        }

    return _normalise_llm_result(raw, f"ollama:{OLLAMA_MODEL}")


def _gemini_extract(text: str) -> Dict:
    """Call Google Gemini API."""
    if not HAS_GEMINI:
        raise RuntimeError("google-generativeai package is not installed.")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    _genai.configure(api_key=GEMINI_API_KEY)
    model = _genai.GenerativeModel(GEMINI_MODEL)
    prompt = LLM_PROMPT_PL.format(text=text[:12000])

    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1},
        )
        content = response.text
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    raw = _extract_json_from_text(content)
    if not raw:
        return {
            "postanowienie_niedozwolone": None,
            "powod": "Prezes UOKiK",
            "pozwany": None,
            "paragraf": None,
            "punkt": None,
            "confidence": 0.0,
            "method": "gemini:flash",
        }

    return _normalise_llm_result(raw, "gemini:flash")


def _openai_extract(text: str) -> Dict:
    """Call OpenAI ChatCompletion API."""
    if not HAS_OPENAI:
        raise RuntimeError("openai package is not installed.")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = _openai_lib.OpenAI(api_key=OPENAI_API_KEY)
    prompt = LLM_PROMPT_PL.format(text=text[:12000])

    try:
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Jesteś polskim prawnikiem specjalizującym się w prawie konsumenckim. Odpowiadasz wyłącznie w formacie JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        content = chat.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    raw = _extract_json_from_text(content)
    if not raw:
        return {
            "postanowienie_niedozwolone": None,
            "powod": "Prezes UOKiK",
            "pozwany": None,
            "paragraf": None,
            "punkt": None,
            "confidence": 0.0,
            "method": "openai:gpt-4o-mini",
        }

    return _normalise_llm_result(raw, "openai:gpt-4o-mini")


def _claude_extract(text: str) -> Dict:
    """Call Anthropic Claude API."""
    if not HAS_ANTHROPIC:
        raise RuntimeError("anthropic package is not installed.")
    if not CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not set.")

    client = _anthropic_lib.Anthropic(api_key=CLAUDE_API_KEY)
    prompt = LLM_PROMPT_PL.format(text=text[:12000])

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text if message.content else ""
    except Exception as exc:
        raise RuntimeError(f"Claude API request failed: {exc}") from exc

    raw = _extract_json_from_text(content)
    if not raw:
        return {
            "postanowienie_niedozwolone": None,
            "powod": "Prezes UOKiK",
            "pozwany": None,
            "paragraf": None,
            "punkt": None,
            "confidence": 0.0,
            "method": "claude:haiku",
        }

    return _normalise_llm_result(raw, "claude:haiku")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_clause_with_llm(text: str, backend: Optional[str] = None) -> Dict:
    """Extract clause using the specified LLM backend.

    Args:
        text: Full text extracted from the PDF (or OCR output).
        backend: One of "ollama", "gemini", "openai", "claude".
                 Defaults to config.PARSER_BACKEND.

    Returns:
        Dictionary with keys:
            - postanowienie_niedozwolone (str or None)
            - powod (str)
            - pozwany (str or None)
            - confidence (float 0.0–1.0)
            - method (str)

    Raises:
        RuntimeError: if the backend is unavailable or the API call fails.
    """
    backend = (backend or PARSER_BACKEND).lower().strip()

    if backend == "rule_based":
        raise RuntimeError(
            "extract_clause_with_llm() should not be called with backend='rule_based'. "
            "Use the heuristic pipeline instead."
        )

    if not is_backend_available(backend):
        available = [b for b in ("ollama", "gemini", "openai", "claude") if is_backend_available(b)]
        raise RuntimeError(
            f"Backend '{backend}' is not available. "
            f"Available backends: {available or 'none'}. "
            f"Check installed packages and API keys."
        )

    if backend == "ollama":
        return _ollama_extract(text)
    if backend == "gemini":
        return _gemini_extract(text)
    if backend == "openai":
        return _openai_extract(text)
    if backend == "claude":
        return _claude_extract(text)

    raise RuntimeError(f"Unknown backend: {backend}")
