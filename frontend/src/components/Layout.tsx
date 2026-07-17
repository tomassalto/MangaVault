import { Outlet, Link, useLocation } from "react-router-dom";
import { BookOpen, Home } from "lucide-react";
import { clsx } from "clsx";

export function Layout() {
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="h-16 border-b flex items-center justify-between px-6 shrink-0" style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-secondary)" }}>
        <Link to="/" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ backgroundColor: "rgba(139, 92, 246, 0.15)" }}>
            <BookOpen className="w-5 h-5" style={{ color: "var(--accent)" }} />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
              MangaVault
            </h1>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          <NavItem to="/" icon={Home} label="Library" active={location.pathname === "/"} />
        </nav>
      </header>

      {/* Content */}
      <main className="flex-1">
        <div className="max-w-[1400px] mx-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function NavItem({ to, icon: Icon, label, active }: { to: string; icon: React.ComponentType<{ className?: string }>; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={clsx(
        "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors",
        active ? "text-white" : "hover:text-white"
      )}
      style={{
        backgroundColor: active ? "rgba(139, 92, 246, 0.15)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
      }}
    >
      <Icon className="w-4 h-4" />
      {label}
    </Link>
  );
}
