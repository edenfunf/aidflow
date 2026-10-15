"use client";

// Front door. Citizens pick the disaster they want to report or follow; staff
// sign in to the 政府管理後台. The map behind is Taiwan's terrain — no disaster
// is implied at this level.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import CountUp from "@/components/CountUp";
import { BrandLockup } from "@/components/Brand";
import { EmptyState, Skeleton } from "@/components/ui";
import { api, getToken } from "@/lib/api";
import { HAZARD_LABEL } from "@/lib/labels";
import { fmtAgo } from "@/lib/format";
import type { PublicPlatform, Situation } from "@/lib/types";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

const TAIWAN_CENTER: [number, number] = [23.7, 120.95];
const HERO_CARD_WIDTH = 560; // keep in sync with the hero card's max-width

// The hero card covers the left of the viewport on desktop. Rather than guess a
// longitude offset (which drifts with window size), hand the map the card's
// width as camera padding: it keeps Taiwan centred in the clear space to the
// right at any width. Phones show the card below the fold, so no padding.
function heroView(width: number): { zoom: number; padLeft: number } {
  if (width < 900) return { zoom: 6.1, padLeft: 0 };
  const cardRight = Math.max(0, (width - 1200) / 2) + HERO_CARD_WIDTH;
  return { zoom: width >= 1280 ? 7.1 : 6.9, padLeft: Math.min(cardRight, width * 0.5) };
}

