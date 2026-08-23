"""
PDF parser module for extracting unfair contract clauses from UOKiK decision PDFs.

Dependencies (add to pyproject.toml if needed):
    - pdfplumber (primary, better text extraction from complex layouts)
    - pypdf (fallback if pdfplumber is not available)
    - PyPDF2 (alternative fallback, older package name)

Usage:
    from pdf_parser import extract_text_from_pdf, extract_clause_with_ai, process_decision
    from pdf_parser import process_all_decisions

    # Extract text from a single PDF
    text = extract_text_from_pdf("pdfs/2024/decyzja.pdf")

    # Extract clause using rule-based heuristics
    result = extract_clause_with_ai(text, "RGD-2/2026")

    # Process a single decision ORM object
    result = process_decision(decyzja_obj)

    # Process all pending decisions in the database
    stats = process_all_decisions(years=[2024], save_to_db=True)
"""
import os
import re
import time
import random
from typing import List, Dict, Optional
from datetime import datetime
from tqdm import tqdm

# Optional imports for PDF extraction
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False

from database import get_db
from models import DecyzjaUOKiK, DecyzjaPDF, KlauzulaNiedozwolona
from config import PARSER_BACKEND

# Optional OCR / LLM imports (fail gracefully if packages are missing)
try:
    from ocr_extractor import extract_text_with_ocr, is_ocr_available
    HAS_OCR = True
except Exception as _exc_ocr:  # noqa: F841
    HAS_OCR = False

try:
    from llm_extractor import extract_clause_with_llm, is_backend_available
    HAS_LLM = True
except Exception as _exc_llm:  # noqa: F841
    HAS_LLM = False


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using pdfplumber, pypdf, or OCR fallback.

    Extraction order:
        1. pdfplumber (best for complex layouts)
        2. pypdf / PyPDF2
        3. OCR (pdf2image + pytesseract) if text is empty — handles scanned PDFs

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted raw text from the PDF.  May be empty for scanned PDFs without OCR.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        RuntimeError: If no PDF library is available and OCR is also unavailable.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    text = ""

    # Try pdfplumber first (better for complex layouts / multi-column docs)
    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text
            # text is empty — possible scanned PDF, fall through to OCR
        except Exception as e:
            print(f"pdfplumber failed for {pdf_path}: {e}. Trying pypdf fallback...")

    # Fallback to pypdf / PyPDF2
    if HAS_PYPDF:
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if text.strip():
                return text
            # text is empty — possible scanned PDF, fall through to OCR
        except Exception as e:
            raise RuntimeError(
                f"Failed to extract text from PDF {pdf_path}: {e}"
            ) from e

    # Last resort: OCR for scanned PDFs
    if HAS_OCR:
        print(f"[OCR] Normal extraction returned empty text for {pdf_path}. Attempting OCR...")
        ocr_text = extract_text_with_ocr(pdf_path)
        if ocr_text.strip():
            return ocr_text
        print(f"[OCR] OCR also returned empty text for {pdf_path}.")
    else:
        if not (HAS_PDFPLUMBER or HAS_PYPDF):
            raise RuntimeError(
                "No PDF library available. Install one of: pdfplumber, pypdf, PyPDF2"
            )
        # Libraries exist but produced empty text — warn about possible scanned PDF
        print(f"[WARN] {pdf_path} appears to be a scanned PDF and OCR is unavailable. "
              "Install pdf2image + pytesseract + poppler to enable OCR fallback.")

    return text


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalise PDF text: collapse whitespace, remove standalone page numbers."""
    # Replace tabs and multiple spaces with a single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Remove lines that are just page numbers (e.g. "12" or " - 12 -")
    text = re.sub(r'\n\s*(?:-\s*)?\d+(?:\s*-)?\s*\n', '\n', text)
    # Collapse three or more newlines into two
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_into_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs using double-newlines or capitalised line starts."""
    # Split on double newline or on single newline followed by uppercase
    paragraphs = re.split(r'\n\s*\n|\n(?=[A-ZĄĆĘŁŃÓŚŹŻ])', text)
    return [p.strip() for p in paragraphs if p.strip()]


# ---------------------------------------------------------------------------
# Heuristic scoring for clause relevance
# ---------------------------------------------------------------------------

