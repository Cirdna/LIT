import type { ReactNode } from "react";
import { NavLink, Link } from "react-router-dom";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded text-[0.98rem] font-medium ${
    isActive ? "bg-navy text-white" : "text-ink hover:bg-paper"
  }`;

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="no-print border-b border-rule bg-surface">
        <div className="mx-auto flex max-w-[1200px] items-center gap-4 px-5 py-3">
          <Link to="/" className="flex items-baseline gap-2">
            <span className="text-xl font-bold tracking-tight text-navy">AITHENA</span>
            <span className="hidden text-sm text-faint sm:inline">contract portfolio</span>
          </Link>
          <nav className="ml-4 flex items-center gap-1" aria-label="Primary">
            <NavLink to="/" className={navClass} end>
              Portfolio
            </NavLink>
            <NavLink to="/calendar" className={navClass}>
              Calendar
            </NavLink>
            <NavLink to="/conflicts" className={navClass}>
              Conflicts
            </NavLink>
            <NavLink to="/ask" className={navClass}>
              Ask
            </NavLink>
          </nav>
          <div className="ml-auto">
            {/* Reachable from any screen in one click (§9 boundary states). */}
            <Link to="/scope" className="text-sm text-muted underline decoration-rule underline-offset-4 hover:text-ink">
              What this tool won’t tell you
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] flex-1 px-5 py-6">{children}</main>

      <footer className="no-print border-t border-rule bg-surface">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4 text-sm text-muted">
          <span>AITHENA reports what the documents say. It does not give legal advice.</span>
          <Link to="/scope" className="link">
            What this tool won’t tell you →
          </Link>
        </div>
      </footer>
    </div>
  );
}
