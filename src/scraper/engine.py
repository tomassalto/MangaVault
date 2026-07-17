"""Scraper engine — orchestrates the full scraping pipeline."""

import asyncio
import re
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from slugify import slugify


def _domain_from_url(url: str) -> str:
    """Extrae el dominio de una URL para no repetir el mismo sitio."""
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except Exception:
        return ""

from src.config import AppConfig
from src.db.database import SessionLocal
from src.db.models import Chapter, Manga, MangaTag, Page

from .adapters.base import BaseAdapter, MangaResult, PageUrl
from .adapters.generic import GenericAdapter
from .downloader import download_chapter_pages, download_cover
from .search import build_search_query, search_duckduckgo

try:
    from .adapters.mangadex import MangaDexAdapter
except ImportError:
    MangaDexAdapter = None  # type: ignore[assignment]

try:
    from .adapters.manhwaweb import ManhwaWebAdapter
except ImportError:
    ManhwaWebAdapter = None  # type: ignore[assignment]

ProgressCallback = Callable[[str, dict], None]


def _create_adapters(config: AppConfig) -> list[BaseAdapter]:
    """Create adapter instances based on config, sorted by priority."""
    adapters: list[tuple[int, BaseAdapter]] = []

    for site in config.scraper.sites:
        if not site.enabled:
            continue
        if site.name == "mangadex" and MangaDexAdapter is not None:
            adapters.append((site.priority, MangaDexAdapter(site.base_url)))
        elif site.name == "manhwaweb" and ManhwaWebAdapter is not None:
            adapters.append((site.priority, ManhwaWebAdapter(site.base_url)))

    adapters.sort(key=lambda x: x[0])
    return [a for _, a in adapters]


