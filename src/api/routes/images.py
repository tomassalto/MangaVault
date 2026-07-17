"""Image serving routes — serve manga page images."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.config import get_config

router = APIRouter(tags=["images"])


@router.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """
    Serve a manga image file.

    The file_path is relative to the download_path configured in config.yaml.
    Example: /images/one-piece/ch-1/001.jpg
    """
    config = get_config()
    base = Path(config.scraper.download_path)
    if not base.is_absolute():
        # Resolve relative to project root (python-worker): src/api/routes -> 4 parents
        base = (Path(__file__).resolve().parent.parent.parent.parent / base).resolve()
    # Normalize path (forward slashes from URL / JSON)
    file_path = file_path.replace("\\", "/").lstrip("/")
    full_path = base / file_path

    # Security: ensure the path doesn't escape the base directory
    try:
        full_path.resolve().relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    # Determine media type
    suffix = full_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        full_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},  # 24h cache
    )
