"use client";

// Map-first public portal: the 3D situation map *is* the page; everything
// else is a thin overlay.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { CasePanel, LayerChips, MapLegend, StatusStrip, TimeScrubber } from "@/components/portal/Hud";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { GeoFeature, MapFeature, Phase, PublicCase, PublicCaseDetail, RouteFeature, VehicleItem } from "@/lib/types";
import { countsByLayer, usePublicPlatform } from "@/lib/usePortal";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full !rounded-none" /> });

export default function PortalHome() {
  const { slug } = useParams<{ slug: string }>();
  const { platform, situation, map, statuses, error, reload, layers, visible, toggle, official } = usePublicPlatform(slug);
  const [cases, setCases] = useState<PublicCase[]>([]);
  const [phase, setPhase] = useState<Phase | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PublicCaseDetail | null>(null);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const [threeD, setThreeD] = useState(true);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [vehicles, setVehicles] = useState<VehicleItem[]>([]);
  const [hasLive, setHasLive] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const [orbit, setOrbit] = useState(false);
  const nowMs = useMemo(() => Date.now(), [situation?.generated_at]); // eslint-disable-line react-hooks/exhaustive-deps

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
    const id = window.setInterval(loadCases, 30000);
    return () => window.clearInterval(id);
  }, [loadCases]);

  // dispatch routes + responding vehicles (vehicles poll fast; positions are
  // interpolated client-side so motion is smooth)
  useEffect(() => {
    // government movement is opt-in on the public site: don't poll what is hidden
    if (visible.dispatch !== true) {
      setRoutes([]);
      setVehicles([]);
      return;
    }
    const loadRoutes = () => api.publicRoutes(slug).then((r) => setRoutes(r.features)).catch(() => undefined);
    const loadVehicles = () =>
      api
        .publicVehicles(slug)
        .then((r) => {
          setVehicles(r.items);
          setHasLive(r.has_live);
        })
        .catch(() => undefined);
    loadRoutes();
    loadVehicles();
    const a = window.setInterval(loadRoutes, 20000);
    const b = window.setInterval(loadVehicles, 3000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [slug, visible.dispatch]);

  useEffect(() => {
    if (!selectedId?.startsWith("case:")) {
      setDetail(null);
      return;
    }
    const id = selectedId.slice(5);
    api.publicCase(slug, id).then(setDetail).catch(() => setDetail(null));
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
          <ErrorBox message={/not found|404/i.test(error) ? "找不到這個災情平台：網址可能已變更、平台已下架或重新建立。" : error} onRetry={reload} />
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
      <div className="relative h-[calc(100dvh-52px)] w-full overflow-hidden bg-[#e9edf1]">
        {platform ? (
          <TerrainMap center={center} zoom={platform.map.zoom} features={features} officialLayers={official} visible={visible} enabledLayers={layers} selectedId={selectedId} onSelect={onSelect} timeCutoff={cutoff} threeD={threeD} routes={routes} vehicles={vehicles} fitToData orbit={orbit && threeD} />
        ) : (
          <Skeleton className="h-full w-full !rounded-none" />
        )}

        {/* top-left: status + layers */}
        <div className="pointer-events-none absolute left-3 right-3 top-3 z-10 flex flex-col gap-2 lg:right-[372px]">
          <div className="pointer-events-auto">
            <StatusStrip situation={situation} county={platform?.county ?? null} />
          </div>
          <div className="pointer-events-auto max-w-full overflow-x-auto pb-1 [scrollbar-width:none]">
            <LayerChips enabledLayers={layers} visible={visible} onToggle={toggle} statuses={statuses} official={official} threeD={threeD} onToggle3D={() => setThreeD((v) => !v)} legendOpen={legendOpen} onToggleLegend={() => setLegendOpen((v) => !v)} vehicleCount={vehicles.length} hasLive={hasLive} orbit={orbit} onToggleOrbit={() => setOrbit((v) => !v)} counts={layerCounts} />
          </div>
        </div>

        {legendOpen ? (
          <div className="absolute left-3 top-[118px] z-10 lg:top-[128px]">
            <MapLegend />
          </div>
        ) : null}

        {/* right: case panel (desktop) */}
        <div className="absolute bottom-3 right-3 top-3 z-10 hidden w-[348px] lg:block">
          <CasePanel slug={slug} cases={cases} phase={phase} onPhase={setPhase} selectedId={selectedId} onSelect={setSelectedId} detail={detail} onClose={() => setSelectedId(null)} />
        </div>

        {/* bottom-left: time scrubber (desktop) */}
        <div className="absolute bottom-3 left-3 z-10 hidden w-[min(560px,calc(100%-400px))] lg:block">
          {situation ? <TimeScrubber trend={situation.trend} cutoff={cutoff} onCutoff={setCutoff} nowMs={nowMs} /> : null}
        </div>

        {/* mobile: bottom sheet */}
        <div className={`absolute inset-x-0 bottom-0 z-10 transition-[height] lg:hidden ${panelOpen ? "h-[58%]" : "h-12"}`}>
          <button type="button" className="af-hud flex h-12 w-full items-center justify-between rounded-b-none px-4 text-[13px] font-medium" onClick={() => setPanelOpen((v) => !v)} aria-expanded={panelOpen}>
            <span>
              最新災情 · {cases.length} 件
              <span className="ml-2 text-[9.5px] font-normal text-[var(--faint)]">© OpenStreetMap · OpenFreeMap · AWS Terrain</span>
            </span>
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
