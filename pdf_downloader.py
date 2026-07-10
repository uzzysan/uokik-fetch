"""
PDF downloader module for UOKiK decisions from decyzje.uokik.gov.pl.

Because the site is protected by Imperva TSPD WAF, plain HTTP requests are
blocked.  This module uses undetected-chromedriver (a real browser) to:
  1. Navigate to the decision detail page (passing the JS challenge)
  2. Download the PDF via XMLHttpRequest inside the browser (same origin)
  3. Decode the base64 response and save it to disk

The browser is closed after each batch to avoid stale sessions.
"""

import os
import base64
import time
import random
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from models import DecyzjaUOKiK, DecyzjaPDF
from config import REQUEST_HEADERS, REQUEST_TIMEOUT

try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False


def ensure_pdf_filename(pdf_url: str, numer_decyzji: str) -> str:
    """Generate a safe filename for a PDF from the URL or decision number."""
    if pdf_url and '/' in pdf_url:
        url_filename = pdf_url.split('/')[-1]
        if url_filename and url_filename.endswith('.pdf'):
            safe_name = re.sub(r'[^\w\-_.]', '_', url_filename)
            return safe_name
    if numer_decyzji:
        safe = re.sub(r'[^\w\-]', '_', numer_decyzji)
        return f"{safe}.pdf"
    return f"decyzja_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"


def _init_driver():
    """Start an undetected Chrome instance."""
    if not HAS_UC:
        raise RuntimeError(
            "undetected-chromedriver is not installed. "
            "Install it with: pip install undetected-chromedriver"
        )
    options = uc.ChromeOptions()
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            options.binary_location = path
            break
    driver = uc.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _download_pdf_via_browser_xhr(driver, pdf_url: str) -> Optional[bytes]:
    """
    Download a PDF via XMLHttpRequest inside the browser.

    The browser must already be on a page from the same origin
    (decyzje.uokik.gov.pl) so that the TSPD session is active.
    """
    js = f"""
    return new Promise((resolve) => {{
        const xhr = new XMLHttpRequest();
        xhr.open('GET', '{pdf_url}');
        xhr.responseType = 'arraybuffer';
        xhr.onload = () => {{
            if (xhr.status !== 200) {{
                resolve(JSON.stringify({{status: xhr.status, error: 'HTTP ' + xhr.status}}));
                return;
            }}
            const bytes = new Uint8Array(xhr.response);
            let binary = '';
            const chunk = 65536;
            for (let i = 0; i < bytes.length; i += chunk) {{
                binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
            }}
            const base64 = btoa(binary);
            resolve(JSON.stringify({{status: 200, size: bytes.length, base64: base64}}));
        }};
        xhr.onerror = () => {{
            resolve(JSON.stringify({{status: 0, error: 'Network error'}}));
        }};
        xhr.send();
    }});
    """
    try:
        result = driver.execute_script(js)
        if isinstance(result, str):
            import json
            data = json.loads(result)
            if data.get("status") != 200:
                print(f"[ERROR] XHR failed: {data.get('error')}")
                return None
            b64 = data.get("base64", "")
            if not b64:
                return None
            return base64.b64decode(b64)
        return None
    except Exception as e:
        print(f"[ERROR] XHR exception: {e}")
        return None


