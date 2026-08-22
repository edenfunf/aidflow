"use client";

// Public portal chrome: a government-site header with the platform name, a
// short nav and the emergency numbers. Mobile first.

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { PublicPlatform } from "@/lib/types";
import { BrandMark } from "@/components/Brand";

export default function PortalShell({ platform, slug, children, fullBleed = false }: { platform: PublicPlatform | null; slug: string; children: React.ReactNode; fullBleed?: boolean }) {
  const pathname = usePathname();
  const base = `/p/${slug}`;
  const nav = [
    { href: base, label: "即時態勢" },
    { href: `${base}/cases`, label: "災情案件" },
    { href: `${base}/report`, label: "我要通報" },
  ];
  const isActive = (href: string) => (href === base ? pathname === base : pathname.startsWith(href));
  const county = platform?.county || "";

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      <header className="sticky top-0 z-20" style={{ background: "var(--brand)", color: "#fff" }}>
        <div className="mx-auto flex h-[52px] max-w-[1440px] items-center justify-between gap-3 px-4">
          <Link href={base} className="flex min-w-0 items-center gap-2.5">
            <BrandMark size={30} inverted className="flex-none" />
            <span className="min-w-0">
              <span className="block text-[10.5px] uppercase tracking-[0.14em] text-white/60">{county ? `${county}政府` : "AidFlow"} · 災害應變</span>
              <span className="block truncate text-[15px] font-semibold leading-tight">{platform?.name || "災情通報平台"}</span>
            </span>
          </Link>
          <nav className="flex flex-none items-center gap-0.5 text-[13px] sm:gap-1">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`whitespace-nowrap rounded px-2 py-1.5 transition sm:px-2.5 ${isActive(n.href) ? "bg-white/15 text-white" : "text-white/75 hover:bg-white/10 hover:text-white"} ${n.label === "我要通報" ? "!bg-white !text-[var(--brand)] font-semibold" : ""}`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className={fullBleed ? "" : "af-page mx-auto max-w-[1440px] px-3 py-4 sm:px-4"}>{children}</main>
      <footer className={`mx-auto max-w-[1440px] px-4 pb-8 pt-4 text-[11px] text-[var(--muted)] ${fullBleed ? "hidden" : ""}`}>
        <div className="af-divider mb-3" />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {(platform?.contacts || []).map((c) => (
            <span key={c.name}>
              {c.name} <a href={`tel:${c.phone}`} className="font-semibold text-[var(--ink-2)]">{c.phone}</a>
            </span>
          ))}
          <span className="ml-auto">本站資訊以各主管機關正式公告為準。公開內容已去識別化。</span>
        </div>
      </footer>
    </div>
  );
}
