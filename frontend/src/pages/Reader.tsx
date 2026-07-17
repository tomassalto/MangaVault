import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Maximize,
  Minimize,
  Loader2,
  Home,
  ZoomIn,
  ZoomOut,
  RotateCcw,
} from "lucide-react";
import { getChapterPages, getManga, imageUrl, type Page, type MangaDetail } from "../api/client";
import { clsx } from "clsx";

export function Reader() {
  const { slug, chapter } = useParams<{ slug: string; chapter: string }>();
  const navigate = useNavigate();

  const [manga, setManga] = useState<MangaDetail | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(0);
  const [showUI, setShowUI] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);

  const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
  const zoomIn = () =>
    setZoom((z) => {
      const i = ZOOM_STEPS.findIndex((s) => s >= z);
      const next = i >= 0 && i < ZOOM_STEPS.length - 1 ? ZOOM_STEPS[i + 1] : ZOOM_STEPS[ZOOM_STEPS.length - 1];
      return Math.min(2, next);
    });
  const zoomOut = () =>
    setZoom((z) => {
      const i = ZOOM_STEPS.findIndex((s) => s >= z);
      const prev = i > 0 ? ZOOM_STEPS[i - 1] : ZOOM_STEPS[0];
      return Math.max(0.5, prev);
    });
  const zoomReset = () => setZoom(1);

  const chapterNum = parseFloat(chapter || "1");

  useEffect(() => {
    if (!slug || !chapter) return;
    setLoading(true);
    Promise.all([getManga(slug), getChapterPages(slug, chapterNum)])
      .then(([m, p]) => {
        setManga(m);
        setPages(p);
        setCurrentPage(0);
        pageRefs.current = new Array(p.length);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [slug, chapter]);

  const chapters = useMemo(
    () => [...(manga?.chapters ?? [])].sort((a, b) => a.number - b.number),
    [manga?.chapters]
  );
  const currentIdx = chapters.findIndex((c) => c.number === chapterNum);
  const prevChapter = currentIdx > 0 ? chapters[currentIdx - 1] : null;
  const nextChapter = currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;

  const goToPage = useCallback((n: number) => {
    const clamped = Math.max(0, Math.min(n, pages.length - 1));
    setCurrentPage(clamped);
    pageRefs.current[clamped]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [pages.length]);

  const goPrev = useCallback(() => {
    if (currentPage > 0) {
      goToPage(currentPage - 1);
    } else if (prevChapter) {
      navigate(`/read/${slug}/${prevChapter.number}`);
    }
  }, [currentPage, prevChapter, goToPage, navigate, slug]);

  const goNext = useCallback(() => {
    if (currentPage < pages.length - 1) {
      goToPage(currentPage + 1);
    } else if (nextChapter) {
      navigate(`/read/${slug}/${nextChapter.number}`);
    }
  }, [currentPage, pages.length, nextChapter, goToPage, navigate, slug]);

  // Update current page from scroll (intersection observer)
  useEffect(() => {
    if (pages.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const i = Number((e.target as HTMLElement).dataset.pageIndex);
            if (!Number.isNaN(i)) setCurrentPage(i);
            break;
          }
        }
      },
      { root: null, rootMargin: "-40% 0px -40% 0px", threshold: 0 }
    );
    pageRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [pages.length]);

  // Keyboard
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "Escape") setShowUI(true);
      else if (e.key === "f") toggleFullscreen();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, goPrev]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ backgroundColor: "var(--bg-primary)" }}
      >
        <Loader2 className="w-8 h-8 animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="min-h-screen relative"
      style={{ backgroundColor: "#0a0a0a" }}
      onClick={() => setShowUI(!showUI)}
    >
      {/* Top bar */}
      <div
        className={clsx(
          "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
          showUI ? "translate-y-0 opacity-100" : "-translate-y-full opacity-0"
        )}
        style={{ backgroundColor: "rgba(0,0,0,0.9)", backdropFilter: "blur(12px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 px-4 h-14 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <Link
              to={`/manga/${slug}`}
              className="p-2 rounded-lg transition-colors shrink-0"
              style={{ color: "var(--text-secondary)" }}
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">{manga?.title}</p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                Cap. {chapterNum} · Pág. {currentPage + 1}/{pages.length}
              </p>
            </div>
          </div>

          {/* Page controls: Prev | Dropdown | Next */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); goPrev(); }}
              disabled={currentPage <= 0 && !prevChapter}
              className="p-2 rounded-lg transition-colors disabled:opacity-30"
              style={{ backgroundColor: "rgba(255,255,255,0.08)", color: "white" }}
              title="Página anterior"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <select
              value={currentPage}
              onChange={(e) => goToPage(Number(e.target.value))}
              onClick={(e) => e.stopPropagation()}
              className="px-3 py-2 rounded-lg text-sm font-medium bg-white/10 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-purple-500 min-w-16"
              title="Ir a página"
            >
              {pages.map((_, i) => (
                <option key={i} value={i} className="bg-gray-900 text-white">
                  {i + 1}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); goNext(); }}
              disabled={currentPage >= pages.length - 1 && !nextChapter}
              className="p-2 rounded-lg transition-colors disabled:opacity-30"
              style={{ backgroundColor: "rgba(255,255,255,0.08)", color: "white" }}
              title="Página siguiente"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <span className="text-xs text-white/80 px-1">{Math.round(zoom * 100)}%</span>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); zoomOut(); }}
              disabled={zoom <= 0.5}
              className="p-2 rounded-lg transition-colors disabled:opacity-30"
              style={{ backgroundColor: "rgba(255,255,255,0.08)", color: "white" }}
              title="Alejar"
            >
              <ZoomOut className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); zoomReset(); }}
              className="p-2 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(255,255,255,0.08)", color: "white" }}
              title="Restablecer zoom"
            >
              <RotateCcw className="w-5 h-5" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); zoomIn(); }}
              disabled={zoom >= 2}
              className="p-2 rounded-lg transition-colors disabled:opacity-30"
              style={{ backgroundColor: "rgba(255,255,255,0.08)", color: "white" }}
              title="Acercar"
            >
              <ZoomIn className="w-5 h-5" />
            </button>
            <button
              onClick={toggleFullscreen}
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              {isFullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Vertical content — all pages with zoom */}
      <div
        className="flex flex-col items-center pt-14 pb-24 origin-top"
        style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}
      >
        {pages.map((page, i) => (
          <div
            key={page.id}
            ref={(el) => { pageRefs.current[i] = el; }}
            data-page-index={i}
            className="w-full max-w-3xl"
          >
            <img
              src={imageUrl(page.image_path)}
              alt={`Página ${page.number}`}
              className="w-full block"
              loading="lazy"
            />
          </div>
        ))}
      </div>

      {/* Bottom bar — chapter nav */}
      <div
        className={clsx(
          "fixed bottom-0 left-0 right-0 z-50 transition-all duration-300",
          showUI ? "translate-y-0 opacity-100" : "translate-y-full opacity-0"
        )}
        style={{ backgroundColor: "rgba(0,0,0,0.9)", backdropFilter: "blur(12px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 h-14">
          {prevChapter ? (
            <Link
              to={`/read/${slug}/${prevChapter.number}`}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors"
              style={{ color: "var(--text-secondary)", backgroundColor: "rgba(255,255,255,0.05)" }}
            >
              <ChevronLeft className="w-4 h-4" /> Cap. {prevChapter.number}
            </Link>
          ) : (
            <div className="w-24" />
          )}

          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            Pág. {currentPage + 1} / {pages.length}
          </span>

          {nextChapter ? (
            <Link
              to={`/read/${slug}/${nextChapter.number}`}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors"
              style={{ color: "var(--text-secondary)", backgroundColor: "rgba(255,255,255,0.05)" }}
            >
              Cap. {nextChapter.number} <ChevronRight className="w-4 h-4" />
            </Link>
          ) : (
            <Link
              to={`/manga/${slug}`}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors"
              style={{ color: "var(--accent)", backgroundColor: "rgba(139,92,246,0.15)" }}
            >
              <Home className="w-4 h-4" /> Volver
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
