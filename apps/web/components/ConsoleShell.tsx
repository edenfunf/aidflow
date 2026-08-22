"use client";

// Government operations console chrome. Desktop first; works on a tablet.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getApiKey, setApiKey } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";
import { BrandMark } from "@/components/Brand";

const NAV = [
  { href: "/", label: "系統控制台", exact: true },
  { href: "/console", label: "平台管理" },
  { href: "/console/new", label: "建立平台" },
  { href: "/console/modules", label: "模組註冊表" },
  { href: "/console/connectors", label: "官方資料介接" },
];

export default function ConsoleShell({ children, title, crumbs, wide = false }: { children: React.ReactNode; title?: string; crumbs?: { href?: string; label: string }[]; wide?: boolean }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [keyOpen, setKeyOpen] = useState(false);
  const [key, setKey] = useState("");
  const [dark, setDark] = useState(false);

  // command-centre dark theme: console only, remembered per browser
  useEffect(() => {
    let on = false;
    try {
      on = window.localStorage.getItem("af-console-theme") === "dark";
    } catch {
      /* ignore */
    }
    setDark(on);
  }, []);
  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.setAttribute("data-console-theme", "dark");
    else root.removeAttribute("data-console-theme");
    return () => root.removeAttribute("data-console-theme");
  }, [dark]);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    try {
      window.localStorage.setItem("af-console-theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    setKey(getApiKey());
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : href === "/console" ? pathname === "/console" || pathname.startsWith("/console/platforms") : pathname.startsWith(href));

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      <header className="sticky top-0 z-20 border-b" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className={`mx-auto flex items-center justify-between gap-4 px-4 py-2 ${wide ? "max-w-none" : "max-w-[1440px]"}`}>
          <div className="flex items-center gap-5">
            <Link href="/" className="flex items-center gap-2">
              <BrandMark size={28} />
              <span className="leading-none">
                <span className="block text-[14px] font-semibold text-[var(--ink)]">AidFlow</span>
                <span className="block text-[10px] tracking-[0.12em] text-[var(--muted)]">災情平台生成系統</span>
              </span>
            </Link>
            <nav className="hidden items-center gap-0.5 text-[13px] md:flex">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className={`rounded px-2.5 py-1.5 transition ${isActive(n.href) ? "bg-[var(--surface-3)] font-medium text-[var(--ink)]" : "text-[var(--muted)] hover:text-[var(--ink)]"}`}>
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-[var(--muted)]">
            {health ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--st-done)" }} />
                API v{health.version}
                {health.ai_enabled ? " · AI 解析已啟用" : " · 規則式解析"}
                {health.api_key_required ? " · 需 API Key" : ""}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--sev-high)" }} /> API 未連線
              </span>
            )}
            <button type="button" className="af-btn af-btn-ghost !px-2 !py-1 text-[11px]" onClick={toggleTheme} title="切換指揮中心深色／亮色">
              {dark ? "亮色" : "深色"}
            </button>
            <button type="button" className="af-btn af-btn-ghost !px-2 !py-1 text-[11px]" onClick={() => setKeyOpen((v) => !v)}>
              {key ? "API Key ✓" : "API Key"}
            </button>
          </div>
        </div>
        {keyOpen ? (
          <div className="border-t px-4 py-2" style={{ borderColor: "var(--line)", background: "var(--surface-2)" }}>
            <div className={`mx-auto flex items-center gap-2 ${wide ? "max-w-none" : "max-w-[1440px]"}`}>
              <label className="af-label whitespace-nowrap">X-API-Key</label>
              <input className="af-input max-w-sm" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="設定 ADMIN_API_KEY 時需要" />
              <button
                type="button"
                className="af-btn af-btn-primary"
                onClick={() => {
                  setApiKey(key.trim());
                  setKeyOpen(false);
                }}
              >
                儲存於此瀏覽器
              </button>
            </div>
          </div>
        ) : null}
      </header>
      <main className={`af-page mx-auto px-4 py-4 ${wide ? "max-w-none" : "max-w-[1440px]"}`}>
        {crumbs && crumbs.length ? (
          <div className="mb-2 flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
            {crumbs.map((c, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {c.href ? (
                  <Link href={c.href} className="hover:text-[var(--ink)]">
                    {c.label}
                  </Link>
                ) : (
                  <span className="text-[var(--ink-2)]">{c.label}</span>
                )}
                {i < crumbs.length - 1 ? <span>/</span> : null}
              </span>
            ))}
          </div>
        ) : null}
        {title ? <h1 className="af-h1 mb-3">{title}</h1> : null}
        {children}
      </main>
    </div>
  );
}
