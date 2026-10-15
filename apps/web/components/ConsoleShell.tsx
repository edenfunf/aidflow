"use client";

// Government console chrome. Desktop first; works on a tablet. Every console
// page renders inside it, so it is also the login guard: no session → /login,
// a password that must be changed → the account page, 30 minutes idle → out.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { IDLE_TIMEOUT_MS, signOut, useMe } from "@/lib/auth";
import type { HealthResponse, Permission } from "@/lib/types";
import { BrandMark } from "@/components/Brand";
import { Skeleton } from "@/components/ui";

const NAV: { href: string; label: string; perm?: Permission }[] = [
  { href: "/console", label: "災害平台" },
  { href: "/console/new", label: "建立平台", perm: "manage_platforms" },
  { href: "/console/users", label: "帳號管理", perm: "manage_users" },
  { href: "/console/audit", label: "稽核紀錄", perm: "view_audit" },
  { href: "/console/connectors", label: "資料介接" },
];

export default function ConsoleShell({ children, title, crumbs, wide = false }: { children: React.ReactNode; title?: string; crumbs?: { href?: string; label: string }[]; wide?: boolean }) {
  const pathname = usePathname();
  const { me, loading, can } = useMe();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const lastActive = useRef(Date.now());

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
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  // a password reset by the administrator must be changed before anything else
  useEffect(() => {
    if (me?.must_change_password && !pathname.startsWith("/console/account")) {
      window.location.assign(`/console/account?force=1&next=${encodeURIComponent(pathname)}`);
    }
  }, [me, pathname]);

  // idle sign-out (only for real accounts)
  useEffect(() => {
    if (me?.kind !== "user") return;
    const bump = () => {
      lastActive.current = Date.now();
    };
    const events = ["mousemove", "keydown", "mousedown", "touchstart", "wheel"];
    events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const timer = window.setInterval(() => {
      if (Date.now() - lastActive.current > IDLE_TIMEOUT_MS) signOut("idle");
    }, 30_000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, bump));
      window.clearInterval(timer);
    };
  }, [me]);

  const isActive = (href: string) => (href === "/console" ? pathname === "/console" || pathname.startsWith("/console/platforms") : pathname.startsWith(href));
  const width = wide ? "max-w-none" : "max-w-[1440px]";

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      <header className="sticky top-0 z-20 border-b" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className={`mx-auto flex items-center justify-between gap-4 px-4 py-2 ${width}`}>
          <div className="flex items-center gap-5">
            <Link href="/console" className="flex items-center gap-2">
              <BrandMark size={32} />
              <span className="leading-none">
                <span className="block text-[17px] font-semibold text-[var(--ink)]">AidFlow</span>
                <span className="block text-[12px] tracking-[0.1em] text-[var(--muted)]">政府管理後台</span>
              </span>
            </Link>
            <nav className="hidden items-center gap-1 text-[15px] md:flex">
              {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
                <Link key={n.href} href={n.href} className={`rounded px-3 py-2 transition ${isActive(n.href) ? "bg-[var(--surface-3)] font-semibold text-[var(--ink)]" : "text-[var(--muted)] hover:text-[var(--ink)]"}`}>
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-[var(--muted)]">
            {health ? (
              <span className="hidden items-center gap-1.5 lg:inline-flex" title={health.channels ? `LINE ${health.channels.line ? "已設定" : "未設定"} · Email ${health.channels.email ? "已設定" : "未設定"} · EMIC ${health.channels.emic === "api" ? "介接" : "人工登錄"}` : "系統正常"}>
                <span className="h-2 w-2 rounded-full" style={{ background: "var(--st-done)" }} />
                系統正常
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: "var(--sev-high)" }} /> API 未連線
              </span>
            )}
            <button type="button" className="af-btn af-btn-ghost !px-2.5 !py-1.5 text-[13px]" onClick={toggleTheme} title="切換深色／亮色">
              {dark ? "亮色" : "深色"}
            </button>
            {me ? (
              <div className="relative">
                <button type="button" className="af-btn af-btn-secondary !py-1.5 text-[14px]" onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen}>
                  <span className="grid h-6 w-6 place-items-center rounded-full text-[12px] font-semibold text-white" style={{ background: "var(--brand)" }}>
                    {me.display_name.slice(0, 1)}
                  </span>
                  <span className="max-w-[9rem] truncate">{me.display_name}</span>
                  <span className="hidden text-[12px] text-[var(--muted)] sm:inline">{me.role_label}</span>
                </button>
                {menuOpen ? (
                  <div className="af-panel absolute right-0 top-full z-30 mt-1 w-56 p-1.5 shadow-lg">
                    <div className="px-2.5 py-2 text-[13px] text-[var(--muted)]">
                      {me.username ? <div className="font-mono text-[var(--ink-2)]">{me.username}</div> : null}
                      {me.role_label}
                    </div>
                    {me.kind === "user" ? (
                      <Link href="/console/account" className="block rounded px-2.5 py-2 text-[15px] text-[var(--ink)] hover:bg-[var(--surface-2)]" onClick={() => setMenuOpen(false)}>
                        變更密碼
                      </Link>
                    ) : null}
                    <div className="md:hidden">
                      {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
                        <Link key={n.href} href={n.href} className="block rounded px-2.5 py-2 text-[15px] text-[var(--ink)] hover:bg-[var(--surface-2)]" onClick={() => setMenuOpen(false)}>
                          {n.label}
                        </Link>
                      ))}
                    </div>
                    {me.kind === "user" ? (
                      <button type="button" className="block w-full rounded px-2.5 py-2 text-left text-[15px] text-[var(--sev-high)] hover:bg-[var(--surface-2)]" onClick={() => signOut()}>
                        登出
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        {me?.kind === "dev" ? (
          <div className="border-t px-4 py-1.5 text-center text-[13px]" style={{ borderColor: "var(--line)", background: "#fffaeb", color: "#93370d" }}>
            開發模式：後端未要求登入（AUTH_REQUIRED=false），所有權限開放。正式環境請務必開啟登入。
          </div>
        ) : null}
      </header>
      <main className={`af-page mx-auto px-4 py-5 ${width}`}>
        {crumbs && crumbs.length ? (
          <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[13px] text-[var(--muted)]">
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
        {title ? <h1 className="af-h1 mb-4">{title}</h1> : null}
        {loading && !me ? <Skeleton className="h-64" /> : me ? children : <Skeleton className="h-64" />}
      </main>
    </div>
  );
}
