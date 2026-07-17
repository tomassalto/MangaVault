"""LLM client for manga analysis using Ollama."""

import json
import re

import httpx


class OllamaClient:
    """Client for Ollama REST API to analyze manga content."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "mistral"):
        self.host = host.rstrip("/")
        self.model = model

    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def analyze_manga_text(
        self, sampled_text: str, title: str = ""
    ) -> dict:
        """
        Send sampled OCR text to the LLM for analysis.

        Returns:
            {
                "language": "es" | "en" | "other",
                "tags": ["ecchi", "romance", ...],
                "synopsis": "Brief description...",
                "content_rating": "safe" | "suggestive" | "explicit"
            }
        """
        prompt = f"""You are a manga/manhwa/manhua content analyzer. Analyze the following text extracted via OCR from a comic/manga.

Title: {title or 'Unknown'}

Extracted text (sampled from multiple pages):
---
{sampled_text}
---

Based on the text above, provide a JSON analysis with these exact fields:
1. "language": The primary language of the text. Use "es" for Spanish, "en" for English, "other" for anything else.
2. "tags": An array of genre/content tags (lowercase). Common tags: action, adventure, comedy, drama, ecchi, fantasy, harem, horror, isekai, martial arts, mystery, romance, sci-fi, slice of life, supernatural, thriller.
3. "synopsis": A brief synopsis of the story (2-3 sentences) based on what you can infer from the text. Write it in the same language as the manga.
4. "content_rating": One of "safe", "suggestive", or "explicit" based on the content.

IMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, just the JSON object.

Example response:
{{"language": "es", "tags": ["romance", "comedy", "ecchi"], "synopsis": "Una historia sobre...", "content_rating": "suggestive"}}
"""

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 1000,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw_response = data.get("response", "")

                return self._parse_response(raw_response)

        except Exception as e:
            return {
                "language": "other",
                "tags": [],
                "synopsis": "",
                "content_rating": "safe",
                "error": str(e),
                "raw": "",
            }

    def _parse_response(self, raw: str) -> dict:
        """Parse the LLM response, extracting JSON from potentially messy output."""
        # Try to extract JSON from the response
        # The LLM might wrap it in markdown code blocks
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Validate required fields
                result = {
                    "language": parsed.get("language", "other"),
                    "tags": parsed.get("tags", []),
                    "synopsis": parsed.get("synopsis", ""),
                    "content_rating": parsed.get("content_rating", "safe"),
                    "raw": raw,
                }

                # Normalize language
                lang = result["language"].lower().strip()
                if lang in ("es", "español", "spanish", "es-la"):
                    result["language"] = "es"
                elif lang in ("en", "english", "inglés", "ingles"):
                    result["language"] = "en"
                elif lang not in ("es", "en"):
                    result["language"] = "other"

                # Normalize tags to lowercase
                result["tags"] = [t.lower().strip() for t in result["tags"] if isinstance(t, str)]

                return result
            except json.JSONDecodeError:
                pass

        # Fallback: try to detect language from text
        return {
            "language": "other",
            "tags": [],
            "synopsis": "",
            "content_rating": "safe",
            "raw": raw,
            "error": "Failed to parse LLM response as JSON",
        }

    async def generate_synopsis(self, text: str, title: str, language: str) -> str:
        """Generate a synopsis given text in a specific language."""
        lang_name = "Spanish" if language == "es" else "English"
        prompt = f"""Write a brief, engaging synopsis (3-4 sentences) for this manga/comic in {lang_name}.

Title: {title}
Text from the manga:
{text[:3000]}

Write ONLY the synopsis, nothing else. Write it in {lang_name}."""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.7, "num_predict": 500},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except Exception:
            return ""
