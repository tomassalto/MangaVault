"""Configuration loader from config.yaml."""

from pathlib import Path
from typing import Any
import os

import yaml
from pydantic import BaseModel


class SiteConfig(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 1
    base_url: str = ""


class SearchConfig(BaseModel):
    engine: str = "duckduckgo"
    enabled: bool = True
    priority: int = 99
    keywords: list[str] = ["manga", "manhwa", "read online"]


class ImageFilterConfig(BaseModel):
    """Filtro de imágenes: descarta placeholders (negro/blanco/gris) y opcionalmente usa visión (Ollama)."""
    enabled: bool = True
    min_variance: float = 80.0  # imágenes con varianza menor se consideran placeholder
    use_ollama_vision: bool = False  # si True, además pregunta a un modelo con visión (llava, pixtral)
    ollama_vision_model: str = "llava"  # Mistral es solo texto; para visión usar llava, pixtral, etc.


class ScraperConfig(BaseModel):
    public_demo_mode: bool = True
    genres: list[str] = ["ecchi", "romance", "action"]
    languages: list[str] = ["es", "en"]
    only_preferred_language: bool = False
    min_images_per_chapter: int = 50  # si el primer capítulo tiene menos, no descargar y probar otra fuente
    max_concurrent: int = 3
    download_path: str = "./data/manga"
    delay_between_requests: float = 2.0
    sites: list[SiteConfig] = []
    search: SearchConfig = SearchConfig()
    image_filter: ImageFilterConfig = ImageFilterConfig()


class AnalyzerConfig(BaseModel):
    ocr_languages: list[str] = ["es", "en"]
    max_tokens: int = 32768
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    min_text_length: int = 50
    sample_strategy: str = "uniform"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5174"]


class AppConfig(BaseModel):
    scraper: ScraperConfig = ScraperConfig()
    analyzer: AnalyzerConfig = AnalyzerConfig()
    api: ApiConfig = ApiConfig()


_config: AppConfig | None = None


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file."""
    global _config

    if _config is not None and config_path is None:
        return _config

    if config_path is None:
        config_path = os.getenv("MANGAVAULT_CONFIG")

    if config_path is None:
        # Look for config.yaml relative to the project root.
        config_path = Path(__file__).parent.parent / "config.yaml"

    config_path = Path(config_path)

    if config_path.exists():
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        cors_origins = os.getenv("MANGAVAULT_CORS_ORIGINS")
        if cors_origins:
            raw.setdefault("api", {})["cors_origins"] = [
                origin.strip()
                for origin in cors_origins.split(",")
                if origin.strip()
            ]
        _config = AppConfig(**raw)
    else:
        _config = AppConfig()

    return _config


def get_config() -> AppConfig:
    """Get the current config (loads default if not yet loaded)."""
    if _config is None:
        return load_config()
    return _config
