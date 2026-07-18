import axios from "axios";

const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL || "/api");

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: "application/json" },
});

// Types
export interface MangaTag {
  tag: string;
}

export interface Manga {
  id: number;
  title: string;
  slug: string;
  synopsis: string | null;
  language: string | null;
  source_url: string | null;
  source_site: string | null;
  cover_path: string | null;
  status: string;
  content_rating: string | null;
  total_chapters: number;
  tags: MangaTag[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MangaDetail extends Manga {
  chapters: Chapter[];
}

export interface Chapter {
  id: number;
  number: number;
  title: string | null;
  page_count: number;
  path: string | null;
  downloaded_at: string | null;
}

export interface Page {
  id: number;
  number: number;
  image_path: string;
  width: number | null;
  height: number | null;
}

export interface MangaListResponse {
  items: Manga[];
  total: number;
  page: number;
  per_page: number;
}

export interface ScraperStatus {
  running: boolean;
  last_run: string | null;
  total_mangas: number;
  ready: number;
  downloading: number;
  analyzing: number;
  discarded: number;
}

export interface ScraperLogEntry {
  time: string;
  phase: string;
  message: string;
  detail?: Record<string, unknown>;
}

export interface ScraperProgress {
  phase: string;
  message: string;
  current_manga: string;
  manga_index: number;
  manga_total: number;
  chapter_index: number;
  chapter_total: number;
  page_index: number;
  page_total: number;
  processed_count: number;
  errors: string[];
  logs: ScraperLogEntry[];
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface DemoManifestItem {
  title: string;
  slug: string;
  language: string;
  tags: string[];
  synopsis: string;
  imported: boolean;
}

export interface DemoImportResponse {
  created: boolean;
  title: string;
  slug: string;
  message: string;
}

// API calls
export const getMangaList = (params?: {
  page?: number;
  per_page?: number;
  status?: string;
  language?: string;
  tag?: string;
  search?: string;
}) => api.get<MangaListResponse>("/manga", { params }).then((r) => r.data);

export const getManga = (slug: string) =>
  api.get<MangaDetail>(`/manga/${slug}`).then((r) => r.data);

export const deleteManga = (slug: string) =>
  api.delete(`/manga/${slug}`).then((r) => r.data);

export const getTags = () =>
  api.get<TagCount[]>("/manga/tags").then((r) => r.data);

export const getChapterPages = (slug: string, chapterNum: number) =>
  api.get<Page[]>(`/manga/${slug}/chapters/${chapterNum}/pages`).then((r) => r.data);

export const runScraper = (data: {
  genre?: string;
  limit?: number;
  site?: string;
  query?: string;
  direct_chapter_url?: string;
}) => api.post("/scraper/run", data).then((r) => r.data);

export interface SuggestedManga {
  id: number;
  title: string;
  status: string;
  created_at: string | null;
}

export const getSuggestions = () =>
  api.get<SuggestedManga[]>("/suggestions").then((r) => r.data);

export const addSuggestion = (title: string) =>
  api.post<SuggestedManga>("/suggestions", { title }).then((r) => r.data);

export const deleteSuggestion = (id: number) =>
  api.delete(`/suggestions/${id}`).then((r) => r.data);

export const updateMangaChapters = (slug: string, maxChapters = 5) =>
  api.post<{ ok: boolean; added: number; message: string }>(`/manga/${slug}/update-chapters`, { max_chapters: maxChapters }).then((r) => r.data);

export const getScraperStatus = () =>
  api.get<ScraperStatus>("/scraper/status").then((r) => r.data);

export const getScraperProgress = () =>
  api.get<ScraperProgress>("/scraper/progress").then((r) => r.data);

export const analyzeManga = (slug: string) =>
  api.post("/analyze", { slug }).then((r) => r.data);

export const getDemoManifest = () =>
  api.get<DemoManifestItem[]>("/demo/manifest").then((r) => r.data);

export const importDemoTitle = (query: string) =>
  api.post<DemoImportResponse>("/demo/import", { query }).then((r) => r.data);

export const imageUrl = (path: string) => joinApiPath(`/images/${path}`);

function normalizeApiBaseUrl(url: string) {
  return url.replace(/\/+$/, "") || "/api";
}

function joinApiPath(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}
