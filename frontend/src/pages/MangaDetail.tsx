import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  Globe,
  Tag,
  Calendar,
  ExternalLink,
  Brain,
  Loader2,
  Trash2,
  Play,
  Download,
} from "lucide-react";
import { getManga, imageUrl, analyzeManga, deleteManga, updateMangaChapters, type MangaDetail as MangaDetailType } from "../api/client";
import { formatDistanceToNow, parseISO } from "date-fns";

export function MangaDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [manga, setManga] = useState<MangaDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [updatingChapters, setUpdatingChapters] = useState(false);
  const [chaptersUpdateResult, setChaptersUpdateResult] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    getManga(slug)
      .then(setManga)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [slug]);

  const handleAnalyze = async () => {
    if (!manga) return;
    setAnalyzing(true);
    try {
      await analyzeManga(manga.slug);
      // Refresh
      const updated = await getManga(manga.slug);
      setManga(updated);
    } catch (e) {
      console.error(e);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDelete = async () => {
    if (!manga || !confirm("Delete this manga and all its files?")) return;
    await deleteManga(manga.slug);
    window.location.href = "/";
  };

  const handleUpdateChapters = async () => {
    if (!manga) return;
    setChaptersUpdateResult(null);
    setUpdatingChapters(true);
    try {
      const res = await updateMangaChapters(manga.slug, 5);
      setChaptersUpdateResult(res.added > 0 ? `Se descargaron ${res.added} capítulo(s) nuevo(s).` : "No hay capítulos nuevos.");
      const updated = await getManga(manga.slug);
      setManga(updated);
    } catch (e) {
      console.error(e);
      setChaptersUpdateResult("Error al buscar capítulos.");
    } finally {
      setUpdatingChapters(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 rounded-xl w-48" style={{ backgroundColor: "var(--bg-tertiary)" }} />
        <div className="h-96 rounded-2xl" style={{ backgroundColor: "var(--bg-card)" }} />
      </div>
    );
  }

  if (!manga) {
    return (
      <div className="text-center py-20">
        <p style={{ color: "var(--text-secondary)" }}>Manga not found</p>
        <Link to="/" className="text-sm mt-2 inline-block" style={{ color: "var(--accent)" }}>
          Back to Library
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="text-sm flex items-center gap-1 transition-colors"
        style={{ color: "var(--text-secondary)" }}
      >
        <ArrowLeft className="w-4 h-4" /> Back to Library
      </Link>

      {/* Hero */}
      <div
        className="rounded-2xl overflow-hidden border"
        style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex flex-col md:flex-row gap-6 p-6">
          {/* Cover */}
          <div className="w-48 shrink-0">
            <div className="aspect-[3/4] rounded-xl overflow-hidden" style={{ backgroundColor: "var(--bg-tertiary)" }}>
              {manga.cover_path ? (
                <img
                  src={imageUrl(manga.cover_path)}
                  alt={manga.title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <BookOpen className="w-12 h-12" style={{ color: "var(--text-muted)" }} />
                </div>
              )}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-bold tracking-tight mb-2">{manga.title}</h1>

            <div className="flex items-center gap-4 mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>
              {manga.language && (
                <span className="flex items-center gap-1">
                  <Globe className="w-3.5 h-3.5" />
                  {manga.language.toUpperCase()}
                </span>
              )}
              <span className="flex items-center gap-1">
                <BookOpen className="w-3.5 h-3.5" />
                {manga.total_chapters} chapters
              </span>
              {manga.source_site && (
                <span className="flex items-center gap-1">
                  Source: {manga.source_site}
                </span>
              )}
              {manga.created_at && (
                <span className="flex items-center gap-1">
                  <Calendar className="w-3.5 h-3.5" />
                  {formatDistanceToNow(parseISO(manga.created_at), { addSuffix: true })}
                </span>
              )}
            </div>

            {/* Tags */}
            {manga.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                {manga.tags.map((t) => (
                  <span
                    key={t.tag}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium"
                    style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
                  >
                    <Tag className="w-3 h-3 inline mr-1" />
                    {t.tag}
                  </span>
                ))}
              </div>
            )}

            {/* Synopsis */}
            {manga.synopsis && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold mb-1" style={{ color: "var(--text-secondary)" }}>
                  Synopsis
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  {manga.synopsis}
                </p>
              </div>
            )}

            {/* Status badge */}
            <div className="flex items-center gap-2 mb-4">
              <span
                className="px-2.5 py-1 rounded-lg text-xs font-bold uppercase"
                style={{
                  backgroundColor:
                    manga.status === "ready"
                      ? "rgba(34,197,94,0.15)"
                      : manga.status === "discarded"
                        ? "rgba(239,68,68,0.15)"
                        : "rgba(245,158,11,0.15)",
                  color:
                    manga.status === "ready"
                      ? "var(--success)"
                      : manga.status === "discarded"
                        ? "var(--danger)"
                        : "var(--warning)",
                }}
              >
                {manga.status}
              </span>
              {manga.content_rating && (
                <span
                  className="px-2.5 py-1 rounded-lg text-xs font-medium uppercase"
                  style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-muted)" }}
                >
                  {manga.content_rating}
                </span>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              {manga.chapters.length > 0 && (
                <Link
                  to={`/read/${manga.slug}/${manga.chapters[0].number}`}
                  className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 text-white transition-colors"
                  style={{ backgroundColor: "var(--accent)" }}
                >
                  <Play className="w-4 h-4" /> Start Reading
                </Link>
              )}
              {manga.status !== "ready" && (
                <button
                  onClick={handleAnalyze}
                  disabled={analyzing}
                  className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 border transition-colors disabled:opacity-50"
                  style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
                >
                  {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain className="w-4 h-4" />}
                  {analyzing ? "Analyzing..." : "Analyze with AI"}
                </button>
              )}
              {manga.source_url && manga.source_site !== "demo" && (
                <>
                  <button
                    type="button"
                    onClick={handleUpdateChapters}
                    disabled={updatingChapters}
                    className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 text-white transition-colors disabled:opacity-50"
                    style={{ backgroundColor: "var(--accent)" }}
                    title="Descargar los siguientes 5 capítulos desde la fuente"
                  >
                    {updatingChapters ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    {updatingChapters ? "Descargando..." : "Descargar 5 caps más"}
                  </button>
                  <a
                    href={manga.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 border transition-colors"
                    style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
                  >
                    <ExternalLink className="w-4 h-4" /> Fuente
                  </a>
                </>
              )}
              <button
                onClick={handleDelete}
                className="p-2.5 rounded-xl border transition-colors"
                style={{ borderColor: "var(--border)", color: "var(--danger)" }}
                title="Delete manga"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Chapters list */}
      <div
        className="rounded-2xl overflow-hidden border"
        style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="p-5 border-b flex items-center justify-between flex-wrap gap-2" style={{ borderColor: "var(--border)" }}>
          <h2 className="text-lg font-semibold">Capítulos ({manga.chapters.length})</h2>
          {chaptersUpdateResult && (
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{chaptersUpdateResult}</p>
          )}
        </div>
        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {manga.chapters.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
              No chapters downloaded yet
            </div>
          ) : (
            manga.chapters.map((ch) => (
              <Link
                key={ch.id}
                to={`/read/${manga.slug}/${ch.number}`}
                className="flex items-center justify-between p-4 transition-colors"
                style={{ borderColor: "var(--border)" }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--bg-hover)")}
                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
              >
                <div className="flex items-center gap-3">
                  <span
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold"
                    style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--accent)" }}
                  >
                    {ch.number}
                  </span>
                  <div>
                    <p className="text-sm font-medium">
                      Chapter {ch.number}
                      {ch.title && <span style={{ color: "var(--text-secondary)" }}> — {ch.title}</span>}
                    </p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {ch.page_count} pages
                      {ch.downloaded_at && ` · Downloaded ${formatDistanceToNow(parseISO(ch.downloaded_at), { addSuffix: true })}`}
                    </p>
                  </div>
                </div>
                <Play className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
