"""
CLI script to run the UOKiK decisions scraper (decyzje.uokik.gov.pl).

Usage examples:
    python scrape_decyzje.py --all
    python scrape_decyzje.py --years 2020,2021,2022
    python scrape_decyzje.py --years 2024

The script:
    1. Tests the database connection.
    2. Initializes the database (creates tables if missing).
    3. Scrapes decisions for the requested years.
    4. Saves / updates DecyzjaUOKiK records incrementally.
    5. Prints a summary of the run.
"""

import argparse
import sys
from typing import Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from database import init_db, get_db, engine
from models import DecyzjaUOKiK
from scraper_decyzje import scrape_all_decisions
from config import DATABASE_URL


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def test_database_connection() -> bool:
    """
    Verify that the application can reach the configured database.

    Returns:
        True if the connection succeeds, False otherwise.
    """
    print("Testing database connection...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
        print("✓ Database connection successful")
        return True
    except OperationalError as e:
        print("✗ Failed to connect to database:")
        print(f"  {e}")
        safe_url = DATABASE_URL.replace(":", ":", 1)
        if "://" in safe_url:
            safe_url = safe_url.split("://")[0] + "://***@" + safe_url.split("@")[-1] if "@" in safe_url else safe_url
        print(f"\n  Database URL: {safe_url}")
        print("\nPlease check:")
        print("  1. Database server is running")
        print("  2. Connection details in .env file are correct")
        print("  3. Network connectivity to database server")
        return False
    except Exception as e:
        print(f"✗ Unexpected error testing database connection: {e}")
        return False


def save_decisions_to_db(decision: dict, quiet: bool = True) -> Tuple[int, int]:
    """
    Save or update a single scraped decision in the database.

    The function uses ``numer_decyzji`` as the unique key. If a record with
    the same decision number already exists, all mutable fields are updated
    and the existing row is kept (counts as *skipped*). If the decision is
    new, a ``DecyzjaUOKiK`` row is inserted (counts as *saved*).

    Args:
        decision: Dictionary produced by the scraper (must contain
            ``numer_decyzji`` and the mapped field names).
        quiet: When False, print per-row status messages.

    Returns:
        Tuple ``(saved_count, skipped_count)`` where each element is 0 or 1.
    """
    db = get_db()
    try:
        # --- Look for an existing record by decision number -----------------
        existing = (
            db.query(DecyzjaUOKiK)
            .filter_by(numer_decyzji=decision.get("numer_decyzji"))
            .first()
        )

        if existing:
            # Update existing record in-place
            for key, value in decision.items():
                if hasattr(existing, key) and key not in ("id", "created_at"):
                    setattr(existing, key, value)

            existing.status_parsowania = "sparsowane"
            db.commit()

            if not quiet:
                print(f"  Updated: {decision.get('numer_decyzji')}")
            return 0, 1  # saved=0, skipped=1

        # --- Create new record -----------------------------------------------
        new_decision = DecyzjaUOKiK(
            numer_decyzji=decision.get("numer_decyzji"),
            data_wydania=decision.get("data_wydania"),
            sygnatura_akt=decision.get("sygnatura_akt"),
            uczestnicy_postepowania=decision.get("uczestnicy_postepowania"),
            rodzaj_praktyki=decision.get("rodzaj_praktyki"),
            kara=decision.get("kara"),
            branza=decision.get("branza"),
            region=decision.get("region"),
            odwolanie_do_sadu=decision.get("odwolanie_do_sadu"),
            orzecznictwo=decision.get("orzecznictwo"),
            unid=decision.get("unid"),
            pdf_url=decision.get("pdf_url"),
            pdf_filename=decision.get("pdf_filename"),
            rok=decision.get("rok"),
            status_parsowania="sparsowane",
        )
        db.add(new_decision)
        db.commit()

        if not quiet:
            print(f"  Saved: {decision.get('numer_decyzji')}")
        return 1, 0  # saved=1, skipped=0

    except IntegrityError as e:
        db.rollback()
        if not quiet:
            print(f"  Integrity error for {decision.get('numer_decyzji')}: {e}")
        return 0, 1

    except Exception as e:
        db.rollback()
        if not quiet:
            print(f"  Error saving {decision.get('numer_decyzji')}: {e}")
        return 0, 0

    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_years_argument(years_str: str) -> list:
    """
    Parse a comma-separated year string into a sorted list of integers.

    Args:
        years_str: e.g. "2020,2021,2022" or "2024".

    Returns:
        Sorted list of unique integer years.
    """
    years = []
    for part in years_str.split(","):
        part = part.strip()
        if part.isdigit():
            years.append(int(part))
    return sorted(set(years))


def main():
    parser = argparse.ArgumentParser(
        description="Scrape UOKiK decisions from decyzje.uokik.gov.pl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_decyzje.py --all
  python scrape_decyzje.py --years 2020,2021,2022
  python scrape_decyzje.py --years 2024
        """,
    )
    parser.add_argument(
        "--years",
        type=str,
        default=None,
        help='Comma-separated list of years to scrape (e.g. "2017,2018,2019").',
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all years from 2017 through 2026.",
    )
    args = parser.parse_args()

    # --- Determine years to scrape ------------------------------------------
    if args.years:
        years = parse_years_argument(args.years)
    elif args.all:
        years = list(range(2017, 2027))
    else:
        parser.print_help()
        sys.exit(1)

    # --- Banner -------------------------------------------------------------
    print("=" * 60)
    print("UOKiK Decisions Scraper  —  decyzje.uokik.gov.pl")
    print("=" * 60)
    print(f"Years to scrape: {years}")
    print()

    # --- 1. Test DB connection -----------------------------------------------
    print("1. Testing database connection...")
    if not test_database_connection():
        print("\n✗ Aborting: Cannot connect to database.\n")
        sys.exit(1)

    # --- 2. Initialize database ----------------------------------------------
    print("\n2. Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        sys.exit(1)

    # --- 3. Scrape -----------------------------------------------------------
    print(f"\n3. Scraping decisions for {len(years)} year(s)...")
    print("   (Random delays: 1–3 s between decisions, 2–5 s between years)\n")

    stats = scrape_all_decisions(
        years=years,
        save_callback=lambda decision: save_decisions_to_db(decision, quiet=True),
    )

    # --- 4. Summary ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total years processed : {stats['total_years']}")
    print(f"  Total decisions found : {stats['total_decisions']}")
    print(f"  Detail pages fetched  : {stats['successful_details']}")
    print(f"  Detail pages failed   : {stats['failed_details']}")
    print(f"  Records saved (new)   : {stats['saved']}")
    print(f"  Records updated (dup) : {stats['skipped']}")
    print(f"  Errors                : {stats['errors']}")
    print("=" * 60)
    print("\nDone!")


if __name__ == "__main__":
    main()
