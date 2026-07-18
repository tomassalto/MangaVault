"""Create a portfolio demo library with original generated assets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont
from slugify import slugify

from src.config import get_config
from src.db.database import SessionLocal, init_db
from src.db.models import AnalysisLog, Chapter, Manga, MangaTag, Page


PROJECT_ROOT = Path(__file__).resolve().parent.parent


DEMO_MANGA = [
    {
        "title": "Captain Comet and the Moon Raiders",
        "slug": "captain-comet-moon-raiders",
        "language": "en",
        "rating": "safe",
        "tags": ["golden-age", "sci-fi", "adventure"],
        "colors": ("#12233f", "#f23838", "#ffd43b"),
        "synopsis": "A rocket-age pilot defends Lunar Station Seven after masked raiders steal the map to a hidden gravity engine.",
    },
    {
        "title": "La Mascara Relampago",
        "slug": "la-mascara-relampago",
        "language": "es",
        "rating": "safe",
        "tags": ["superheroe", "aventura", "misterio"],
        "colors": ("#241036", "#ffb000", "#35c2ff"),
        "synopsis": "Un vigilante de medianoche persigue a una banda que roba electricidad de toda la ciudad para alimentar una maquina secreta.",
    },
    {
        "title": "Jungle Queen of Mars",
        "slug": "jungle-queen-of-mars",
        "language": "en",
        "rating": "safe",
        "tags": ["pulp", "jungle", "space"],
        "colors": ("#17351f", "#ff5c35", "#ffe66d"),
        "synopsis": "A stranded explorer becomes protector of a crystal jungle where every vine remembers a different planet.",
    },
    {
        "title": "El Tren Fantasma de Andromeda",
        "slug": "tren-fantasma-andromeda",
        "language": "es",
        "rating": "safe",
        "tags": ["sci-fi", "suspenso", "space-opera"],
        "colors": ("#071624", "#59d2fe", "#f9c74f"),
        "synopsis": "Una reportera sube a un tren orbital que desaparece cada noche y vuelve con pasajeros de decadas distintas.",
    },
    {
        "title": "Atomic Scarlet vs. The Clockwork Sun",
        "slug": "atomic-scarlet-clockwork-sun",
        "language": "en",
        "rating": "safe",
        "tags": ["superhero", "atomic-age", "action"],
        "colors": ("#2b1214", "#f94144", "#43aa8b"),
        "synopsis": "A city scientist becomes Atomic Scarlet and races to stop a mechanical sun from freezing time at noon.",
    },
]

LEGACY_DEMO_SLUGS = {
    "asterismo-cero",
    "iron-bento-club",
    "luna-de-papel",
    "neon-courier",
    "the-orchard-witch",
}

DEFAULT_DEMO_INITIAL_SLUGS = {
    "captain-comet-moon-raiders",
    "la-mascara-relampago",
}


PAGE_LINES = [
    [
        "Panel 1: A siren cracks the midnight sky.",
        "Panel 2: The hero spots a clue hidden in plain sight.",
        "Panel 3: WHAM! The first trap springs shut.",
    ],
    [
        "Panel 1: A secret machine hums below the city.",
        "Panel 2: The villain laughs from behind the control glass.",
        "Panel 3: ZAP! The countdown begins.",
    ],
    [
        "Panel 1: Allies race across a bridge of sparks.",
        "Panel 2: One brave choice turns the whole battle.",
        "Panel 3: The final page points toward a bigger mystery.",
    ],
]


def seed_demo_library(reset: bool = False, slugs: list[str] | None = None) -> dict[str, int]:
    """Populate the local database with original demo titles and generated images."""
    init_db()
    image_root = _image_root()
    selected_slugs = set(slugs) if slugs is not None else DEFAULT_DEMO_INITIAL_SLUGS

    db = SessionLocal()
    try:
        if reset:
            _clear_demo_data(db, image_root)

        created = 0
        for index, item in enumerate(DEMO_MANGA, start=1):
            if item["slug"] not in selected_slugs:
                continue
            existing = db.query(Manga).filter(Manga.slug == item["slug"]).first()
            if existing:
                continue
            _create_demo_manga(db, image_root, item, index)
            created += 1

        db.commit()
        return {"created": created, "total": db.query(Manga).count()}
    finally:
        db.close()


def import_demo_title(query: str) -> dict[str, object]:
    """Import one cached demo title, simulating the public ingestion path."""
    init_db()
    image_root = _image_root()
    item, index = _find_demo_item(query)

    db = SessionLocal()
    try:
        existing = db.query(Manga).filter(Manga.slug == item["slug"]).first()
        if existing:
            return {
                "created": False,
                "title": existing.title,
                "slug": existing.slug,
                "message": "Demo title was already imported.",
            }

        manga = _create_demo_manga(db, image_root, item, index)
        db.commit()
        return {
            "created": True,
            "title": manga.title,
            "slug": manga.slug,
            "message": "Demo title imported from the cached public dataset.",
        }
    finally:
        db.close()


def list_demo_manifest() -> list[dict[str, object]]:
    """Return the public demo catalog, including whether each title is imported."""
    init_db()
    db = SessionLocal()
    try:
        imported = {
            slug
            for (slug,) in db.query(Manga.slug)
            .filter(Manga.source_site == "demo")
            .all()
        }
        return [
            {
                "title": item["title"],
                "slug": item["slug"],
                "language": item["language"],
                "tags": item["tags"],
                "synopsis": item["synopsis"],
                "imported": item["slug"] in imported,
            }
            for item in DEMO_MANGA
        ]
    finally:
        db.close()


def _create_demo_manga(db, image_root: Path, item: dict, index: int) -> Manga:
    manga_dir = image_root / item["slug"]
    manga_dir.mkdir(parents=True, exist_ok=True)
    cover_rel = f"{item['slug']}/cover.png"
    _draw_cover(image_root / cover_rel, item)

    manga = Manga(
        title=item["title"],
        slug=item["slug"],
        synopsis=item["synopsis"],
        language=item["language"],
        source_url=None,
        source_site="demo",
        cover_path=cover_rel,
        status="ready",
        content_rating=item["rating"],
        total_chapters=2,
    )
    db.add(manga)
    db.flush()

    for tag in item["tags"]:
        db.add(MangaTag(manga_id=manga.id, tag=tag))

    _create_chapters(db, image_root, manga, item, index)
    db.add(
        AnalysisLog(
            manga_id=manga.id,
            model_used="demo-seed",
            tokens_used=420 + index * 35,
            raw_response="Demo metadata seeded for portfolio mode.",
            language_detected=item["language"],
            tags_detected=str(item["tags"]),
            accepted=True,
        )
    )
    return manga


def _find_demo_item(query: str) -> tuple[dict, int]:
    normalized = slugify(query or "")
    if not normalized:
        return DEMO_MANGA[0], 1

    for index, item in enumerate(DEMO_MANGA, start=1):
        if normalized in item["slug"] or normalized in slugify(item["title"]):
            return item, index

    aliases = {
        "batman": "la-mascara-relampago",
        "superman": "captain-comet-moon-raiders",
        "one-piece": "captain-comet-moon-raiders",
        "doctor-stone": "atomic-scarlet-clockwork-sun",
        "dr-stone": "atomic-scarlet-clockwork-sun",
    }
    mapped_slug = aliases.get(normalized)
    if mapped_slug:
        for index, item in enumerate(DEMO_MANGA, start=1):
            if item["slug"] == mapped_slug:
                return item, index

    index = sum(ord(char) for char in normalized) % len(DEMO_MANGA)
    return DEMO_MANGA[index], index + 1


def _image_root() -> Path:
    config = get_config()
    image_root = Path(config.scraper.download_path)
    if not image_root.is_absolute():
        image_root = PROJECT_ROOT / image_root
    image_root.mkdir(parents=True, exist_ok=True)
    return image_root


def _clear_demo_data(db, image_root: Path) -> None:
    demo_mangas = db.query(Manga).filter(Manga.source_site == "demo").all()
    demo_slugs = {manga.slug for manga in demo_mangas}
    demo_slugs.update(item["slug"] for item in DEMO_MANGA)
    demo_slugs.update(LEGACY_DEMO_SLUGS)

    for manga in demo_mangas:
        db.delete(manga)
    db.commit()

    for slug in demo_slugs:
        path = image_root / slug
        if path.exists():
            import shutil

            shutil.rmtree(path)


def _create_chapters(db, image_root: Path, manga: Manga, item: dict, offset: int) -> None:
    for chapter_num in (1, 2):
        chapter_path = f"{manga.slug}/ch-{chapter_num}"
        chapter_dir = image_root / chapter_path
        chapter_dir.mkdir(parents=True, exist_ok=True)
        chapter = Chapter(
            manga_id=manga.id,
            number=float(chapter_num),
            title=_chapter_title(item, chapter_num),
            page_count=3,
            path=chapter_path,
            source_url=None,
            downloaded_at=datetime.now(timezone.utc),
        )
        db.add(chapter)
        db.flush()

        for page_num in (1, 2, 3):
            rel = f"{chapter_path}/{page_num:03}.png"
            ocr_text = _page_text(item, chapter_num, page_num)
            _draw_page(image_root / rel, item, chapter_num, page_num, ocr_text, offset)
            db.add(
                Page(
                    chapter_id=chapter.id,
                    number=page_num,
                    image_path=rel,
                    width=900,
                    height=1300,
                    ocr_text=ocr_text,
                )
            )


def _page_text(item: dict, chapter_num: int, page_num: int) -> str:
    base = PAGE_LINES[(chapter_num + page_num - 2) % len(PAGE_LINES)]
    if item["language"] == "es":
        translated = [
            "Panel 1: Una sirena parte el cielo de medianoche.",
            "Panel 2: La pista aparece justo donde nadie mira.",
            "Panel 3: ZAS! La primera trampa se cierra.",
        ]
        base = translated
    return f"{item['title']} chapter {chapter_num}, page {page_num}. " + " ".join(base)


def _chapter_title(item: dict, chapter_num: int) -> str:
    if item["language"] == "es":
        return ["La pista imposible", "Medianoche en llamas"][chapter_num - 1]
    return ["The Impossible Signal", "Midnight Machine"][chapter_num - 1]


def _draw_cover(path: Path, item: dict) -> None:
    bg, primary, secondary = item["colors"]
    img = Image.new("RGB", (720, 960), bg)
    draw = ImageDraw.Draw(img)
    font_title = _font(50)
    font_banner = _font(24)
    font_issue = _font(20)
    font_bang = _font(64)

    draw.rectangle((0, 0, 720, 92), fill=secondary)
    draw.text((32, 25), "MANGAVAULT PRESENTS", fill="#171717", font=font_banner)
    draw.rectangle((34, 116, 686, 915), outline="#f8f2de", width=7)
    draw.rectangle((52, 134, 668, 897), outline=primary, width=5)

    burst = [
        (360, 175), (405, 282), (520, 238), (470, 350), (590, 390), (468, 430),
        (520, 552), (405, 505), (360, 625), (315, 505), (200, 552), (252, 430),
        (130, 390), (250, 350), (200, 238), (315, 282),
    ]
    draw.polygon(burst, fill=primary, outline="#111111")
    draw.ellipse((250, 260, 470, 480), fill=secondary, outline="#111111", width=6)
    draw.rectangle((330, 470, 390, 720), fill="#f8f2de", outline="#111111", width=5)
    draw.polygon([(270, 720), (450, 720), (530, 860), (190, 860)], fill=primary, outline="#111111")
    draw.line((126, 262, 590, 750), fill="#f8f2de", width=8)
    draw.line((590, 250, 116, 765), fill="#f8f2de", width=8)

    y = 610
    for line in wrap(item["title"].upper(), width=16):
        draw.rectangle((70, y - 6, 650, y + 58), fill="#111111")
        draw.text((92, y), line, fill="#ffffff", font=font_title)
        y += 66

    draw.ellipse((536, 112, 664, 240), fill="#ffffff", outline="#111111", width=5)
    draw.text((565, 142), "No. 1", fill="#111111", font=font_issue)
    draw.text((560, 172), "10c", fill="#111111", font=font_issue)
    draw.text((88, 152), "ZAP!", fill=secondary, font=font_bang)
    img.save(path)


def _draw_page(path: Path, item: dict, chapter_num: int, page_num: int, text: str, offset: int) -> None:
    bg, primary, secondary = item["colors"]
    img = Image.new("RGB", (900, 1300), "#f8f0d8")
    draw = ImageDraw.Draw(img)
    font_panel = _font(20)
    font_text = _font(22)
    font_small = _font(18)
    font_fx = _font(50)
    font_caption = _font(21)

    draw.rectangle((0, 0, 900, 68), fill=bg)
    draw.text((40, 20), f"{item['title']}  /  Ch. {chapter_num}  /  Page {page_num}", fill="white", font=font_small)

    panels = [
        (55, 105, 845, 420),
        (55, 455, 420, 785),
        (455, 455, 845, 785),
        (55, 820, 845, 1215),
    ]
    lines = text.split(". ")[1:]
    for i, box in enumerate(panels):
        x1, y1, x2, y2 = box
        draw.rectangle(box, fill="#fff7df", outline="#171717", width=4)
        fill = primary if (i + page_num + offset) % 2 == 0 else secondary
        art_box = (x1 + 14, y1 + 14, x2 - 14, y2 - 74)
        draw.rectangle(art_box, fill=fill)
        _draw_halftone(draw, art_box, bg, step=28)

        if i == 0:
            _draw_city_scene(draw, art_box, bg, secondary)
            _draw_character(draw, x1 + 95, y1 + 95, 1.05, bg, "#f8f2de")
            _draw_speech_bubble(
                draw,
                (x2 - 285, y1 + 34, x2 - 42, y1 + 118),
                "The signal is moving!",
                font_text,
            )
        elif i == 1:
            _draw_character(draw, x1 + 70, y1 + 85, 0.82, bg, "#f8f2de")
            _draw_starburst(draw, (x1 + 202, y1 + 55), 76, "BAM!", font_fx, "#fff3a3", "#111111")
        elif i == 2:
            _draw_villain(draw, x1 + 78, y1 + 78, 0.78, bg)
            _draw_speech_bubble(
                draw,
                (x1 + 168, y1 + 42, x2 - 32, y1 + 122),
                "Too late, hero!",
                font_text,
            )
        else:
            _draw_speed_lines(draw, art_box, bg)
            _draw_character(draw, x1 + 210, y1 + 88, 1.0, bg, "#f8f2de")
            _draw_starburst(draw, (x2 - 175, y1 + 105), 84, "ZAP!", font_fx, secondary, "#111111")

        caption = _clean_caption(lines[i] if i < len(lines) else "The trail continues into next issue.")
        caption_box = (x1 + 20, y2 - 64, x2 - 20, y2 - 18)
        draw.rectangle(caption_box, fill="#fff7df")
        draw.text((x1 + 28, y2 - 58), f"Panel {i + 1}", fill="#111111", font=font_panel)
        _draw_wrapped_text(
            draw,
            caption,
            (x1 + 118, y2 - 58),
            max_width=(x2 - x1 - 155),
            font=font_caption,
            fill="#232323",
            line_gap=3,
            max_lines=2,
        )

    img.save(path)


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    origin: tuple[int, int],
    max_width: int,
    font,
    fill: str,
    line_gap: int = 4,
    max_lines: int | None = None,
) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "...", font=font)[2] > max_width:
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] += "..."

    x, y = origin
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + line_gap
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, fill=fill, font=font)


def _clean_caption(text: str) -> str:
    if ":" in text and text.lower().startswith("panel "):
        return text.split(":", 1)[1].strip()
    return text.strip()


def _draw_halftone(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str, step: int) -> None:
    x1, y1, x2, y2 = box
    for y in range(y1 + 12, y2, step):
        for x in range(x1 + 12, x2, step):
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)


def _draw_city_scene(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str, light: str) -> None:
    x1, y1, x2, y2 = box
    horizon = y2 - 70
    for idx, x in enumerate(range(x1 + 24, x2 - 60, 62)):
        height = 70 + (idx % 4) * 28
        draw.rectangle((x, horizon - height, x + 48, horizon), fill=color)
        for wy in range(horizon - height + 12, horizon - 8, 26):
            draw.rectangle((x + 10, wy, x + 19, wy + 10), fill=light)
            draw.rectangle((x + 29, wy, x + 38, wy + 10), fill=light)
    draw.line((x1 + 20, horizon, x2 - 20, horizon), fill=color, width=5)


def _draw_speed_lines(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str) -> None:
    x1, y1, x2, y2 = box
    for offset in range(0, 260, 34):
        draw.line((x1 + 25, y1 + 35 + offset, x2 - 45, y1 + 5 + offset), fill=color, width=5)


def _draw_character(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    scale: float,
    suit: str,
    cape: str,
) -> None:
    s = scale
    draw.polygon(
        [
            (x + int(72 * s), y + int(96 * s)),
            (x + int(178 * s), y + int(54 * s)),
            (x + int(158 * s), y + int(210 * s)),
        ],
        fill=cape,
        outline="#111111",
    )
    draw.ellipse((x + int(44 * s), y + int(24 * s), x + int(104 * s), y + int(84 * s)), fill="#ffd7aa", outline="#111111", width=3)
    draw.rectangle((x + int(54 * s), y + int(82 * s), x + int(118 * s), y + int(176 * s)), fill=suit, outline="#111111", width=3)
    draw.line((x + int(58 * s), y + int(112 * s), x + int(18 * s), y + int(154 * s)), fill="#111111", width=max(3, int(6 * s)))
    draw.line((x + int(116 * s), y + int(112 * s), x + int(168 * s), y + int(130 * s)), fill="#111111", width=max(3, int(6 * s)))
    draw.line((x + int(72 * s), y + int(176 * s), x + int(44 * s), y + int(238 * s)), fill="#111111", width=max(3, int(7 * s)))
    draw.line((x + int(104 * s), y + int(176 * s), x + int(142 * s), y + int(235 * s)), fill="#111111", width=max(3, int(7 * s)))
    draw.rectangle((x + int(64 * s), y + int(116 * s), x + int(108 * s), y + int(142 * s)), fill="#ffffff", outline="#111111")


def _draw_villain(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, color: str) -> None:
    s = scale
    draw.ellipse((x + int(42 * s), y + int(24 * s), x + int(112 * s), y + int(94 * s)), fill="#f0c39b", outline="#111111", width=3)
    draw.polygon(
        [
            (x + int(54 * s), y + int(94 * s)),
            (x + int(130 * s), y + int(104 * s)),
            (x + int(154 * s), y + int(220 * s)),
            (x + int(22 * s), y + int(220 * s)),
        ],
        fill=color,
        outline="#111111",
    )
    draw.rectangle((x + int(48 * s), y + int(48 * s), x + int(108 * s), y + int(66 * s)), fill="#111111")
    draw.line((x + int(42 * s), y + int(132 * s), x + int(5 * s), y + int(178 * s)), fill="#111111", width=max(3, int(6 * s)))
    draw.line((x + int(120 * s), y + int(132 * s), x + int(176 * s), y + int(146 * s)), fill="#111111", width=max(3, int(6 * s)))


def _draw_speech_bubble(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=24, fill="#ffffff", outline="#111111", width=3)
    draw.polygon([(x1 + 42, y2 - 6), (x1 + 78, y2 + 34), (x1 + 102, y2 - 5)], fill="#ffffff", outline="#111111")
    _draw_wrapped_text(draw, text, (x1 + 20, y1 + 18), max_width=(x2 - x1 - 40), font=font, fill="#111111", max_lines=2)


def _draw_starburst(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    text: str,
    font,
    fill: str,
    outline: str,
) -> None:
    import math

    cx, cy = center
    points = []
    for i in range(18):
        angle = math.pi * 2 * i / 18
        r = radius if i % 2 == 0 else int(radius * 0.55)
        points.append((cx + int(math.cos(angle) * r), cy + int(math.sin(angle) * r)))
    draw.polygon(points, fill=fill, outline=outline)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bbox[2] - bbox[0]) / 2, cy - (bbox[3] - bbox[1]) / 2 - 4), text, fill=outline, font=font)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()
