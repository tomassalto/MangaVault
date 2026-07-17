"""Downloads manga pages (images) to the local filesystem. Saves as WebP for size/quality."""

import asyncio
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from PIL import Image

from src.db.models import Chapter, Manga, Page

from .image_filter import (
    is_likely_content_heuristic,
    is_likely_content_ollama,
    prepare_image_for_ollama,
)

if TYPE_CHECKING:
    from src.scraper.progress import ProgressCallback

logger = logging.getLogger(__name__)

# WebP quality (0-100). 85 balances size and quality.
WEBP_QUALITY = 85


def _save_as_webp(image: Image.Image, out_path: Path) -> None:
    """Save PIL Image as WebP. Preserves transparency for PNG."""
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGBA")
        image.save(out_path, "WEBP", quality=WEBP_QUALITY, method=6)
    else:
        image = image.convert("RGB")
        image.save(out_path, "WEBP", quality=WEBP_QUALITY, method=6)


async def download_cover(
    manga: Manga,
    cover_url: str,
    base_path: str,
    progress_callback: "ProgressCallback | None" = None,
) -> str | None:
    """Download the cover image and save as WebP."""
    if not cover_url:
        return None

    base = Path(base_path)
    manga_dir = base / manga.slug
    manga_dir.mkdir(parents=True, exist_ok=True)

    cover_path = manga_dir / "cover.webp"

    try:
        if progress_callback:
            progress_callback("cover", {"status": "downloading", "title": manga.title})
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(cover_url)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            img.load()
            _save_as_webp(img, cover_path)

        if progress_callback:
            progress_callback("cover", {"status": "done", "title": manga.title})
        return cover_path.relative_to(base).as_posix()
    except Exception as e:
        if progress_callback:
            progress_callback("cover", {"status": "error", "title": manga.title, "error": str(e)})
        cover_path.unlink(missing_ok=True)
        return None


async def download_chapter_pages(
    manga: Manga,
    chapter: Chapter,
    page_urls: list[dict],
    base_path: str,
    delay: float = 0.5,
    progress_callback: "ProgressCallback | None" = None,
    image_filter_config: "dict | None" = None,
    ollama_host: str = "http://localhost:11434",
) -> list[dict]:
    """
    Download all pages for a chapter.
    Opcionalmente filtra placeholders (negro/blanco/gris) con heurística y/o modelo de visión (Ollama).

    Args:
        manga: The manga record
        chapter: The chapter record
        page_urls: List of dicts with 'number', 'url', optional 'filename'
        base_path: Root download directory
        delay: Delay between downloads (to be polite)
        image_filter_config: Optional dict with enabled, min_variance, use_ollama_vision, ollama_vision_model
        ollama_host: Base URL for Ollama when using vision filter

    Returns:
        List of dicts with 'number', 'image_path', 'width', 'height' (números consecutivos 1,2,3...)
    """
    chapter_dir = Path(base_path) / manga.slug / f"ch-{chapter.number:g}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    filter_cfg = image_filter_config or {}
    filter_enabled = filter_cfg.get("enabled", True)
    min_variance = float(filter_cfg.get("min_variance", 80.0))
    use_ollama = bool(filter_cfg.get("use_ollama_vision", False))
    ollama_model = str(filter_cfg.get("ollama_vision_model", "llava"))

    downloaded: list[dict] = []
    total_pages = len(page_urls)
    next_page_number = 1

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": chapter.source_url or manga.source_url or "",
        },
    ) as client:
        for i, page_info in enumerate(page_urls):
            url = page_info["url"]

            if progress_callback:
                progress_callback(
                    "pages",
                    {
                        "page": i + 1,
                        "total": total_pages,
                        "chapter": chapter.number,
                        "title": manga.title,
                    },
                )

            try:
                resp = await client.get(url)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content))
                img.load()

                # Filtro: descartar placeholders (negro, blanco, gris) y opcionalmente validar con visión
                if filter_enabled:
                    if not is_likely_content_heuristic(img, min_variance=min_variance):
                        logger.info("Page discarded (low variance, likely placeholder): %s", url[:80])
                        if delay > 0:
                            await asyncio.sleep(delay)
                        continue
                    if use_ollama:
                        img_bytes = prepare_image_for_ollama(img)
                        if not await is_likely_content_ollama(
                            img_bytes,
                            base_url=ollama_host,
                            model=ollama_model,
                        ):
                            logger.info("Page discarded by vision model (not content): %s", url[:80])
                            if delay > 0:
                                await asyncio.sleep(delay)
                            continue

                out_name = f"{next_page_number:03d}.webp"
                file_path = chapter_dir / out_name
                _save_as_webp(img, file_path)

                width, height = img.size
                rel_path = file_path.relative_to(Path(base_path)).as_posix()
                downloaded.append(
                    {
                        "number": next_page_number,
                        "image_path": rel_path,
                        "width": width,
                        "height": height,
                    }
                )
                next_page_number += 1
            except Exception as e:
                logger.warning("Failed to download page %s: %s", url[:60], e)

            if delay > 0:
                await asyncio.sleep(delay)

    return downloaded
