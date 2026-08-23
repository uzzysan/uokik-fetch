#!/usr/bin/env python3
"""
One-off schema migration: adds numer_decyzji, paragraf, punkt columns to
klauzule_niedozwolone.

This project has no Alembic (see init_database.py, which only creates missing
tables via Base.metadata.create_all and never alters existing ones) — schema
changes to existing tables are applied by hand with scripts like this one.
Safe to run more than once: columns/indexes already present are skipped.

Usage:
    uv run migrate_add_paragraf_punkt.py
"""
from sqlalchemy import inspect, text
from database import engine
from config import DATABASE_URL

TABLE = "klauzule_niedozwolone"

NEW_COLUMNS = [
    ("numer_decyzji", "VARCHAR(50)"),
    ("paragraf", "VARCHAR(50)"),
    ("punkt", "VARCHAR(50)"),
]

NEW_INDEXES = [
    ("ix_klauzule_niedozwolone_numer_decyzji", "numer_decyzji"),
]


def main():
    print(f"Database: {DATABASE_URL.split('@')[-1]}")
    inspector = inspect(engine)
    existing_columns = {c["name"] for c in inspector.get_columns(TABLE)}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}

    with engine.begin() as conn:
        for name, coltype in NEW_COLUMNS:
            if name in existing_columns:
                print(f"skip  column {name} (already exists)")
                continue
            print(f"add   column {name} {coltype}")
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {coltype}"))

        for name, column in NEW_INDEXES:
            if name in existing_indexes:
                print(f"skip  index {name} (already exists)")
                continue
            print(f"add   index {name} ON {column}")
            conn.execute(text(f"CREATE INDEX {name} ON {TABLE} ({column})"))

    print("Done.")


if __name__ == "__main__":
    main()
