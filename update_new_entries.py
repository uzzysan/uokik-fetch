#!/usr/bin/env python3
"""
Incremental update script for UOKiK registry.

This script checks the database for the highest entry number and fetches
only new entries from the UOKiK registry that have a higher number.

Usage:
    uv run update_new_entries.py
"""
import sys
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from database import init_db, get_db, engine
from models import KlauzulaNiedozwolona
from scraper import scrape_page, fetch_page
from main import save_entries_to_db, test_database_connection
from bs4 import BeautifulSoup
from config import UOKIK_MAIN_PAGE


def get_max_entry_number_from_db() -> int:
    """
    Get the highest entry number (numer_postanowienia) from the database.
    
    Returns:
        Highest entry number as integer, or 0 if database is empty
    """
    db = get_db()
    try:
        # Query for max numer_postanowienia
        result = db.query(KlauzulaNiedozwolona.numer_postanowienia).order_by(
            KlauzulaNiedozwolona.numer_postanowienia.desc()
        ).first()
        
        if result and result[0]:
            max_num = int(result[0])
            print(f"Highest entry in database: {max_num}")
            return max_num
        else:
            print("Database is empty")
            return 0
    finally:
        db.close()


def get_newest_entries_from_site(max_db_number: int, max_pages: int = 5):
    """
    Fetch new entries from the UOKiK site that have higher numbers than database.
    
    Args:
        max_db_number: Highest entry number currently in database
        max_pages: Maximum number of pages to check (default 5)
    
    Returns:
        List of new entries
    """
    print(f"\nChecking first {max_pages} pages for entries > {max_db_number}...")
    
    new_entries = []
    pages_checked = 0
    found_old_entry = False
    
    for page_num in range(max_pages):
        print(f"\nChecking page {page_num + 1}...")
        entries = scrape_page(page_num, quiet=False)
        
        page_has_new = False
        for entry in entries:
            entry_num = int(entry['numer_postanowienia'])
            
            if entry_num > max_db_number:
                new_entries.append(entry)
                page_has_new = True
                print(f"  ✓ Found new entry: {entry_num}")
            else:
                # We found an old entry - site is ordered by newest first
                # So we can stop checking if we've already found some new ones
                if new_entries:
                    print(f"  → Reached existing entries (found {entry_num})")
                    found_old_entry = True
                    break
        
        pages_checked += 1
        
        # If this page had no new entries and we found old ones, stop
        if not page_has_new and found_old_entry:
            print(f"\n→ Stopping: no new entries on page {page_num + 1}")
            break
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Pages checked: {pages_checked}")
    print(f"  New entries found: {len(new_entries)}")
    print(f"{'='*60}")
    
    return new_entries


def main():
    """Main function to update database with new entries."""
    print("=" * 60)
    print("UOKiK Registry - Incremental Update")
    print("=" * 60)
    
    # Test database connection
    print("\n1. Testing database connection...")
    if not test_database_connection():
        print("\n✗ Aborting: Cannot connect to database")
        sys.exit(1)
    
    # Initialize database (create tables if needed)
    print("\n2. Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        sys.exit(1)
    
    # Get highest entry number from database
    print("\n3. Checking database for highest entry number...")
    max_db_number = get_max_entry_number_from_db()
    
    if max_db_number == 0:
        print("\n⚠ Database is empty. Please run full scraper first:")
        print("  uv run main.py")
        sys.exit(1)
    
    # Fetch new entries from site
    print(f"\n4. Fetching new entries from UOKiK site...")
    new_entries = get_newest_entries_from_site(max_db_number)
    
    if not new_entries:
        print("\n✓ No new entries found. Database is up to date!")
        return 0
    
    # Save new entries to database
    print(f"\n5. Saving {len(new_entries)} new entries to database...")
    saved, skipped, errors = save_entries_to_db(new_entries, quiet=False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Update Summary:")
    print(f"  New entries found: {len(new_entries)}")
    print(f"  Successfully saved: {saved}")
    print(f"  Skipped (duplicates): {skipped}")
    print(f"  Errors: {errors}")
    print("=" * 60)
    
    if saved > 0:
        print(f"\n✓ Database updated successfully with {saved} new entries!")
    else:
        print("\n⚠ No entries were saved (all might be duplicates)")
    
    return 0


if __name__ == "__main__":
    exit(main())
