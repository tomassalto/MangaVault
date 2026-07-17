"""Chapter API routes — list pages, read chapters."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.db.database import get_db
from src.db.models import Chapter, Manga, Page

from ..schemas import ChapterDetailOut, PageOut

router = APIRouter(prefix="/manga/{slug}/chapters", tags=["chapters"])


@router.get("/{chapter_num}", response_model=ChapterDetailOut)
def get_chapter(slug: str, chapter_num: float, db: Session = Depends(get_db)):
    """Get a chapter with all its pages."""
    manga = db.query(Manga).filter(Manga.slug == slug).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    chapter = (
        db.query(Chapter)
        .options(joinedload(Chapter.pages))
        .filter(Chapter.manga_id == manga.id, Chapter.number == chapter_num)
        .first()
    )

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return ChapterDetailOut.model_validate(chapter)


@router.get("/{chapter_num}/pages", response_model=list[PageOut])
def get_chapter_pages(slug: str, chapter_num: float, db: Session = Depends(get_db)):
    """Get just the pages for a chapter (for the reader)."""
    manga = db.query(Manga).filter(Manga.slug == slug).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    chapter = (
        db.query(Chapter)
        .filter(Chapter.manga_id == manga.id, Chapter.number == chapter_num)
        .first()
    )

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    pages = (
        db.query(Page)
        .filter(Page.chapter_id == chapter.id)
        .order_by(Page.number)
        .all()
    )

    return [PageOut.model_validate(p) for p in pages]


@router.get("")
def list_chapters(slug: str, db: Session = Depends(get_db)):
    """List all chapters for a manga."""
    manga = db.query(Manga).filter(Manga.slug == slug).first()
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    chapters = (
        db.query(Chapter)
        .filter(Chapter.manga_id == manga.id)
        .order_by(Chapter.number)
        .all()
    )

    return [
        {
            "id": c.id,
            "number": c.number,
            "title": c.title,
            "page_count": c.page_count,
            "downloaded_at": c.downloaded_at,
        }
        for c in chapters
    ]
