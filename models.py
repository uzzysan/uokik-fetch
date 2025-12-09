"""
Database models for storing UOKiK unfair contract terms registry data.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class KlauzulaNiedozwolona(Base):
    """Model representing an unfair contract term from UOKiK registry."""
    
    __tablename__ = 'klauzule_niedozwolone'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    numer_postanowienia = Column(String(50), unique=True, nullable=False, index=True)
    data_wyroku = Column(Date, nullable=True, index=True)
    sygnatura = Column(String(100), nullable=True, index=True)
    postanowienie_niedozwolone = Column(Text, nullable=True)
    branza = Column(String(200), nullable=True, index=True)
    powod = Column(String(500), nullable=True)
    pozwany = Column(String(500), nullable=True)
    data_wpisu = Column(Date, nullable=True)
    zagadnienie = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<KlauzulaNiedozwolona(numer={self.numer_postanowienia}, sygnatura={self.sygnatura})>"
