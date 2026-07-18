"""FastAPI application — the manga library API server."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from slugify import slugify

from src.config import load_config
from src.db.database import get_db, init_db
from src.db.models import Manga, SuggestedManga

from .routes import chapters, images, manga
from .schemas import (
    AnalyzeRequest,
    AnalyzeResult,
    ScraperProgressOut,
    ScraperRunRequest,
    ScraperStatusOut,
    SuggestMangaRequest,
    SuggestedMangaOut,
    UpdateChaptersRequest,
)

# Global state for scraper status
_scraper_running = False
_scraper_last_run: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    init_db()
    if os.getenv("MANGAVAULT_SEED_DEMO_ON_START", "").lower() in {"1", "true", "yes"}:
        from src.demo_seed import seed_demo_library

        seed_demo_library(reset=False)
    yield


app = FastAPI(
    title="Manga Worker API",
    description="API for the manga scraper, analyzer, and reader library",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
config = load_config()
allow_all_cors = "*" in config.api.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_cors else config.api.cors_origins,
    allow_credentials=not allow_all_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(manga.router)
app.include_router(chapters.router)
app.include_router(images.router)


# --- Scraper endpoints ---


def _make_api_progress_callback(limit: int):
    """Build a callback that updates api_progress for frontend polling."""
    from src.scraper.progress import api_progress

    def callback(phase: str, detail: dict) -> None:
        msg = detail.get("message") or detail.get("reason", "")
        api_progress.append_log(phase, msg, detail)
        api_progress.phase = phase
        api_progress.message = msg
        api_progress.current_manga = detail.get("title", detail.get("manga", api_progress.current_manga))
        if phase == "search":
            if "to_process" in detail:
                api_progress.manga_total = detail["to_process"]
        elif phase == "manga_start":
            api_progress.manga_index = detail.get("index", api_progress.manga_index)
            api_progress.manga_total = detail.get("total", limit)
        elif phase == "chapter":
            api_progress.chapter_index = detail.get("chapter", api_progress.chapter_index)
            api_progress.chapter_total = detail.get("total", api_progress.chapter_total)
        elif phase == "pages":
            api_progress.page_index = detail.get("page", api_progress.page_index)
            api_progress.page_total = detail.get("total", api_progress.page_total)
        if phase == "manga_done":
            api_progress.processed_count = api_progress.processed_count + 1
        if phase == "error":
            err_msg = detail.get("message", "")
            ctx = detail.get("title", detail.get("context", ""))
            api_progress.errors.append(f"{ctx}: {err_msg}" if ctx else err_msg)
        if phase == "done":
            api_progress.phase = "done"
            api_progress.processed_count = detail.get("processed", 0)

    return callback


def _ensure_scraper_enabled() -> None:
    if config.scraper.public_demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Scraper is disabled in this public build.",
        )


async def _run_scraper_task(
    genre: str | None,
    limit: int,
    site: str | None,
    query: str | None = None,
    direct_chapter_url: str | None = None,
):
    """Background task to run the scraper."""
    global _scraper_running, _scraper_last_run

    from src.scraper.engine import ScraperEngine
    from src.scraper.progress import api_progress

    _scraper_running = True
    effective_limit = 1 if direct_chapter_url else (limit if not query else min(limit, 10))
    api_progress.phase = "search"
    api_progress.message = "Starting..."
    api_progress.current_manga = ""
    api_progress.manga_index = 0
    api_progress.manga_total = effective_limit
    api_progress.chapter_index = 0
    api_progress.chapter_total = 0
    api_progress.page_index = 0
    api_progress.page_total = 0
    api_progress.processed_count = 0
    api_progress.errors = []
    api_progress.logs = []

    try:
        engine = ScraperEngine(config)
        callback = _make_api_progress_callback(effective_limit)
        await engine.run(
            genre=genre,
            limit=effective_limit,
            site_name=site,
            query=query,
            direct_chapter_url=direct_chapter_url,
            progress_callback=callback,
        )
    finally:
        _scraper_running = False
        _scraper_last_run = datetime.now(timezone.utc)
        api_progress.phase = "idle"
        api_progress.message = ""


@app.post("/scraper/run")
async def run_scraper(req: ScraperRunRequest, background_tasks: BackgroundTasks):
    """Trigger a scraper run in the background (by genre or by query/name)."""
    global _scraper_running
    _ensure_scraper_enabled()

    if _scraper_running:
        return {"ok": False, "message": "Scraper is already running"}

    url = (req.direct_chapter_url or "").strip() or None
    background_tasks.add_task(
        _run_scraper_task, req.genre, req.limit, req.site, req.query, url
    )
    return {"ok": True, "message": "Scraper started in background"}


# --- Suggestions (manga to scrape by name) ---


@app.post("/suggestions", response_model=SuggestedMangaOut)
def add_suggestion(req: SuggestMangaRequest, db: Session = Depends(get_db)):
    """Add a manga suggestion for later scraping. Rejects if already in library."""
    _ensure_scraper_enabled()

    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    slug = slugify(title)
    existing = db.query(Manga).filter(Manga.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Already in library: {existing.title}",
        )

    duplicate = db.query(SuggestedManga).filter(
        SuggestedManga.title.ilike(title), SuggestedManga.status == "pending"
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Already suggested (pending)")

    suggestion = SuggestedManga(title=title, status="pending")
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


@app.get("/suggestions", response_model=list[SuggestedMangaOut])
def list_suggestions(db: Session = Depends(get_db)):
    """List all suggestions (pending first)."""
    items = (
        db.query(SuggestedManga)
        .order_by(SuggestedManga.status.asc(), SuggestedManga.created_at.desc())
        .all()
    )
    return items


@app.delete("/suggestions/{suggestion_id}")
def delete_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    """Remove a suggestion."""
    _ensure_scraper_enabled()

    s = db.query(SuggestedManga).filter(SuggestedManga.id == suggestion_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


# --- Update chapters for existing manga ---


@app.post("/manga/{slug}/update-chapters")
async def update_manga_chapters(
    slug: str,
    req: UpdateChaptersRequest | None = None,
    db: Session = Depends(get_db),
):
    """Check source for new chapters and download any that are missing."""
    _ensure_scraper_enabled()

    from src.scraper.engine import ScraperEngine

    manga = (
        db.query(Manga)
        .options(joinedload(Manga.chapters))
        .filter(Manga.slug == slug)
        .first()
    )
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    max_ch = req.max_chapters if req else 5
    engine = ScraperEngine(config)
    added = await engine.update_manga_chapters(manga, db, max_new_chapters=max_ch)
    return {"ok": True, "added": added, "message": f"Downloaded {added} new chapter(s)"}


@app.get("/scraper/status", response_model=ScraperStatusOut)
def scraper_status(db: Session = Depends(get_db)):
    """Get current scraper status and library stats."""
    total = db.query(Manga).count()
    ready = db.query(Manga).filter(Manga.status == "ready").count()
    downloading = db.query(Manga).filter(Manga.status == "downloading").count()
    analyzing = db.query(Manga).filter(Manga.status == "analyzing").count()
    discarded = db.query(Manga).filter(Manga.status == "discarded").count()

    return ScraperStatusOut(
        running=_scraper_running,
        last_run=_scraper_last_run,
        total_mangas=total,
        ready=ready,
        downloading=downloading,
        analyzing=analyzing,
        discarded=discarded,
    )


@app.get("/scraper/progress", response_model=ScraperProgressOut)
def scraper_progress():
    """Get live progress when scraper is running (poll this while status.running is true)."""
    from src.scraper.progress import api_progress

    return ScraperProgressOut(**api_progress.to_dict())


@app.post("/analyze", response_model=AnalyzeResult)
async def analyze_manga(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """Run the analysis pipeline on a specific manga."""
    from src.analyzer.pipeline import AnalysisPipeline

    manga_obj = db.query(Manga).filter(Manga.slug == req.slug).first()
    if not manga_obj:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Manga not found")

    pipeline = AnalysisPipeline(config)
    result = await pipeline.analyze_manga(manga_obj, db)

    return AnalyzeResult(
        accepted=result.get("accepted", False),
        language=result.get("language"),
        tags=result.get("tags", []),
        synopsis=result.get("synopsis", ""),
        content_rating=result.get("content_rating", "safe"),
        tokens_used=result.get("tokens_used", 0),
        pages_analyzed=result.get("pages_analyzed", 0),
    )


@app.get("/health")
def health():
    """Health check."""
    return {"ok": True, "service": "manga-worker"}
