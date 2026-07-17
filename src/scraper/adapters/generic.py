"""Generic adapter — uses Playwright to scrape unknown manga sites found via search."""

import re
import logging
from urllib.parse import urljoin

from .base import BaseAdapter, ChapterInfo, MangaResult, PageUrl
from .image_detection import (
    JS_DOM_IMAGE_STATS,
    JS_EXTRACT_DOM_URLS_EXTENDED,
    JS_EXTRACT_DOM_URLS_WITH_DIMENSIONS,
    JS_EXTRACT_PANEL_IMAGES,
    JS_GET_SCROLL_STATE,
    log_dom_image_stats,
)

logger = logging.getLogger(__name__)

IMG_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")

SKIP_KEYWORDS = (
    "avatar", "logo", "icon", "banner", "favicon", "sprite",
    "pixel", "analytics", "tracking", "advertisement", "ads",
    "placeholder", "loading", "spinner", "thumbnail",
    "background", "bg-", "pattern", "noise",
    "google", "facebook", "twitter", "disqus",
    "gravatar", "captcha", ".svg",
    "radio", "audio", "player", "podcast",
    "social", "share", "whatsapp", "telegram", "discord",
    "footer", "header", "sidebar", "widget", "comment",
    "emoji", "sticker", "badge", "reward", "coin",
)

# JS para interceptar IntersectionObserver y forzar que todos los elementos
# observados se reporten como visibles inmediatamente.
# Debe inyectarse ANTES de que la página cargue su propio JS.
_JS_OVERRIDE_INTERSECTION_OBSERVER = """
() => {
    if (window.__ioOverridden) return;
    window.__ioOverridden = true;
    const OrigIO = window.IntersectionObserver;
    if (!OrigIO) return;
    window.IntersectionObserver = function(callback, options) {
        const obs = new OrigIO(function(entries, observer) {
            const faked = entries.map(e => {
                if (!e.isIntersecting) {
                    return {
                        target: e.target,
                        isIntersecting: true,
                        intersectionRatio: 1.0,
                        boundingClientRect: e.boundingClientRect,
                        intersectionRect: e.boundingClientRect,
                        rootBounds: e.rootBounds,
                        time: e.time,
                    };
                }
                return e;
            });
            callback(faked, observer);
        }, options);
        const origObserve = obs.observe.bind(obs);
        obs.observe = function(target) {
            origObserve(target);
            // Disparar callback inmediatamente para el elemento observado
            setTimeout(() => {
                const rect = target.getBoundingClientRect();
                callback([{
                    target,
                    isIntersecting: true,
                    intersectionRatio: 1.0,
                    boundingClientRect: rect,
                    intersectionRect: rect,
                    rootBounds: null,
                    time: performance.now(),
                }], obs);
            }, 50);
        };
        return obs;
    };
    window.IntersectionObserver.prototype = OrigIO.prototype;
}
"""

# JS para forzar la carga de todas las imágenes lazy ya presentes en el DOM
_JS_FORCE_LAZY = """
() => {
    // 1. Quitar loading="lazy" nativo del browser
    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
        img.removeAttribute('loading');
        img.loading = 'eager';
    });

    // 2. Mover data-src / data-lazy-src / data-original → src
    const dataSrcAttrs = [
        'data-src', 'data-lazy-src', 'data-original',
        'data-url', 'data-image', 'data-img', 'data-cfsrc'
    ];
    document.querySelectorAll('img').forEach(img => {
        for (const attr of dataSrcAttrs) {
            const val = img.getAttribute(attr);
            if (val && val.startsWith('http')) {
                if (!img.src || img.src.startsWith('data:') || img.src === window.location.href) {
                    img.src = val;
                    break;
                }
            }
        }
    });

    // 3. Disparar IntersectionObserver: desconectar todos los observers activos
    //    para que dejen de bloquear, y forzar carga via scrollIntoView
    document.querySelectorAll('img').forEach(img => {
        if (!img.src || img.src.startsWith('data:') || img.naturalWidth === 0) {
            img.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
    });
}
"""

def _is_manga_page_image(url: str) -> bool:
    """Heurística: ¿parece una imagen de página de manga (no UI)?"""
    if not url or len(url) < 20:
        return False
    ul = url.lower().split("?")[0]
    if any(k in ul for k in SKIP_KEYWORDS):
        return False
    has_img_ext = any(ul.endswith(ext) for ext in IMG_EXTENSIONS)
    is_content_path = any(x in ul for x in (
        "/uploads/", "/chapters/", "/pages/", "/content/",
        "/manga/", "/manhwa/", "/manhua/", "/comic/",
        "/images/", "/img/", "/cdn/", "/storage/", "/media/",
    ))
    return has_img_ext or is_content_path


