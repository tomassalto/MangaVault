"""
Utilidades compartidas para detección de imágenes lazy en lectores de manga.
Usado por GenericAdapter y ManhwaWebAdapter.
"""

import logging

logger = logging.getLogger(__name__)

# ─── Scroll: cortar por document height, no por conteo de imágenes ───────────

# Obtener scrollHeight del documento o del contenedor de scroll
_JS_GET_SCROLL_STATE = """
(selector) => {
    const el = selector ? document.querySelector(selector) : null;
    if (el) {
        return { scrollHeight: el.scrollHeight, scrollTop: el.scrollTop, clientHeight: el.clientHeight };
    }
    return {
        scrollHeight: document.body.scrollHeight,
        scrollTop: window.scrollY,
        clientHeight: window.innerHeight
    };
}
"""

# Contar nodos img en DOM (para esperar "nuevo contenido")
_JS_IMG_COUNTS = """
() => {
    const imgs = document.querySelectorAll('img');
    let withSrc = 0, withDataSrc = 0, naturalWidthPositive = 0;
    imgs.forEach(img => {
        if (img.src && !img.src.startsWith('data:') && img.src !== window.location.href) withSrc++;
        if (img.getAttribute('data-src') || img.getAttribute('data-original') || img.getAttribute('data-lazy-src')) withDataSrc++;
        if (img.naturalWidth > 0) naturalWidthPositive++;
    });
    return {
        total: imgs.length,
        withSrc,
        withDataSrc,
        naturalWidthPositive
    };
}
"""

# Estadísticas para logging diagnóstico
_JS_DOM_IMAGE_STATS = """
() => {
    const imgs = document.querySelectorAll('img');
    let withSrc = 0, withDataSrc = 0, naturalWidthPositive = 0;
    const dataSrcAttrs = ['data-src', 'data-original', 'data-lazy-src', 'data-lazy'];
    imgs.forEach(img => {
        if (img.src && !img.src.startsWith('data:') && img.src !== window.location.href) withSrc++;
        const hasData = dataSrcAttrs.some(a => img.getAttribute(a));
        if (hasData) withDataSrc++;
        if (img.naturalWidth > 0) naturalWidthPositive++;
    });
    const body = document.body;
    const docEl = document.documentElement;
    const scrollHeight = Math.max(body.scrollHeight, body.offsetHeight, docEl.clientHeight, docEl.scrollHeight, docEl.offsetHeight);
    return {
        imgTotal: imgs.length,
        imgWithSrc: withSrc,
        imgWithDataSrc: withDataSrc,
        imgNaturalWidthPositive: naturalWidthPositive,
        scrollHeight
    };
}
"""

# Extracción ampliada: currentSrc, img.src (propiedad), <picture><source>, más attrs
_JS_EXTRACT_DOM_URLS_EXTENDED = r"""
() => {
    const attrs = [
        'src', 'data-src', 'data-lazy-src', 'data-original', 'data-lazy',
        'data-url', 'data-image', 'data-img', 'data-cfsrc',
        'data-srcset', 'srcset',
    ];
    const urls = new Set();

    function addUrl(u) {
        if (!u || u.startsWith('data:') || u === window.location.href) return;
        if (u.startsWith('http')) urls.add(u);
    }

    function parseSrcset(val) {
        if (!val) return;
        val.split(',').forEach(part => {
            const u = part.trim().split(/\s+/)[0];
            if (u && u.startsWith('http')) urls.add(u);
        });
    }

    // 1. Todas las <img>: atributos + currentSrc (propiedad real del navegador) y .src
    document.querySelectorAll('img').forEach(img => {
        addUrl(img.currentSrc || img.src);
        for (const attr of attrs) {
            const val = img.getAttribute(attr);
            if (!val) continue;
            if (attr === 'srcset' || attr === 'data-srcset') {
                parseSrcset(val);
            } else if (val.startsWith('http')) {
                urls.add(val);
            }
        }
    });

    // 2. <picture><source srcset>
    document.querySelectorAll('picture source[srcset], picture source[data-srcset]').forEach(el => {
        const val = el.getAttribute('srcset') || el.getAttribute('data-srcset');
        parseSrcset(val);
    });

    // 3. Elementos con data-src / data-original (divs, etc.)
    document.querySelectorAll('[data-src], [data-original], [data-lazy-src], [data-lazy]').forEach(el => {
        for (const attr of ['data-src', 'data-original', 'data-lazy-src', 'data-lazy']) {
            const val = el.getAttribute(attr);
            if (val && val.startsWith('http')) urls.add(val);
        }
    });

    return Array.from(urls);
}
"""

