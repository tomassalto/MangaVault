"""Manga API routes — list, search, detail."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from src.db.database import get_db
from src.db.models import Manga, MangaTag

from ..schemas import MangaDetailOut, MangaListOut, MangaOut

router = APIRouter(prefix="/manga", tags=["manga"])


@router.get("", response_model=MangaListOut)
def list_manga(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    language: str | None = Query(None),
    tag: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List manga with filters and pagination."""
    query = db.query(Manga).options(joinedload(Manga.tags))

    if status:
        query = query.filter(Manga.status == status)
    else:
        # Default: show all except discarded (ready, downloading, analyzing, pending)
        query = query.filter(Manga.status != "discarded")

    if language:
        query = query.filter(Manga.language == language)

    if tag:
        query = query.join(MangaTag).filter(MangaTag.tag == tag.lower())

    if search:
        query = query.filter(Manga.title.ilike(f"%{search}%"))

    total = query.count()
    items = (
        query.order_by(Manga.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Deduplicate (joinedload can create dupes with many-to-many-like joins)
    seen_ids: set[int] = set()
    unique_items: list[Manga] = []
    for item in items:
        if item.id not in seen_ids:
            seen_ids.add(item.id)
            unique_items.append(item)

    return MangaListOut(
        items=[MangaOut.model_validate(m) for m in unique_items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    """Get all unique tags with counts."""
    from sqlalchemy import func

    results = (
        db.query(MangaTag.tag, func.count(MangaTag.id).label("count"))
        .join(Manga)
        .filter(Manga.status != "discarded")
        .group_by(MangaTag.tag)
        .order_by(func.count(MangaTag.id).desc())
        .all()
    )

    return [{"tag": tag, "count": count} for tag, count in results]


@router.get("/{slug}", response_model=MangaDetailOut)
def get_manga(slug: str, db: Session = Depends(get_db)):
    """Get manga details by slug, including chapters."""
    manga = (
        db.query(Manga)
        .options(joinedload(Manga.tags), joinedload(Manga.chapters))
        .filter(Manga.slug == slug)
        .first()
    )

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    return MangaDetailOut.model_validate(manga)


@router.delete("/{slug}")
def delete_manga(slug: str, db: Session = Depends(get_db)):
    """Delete a manga and all its data."""
    import shutil
    from pathlib import Path

    from src.config import get_config

    manga = db.query(Manga).filter(Manga.slug == slug).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Delete files
    config = get_config()
    manga_dir = Path(config.scraper.download_path) / slug
    if manga_dir.exists():
        shutil.rmtree(manga_dir)

    db.delete(manga)
    db.commit()

    return {"ok": True, "deleted": slug}
