"use client";

// Case workbench. The main panel changes with the case's stage:
//   待審核            → the 審核點: 上報 EMIC／民間可處理／不成案
//   已上報 EMIC／處理中 → record the EMIC case number, status and unit; close
//   民眾協助           → watch, escalate, or confirm the citizen's photos
// Actions are offered only to roles that may take them (the API enforces it).

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import CaseTimeline, { ProgressSteps } from "@/components/CaseTimeline";
import PhotoStrip from "@/components/PhotoStrip";
import { ErrorBox, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { fmtMeters, fmtTime } from "@/lib/format";
import { CATEGORY_LABEL, CATEGORY_LAYER, CONSOLE_STATUS_LABEL, ROLE_LABEL, SEVERITY_HEX } from "@/lib/labels";
import type { CaseDetail, MapFeature, ProgressStep, PublicTimelineItem, ReviewDecision } from "@/lib/types";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const DECISIONS: { key: ReviewDecision; title: string; detail: string; color: string }[] = [
  { key: "emic", title: "上報 EMIC", detail: "需權責單位處理的災情：列入 EMIC 上報，後續依 EMIC 狀態追蹤。", color: "#1d4ed8" },
  { key: "community", title: "民間可處理", detail: "小型災情（如倒木、排水孔堵塞）：開放民眾協助，民眾上傳處理後照片再由您確認。", color: "#0e7490" },
  { key: "dismiss", title: "不成案", detail: "誤報、重複或不需處理：不公開於地圖，保留紀錄。", color: "#667085" },
];

function Panel({ title, children, accent }: { title: string; children: React.ReactNode; accent?: string }) {
  return (
    <section className="af-panel overflow-hidden">
      <div className="border-b px-4 py-3" style={{ borderColor: "var(--line)", borderTop: accent ? `4px solid ${accent}` : undefined }}>
        <h2 className="text-[19px] font-semibold text-[var(--ink)]">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export default function CaseWorkbenchPage() {
  const { id, caseId } = useParams<{ id: string; caseId: string }>();
  const { can } = useMe();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [emicNo, setEmicNo] = useState("");
  const [emicStatus, setEmicStatus] = useState("");
  const [emicUnit, setEmicUnit] = useState("");
  const [emicNote, setEmicNote] = useState("");
  const [confirmNote, setConfirmNote] = useState("");
  const [note, setNote] = useState("");
  const [notePublic, setNotePublic] = useState(true);
  const [photoKind, setPhotoKind] = useState<"before" | "scene" | "after">("after");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const hydrated = useRef(false);

  const load = useCallback(() => {
    api
      .getCase(caseId)
      .then((d) => {
        setDetail(d);
        if (!hydrated.current) {
          setEmicNo(d.case.emic_case_no || "");
          setEmicStatus(d.case.emic_status || "");
          setEmicUnit(d.case.assigned_unit || "");
          hydrated.current = true;
        }
      })
      .catch((e) => setError((e as Error).message));
  }, [caseId]);
  useEffect(() => {
    load();
    const t = window.setInterval(() => {
      if (!document.hidden) load();
    }, 15000);
    return () => window.clearInterval(t);
  }, [load]);

  const run = async (key: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      const r = await fn();
      const detailMsg = (r as { result?: { detail?: string | null } } | undefined)?.result?.detail;
      setNotice(detailMsg || done || null);
      hydrated.current = false;
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const features = useMemo<MapFeature[]>(() => {
    if (!detail) return [];
    const c = detail.case;
    const main: MapFeature = {
      type: "Feature",
      id: `case:${c.id}`,
      geometry: { type: "Point", coordinates: [c.lon, c.lat] },
      properties: { ...c, layer: "incident_cases", category_layer: CATEGORY_LAYER[c.category] || "other" },
    };
    const reps: MapFeature[] = detail.reports
      .filter((r) => r.lat != null && r.lon != null)
      .map((r) => ({
        type: "Feature",
        id: `report:${r.id}`,
        geometry: { type: "Point", coordinates: [r.lon as number, r.lat as number] },
        properties: { layer: "citizen_reports", category_layer: CATEGORY_LAYER[r.category] || "other", category: r.category, description: r.description, address: r.address, created_at: r.created_at, report_id: r.id, photo_count: r.photo_count },
      }));
    return [main, ...reps];
  }, [detail]);
  const mapVisible = useMemo(() => ({ incident_cases: true, citizen_reports: true }), []);

  const timelineItems = useMemo<PublicTimelineItem[]>(
    () =>
      (detail?.events || []).map((e) => ({
        event_type: e.event_type,
        label: e.label,
        note: [e.note, e.actor_name ? `— ${e.actor_name}` : "", e.public ? "" : "（內部）"].filter(Boolean).join(" "),
        to_status: (e.to_status as PublicTimelineItem["to_status"]) || null,
        at: e.created_at,
      })),
    [detail]
  );

  const progress = useMemo<ProgressStep[]>(() => {
    if (!detail) return [];
    const c = detail.case;
    const path: ProgressStep["key"][] =
      c.status === "dismissed" ? ["pending_review", "dismissed"] : c.track === "community" ? ["pending_review", "community_open", "community_submitted", "closed"] : c.track === "emic" ? ["pending_review", "reported_emic", "emic_processing", "closed"] : ["pending_review", "closed"];
    const reached: Record<string, string> = {};
    for (const e of detail.events) if (e.to_status && !reached[e.to_status]) reached[e.to_status] = e.created_at;
    const cur = path.indexOf(c.status);
    return path.map((k, i) => ({ key: k, label: CONSOLE_STATUS_LABEL[k], reached: Boolean(reached[k]) || (cur >= 0 && i <= cur), current: cur === i, at: reached[k] || null }));
  }, [detail]);

  if (!detail) {
    return (
      <ConsoleShell crumbs={[{ href: "/console", label: "災害平台" }, { href: `/console/platforms/${id}`, label: "平台後台" }, { label: "案件" }]}>
        {error ? <ErrorBox message={error} onRetry={load} /> : <Skeleton className="h-80" />}
      </ConsoleShell>
    );
  }
  const c = detail.case;
  const officer = can("review_cases");
  const citizenPhotos = detail.photos.filter((p) => p.source === "citizen" && p.kind === "after");
  const isEmic = c.status === "reported_emic" || c.status === "emic_processing";

  return (
    <ConsoleShell wide crumbs={[{ href: "/console", label: "災害平台" }, { href: `/console/platforms/${id}`, label: "平台後台" }, { label: c.case_number }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} />
        </div>
      ) : null}
      {notice ? <div className="mb-3 rounded-md border px-4 py-3 text-[16px]" style={{ borderColor: "#b2ddff", background: "#eff8ff", color: "#175cd3" }}>{notice}</div> : null}

      <div className="af-panel relative mb-4 overflow-hidden p-5">
        <span className="absolute inset-y-0 left-0 w-2" style={{ background: SEVERITY_HEX[c.severity] }} />
        <div className="flex flex-wrap items-start justify-between gap-3 pl-2">
          <div>
            <div className="font-mono text-[14px] text-[var(--muted)]">{c.case_number}</div>
            <h1 className="text-[28px] font-bold text-[var(--ink)]">{c.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[15px] text-[var(--ink-2)]">
              <StatusPill status={c.status} phase={c.phase} console />
              <SeverityTag severity={c.severity} />
              {c.track_label ? <span className="af-chip">{c.track_label}</span> : null}
              <span>{c.unique_reporter_count} 人回報（{c.report_count} 筆）</span>
              <span>
                {c.town} · {c.location_label}
              </span>
              <span className="font-mono text-[var(--muted)]">
                {c.lat.toFixed(5)}, {c.lon.toFixed(5)}
              </span>
            </div>
          </div>
          <div className="text-right text-[14px] text-[var(--muted)]">
            <div>成案 {fmtTime(c.created_at)}</div>
            {c.reviewed_at ? <div>審核 {fmtTime(c.reviewed_at)}{c.reviewed_by ? `（${c.reviewed_by}）` : ""}</div> : null}
            {c.closed_at ? <div>結案 {fmtTime(c.closed_at)}</div> : null}
          </div>
        </div>
        <div className="mt-5 pl-2">
          <ProgressSteps steps={progress} />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        <div className="min-w-0 space-y-4 xl:col-span-5">
          {/* ── 審核點 ── */}
          {c.status === "pending_review" ? (
            <Panel title="審核：這件災情要怎麼處理？" accent="var(--st-pending)">
              {officer ? (
                <>
                  <p className="text-[15px] text-[var(--ink-2)]">請先檢視右側的民眾回報與照片，再決定處理方式。決定後才會進入案件佇列，並通知訂閱進度的民眾。</p>
                  <textarea className="af-input mt-3" placeholder="審核說明（選填，公開於處理時間軸）" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} maxLength={500} />
                  <div className="mt-3 grid gap-2.5">
                    {DECISIONS.map((d) => (
                      <button
                        key={d.key}
                        type="button"
                        disabled={Boolean(busy)}
                        className="flex w-full items-start gap-3 rounded-md border-2 p-3.5 text-left transition hover:shadow-md disabled:opacity-60"
                        style={{ borderColor: d.color }}
                        onClick={() => {
                          if (d.key === "dismiss" && !window.confirm("確定判定為不成案？")) return;
                          run(`review-${d.key}`, () => api.reviewCase(c.id, { decision: d.key, note: reviewNote.trim() || undefined }), d.key === "community" ? "已開放民眾協助處理。" : d.key === "dismiss" ? "已判定不成案。" : undefined);
                        }}
                      >
                        <span className="mt-0.5 h-5 w-5 flex-none rounded-full border-[3px]" style={{ borderColor: d.color }} />
                        <span>
                          <span className="block text-[19px] font-bold" style={{ color: d.color }}>
                            {busy === `review-${d.key}` ? "處理中…" : d.title}
                          </span>
                          <span className="mt-0.5 block text-[14px] text-[var(--ink-2)]">{d.detail}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-[15px] text-[var(--muted)]">此案件等待承辦審核人員決定處理方式。您的角色可檢視，無審核權限。</p>
              )}
            </Panel>
          ) : null}

          {/* ── EMIC ── */}
          {isEmic ? (
            <Panel title="EMIC 上報與處理進度" accent="var(--st-active)">
              <div className="rounded-md bg-[var(--surface-2)] px-3 py-2.5 text-[14px] text-[var(--ink-2)]">
                {detail.emic.mode === "api" ? (
                  c.emic_channel === "api" ? "已透過介接端點送出至 EMIC。" : "自動上報未成功，請於 EMIC 建立案件後回填案號。"
                ) : (
                  <>
                    <b>人工登錄模式</b>：EMIC 介接規格尚未提供。請於 EMIC 建立案件，再將 EMIC 案號、處理狀態與處理單位回填於此；處理狀態與單位會公開顯示，EMIC 案號僅內部可見。
                  </>
                )}
              </div>
              {officer ? (
                <>
                  <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
                    <label>
                      <span className="af-label">EMIC 案號（內部）</span>
                      <input className="af-input mt-1 font-mono" value={emicNo} onChange={(e) => setEmicNo(e.target.value)} maxLength={60} placeholder="例如 EMIC-1150903-0012" />
                    </label>
                    <label>
                      <span className="af-label">EMIC 處理狀態（公開）</span>
                      <input className="af-input mt-1" list="emic-status" value={emicStatus} onChange={(e) => setEmicStatus(e.target.value)} maxLength={60} />
                      <datalist id="emic-status">
                        {detail.emic.status_suggestions.map((s) => (
                          <option key={s} value={s} />
                        ))}
                      </datalist>
                    </label>
                    <label className="sm:col-span-2">
                      <span className="af-label">處理單位（公開）</span>
                      <input className="af-input mt-1" value={emicUnit} onChange={(e) => setEmicUnit(e.target.value)} maxLength={100} placeholder="例如 公路局中區養護工程分局埔里工務段" />
                    </label>
                    <label className="sm:col-span-2">
                      <span className="af-label">公開處理進度（選填）</span>
                      <input className="af-input mt-1" value={emicNote} onChange={(e) => setEmicNote(e.target.value)} maxLength={1000} placeholder="例如 重機具進場清除土石，預計 2 小時後單線通行" />
                    </label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" className="af-btn af-btn-secondary af-btn-lg" disabled={Boolean(busy)} onClick={() => run("emic-save", async () => { const r = await api.updateEmic(c.id, { emic_case_no: emicNo, emic_status: emicStatus, assigned_unit: emicUnit, note: emicNote.trim() || undefined }); setEmicNote(""); return r; }, "已更新 EMIC 資訊。")}>
                      儲存
                    </button>
                    {c.status === "reported_emic" ? (
                      <button type="button" className="af-btn af-btn-primary af-btn-lg" disabled={Boolean(busy)} onClick={() => run("emic-processing", () => api.updateEmic(c.id, { emic_case_no: emicNo, emic_status: emicStatus, assigned_unit: emicUnit, note: emicNote.trim() || undefined, status: "emic_processing" }), "已改為處理中。")}>
                        儲存並改為處理中
                      </button>
                    ) : null}
                    <button type="button" className="af-btn af-btn-lg font-bold text-white" style={{ background: "var(--st-done)" }} disabled={Boolean(busy)} onClick={() => window.confirm("確認此案件已處理完成並結案？結案後會自民眾地圖撤除。") && run("emic-close", () => api.updateEmic(c.id, { emic_case_no: emicNo, emic_status: emicStatus || "已處理完成", assigned_unit: emicUnit, note: emicNote.trim() || undefined, status: "closed" }), "已結案並自地圖撤除。")}>
                      處理完成・結案
                    </button>
                  </div>
                </>
              ) : (
                <dl className="mt-3 grid grid-cols-[7rem_1fr] gap-y-1.5 text-[15px]">
                  <dt className="text-[var(--muted)]">EMIC 案號</dt>
                  <dd className="font-mono">{c.emic_case_no || "—"}</dd>
                  <dt className="text-[var(--muted)]">處理狀態</dt>
                  <dd>{c.emic_status || "—"}</dd>
                  <dt className="text-[var(--muted)]">處理單位</dt>
                  <dd>{c.assigned_unit || "—"}</dd>
                </dl>
              )}
              <details className="mt-3">
                <summary className="cursor-pointer text-[14px] text-[var(--muted)]">EMIC 欄位對照（暫定）</summary>
                <div className="overflow-x-auto">
                <table className="af-table mt-2 min-w-[420px]">
                  <thead>
                    <tr>
                      <th>上報欄位</th>
                      <th>說明</th>
                      <th>本系統來源</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.emic.field_map.map((f) => (
                      <tr key={f.key}>
                        <td className="font-mono text-[13px]">{f.key}</td>
                        <td>{f.label}</td>
                        <td className="text-[13px] text-[var(--muted)]">{f.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </details>
            </Panel>
          ) : null}

          {/* ── community ── */}
          {c.status === "community_open" ? (
            <Panel title="開放民眾協助處理中" accent="var(--st-community)">
              <p className="text-[15px] text-[var(--ink-2)]">民眾網站的案件頁已顯示「我來協助處理」。有民眾上傳處理完成照片時，LINE 群組會收到通知，案件會移到「待確認完成」。</p>
              {officer ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" className="af-btn af-btn-secondary" disabled={Boolean(busy)} onClick={() => window.confirm("改列上報 EMIC？") && run("escalate", () => api.transitionCase(c.id, { status: "reported_emic", note: "情況超出民眾可處理範圍，改列上報 EMIC" }))}>
                    改列上報 EMIC
                  </button>
                  <button type="button" className="af-btn af-btn-secondary" disabled={Boolean(busy)} onClick={() => window.confirm("確認已由其他方式處理完成並結案？") && run("close", () => api.transitionCase(c.id, { status: "closed", note: "承辦人員確認已處理完成" }), "已結案並自地圖撤除。")}>
                    已處理完成・直接結案
                  </button>
                </div>
              ) : null}
            </Panel>
          ) : null}

          {c.status === "community_submitted" ? (
            <Panel title="確認民眾的處理完成回報" accent="var(--st-community)">
              <p className="text-[15px] text-[var(--ink-2)]">民眾於 {fmtTime(c.community_submitted_at)} 回報已處理完成。請檢視處理後照片：</p>
              <div className="mt-3">
                <PhotoStrip photos={citizenPhotos} emptyText="沒有處理後照片" />
              </div>
              {officer ? (
                <>
                  <textarea className="af-input mt-3" placeholder="說明（選填；不通過時會公開顯示原因）" value={confirmNote} onChange={(e) => setConfirmNote(e.target.value)} maxLength={500} />
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <button type="button" className="af-btn af-btn-lg font-bold text-white" style={{ background: "var(--st-done)" }} disabled={Boolean(busy)} onClick={() => run("confirm-yes", () => api.confirmCommunity(c.id, { approve: true, note: confirmNote.trim() || undefined }), "已確認處理完成，結案並自地圖撤除。")}>
                      確認通過・結案
                    </button>
                    <button type="button" className="af-btn af-btn-danger af-btn-lg" disabled={Boolean(busy)} onClick={() => run("confirm-no", () => api.confirmCommunity(c.id, { approve: false, note: confirmNote.trim() || undefined }), "已退回，重新開放民眾協助。")}>
                      不通過・退回
                    </button>
                  </div>
                  <button type="button" className="mt-2 text-[14px] text-[var(--focus)] hover:underline" disabled={Boolean(busy)} onClick={() => window.confirm("改列上報 EMIC？") && run("escalate", () => api.transitionCase(c.id, { status: "reported_emic", note: "民眾處理後仍需權責單位處理，改列上報 EMIC" }))}>
                    仍需權責單位處理？改列上報 EMIC
                  </button>
                </>
              ) : null}
            </Panel>
          ) : null}

          {c.status === "closed" || c.status === "dismissed" ? (
            <Panel title={c.status === "closed" ? "已結案" : "不成案"} accent={c.status === "closed" ? "var(--st-done)" : "var(--st-dismissed)"}>
              <p className="text-[15px] text-[var(--ink-2)]">{c.status === "closed" ? "此案件已處理完成，並已自民眾地圖撤除。" : "此通報經審核判定不成案，不會公開於地圖。"}</p>
            </Panel>
          ) : null}

          {/* ── progress notes ── */}
          {officer && c.status !== "dismissed" ? (
            <Panel title="處理紀錄">
              <textarea className="af-input" placeholder="例如：已聯繫里長確認現場狀況" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
              <div className="mt-2 flex flex-wrap items-center gap-4 text-[15px]">
                <label className="inline-flex items-center gap-1.5">
                  <input type="radio" className="h-4 w-4" checked={notePublic} onChange={() => setNotePublic(true)} /> 公開顯示
                </label>
                <label className="inline-flex items-center gap-1.5">
                  <input type="radio" className="h-4 w-4" checked={!notePublic} onChange={() => setNotePublic(false)} /> 僅內部
                </label>
                <button type="button" className="af-btn af-btn-secondary ml-auto" disabled={!note.trim() || busy === "note"} onClick={() => run("note", async () => { const r = await api.addCaseUpdate(c.id, { note: note.trim(), public: notePublic }); setNote(""); return r; }, "已新增紀錄。")}>
                  新增紀錄
                </button>
              </div>
            </Panel>
          ) : null}

          <section className="af-panel overflow-hidden">
            <div className="h-72">
              <TerrainMap center={[c.lat, c.lon]} zoom={13} features={features} visible={mapVisible} enabledLayers={["incident_cases", "citizen_reports"]} threeD={false} />
            </div>
            {detail.nearby.length ? (
              <div className="p-3">
                <div className="af-eyebrow mb-1">附近案件（2 公里內）</div>
                <ul className="space-y-1.5 text-[15px]">
                  {detail.nearby.map((n) => (
                    <li key={n.id} className="flex items-center justify-between gap-2">
                      <Link href={`/console/platforms/${id}/cases/${n.id}`} className="truncate text-[var(--ink)] hover:underline">
                        {n.case_number} {n.title}
                      </Link>
                      <span className="flex items-center gap-2 text-[var(--muted)]">
                        <StatusPill status={n.status} console /> {fmtMeters(n.distance_m)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </div>

        <div className="min-w-0 space-y-4 xl:col-span-7">
          <section className="af-panel">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3" style={{ borderColor: "var(--line)" }}>
              <h2 className="text-[19px] font-semibold text-[var(--ink)]">民眾回報</h2>
              <span className="text-[14px] text-[var(--muted)]">
                {Object.entries(detail.reporter_roles)
                  .map(([k, v]) => `${ROLE_LABEL[k] || k} ${v}`)
                  .join(" · ")}
              </span>
            </div>
            {!detail.reports.some((r) => r.reporter_name || r.reporter_contact || r.reporter_email || r.pii_hidden) ? null : detail.pii_visible ? (
              <div className="border-b px-4 py-2 text-[13px] text-[var(--muted)]" style={{ borderColor: "var(--line)" }}>
                含個人聯絡資料，僅供查證聯繫使用；本次查閱已留存紀錄。
              </div>
            ) : (
              <div className="border-b px-4 py-2 text-[13px] text-[var(--muted)]" style={{ borderColor: "var(--line)" }}>
                您的角色不可檢視通報者個人資料。
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="af-table min-w-[680px]">
                <thead>
                  <tr>
                    <th>時間</th>
                    <th>類別／描述</th>
                    <th>地點</th>
                    <th>回報者</th>
                    <th className="text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.reports.map((r) => (
                    <tr key={r.id} className={r.status === "rejected" ? "opacity-50" : ""}>
                      <td className="whitespace-nowrap font-mono text-[13px] text-[var(--muted)]">{fmtTime(r.created_at)}</td>
                      <td>
                        <div className="font-medium">{CATEGORY_LABEL[r.category] || r.category}</div>
                        <div className="text-[15px] text-[var(--ink-2)]">{r.description || "（無描述）"}</div>
                        {r.photo_count ? <div className="text-[13px] text-[var(--muted)]">{r.photo_count} 張照片</div> : null}
                      </td>
                      <td className="text-[15px]">
                        {r.address || r.town || "—"}
                        {r.lat != null ? (
                          <div className="font-mono text-[12.5px] text-[var(--muted)]">
                            {r.lat.toFixed(5)}, {r.lon?.toFixed(5)}
                          </div>
                        ) : null}
                      </td>
                      <td className="text-[15px]">
                        {ROLE_LABEL[r.reporter_role] || r.reporter_role}
                        {!detail.reports.some((r) => r.reporter_name || r.reporter_contact || r.reporter_email || r.pii_hidden) ? null : detail.pii_visible ? (
                          <div className="text-[14px] text-[var(--ink-2)]">
                            {[r.reporter_name, r.reporter_contact, r.reporter_email].filter(Boolean).join(" · ") || (r.has_identity ? "未留聯絡資料" : "匿名")}
                          </div>
                        ) : r.pii_hidden ? (
                          <div className="text-[13px] text-[var(--muted)]">已留聯絡資料（不可檢視）</div>
                        ) : null}
                        {r.notify_opt_in ? <div className="text-[13px] text-[var(--st-active)]">訂閱進度通知</div> : null}
                      </td>
                      <td className="text-right">
                        {r.status !== "rejected" ? (
                          officer ? (
                            <button type="button" className="af-btn af-btn-ghost" disabled={busy === `rej-${r.id}`} onClick={() => run(`rej-${r.id}`, () => api.rejectReport(r.id, "承辦判定不可信"))}>
                              排除
                            </button>
                          ) : null
                        ) : (
                          <span className="text-[13px] text-[var(--muted)]">已排除</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="af-panel p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[19px] font-semibold text-[var(--ink)]">照片</h2>
              {officer ? (
                <div className="flex items-center gap-2">
                  <select className="af-input !w-auto !py-1.5" value={photoKind} onChange={(e) => setPhotoKind(e.target.value as typeof photoKind)}>
                    <option value="before">處理前</option>
                    <option value="scene">現場</option>
                    <option value="after">處理後</option>
                  </select>
                  <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) run("photo", () => api.uploadCasePhoto(c.id, f, photoKind), "已上傳照片。"); e.target.value = ""; }} />
                  <button type="button" className="af-btn af-btn-secondary" disabled={busy === "photo"} onClick={() => fileRef.current?.click()}>
                    上傳照片
                  </button>
                </div>
              ) : null}
            </div>
            <PhotoStrip photos={detail.photos} emptyText="尚無照片。民眾通報與協助處理的照片、承辦上傳的照片會顯示於此。" />
          </section>

          <section className="af-panel p-4">
            <h2 className="mb-3 text-[19px] font-semibold text-[var(--ink)]">完整時間軸（含內部紀錄）</h2>
            <CaseTimeline items={timelineItems} dense />
          </section>
        </div>
      </div>
    </ConsoleShell>
  );
}
