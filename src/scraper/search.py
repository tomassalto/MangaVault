"""Search helpers for the public build.

The public repository keeps source-specific discovery disabled. Private local
adapters can still provide their own native search implementation.
"""

from .adapters.base import MangaResult


async def search_duckduckgo(query: str, max_results: int = 10) -> list[MangaResult]:
    """Return no web-search results in the public build."""
    _ = (query, max_results)
    return []


def build_search_query(genre: str | None, keyword: str | None, language: str = "es") -> str:
    """Build a descriptive query string for private integrations."""
    parts: list[str] = []

    if keyword:
        parts.append(keyword)
    if genre:
        parts.append(genre)

    parts.append("manga")

    if language == "es":
        parts.append("espanol")
    elif language == "en":
        parts.append("english")

    return " ".join(parts)
