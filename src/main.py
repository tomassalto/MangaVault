"""CLI entry point for the manga scraper worker."""

import typer
import uvicorn

from src.config import load_config
from src.db.database import init_db

app = typer.Typer(name="manga-worker", help="Manga Scraper & Analyzer Bot")


@app.command()
def init():
    """Initialize the database and create tables."""
    init_db()
    typer.echo("Database initialized successfully.")


@app.command("seed-demo")
def seed_demo(reset: bool = typer.Option(False, "--reset", help="Replace existing demo data.")):
    """Create portfolio demo data with generated original assets."""
    from src.demo_seed import seed_demo_library

    result = seed_demo_library(reset=reset)
    typer.echo(f"Demo library ready. Created {result['created']} manga. Total: {result['total']}.")


def _format_progress(phase: str, detail: dict) -> str:
    """Format progress callback data for Rich display."""
    if phase == "search":
        msg = detail.get("message", "Searching...")
        if "adapter" in detail:
            msg = f"[{detail['adapter']}] {detail.get('count', msg)}"
        return msg
    if phase == "manga_start":
        return f"Manga {detail.get('index', '?')}/{detail.get('total', '?')}: {detail.get('title', '')}"
    if phase == "cover":
        status = detail.get("status", "")
        return f"Cover: {detail.get('title', '')} ({status})"
    if phase == "chapter":
        return f"Chapter {detail.get('chapter', '?')}/{detail.get('total', '?')}: {detail.get('title', '')}"
    if phase == "pages":
        return f"Pages: {detail.get('page', 0)}/{detail.get('total', 0)} — {detail.get('title', '')}"
    if phase == "manga_done":
        return f"Saved: {detail.get('title', '')} ({detail.get('chapters', 0)} chapters)"
    if phase == "skip":
        return f"Skipped: {detail.get('title', '')} ({detail.get('reason', '')})"
    if phase == "error":
        return f"[red]Error: {detail.get('message', '')} ({detail.get('title', detail.get('context', ''))})[/red]"
    if phase == "done":
        attempted = detail.get("attempted", detail.get("total", 0))
        processed = detail.get("processed", 0)
        if attempted == 0:
            return "Complete: no new manga (search had no results or all already in library)"
        return f"Complete: {processed}/{attempted} manga processed ({processed} new)"
    return str(detail)


@app.command()
def scrape(
    genre: str = typer.Option(None, help="Specific genre to search for"),
    limit: int = typer.Option(10, help="Max mangas to process per run"),
    site: str = typer.Option(None, help="Specific site adapter to use"),
):
    """Run the scraper bot to find and download manga."""
    import asyncio

    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from src.scraper.engine import ScraperEngine

    config = load_config()
    if config.scraper.public_demo_mode:
        typer.echo(
            "Scraper is disabled in this public build. Configure a private adapter set to enable ingestion."
        )
        raise typer.Exit(1)

    engine = ScraperEngine(config)
    console = Console()

    typer.echo(f"Starting scraper (genre={genre or 'all'}, limit={limit}, site={site or 'all'})...")

    def progress_callback(phase: str, detail: dict) -> None:
        desc = _format_progress(phase, detail)
        if progress is not None and task_id is not None:
            progress.update(task_id, description=desc)
        if phase == "error":
            console.print(desc)
        elif phase == "manga_done" or phase == "done":
            console.print(f"  [green]{desc}[/green]")

    progress = None
    task_id = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task_id = progress.add_task("Initializing...", total=None)
        progress_callback("search", {"message": "Starting..."})

        asyncio.run(
            engine.run(
                genre=genre,
                limit=limit,
                site_name=site,
                progress_callback=progress_callback,
            )
        )
        progress.update(task_id, description="[green]Scraping complete.[/green]")

    typer.echo("Scraping complete.")


@app.command()
def analyze(
    slug: str = typer.Option(None, help="Analyze a specific manga by slug"),
    pending: bool = typer.Option(False, help="Analyze all pending mangas"),
):
    """Run the analysis pipeline on downloaded manga."""
    import asyncio

    from src.analyzer.pipeline import AnalysisPipeline
    from src.db.database import SessionLocal
    from src.db.models import Manga

    config = load_config()
    pipeline = AnalysisPipeline(config)

    db = SessionLocal()
    try:
        if slug:
            manga = db.query(Manga).filter(Manga.slug == slug).first()
            if not manga:
                typer.echo(f"Manga '{slug}' not found.")
                raise typer.Exit(1)
            typer.echo(f"Analyzing: {manga.title}")
            result = asyncio.run(pipeline.analyze_manga(manga, db))
            typer.echo(f"Result: language={result.get('language')}, accepted={result.get('accepted')}")
        elif pending:
            mangas = db.query(Manga).filter(Manga.status == "downloading").all()
            typer.echo(f"Found {len(mangas)} pending mangas to analyze.")
            for manga in mangas:
                typer.echo(f"  Analyzing: {manga.title}...")
                result = asyncio.run(pipeline.analyze_manga(manga, db))
                status = "accepted" if result.get("accepted") else "discarded"
                typer.echo(f"    -> {status} (lang={result.get('language')})")
        else:
            typer.echo("Specify --slug or --pending")
    finally:
        db.close()


@app.command()
def serve(
    host: str = typer.Option(None, help="API host"),
    port: int = typer.Option(None, help="API port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (can crash on Windows)"),
):
    """Start the FastAPI server."""
    config = load_config()
    init_db()

    _host = host or config.api.host
    _port = port or config.api.port

    typer.echo(f"Starting API server on {_host}:{_port}")
    uvicorn.run("src.api.app:app", host=_host, port=_port, reload=reload)


@app.command()
def status():
    """Show library statistics."""
    from src.db.database import SessionLocal
    from src.db.models import Chapter, Manga, MangaTag, Page

    init_db()
    db = SessionLocal()
    try:
        total = db.query(Manga).count()
        ready = db.query(Manga).filter(Manga.status == "ready").count()
        discarded = db.query(Manga).filter(Manga.status == "discarded").count()
        analyzing = db.query(Manga).filter(Manga.status == "analyzing").count()
        downloading = db.query(Manga).filter(Manga.status == "downloading").count()
        chapters = db.query(Chapter).count()
        pages = db.query(Page).count()
        tags = db.query(MangaTag.tag).distinct().count()

        typer.echo("=== Manga Library Status ===")
        typer.echo(f"  Total mangas:   {total}")
        typer.echo(f"    Ready:        {ready}")
        typer.echo(f"    Downloading:  {downloading}")
        typer.echo(f"    Analyzing:    {analyzing}")
        typer.echo(f"    Discarded:    {discarded}")
        typer.echo(f"  Total chapters: {chapters}")
        typer.echo(f"  Total pages:    {pages}")
        typer.echo(f"  Unique tags:    {tags}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
