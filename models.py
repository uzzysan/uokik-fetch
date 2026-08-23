"""
Database models for storing UOKiK unfair contract terms registry data.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()


class KlauzulaNiedozwolona(Base):
    """Model representing an unfair contract term from UOKiK registry."""
    
    __tablename__ = 'klauzule_niedozwolone'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    numer_postanowienia = Column(String(50), unique=True, nullable=False, index=True)
    numer_decyzji = Column(String(50), nullable=True, index=True)
    data_wyroku = Column(Date, nullable=True, index=True)
    sygnatura = Column(String(100), nullable=True, index=True)
    postanowienie_niedozwolone = Column(Text, nullable=True)
    branza = Column(String(200), nullable=True, index=True)
    powod = Column(String(500), nullable=True)
    pozwany = Column(String(500), nullable=True)
    data_wpisu = Column(Date, nullable=True)
    zagadnienie = Column(String(500), nullable=True)
    paragraf = Column(String(50), nullable=True)
    punkt = Column(String(50), nullable=True)
    source = Column(String(20), nullable=True, default='stary_rejestr')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<KlauzulaNiedozwolona(numer={self.numer_postanowienia}, sygnatura={self.sygnatura})>"


class DecyzjaUOKiK(Base):
    """Model representing a UOKiK decision from the new decyzje.uokik.gov.pl site."""
    
    __tablename__ = 'decyzje_uokik'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    numer_decyzji = Column(String(50), unique=True, nullable=False, index=True)
    data_wydania = Column(Date, nullable=True, index=True)
    sygnatura_akt = Column(String(100), nullable=True, index=True)
    uczestnicy_postepowania = Column(Text, nullable=True)
    rodzaj_praktyki = Column(String(100), nullable=True)
    kara = Column(String(10), nullable=True)
    branza = Column(String(300), nullable=True, index=True)
    region = Column(String(100), nullable=True)
    odwolanie_do_sadu = Column(String(10), nullable=True)
    orzecznictwo = Column(Text, nullable=True)
    unid = Column(String(64), nullable=True, index=True)
    pdf_url = Column(String(500), nullable=True)
    pdf_filename = Column(String(300), nullable=True)
    pdf_local_path = Column(String(500), nullable=True)
    status_parsowania = Column(String(20), default='nowe', nullable=False)
    extracted_klauzula = Column(Text, nullable=True)
    rok = Column(String(4), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    pdfs = relationship("DecyzjaPDF", back_populates="decyzja", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<DecyzjaUOKiK(numer={self.numer_decyzji}, rok={self.rok})>"


class DecyzjaPDF(Base):
    """Model representing a downloaded PDF for a UOKiK decision."""
    
    __tablename__ = 'decyzje_pdfs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    decyzja_id = Column(Integer, ForeignKey('decyzje_uokik.id'), nullable=False, index=True)
    decyzja = relationship("DecyzjaUOKiK", back_populates="pdfs")
    pdf_url = Column(String(500), nullable=False)
    local_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    download_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<DecyzjaPDF(decyzja_id={self.decyzja_id}, path={self.local_path})>"
