"""
Filtrado de imágenes descargadas: descarta placeholders (negro, blanco, gris)
y opcionalmente usa un modelo de visión (Ollama) para confirmar que es contenido de manga.
"""

import base64
import io
import logging
from typing import Any

import httpx
from PIL import Image, ImageStat

logger = logging.getLogger(__name__)

# Umbral por defecto: imágenes con varianza muy baja son casi sólidas (placeholder)
DEFAULT_MIN_VARIANCE = 80.0

# Prompt para modelos de visión en Ollama (LLaVA, Pixtral, etc.)
VISION_PROMPT = (
    "This image is from a manga or comic reader. "
    "Does it show actual page content (panels, art, drawings, text) and NOT a loading placeholder, "
    "solid black/white/gray, spinner, or blank? Answer only YES or NO."
)


def is_likely_content_heuristic(
    image: Image.Image,
    min_variance: float = DEFAULT_MIN_VARIANCE,
) -> bool:
    """
    Heurística rápida: descarta imágenes casi sólidas (negro, blanco, gris).
    Usa la varianza de los píxeles en escala de grises; placeholders tienen varianza ~0.
    """
    try:
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        variance = stat.var[0] if stat.var else 0
        return variance >= min_variance
    except Exception as e:
        logger.warning("image_filter heuristic failed: %s", e)
        return True  # En caso de error, no descartar


async def is_likely_content_ollama(
    image_bytes: bytes,
    base_url: str = "http://localhost:11434",
    model: str = "llava",
    timeout: float = 30.0,
) -> bool:
    """
    Envía la imagen a un modelo de visión en Ollama y pregunta si es contenido real.
    Requiere un modelo con visión (llava, pixtral, bakllava, etc.). Mistral solo texto no sirve.
    """
    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "model": model,
            "prompt": VISION_PROMPT,
            "images": [b64],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json=payload,
            )
            r.raise_for_status()
        data = r.json()
        response_text = (data.get("response") or "").strip().upper()
        first_part = (response_text[:50] or "").strip()
        if not first_part:
            return True
        if first_part.startswith("NO"):
            return False
        return "YES" in first_part or first_part.startswith("Y")
    except Exception as e:
        logger.warning("Ollama vision filter failed: %s", e)
        return True  # Si falla la llamada, no descartar por defecto


def prepare_image_for_ollama(image: Image.Image, max_size: int = 512) -> bytes:
    """Redimensiona la imagen para no enviar demasiados datos a Ollama."""
    if max(image.size) <= max_size:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    ratio = max_size / max(image.size)
    new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
    resized = image.convert("RGB").resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
