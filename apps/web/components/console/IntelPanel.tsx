"use client";

// Command-centre intelligence board: the second-wave official data that is
// not a dot on the map — debris-flow alerts, reservoir state, road news,
// population-weighted townships, planned outages and the nearest road CCTV
// for the selected case. Every block names its source and its status; a
// missing key shows as "未設定", never as made-up data.

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { haversineM } from "@/lib/geo";
import type { CaseItem, GeoFeature, LayerResponse } from "@/lib/types";

const INTEL_LAYERS = ["debris_flow", "landslide_zone", "reservoir", "population", "road_traffic", "power_outage"] as const;
type IntelKey = (typeof INTEL_LAYERS)[number];

function useIntel(platformId: string, enabled: string[], active: boolean) {
  const [data, setData] = useState<Partial<Record<IntelKey, LayerResponse>>>({});
  useEffect(() => {
    if (!active) return; // these layers are megabytes: never fetch them for a tab nobody opened
    let alive = true;
    const load = () =>
      INTEL_LAYERS.filter((k) => enabled.includes(k)).forEach((k) =>
        api
          .consoleLayer(platformId, k)
          .then((r) => alive && setData((d) => ({ ...d, [k]: r })))
          .catch(() => undefined)
      );
    load();
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 120000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [platformId, enabled.join(","), active]); // eslint-disable-line react-hooks/exhaustive-deps
  return data;
}

function Status({ r, label }: { r: LayerResponse | undefined; label: string }) {
  if (!r) return <span className="text-[10.5px] text-[var(--faint)]">載入中…</span>;
  if (r.status === "ok") return <span className="text-[10.5px] text-[var(--faint)]">{label} · {r.count} 筆 · {fmtTime(r.fetched_at)}</span>;
  return <span className="text-[10.5px] text-[var(--sev-medium)]">{r.status === "disabled" ? "未設定金鑰" : "暫時無法取得"}{r.detail ? `：${r.detail}` : ""}</span>;
}

function Block({ title, status, children }: { title: string; status: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="af-subtle p-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--ink)]">{title}</h3>
        {status}
      </div>
      {children}
    </section>
  );
}

const ALERT_HEX: Record<string, string> = { red: "#dc2626", yellow: "#f59e0b" };

export default function IntelPanel({ platformId, enabledLayers, cases, selectedCase, active = true }: { platformId: string; enabledLayers: string[]; cases: CaseItem[]; selectedCase?: CaseItem | null; active?: boolean }) {
  const data = useIntel(platformId, enabledLayers, active);
  const feats = (k: IntelKey): GeoFeature[] => data[k]?.features || [];

  const alerts = useMemo(() => feats("debris_flow").filter((f) => f.properties.alert).concat(feats("landslide_zone").filter((f) => f.properties.alert)), [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const streams = feats("debris_flow").filter((f) => f.properties.kind === "stream");
  const reservoirs = feats("reservoir");
  const towns = feats("population");
  const news = feats("road_traffic").filter((f) => f.properties.kind === "news");
  const cctv = feats("road_traffic").filter((f) => f.properties.kind === "cctv");
  const outages = feats("power_outage");

  // population-weighted load: open cases per 10k residents per township
  const perTown = useMemo(() => {
    const open = cases.filter((c) => c.phase !== "done");
    return towns
      .map((t) => {
        const n = open.filter((c) => c.town === t.properties.town).length;
        const pop = Number(t.properties.population) || 0;
        return { town: t.properties.town as string, pop, n, rate: pop ? (n / pop) * 10000 : 0 };
      })
      .sort((a, b) => b.rate - a.rate || b.n - a.n);
  }, [towns, cases]);
  const maxRate = Math.max(0.001, ...perTown.map((t) => t.rate));

  // nearest cameras to the selected case
  const nearCams = useMemo(() => {
    if (!selectedCase) return [];
    return cctv
      .map((f) => ({ f, d: haversineM(selectedCase.lat, selectedCase.lon, f.coordinates[1], f.coordinates[0]) }))
      .filter((x) => x.d < 8000)
      .sort((a, b) => a.d - b.d)
      .slice(0, 3);
  }, [cctv, selectedCase]);

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Block title="土石流／大規模崩塌警戒" status={<Status r={data.debris_flow} label="農村發展及水土保持署" />}>
        {alerts.length ? (
          <ul className="space-y-1.5">
            {alerts.map((f) => (
              <li key={f.id} className="flex items-start gap-2 text-xs">
                <span className="mt-0.5 inline-block h-3 w-3 flex-none rounded-sm" style={{ background: ALERT_HEX[f.properties.alert] }} />
                <span className="min-w-0">
                  <span className="font-medium text-[var(--ink)]">{f.properties.alert === "red" ? "紅色警戒" : "黃色警戒"}</span> {f.properties.town}
                  {f.properties.vill} · {f.properties.name}
                  {f.properties.road ? ` · ${f.properties.road}` : ""}
                  <span className="block text-[10.5px] text-[var(--muted)]">{f.properties.debris_no || f.properties.zone_no} · 保全 {f.properties.households_class || "—"} · {f.properties.alert_time}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-[var(--muted)]">
            目前本縣沒有發布中的土石流警戒。潛勢溪流 {streams.length} 條（高風險 {streams.filter((s) => s.properties.risk === "高").length} 條）持續監看。
          </div>
        )}
      </Block>

      <Block title="水庫水情" status={<Status r={data.reservoir} label="水利署" />}>
        {reservoirs.length ? (
          <ul className="space-y-2">
            {reservoirs.map((f) => {
              const p = f.properties;
              const pct = Number(p.storage_pct);
              const color = p.status === "releasing" ? "#b91c1c" : p.status === "high" ? "#d97706" : p.status === "low" ? "#64748b" : "#0e7490";
              return (
                <li key={f.id} className="text-xs">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium text-[var(--ink)]">
                      {p.name} <span className="text-[var(--muted)]">{p.town}</span>
                    </span>
                    <span style={{ color }} className="font-medium">
                      {p.status === "releasing" ? `洩洪中 ${p.spillway_cms} cms` : p.status === "high" ? "接近滿水位" : p.status === "low" ? "蓄水偏低" : "正常"}
                    </span>
                  </div>
                  <div className="mt-1 flex h-2 overflow-hidden rounded-full bg-[var(--surface-3)]">
                    <span style={{ width: `${Math.min(100, Number.isFinite(pct) ? pct : 0)}%`, background: color }} />
                  </div>
                  <div className="mt-0.5 flex justify-between text-[10.5px] text-[var(--muted)]">
                    <span>蓄水率 {Number.isFinite(pct) ? `${pct}%` : "—"} · 水位 {p.water_level_m ?? "—"} m</span>
                    <span>
                      {p.inflow_cms != null ? `入 ${p.inflow_cms} ` : ""}
                      {p.outflow_cms != null ? `出 ${p.outflow_cms} cms · ` : ""}
                      {fmtTime(p.observed_at)}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="text-xs text-[var(--muted)]">本縣無水利署列管水庫資料。</div>
        )}
      </Block>

      <Block title="人口加權負荷（每萬人進行中案件）" status={<Status r={data.population} label={`戶政司 ${towns[0]?.properties.statistic_month ? `民國 ${towns[0].properties.statistic_month.slice(0, 3)} 年 ${towns[0].properties.statistic_month.slice(3)} 月` : ""}`} />}>
        {perTown.length ? (
          <ul className="space-y-1">
            {perTown.slice(0, 8).map((t) => (
              <li key={t.town} className="flex items-center gap-2 text-xs">
                <span className="w-14 flex-none text-[var(--ink-2)]">{t.town}</span>
                <span className="flex h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
                  <span style={{ width: `${(t.rate / maxRate) * 100}%`, background: t.n ? "var(--st-pending)" : "transparent" }} />
                </span>
                <span className="w-24 flex-none text-right tabular-nums text-[var(--muted)]">
                  {t.n} 件 / {(t.pop / 10000).toFixed(1)} 萬人
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-[var(--muted)]">尚無人口資料。</div>
        )}
      </Block>

      <Block title="路況消息與 CCTV" status={<Status r={data.road_traffic} label="交通部 TDX" />}>
        {data.road_traffic?.status === "ok" ? (
          <>
            {selectedCase ? (
              <div className="mb-2">
                <div className="af-eyebrow mb-1">距 {selectedCase.title} 最近的監視器</div>
                {nearCams.length ? (
                  <div className="grid grid-cols-3 gap-1.5">
                    {nearCams.map(({ f, d }) => (
                      <a key={f.id} href={f.properties.stream_url || f.properties.image_url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded border" style={{ borderColor: "var(--line)" }}>
                        {f.properties.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={`${f.properties.image_url}${f.properties.image_url.includes("?") ? "&" : "?"}t=${Math.floor(Date.now() / 60000)}`} alt={f.properties.name} className="h-20 w-full object-cover" loading="lazy" />
                        ) : (
                          <div className="grid h-20 place-items-center text-[10px] text-[var(--muted)]">無靜態影像</div>
                        )}
                        <div className="truncate px-1 py-0.5 text-[10px] text-[var(--ink-2)]">
                          {f.properties.road} {f.properties.mile || ""} · {(d / 1000).toFixed(1)} km
                        </div>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="text-[11px] text-[var(--muted)]">8 公里內沒有路況監視器。</div>
                )}
              </div>
            ) : null}
            {news.length ? (
              <ul className="space-y-1.5">
                {news.slice(0, 8).map((f) => (
                  <li key={f.id} className="text-xs">
                    <span className="mr-1.5 inline-block rounded px-1 text-[10px] font-medium" style={{ background: f.properties.status === "closure" ? "#fee2e2" : "var(--surface-3)", color: f.properties.status === "closure" ? "#991b1b" : "var(--ink-2)" }}>
                      {f.properties.status === "closure" ? "封閉／中斷" : "路況"}
                    </span>
                    <span className="text-[var(--ink)]">{f.properties.headline}</span>
                    <span className="block text-[10.5px] text-[var(--muted)]">{fmtTime(f.properties.published_at)} · {f.properties.authority === "highway" ? "公路局" : "縣市"}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-[var(--muted)]">目前沒有本縣的路況消息；CCTV {cctv.length} 支。</div>
            )}
          </>
        ) : (
          <div className="text-xs text-[var(--muted)]">設定 TDX_CLIENT_ID / TDX_CLIENT_SECRET 後，這裡會顯示本縣封閉／坍方路況與案件附近的監視器畫面。</div>
        )}
      </Block>

      <Block title="計畫性停電公告" status={<Status r={data.power_outage} label="台電" />}>
        {outages.length ? (
          <ul className="space-y-1 text-xs">
            {outages.map((f) => (
              <li key={f.id}>
                <span className="font-medium text-[var(--ink)]">{f.properties.town}</span> {f.properties.count} 件
                <span className="block truncate text-[10.5px] text-[var(--muted)]">{(f.properties.items || []).slice(0, 2).map((i: any) => `${i.when} ${i.area}`).join("；")}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-[var(--muted)]">本縣近日沒有計畫性停電。台電未開放事故停電即時資料。</div>
        )}
      </Block>
    </div>
  );
}
