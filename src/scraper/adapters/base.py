"""Abstract base adapter for manga site scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MangaResult:
    """A manga found by a search."""

    title: str
    url: str
    cover_url: str | None = None
    source_site: str = ""
    language: str | None = None
    genres: list[str] = field(default_factory=list)
    description: str | None = None
    external_id: str | None = None


@dataclass
class ChapterInfo:
    """Info about a chapter to download."""

    number: float
    title: str | None = None
    url: str = ""
    language: str | None = None
    external_id: str | None = None
    page_count: int | None = None


@dataclass
class PageUrl:
    """A single page URL."""

    number: int
    url: str
    filename: str | None = None


class BaseAdapter(ABC):
    """Abstract adapter for a manga source site."""

    name: str = "base"
    base_url: str = ""

    @abstractmethod
    async def search(
        self, genre: str | None = None, keyword: str | None = None, limit: int = 10
    ) -> list[MangaResult]:
        """Search for manga by genre or keyword."""
        ...

    @abstractmethod
    async def get_chapters(
        self, manga_url: str, language: str | None = None, external_id: str | None = None
    ) -> list[ChapterInfo]:
        """Get list of chapters for a manga."""
        ...

    @abstractmethod
    async def get_pages(
        self, chapter_url: str, external_id: str | None = None
    ) -> list[PageUrl]:
        """Get page image URLs for a chapter."""
        ...
