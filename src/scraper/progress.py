"""Shared progress state for scraper — used by CLI (Rich) and API (polling)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

# Type for progress callbacks: (phase: str, detail: dict) -> None
ProgressCallback = Callable[[str, dict], None]

MAX_LOG_ENTRIES = 300


@dataclass
class ScraperProgressState:
    """Current scraper run progress (for API polling)."""

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
    errors: list[str] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)

    def append_log(self, phase: str, message: str, detail: dict | None = None) -> None:
        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "phase": phase,
            "message": message or phase,
        }
        if detail:
            safe = {}
            for k, v in detail.items():
                if k in ("message", "phase") or v is None:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    safe[k] = v
                else:
                    safe[k] = str(v)
            if safe:
                entry["detail"] = safe
        self.logs.append(entry)
        if len(self.logs) > MAX_LOG_ENTRIES:
            self.logs = self.logs[-MAX_LOG_ENTRIES:]

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "message": self.message,
            "current_manga": self.current_manga,
            "manga_index": self.manga_index,
            "manga_total": self.manga_total,
            "chapter_index": self.chapter_index,
            "chapter_total": self.chapter_total,
            "page_index": self.page_index,
            "page_total": self.page_total,
            "processed_count": self.processed_count,
            "errors": self.errors.copy(),
            "logs": list(self.logs),
        }


# Global state for API — updated by engine when running via API
api_progress = ScraperProgressState()
