"""
Web scraper for UOKiK unfair contract terms registry.
"""
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
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


def scrape_main_page() -> List[Dict]:
    """
    Scrape the main UOKiK registry page and extract all entries.
    
    Returns:
        List of dictionaries containing scraped data.
    """
    print(f"Fetching main page: {UOKIK_MAIN_PAGE}")
    html = fetch_page(UOKIK_MAIN_PAGE)
    
    if not html:
        print("Failed to fetch main page")
        return []
    
    soup = BeautifulSoup(html, 'lxml')
    entries = []
    
    # Look for the main results table
    # Based on the HTML structure, we need to find the table with results
    results_div = soup.find('div', {'id': 'advancedResults'})
    
    if not results_div:
        # Try to find any table that might contain the data
        print("Looking for data in tables...")
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip header row
                cols = row.find_all('td')
                if len(cols) >= 4:  # We need at least 4 columns
                    entry = extract_entry_from_row(cols)
                    if entry:
                        entries.append(entry)
    else:
        # Process the results div
        rows = results_div.find_all('div', class_='row')
        for row in rows:
            entry = extract_entry_from_div(row)
            if entry:
                entries.append(entry)
    
    print(f"Scraped {len(entries)} entries")
    return entries


def extract_entry_from_row(cols) -> Optional[Dict]:
    """Extract entry data from table row columns."""
    try:
        # This function will need to be adjusted based on actual table structure
        # For now, we'll extract what we can
        entry = {
            'numer_postanowienia': cols[0].get_text(strip=True) if len(cols) > 0 else None,
            'data_wyroku': parse_date(cols[1].get_text(strip=True)) if len(cols) > 1 else None,
            'sygnatura': cols[2].get_text(strip=True) if len(cols) > 2 else None,
            'postanowienie_niedozwolone': cols[3].get_text(strip=True) if len(cols) > 3 else None,
            'branza': cols[4].get_text(strip=True) if len(cols) > 4 else None,
            'powod': cols[5].get_text(strip=True) if len(cols) > 5 else None,
            'pozwany': cols[6].get_text(strip=True) if len(cols) > 6 else None,
            'data_wpisu': parse_date(cols[7].get_text(strip=True)) if len(cols) > 7 else None,
            'zagadnienie': None
        }
        return entry if entry['numer_postanowienia'] else None
    except Exception as e:
        print(f"Error extracting entry from row: {e}")
        return None


def extract_entry_from_div(div) -> Optional[Dict]:
    """Extract entry data from div element."""
    try:
        # This will need adjustment based on actual page structure
        entry = {
            'numer_postanowienia': None,
            'data_wyroku': None,
            'sygnatura': None,
            'postanowienie_niedozwolone': None,
            'branza': None,
            'powod': None,
            'pozwany': None,
            'data_wpisu': None,
            'zagadnienie': None
        }
        
        # Extract text content and try to map fields
        text = div.get_text(strip=True)
        # Further parsing logic needed based on actual structure
        
        return entry if entry['numer_postanowienia'] else None
    except Exception as e:
        print(f"Error extracting entry from div: {e}")
        return None


def scrape_all_pages() -> List[Dict]:
    """
    Scrape all pages from the UOKiK registry.
    
    Returns:
        List of all scraped entries from all pages.
    """
    all_entries = []
    
    # Start with the main page
    entries = scrape_main_page()
    all_entries.extend(entries)
    
    # TODO: Implement pagination if the site has multiple pages
    # This would require analyzing the pagination structure
    
    return all_entries