def _score_paragraph_for_clause(paragraph: str) -> float:
    """Score a paragraph for likelihood of containing an unfair contract clause.

    Uses keyword matching and heuristics specific to Polish legal/administrative
    language used in UOKiK decisions.
    """
    score = 0.0
    p_lower = paragraph.lower()
    length = len(paragraph)

    # --- High-weight keywords (directly related to unfair clauses) ---
    high_keywords = [
        "niedozwolone", "zakazane jest", "postanowienie niedozwolone",
        "klauzula niedozwolona", "zakazane postanowienie",
        "stwierdza się", "zobowiązuje się", "w trybie art", "na podstawie art",
        "uznaje się za", "zakazuje stosowania",
    ]
    for kw in high_keywords:
        if kw in p_lower:
            score += 3.0

    # --- Medium-weight keywords (contract / consumer law domain) ---
    medium_keywords = [
        "klauzula", "postanowienie", "warunek", "zapis", "umowy",
        "konsument", "przedsiębiorca", "strona", "umowa", "prawo",
        "obowiązek", "odpowiedzialność", "zwrot", "rekompensata",
        "prawo odstąpienia", "odstąpienie od umowy", "reklamacja",
    ]
    for kw in medium_keywords:
        if kw in p_lower:
            score += 1.5

    # --- Low-weight but still relevant context words ---
    low_keywords = [
        "decyzja", "prezes", "uokik", "postępowanie", "praktyka",
        "sąd", "orzeczenie", "nakaz",
    ]
    for kw in low_keywords:
        if kw in p_lower:
            score += 0.5

    # --- Length bonus / penalty ---
    # Ideal clause paragraph: 100–800 characters
    if 100 <= length <= 800:
        score += 2.0
    elif 50 <= length < 100:
        score += 1.0
    elif length > 1500:
        score -= 1.5  # Too long, likely the whole document body
    elif length < 30:
        score -= 2.0  # Too short to be meaningful

    # --- Bonus for quoted text (often contains the actual clause wording) ---
    if any(ch in paragraph for ch in ('"', '„', '»', '«', '”', '“')):
        score += 1.5

    # --- Bonus for legal article references (e.g. "art. 23", "art. 104") ---
    if re.search(r'art\.?\s*\d+', paragraph, re.IGNORECASE):
        score += 1.0

    # --- Penalty for obvious boilerplate / metadata paragraphs ---
    boilerplate_patterns = [
        r'^data wydania',
        r'^numer decyzji',
        r'^sygnatura',
        r'^uczestnicy postępowania',
        r'^rodzaj praktyki',
        r'^kara',
        r'^branża',
        r'^region',
        r'^odwołanie do sądu',
    ]
    for bp in boilerplate_patterns:
        if re.search(bp, p_lower):
            score -= 3.0

    return score


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def _extract_by_markers(text: str) -> Optional[str]:
    """Try to extract clause text using explicit section markers in Polish decisions."""
    # (start_marker, end_marker) pairs.  end_marker=None means "read until blank
    # line after collecting at least a few lines".
    markers = [
        ("POSTANOWIENIE NIEDOZWOLONE", None),
        ("TREŚĆ POSTANOWIENIA", None),
        ("ZAKAZANE POSTANOWIENIE", None),
        ("ZAKAZANE JEST", None),
        ("STWIERDZA SIĘ, ŻE", None),
        ("UZNAJE SIĘ ZA", None),
        ("POSTANOWIENIE", "NA PRAWO"),  # older style
    ]

    lines = text.split('\n')

    for start_marker, end_marker in markers:
        for i, line in enumerate(lines):
            if start_marker.lower() in line.lower():
                extracted_lines = [line]
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    # Stop at explicit end marker
                    if end_marker and end_marker.lower() in next_line.lower():
                        break
                    # Stop at blank line after collecting a reasonable chunk
                    if next_line == "" and len(''.join(extracted_lines)) > 100:
                        break
                    # Hard stop at very long chunk
                    if len(''.join(extracted_lines)) > 2000:
                        break
                    extracted_lines.append(next_line)

                result = '\n'.join(extracted_lines).strip()
                if len(result) > 50:
                    return result

    return None


def _extract_by_scoring(text: str) -> Optional[str]:
    """Extract the most relevant paragraph using keyword-density heuristics."""
    paragraphs = _split_into_paragraphs(text)

    best_paragraph = None
    best_score = -float('inf')

    for paragraph in paragraphs:
        score = _score_paragraph_for_clause(paragraph)
        if score > best_score:
            best_score = score
            best_paragraph = paragraph

    # Only return if the score is above a minimum threshold
    if best_score >= 2.0:
        return best_paragraph

    return None


def _extract_fallback(text: str) -> Optional[str]:
    """Last-resort fallback: find the first substantial paragraph with a keyword."""
    paragraphs = _split_into_paragraphs(text)
    for p in paragraphs:
        p_lower = p.lower()
        if any(kw in p_lower for kw in ['niedozwolone', 'zakazane', 'klauzula', 'postanowienie']):
            if len(p) > 50:
                return p
    # Absolute fallback: first paragraph with >100 chars
    for p in paragraphs:
        if len(p) > 100:
            return p
    return None


