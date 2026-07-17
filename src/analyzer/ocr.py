"""OCR module — extracts text from manga page images using EasyOCR."""

from pathlib import Path

import easyocr
from PIL import Image


class OCREngine:
    """Wrapper around EasyOCR for manga text extraction."""

    def __init__(self, languages: list[str] | None = None):
        self._languages = languages or ["es", "en"]
        self._reader: easyocr.Reader | None = None

    @property
    def reader(self) -> easyocr.Reader:
        """Lazy-load the EasyOCR reader (heavy on first init)."""
        if self._reader is None:
            self._reader = easyocr.Reader(
                self._languages,
                gpu=False,  # CPU mode for portability
                verbose=False,
            )
        return self._reader

    def extract_text(self, image_path: str | Path) -> str:
        """
        Extract all text from a single manga page image.

        Returns concatenated text from all detected text regions.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return ""

        try:
            # EasyOCR returns list of (bbox, text, confidence)
            results = self.reader.readtext(str(image_path), detail=1, paragraph=True)

            # Filter by confidence and join text
            texts: list[str] = []
            for result in results:
                if len(result) >= 3:
                    _bbox, text, confidence = result[0], result[1], result[2]
                    if confidence > 0.3 and len(text.strip()) > 1:
                        texts.append(text.strip())
                elif len(result) >= 2:
                    texts.append(str(result[1]).strip())

            return " ".join(texts)
        except Exception:
            return ""

    def extract_text_batch(
        self, image_paths: list[str | Path], min_text_length: int = 10
    ) -> list[dict]:
        """
        Extract text from multiple images.

        Returns list of dicts: { 'path': str, 'text': str, 'has_text': bool }
        """
        results: list[dict] = []
        for path in image_paths:
            text = self.extract_text(path)
            results.append(
                {
                    "path": str(path),
                    "text": text,
                    "has_text": len(text) >= min_text_length,
                }
            )
        return results
