"""
OCR extractor module for scanned PDFs that contain no text layer.

Dependencies (listed in pyproject.toml):
    - pdf2image      (PDF -> PIL.Image conversion)
    - pytesseract    (OCR engine wrapper)
    - pillow         (PIL, required by pdf2image)

System dependency:
    - Tesseract OCR must be installed on the system:
        Ubuntu/Debian:  sudo apt-get install tesseract-ocr tesseract-ocr-pol
        Windows:        https://github.com/UB-Mannheim/tesseract/wiki
        macOS:          brew install tesseract tesseract-lang

    - Poppler must be installed (required by pdf2image):
        Ubuntu/Debian:  sudo apt-get install poppler-utils
        Windows:        download poppler-utils binaries and add to PATH
        macOS:          brew install poppler

If OCR dependencies are missing the module gracefully degrades and returns
an empty string with a warning logged to stderr.
"""

import os
import warnings
from typing import Optional

# Optional imports — if they are missing the module still loads but OCR is
# unavailable.
try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except Exception as _exc_pdf2image:  # noqa: F841
    HAS_PDF2IMAGE = False

try:
    import pytesseract
    HAS_TESSERACT = True
except Exception as _exc_tesseract:  # noqa: F841
    HAS_TESSERACT = False

from config import OCR_DPI, OCR_ENABLED


__all__ = ["is_ocr_available", "extract_text_with_ocr"]


def is_ocr_available() -> bool:
    """Return True if both pdf2image and pytesseract are importable."""
    return HAS_PDF2IMAGE and HAS_TESSERACT and OCR_ENABLED


def extract_text_with_ocr(pdf_path: str, dpi: Optional[int] = None) -> str:
    """Extract text from a scanned PDF using OCR.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for PDF-to-image conversion.  Higher = better OCR
             but slower and more memory.  Defaults to config.OCR_DPI (300).

    Returns:
        Extracted text (Polish language assumed).  Empty string if OCR fails
        or is not available.
    """
    if not is_ocr_available():
        warnings.warn(
            "OCR is unavailable: pdf2image or pytesseract not installed, "
            "or OCR_ENABLED=false.  Skipping OCR fallback.",
            stacklevel=2,
        )
        return ""

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    dpi = dpi or OCR_DPI
    text_parts = []

    try:
        images = convert_from_path(pdf_path, dpi=dpi)
    except Exception as exc:
        warnings.warn(
            f"pdf2image failed to convert {pdf_path}: {exc}.  "
            "Is poppler installed and on PATH?",
            stacklevel=2,
        )
        return ""

    for i, image in enumerate(images, start=1):
        try:
            # Polish language model is expected to be installed.
            page_text = pytesseract.image_to_string(image, lang="pol")
            if page_text:
                text_parts.append(page_text)
        except Exception as exc:
            warnings.warn(
                f"OCR failed on page {i} of {pdf_path}: {exc}",
                stacklevel=2,
            )
            continue

    return "\n".join(text_parts)