# ---------------------------------------------------------------------------
# Metadata extraction (powód / pozwany)
# ---------------------------------------------------------------------------

def _extract_powod(text: str) -> str:
    """Extract plaintiff (powód) from the text.

    In UOKiK decisions the plaintiff is almost always the President of UOKiK
    or the UOKiK office itself.
    """
    text_lower = text.lower()

    if "prezes urzędu ochrony konkurencji i konsumentów" in text_lower:
        return "Prezes Urzędu Ochrony Konkurencji i Konsumentów"
    if "prezes uokik" in text_lower:
        return "Prezes UOKiK"
    if "urząd ochrony konkurencji i konsumentów" in text_lower:
        return "Urząd Ochrony Konkurencji i Konsumentów"
    if "urząd ochrony konkurencji" in text_lower:
        return "Urząd Ochrony Konkurencji"

    return "Prezes UOKiK"


def _extract_pozwany(text: str, uczestnicy: Optional[str] = None) -> Optional[str]:
    """Extract defendant (pozwany) from the text or from the participants metadata.

    In UOKiK decisions the defendant is the company against which the decision
    was issued.  We first try to extract from the participants field, then fall
    back to regex patterns in the full text.
    """
    # 1. Try the participants field (first non-empty line after cleaning)
    if uczestnicy:
        lines = [l.strip() for l in uczestnicy.split('\n') if l.strip()]
        for line in lines:
            # Remove leading numbering like "1." or "a)"
            line = re.sub(r'^\d+[.)\s]+', '', line)
            if len(line) > 3:
                # Truncate to 500 chars (matches KlauzulaNiedozwolona.pozwany)
                return line[:500]

    # 2. Regex patterns in the full text
    patterns = [
        # "przeciwko / wobec / w stosunku do" + company name with common Polish suffixes
        r'(?:przeciwko|wobec|w\s*stosunku\s*do)\s+('
        r'[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż\s\d\.\-]+?'
        r'(?:sp\.?\s*z\s*o\.?o\.?|S\.A\.|s\.a\.|sp\.?k\.|sp\.?j\.|sp\.?c\.|'
        r'z\s*o\.?o\.?|GmbH|Ltd|Inc|LLC))',
        # Same but with broader ending
        r'(?:przeciwko|wobec|w\s*stosunku\s*do)\s+('
        r'[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż\s\d\.\-]+?'
        r'(?:Przedsiębiorstwo|Spółka|Firma|Bank|Ubezpieczenia|Sklep|Restauracja))',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:500]

    # 3. Very loose fallback: anything after "przeciwko" / "wobec"
    match = re.search(
        r'(?:przeciwko|wobec)\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż\s\.]+)',
        text, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()[:500]

    return None


# ---------------------------------------------------------------------------
# Public API: extract_clause_with_ai
# ---------------------------------------------------------------------------

def extract_clause_with_ai(pdf_text: str, numer_decyzji: str, backend: Optional[str] = None) -> Dict:
    """Extract the prohibited clause and related metadata from PDF text.

    Behaviour depends on the selected backend (config.PARSER_BACKEND or the
    *backend* argument):

    * rule_based (default) – fully offline heuristic pipeline with Polish
      legal-language rules.  No API keys required.
    * ollama / gemini / openai / claude – calls an LLM (local or cloud).
      Requires the respective package and (for cloud) API key.

    The rule-based pipeline tries three strategies in order:
        1. Explicit marker detection (e.g. "POSTANOWIENIE NIEDOZWOLONE")
        2. Paragraph keyword scoring (density of legal/contract terms)
        3. Fallback keyword search (first substantial paragraph with a keyword)

    Args:
        pdf_text: Raw text extracted from the PDF.
        numer_decyzji: Decision number for logging/context.
        backend: Override the default parser backend.  If None, reads
                 config.PARSER_BACKEND.

    Returns:
        Dictionary with keys:
            - postanowienie_niedozwolone: The extracted clause text (or None)
            - powod: The plaintiff (usually "Prezes UOKiK")
            - pozwany: The defendant company name (or None)
            - confidence: Rough confidence score 0.0–1.0
            - method: Which extraction strategy / backend succeeded
    """
    selected_backend = (backend or PARSER_BACKEND).lower().strip()

    # --- LLM backends ---
    if selected_backend in ("ollama", "gemini", "openai", "claude"):
        if not HAS_LLM:
            print(f"[WARN] LLM backend '{selected_backend}' requested but llm_extractor is not available. "
                  "Falling back to rule_based.")
            selected_backend = "rule_based"
        else:
            if not is_backend_available(selected_backend):
                print(f"[WARN] Backend '{selected_backend}' is not configured (missing package or API key). "
                      "Falling back to rule_based.")
                selected_backend = "rule_based"
            else:
                try:
                    return extract_clause_with_llm(pdf_text, backend=selected_backend)
                except Exception as e:
                    print(f"[WARN] LLM backend '{selected_backend}' failed for {numer_decyzji}: {e}. "
                          "Falling back to rule_based.")
                    selected_backend = "rule_based"

    # --- Rule-based backend (default) ---
    if not pdf_text or not pdf_text.strip():
        return {
            'postanowienie_niedozwolone': None,
            'powod': None,
            'pozwany': None,
            'confidence': 0.0,
            'method': 'no_text'
        }

    normalized = _normalize_text(pdf_text)

    # Strategy 1: explicit markers
    clause_text = _extract_by_markers(normalized)
    method = 'markers'
    confidence = 0.85

    # Strategy 2: keyword scoring
    if not clause_text:
        clause_text = _extract_by_scoring(normalized)
        method = 'scoring'
        confidence = 0.60

    # Strategy 3: fallback
    if not clause_text:
        clause_text = _extract_fallback(normalized)
        method = 'fallback'
        confidence = 0.35

    # If absolutely nothing found, return empty
    if not clause_text:
        return {
            'postanowienie_niedozwolone': None,
            'powod': _extract_powod(normalized),
            'pozwany': None,
            'confidence': 0.0,
            'method': 'none'
        }

    # Extract plaintiff and defendant
    powod = _extract_powod(normalized)
    pozwany = _extract_pozwany(normalized)

    # Truncate very long extracts to avoid storing the entire document
    if len(clause_text) > 3000:
        clause_text = clause_text[:3000] + "..."
        confidence *= 0.8  # Penalty for truncation

    return {
        'postanowienie_niedozwolone': clause_text.strip(),
        'powod': powod,
        'pozwany': pozwany,
        'confidence': round(min(confidence, 1.0), 2),
        'method': method
    }

    return {
        'postanowienie_niedozwolone': clause_text.strip(),
        'powod': powod,
        'pozwany': pozwany,
        'confidence': round(min(confidence, 1.0), 2),
        'method': method
    }


# ---------------------------------------------------------------------------
# Single-decision processing
# ---------------------------------------------------------------------------

def process_decision(decyzja: DecyzjaUOKiK) -> Dict:
    """Process a single decision: read PDF, extract text, and extract clause.

    Args:
        decyzja: DecyzjaUOKiK ORM object with pdf_local_path set.

    Returns:
        Dictionary with:
            - decyzja_id
            - numer_decyzji
            - success (bool)
            - extracted (dict from extract_clause_with_ai)
            - error (str or None)
            - text_length (int or None)
    """
    result = {
        'decyzja_id': decyzja.id,
        'numer_decyzji': decyzja.numer_decyzji,
        'success': False,
        'extracted': None,
        'error': None,
        'text_length': None,
    }

    # Guard: no local path
    if not decyzja.pdf_local_path:
        result['error'] = "No pdf_local_path set for this decision"
        return result

    # Guard: file missing
    if not os.path.exists(decyzja.pdf_local_path):
        result['error'] = f"PDF file not found: {decyzja.pdf_local_path}"
        return result

    try:
        pdf_text = extract_text_from_pdf(decyzja.pdf_local_path)
        result['text_length'] = len(pdf_text)

        if not pdf_text or not pdf_text.strip():
            result['error'] = "PDF text extraction returned empty result"
            return result

        extracted = extract_clause_with_ai(pdf_text, decyzja.numer_decyzji)
        result['extracted'] = extracted
        result['success'] = True

    except FileNotFoundError as e:
        result['error'] = str(e)
    except RuntimeError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f"Unexpected error ({type(e).__name__}): {e}"

    return result


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def process_all_decisions(
    years: Optional[List[int]] = None,
    save_to_db: bool = False,
    dry_run: bool = False
) -> Dict:
    """Process all decisions with status 'pobrane' and extract clauses.

    Args:
        years: Optional list of years to filter (e.g. [2024, 2025]).
               If None, processes all decisions with status='pobrane'.
        save_to_db: If True, also inserts / updates records in the
                    KlauzulaNiedozwolona table with source='decyzje_uokik'.
        dry_run: If True, no database changes are committed (useful for
                 previewing extraction quality).

    Returns:
        Dictionary with statistics:
            {
                'total': int,
                'success': int,
                'failed': int,
                'saved_to_db': int,
                'updated_in_db': int,
                'db_errors': int,
            }
    """
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'saved_to_db': 0,
        'updated_in_db': 0,
        'db_errors': 0,
    }

    db = get_db()
    try:
        query = db.query(DecyzjaUOKiK).filter(
            DecyzjaUOKiK.status_parsowania == 'pobrane'
        )

        if years:
            year_strs = [str(y) for y in years]
            query = query.filter(DecyzjaUOKiK.rok.in_(year_strs))

        decisions = query.all()
        stats['total'] = len(decisions)

        if not decisions:
            print("No decisions with status 'pobrane' found to process.")
            return stats

        print(f"Processing {len(decisions)} decisions...")

        with tqdm(
            total=len(decisions),
            desc="Parsing PDFs",
            unit="pdf",
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
        ) as pbar:
            for decyzja in decisions:
                result = process_decision(decyzja)

                if dry_run:
                    if result['success'] and result['extracted']:
                        preview = result['extracted']['postanowienie_niedozwolone']
                        preview = preview[:120] if preview else "(empty)"
                        print(f"\n  [DRY-RUN] {decyzja.numer_decyzji}  confidence={result['extracted']['confidence']}  method={result['extracted']['method']}")
                        print(f"    Preview: {preview}...")
                    else:
                        print(f"\n  [DRY-RUN] {decyzja.numer_decyzji}  FAILED: {result['error']}")
                    pbar.update(1)
                    continue

                if result['success']:
                    stats['success'] += 1

                    # Update the decision record
                    decyzja.extracted_klauzula = result['extracted']['postanowienie_niedozwolone']
                    decyzja.status_parsowania = 'sparsowane'
                    decyzja.updated_at = datetime.utcnow()

                    # Optionally save to KlauzulaNiedozwolona
                    if save_to_db:
                        try:
                            existing = db.query(KlauzulaNiedozwolona).filter_by(
                                numer_postanowienia=decyzja.numer_decyzji
                            ).first()

                            # Determine pozwany (use extracted or participants fallback)
                            pozwany = result['extracted']['pozwany']
                            if not pozwany and decyzja.uczestnicy_postepowania:
                                pozwany = _extract_pozwany(
                                    "", decyzja.uczestnicy_postepowania
                                )

                            if existing:
                                existing.data_wyroku = decyzja.data_wydania
                                existing.sygnatura = decyzja.sygnatura_akt
                                existing.postanowienie_niedozwolone = result['extracted']['postanowienie_niedozwolone']
                                existing.branza = decyzja.branza
                                existing.powod = result['extracted']['powod']
                                existing.pozwany = pozwany
                                existing.numer_decyzji = decyzja.numer_decyzji
                                existing.paragraf = result['extracted'].get('paragraf')
                                existing.punkt = result['extracted'].get('punkt')
                                existing.source = 'decyzje_uokik'
                                existing.updated_at = datetime.utcnow()
                                stats['updated_in_db'] += 1
                            else:
                                klauzula = KlauzulaNiedozwolona(
                                    numer_postanowienia=decyzja.numer_decyzji,
                                    numer_decyzji=decyzja.numer_decyzji,
                                    data_wyroku=decyzja.data_wydania,
                                    sygnatura=decyzja.sygnatura_akt,
                                    postanowienie_niedozwolone=result['extracted']['postanowienie_niedozwolone'],
                                    branza=decyzja.branza,
                                    powod=result['extracted']['powod'],
                                    pozwany=pozwany,
                                    data_wpisu=None,
                                    zagadnienie=None,
                                    paragraf=result['extracted'].get('paragraf'),
                                    punkt=result['extracted'].get('punkt'),
                                    source='decyzje_uokik',
                                )
                                db.add(klauzula)
                                stats['saved_to_db'] += 1

                            db.commit()

                        except Exception as e:
                            db.rollback()
                            print(f"[DB ERROR] {decyzja.numer_decyzji}: {e}")
                            stats['db_errors'] += 1

                    # Commit the decision status update (separate from Klauzula save)
                    db.commit()

                else:
                    stats['failed'] += 1
                    print(f"[FAIL] {decyzja.numer_decyzji}: {result['error']}")

                    # Mark as error
                    decyzja.status_parsowania = 'blad'
                    db.commit()

                pbar.update(1)

                # Small delay to avoid CPU / I/O thrashing
                time.sleep(random.uniform(0.2, 0.8))

    finally:
        db.close()

    return stats