def _score_url(url: str) -> int:
    ul = url.lower()
    s = 0
    for kw in ("/chapters/", "/pages/", "/uploads/", "/content/", "/manga/", "/comic/"):
        if kw in ul:
            s += 10
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if ul.split("?")[0].endswith(ext):
            s += 5
    return s


class GenericAdapter(BaseAdapter):
    """
    Generic scraper for unknown manga sites.
    Uses Playwright to navigate and extract content.
    This is the fallback when no specific adapter exists.
    """

    name = "generic"
    base_url = ""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    async def search(
        self, genre: str | None = None, keyword: str | None = None, limit: int = 10
    ) -> list[MangaResult]:
        return []

    async def get_chapters(
        self, manga_url: str, language: str | None = None, external_id: str | None = None
    ) -> list[ChapterInfo]:
        """Extract chapter list from a manga page using Playwright."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        chapters: list[ChapterInfo] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(manga_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                links = await page.query_selector_all(
                    "a[href*='chapter'], a[href*='capitulo'], a[href*='cap-'], "
                    "a[href*='/ch-'], a[href*='/c/'], .chapter-list a, "
                    ".chapters a, ul.chapter-list li a"
                )

                seen_numbers: set[float] = set()
                for link in links:
                    href = await link.get_attribute("href") or ""
                    text = (await link.inner_text()).strip()

                    match = re.search(
                        r"(?:chapter|cap[ií]tulo|ch)[.\-_ ]*(\d+(?:\.\d+)?)",
                        href + " " + text,
                        re.IGNORECASE,
                    )
                    if match:
                        num = float(match.group(1))
                        if num not in seen_numbers:
                            seen_numbers.add(num)
                            full_url = urljoin(manga_url, href)
                            chapters.append(
                                ChapterInfo(
                                    number=num,
                                    title=text[:200] if text else None,
                                    url=full_url,
                                    language=language,
                                )
                            )
            except Exception:
                pass
            finally:
                await browser.close()

        chapters.sort(key=lambda c: c.number)
        return chapters

    async def get_pages(
        self, chapter_url: str, external_id: str | None = None
    ) -> list[PageUrl]:
        """
        Extrae URLs de imágenes combinando:
        1. Intercepción de red (request + response)
        2. Forzado de carga lazy via JS (elimina loading=lazy, mueve data-src→src)
        3. Scroll lento con re-aplicación del fix cada 5 pasos
        4. Extracción del DOM post-scroll
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        network_seen: set[str] = set()
        network_urls: list[str] = []

        def add(url: str) -> None:
            if url and url not in network_seen and _is_manga_page_image(url):
                network_seen.add(url)
                network_urls.append(url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # ── Estrategia 1: interceptar red ──────────────────────────────────
            async def capture_route(route):
                req = route.request
                u = req.url
                if req.resource_type == "image":
                    add(u)
                elif any(u.lower().split("?")[0].endswith(ext) for ext in IMG_EXTENSIONS):
                    add(u)
                await route.continue_()

            def on_response(response):
                try:
                    ct = (response.headers.get("content-type") or "").lower()
                    if ct.startswith("image/") and "svg" not in ct:
                        # Usar request URL para capturar la URL real cuando la respuesta es blob:
                        u = getattr(response.request, "url", None) or response.url
                        if u and not u.startswith("blob:"):
                            add(u)
                except Exception:
                    pass

            await page.route("**/*", capture_route)
            page.on("response", on_response)

            try:
                # Inyectar override de IntersectionObserver ANTES de navegar
                await page.add_init_script(_JS_OVERRIDE_INTERSECTION_OBSERVER)

                await page.goto(chapter_url, wait_until="load", timeout=40000)
                await page.wait_for_timeout(2000)

                # Forzar carga lazy en imágenes ya presentes
                await page.evaluate(_JS_FORCE_LAZY)
                await page.wait_for_timeout(1500)

                # ── Detectar contenedor de scroll (reader/viewer) si existe ────
                scroll_selector: str | None = await page.evaluate(
                    """
                    () => {
                        const candidates = ['[class*="reader"]', '[class*="viewer"]', '[class*="chapter-content"]',
                            '[class*="pages"]', 'main', 'article'];
                        for (const sel of candidates) {
                            const el = document.querySelector(sel);
                            if (el && el.scrollHeight > window.innerHeight + 200) {
                                const st = getComputedStyle(el);
                                if (st.overflowY === 'auto' || st.overflowY === 'scroll') return sel;
                            }
                        }
                        return null;
                    }
                    """
                )

                # ── Scroll lento hasta que scrollHeight deje de crecer ─────────
                scroll_step = 350
                max_steps = 300
                stall_limit = 8
                prev_scroll_height = -1
                stall_cycles = 0

                for step in range(max_steps):
                    if scroll_selector:
                        await page.evaluate(
                            f"(s) => {{ const el = document.querySelector(s); if (el) el.scrollBy(0, {scroll_step}); }}",
                            scroll_selector,
                        )
                    else:
                        await page.evaluate(f"window.scrollBy(0, {scroll_step})")

                    # Re-aplicar force lazy cada 3 pasos
                    if step % 3 == 0:
                        await page.evaluate(_JS_FORCE_LAZY)

                    # Esperar a que las imágenes lazy se disparen y carguen
                    await page.wait_for_timeout(400)

                    # Si llegamos al fondo, dar más tiempo para carga de contenido dinámico
                    state = await page.evaluate(JS_GET_SCROLL_STATE, scroll_selector)
                    new_height = state.get("scrollHeight") or 0
                    at_bottom = (
                        state.get("scrollTop", 0) + state.get("clientHeight", 0)
                        >= new_height - 80
                    )
                    if at_bottom:
                        await page.wait_for_timeout(800)
                        state = await page.evaluate(JS_GET_SCROLL_STATE, scroll_selector)
                        new_height = state.get("scrollHeight") or 0

                    if new_height == prev_scroll_height:
                        stall_cycles += 1
                        if stall_cycles >= stall_limit:
                            break
                    else:
                        stall_cycles = 0
                    prev_scroll_height = new_height

                # Esperar a que la red se calme después del scroll completo
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await page.wait_for_timeout(1000)

                # ── Volver al inicio: la SPA puede descargar imágenes del top ─
                if scroll_selector:
                    await page.evaluate(
                        "(s) => { const el = document.querySelector(s); if (el) el.scrollTo(0, 0); }",
                        scroll_selector,
                    )
                else:
                    await page.evaluate("window.scrollTo(0, 0)")
                await page.evaluate(_JS_FORCE_LAZY)
                await page.wait_for_timeout(3000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                # ── Logging diagnóstico ────────────────────────────────────────
                dom_stats = await page.evaluate(JS_DOM_IMAGE_STATS)
                log_dom_image_stats(dom_stats, len(network_urls))

                # ── Extracción prioritaria: imágenes de panel (clase/tamaño) ──
                panel_urls: list[str] = []
                try:
                    panel_urls = await page.evaluate(
                        JS_EXTRACT_PANEL_IMAGES,
                        {"panelClasses": ["w-full", "img-fluid", "page-img", "chapter-img", "manga-page"],
                         "minWidthRatio": 0.4},
                    )
                    logger.info("panel images (class/size filter): %d", len(panel_urls))
                except Exception:
                    pass

                # ── Fallback: extracción DOM ampliada ─────────────────────────
                dom_urls: list[str] = await page.evaluate(JS_EXTRACT_DOM_URLS_EXTENDED)
                for url in dom_urls:
                    add(url)

                try:
                    with_dims = await page.evaluate(
                        JS_EXTRACT_DOM_URLS_WITH_DIMENSIONS,
                        {"minWidth": 100, "minHeight": 150, "minAspectRatio": 0.3},
                    )
                    for item in with_dims:
                        u = item.get("url")
                        if u:
                            add(u)
                except Exception:
                    pass

            except Exception as e:
                logger.warning("get_pages error: %s", e, exc_info=True)
            finally:
                await browser.close()

        # ── Filtrado: preferir imágenes de panel si hay suficientes ───────────
        panel_set = {u for u in panel_urls if _is_manga_page_image(u)}
        if len(panel_set) >= 5:
            all_urls = [u for u in panel_urls if u in panel_set]
            logger.info("Using %d panel-class images (filtered from %d network)", len(all_urls), len(network_seen))
        else:
            all_urls = list(network_seen)
            if not all_urls:
                return []
            high = [u for u in all_urls if _score_url(u) >= 5]
            if len(high) >= 5:
                all_urls = high

        if not all_urls:
            return []

        # Deduplicar preservando orden
        deduped: list[str] = []
        deduped_set: set[str] = set()
        for u in all_urls:
            if u not in deduped_set:
                deduped_set.add(u)
                deduped.append(u)
        all_urls = deduped

        def page_num(url: str) -> int:
            base = url.split("?")[0].split("/")[-1]
            nums = re.findall(r"\d+", base)
            return int(nums[-1]) if nums else 0

        try:
            dirs = {"/".join(u.split("/")[:-1]) for u in all_urls}
            if len(dirs) <= 3:
                all_urls.sort(key=page_num)
        except Exception:
            pass

        return [PageUrl(number=i + 1, url=url) for i, url in enumerate(all_urls)]