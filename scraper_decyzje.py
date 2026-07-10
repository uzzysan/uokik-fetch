"""
Web scraper for UOKiK decisions from decyzje.uokik.gov.pl (Lotus Notes/Domino).

The site is protected by Imperva TSPD WAF, which blocks plain HTTP requests.
This module uses undetected-chromedriver (a real browser) to pass the JS
challenge and maintain the session cookies required to access the search form.

Because uc.Chrome() spins up a real browser window, the scraper is slower
than requests but can reliably bypass the WAF.
"""

import time
import random
import re
import os
from datetime import datetime
from typing import List, Dict, Optional

from bs4 import BeautifulSoup
from tqdm import tqdm

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.support.ui import Select
    HAS_UC = True
except ImportError:
    HAS_UC = False

from config import REQUEST_TIMEOUT, REQUEST_HEADERS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DECYZJE_BASE_URL = "https://decyzje.uokik.gov.pl"
SEARCH_FORM_URL = f"{DECYZJE_BASE_URL}/bp/dec_prez.nsf/UOKiK?OpenForm"
DECISION_DETAIL_URL_TEMPLATE = f"{DECYZJE_BASE_URL}/bp/dec_prez.nsf/1/{{unid}}?editDocument&act=Decyzja"

DETAIL_LINK_PATTERN = re.compile(r"/bp/dec_prez\.nsf/1/([^?]+)\?editDocument&act=Decyzja")


