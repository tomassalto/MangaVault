<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/Ollama-AI-000000?style=for-the-badge&logo=ollama&logoColor=white" alt="Ollama" />
</p>

# MangaVault - Reader, OCR & Analysis

MangaVault is a local manga/comic library app with a React reader, a FastAPI backend, SQLite persistence, image serving, OCR caching, and optional LLM-assisted metadata analysis.

This public repository is the portfolio/demo build. It keeps the product architecture, reader experience, API, data model, and analysis pipeline, while source-specific ingestion adapters are intentionally omitted.

---

## What It Demonstrates

- A full-stack reader experience built with React, Vite, FastAPI, SQLAlchemy, and SQLite.
- A normalized local library model for titles, chapters, pages, tags, analysis logs, and suggestions.
- A fullscreen chapter reader with page navigation, zoom controls, lazy image loading, and keyboard navigation.
- A local media API that serves stored page images safely from the configured library path.
- An OCR + text-processing pipeline with cached page text, chunking, token-budget sampling, and Ollama-based metadata analysis.
- A public demo mode that generates original sample content without relying on copyrighted assets or third-party scraping code.
- A private-extension architecture where real ingestion adapters can exist locally without being shipped in the public repository.

---

## Public Demo Mode

The public build runs with:

```yaml
scraper:
  public_demo_mode: true
  sites: []
  search:
    engine: disabled
    enabled: false
```

The `seed-demo` command creates a complete local library using generated covers, chapters, pages, tags, synopsis, and cached OCR text:

```bash
python -m src.main seed-demo --reset
```

Generated demo data lives under `data/`, which is ignored by Git.

---

## Architecture

```text
React/Vite frontend
    |
    | /api proxy
    v
FastAPI backend
    |
    | SQLAlchemy
    v
SQLite library database
    |
    | image_path
    v
Local image storage
```

Analysis flow:

```text
Stored page images
    |
    v
OCR extraction
    |
    v
Text chunking + smart sampling
    |
    v
LLM metadata analysis
    |
    v
Language, tags, synopsis, rating, analysis log
```

---

## Quick Start

```bash
cd MangaVault

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python -m src.main init
python -m src.main seed-demo --reset
python -m src.main serve
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

- API: `http://localhost:8000`
- Frontend: `http://localhost:5174`

---

## CLI

```bash
python -m src.main init
python -m src.main seed-demo --reset
python -m src.main analyze --slug "title-slug"
python -m src.main analyze --pending
python -m src.main serve --port 8000
python -m src.main status
```

`python -m src.main scrape` is disabled in the public build. Private adapters can be mounted locally without changing the public repository.

---

## Portfolio Recording Flow

The public frontend includes a cached demo import panel for short project walkthroughs.

Suggested recording:

1. Run `python -m src.main seed-demo --reset`.
2. Start the backend and frontend.
3. Run the cached demo import for a title such as `Atomic Scarlet`.
4. Open the filtered result.
5. Show the detail page, chapter list, reader, zoom, page navigation, and fullscreen controls.

The cached flow is intentionally fast and uses local demo assets. It is meant to demonstrate the workflow without publishing private ingestion adapters.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/manga` | List titles with filters and pagination |
| GET | `/manga/tags` | List tags with counts |
| GET | `/manga/{slug}` | Title detail with chapters |
| DELETE | `/manga/{slug}` | Delete title and files |
| GET | `/manga/{slug}/chapters` | List chapters |
| GET | `/manga/{slug}/chapters/{num}` | Chapter detail with pages |
| GET | `/manga/{slug}/chapters/{num}/pages` | Page list for the reader |
| GET | `/images/{path}` | Serve stored page images |
| POST | `/scraper/run` | Disabled in public demo mode |
| GET | `/scraper/status` | Library and processing stats |
| POST | `/analyze` | Run OCR/LLM analysis for a title |
| GET | `/health` | Health check |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend API | FastAPI, Uvicorn |
| Persistence | SQLAlchemy, SQLite |
| Frontend | React 19, Vite, Tailwind CSS 4 |
| OCR | EasyOCR |
| LLM Analysis | Ollama |
| Image Processing | Pillow, OpenCV |
| CLI | Typer |
| Private Ingestion | Adapter interface; source-specific adapters omitted |

---

## Repository Notes

The following are intentionally ignored:

- generated library data in `data/`
- local SQLite databases
- Node and Python build artifacts
- local private config files
- private source-specific ingestion adapters

This keeps the public repository focused on the application architecture and demo experience.
