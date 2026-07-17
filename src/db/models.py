"""SQLAlchemy ORM models for the manga library."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Manga(Base):
    __tablename__ = "mangas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(500), unique=True, nullable=False, index=True)
    synopsis = Column(Text, nullable=True)
    language = Column(String(10), nullable=True)  # "es", "en", "other"
    source_url = Column(String(2000), nullable=True)
    source_site = Column(String(100), nullable=True)  # "mangadex", "tmo", etc.
    cover_path = Column(String(1000), nullable=True)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, downloading, analyzing, ready, discarded
    content_rating = Column(String(20), nullable=True)  # safe, suggestive, explicit
    total_chapters = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    tags = relationship("MangaTag", back_populates="manga", cascade="all, delete-orphan")
    chapters = relationship(
        "Chapter", back_populates="manga", cascade="all, delete-orphan", order_by="Chapter.number"
    )
    analysis_logs = relationship(
        "AnalysisLog", back_populates="manga", cascade="all, delete-orphan"
    )


class MangaTag(Base):
    __tablename__ = "manga_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manga_id = Column(Integer, ForeignKey("mangas.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String(100), nullable=False, index=True)

    manga = relationship("Manga", back_populates="tags")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manga_id = Column(Integer, ForeignKey("mangas.id", ondelete="CASCADE"), nullable=False)
    number = Column(Float, nullable=False)  # Float to support chapter 1.5, etc.
    title = Column(String(500), nullable=True)
    page_count = Column(Integer, default=0)
    path = Column(String(1000), nullable=True)  # relative path to chapter folder
    source_url = Column(String(2000), nullable=True)
    downloaded_at = Column(DateTime, nullable=True)

    manga = relationship("Manga", back_populates="chapters")
    pages = relationship("Page", back_populates="chapter", cascade="all, delete-orphan", order_by="Page.number")


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    image_path = Column(String(1000), nullable=False)  # relative path to image
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    ocr_text = Column(Text, nullable=True)  # cached OCR result

    chapter = relationship("Chapter", back_populates="pages")


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manga_id = Column(Integer, ForeignKey("mangas.id", ondelete="CASCADE"), nullable=False)
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    raw_response = Column(Text, nullable=True)
    language_detected = Column(String(10), nullable=True)
    tags_detected = Column(Text, nullable=True)  # JSON array string
    accepted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    manga = relationship("Manga", back_populates="analysis_logs")


class SuggestedManga(Base):
    """User suggestions for manga to scrape (by title search)."""

    __tablename__ = "suggested_manga"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    status = Column(String(20), default="pending")  # pending, scraped, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
