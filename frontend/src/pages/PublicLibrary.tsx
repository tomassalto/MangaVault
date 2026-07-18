import { useEffect, useState, useCallback, useRef } from "react";
import { BookOpen, CheckCircle2, DownloadCloud, Loader2, RefreshCw, Search } from "lucide-react";
import { MangaCard } from "../components/MangaCard";
import { TagFilter } from "../components/TagFilter";
import {
  getDemoManifest,
  getMangaList,
  getTags,
  importDemoTitle,
  type DemoManifestItem,
  getScraperStatus,
  type Manga,
  type TagCount,
  type ScraperStatus,
} from "../api/client";

const DEMO_STEPS = [
  "Resolving cached public source",
  "Indexing chapter and page manifest",
  "Copying generated page assets",
  "Loading cached OCR and metadata",
  "Saving title, chapters, pages, and tags",
];

export function PublicLibrary() {
  const [mangas, setMangas] = useState<Manga[]>([]);
  const [tags, setTags] = useState<TagCount[]>([]);
  const [demoManifest, setDemoManifest] = useState<DemoManifestItem[]>([]);
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [selectedLang, setSelectedLang] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [demoQuery, setDemoQuery] = useState("Atomic Scarlet");
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoStep, setDemoStep] = useState(-1);
  const [demoLogs, setDemoLogs] = useState<string[]>([]);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [mangaRes, tagsRes, statusRes, manifestRes] = await Promise.all([
        getMangaList({
          page,
          per_page: 24,
          tag: selectedTag || undefined,
          language: selectedLang || undefined,
          search: searchQuery || undefined,
        }),
        getTags(),
        getScraperStatus(),
        getDemoManifest(),
      ]);
      setMangas(mangaRes.items);
      setTotal(mangaRes.total);
      setTags(tagsRes);
      setStatus(statusRes);
      setDemoManifest(manifestRes);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, selectedTag, selectedLang, searchQuery]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    return () => {
      timers.current.forEach(clearTimeout);
    };
  }, []);

  const runDemoImport = (query = demoQuery) => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setDemoRunning(true);
    setDemoStep(0);
    setDemoQuery(query);
    setDemoLogs([`Queued cached import: ${query || "Atomic Scarlet"}`]);
    setSearchQuery("");
    setSelectedTag(null);
    setSelectedLang(null);
    setPage(1);

    DEMO_STEPS.forEach((step, index) => {
      const timer = setTimeout(() => {
        setDemoStep(index);
        setDemoLogs((current) => [...current, step]);
      }, 520 * (index + 1));
      timers.current.push(timer);
    });

    const doneTimer = setTimeout(async () => {
      try {
        const result = await importDemoTitle(query);
        setDemoStep(DEMO_STEPS.length);
        setDemoLogs((current) => [
          ...current,
          `${result.created ? "Imported" : "Already imported"}: ${result.title}`,
        ]);
        setSearchQuery(result.title);
        setPage(1);
        await fetchData();
      } catch (error) {
        console.error(error);
        setDemoLogs((current) => [...current, "Import failed. Check API deployment logs."]);
      } finally {
        setDemoRunning(false);
      }
    }, 520 * (DEMO_STEPS.length + 1));
    timers.current.push(doneTimer);
  };

  const totalPages = Math.ceil(total / 24);
  const progressPercent = demoStep < 0 ? 0 : Math.min(100, ((demoStep + 1) / (DEMO_STEPS.length + 1)) * 100);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Library</h1>
          <p style={{ color: "var(--text-secondary)" }} className="mt-1 text-sm">
            {total} title{total !== 1 ? "s" : ""} in your collection
            {status && status.downloading > 0 && (
              <span style={{ color: "var(--warning)" }}> · {status.downloading} processing</span>
            )}
          </p>
        </div>

        <button
          onClick={fetchData}
          className="p-2.5 rounded-xl transition-colors border"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <section
        className="rounded-2xl border overflow-hidden"
        style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="grid gap-4 p-4 md:grid-cols-[minmax(0,1fr)_minmax(280px,420px)]">
          <div>
            <div className="flex items-center gap-2">
              <DownloadCloud className="w-5 h-5" style={{ color: "var(--accent)" }} />
              <h2 className="text-base font-semibold">Cached demo import</h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              Public mode does not scrape the web. It imports from a small legal cache of original demo comics so reviewers can see the ingestion flow, generated pages, OCR metadata, tags, and reader without private adapters.
            </p>

            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  type="text"
                  value={demoQuery}
                  onChange={(e) => setDemoQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !demoRunning && runDemoImport()}
                  className="w-full pl-10 pr-3 py-2.5 rounded-xl text-sm border focus:outline-none"
                  style={{
                    backgroundColor: "var(--bg-secondary)",
                    borderColor: "var(--border)",
                    color: "var(--text-primary)",
                  }}
                />
              </div>
              <button
                type="button"
                onClick={() => runDemoImport()}
                disabled={demoRunning}
                className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2 text-white disabled:opacity-60"
                style={{ backgroundColor: "var(--accent)" }}
              >
                {demoRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <DownloadCloud className="w-4 h-4" />}
                {demoRunning ? "Importing..." : "Import cached title"}
              </button>
            </div>

            {demoManifest.length > 0 && (
              <div className="mt-4 grid gap-2">
                {demoManifest.map((item) => (
                  <button
                    key={item.slug}
                    type="button"
                    onClick={() => runDemoImport(item.title)}
                    disabled={demoRunning}
                    className="rounded-xl border p-3 text-left transition-colors disabled:opacity-60"
                    style={{
                      backgroundColor: item.imported ? "rgba(34,197,94,0.08)" : "var(--bg-secondary)",
                      borderColor: item.imported ? "rgba(34,197,94,0.35)" : "var(--border)",
                    }}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                        {item.title}
                      </span>
                      <span
                        className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                        style={{
                          backgroundColor: item.imported ? "rgba(34,197,94,0.16)" : "rgba(139,92,246,0.14)",
                          color: item.imported ? "var(--success)" : "var(--accent)",
                        }}
                      >
                        {item.imported ? "Imported" : "Import"}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      {item.synopsis}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div
            className="rounded-xl border p-3"
            style={{ backgroundColor: "var(--bg-secondary)", borderColor: "var(--border)" }}
          >
            <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
              <div
                className="h-full transition-all duration-300"
                style={{ width: `${progressPercent}%`, backgroundColor: "var(--accent)" }}
              />
            </div>
            <div className="mt-3 space-y-1.5 min-h-28">
              {demoLogs.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Pick a cached title to simulate ingestion.
                </p>
              ) : (
                demoLogs.slice(-5).map((log, index) => (
                  <div key={`${log}-${index}`} className="flex items-center gap-2 text-sm">
                    {index === demoLogs.slice(-5).length - 1 && demoRunning ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: "var(--accent)" }} />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5" style={{ color: "var(--success)" }} />
                    )}
                    <span style={{ color: "var(--text-secondary)" }}>{log}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="space-y-4">
        <div className="relative">
          <Search
            className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: "var(--text-muted)" }}
          />
          <input
            type="text"
            placeholder="Search library..."
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

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
            Language:
          </span>
          {[null, "es", "en"].map((lang) => (
            <button
              key={lang ?? "all"}
              onClick={() => {
                setSelectedLang(lang);
                setPage(1);
              }}
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

        {tags.length > 0 && (
          <TagFilter
            tags={tags}
            selected={selectedTag}
            onSelect={(t) => {
              setSelectedTag(t);
              setPage(1);
            }}
          />
        )}
      </div>

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
            No titles found
          </p>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Import one cached demo title or clear your filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {mangas.map((manga) => (
            <MangaCard key={manga.id} manga={manga} />
          ))}
        </div>
      )}

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
