"""
Database connection and session management.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base
from config import DATABASE_URL


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully.")


def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e
