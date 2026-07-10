#!/usr/bin/env python3
"""
CLI script to parse PDFs from UOKiK decisions and extract unfair contract clauses.

Usage:
    python parse_pdfs.py
    python parse_pdfs.py --years 2024,2025
    python parse_pdfs.py --dry-run
    python parse_pdfs.py --save-to-db --years 2020,2021,2022

This script:
  1. Tests the database connection
  2. Initializes the database (creates tables if missing)
  3. Queries decisions with status='pobrane' (optionally filtered by year)
  4. Extracts text from each PDF using pdfplumber / pypdf
  5. Runs rule-based clause extraction (offline, no API keys)
  6. Updates the DecyzjaUOKiK record and optionally saves to KlauzulaNiedozwolona
  7. Prints a summary of the operation
"""
import sys
import argparse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import init_db, get_db, engine
from pdf_parser import process_all_decisions
from models import DecyzjaUOKiK
from config import DATABASE_URL


def test_database_connection():
    """Test database connection before starting the parser."""
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


def print_summary(stats):
    """Print a formatted summary of the parsing operation."""
    print("\n" + "=" * 60)
    print("PDF Parsing Summary")
    print("=" * 60)
    print(f"  Total decisions processed: {stats['total']}")
    print(f"  Successfully parsed:       {stats['success']}")
    print(f"  Failed:                    {stats['failed']}")
    if stats['saved_to_db'] > 0 or stats['updated_in_db'] > 0:
        print(f"  Saved to KlauzulaNiedozwolona:   {stats['saved_to_db']}")
        print(f"  Updated in KlauzulaNiedozwolona: {stats['updated_in_db']}")
    if stats['db_errors'] > 0:
        print(f"  Database errors:           {stats['db_errors']}")
    print("=" * 60)
    print("\nDone!")


def main():
    """Main entry point for the PDF parser CLI."""
    parser = argparse.ArgumentParser(
        description="Parse UOKiK decision PDFs and extract unfair contract clauses.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Parse all pending PDFs
  %(prog)s --years 2024,2025            # Parse only PDFs for 2024-2025
  %(prog)s --dry-run                    # Preview extraction without saving
  %(prog)s --save-to-db                 # Also insert into KlauzulaNiedozwolona
  %(prog)s --dry-run --years 2024       # Preview 2024 decisions only
"""
    )
    parser.add_argument(
        '--years',
        type=str,
        default=None,
        help='Comma-separated list of years to filter (e.g., "2024,2025").'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview extraction results without saving any changes to the database.'
    )
    parser.add_argument(
        '--save-to-db',
        action='store_true',
        help='After parsing, save extracted clauses into the KlauzulaNiedozwolona table.'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("UOKiK Decision PDF Parser")
    print("=" * 60)

    # 1. Test database connection
    print("\n1. Testing database connection...")
    if not test_database_connection():
        print("\n✗ Aborting: Cannot connect to database")
        sys.exit(1)

    # 2. Initialize database
    print("\n2. Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        sys.exit(1)

    # 3. Parse years argument
    years = None
    if args.years:
        try:
            years = [int(y.strip()) for y in args.years.split(',') if y.strip()]
            print(f"\n3. Filtering for years: {', '.join(map(str, years))}")
        except ValueError:
            print("✗ Invalid year format. Use comma-separated integers, e.g., '2024,2025'")
            sys.exit(1)
    else:
        print("\n3. Processing all years (no filter)")

    # 4. Check available decisions
    db = get_db()
    try:
        query = db.query(DecyzjaUOKiK).filter(
            DecyzjaUOKiK.status_parsowania == 'pobrane'
        )
        if years:
            query = query.filter(DecyzjaUOKiK.rok.in_([str(y) for y in years]))
        count = query.count()
        print(f"   Found {count} decisions with status 'pobrane'")
    finally:
        db.close()

    if count == 0:
        print("\n✗ No decisions to process. Make sure the scraper and downloader have run first.")
        sys.exit(1)

    # 5. Run parsing
    mode = "DRY RUN" if args.dry_run else "LIVE"
    save_flag = " + saving to KlauzulaNiedozwolona" if args.save_to_db else ""
    print(f"\n4. Starting PDF parsing ({mode}{save_flag})...")

    stats = process_all_decisions(
        years=years,
        save_to_db=args.save_to_db,
        dry_run=args.dry_run
    )

    # 6. Print summary
    print_summary(stats)

    # Exit with non-zero if everything failed
    if stats['total'] > 0 and stats['success'] == 0:
        print("\n⚠ Warning: All parsing attempts failed. Check logs above.")
        sys.exit(2)


if __name__ == "__main__":
    main()
