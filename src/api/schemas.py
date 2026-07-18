"""Pydantic schemas for the API."""

from datetime import datetime

from pydantic import BaseModel


class TagOut(BaseModel):
    tag: str

    class Config:
        from_attributes = True


class PageOut(BaseModel):
    id: int
    number: int
    image_path: str
    width: int | None = None
    height: int | None = None

    class Config:
        from_attributes = True


class ChapterOut(BaseModel):
    id: int
    number: float
    title: str | None = None
    page_count: int = 0
    path: str | None = None
    downloaded_at: datetime | None = None

    class Config:
        from_attributes = True


class ChapterDetailOut(ChapterOut):
    pages: list[PageOut] = []


class MangaOut(BaseModel):
    id: int
    title: str
    slug: str
    synopsis: str | None = None
    language: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    cover_path: str | None = None
    status: str
    content_rating: str | None = None
    total_chapters: int = 0
    tags: list[TagOut] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class MangaDetailOut(MangaOut):
    chapters: list[ChapterOut] = []


class MangaListOut(BaseModel):
    items: list[MangaOut]
    total: int
    page: int
    per_page: int


class ScraperRunRequest(BaseModel):
    genre: str | None = None
    limit: int = 10
    site: str | None = None
    query: str | None = None  # Search by manga name (e.g. "One Piece")
    direct_chapter_url: str | None = None  # Si se pasa, no se busca; solo se scrapea este capítulo (ej. ManhwaWeb)


class ScraperStatusOut(BaseModel):
    running: bool
    last_run: datetime | None = None
    total_mangas: int = 0
    ready: int = 0
    downloading: int = 0
    analyzing: int = 0
    discarded: int = 0


class ScraperProgressLogEntry(BaseModel):
    time: str = ""
    phase: str = ""
    message: str = ""
    detail: dict | None = None


class ScraperProgressOut(BaseModel):
    """Live progress when scraper is running (for polling)."""
    phase: str = "idle"
    message: str = ""
    current_manga: str = ""
    manga_index: int = 0
    manga_total: int = 0
    chapter_index: int = 0
    chapter_total: int = 0
    page_index: int = 0
    page_total: int = 0
    processed_count: int = 0
    errors: list[str] = []
    logs: list[dict] = []


class AnalyzeRequest(BaseModel):
    slug: str


class AnalyzeResult(BaseModel):
    accepted: bool
    language: str | None = None
    tags: list[str] = []
    synopsis: str = ""
    content_rating: str = "safe"
    tokens_used: int = 0
    pages_analyzed: int = 0


class SuggestedMangaOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class UpdateChaptersRequest(BaseModel):
    max_chapters: int = 5


class SuggestMangaRequest(BaseModel):
    title: str


class DemoImportRequest(BaseModel):
    query: str


class DemoImportOut(BaseModel):
    created: bool
    title: str
    slug: str
    message: str


class DemoManifestItem(BaseModel):
    title: str
    slug: str
    language: str
    tags: list[str]
    synopsis: str
    imported: bool
