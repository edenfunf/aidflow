"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import PortalShell from "@/components/PortalShell";
import CaseTimeline, { ProgressSteps } from "@/components/CaseTimeline";
import CompareSlider from "@/components/CompareSlider";
import PhotoStrip from "@/components/PhotoStrip";
import { BackLink, ErrorBox, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { CategoryBadge } from "@/lib/categoryIcons";
import { fmtAgo, fmtTime } from "@/lib/format";
import { CATEGORY_LAYER, ROLE_LABEL, VEHICLE_LABEL, VEHICLE_STATUS_LABEL } from "@/lib/labels";
import type { GeoFeature, MapFeature, PublicCaseDetail, PublicPlatform, RouteFeature, VehicleItem } from "@/lib/types";
import { haversineM } from "@/lib/geo";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

export default function PortalCasePage() {
  const { slug, caseId } = useParams<{ slug: string; caseId: string }>();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [detail, setDetail] = useState<PublicCaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [vehicles, setVehicles] = useState<VehicleItem[]>([]);
  const [context, setContext] = useState<{ streams: GeoFeature[]; cams: GeoFeature[] }>({ streams: [], cams: [] });

  const load = useCallback(() => {
    api.publicCase(slug, caseId).then(setDetail).catch((e) => setError((e as Error).message));
  }, [slug, caseId]);
  useEffect(() => {
    api.publicPlatform(slug).then(setPlatform).catch(() => undefined);
    load();
    const id = window.setInterval(load, 20000);
    return () => window.clearInterval(id);
  }, [slug, load]);

  // this case's dispatch route + vehicles, on the same map language as the portal
  useEffect(() => {
    const loadLive = () => {
      api.publicRoutes(slug).then((r) => setRoutes(r.features.filter((f) => f.properties.case_id === caseId))).catch(() => undefined);
      api.publicVehicles(slug).then((r) => setVehicles(r.items.filter((v) => v.case_id === caseId))).catch(() => undefined);
    };
    loadLive();
    const id = window.setInterval(loadLive, 4000);
    return () => window.clearInterval(id);
  }, [slug, caseId]);

  // official context around the case: debris-flow streams within 400 m, road CCTV within 6 km
  useEffect(() => {
    if (!platform || !detail) return;
    const c = detail.case;
    const near = (f: GeoFeature, maxM: number) => {
      const pts: number[][] = f.type === "Point" ? [f.coordinates] : f.type === "LineString" ? f.coordinates : f.type === "Polygon" ? f.coordinates[0] : [];
      let best = Infinity;
      for (const [lon, lat] of pts) best = Math.min(best, haversineM(c.lat, c.lon, lat, lon));
      return best <= maxM ? best : null;
    };
    if (platform.layers.includes("debris_flow")) {
      api.publicLayer(slug, "debris_flow").then((r) => setContext((x) => ({ ...x, streams: r.features.filter((f) => f.properties.kind === "stream" && near(f, 400) !== null) }))).catch(() => undefined);
    }
    if (platform.layers.includes("road_traffic")) {
      api
        .publicLayer(slug, "road_traffic")
        .then((r) => {
          const cams = r.features
            .filter((f) => f.properties.kind === "cctv")
            .map((f) => ({ f, d: near(f, 6000) }))
            .filter((x): x is { f: GeoFeature; d: number } => x.d !== null)
            .sort((a, b) => a.d - b.d)
            .slice(0, 2)
            .map((x) => ({ ...x.f, properties: { ...x.f.properties, distance_m: Math.round(x.d) } }));
          setContext((x) => ({ ...x, cams }));
        })
        .catch(() => undefined);
    }
  }, [platform, detail, slug]);

  const feature = useMemo<MapFeature[]>(() => {
    if (!detail) return [];
    const c = detail.case;
    return [
      {
        type: "Feature",
        id: `case:${c.id}`,
        geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        properties: { ...c, layer: "incident_cases", category_layer: CATEGORY_LAYER[c.category] || "other" },
      },
    ];
  }, [detail]);
  const mapVisible = useMemo(() => ({ incident_cases: true, dispatch: true, debris_flow: true, road_traffic: true }), []);
  const [ctxLayers, setCtxLayers] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!platform) return;
    for (const k of ["debris_flow", "road_traffic"]) {
      if (platform.layers.includes(k)) api.publicLayer(slug, k).then((r) => setCtxLayers((x) => ({ ...x, [k]: r }))).catch(() => undefined);
    }
  }, [platform, slug]);

  const compare = useMemo(() => {
    if (!detail) return null;
    const after = detail.photos.filter((p) => p.kind === "after").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    const before = detail.photos.filter((p) => p.kind === "before" || p.kind === "scene").sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
    return after && before ? { before: api.mediaUrl(before.url), after: api.mediaUrl(after.url), beforeLabel: before.kind === "before" ? "處理前" : "現場" } : null;
  }, [detail]);

  return (
    <PortalShell platform={platform} slug={slug}>
      <div className="mb-2">
        <BackLink href={`/p/${slug}/cases`} label="全部案件" />
      </div>
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {!detail ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          {/* header over the case's own terrain view */}
          <div className="af-panel mb-3 overflow-hidden">
            <div className="relative h-[260px] sm:h-[320px]">
              <TerrainMap center={[detail.case.lat, detail.case.lon]} zoom={13.6} features={feature} visible={mapVisible} enabledLayers={["incident_cases", "dispatch", "debris_flow", "road_traffic"]} officialLayers={ctxLayers} routes={routes} vehicles={vehicles} threeD orbit minimal />
              <div className="pointer-events-none absolute left-3 top-3 max-w-[calc(100%-24px)] sm:max-w-[520px]">
                <div className="af-hero-card pointer-events-auto p-3.5">
                  <div className="flex items-start gap-3">
                    <CategoryBadge category={detail.case.category} size={38} />
                    <div className="min-w-0">
                      <div className="font-mono text-[11px] text-[var(--muted)]">{detail.case.case_number}</div>
                      <h1 className="text-lg font-semibold leading-tight text-[var(--ink)] sm:text-xl">{detail.case.title}</h1>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--ink-2)]">
                        <StatusPill status={detail.case.status} phase={detail.case.phase} />
                        <SeverityTag severity={detail.case.severity} />
                        <span>{detail.case.unique_reporter_count} 人回報（{detail.case.report_count} 筆）</span>
                        <span>{detail.case.location_label || detail.case.town}</span>
                      </div>
                      {context.streams.length ? (
                        <div className="mt-2 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] font-medium" style={{ background: context.streams.some((s) => s.properties.alert === "red") ? "#fee2e2" : context.streams.some((s) => s.properties.alert) ? "#fef3c7" : "var(--surface-3)", color: context.streams.some((s) => s.properties.alert === "red") ? "#991b1b" : context.streams.some((s) => s.properties.alert) ? "#92400e" : "var(--ink-2)" }}>
                          <span className="h-1.5 w-1.5 rounded-full bg-current" />
                          {context.streams.some((s) => s.properties.alert) ? `位於土石流${context.streams.some((s) => s.properties.alert === "red") ? "紅色" : "黃色"}警戒溪流 400 m 內` : "鄰近土石流潛勢溪流"}：{context.streams.map((s) => s.properties.debris_no).slice(0, 2).join("、")}（水保署）
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
              <div className="pointer-events-none absolute bottom-2 right-3 text-[10.5px] text-[var(--ink-2)]">
                <span className="rounded bg-white/85 px-1.5 py-0.5">位置已粗化至約 100 公尺</span>
              </div>
            </div>
            <div className="p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--muted)]">
                <span>第一筆通報 {fmtTime(detail.timeline[0]?.at)} · 最近更新 {fmtAgo(detail.case.updated_at)}</span>
                {detail.case.assigned_unit ? <span className="font-medium text-[var(--ink-2)]">處理單位：{detail.case.assigned_unit}</span> : null}
              </div>
              <ProgressSteps steps={detail.progress} />
              {detail.case.public_summary ? (
                <div className="mt-4 rounded border-l-2 bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--ink-2)]" style={{ borderColor: "var(--st-active)" }}>
                  <span className="af-eyebrow mr-2">最新進度</span>
                  {detail.case.public_summary}
                </div>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-12">
            <section className="af-panel p-4 lg:col-span-7">
              <h2 className="af-h2 mb-3">處理時間軸</h2>
              <CaseTimeline items={detail.timeline} />
            </section>
            <div className="space-y-3 lg:col-span-5">
              {vehicles.length ? (
                <section className="af-panel p-3">
                  <h2 className="af-h2 mb-2">出勤車輛</h2>
                  <ul className="divide-y text-xs" style={{ borderColor: "var(--line)" }}>
                    {vehicles.map((v) => (
                      <li key={v.vehicle_id} className="flex items-center justify-between py-1.5">
                        <span className="text-[var(--ink-2)]">
                          <span className="font-medium text-[var(--ink)]">{VEHICLE_LABEL[v.kind] || v.kind_label}</span> · {v.unit_name}
                        </span>
                        <span className="text-[var(--muted)]">
                          {v.status === "en_route" && v.eta_minutes ? `約 ${v.eta_minutes} 分鐘抵達` : VEHICLE_STATUS_LABEL[v.status] || v.status}
                          {v.source === "simulated" ? "（模擬）" : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {context.cams.length ? (
                <section className="af-panel p-3">
                  <h2 className="af-h2 mb-2">附近路況監視器（交通部 TDX）</h2>
                  <div className="grid grid-cols-2 gap-2">
                    {context.cams.map((f) => (
                      <a key={f.id} href={f.properties.stream_url || f.properties.image_url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
                        {f.properties.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={f.properties.image_url} alt={f.properties.name} className="h-28 w-full object-cover" loading="lazy" />
                        ) : (
                          <div className="grid h-28 place-items-center text-[11px] text-[var(--muted)]">無靜態影像</div>
                        )}
                        <div className="truncate px-1.5 py-1 text-[10.5px] text-[var(--ink-2)]">
                          {f.properties.road} {f.properties.mile || ""} · 距案件 {(f.properties.distance_m / 1000).toFixed(1)} km
                        </div>
                      </a>
                    ))}
                  </div>
                </section>
              ) : null}
              {compare ? (
                <section className="af-panel p-3">
                  <h2 className="af-h2 mb-2">處理前後比對</h2>
                  <CompareSlider before={compare.before} after={compare.after} beforeLabel={compare.beforeLabel} />
                  <div className="mt-1 text-[10.5px] text-[var(--muted)]">拖曳中線比較；左為處理後、右為處理前。</div>
                </section>
              ) : null}
              <section className="af-panel p-3">
                <h2 className="af-h2 mb-2">現場照片</h2>
                <PhotoStrip photos={detail.photos} />
              </section>
              <section className="af-panel p-3">
                <h2 className="af-h2 mb-2">民眾回報（去識別化）</h2>
                <ul className="divide-y text-xs" style={{ borderColor: "var(--line)" }}>
                  {detail.reports.map((r, i) => (
                    <li key={r.report_id} className="py-2">
                      <div className="flex items-center justify-between text-[var(--muted)]">
                        <span>
                          第 {i + 1} 筆 · {ROLE_LABEL[r.reporter_role] || r.reporter_role}
                        </span>
                        <span className="font-mono">{fmtTime(r.created_at)}</span>
                      </div>
                      {r.description ? <p className="mt-0.5 text-[var(--ink-2)]">{r.description}</p> : <p className="mt-0.5 text-[var(--faint)]">（無文字描述）</p>}
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        </>
      )}
    </PortalShell>
  );
}
