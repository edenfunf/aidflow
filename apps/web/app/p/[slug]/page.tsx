"use client";

// Map-first public portal: the situation map *is* the page; everything else
// is a thin overlay. The one action that always stays in reach is 「我要通報」.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { CasePanel, LayerChips, MapLegend, StatusStrip } from "@/components/portal/Hud";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { GeoFeature, MapFeature, Phase, PublicCase, PublicCaseDetail } from "@/lib/types";
import { countsByLayer, usePublicPlatform } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

export default function PortalHome() {
  const { slug } = useParams<{ slug: string }>();
  const { platform, situation, map, statuses, error, reload, layers, visible, toggle, official } = usePublicPlatform(slug);
  const [cases, setCases] = useState<PublicCase[]>([]);
  const [phase, setPhase] = useState<Phase | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PublicCaseDetail | null>(null);
  const [threeD, setThreeD] = useState(true);
  const [panelOpen, setPanelOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.innerWidth < 1024) setThreeD(false);
  }, []);

  const loadCases = useCallback(() => {
    api
      .publicCases(slug, { phase: phase === "all" ? "open" : phase, sort: "updated_desc", limit: 60 })
      .then((r) => setCases(r.items))
      .catch(() => undefined);
  }, [slug, phase]);
  useEffect(() => {
    loadCases();
    const id = window.setInterval(() => {
      if (!document.hidden) loadCases();
    }, 30000);
    return () => window.clearInterval(id);
  }, [loadCases]);

  useEffect(() => {
    if (!selectedId?.startsWith("case:")) {
      setDetail(null);
      return;
    }
    api.publicCase(slug, selectedId.slice(5)).then(setDetail).catch(() => setDetail(null));
  }, [selectedId, slug]);

  const features = useMemo(() => map?.features ?? [], [map]);
  const layerCounts = useMemo(() => countsByLayer(features), [features]);
  const onSelect = useCallback((f: MapFeature | GeoFeature | null) => {
    const id = f && "geometry" in f ? (f as MapFeature).id : null;
    setSelectedId(id);
    if (id) setPanelOpen(true);
  }, []);

  if (error && !platform) {
    return (
      <PortalShell platform={null} slug={slug}>
        <div className="mx-auto max-w-lg py-10">
          <ErrorBox message={/not found|404/i.test(error) ? "找不到這個災情平台：網址可能已變更或平台已下架。" : error} onRetry={reload} />
          <div className="mt-3 text-center">
            <Link href="/" className="af-btn af-btn-primary">
              查看目前開放中的平台
            </Link>
          </div>
        </div>
      </PortalShell>
    );
  }
  const center = platform?.map.center ?? [23.91, 120.69];

  return (
    <PortalShell platform={platform} slug={slug} fullBleed>
      <div className="relative h-[calc(100dvh-100px)] w-full overflow-hidden bg-[#e9edf1] sm:h-[calc(100dvh-60px)]">
        {platform ? (
          <TerrainMap center={center} zoom={platform.map.zoom} features={features} officialLayers={official} visible={visible} enabledLayers={layers} selectedId={selectedId} onSelect={onSelect} threeD={threeD} fitToData />
        ) : (
          <Skeleton className="h-full w-full !rounded-none" />
        )}

        {/* top-left: status + layers */}
        <div className="pointer-events-none absolute left-3 right-3 top-3 z-10 flex flex-col gap-2 lg:right-[392px]">
          <div className="pointer-events-auto">
            <StatusStrip situation={situation} county={platform?.county ?? null} />
          </div>
          <div className="pointer-events-auto max-w-full overflow-x-auto pb-1 [scrollbar-width:none]">
            <LayerChips enabledLayers={layers} visible={visible} onToggle={toggle} statuses={statuses} official={official} threeD={threeD} onToggle3D={() => setThreeD((v) => !v)} legendOpen={legendOpen} onToggleLegend={() => setLegendOpen((v) => !v)} counts={layerCounts} />
          </div>
        </div>

        {legendOpen ? (
          <div className="absolute left-3 top-[140px] z-10">
            <MapLegend />
          </div>
        ) : null}

        {/* the primary action, over the map */}
        <Link
          href={`/p/${slug}/report`}
          className="absolute bottom-16 left-1/2 z-10 inline-flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full bg-[#d92d20] px-6 py-3.5 text-[18px] font-bold lg:px-7 lg:py-4 lg:text-[20px] text-white shadow-[0_10px_28px_-10px_rgba(185,28,28,0.8)] transition hover:bg-[#b42318] lg:bottom-6 lg:left-6 lg:translate-x-0"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3v11" />
            <path d="M12 19.5v.5" />
            <circle cx="12" cy="12" r="10" />
          </svg>
          我要通報災情
        </Link>

        {/* right: case panel (desktop) */}
        <div className="absolute bottom-3 right-3 top-3 z-10 hidden w-[372px] lg:block">
          <CasePanel slug={slug} cases={cases} phase={phase} onPhase={setPhase} selectedId={selectedId} onSelect={setSelectedId} detail={detail} onClose={() => setSelectedId(null)} />
        </div>

        {/* mobile: bottom sheet */}
        <div className={`absolute inset-x-0 bottom-0 z-20 transition-[height] lg:hidden ${panelOpen ? "h-[62%]" : "h-12"}`}>
          <button type="button" className="af-hud flex h-12 w-full items-center justify-between rounded-b-none px-4 text-[16px] font-medium" onClick={() => setPanelOpen((v) => !v)} aria-expanded={panelOpen}>
            <span>最新災情 · {cases.length} 件</span>
            <span className="text-[var(--muted)]">{panelOpen ? "收合 ▾" : "展開 ▴"}</span>
          </button>
          {panelOpen ? (
            <div className="h-[calc(100%-3rem)]">
              <CasePanel slug={slug} cases={cases} phase={phase} onPhase={setPhase} selectedId={selectedId} onSelect={setSelectedId} detail={detail} onClose={() => setSelectedId(null)} />
            </div>
          ) : null}
        </div>
      </div>
    </PortalShell>
  );
}
