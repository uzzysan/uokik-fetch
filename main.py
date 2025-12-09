"""
Main script to run the UOKiK registry scraper.
"""
import sys
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from database import init_db, get_db, engine
from models import KlauzulaNiedozwolona
from scraper import scrape_all_pages
from config import DATABASE_URL


def save_entries_to_db(entries, quiet=True):
    """Save scraped entries to the database.
    
    Args:
        entries: List of entries to save
        quiet: If True, suppress individual entry print statements
    """
    db = get_db()
    saved_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        for entry in entries:
            try:
                # Check if entry already exists
                existing = db.query(KlauzulaNiedozwolona).filter_by(
                    numer_postanowienia=entry['numer_postanowienia']
                ).first()
                
                if existing:
                    if not quiet:
                        print(f"Skipping duplicate entry: {entry['numer_postanowienia']}")
                    skipped_count += 1
                    continue
                
                # Create new entry
                klauzula = KlauzulaNiedozwolona(
                    numer_postanowienia=entry['numer_postanowienia'],
                    data_wyroku=entry['data_wyroku'],
                    sygnatura=entry['sygnatura'],
                    postanowienie_niedozwolone=entry['postanowienie_niedozwolone'],
                    branza=entry['branza'],
                    powod=entry.get('powod'),
                    pozwany=entry.get('pozwany'),
                    data_wpisu=entry.get('data_wpisu'),
                    zagadnienie=entry.get('zagadnienie')
                )
                
                db.add(klauzula)
                db.commit()
                saved_count += 1
                if not quiet:
                    print(f"Saved: {entry['numer_postanowienia']}")
                
            except IntegrityError as e:
                db.rollback()
                if not quiet:
                    print(f"Integrity error for {entry.get('numer_postanowienia')}: {e}")
                skipped_count += 1
            except Exception as e:
                db.rollback()
                if not quiet:
                    print(f"Error saving entry {entry.get('numer_postanowienia')}: {e}")
                error_count += 1
    
    finally:
        db.close()
    
    return saved_count, skipped_count, error_count


def test_database_connection():
    """Test database connection before starting the scraper."""
    print("Testing database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print("✓ Database connection successful")
        return True
    except OperationalError as e:
        print("✗ Failed to connect to database:")
        print(f"  {e}")
        print(f"\nDatabase URL: {DATABASE_URL.replace(':jakieshaslo@', ':***@')}")
        print("\nPlease check:")
        print("  1. Database server is running")
        print("  2. Connection details in .env file are correct")
        print("  3. Network connectivity to database server")
        return False
    except Exception as e:
        print("✗ Unexpected error testing database connection:")
        print(f"  {e}")
        return False


def main():
    """Main function to orchestrate the scraping and database operations."""
    print("=" * 60)
    print("UOKiK Unfair Contract Terms Scraper")
    print("=" * 60)
    
    # Test database connection first
    print("\n1. Testing database connection...")
    if not test_database_connection():
        print("\n✗ Aborting: Cannot connect to database")
        sys.exit(1)
    
    # Initialize database
    print("\n2. Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        sys.exit(1)
    
    # Statistics tracking
    total_saved = 0
    total_skipped = 0
    total_errors = 0
    
    # Define callback to save entries after each page
    def save_page_entries(entries):
        nonlocal total_saved, total_skipped, total_errors
        saved, skipped, errors = save_entries_to_db(entries)
        total_saved += saved
        total_skipped += skipped
        total_errors += errors
        return (saved, skipped)  # Return for progress bar update
    
    # Scrape data and save incrementally
    print("\n3. Scraping data from UOKiK registry (saving after each page)...")
    result = scrape_all_pages(save_callback=save_page_entries)
    
    if result['total_entries'] == 0:
        print("\n✗ No entries found. Please check the scraper logic.")
        sys.exit(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total pages scraped: {result['total_pages']}")
    print(f"  Total entries found: {result['total_entries']}")
    print(f"  Successfully saved: {total_saved}")
    print(f"  Skipped (duplicates): {total_skipped}")
    print(f"  Errors: {total_errors}")
    print("=" * 60)
    print("\nDone!")


if __name__ == "__main__":
    main()