def download_pdf(decyzja: DecyzjaUOKiK, output_dir: str = "pdfs") -> Tuple[Optional[str], bool]:
    """
    Download the PDF for a single UOKiK decision using a real browser.

    Updates the database record with:
      - pdf_local_path
      - status_parsowania = 'pobrane'
      - Creates/updates DecyzjaPDF record

    Returns:
        Tuple of (local_path, was_already_existing).
    """
    if not decyzja.pdf_url:
        print(f"[SKIP] No PDF URL for decision {decyzja.numer_decyzji}")
        return None, False

    filename = ensure_pdf_filename(decyzja.pdf_url, decyzja.numer_decyzji)
    year = decyzja.rok or "unknown"
    year_dir = os.path.join(output_dir, year)
    os.makedirs(year_dir, exist_ok=True)

    local_path = os.path.join(year_dir, filename)
    local_path = os.path.abspath(local_path)

    # Skip if already downloaded and valid
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        print(f"[SKIP] Already exists: {local_path}")
        _update_decyzja_after_download(decyzja, local_path, decyzja.pdf_url, os.path.getsize(local_path))
        return local_path, True

    driver = None
    try:
        driver = _init_driver()

        # Navigate to the detail page first (same origin required for XHR)
        detail_url = f"https://decyzje.uokik.gov.pl/bp/dec_prez.nsf/1/{decyzja.unid}?editDocument&act=Decyzja"
        print(f"[NAVIGATE] {decyzja.numer_decyzji}")
        driver.get(detail_url)
        time.sleep(random.uniform(4, 7))

        # Wait for TSPD if the page shows challenge
        if "Request Rejected" in driver.page_source:
            time.sleep(random.uniform(4, 8))
            driver.get(detail_url)
            time.sleep(random.uniform(4, 8))

        if "Request Rejected" in driver.page_source:
            print(f"[ERROR] TSPD rejected detail page for {decyzja.numer_decyzji}")
            _set_decyzja_error(decyzja, "TSPD rejected detail page")
            return None, False

        print(f"[DOWNLOAD] {decyzja.numer_decyzji} -> {filename}")
        pdf_bytes = _download_pdf_via_browser_xhr(driver, decyzja.pdf_url)

        if not pdf_bytes:
            print(f"[ERROR] XHR returned no data for {decyzja.numer_decyzji}")
            _set_decyzja_error(decyzja, "XHR PDF download returned no data")
            return None, False

        # Validate PDF header
        if pdf_bytes[:4] != b'%PDF':
            print(f"[ERROR] Downloaded file is not a valid PDF for {decyzja.numer_decyzji} (header: {pdf_bytes[:4]})")
            _set_decyzja_error(decyzja, "Downloaded file is not a valid PDF")
            return None, False

        with open(local_path, 'wb') as f:
            f.write(pdf_bytes)

        file_size = len(pdf_bytes)
        print(f"[OK] Saved {file_size} bytes to {local_path}")

        _update_decyzja_after_download(decyzja, local_path, decyzja.pdf_url, file_size)
        return local_path, False

    except Exception as e:
        print(f"[ERROR] Unexpected error downloading {decyzja.numer_decyzji}: {e}")
        _set_decyzja_error(decyzja, f"Unexpected error: {e}")
        return None, False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _update_decyzja_after_download(decyzja: DecyzjaUOKiK, local_path: str, pdf_url: str, file_size: int) -> None:
    """Update database records after successful PDF download."""
    db = get_db()
    try:
        db_decyzja = db.query(DecyzjaUOKiK).filter_by(id=decyzja.id).first()
        if not db_decyzja:
            print(f"[WARN] Decision id={decyzja.id} not found in DB during update")
            return

        db_decyzja.pdf_local_path = local_path
        db_decyzja.pdf_filename = os.path.basename(local_path)
        db_decyzja.status_parsowania = 'pobrane'
        db_decyzja.updated_at = datetime.utcnow()

        pdf_record = db.query(DecyzjaPDF).filter_by(decyzja_id=db_decyzja.id).first()
        if pdf_record:
            pdf_record.local_path = local_path
            pdf_record.file_size = file_size
            pdf_record.download_date = datetime.utcnow()
        else:
            pdf_record = DecyzjaPDF(
                decyzja_id=db_decyzja.id,
                pdf_url=pdf_url,
                local_path=local_path,
                file_size=file_size,
                download_date=datetime.utcnow()
            )
            db.add(pdf_record)

        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        print(f"[ERROR] DB update failed after download: {e}")
    finally:
        db.close()


def _set_decyzja_error(decyzja: DecyzjaUOKiK, error_msg: str) -> None:
    """Set decision status to 'blad' on download failure."""
    db = get_db()
    try:
        db_decyzja = db.query(DecyzjaUOKiK).filter_by(id=decyzja.id).first()
        if db_decyzja:
            db_decyzja.status_parsowania = 'blad'
            db_decyzja.updated_at = datetime.utcnow()
            db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        print(f"[ERROR] Failed to set error status: {e}")
    finally:
        db.close()


def download_all_pdfs(years: List[int] = None, output_dir: str = "pdfs") -> Dict:
    """
    Download PDFs for all UOKiK decisions with status 'nowe'.
    """
    db = get_db()
    try:
        query = db.query(DecyzjaUOKiK).filter(
            DecyzjaUOKiK.status_parsowania == 'nowe'
        )

        if years:
            year_strs = [str(y) for y in years]
            query = query.filter(DecyzjaUOKiK.rok.in_(year_strs))

        decisions = query.all()
        total = len(decisions)

        if total == 0:
            print("No decisions with status='nowe' found.")
            return {'total': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0, 'output_dir': os.path.abspath(output_dir)}

        print(f"\nFound {total} decisions to download.")
        print(f"Output directory: {os.path.abspath(output_dir)}")
        print(f"Using undetected-chromedriver + XHR for downloads.\n")

        downloaded = 0
        skipped = 0
        failed = 0

        with tqdm(total=total, desc="Downloading PDFs", unit="file",
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            for i, decyzja in enumerate(decisions):
                result_path, was_existing = download_pdf(decyzja, output_dir=output_dir)
                if result_path:
                    if was_existing:
                        skipped += 1
                    else:
                        downloaded += 1
                else:
                    failed += 1

                pbar.set_postfix({'downloaded': downloaded, 'skipped': skipped, 'failed': failed})
                pbar.update(1)

                if i < total - 1:
                    delay = random.uniform(3.0, 7.0)
                    time.sleep(delay)

        print(f"\n✓ PDF download complete")
        print(f"  Total: {total}")
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped (already existed): {skipped}")
        print(f"  Failed: {failed}")

        return {
            'total': total,
            'downloaded': downloaded,
            'skipped': skipped,
            'failed': failed,
            'output_dir': os.path.abspath(output_dir)
        }

    finally:
        db.close()
