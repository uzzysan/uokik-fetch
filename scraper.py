"""
Web scraper for UOKiK unfair contract terms registry.
"""
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from config import UOKIK_MAIN_PAGE, REQUEST_TIMEOUT, REQUEST_HEADERS


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string from UOKiK format to datetime object."""
    if not date_str or date_str.strip() == "":
        return None
    
    try:
        # Try common Polish date format: DD.MM.YYYY or DD-MM-YYYY
        for fmt in ["%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        return None


def fetch_page(url: str, params: Optional[Dict] = None) -> Optional[str]:
    """Fetch a page from UOKiK registry."""
    try:
        response = requests.get(
            url,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {url}: {e}")
        return None


def scrape_page(page_number: int = 0, quiet: bool = False) -> List[Dict]:
    """
    Scrape a specific page from the UOKiK registry.
    
    Args:
        page_number: Page number (0 for first page, 1 for second, etc.)
        quiet: If True, suppress print statements
    
    Returns:
        List of dictionaries containing scraped data.
    """
    if page_number == 0:
        url = UOKIK_MAIN_PAGE
    else:
        url = f"{UOKIK_MAIN_PAGE}?page={page_number}&view="
    
    html = fetch_page(url)
    
    if not html:
        if not quiet:
            print(f"Failed to fetch page {page_number + 1}")
        return []
    
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    
    # Find the results table
    table = soup.find('table', class_='results')
    
    if not table:
        if not quiet:
            print(f"No results table found on page {page_number + 1}")
        return []
    
    # Extract rows from tbody
    tbody = table.find('tbody')
    if not tbody:
        if not quiet:
            print(f"No tbody found on page {page_number + 1}")
        return []
    
    rows = tbody.find_all('tr', class_='result_item')
    
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 9:  # We expect 9 columns
            entry = extract_entry_from_row(cols)
            if entry:
                entries.append(entry)
    
    return entries


def get_total_pages() -> int:
    """
    Get the total number of pages in the registry.
    
    Returns:
        Total number of pages.
    """
    print("Detecting total number of pages...")
    html = fetch_page(UOKIK_MAIN_PAGE)
    
    if not html:
        print("Failed to fetch main page for pagination detection")
        return 1
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Find pagination links
    pagination = soup.find('ul', class_='paginate')
    if not pagination:
        print("No pagination found, assuming single page")
        return 1
    
    # Find all page links and extract the highest page number
    page_links = pagination.find_all('a')
    max_page = 1
    
    for link in page_links:
        href = link.get('href', '')
        if 'page=' in href:
            try:
                page_num = int(href.split('page=')[1].split('&')[0])
                max_page = max(max_page, page_num + 1)  # +1 because pages are 0-indexed
            except (ValueError, IndexError):
                continue
    
    print(f"Found {max_page} pages in total")
    return max_page


def extract_entry_from_row(cols) -> Optional[Dict]:
    """
    Extract entry data from table row columns.
    
    Column structure based on actual UOKiK HTML:
    0: LP (row number)
    1: DATA WYROKU (verdict date)
    2: SYGNATURA (signature)
    3: SĄD (court)
    4: POWÓD (plaintiff)
    5: POZWANY (defendant)
    6: POSTANOWIENIE NIEDOZWOLONE (prohibited clause text)
    7: DATA WPISU (entry date)
    8: BRANŻA (industry)
    """
    try:
        # Extract numer_postanowienia from first column (LP)
        numer_postanowienia = cols[0].get_text(strip=True) if len(cols) > 0 else None
        
        if not numer_postanowienia:
            return None
        
        entry = {
            'numer_postanowienia': numer_postanowienia,
            'data_wyroku': parse_date(cols[1].get_text(strip=True)) if len(cols) > 1 else None,
            'sygnatura': cols[2].get_text(strip=True) if len(cols) > 2 else None,
            'postanowienie_niedozwolone': cols[6].get_text(strip=True) if len(cols) > 6 else None,
            'branza': cols[8].get_text(strip=True) if len(cols) > 8 else None,
            'powod': cols[4].get_text(strip=True) if len(cols) > 4 else None,
            'pozwany': cols[5].get_text(strip=True) if len(cols) > 5 else None,
            'data_wpisu': parse_date(cols[7].get_text(strip=True)) if len(cols) > 7 else None,
            'zagadnienie': None  # This field is not in the table, may need separate lookup
        }
        return entry
    except Exception as e:
        print(f"Error extracting entry from row: {e}")
        return None


def scrape_all_pages(save_callback=None):
    """
    Scrape all pages from the UOKiK registry.
    
    Implements random delays (2-5 seconds) between page requests
    to avoid overloading the server.
    
    Args:
        save_callback: Optional function to call after each page is scraped.
                      Should accept a list of entries as parameter.
    
    Returns:
        Dictionary with scraping statistics.
    """
    total_entries = 0
    total_saved = 0
    total_skipped = 0
    
    # Detect total number of pages
    total_pages = get_total_pages()
    print(f"\nStarting to scrape {total_pages} pages...")
    print("(Using 2-5 second delays between requests to avoid server overload)\n")
    
    # Scrape each page with progress bar
    with tqdm(total=total_pages, desc="Scraping", unit="page", 
              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
        
        for page_num in range(total_pages):
            entries = scrape_page(page_num, quiet=True)
            
            # Save entries immediately if callback provided
            if save_callback and entries:
                result = save_callback(entries)
                if result:
                    saved, skipped = result
                    total_saved += saved
                    total_skipped += skipped
            
            total_entries += len(entries)
            
            # Update progress bar with statistics
            pbar.set_postfix({
                'entries': total_entries,
                'saved': total_saved,
                'skipped': total_skipped
            })
            pbar.update(1)
            
            # Add random delay between requests (except after the last page)
            if page_num < total_pages - 1:
                delay = random.uniform(2.0, 5.0)
                time.sleep(delay)
    
    print(f"\n✓ Completed scraping all {total_pages} pages")
    print(f"✓ Total entries collected: {total_entries}")
    
    return {'total_pages': total_pages, 'total_entries': total_entries}