__all__ = [
    "parse_date",
    "fetch_search_results",
    "fetch_decision_detail",
    "scrape_all_decisions",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string from UOKiK format to a datetime.date object."""
    if not date_str or date_str.strip() == "":
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _extract_unid_from_url(href: str) -> Optional[str]:
    """Extract the Lotus Notes UNID from a decision detail URL."""
    match = DETAIL_LINK_PATTERN.search(href)
    return match.group(1) if match else None


def _init_driver():
    """Start an undetected Chrome instance."""
    if not HAS_UC:
        raise RuntimeError(
            "undetected-chromedriver is not installed. "
            "Install it with: pip install undetected-chromedriver"
        )
    options = uc.ChromeOptions()
    # Try to locate Chrome binary on Windows / common paths
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


# ---------------------------------------------------------------------------
# WebBridge fallback helpers
# ---------------------------------------------------------------------------

def _try_webbridge_navigate(url: str) -> bool:
    """Try to navigate using WebBridge. Returns True if successful."""
    try:
        import webbridge_client as wb
        wb.navigate(url, new_tab=False, session="uokik-scraper")
        return True
    except Exception:
        return False


def _try_webbridge_submit(year: int) -> str:
    """Submit the form via WebBridge evaluate. Returns JS result."""
    import webbridge_client as wb
    js = f"""
    (() => {{
        const s1 = document.querySelector('select[name="PraktykaPyt"]');
        if (s1) {{ const opt = Array.from(s1.options).find(o => o.text.trim() === 'Klauzule niedozwolone');
            if (opt) {{ s1.value = opt.value; opt.selected = true; s1.dispatchEvent(new Event('change', {{bubbles: true}})); }}
        }}
        const s2 = document.querySelector('select[name="dataRR"]');
        if (s2) {{ const opt2 = Array.from(s2.options).find(o => o.text.trim() === '{year}');
            if (opt2) {{ s2.value = opt2.value; opt2.selected = true; s2.dispatchEvent(new Event('change', {{bubbles: true}})); }}
        }}
        const btn = document.querySelector('input.btn.btn-default[type="button"]');
        if (btn) {{ btn.click(); return 'clicked'; }}
        return 'no button';
    }})()
    """
    return wb.evaluate(js, session="uokik-scraper")


def _human_like_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> None:
    """Wait a random amount of time to mimic human behaviour."""
    time.sleep(random.uniform(min_sec, max_sec))


# ---------------------------------------------------------------------------
# Search results
# ---------------------------------------------------------------------------

def fetch_search_results(year: int) -> List[Dict]:
    """
    Search for decisions in a given year using a browser.

    Tries undetected-chromedriver first, then falls back to WebBridge.
    """
    results: List[Dict] = []
    driver = None
    try:
        driver = _init_driver()
        driver.get(SEARCH_FORM_URL)
        # Wait for TSPD challenge to resolve and the form to appear
        time.sleep(random.uniform(6, 10))

        # If page is rejected, try once more after a short pause
        if "Request Rejected" in driver.page_source:
            _human_like_delay(4, 8)
            driver.get(SEARCH_FORM_URL)
            time.sleep(random.uniform(6, 10))

        html = driver.page_source
        if "Request Rejected" in html:
            print(f"[Year {year}] TSPD rejected the request. Try again later or use a different IP.")
            return []

        if 'canvas' in html.lower() and 'form' not in html.lower():
            # Still showing challenge; wait a bit longer
            time.sleep(random.uniform(8, 14))

        # Simulate reading the page before filling the form
        _human_like_delay(1.5, 3.5)

        # Fill form
        Select(driver.find_element("name", "PraktykaPyt")).select_by_visible_text("Klauzule niedozwolone")
        _human_like_delay(0.5, 1.2)
        Select(driver.find_element("name", "dataRR")).select_by_visible_text(str(year))
        _human_like_delay(0.8, 1.8)
        driver.execute_script("document.querySelector('input.btn.btn-default[type=\"button\"]').click();")
        time.sleep(random.uniform(4, 8))

        # Wait for results page
        for _ in range(10):
            if "SearchView" in driver.current_url:
                break
            time.sleep(random.uniform(0.8, 1.5))

        # Extract links
        soup = BeautifulSoup(driver.page_source, "lxml")
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            match = DETAIL_LINK_PATTERN.search(href)
            if match:
                unid = match.group(1)
                numer = link.get_text(strip=True)
                if unid and numer:
                    results.append({
                        "unid": unid,
                        "numer_decyzji": numer,
                        "detail_url": f"{DECYZJE_BASE_URL}{href}" if href.startswith("/") else href,
                    })

        # Deduplicate by UNID
        seen = set()
        unique = []
        for r in results:
            if r["unid"] not in seen:
                seen.add(r["unid"])
                unique.append(r)
        results = unique

        print(f"[Year {year}] Found {len(results)} decisions.")
        return results

    except Exception as e:
        print(f"[Year {year}] Error fetching search results: {e}")
        return []
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Decision detail
# ---------------------------------------------------------------------------

def fetch_decision_detail(unid: str) -> Dict:
    """
    Fetch and parse a single decision detail page using the browser.
    """
    url = DECISION_DETAIL_URL_TEMPLATE.format(unid=unid)
    driver = None
    try:
        driver = _init_driver()
        driver.get(url)
        time.sleep(random.uniform(3, 6))

        # Micro-pause to simulate reading
        _human_like_delay(1.0, 2.5)

        soup = BeautifulSoup(driver.page_source, "lxml")
        data = {
            "unid": unid,
            "numer_decyzji": None,
            "data_wydania": None,
            "sygnatura_akt": None,
            "uczestnicy_postepowania": None,
            "rodzaj_praktyki": None,
            "kara": None,
            "branza": None,
            "region": None,
            "odwolanie_do_sadu": None,
            "orzecznictwo": None,
            "pdf_url": None,
            "pdf_filename": None,
        }

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                label = cols[0].get_text(strip=True)
                value_cell = cols[1]
                value = value_cell.get_text(strip=True)

                if "Numer decyzji" in label:
                    data["numer_decyzji"] = value or None
                elif "Data wydania decyzji" in label:
                    data["data_wydania"] = parse_date(value)
                elif "Sygnatura akt" in label:
                    data["sygnatura_akt"] = value or None
                elif "Uczestnicy postępowania" in label:
                    data["uczestnicy_postepowania"] = value or None
                elif "Rodzaj praktyki" in label:
                    data["rodzaj_praktyki"] = value or None
                elif "Kara" in label:
                    data["kara"] = value or None
                elif "Branża" in label:
                    data["branza"] = value or None
                elif "Region" in label:
                    data["region"] = value or None
                elif "Odwołanie do sądu" in label:
                    data["odwolanie_do_sadu"] = value or None
                elif "Orzecznictwo" in label:
                    data["orzecznictwo"] = value or None
                elif "Decyzja" in label:
                    pdf_link = value_cell.find("a", href=True)
                    if pdf_link:
                        pdf_href = pdf_link.get("href", "")
                        if pdf_href:
                            data["pdf_url"] = f"{DECYZJE_BASE_URL}{pdf_href}" if pdf_href.startswith("/") else pdf_href
                            data["pdf_filename"] = pdf_link.get_text(strip=True) or None

        return data
    except Exception as e:
        print(f"[UNID {unid}] Error fetching detail: {e}")
        return {"unid": unid}
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def scrape_all_decisions(
    years: List[int] = None,
    save_callback=None,
) -> Dict:
    """
    Scrape decisions for the specified years using a real browser.
    """
    if years is None:
        years = list(range(2017, 2027))

    stats = {
        "total_years": len(years),
        "total_decisions": 0,
        "successful_details": 0,
        "failed_details": 0,
        "saved": 0,
        "skipped": 0,
        "errors": 0,
    }

    for year_idx, year in enumerate(
        tqdm(years, desc="Years", unit="year", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]")
    ):
        try:
            results = fetch_search_results(year)
        except Exception as e:
            print(f"[Year {year}] Unexpected error fetching search results: {e}")
            stats["errors"] += 1
            continue

        stats["total_decisions"] += len(results)

        if not results:
            continue

        for decision in tqdm(
            results,
            desc=f"Year {year}",
            unit="decision",
            leave=False,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ):
            try:
                detail = fetch_decision_detail(decision["unid"])
                decision.update(detail)
                decision["rok"] = str(year)
                stats["successful_details"] += 1
            except Exception as e:
                print(f"[{decision.get('unid', '?')}] Error fetching detail: {e}")
                stats["failed_details"] += 1
                continue

            if save_callback is not None:
                try:
                    result = save_callback(decision)
                    if result and isinstance(result, (tuple, list)) and len(result) >= 2:
                        stats["saved"] += int(result[0])
                        stats["skipped"] += int(result[1])
                except Exception as e:
                    print(f"[{decision.get('unid', '?')}] Error in save callback: {e}")
                    stats["errors"] += 1

            _human_like_delay(2.5, 5.5)

        if year_idx < len(years) - 1:
            _human_like_delay(4.0, 9.0)

    return stats
