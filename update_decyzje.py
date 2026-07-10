#!/usr/bin/env python3
"""
Incremental update script for UOKiK decisions from decyzje.uokik.gov.pl.

This script checks the database for the highest decision number and fetches
only new decisions from the UOKiK site that are not yet in the database.

Usage:
    python update_decyzje.py
    python update_decyzje.py --years 2024,2025
"""
import sys
import argparse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import init_db, get_db, engine
from models import DecyzjaUOKiK
from scraper_decyzje import fetch_search_results, fetch_decision_detail
from config import DATABASE_URL


def test_database_connection():
    """Test database connection."""
    print("Testing database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print("✓ Database connection successful")
        return True
    except OperationalError as e:
        print(f"✗ Failed to connect to database: {e}")
        return False


def get_max_decision_number():
    """Get the highest numer_decyzji from the database."""
    db = get_db()
    try:
        result = db.query(DecyzjaUOKiK.numer_decyzji).order_by(
            DecyzjaUOKiK.numer_decyzji.desc()
        ).first()
        if result and result[0]:
            print(f"Highest decision in database: {result[0]}")
            return result[0]
        print("Database is empty")
        return None
    finally:
        db.close()


def save_decision_to_db(decision: dict) -> tuple:
    """Save or update a single decision."""
    db = get_db()
    try:
        existing = db.query(DecyzjaUOKiK).filter_by(
            numer_decyzji=decision.get("numer_decyzji")
        ).first()

        if existing:
            for key, value in decision.items():
                if hasattr(existing, key) and key not in ("id", "created_at"):
                    setattr(existing, key, value)
            existing.status_parsowania = "sparsowane"
            db.commit()
            return 0, 1

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
        return 1, 0
    except Exception as e:
        db.rollback()
        print(f"  Error saving {decision.get('numer_decyzji')}: {e}")
        return 0, 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Incremental update for UOKiK decisions")
    parser.add_argument("--years", type=str, default=None, help="Comma-separated years")
    args = parser.parse_args()

    print("=" * 60)
    print("UOKiK Decisions - Incremental Update")
    print("=" * 60)

    if not test_database_connection():
        sys.exit(1)

    init_db()

    years = None
    if args.years:
        years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    else:
        years = [datetime.now().year]

    print(f"\nChecking years: {years}")

    total_new = 0
    total_skipped = 0

    for year in years:
        print(f"\n--- Year {year} ---")
        results = fetch_search_results(year)
        if not results:
            print(f"  No results")
            continue

        new_count = 0
        for decision in results:
            # Check if already exists
            db = get_db()
            try:
                existing = db.query(DecyzjaUOKiK).filter_by(
                    numer_decyzji=decision.get("numer_decyzji")
                ).first()
            finally:
                db.close()

            if existing:
                continue

            # Fetch detail
            detail = fetch_decision_detail(decision["unid"])
            decision.update(detail)
            decision["rok"] = str(year)

            saved, skipped = save_decision_to_db(decision)
            total_new += saved
            total_skipped += skipped
            if saved:
                print(f"  + New: {decision['numer_decyzji']}")
            new_count += 1

        print(f"  Year {year}: {new_count} new decisions")

    print("\n" + "=" * 60)
    print(f"Total new: {total_new}")
    print(f"Total updated: {total_skipped}")
    print("=" * 60)


if __name__ == "__main__":
    from datetime import datetime
    main()
