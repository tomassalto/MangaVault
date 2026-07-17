import { Link } from "react-router-dom";
import { BookOpen } from "lucide-react";
import type { Manga } from "../api/client";
import { imageUrl } from "../api/client";

export function MangaCard({ manga }: { manga: Manga }) {
  const ratingColors: Record<string, string> = {
    safe: "var(--success)",
    suggestive: "var(--warning)",
    explicit: "var(--danger)",
  };

  return (
    <Link
      to={`/manga/${manga.slug}`}
      className="group block rounded-2xl overflow-hidden transition-all duration-300 hover:-translate-y-1"
      style={{ backgroundColor: "var(--bg-card)", border: "1px solid var(--border)" }}
    >
      {/* Cover */}
      <div className="relative aspect-[3/4] overflow-hidden" style={{ backgroundColor: "var(--bg-tertiary)" }}>
        {manga.cover_path ? (
          <img
            src={imageUrl(manga.cover_path)}
            alt={manga.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <BookOpen className="w-12 h-12" style={{ color: "var(--text-muted)" }} />
          </div>
        )}

        {/* Language badge */}
        {manga.language && (
          <span
            className="absolute top-2 left-2 px-2 py-0.5 rounded-lg text-xs font-bold uppercase"
            style={{ backgroundColor: "rgba(0,0,0,0.7)", color: "white" }}
          >
            {manga.language}
          </span>
        )}

        {/* Content rating */}
        {manga.content_rating && manga.content_rating !== "safe" && (
          <span
            className="absolute top-2 right-2 px-2 py-0.5 rounded-lg text-xs font-bold uppercase"
            style={{ backgroundColor: "rgba(0,0,0,0.7)", color: ratingColors[manga.content_rating] || "white" }}
          >
            {manga.content_rating}
          </span>
        )}

        {/* Chapters count overlay */}
        <div
          className="absolute bottom-0 left-0 right-0 px-3 py-2"
          style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.8))" }}
        >
          <span className="text-xs text-white font-medium">
            {manga.total_chapters} cap{manga.total_chapters !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <h3
          className="font-semibold text-sm leading-tight line-clamp-2 mb-1.5"
          style={{ color: "var(--text-primary)" }}
        >
          {manga.title}
        </h3>

        {/* Tags */}
        {manga.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {manga.tags.slice(0, 3).map((t) => (
              <span
                key={t.tag}
                className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                style={{ backgroundColor: "var(--bg-tertiary)", color: "var(--text-secondary)" }}
              >
                {t.tag}
              </span>
            ))}
            {manga.tags.length > 3 && (
              <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                +{manga.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}
