"use client";

// Public portal chrome: a government-site header with the platform name, a
// short nav and the emergency numbers. Mobile first; 「我要通報」 is always the
// most prominent control on the page — reporting is what the site is for.

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { PublicPlatform } from "@/lib/types";
import { BrandMark } from "@/components/Brand";

export const PORTAL_HEADER_PX = 60;

export default function PortalShell({ platform, slug, children, fullBleed = false }: { platform: PublicPlatform | null; slug: string; children: React.ReactNode; fullBleed?: boolean }) {
  const pathname = usePathname();
  const base = `/p/${slug}`;
  const nav = [
    { href: base, label: "災情地圖" },
    { href: `${base}/cases`, label: "處理進度" },
  ];
  const isActive = (href: string) => (href === base ? pathname === base : pathname.startsWith(href));
  const onReport = pathname.startsWith(`${base}/report`);
  const county = platform?.county || "";

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      <header className="sticky top-0 z-20" style={{ background: "var(--brand)", color: "#fff" }}>
        <div className="mx-auto flex h-[60px] max-w-[1440px] items-center justify-between gap-3 px-3 sm:px-4">
          <Link href={base} className="flex min-w-0 items-center gap-2.5">
            <BrandMark size={34} inverted className="flex-none" />
            <span className="min-w-0">
              <span className="block truncate text-[12px] tracking-[0.1em] text-white/65">{county ? `${county}政府 · 災害應變` : "AidFlow"}</span>
              <span className="block truncate text-[17px] font-semibold leading-tight">{platform?.name || "災情通報平台"}</span>
            </span>
          </Link>
          <nav className="flex flex-none items-center gap-1 text-[15px]">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`hidden whitespace-nowrap rounded px-3 py-2 transition sm:inline-block ${isActive(n.href) ? "bg-white/15 text-white" : "text-white/80 hover:bg-white/10 hover:text-white"}`}
              >
                {n.label}
              </Link>
            ))}
            <Link
              href={`${base}/report`}
              className={`ml-1 inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-4 py-2 text-[16px] font-bold shadow-sm transition ${onReport ? "bg-white text-[var(--brand)]" : "bg-[#d92d20] text-white hover:bg-[#b42318]"}`}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3v11" />
                <path d="M12 19.5v.5" />
                <circle cx="12" cy="12" r="10" />
              </svg>
              我要通報
            </Link>
          </nav>
        </div>
        {/* phones: the two views as a tab row under the header */}
        <div className="flex border-t border-white/10 sm:hidden">
          {nav.map((n) => (
            <Link key={n.href} href={n.href} className={`flex-1 py-2 text-center text-[15px] ${isActive(n.href) ? "bg-white/15 font-semibold text-white" : "text-white/75"}`}>
              {n.label}
            </Link>
          ))}
        </div>
      </header>
      <main className={fullBleed ? "" : "af-page mx-auto max-w-[1440px] px-3 py-4 sm:px-4"}>{children}</main>
      <footer className={`mx-auto max-w-[1440px] px-4 pb-8 pt-4 text-[14px] text-[var(--muted)] ${fullBleed ? "hidden" : ""}`}>
        <div className="af-divider mb-3" />
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
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