# Extraer URLs de imágenes que parecen "página" (tamaño mínimo y aspect ratio)
# Devuelve { url, naturalWidth, naturalHeight }. Recibe opts: { minWidth, minHeight, minAspectRatio }
_JS_EXTRACT_DOM_URLS_WITH_DIMENSIONS = """
(opts) => {
    const minWidth = (opts && opts.minWidth) || 100;
    const minHeight = (opts && opts.minHeight) || 150;
    const minAspectRatio = (opts && opts.minAspectRatio) != null ? opts.minAspectRatio : 0.3;

    const result = [];
    document.querySelectorAll('img').forEach(img => {
        const url = img.currentSrc || img.src;
        if (!url || url.startsWith('data:') || url === window.location.href) return;
        if (!url.startsWith('http')) return;

        const w = img.naturalWidth || 0;
        const h = img.naturalHeight || 0;
        if (w < minWidth || h < minHeight) return;
        const aspect = w > 0 ? h / w : 0;
        if (aspect < minAspectRatio) return;
        result.push({ url, naturalWidth: w, naturalHeight: h });
    });
    return result;
}
"""


def log_dom_image_stats(stats: dict, network_image_count: int) -> None:
    """Registro mínimo para diagnosticar por qué hay pocas imágenes."""
    logger.info(
        "image_detection stats: img_total=%s img_with_src=%s img_with_data_src=%s "
        "img_naturalWidth>0=%s network_image_requests=%s scrollHeight=%s",
        stats.get("imgTotal", 0),
        stats.get("imgWithSrc", 0),
        stats.get("imgWithDataSrc", 0),
        stats.get("imgNaturalWidthPositive", 0),
        network_image_count,
        stats.get("scrollHeight", 0),
    )
    if stats.get("imgTotal", 0) > 0 and stats.get("imgNaturalWidthPositive", 0) < stats.get("imgTotal", 0) // 2:
        logger.info(
            "image_detection: muchas img en DOM pero pocas con naturalWidth>0 → contenido lazy no cargado o placeholders"
        )
    if stats.get("imgTotal", 0) > (stats.get("imgWithSrc", 0) + stats.get("imgWithDataSrc", 0)):
        logger.info("image_detection: hay img sin src ni data-src → revisar otros atributos o background-image")


# Extraer imágenes de panel de manga usando señales fuertes del DOM:
# 1. Grupo por alt: si muchas img comparten el mismo alt, son paneles
# 2. Clase indicativa (w-full, img-fluid, etc.)
# 3. Tamaño grande (ocupa buena parte del viewport)
# Devuelve lista de URLs ordenadas por posición en el DOM.
# Recibe opts: { panelClasses, minWidthRatio }
_JS_EXTRACT_PANEL_IMAGES = """
(opts) => {
    const panelClasses = (opts && opts.panelClasses) || ['w-full', 'img-fluid', 'page-img', 'chapter-img', 'manga-page'];
    const minWidthRatio = (opts && opts.minWidthRatio) || 0.4;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;

    const skipLower = ['avatar', 'logo', 'icon', 'banner', 'favicon', 'sprite',
        'thumbnail', 'profile', 'advertisement', 'captcha', 'radio', 'social',
        'footer', 'header', 'sidebar', 'nav', 'menu', 'button'];

    function isSkip(url) {
        const ul = url.toLowerCase();
        return skipLower.some(k => ul.includes(k));
    }

    function getUrl(img) {
        const url = img.currentSrc || img.src;
        if (!url || url.startsWith('data:') || url === window.location.href || !url.startsWith('http')) return null;
        if (isSkip(url)) return null;
        return url;
    }

    // Estrategia 1: agrupar por alt — si N imgs comparten el mismo alt no vacío, son paneles
    const altGroups = {};
    document.querySelectorAll('img[alt]').forEach(img => {
        const alt = (img.getAttribute('alt') || '').trim();
        if (alt.length < 2) return;
        const url = getUrl(img);
        if (!url) return;
        if (!altGroups[alt]) altGroups[alt] = [];
        altGroups[alt].push(url);
    });

    // Encontrar el alt más frecuente con >= 3 imágenes
    let bestAlt = null, bestCount = 0;
    for (const [alt, urls] of Object.entries(altGroups)) {
        if (urls.length > bestCount) {
            bestCount = urls.length;
            bestAlt = alt;
        }
    }

    if (bestAlt && bestCount >= 3) {
        return altGroups[bestAlt];
    }

    // Estrategia 2: clase + tamaño (fallback)
    const urls = [];
    document.querySelectorAll('img').forEach(img => {
        const url = getUrl(img);
        if (!url) return;

        const classes = (img.className || '').toLowerCase();
        const hasClass = panelClasses.some(c => classes.includes(c.toLowerCase()));

        const w = img.naturalWidth || img.width || 0;
        const h = img.naturalHeight || img.height || 0;
        const isLarge = w >= viewportWidth * minWidthRatio && h > 200;

        if (hasClass || isLarge) {
            urls.push(url);
        }
    });
    return urls;
}
"""


# Exportar para uso en adapters
JS_GET_SCROLL_STATE = _JS_GET_SCROLL_STATE
JS_IMG_COUNTS = _JS_IMG_COUNTS
JS_DOM_IMAGE_STATS = _JS_DOM_IMAGE_STATS
JS_EXTRACT_DOM_URLS_EXTENDED = _JS_EXTRACT_DOM_URLS_EXTENDED
JS_EXTRACT_DOM_URLS_WITH_DIMENSIONS = _JS_EXTRACT_DOM_URLS_WITH_DIMENSIONS
JS_EXTRACT_PANEL_IMAGES = _JS_EXTRACT_PANEL_IMAGES
