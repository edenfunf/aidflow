"use client";

// A case as the public sees it: where it is, how far along it is (EMIC
// progress or community handling), the timeline and photos — and, for a small
// case opened to the community, the 「我來協助處理」 form.

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PortalShell from "@/components/PortalShell";
import CaseTimeline, { ProgressSteps } from "@/components/CaseTimeline";
import CompareSlider from "@/components/CompareSlider";
import PhotoStrip from "@/components/PhotoStrip";
import { BackLink, ErrorBox, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { CategoryBadge } from "@/lib/categoryIcons";
import { fmtAgo, fmtTime } from "@/lib/format";
import { CATEGORY_LAYER, ROLE_LABEL } from "@/lib/labels";
import type { GeoFeature, MapFeature, PublicCaseDetail, PublicPlatform } from "@/lib/types";
import { haversineM } from "@/lib/geo";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

function AssistForm({ slug, caseId, onDone }: { slug: string; caseId: string; onDone: (message: string) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [helper, setHelper] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const previews = useMemo(() => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })), [files]);
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.submitCommunityReport(slug, caseId, { files, note: note.trim() || undefined, helper_name: helper.trim() || undefined });
      onDone(res.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-md border-2 p-4" style={{ borderColor: "var(--st-community)" }}>
      <h3 className="text-[19px] font-semibold text-[var(--ink)]">回報已協助處理完成</h3>
      <p className="mt-1 text-[15px] text-[var(--ink-2)]">請上傳「處理完成後」的現場照片（至少 1 張），承辦人員確認後會結案並自地圖撤除。不需要登入。</p>
      <p className="mt-1 text-[14px] text-[var(--sev-high)]">請注意自身安全；有危險時請勿自行處理，危及生命請撥 119。</p>
      {error ? (
        <div className="mt-3">
          <ErrorBox message={error} />
        </div>
      ) : null}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" multiple className="hidden" onChange={(e) => setFiles([...files, ...Array.from(e.target.files || [])].slice(0, 3))} />
      <div className="mt-3 flex flex-wrap gap-2.5">
        {previews.map((p, i) => (
          <div key={p.url} className="relative h-24 w-24 overflow-hidden rounded-md border" style={{ borderColor: "var(--line)" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
            <button type="button" className="absolute right-1 top-1 rounded bg-black/60 px-1.5 text-[13px] text-white" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label="移除照片">
              ✕
            </button>
          </div>
        ))}
        {files.length < 3 ? (
          <button type="button" className="flex h-24 w-24 flex-col items-center justify-center rounded-md border border-dashed text-[15px] text-[var(--muted)]" style={{ borderColor: "var(--line-2)" }} onClick={() => input.current?.click()}>
            <span className="text-2xl leading-none">＋</span>
            處理後照片
          </button>
        ) : null}
      </div>
      <label className="mt-3 block">
        <span className="af-label">處理說明（選填）</span>
        <textarea className="af-input mt-1" placeholder="例如：已清除排水孔落葉，路面積水已退" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
      </label>
      <label className="mt-2 block">
        <span className="af-label">您的稱呼（選填，不公開）</span>
        <input className="af-input mt-1" value={helper} onChange={(e) => setHelper(e.target.value)} maxLength={60} />
      </label>
      <button type="button" className="af-btn af-btn-lg mt-4 w-full font-bold text-white disabled:opacity-60" style={{ background: "var(--st-community)" }} disabled={busy || files.length === 0} onClick={submit}>
        {busy ? (
          <>
            <span className="af-spinner" /> 上傳中…
          </>
        ) : files.length === 0 ? (
          "請先加入處理完成照片"
        ) : (
          "送出處理完成回報"
        )}
      </button>
    </div>
  );
}

export default function PortalCasePage() {
  const { slug, caseId } = useParams<{ slug: string; caseId: string }>();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [detail, setDetail] = useState<PublicCaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [context, setContext] = useState<{ streams: GeoFeature[]; cams: GeoFeature[] }>({ streams: [], cams: [] });
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistDone, setAssistDone] = useState<string | null>(null);

  const load = useCallback(() => {
    api.publicCase(slug, caseId).then(setDetail).catch((e) => setError((e as Error).message));
  }, [slug, caseId]);
  useEffect(() => {
    api.publicPlatform(slug).then(setPlatform).catch(() => undefined);
    load();
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, 20000);
    return () => window.clearInterval(id);
  }, [slug, load]);
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#assist") setAssistOpen(true);
  }, []);

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
  const mapVisible = useMemo(() => ({ incident_cases: true, debris_flow: true }), []);
  const [ctxLayers, setCtxLayers] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!platform) return;
    if (platform.layers.includes("debris_flow")) api.publicLayer(slug, "debris_flow").then((r) => setCtxLayers((x) => ({ ...x, debris_flow: r }))).catch(() => undefined);
  }, [platform, slug]);

  const compare = useMemo(() => {
    if (!detail) return null;
    const after = detail.photos.filter((p) => p.kind === "after").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    const before = detail.photos.filter((p) => p.kind === "before" || p.kind === "scene").sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
    return after && before ? { before: api.mediaUrl(before.url), after: api.mediaUrl(after.url), beforeLabel: before.kind === "before" ? "處理前" : "現場" } : null;
  }, [detail]);

  const c = detail?.case;
  return (
    <PortalShell platform={platform} slug={slug}>
      <div className="mb-2">
        <BackLink href={`/p/${slug}/cases`} label="全部處理進度" />
      </div>
      {error ? <ErrorBox message={error} onRetry={load} /> : null}
      {!detail || !c ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          <div className="af-panel mb-3 overflow-hidden">
            <div className="relative h-[180px] sm:h-[300px]">
              <TerrainMap center={[c.lat, c.lon]} zoom={13.6} features={feature} visible={mapVisible} enabledLayers={["incident_cases", "debris_flow"]} officialLayers={ctxLayers} threeD minimal />
              <div className="pointer-events-none absolute bottom-2 right-3 text-[13px] text-[var(--ink-2)]">
                <span className="rounded bg-white/85 px-1.5 py-0.5">位置已粗化至約 100 公尺</span>
              </div>
            </div>
            <div className="p-4 sm:p-5">
              <div className="flex items-start gap-3">
                <CategoryBadge category={c.category} size={48} />
                <div className="min-w-0">
                  <div className="font-mono text-[14px] text-[var(--muted)]">{c.case_number}</div>
                  <h1 className="text-[24px] font-bold leading-tight text-[var(--ink)] sm:text-[28px]">{c.title}</h1>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[15px] text-[var(--ink-2)]">
                    <StatusPill status={c.status} phase={c.phase} />
                    <SeverityTag severity={c.severity} />
                    <span>{c.unique_reporter_count} 人回報（{c.report_count} 筆）</span>
                    <span>{c.location_label || c.town}</span>
                  </div>
                </div>
              </div>
              {context.streams.length ? (
                <div className="mt-3 inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[14px] font-medium" style={{ background: context.streams.some((s) => s.properties.alert === "red") ? "#fee2e2" : context.streams.some((s) => s.properties.alert) ? "#fef3c7" : "var(--surface-3)", color: context.streams.some((s) => s.properties.alert === "red") ? "#991b1b" : context.streams.some((s) => s.properties.alert) ? "#92400e" : "var(--ink-2)" }}>
                  <span className="h-2 w-2 rounded-full bg-current" />
                  {context.streams.some((s) => s.properties.alert) ? `位於土石流${context.streams.some((s) => s.properties.alert === "red") ? "紅色" : "黃色"}警戒溪流 400 m 內` : "鄰近土石流潛勢溪流"}：{context.streams.map((s) => s.properties.debris_no).slice(0, 2).join("、")}（水保署）
                </div>
              ) : null}

              <div className="mt-5">
                <ProgressSteps steps={detail.progress} />
              </div>

              {/* what the progress means, in words */}
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                {c.track === "emic" || c.status === "reported_emic" || c.status === "emic_processing" ? (
                  <div className="af-subtle p-3 text-[15px] text-[var(--ink-2)]">
                    <div className="text-[13px] tracking-[0.08em] text-[var(--muted)]">處理方式</div>
                    <div className="mt-0.5 font-semibold text-[var(--ink)]">已上報內政部消防署 EMIC，由權責單位處理</div>
                    {c.emic_status ? <div className="mt-1">EMIC 處理狀態：<b>{c.emic_status}</b></div> : null}
                    {c.assigned_unit ? <div className="mt-0.5">處理單位：{c.assigned_unit}</div> : null}
                  </div>
                ) : null}
                {c.track === "community" ? (
                  <div className="af-subtle p-3 text-[15px] text-[var(--ink-2)]">
                    <div className="text-[13px] tracking-[0.08em] text-[var(--muted)]">處理方式</div>
                    <div className="mt-0.5 font-semibold text-[var(--ink)]">經審核為小型災情，開放民眾協助處理</div>
                    {c.status === "community_submitted" ? <div className="mt-1">已有民眾回報處理完成，等待承辦人員確認照片。</div> : null}
                  </div>
                ) : null}
                {c.status === "pending_review" ? (
                  <div className="af-subtle p-3 text-[15px] text-[var(--ink-2)]">
                    <div className="font-semibold text-[var(--ink)]">縣府承辦人員審核中</div>
                    <div className="mt-0.5">審核後會決定上報 EMIC 由權責單位處理，或開放民眾協助處理。</div>
                  </div>
                ) : null}
                {c.status === "closed" ? (
                  <div className="af-subtle p-3 text-[15px] text-[var(--ink-2)]">
                    <div className="font-semibold" style={{ color: "var(--st-done)" }}>此災情已處理完成並結案</div>
                    <div className="mt-0.5">已自災情地圖撤除。{c.closed_at ? `結案時間 ${fmtTime(c.closed_at)}` : ""}</div>
                  </div>
                ) : null}
              </div>

              {c.public_summary ? (
                <div className="mt-4 rounded border-l-4 bg-[var(--surface-2)] px-3 py-2.5 text-[16px] text-[var(--ink-2)]" style={{ borderColor: "var(--st-active)" }}>
                  <span className="af-eyebrow mr-2">最新進度</span>
                  {c.public_summary}
                </div>
              ) : null}

              {detail.can_assist && !assistDone && !assistOpen ? (
                <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-[var(--bg)]/95 px-3 py-3 backdrop-blur sm:hidden" style={{ borderColor: "var(--line)" }}>
                  <button
                    type="button"
                    className="af-btn af-btn-lg w-full !py-4 !text-[19px] font-bold text-white"
                    style={{ background: "var(--st-community)" }}
                    onClick={() => {
                      setAssistOpen(true);
                      requestAnimationFrame(() => document.getElementById("assist")?.scrollIntoView({ behavior: "smooth", block: "center" }));
                    }}
                  >
                    我來協助處理
                  </button>
                </div>
              ) : null}

              {detail.can_assist && !assistDone ? (
                <div id="assist" className={`mt-5 ${assistOpen ? "" : "hidden sm:block"}`}>
                  {!assistOpen ? (
                    <button type="button" className="af-btn af-btn-lg w-full !py-4 !text-[20px] font-bold text-white" style={{ background: "var(--st-community)" }} onClick={() => setAssistOpen(true)}>
                      我來協助處理
                    </button>
                  ) : (
                    <AssistForm
                      slug={slug}
                      caseId={caseId}
                      onDone={(m) => {
                        setAssistDone(m);
                        load();
                      }}
                    />
                  )}
                </div>
              ) : null}
              {assistDone ? (
                <div className="mt-5 rounded-md border p-4 text-[17px] font-medium" style={{ borderColor: "var(--st-done)", color: "var(--st-done)", background: "#ecfdf3" }}>
                  {assistDone}
                </div>
              ) : null}

              <div className="mt-4 text-[14px] text-[var(--muted)]">
                第一筆通報 {fmtTime(detail.timeline[0]?.at)} · 最近更新 {fmtAgo(c.updated_at)}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-12">
            <section className="af-panel p-4 lg:col-span-7">
              <h2 className="af-h2 mb-3">處理時間軸</h2>
              <CaseTimeline items={detail.timeline} />
            </section>
            <div className="space-y-3 lg:col-span-5">
              {compare ? (
                <section className="af-panel p-3">
                  <h2 className="af-h2 mb-2">處理前後比對</h2>
                  <CompareSlider before={compare.before} after={compare.after} beforeLabel={compare.beforeLabel} />
                  <div className="mt-1 text-[13px] text-[var(--muted)]">拖曳中線比較；左為處理後、右為處理前。</div>
                </section>
              ) : null}
              <section className="af-panel p-3">
                <h2 className="af-h2 mb-2">現場照片</h2>
                <PhotoStrip photos={detail.photos} />
              </section>
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
                          <div className="grid h-28 place-items-center text-[13px] text-[var(--muted)]">無靜態影像</div>
                        )}
                        <div className="truncate px-1.5 py-1 text-[13px] text-[var(--ink-2)]">
                          {f.properties.road} {f.properties.mile || ""} · 距案件 {(f.properties.distance_m / 1000).toFixed(1)} km
                        </div>
                      </a>
                    ))}
                  </div>
                </section>
              ) : null}
              <section className="af-panel p-3">
                <h2 className="af-h2 mb-2">民眾回報（去識別化）</h2>
                <ul className="divide-y text-[15px]" style={{ borderColor: "var(--line)" }}>
                  {detail.reports.map((r, i) => (
                    <li key={r.report_id} className="py-2">
                      <div className="flex items-center justify-between text-[13px] text-[var(--muted)]">
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
          {/* room for the docked 我來協助處理 bar on phones */}
          {detail.can_assist && !assistDone && !assistOpen ? <div className="h-24 sm:hidden" /> : null}
        </>
      )}
    </PortalShell>
  );
}
