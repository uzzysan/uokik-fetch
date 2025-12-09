#!/usr/bin/env python3
"""
Database initialization script.

This script creates all necessary tables in the PostgreSQL database
if they don't already exist.

Usage:
    uv run init_database.py
"""
from sqlalchemy import inspect, text
from database import engine, init_db
from models import Base
from config import DATABASE_URL


def check_database_connection():
    """Test database connection."""
    print("Testing database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✓ Successfully connected to PostgreSQL")
            print(f"  Version: {version.split(',')[0]}")
        return True
    except Exception as e:
        print(f"✗ Failed to connect to database:")
        print(f"  {e}")
        return False


def check_existing_tables():
    """Check which tables already exist."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"\nExisting tables in database:")
        for table in existing_tables:
            print(f"  - {table}")
    else:
        print("\nNo tables found in database.")
    
    return existing_tables


def create_tables():
    """Create all tables defined in models."""
    print("\nCreating tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Tables created successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to create tables:")
        print(f"  {e}")
        return False


def verify_table_structure():
    """Verify the created table structure."""
    inspector = inspect(engine)
    table_name = 'klauzule_niedozwolone'
    
    if table_name not in inspector.get_table_names():
        print(f"\n✗ Table '{table_name}' was not created")
        return False
    
    print(f"\n✓ Table '{table_name}' structure:")
    columns = inspector.get_columns(table_name)
    
    for col in columns:
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        print(f"  - {col['name']}: {col['type']} {nullable}")
    
    # Check indexes
    indexes = inspector.get_indexes(table_name)
    if indexes:
        print(f"\n  Indexes:")
        for idx in indexes:
            cols = ', '.join(idx['column_names'])
            unique = "UNIQUE" if idx['unique'] else ""
            print(f"    - {idx['name']}: ({cols}) {unique}")
    
    return True


def main():
    """Main initialization routine."""
    print("=" * 70)
    print("Database Initialization Script")
    print("=" * 70)
    print(f"\nDatabase URL: {DATABASE_URL.replace(':jakieshaslo@', ':***@')}")
    
    # Step 1: Check connection
    if not check_database_connection():
        print("\n✗ Aborting: Cannot connect to database")
        return 1
    
    # Step 2: Check existing tables
    existing_tables = check_existing_tables()
    
    # Step 3: Create tables
    if not create_tables():
        print("\n✗ Aborting: Failed to create tables")
        return 1
    
    # Step 4: Verify structure
    if not verify_table_structure():
        print("\n✗ Aborting: Failed to verify table structure")
        return 1
    
    print("\n" + "=" * 70)
    print("✓ Database initialization completed successfully!")
    print("=" * 70)
    print("\nYou can now run the scraper with: uv run main.py")
    
    return 0


if __name__ == "__main__":
    exit(main())