export default function HomePage() {
  const [items, setItems] = useState<PublicPlatform[] | null>(null);
  const [situations, setSituations] = useState<Record<string, Situation>>({});
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [hero, setHero] = useState<{ zoom: number; padLeft: number } | null>(null);

  useEffect(() => {
    setSignedIn(Boolean(getToken()));
    const applyHero = () => setHero(heroView(window.innerWidth));
    applyHero();
    window.addEventListener("resize", applyHero);
    api
      .publicPlatforms()
      .then((r) => {
        setItems(r.items);
        r.items.slice(0, 12).forEach((p) =>
          api
            .situation(p.slug)
            .then((s) => setSituations((x) => ({ ...x, [p.slug]: s })))
            .catch(() => undefined)
        );
      })
      .catch((e) => setError((e as Error).message));
    return () => window.removeEventListener("resize", applyHero);
  }, []);

  const heroVisible = useMemo(() => ({}), []);
  const noLayers = useMemo<string[]>(() => [], []);
  const featured = items?.[0];

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      <header className="border-b sm:hidden" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className="flex items-center justify-between gap-2 px-3 py-2.5">
          <BrandLockup subtitle="災情通報與處理平台" size={30} />
          <Link href={signedIn ? "/console" : "/login"} className="text-[14px] text-[var(--focus)] hover:underline">
            {signedIn ? "後台" : "政府人員登入"}
          </Link>
        </div>
      </header>

      <section className="relative bg-[var(--surface)] sm:h-[min(62vh,620px)] sm:bg-[#dfe6ee]">
        {/* the decorative national map is desktop-only: on a phone it crops the
            island and pushes the report button below the fold, and the real
            interactive map is one tap away */}
        <div className="hidden sm:absolute sm:inset-0 sm:block">
          {hero ? <TerrainMap center={TAIWAN_CENTER} zoom={hero.zoom} padLeft={hero.padLeft} features={[]} visible={heroVisible} enabledLayers={noLayers} threeD orbit minimal className="absolute inset-0" /> : null}
        </div>
        <div className="af-topfade pointer-events-none absolute inset-x-0 top-0 hidden h-28 sm:block" />
        <header className="absolute inset-x-0 top-0 z-20 hidden sm:block">
          <div className="mx-auto flex max-w-[1200px] items-center justify-between px-4 py-4">
            <BrandLockup subtitle="災情通報與處理平台" size={34} />
            <Link href={signedIn ? "/console" : "/login"} className="af-btn af-btn-secondary">
              {signedIn ? "進入政府管理後台" : "政府人員登入"}
            </Link>
          </div>
        </header>
        <div className="px-4 py-5 sm:pointer-events-none sm:absolute sm:inset-0 sm:flex sm:items-center sm:px-8 sm:py-0">
          <div className="af-hero-card-sm w-full max-w-[560px] sm:pointer-events-auto sm:mx-0 sm:ml-[max(0px,calc((100vw-1200px)/2))] sm:p-6">
            <h1 className="text-[30px] font-bold leading-tight text-[var(--ink)] sm:text-[36px]">看到災情，馬上通報</h1>
            <p className="mt-2 text-[17px] leading-relaxed text-[var(--ink-2)] sm:text-[18px]">免登入、免註冊。通報會即時通知縣府承辦人員，您可以在災情地圖上追蹤處理進度。</p>
            <p className="mt-3 rounded-md border px-3 py-2 text-[16px] font-medium" style={{ borderColor: "#fecdca", background: "#fef3f2", color: "#b42318" }}>
              危及生命請先撥打 <a href="tel:119" className="underline">119</a>
            </p>
            {featured ? (
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <Link href={`/p/${featured.slug}/report`} className="af-btn af-btn-lg flex-1 !py-4 !text-[20px] font-bold text-white" style={{ background: "#d92d20" }}>
                  我要通報災情
                </Link>
                <Link href={`/p/${featured.slug}`} className="af-btn af-btn-secondary af-btn-lg flex-1 !py-4 !text-[18px]">
                  查看災情地圖
                </Link>
              </div>
            ) : null}
            {featured && (items?.length ?? 0) > 1 ? <p className="mt-2 text-[14px] text-[var(--muted)]">目前開放多個災害事件，請於下方選擇。</p> : null}
          </div>
        </div>
      </section>

      <main className="af-page mx-auto max-w-[1200px] px-4 pb-8 pt-5 sm:py-8">
        <h2 className="af-h1">目前開放通報的災害事件</h2>
        {error ? <div className="mt-3 text-[16px] text-[var(--sev-high)]">{error}</div> : null}
        {items === null ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </div>
        ) : items.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="目前沒有開放通報的災害事件" detail="災害發生時，縣府會在此開放通報。" />
          </div>
        ) : (
          <ul className="mt-4 grid gap-3 lg:grid-cols-2">
            {items.map((p) => {
              const s = situations[p.slug];
              return (
                <li key={p.id} className="af-panel flex flex-col p-5">
                  <div className="text-[15px] text-[var(--muted)]">
                    {p.county || "—"} · {p.hazard_labels?.length ? p.hazard_labels.join("、") : p.hazards.map((h) => HAZARD_LABEL[h] || h).join("、")}
                    {s?.last_report_at ? ` · 最近通報 ${fmtAgo(s.last_report_at)}` : ""}
                  </div>
                  <h3 className="mt-1 text-[22px] font-bold text-[var(--ink)]">{p.name}</h3>
                  <div className="mt-3 flex gap-6">
                    {[
                      ["目前災情", s?.cases_open, "var(--ink)"],
                      ["處理中", s?.cases_active, "var(--st-active)"],
                      ["民眾可協助", s?.cases_community, "var(--st-community)"],
                    ].map(([label, value, color]) => (
                      <div key={String(label)}>
                        <div className="text-[26px] font-semibold leading-none tabular-nums" style={{ color: String(color) }}>
                          {value === undefined ? "–" : <CountUp value={Number(value)} />}
                        </div>
                        <div className="mt-1 text-[14px] text-[var(--muted)]">{label}</div>
                      </div>
                    ))}
                  </div>
                  <div className={`mt-4 grid gap-2 sm:grid-cols-2 ${items.length === 1 ? "hidden sm:grid" : ""}`}>
                    <Link href={`/p/${p.slug}/report`} className="af-btn af-btn-lg font-bold text-white" style={{ background: "#d92d20" }}>
                      我要通報
                    </Link>
                    <Link href={`/p/${p.slug}`} className="af-btn af-btn-secondary af-btn-lg">
                      災情地圖與處理進度
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </main>

      <footer className="border-t" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-5 text-[14px] text-[var(--muted)]">
          <span>消防救護 <a href="tel:119" className="font-semibold text-[var(--ink-2)]">119</a></span>
          <span>警察 <a href="tel:110" className="font-semibold text-[var(--ink-2)]">110</a></span>
          <span className="ml-auto">本站資訊以各主管機關正式公告為準。公開內容已去識別化。</span>
          <Link href="/login" className="text-[var(--focus)] hover:underline">
            政府人員登入
          </Link>
        </div>
      </footer>
    </div>
  );
}
