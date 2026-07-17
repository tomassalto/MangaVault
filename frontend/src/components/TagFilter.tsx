import { clsx } from "clsx";
import type { TagCount } from "../api/client";

interface TagFilterProps {
  tags: TagCount[];
  selected: string | null;
  onSelect: (tag: string | null) => void;
}

export function TagFilter({ tags, selected, onSelect }: TagFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onSelect(null)}
        className={clsx(
          "px-3 py-1.5 rounded-xl text-xs font-medium transition-colors border"
        )}
        style={{
          backgroundColor: !selected ? "rgba(139, 92, 246, 0.15)" : "transparent",
          borderColor: !selected ? "rgba(139, 92, 246, 0.3)" : "var(--border)",
          color: !selected ? "var(--accent)" : "var(--text-secondary)",
        }}
      >
        All
      </button>
      {tags.map((t) => (
        <button
          key={t.tag}
          onClick={() => onSelect(t.tag === selected ? null : t.tag)}
          className="px-3 py-1.5 rounded-xl text-xs font-medium transition-colors border"
          style={{
            backgroundColor: t.tag === selected ? "rgba(139, 92, 246, 0.15)" : "transparent",
            borderColor: t.tag === selected ? "rgba(139, 92, 246, 0.3)" : "var(--border)",
            color: t.tag === selected ? "var(--accent)" : "var(--text-secondary)",
          }}
        >
          {t.tag}
          <span className="ml-1 opacity-50">{t.count}</span>
        </button>
      ))}
    </div>
  );
}
