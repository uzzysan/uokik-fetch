"""
Main script to run the UOKiK registry scraper.
"""
from sqlalchemy.exc import IntegrityError
from database import init_db, get_db
from models import KlauzulaNiedozwolona
from scraper import scrape_all_pages


def save_entries_to_db(entries):
    """Save scraped entries to the database."""
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
                print(f"Saved: {entry['numer_postanowienia']}")
                
            except IntegrityError as e:
                db.rollback()
                print(f"Integrity error for {entry.get('numer_postanowienia')}: {e}")
                skipped_count += 1
            except Exception as e:
                db.rollback()
                print(f"Error saving entry {entry.get('numer_postanowienia')}: {e}")
                error_count += 1
    
    finally:
        db.close()
    
    return saved_count, skipped_count, error_count


def main():
    """Main function to orchestrate the scraping and database operations."""
    print("=" * 60)
    print("UOKiK Unfair Contract Terms Scraper")
    print("=" * 60)
    
    # Initialize database
    print("\n1. Initializing database...")
    init_db()
    
    # Scrape data
    print("\n2. Scraping data from UOKiK registry...")
    entries = scrape_all_pages()
    
    if not entries:
        print("\nNo entries found. Please check the scraper logic.")
        return
    
    print(f"\nFound {len(entries)} entries")
    
    # Save to database
    print("\n3. Saving entries to database...")
    saved, skipped, errors = save_entries_to_db(entries)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total entries found: {len(entries)}")
    print(f"  Successfully saved: {saved}")
    print(f"  Skipped (duplicates): {skipped}")
    print(f"  Errors: {errors}")
    print("=" * 60)
    print("\nDone!")


if __name__ == "__main__":
    main()
