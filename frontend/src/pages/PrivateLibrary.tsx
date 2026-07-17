import { useEffect, useState, useCallback, useRef } from "react";
import { Search, Bot, Loader2, BookOpen, RefreshCw, AlertCircle, CheckCircle2, PlusCircle, Trash2 } from "lucide-react";
import { MangaCard } from "../components/MangaCard";
import { TagFilter } from "../components/TagFilter";
import {
  getMangaList,
  getTags,
  getScraperStatus,
  getScraperProgress,
  runScraper,
  getSuggestions,
  addSuggestion,
  deleteSuggestion,
  type Manga,
  type TagCount,
  type ScraperStatus,
  type ScraperProgress,
  type SuggestedManga,
} from "../api/client";

export function PrivateLibrary() {
  const [mangas, setMangas] = useState<Manga[]>([]);
  const [tags, setTags] = useState<TagCount[]>([]);
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [selectedLang, setSelectedLang] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [scraperRunning, setScraperRunning] = useState(false);
  const [scraperProgress, setScraperProgress] = useState<ScraperProgress | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestedManga[]>([]);
  const [suggestInput, setSuggestInput] = useState("");
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [directChapterUrl, setDirectChapterUrl] = useState("");
  const progressPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [mangaRes, tagsRes, statusRes, suggestionsRes] = await Promise.all([
        getMangaList({
          page,
          per_page: 24,
          tag: selectedTag || undefined,
          language: selectedLang || undefined,
          search: searchQuery || undefined,
        }),
        getTags(),
        getScraperStatus(),
        getSuggestions(),
      ]);
      setMangas(mangaRes.items);
      setTotal(mangaRes.total);
      setTags(tagsRes);
      setStatus(statusRes);
      setScraperRunning(statusRes.running);
      setSuggestions(
        [...suggestionsRes].sort((a, b) =>
          (a.status === "pending" ? 0 : 1) - (b.status === "pending" ? 0 : 1)
        )
      );
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, selectedTag, selectedLang, searchQuery]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRunScraper = async (query?: string) => {
    setScraperRunning(true);
    setScraperProgress(null);
    const url = directChapterUrl.trim() || undefined;
    try {
      if (url) {
        await runScraper({ direct_chapter_url: url });
      } else {
        await runScraper(query ? { query, limit: 1 } : { limit: 5 });
      }
    } catch (e) {
      console.error(e);
      setScraperRunning(false);
      return;
    }
    // Poll status + progress while running
    progressPollRef.current = setInterval(async () => {
      try {
        const [s, p] = await Promise.all([getScraperStatus(), getScraperProgress()]);
        setScraperRunning(s.running);
        setScraperProgress(p);
        if (!s.running) {
          if (progressPollRef.current) {
            clearInterval(progressPollRef.current);
            progressPollRef.current = null;
          }
          fetchData();
        }
      } catch {
        // ignore
      }
    }, 1200);
  };

  const handleAddSuggestion = async () => {
    const title = suggestInput.trim();
    if (!title) return;
    setSuggestError(null);
    try {
      await addSuggestion(title);
      setSuggestInput("");
      const list = await getSuggestions();
      setSuggestions(list);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setSuggestError(err.response?.data?.detail || "Error al agregar");
    }
  };

  const handleDeleteSuggestion = async (id: number) => {
    await deleteSuggestion(id);
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
  };

  useEffect(() => {
    return () => {
      if (progressPollRef.current) clearInterval(progressPollRef.current);
    };
  }, []);

  const totalPages = Math.ceil(total / 24);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Library</h1>
          <p style={{ color: "var(--text-secondary)" }} className="mt-1 text-sm">
            {total} manga{total !== 1 ? "s" : ""} in your collection
            {status && status.downloading > 0 && (
              <span style={{ color: "var(--warning)" }}> · {status.downloading} downloading</span>
            )}
          </p>
        </div>

        <div className="flex flex-col gap-2 items-end min-w-0 max-w-md">
          <input
            type="url"
            placeholder="URL directa de capítulo (avanzado)"
            value={directChapterUrl}
            onChange={(e) => setDirectChapterUrl(e.target.value)}
            className="w-full px-3 py-2 rounded-xl text-sm border bg-transparent"
            style={{ borderColor: "var(--border)", color: "var(--text-primary)" }}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={fetchData}
              className="p-2.5 rounded-xl transition-colors border"
              style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
              title="Refrescar"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleRunScraper()}
              disabled={scraperRunning}
              className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 text-white transition-colors disabled:opacity-50"
              style={{ backgroundColor: "var(--accent)" }}
            >
              {scraperRunning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Bot className="w-4 h-4" />
              )}
              {scraperRunning ? "Scrapeando..." : "Scrapear URL"}
            </button>
          </div>
        </div>
      </div>

      {/* Scraper progress panel (durante el run o con logs de la última ejecución) */}
      {scraperProgress && (scraperRunning || (scraperProgress.logs?.length ?? 0) > 0) && (
        <div
          className="rounded-2xl border overflow-hidden"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div
            className="px-5 py-4 border-b flex items-center gap-3"
            style={{ borderColor: "var(--border)" }}
          >
            {scraperRunning ? (
              <Loader2 className="w-5 h-5 animate-spin shrink-0" style={{ color: "var(--accent)" }} />
            ) : (
              <CheckCircle2 className="w-5 h-5 shrink-0" style={{ color: "var(--success, #22c55e)" }} />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate" style={{ color: "var(--text-primary)" }}>
                {scraperProgress.phase === "search" && (scraperProgress.message || "Searching...")}
                {scraperProgress.phase === "manga_start" && `Manga ${scraperProgress.manga_index}/${scraperProgress.manga_total}: ${scraperProgress.current_manga || "..."}`}
                {["cover", "chapter", "pages"].includes(scraperProgress.phase) && scraperProgress.current_manga && (
                  <>Downloading: {scraperProgress.current_manga}</>
                )}
                {scraperProgress.phase === "done" && "Finished"}
                {scraperProgress.phase === "idle" && (scraperProgress.logs?.length ?? 0) > 0 && "Última ejecución"}
                {!["search", "manga_start", "cover", "chapter", "pages", "done", "idle"].includes(scraperProgress.phase) && (scraperProgress.message || scraperProgress.phase)}
                {scraperProgress.phase === "idle" && !(scraperProgress.logs?.length) && scraperProgress.message}
              </p>
              <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                {scraperProgress.chapter_total > 0 && (
                  <>Chapter {scraperProgress.chapter_index}/{scraperProgress.chapter_total}</>
                )}
                {scraperProgress.page_total > 0 && (
                  <span className="ml-2">
                    Page {scraperProgress.page_index}/{scraperProgress.page_total}
                  </span>
                )}
                {scraperProgress.processed_count > 0 && (
                  <span className="ml-2">
                    <CheckCircle2 className="w-3.5 h-3.5 inline align-text-bottom mr-0.5" />
                    {scraperProgress.processed_count} saved
                  </span>
                )}
              </p>
            </div>
          </div>
          {/* Progress bar (manga level) */}
          {scraperProgress.manga_total > 0 && (
            <div className="px-5 py-2" style={{ backgroundColor: "var(--bg-hover)" }}>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(100, (scraperProgress.manga_index / scraperProgress.manga_total) * 100)}%`,
                    backgroundColor: "var(--accent)",
                  }}
                />
              </div>
              <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                Manga {scraperProgress.manga_index} of {scraperProgress.manga_total}
              </p>
            </div>
          )}
          {/* Actividad en vivo: estado actual y motivo si no se guarda */}
          <div className="px-5 py-3 border-t space-y-2" style={{ borderColor: "var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              En vivo
            </p>
            <div
              className="rounded-lg px-4 py-3 text-sm min-h-[3rem] flex items-center"
              style={{
                backgroundColor: "var(--bg-hover)",
                color: "var(--text-primary)",
              }}
            >
              {scraperProgress.message ? (
                <span className="break-words">{scraperProgress.message}</span>
              ) : (
                <span style={{ color: "var(--text-muted)" }}>
                  {scraperProgress.phase === "search" && "Buscando…"}
                  {scraperProgress.phase === "manga_start" && "Iniciando manga…"}
                  {["cover", "chapter", "pages"].includes(scraperProgress.phase) && "Descargando…"}
                  {scraperProgress.phase === "done" && "Finalizado."}
                  {scraperProgress.phase === "idle" && "En espera."}
                  {!["search", "manga_start", "cover", "chapter", "pages", "done", "idle"].includes(scraperProgress.phase) && scraperProgress.phase}
                </span>
              )}
            </div>
            {(() => {
              const logs = scraperProgress.logs ?? [];
              const lastSkipOrError = [...logs].reverse().find((e) => e.phase === "skip" || e.phase === "error");
              if (!lastSkipOrError) return null;
              const isError = lastSkipOrError.phase === "error";
              const title = (lastSkipOrError.detail as { title?: string } | undefined)?.title;
              return (
                <div
                  className="rounded-lg px-4 py-3 text-sm flex flex-col gap-1"
                  style={{
                    backgroundColor: isError ? "rgba(220,80,80,0.12)" : "rgba(200,150,0,0.15)",
                    borderLeft: `4px solid ${isError ? "var(--warning, #e11)" : "rgba(200,150,0,0.8)"}`,
                    color: "var(--text-primary)",
                  }}
                >
                  <span className="font-semibold" style={{ color: isError ? "var(--warning)" : "var(--text-primary)" }}>
                    {isError ? "Error — no se guardará este manga:" : "No se guardará este manga:"}
                  </span>
                  {title && <span className="text-xs" style={{ color: "var(--text-muted)" }}>{title}</span>}
                  <span className="break-words">{lastSkipOrError.message}</span>
                </div>
              );
            })()}
          </div>
          {/* Errors */}
          {scraperProgress.errors.length > 0 && (
            <div
              className="px-5 py-3 border-t flex items-start gap-2"
              style={{ borderColor: "var(--border)" }}
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--warning)" }} />
              <ul className="text-sm list-disc list-inside space-y-0.5" style={{ color: "var(--text-secondary)" }}>
                {scraperProgress.errors.slice(-5).map((err, i) => (
                  <li key={i} className="truncate" title={err}>{err}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Logs del scraper */}
          {(scraperProgress.logs?.length ?? 0) > 0 && (
            <div
              className="border-t"
              style={{ borderColor: "var(--border)" }}
            >
              <p className="px-5 py-2 text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                Logs
              </p>
              <div
                className="px-5 pb-4 overflow-y-auto max-h-64 text-xs font-mono space-y-1"
                style={{ color: "var(--text-secondary)" }}
              >
                {(scraperProgress.logs ?? []).map((entry, i) => (
                  <div key={i} className="flex gap-2 items-baseline flex-wrap">
                    <span className="text-[10px] shrink-0 opacity-80" style={{ color: "var(--text-muted)" }}>
                      {entry.time}
                    </span>
                    <span
                      className="shrink-0 px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor:
                          entry.phase === "error" ? "var(--warning)" :
                          entry.phase === "skip" ? "rgba(200,150,0,0.2)" :
                          entry.phase === "search" ? "rgba(100,150,255,0.15)" :
                          entry.phase === "manga_done" ? "rgba(0,180,100,0.15)" :
                          "var(--bg-hover)",
                        color: "var(--text-primary)",
                      }}
                    >
                      {entry.phase}
                    </span>
                    <span className="min-w-0 break-words">{entry.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sugerir manga */}
      <div
        className="rounded-2xl border overflow-hidden"
        style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="p-5 border-b flex flex-wrap items-end gap-3" style={{ borderColor: "var(--border)" }}>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>
              Buscar manga en ManhwaWeb
            </label>
            <input
              type="text"
              placeholder="Nombre del manga (ej. Solo Leveling, One Piece...)"
              value={suggestInput}
              onChange={(e) => { setSuggestInput(e.target.value); setSuggestError(null); }}
              onKeyDown={(e) => e.key === "Enter" && handleAddSuggestion()}
              className="w-full px-4 py-2.5 rounded-xl text-sm border focus:outline-none"
              style={{
                backgroundColor: "var(--bg-secondary)",
                borderColor: "var(--border)",
                color: "var(--text-primary)",
              }}
            />
            {suggestError && (
              <p className="text-xs mt-1" style={{ color: "var(--warning)" }}>{suggestError}</p>
            )}
          </div>
          <button
            type="button"
            onClick={handleAddSuggestion}
            disabled={!suggestInput.trim()}
            className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
            style={{ backgroundColor: "var(--accent)", color: "white" }}
          >
            <PlusCircle className="w-4 h-4" /> Agregar
          </button>
        </div>
        {suggestions.length > 0 && (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {suggestions.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between gap-3 p-4"
                style={{ borderColor: "var(--border)" }}
              >
                <div>
                  <p className="font-medium text-sm" style={{ color: "var(--text-primary)" }}>{s.title}</p>
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>{s.status}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {s.status === "pending" && (
                    <button
                      type="button"
                      onClick={() => handleRunScraper(s.title)}
                      disabled={scraperRunning}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                      style={{ backgroundColor: "var(--accent)", color: "white" }}
                    >
                      <Bot className="w-3.5 h-3.5" /> Descargar 5 caps
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDeleteSuggestion(s.id)}
                    className="p-1.5 rounded-lg transition-colors"
                    style={{ color: "var(--text-muted)" }}
                    title="Eliminar sugerencia"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search + Filters */}
      <div className="space-y-4">
        <div className="relative">
          <Search
            className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: "var(--text-muted)" }}
          />
          <input
            type="text"
            placeholder="Search manga..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full pl-11 pr-4 py-3 rounded-xl text-sm border focus:outline-none"
            style={{
              backgroundColor: "var(--bg-secondary)",
              borderColor: "var(--border)",
              color: "var(--text-primary)",
            }}
          />
        </div>

        {/* Language filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
            Language:
          </span>
          {[null, "es", "en"].map((lang) => (
            <button
              key={lang ?? "all"}
              onClick={() => { setSelectedLang(lang); setPage(1); }}
              className="px-3 py-1 rounded-lg text-xs font-medium border transition-colors"
              style={{
                backgroundColor: selectedLang === lang ? "rgba(139,92,246,0.15)" : "transparent",
                borderColor: selectedLang === lang ? "rgba(139,92,246,0.3)" : "var(--border)",
                color: selectedLang === lang ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              {lang === null ? "All" : lang.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Tags */}
        {tags.length > 0 && (
          <TagFilter
            tags={tags}
            selected={selectedTag}
            onSelect={(t) => { setSelectedTag(t); setPage(1); }}
          />
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="rounded-2xl animate-pulse aspect-[3/4]"
              style={{ backgroundColor: "var(--bg-card)" }}
            />
          ))}
        </div>
      ) : mangas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <BookOpen className="w-16 h-16 mb-4" style={{ color: "var(--text-muted)" }} />
          <p className="text-lg font-medium" style={{ color: "var(--text-secondary)" }}>
            No manga found
          </p>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Run the scraper to discover manga
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {mangas.map((manga) => (
            <MangaCard key={manga.id} manga={manga} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 pt-4">
          {Array.from({ length: Math.min(totalPages, 10) }).map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className="w-9 h-9 rounded-lg text-sm font-medium transition-colors"
              style={{
                backgroundColor: page === i + 1 ? "var(--accent)" : "var(--bg-secondary)",
                color: page === i + 1 ? "white" : "var(--text-secondary)",
              }}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
