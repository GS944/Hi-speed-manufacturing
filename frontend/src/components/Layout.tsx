import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { BrainCircuit, ClipboardList, Database, FileSpreadsheet, LayoutDashboard, LogOut, Menu, Moon, Radar, Settings, Sun, X } from "lucide-react";
import { useAuth } from "../lib/auth";
import CommandBar from "./CommandBar";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/track", label: "Live Tracker", icon: Radar },
  { to: "/orders", label: "Orders", icon: ClipboardList },
  { to: "/annexure", label: "Annexure & Print", icon: FileSpreadsheet },
  { to: "/data", label: "Data Sheets", icon: Database },
  { to: "/insights", label: "Intelligence", icon: BrainCircuit },
  { to: "/settings", label: "Settings", icon: Settings },
];

function useTheme() {
  const [theme, setTheme] = useState<string>(() => document.documentElement.dataset.theme ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ot-theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}

export default function Layout() {
  const { username, logout } = useAuth();
  const [theme, toggle] = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setMobileOpen(false), [loc.pathname]);

  const sidebar = (
    <nav className="flex h-full flex-col gap-1 p-3">
      <div className="mb-4 flex items-center gap-2.5 px-2 pt-1">
        <img src="/favicon.svg" alt="" className="size-8" />
        <div>
          <div className="text-[15px] font-semibold leading-tight text-ink">OrderTrack Pro</div>
          <div className="text-[11.5px] text-muted">Production & job-work control</div>
        </div>
      </div>
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end}
          className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
            isActive ? "bg-primary-soft text-primary" : "text-ink-2 hover:bg-surface-3 hover:text-ink")}>
          <Icon className="size-[18px]" /> {label}
        </NavLink>
      ))}
      <div className="mt-auto rounded-lg border border-line bg-surface-2 p-3">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-full bg-primary text-[13px] font-semibold text-on-primary">
            {(username || "A")[0].toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{username}</div>
            <div className="text-[11.5px] text-muted">Administrator</div>
          </div>
          <button onClick={() => logout()} title="Sign out" aria-label="Sign out" className="rounded-md p-1.5 text-muted hover:bg-surface-3 hover:text-critical"><LogOut className="size-4" /></button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 border-r border-line bg-surface lg:block no-print">{sidebar}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 lg:hidden no-print" onClick={() => setMobileOpen(false)}>
          <aside className="h-full w-64 bg-surface" onClick={(e) => e.stopPropagation()}>{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur no-print">
          <button className="rounded-md p-1.5 text-ink-2 hover:bg-surface-3 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
          <CommandBar />
          <div className="ml-auto flex items-center gap-1">
            <button onClick={toggle} className="rounded-lg p-2 text-ink-2 hover:bg-surface-3" aria-label="Toggle colour theme" title="Toggle theme">
              {theme === "dark" ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
