"""Analysis pipeline — orchestrates OCR, chunking, sampling, and LLM analysis."""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import AppConfig
from src.db.models import AnalysisLog, Chapter, Manga, Page

from .chunker import chunk_text, estimate_tokens, smart_sample
from .llm import OllamaClient
from .ocr import OCREngine


class AnalysisPipeline:
    """
    Full analysis pipeline for a manga:

    1. Extract text from page images via OCR
    2. Split text into chunks
    3. Smart-sample chunks to fit LLM token budget
    4. Send to LLM for language detection, tagging, synopsis
    5. Accept or discard based on language
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.ocr = OCREngine(languages=config.analyzer.ocr_languages)
        self.llm = OllamaClient(
            host=config.analyzer.ollama_host,
            model=config.analyzer.ollama_model,
        )
        self.download_path = Path(config.scraper.download_path)
        self.max_tokens = config.analyzer.max_tokens
        self.min_text_length = config.analyzer.min_text_length
        self.sample_strategy = config.analyzer.sample_strategy

    async def analyze_manga(self, manga: Manga, db) -> dict:
        """
        Run the full analysis pipeline on a manga.

        Returns dict with analysis results.
        """
        manga.status = "analyzing"
        db.commit()

        # Step 1: Collect all page images
        chapters = (
            db.query(Chapter)
            .filter(Chapter.manga_id == manga.id)
            .order_by(Chapter.number)
            .all()
        )

        all_pages: list[Page] = []
        for chapter in chapters:
            pages = (
                db.query(Page)
                .filter(Page.chapter_id == chapter.id)
                .order_by(Page.number)
                .all()
            )
            all_pages.extend(pages)

        if not all_pages:
            manga.status = "discarded"
            db.commit()
            return {"accepted": False, "reason": "no pages found"}

        # Step 2: OCR — extract text from all pages
        print(f"  [OCR] Processing {len(all_pages)} pages...")
        full_text = self._extract_all_text(all_pages, db)

        if len(full_text) < self.min_text_length:
            # Very little text — might be a raw/untranslated manga
            # Still try to analyze what we have
            print(f"  [OCR] Very little text found ({len(full_text)} chars)")

        # Step 3: Chunk the text
        total_tokens = estimate_tokens(full_text)
        num_chunks = max(1, total_tokens // 500)  # ~500 tokens per chunk
        chunks = chunk_text(full_text, num_chunks)
        print(f"  [Chunk] {total_tokens} tokens -> {len(chunks)} chunks")

        # Step 4: Smart sample to fit token budget
        sampled = smart_sample(chunks, self.max_tokens, self.sample_strategy)
        sampled_text = "\n\n---\n\n".join(sampled)
        sampled_tokens = estimate_tokens(sampled_text)
        print(f"  [Sample] Selected {len(sampled)}/{len(chunks)} chunks ({sampled_tokens} tokens)")

        # Step 5: LLM analysis
        print(f"  [LLM] Analyzing with {self.config.analyzer.ollama_model}...")
        llm_available = await self.llm.health_check()

        if llm_available and sampled_text:
            result = await self.llm.analyze_manga_text(sampled_text, manga.title)
        else:
            # Fallback: basic heuristic language detection
            result = self._heuristic_analysis(full_text)
            result["error"] = "LLM unavailable" if not llm_available else "No text to analyze"

        # Step 6: Decide accept/discard
        detected_lang = result.get("language", "other")
        accepted = detected_lang in self.config.scraper.languages

        # Save analysis log
        log = AnalysisLog(
            manga_id=manga.id,
            model_used=self.config.analyzer.ollama_model if llm_available else "heuristic",
            tokens_used=sampled_tokens,
            raw_response=result.get("raw", ""),
            language_detected=detected_lang,
            tags_detected=json.dumps(result.get("tags", [])),
            accepted=accepted,
        )
        db.add(log)

        # Update manga record
        if accepted:
            manga.status = "ready"
            manga.language = detected_lang
            manga.synopsis = result.get("synopsis") or manga.synopsis
            manga.content_rating = result.get("content_rating")

            # Update tags
            from src.db.models import MangaTag

            existing_tags = {t.tag for t in manga.tags}
            for tag in result.get("tags", []):
                if tag and tag not in existing_tags:
                    db.add(MangaTag(manga_id=manga.id, tag=tag))
        else:
            manga.status = "discarded"

        db.commit()

        return {
            "accepted": accepted,
            "language": detected_lang,
            "tags": result.get("tags", []),
            "synopsis": result.get("synopsis", ""),
            "content_rating": result.get("content_rating", "safe"),
            "tokens_used": sampled_tokens,
            "pages_analyzed": len(all_pages),
            "chunks_total": len(chunks),
            "chunks_sampled": len(sampled),
        }

    def _extract_all_text(self, pages: list[Page], db) -> str:
        """Extract OCR text from all pages, caching results."""
        texts: list[str] = []

        for page in pages:
            # Use cached OCR if available
            if page.ocr_text:
                texts.append(page.ocr_text)
                continue

            # Run OCR
            full_path = self.download_path / page.image_path
            text = self.ocr.extract_text(full_path)

            # Cache the result
            page.ocr_text = text
            texts.append(text)

        db.commit()
        return " ".join(t for t in texts if t)

    def _heuristic_analysis(self, text: str) -> dict:
        """Basic language detection without LLM."""
        text_lower = text.lower()

        # Spanish indicators
        es_words = ["que", "los", "las", "del", "por", "una", "con", "para", "como", "pero", "más", "está"]
        # English indicators
        en_words = ["the", "and", "you", "that", "was", "for", "are", "with", "his", "they", "from"]

        es_score = sum(1 for w in es_words if f" {w} " in f" {text_lower} ")
        en_score = sum(1 for w in en_words if f" {w} " in f" {text_lower} ")

        if es_score > en_score and es_score >= 3:
            language = "es"
        elif en_score > es_score and en_score >= 3:
            language = "en"
        else:
            language = "other"

        return {
            "language": language,
            "tags": [],
            "synopsis": "",
            "content_rating": "safe",
            "raw": f"heuristic: es={es_score}, en={en_score}",
        }
