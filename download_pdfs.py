#!/usr/bin/env python3
"""
CLI script to download PDFs for UOKiK decisions from the database.

Usage:
    python download_pdfs.py
    python download_pdfs.py --years 2024,2025
    python download_pdfs.py --all
    python download_pdfs.py --output-dir ./data/pdfs --years 2023,2024

This script:
  1. Tests the database connection
  2. Initializes the database (creates tables if missing)
  3. Queries decisions with status='nowe' (optionally filtered by year)
  4. Downloads PDFs one by one with random delays
  5. Prints a summary of the operation
"""
import sys
import argparse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import init_db, engine
from pdf_downloader import download_all_pdfs
from config import DATABASE_URL


def test_database_connection():
    """Test database connection before starting downloads."""
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
    """Print a formatted summary of the download operation."""
    print("\n" + "=" * 60)
    print("PDF Download Summary")
    print("=" * 60)
    print(f"  Total decisions processed: {stats['total']}")
    print(f"  Successfully downloaded:    {stats['downloaded']}")
    print(f"  Skipped (already exist):    {stats['skipped']}")
    print(f"  Failed:                     {stats['failed']}")
    print(f"  Output directory:           {stats['output_dir']}")
    print("=" * 60)
    print("\nDone!")


def main():
    """Main entry point for the PDF downloader CLI."""
    parser = argparse.ArgumentParser(
        description="Download PDFs for UOKiK decisions from the database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Download all pending PDFs
  %(prog)s --years 2024,2025            # Download PDFs for 2024-2025
  %(prog)s --all                        # Same as default (all pending)
  %(prog)s --output-dir ./data/pdfs    # Custom output directory
"""
    )
    parser.add_argument(
        '--years',
        type=str,
        default=None,
        help='Comma-separated list of years to filter (e.g., "2024,2025").'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Download all pending PDFs regardless of year (default behavior).'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='pdfs',
        help='Directory where PDFs will be saved (default: "pdfs").'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("UOKiK Decision PDF Downloader")
    print("=" * 60)
    
    # Test database connection
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
    
    # Parse years argument
    years = None
    if args.years:
        try:
            years = [int(y.strip()) for y in args.years.split(',') if y.strip()]
            print(f"\n3. Downloading PDFs for years: {', '.join(map(str, years))}")
        except ValueError:
            print("✗ Invalid years format. Use comma-separated integers, e.g., '2024,2025'")
            sys.exit(1)
    else:
        print("\n3. Downloading all pending PDFs...")
    
    # Run the download
    stats = download_all_pdfs(years=years, output_dir=args.output_dir)
    
    # Print summary
    print_summary(stats)
    
    # Exit with error code if all failed
    if stats['total'] > 0 and stats['downloaded'] == 0 and stats['skipped'] == 0:
        print("\n⚠ Warning: All downloads failed. Check network and logs above.")
        sys.exit(2)


if __name__ == "__main__":
    main()
