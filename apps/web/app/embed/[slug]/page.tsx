"use client";

// Embeddable situation map (P-08) for the county website:
//   <iframe src="https://<host>/embed/<slug>" width="100%" height="560"
//           style="border:0" loading="lazy" title="災情地圖"></iframe>
// Which sites may frame it is set by EMBED_ALLOWED_ORIGINS (next.config.js).
// No site chrome; 「我要通報」 and case links open the full portal in a new tab.

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { BrandMark } from "@/components/Brand";
import { Skeleton, StatusPill } from "@/components/ui";
import type { GeoFeature, MapFeature } from "@/lib/types";
import { usePublicPlatform } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

export default function EmbedMap() {
  const { slug } = useParams<{ slug: string }>();
  const { platform, situation, map, layers, visible, official } = usePublicPlatform(slug, 60000);
  const [selected, setSelected] = useState<MapFeature | null>(null);
  const features = useMemo(() => map?.features ?? [], [map]);
  const onSelect = useCallback((f: MapFeature | GeoFeature | null) => {
    setSelected(f && "geometry" in f && (f as MapFeature).properties.layer === "incident_cases" ? (f as MapFeature) : null);
  }, []);
  const portal = typeof window !== "undefined" ? `${window.location.origin}/p/${slug}` : `/p/${slug}`;

  return (
    <div className="relative h-screen w-full overflow-hidden bg-[#e9edf1]">
      {platform ? (
        <TerrainMap center={platform.map.center} zoom={platform.map.zoom} features={features} officialLayers={official} visible={visible} enabledLayers={layers} onSelect={onSelect} threeD={false} fitToData minimal fitPadding={{ top: 90, bottom: 80, left: 30, right: 30 }} />
      ) : (
        <Skeleton className="h-full w-full !rounded-none" />
      )}

      <div className="pointer-events-none absolute inset-x-2 top-2 z-10 flex items-start justify-between gap-2">
        <div className="af-hud pointer-events-auto flex items-center gap-2.5 px-3 py-2">
          <BrandMark size={26} />
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold text-[var(--ink)]">{platform?.name || "災情地圖"}</div>
            {situation ? (
              <div className="text-[13px] text-[var(--muted)]">
                目前災情 <b className="text-[var(--ink)]">{situation.cases_open}</b> · 處理中 <b className="text-[var(--ink)]">{situation.cases_active}</b> · 民眾可協助 <b className="text-[var(--ink)]">{situation.cases_community}</b>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {selected ? (
        <div className="af-hud absolute bottom-16 left-2 right-2 z-10 p-3 sm:left-auto sm:w-[320px]">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[16px] font-semibold text-[var(--ink)]">{selected.properties.title}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-[var(--muted)]">
                <StatusPill status={selected.properties.status} phase={selected.properties.phase} />
                <span>{selected.properties.unique_reporter_count} 人回報</span>
              </div>
            </div>
            <button type="button" className="af-hud-chip" onClick={() => setSelected(null)} aria-label="關閉">
              ✕
            </button>
          </div>
          <a href={`${portal}/cases/${String(selected.properties.case_id)}`} target="_blank" rel="noopener" className="mt-2 block text-[14px] font-medium text-[var(--focus)] hover:underline">
            查看處理進度 ↗
          </a>
        </div>
      ) : null}

      <a
        href={`${portal}/report`}
        target="_blank"
        rel="noopener"
        className="absolute bottom-3 left-3 z-10 inline-flex items-center gap-2 rounded-full bg-[#d92d20] px-5 py-3 text-[17px] font-bold text-white shadow-lg hover:bg-[#b42318]"
      >
        我要通報災情 ↗
      </a>
      <a href={portal} target="_blank" rel="noopener" className="af-hud absolute bottom-3 right-3 z-10 px-3 py-2 text-[14px] font-medium text-[var(--focus)]">
        開啟完整網站 ↗
      </a>
    </div>
  );
}