class ScraperEngine:
    """Main scraper orchestrator."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.adapters = _create_adapters(config)
        self.download_path = config.scraper.download_path

    async def run(
        self,
        genre: str | None = None,
        limit: int = 10,
        site_name: str | None = None,
        query: str | None = None,
        initial_chapters: int | None = None,
        progress_callback: ProgressCallback | None = None,
        direct_chapter_url: str | None = None,
    ) -> list[Manga]:
        """
        Run a full scraping session.

        Si direct_chapter_url está definido: no se busca nada; solo se scrapea ese capítulo (1).
        Si no:
        1. Search for manga via adapters (priority order)
        2. For each unique title: try sources in order until one succeeds
        3. Save to database with status='downloading'
        """
        def report(phase: str, detail: dict) -> None:
            if progress_callback:
                progress_callback(phase, detail)

        db = SessionLocal()
        processed: list[Manga] = []

        try:
            if direct_chapter_url and direct_chapter_url.strip():
                report("search", {"message": "Usando solo la URL indicada (sin búsqueda)."})
                manga = await self._run_direct_chapter(
                    direct_chapter_url.strip(), db, report
                )
                if manga:
                    processed.append(manga)
                    report("manga_done", {"title": manga.title, "chapters": manga.total_chapters})
                report("done", {"processed": len(processed), "total": 1, "attempted": 1})
                return processed

            report("search", {"message": "Searching..."})
            all_results = await self._search(genre, limit, site_name, report, query=query)

            report("search", {
                "message": f"Found {len(all_results)} results",
                "to_process": min(limit, len(all_results)),
                "limit": limit,
            })

            # ── Cuando buscamos por query, construir UN grupo con todas las fuentes ──
            # Los resultados de DuckDuckGo tienen títulos distintos (título de la página web),
            # así que no podemos agrupar por slug del título. En cambio, cuando hay un query
            # específico, todos los resultados son candidatos para ESE manga.
            # Cuando no hay query (búsqueda por género), cada resultado es un manga distinto.

            from collections import defaultdict

            if query:
                # Modo búsqueda por título: un solo manga, múltiples fuentes
                # Ordenar: adapters nativos por prioridad de config, luego resultados web
                adapter_priority = {a.name: i for i, a in enumerate(self.adapters)}
                native = [r for r in all_results if not r.source_site.startswith("search:")]
                native.sort(key=lambda r: adapter_priority.get(r.source_site, 999))
                web = [r for r in all_results if r.source_site.startswith("search:")]
                def dedup_by_domain(results: list) -> list:
                    seen_d: set[str] = set()
                    out = []
                    for r in results:
                        d = _domain_from_url(r.url) or r.source_site
                        if d not in seen_d:
                            seen_d.add(d)
                            out.append(r)
                    return out
                all_sources = dedup_by_domain(native + web)

                query_slug = slugify(query)
                existing = db.query(Manga).filter(Manga.slug == query_slug).first()
                manga_total = 0 if existing else 1

                report("search", {"message": f"{len(all_sources)} fuentes disponibles para '{query}'"})

                if existing:
                    report("skip", {"title": query, "reason": "already exists"})
                else:
                    report("manga_start", {
                        "title": query,
                        "index": 1,
                        "total": 1,
                        "sources": len(all_sources),
                    })
                    n_chapters = initial_chapters if initial_chapters is not None else 5
                    manga = await self._process_manga_with_fallback(
                        all_sources, db, report, initial_chapters=n_chapters,
                        preferred_slug=query_slug,
                    )
                    if manga:
                        processed.append(manga)
                        report("manga_done", {"title": manga.title, "chapters": manga.total_chapters})
                    else:
                        report("skip", {
                            "title": query,
                            "reason": "all sources failed",
                            "message": f"Ninguna de las {len(all_sources)} fuentes funcionó.",
                        })

            else:
                # Modo búsqueda por género: cada resultado es un manga distinto
                groups: dict[str, list[MangaResult]] = defaultdict(list)
                seen_in_group: dict[str, set[str]] = defaultdict(set)

                for result in all_results:
                    slug = slugify(result.title)
                    domain = _domain_from_url(result.url) or result.source_site
                    if domain not in seen_in_group[slug]:
                        seen_in_group[slug].add(domain)
                        groups[slug].append(result)

                unique_slugs: list[str] = []
                for result in all_results:
                    slug = slugify(result.title)
                    if slug not in unique_slugs:
                        unique_slugs.append(slug)

                manga_total = sum(
                    1 for s in unique_slugs
                    if not db.query(Manga).filter(Manga.slug == s).first()
                )
                report("search", {"message": f"{manga_total} nuevos mangas a procesar"})

                processed_count = 0
                for slug in unique_slugs:
                    if processed_count >= limit:
                        break
                    if db.query(Manga).filter(Manga.slug == slug).first():
                        report("skip", {"title": slug, "reason": "already exists"})
                        continue

                    sources = groups[slug]
                    report("manga_start", {
                        "title": sources[0].title,
                        "index": processed_count + 1,
                        "total": min(limit, manga_total),
                        "sources": len(sources),
                    })

                    n_chapters = initial_chapters if initial_chapters is not None else 3
                    manga = await self._process_manga_with_fallback(
                        sources, db, report, initial_chapters=n_chapters
                    )
                    if manga:
                        processed.append(manga)
                        processed_count += 1
                        report("manga_done", {"title": manga.title, "chapters": manga.total_chapters})
                    else:
                        report("skip", {
                            "title": sources[0].title,
                            "reason": "all sources failed",
                            "message": f"Ninguna de las {len(sources)} fuentes funcionó.",
                        })
                    await asyncio.sleep(self.config.scraper.delay_between_requests)

            report("done", {
                "processed": len(processed),
                "total": manga_total,
                "attempted": min(limit, manga_total),
            })

        finally:
            db.close()

        return processed

    async def _process_manga_with_fallback(
        self,
        sources: list[MangaResult],
        db,
        report: ProgressCallback | None = None,
        initial_chapters: int = 3,
        preferred_slug: str | None = None,
    ) -> Manga | None:
        """
        Intenta procesar un manga probando cada fuente disponible en orden.
        Retorna el primer resultado exitoso, o None si todas fallan.
        preferred_slug: slug canónico a usar en DB (anula el slug del título de la fuente).
        """
        failed_domains: set[str] = set()

        for idx, result in enumerate(sources):
            domain = _domain_from_url(result.url)

            if domain and domain in failed_domains:
                if report:
                    report("skip", {
                        "title": result.title,
                        "reason": "domain already failed",
                        "message": f"Saltando {domain} (ya falló antes)",
                    })
                continue

            if report:
                report("search", {
                    "message": f"Fuente {idx + 1}/{len(sources)}: {result.source_site} · {domain or result.url[:50]}",
                    "adapter": result.source_site,
                    "source_url": result.url[:80],
                })

            try:
                manga = await self._process_manga(
                    result, db, report,
                    initial_chapters=initial_chapters,
                    preferred_slug=preferred_slug,
                )
                if manga:
                    return manga
                else:
                    if domain:
                        failed_domains.add(domain)
                    if idx + 1 < len(sources):
                        next_src = sources[idx + 1]
                        next_domain = _domain_from_url(next_src.url)
                        report("search", {
                            "message": f"Fuente fallida. Probando siguiente ({idx + 2}/{len(sources)}): {next_src.source_site} · {next_domain}",
                        })
            except Exception as e:
                if domain:
                    failed_domains.add(domain)
                if report:
                    report("error", {"message": str(e), "title": result.title, "context": result.source_site})

            await asyncio.sleep(self.config.scraper.delay_between_requests)

        return None

    async def _search(
        self,
        genre: str | None,
        limit: int,
        site_name: str | None,
        report: ProgressCallback | None = None,
        query: str | None = None,
    ) -> list[MangaResult]:
        """Search for manga across all adapters (by keyword/query or genre)."""
        all_results: list[MangaResult] = []
        adapters = self.adapters
        if site_name:
            adapters = [a for a in adapters if a.name == site_name]

        use_keyword = bool(query and query.strip())

        # Buscar por nombre: primero en español (DuckDuckGo), luego adapters (MangaDex, etc.)
        if use_keyword and self.config.scraper.search.enabled and "es" in (self.config.scraper.languages or []):
            try:
                if report:
                    report("search", {"adapter": "DuckDuckGo", "message": f"Buscando '{query}' en español…"})
                es_query = f"{query.strip()} manga español leer"
                es_results = await search_duckduckgo(es_query, max_results=limit * 2)
                all_results.extend(es_results)
                if report and es_results:
                    report("search", {"adapter": "DuckDuckGo", "count": len(es_results)})
            except Exception as e:
                if report:
                    report("error", {"message": str(e), "context": "DuckDuckGo español"})

        for adapter in adapters:
            try:
                if report:
                    msg = f"Buscando en {adapter.name}…" if use_keyword else f"Searching {adapter.name}…"
                    report("search", {"adapter": adapter.name, "message": msg})
                if use_keyword:
                    results = await adapter.search(genre=None, keyword=query.strip(), limit=limit)
                else:
                    results = await adapter.search(genre=genre, limit=limit)
                all_results.extend(results)
                if report and results:
                    report("search", {"adapter": adapter.name, "count": len(results)})
            except Exception as e:
                if report:
                    report("error", {"message": str(e), "context": adapter.name})

        # Si hay pocos resultados y tenemos inglés en config, buscar también en inglés
        if (
            use_keyword
            and self.config.scraper.search.enabled
            and len(all_results) < limit
            and not site_name
            and "en" in (self.config.scraper.languages or [])
        ):
            try:
                if report:
                    report("search", {"adapter": "DuckDuckGo", "message": f"Buscando '{query}' en inglés…"})
                en_query = f"{query.strip()} manga read online"
                seen = {r.url for r in all_results}
                en_results = await search_duckduckgo(en_query, max_results=limit * 2)
                for r in en_results:
                    if r.url not in seen:
                        seen.add(r.url)
                        all_results.append(r)
                if report and en_results:
                    report("search", {"adapter": "DuckDuckGo (en)", "count": len(en_results)})
            except Exception as e:
                if report:
                    report("error", {"message": str(e), "context": "DuckDuckGo inglés"})

        if (
            not use_keyword
            and self.config.scraper.search.enabled
            and len(all_results) < limit
            and not site_name
        ):
            for lang in self.config.scraper.languages:
                search_query = build_search_query(genre, None, lang)
                try:
                    if report:
                        report("search", {"adapter": "DuckDuckGo", "lang": lang})
                    search_results = await search_duckduckgo(search_query, max_results=limit * 2)
                    all_results.extend(search_results)
                except Exception as e:
                    if report:
                        report("error", {"message": str(e), "context": "DuckDuckGo"})

        return all_results

    async def _process_manga(
        self,
        result: MangaResult,
        db,
        report: ProgressCallback | None = None,
        initial_chapters: int = 3,
        preferred_slug: str | None = None,
    ) -> Manga | None:
        """Process a single manga: create record, download cover + first chapters."""
        slug = preferred_slug or slugify(result.title)

        manga = Manga(
            title=result.title,
            slug=slug,
            synopsis=result.description,
            language=result.language,
            source_url=result.url,
            source_site=result.source_site,
            status="downloading",
        )
        db.add(manga)
        db.flush()

        for genre in result.genres:
            db.add(MangaTag(manga_id=manga.id, tag=genre.lower()))

        if result.cover_url:
            cover_rel = await download_cover(
                manga, result.cover_url, self.download_path, progress_callback=report
            )
            if cover_rel:
                manga.cover_path = cover_rel

        adapter = self._get_adapter_for(result)
        if not adapter:
            db.rollback()
            return None
        manga.source_site = adapter.name

        if report:
            site_domain = result.url.split("/")[2] if len(result.url.split("/")) > 2 else result.url
            report("search", {
                "message": f"Fuente: {adapter.name} · {site_domain}",
                "adapter": adapter.name,
                "source_url": result.url[:80] + ("…" if len(result.url) > 80 else ""),
            })

        only_preferred = getattr(self.config.scraper, "only_preferred_language", False)
        lang = self.config.scraper.languages[0] if self.config.scraper.languages else None

        try:
            chapters_info = await adapter.get_chapters(
                result.url,
                language=lang,
                external_id=result.external_id,
            )
            if not chapters_info and lang and not only_preferred:
                chapters_info = await adapter.get_chapters(
                    result.url,
                    language=None,
                    external_id=result.external_id,
                )
        except Exception as e:
            if report:
                report("error", {"message": str(e), "context": "get_chapters"})
            db.rollback()
            return None

        if not chapters_info:
            if report:
                if only_preferred:
                    report("skip", {
                        "title": result.title,
                        "reason": "no chapters in preferred language",
                        "message": "Sin capítulos en español en esta fuente.",
                    })
                else:
                    report("skip", {
                        "title": result.title,
                        "reason": "no chapters found",
                        "message": "Esta fuente no devolvió capítulos.",
                    })
            db.rollback()
            return None

        chapters_info.sort(key=lambda c: c.number)

        if report:
            report("search", {
                "message": f"Capítulos encontrados: {len(chapters_info)} · Idioma: {lang or 'cualquiera'}",
                "chapters_count": len(chapters_info),
                "language": lang or "any",
            })

        # Análisis previo: verificar que el primer capítulo tenga suficientes imágenes
        min_images = getattr(self.config.scraper, "min_images_per_chapter", 50)
        first_chapter = chapters_info[0]

        if report:
            report("chapter", {
                "message": f"Analizando capítulo 1 ({first_chapter.title or first_chapter.number})…",
                "chapter": 1,
                "total": 1,
                "manga": manga.title,
            })

        try:
            first_page_urls = await adapter.get_pages(
                first_chapter.url, external_id=first_chapter.external_id
            )
        except Exception as e:
            if report:
                report("error", {"message": str(e), "context": "get_pages (análisis)"})
            first_page_urls = []

        num_images = len(first_page_urls) if first_page_urls else 0

        if report:
            report("search", {
                "message": f"Capítulo 1: {num_images} imágenes encontradas (mínimo requerido: {min_images})",
                "images_found": num_images,
                "min_required": min_images,
            })

        if num_images < min_images and not only_preferred and adapter.name == "mangadex":
            # Intentar otros idiomas como fallback (inglés primero, luego sin filtro)
            fallback_langs = []
            if lang and lang.startswith("es"):
                fallback_langs = ["en", None]
            elif lang and lang != "en":
                fallback_langs = ["en", None]
            else:
                fallback_langs = [None]

            for fb_lang in fallback_langs:
                lang_label = fb_lang or "any"
                if report:
                    report("search", {
                        "message": f"Solo {num_images} imgs en '{lang}'. Intentando idioma: {lang_label}…",
                    })
                try:
                    fb_chapters = await adapter.get_chapters(
                        result.url, language=fb_lang, external_id=result.external_id
                    )
                    if not fb_chapters:
                        if report:
                            report("search", {"message": f"Sin capítulos en idioma '{lang_label}'"})
                        continue

                    # Buscar el capítulo 1 (o el primero disponible)
                    fb_chapters.sort(key=lambda c: c.number)
                    fb_first = fb_chapters[0]

                    if report:
                        report("search", {
                            "message": f"Verificando cap. {fb_first.number} en idioma '{lang_label}'…",
                        })

                    fb_pages = await adapter.get_pages(fb_first.url, external_id=fb_first.external_id)
                    fb_count = len(fb_pages) if fb_pages else 0

                    if report:
                        report("search", {
                            "message": f"Idioma '{lang_label}': {fb_count} imágenes en cap. 1",
                            "images_found": fb_count,
                        })

                    if fb_count >= min_images:
                        chapters_info = fb_chapters
                        first_chapter = fb_first
                        first_page_urls = fb_pages
                        num_images = fb_count
                        lang = fb_lang or "en"
                        if report:
                            report("search", {
                                "message": f"Fallback '{lang}' OK: {num_images} imágenes. Continuando…",
                                "images_found": num_images,
                            })
                        break
                except Exception as e:
                    if report:
                        report("error", {"message": str(e), "context": f"fallback lang={lang_label}"})

        if num_images < min_images:
            if report:
                report("skip", {
                    "title": result.title,
                    "reason": "few images",
                    "message": f"Solo {num_images} imágenes en el cap. 1 (mín. {min_images}). Probando otra fuente…",
                })
            db.rollback()
            return None

        if report:
            report("search", {"message": f"OK: {num_images} imágenes. Iniciando descarga…"})

        max_chapters = initial_chapters
        for ch_idx, ch_info in enumerate(chapters_info[:max_chapters]):
            if report:
                report(
                    "chapter",
                    {
                        "chapter": ch_idx + 1,
                        "total": min(max_chapters, len(chapters_info)),
                        "title": ch_info.title or f"Ch {ch_info.number}",
                        "manga": manga.title,
                    },
                )
            try:
                if ch_idx == 0 and first_page_urls:
                    page_urls = first_page_urls
                else:
                    page_urls = await adapter.get_pages(
                        ch_info.url, external_id=ch_info.external_id
                    )
                if not page_urls:
                    continue

                chapter = Chapter(
                    manga_id=manga.id,
                    number=ch_info.number,
                    title=ch_info.title,
                    page_count=len(page_urls),
                    source_url=ch_info.url,
                    path=f"{slug}/ch-{ch_info.number:g}",
                )
                db.add(chapter)
                db.flush()

                filter_cfg = getattr(self.config.scraper, "image_filter", None)
                filter_dict = filter_cfg.model_dump() if filter_cfg and hasattr(filter_cfg, "model_dump") else (filter_cfg.dict() if filter_cfg and hasattr(filter_cfg, "dict") else None)
                ollama_host = getattr(getattr(self.config, "analyzer", None), "ollama_host", "http://localhost:11434")
                pages_data = await download_chapter_pages(
                    manga,
                    chapter,
                    [{"number": p.number, "url": p.url, "filename": p.filename} for p in page_urls],
                    self.download_path,
                    delay=self.config.scraper.delay_between_requests / 2,
                    progress_callback=report,
                    image_filter_config=filter_dict,
                    ollama_host=ollama_host,
                )

                for p_data in pages_data:
                    db.add(
                        Page(
                            chapter_id=chapter.id,
                            number=p_data["number"],
                            image_path=p_data["image_path"],
                            width=p_data.get("width"),
                            height=p_data.get("height"),
                        )
                    )

                chapter.page_count = len(pages_data)
                chapter.downloaded_at = datetime.now(timezone.utc)

                await asyncio.sleep(self.config.scraper.delay_between_requests)

            except Exception as e:
                if report:
                    report("error", {"message": str(e), "context": f"chapter {ch_info.number}"})

        manga.total_chapters = len(
            [c for c in db.query(Chapter).filter(Chapter.manga_id == manga.id).all()]
        )
        db.commit()
        return manga

    def _get_adapter_for(self, result: MangaResult) -> BaseAdapter | None:
        """Get the right adapter for a manga result."""
        for adapter in self.adapters:
            if adapter.name == result.source_site:
                return adapter

        if result.source_site.startswith("search:") and result.url:
            url_lower = result.url.lower()
            if "manhwaweb.com" in url_lower:
                for a in self.adapters:
                    if a.name == "manhwaweb":
                        return a
            return GenericAdapter()

        return self.adapters[0] if self.adapters else None

    def _get_adapter_by_name(self, site_name: str) -> BaseAdapter | None:
        """Get adapter by site name."""
        for adapter in self.adapters:
            if adapter.name == site_name:
                return adapter
        return None

    def _get_adapter_for_url(self, url: str) -> BaseAdapter | None:
        """Get the adapter that can handle this chapter/manga URL."""
        if not url:
            return None
        url_lower = url.lower()
        if "manhwaweb.com" in url_lower:
            for a in self.adapters:
                if a.name == "manhwaweb":
                    return a
        if "mangadex.org" in url_lower or "mangadex.org" in url_lower:
            for a in self.adapters:
                if a.name == "mangadex":
                    return a
        try:
            parsed = urlparse(url)
            base = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else ""
        except Exception:
            base = ""
        return GenericAdapter(base_url=base)

    def _title_from_chapter_url(self, url: str) -> tuple[str, str]:
        """Derive (title, slug) from a chapter URL. Ej: ManhwaWeb /leer/mato-seihei-no-slave_xxx-1."""
        try:
            path = urlparse(url).path or ""
            parts = path.strip("/").split("/")
            if not parts:
                return "Manga", "manga"
            last = parts[-1]
            if "manhwaweb.com" in url.lower() and "/leer/" in path.lower():
                slug_part = last.split("_")[0] if "_" in last else last
                slug_part = slug_part.rsplit("-", 1)[0] if slug_part.replace(".", "").isdigit() or (len(slug_part) > 1 and slug_part[-1].isdigit()) else slug_part
                if "-" in slug_part and slug_part.split("-")[-1].isdigit():
                    slug_part = slug_part.rsplit("-", 1)[0]
                slug = slug_part.replace("_", "-").lower()
                title = slug.replace("-", " ").title()
                return title or "Manga", slug or "manga"
            slug = slugify(last.split("?")[0]) or "manga"
            return slug.replace("-", " ").title(), slug
        except Exception:
            return "Manga", "manga"

    async def _run_direct_chapter(
        self, chapter_url: str, db, report: ProgressCallback | None
    ) -> Manga | None:
        """Scrape only this chapter URL: create/find manga, get_pages, save as chapter 1. No search."""
        adapter = self._get_adapter_for_url(chapter_url)
        if not adapter:
            if report:
                report("error", {"message": "No hay adapter para esta URL", "context": chapter_url[:60]})
            return None

        title, slug = self._title_from_chapter_url(chapter_url)
        existing = db.query(Manga).filter(Manga.slug == slug).first()
        if existing:
            if report:
                report("skip", {"title": title, "reason": "already exists", "message": f"Ya existe en la biblioteca: {existing.title}"})
            return None

        manga_page_url = chapter_url
        if "manhwaweb.com" in chapter_url.lower() and "/leer/" in chapter_url.lower():
            # /leer/mato-seihei-no-slave_1690713720857-1 → mato-seihei-no-slave_1690713720857
            full_slug = chapter_url.split("/leer/")[-1].split("?")[0].rstrip("/")
            manga_slug = re.sub(r"-\d+$", "", full_slug)
            manga_page_url = f"https://www.manhwaweb.com/manhwa/{manga_slug}"

        manga = Manga(
            title=title,
            slug=slug,
            synopsis=None,
            language="es",
            source_url=manga_page_url,
            source_site=adapter.name,
            status="downloading",
        )
        db.add(manga)
        db.flush()

        if report:
            report("manga_start", {"title": title, "index": 1, "total": 1})
            report("search", {"message": f"Obteniendo páginas del capítulo desde {adapter.name}…"})

        try:
            page_urls = await adapter.get_pages(chapter_url, external_id=None)
        except Exception as e:
            if report:
                report("error", {"message": str(e), "context": "get_pages", "title": title})
            db.rollback()
            return None

        if not page_urls:
            if report:
                report("skip", {
                    "title": title,
                    "reason": "no images",
                    "message": "No se encontraron imágenes en esta URL.",
                })
            db.rollback()
            return None

        if report:
            report("search", {"message": f"Encontradas {len(page_urls)} imágenes. Descargando capítulo 1…"})
            report("chapter", {"chapter": 1, "total": 1, "title": "Capítulo 1", "manga": title})

        chapter = Chapter(
            manga_id=manga.id,
            number=1,
            title="Capítulo 1",
            page_count=len(page_urls),
            source_url=chapter_url,
            path=f"{slug}/ch-1",
        )
        db.add(chapter)
        db.flush()

        filter_cfg = getattr(self.config.scraper, "image_filter", None)
        filter_dict = filter_cfg.model_dump() if filter_cfg and hasattr(filter_cfg, "model_dump") else (filter_cfg.dict() if filter_cfg and hasattr(filter_cfg, "dict") else None)
        ollama_host = getattr(getattr(self.config, "analyzer", None), "ollama_host", "http://localhost:11434")
        pages_data = await download_chapter_pages(
            manga,
            chapter,
            [{"number": p.number, "url": p.url, "filename": getattr(p, "filename", None)} for p in page_urls],
            self.download_path,
            delay=self.config.scraper.delay_between_requests / 2,
            progress_callback=report,
            image_filter_config=filter_dict,
            ollama_host=ollama_host,
        )

        for p_data in pages_data:
            db.add(
                Page(
                    chapter_id=chapter.id,
                    number=p_data["number"],
                    image_path=p_data["image_path"],
                    width=p_data.get("width"),
                    height=p_data.get("height"),
                )
            )
        chapter.page_count = len(pages_data)
        chapter.downloaded_at = datetime.now(timezone.utc)
        manga.total_chapters = 1
        manga.status = "ready"
        db.commit()
        return manga

    async def update_manga_chapters(
        self,
        manga: Manga,
        db,
        progress_callback: ProgressCallback | None = None,
        max_new_chapters: int = 10,
    ) -> int:
        """
        Fetch new chapters from source that are not yet in DB and download them.
        Returns the number of new chapters added.
        """
        def report(phase: str, detail: dict) -> None:
            if progress_callback:
                progress_callback(phase, detail)

        if not manga.source_site or not manga.source_url:
            return 0

        adapter = self._get_adapter_by_name(manga.source_site)
        if not adapter:
            report("error", {"message": f"No adapter for {manga.source_site}", "context": "update_chapters"})
            return 0

        external_id = None
        if manga.source_site == "mangadex" and manga.source_url:
            url_without_query = manga.source_url.split("?")[0].rstrip("/")
            parts = url_without_query.split("/")
            if parts:
                external_id = parts[-1]

        existing_numbers = {c.number for c in manga.chapters}
        use_language = self.config.scraper.languages[0] if self.config.scraper.languages else None
        only_preferred = getattr(self.config.scraper, "only_preferred_language", False)

        try:
            chapters_info = await adapter.get_chapters(
                manga.source_url,
                language=use_language,
                external_id=external_id,
            )
            if not chapters_info and use_language and len(existing_numbers) == 0 and not only_preferred:
                chapters_info = await adapter.get_chapters(
                    manga.source_url,
                    language=None,
                    external_id=external_id,
                )
        except Exception as e:
            report("error", {"message": str(e), "context": "get_chapters"})
            return 0

        new_chapters = [c for c in chapters_info if c.number not in existing_numbers]
        new_chapters.sort(key=lambda c: c.number)
        existing_max = max(existing_numbers) if existing_numbers else 0
        next_chapters = [c for c in new_chapters if c.number > existing_max]
        to_download = next_chapters[:max_new_chapters]
        added = 0

        for ch_info in to_download:
            if report:
                report("chapter", {"chapter": ch_info.number, "total": len(to_download), "title": manga.title})
            try:
                page_urls = await adapter.get_pages(ch_info.url, external_id=ch_info.external_id)
                if not page_urls:
                    continue

                chapter = Chapter(
                    manga_id=manga.id,
                    number=ch_info.number,
                    title=ch_info.title,
                    page_count=len(page_urls),
                    source_url=ch_info.url,
                    path=f"{manga.slug}/ch-{ch_info.number:g}",
                )
                db.add(chapter)
                db.flush()

                filter_cfg = getattr(self.config.scraper, "image_filter", None)
                filter_dict = filter_cfg.model_dump() if filter_cfg and hasattr(filter_cfg, "model_dump") else (filter_cfg.dict() if filter_cfg and hasattr(filter_cfg, "dict") else None)
                ollama_host = getattr(getattr(self.config, "analyzer", None), "ollama_host", "http://localhost:11434")
                pages_data = await download_chapter_pages(
                    manga,
                    chapter,
                    [{"number": p.number, "url": p.url, "filename": p.filename} for p in page_urls],
                    self.download_path,
                    delay=self.config.scraper.delay_between_requests / 2,
                    progress_callback=report,
                    image_filter_config=filter_dict,
                    ollama_host=ollama_host,
                )

                for p_data in pages_data:
                    db.add(
                        Page(
                            chapter_id=chapter.id,
                            number=p_data["number"],
                            image_path=p_data["image_path"],
                            width=p_data.get("width"),
                            height=p_data.get("height"),
                        )
                    )

                chapter.page_count = len(pages_data)
                chapter.downloaded_at = datetime.now(timezone.utc)
                added += 1
                await asyncio.sleep(self.config.scraper.delay_between_requests)
            except Exception as e:
                if report:
                    report("error", {"message": str(e), "context": f"chapter {ch_info.number}"})

        manga.total_chapters = len(db.query(Chapter).filter(Chapter.manga_id == manga.id).all())
        db.commit()
        return added


def _titles_similar(a: str, b: str) -> bool:
    """Compara dos títulos ignorando mayúsculas y caracteres especiales."""
    def normalize(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    import re
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    # Similar si uno contiene al otro o si comparten 80%+ de caracteres
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return shorter in longer or (len(shorter) / len(longer)) >= 0.8
