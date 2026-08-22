"use client";

// Case workbench: dispatch, progress the state machine, post public updates,
// review every report (with PII, internal only), photos, nearby cases.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import CaseTimeline, { ProgressSteps } from "@/components/CaseTimeline";
import PhotoStrip from "@/components/PhotoStrip";
import ResponderPanel from "@/components/console/ResponderPanel";
import { ErrorBox, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtMeters, fmtTime } from "@/lib/format";
import { CATEGORY_LABEL, CATEGORY_LAYER, EVENT_LABEL, ROLE_LABEL, STATUS_LABEL } from "@/lib/labels";
import type { CaseDetail, CaseStatus, MapFeature, PublicTimelineItem, RouteFeature, VehicleItem } from "@/lib/types";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

const ACTION_LABEL: Partial<Record<CaseStatus, string>> = {
  awaiting_dispatch: "退回待派工",
  en_route: "人員出發",
  on_site: "人員抵達",
  processing: "開始處理",
  resolved: "處理完成",
  closed: "結案",
  dismissed: "判定不成案",
  verifying: "開始查證",
  threshold_reached: "確認成案",
};

const UNIT_PRESETS = ["縣政府工務處道路養護科", "鄉公所民政課", "鄉公所農業課", "縣消防局大隊", "公路局工務段", "水利署河川分署", "農村發展及水土保持署分署", "台電區營業處"];

export default function CaseWorkbenchPage() {
  const { id, caseId } = useParams<{ id: string; caseId: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [unit, setUnit] = useState("");
  const [lead, setLead] = useState("");
  const [contact, setContact] = useState("");
  const [assignNote, setAssignNote] = useState("");
  const [note, setNote] = useState("");
  const [notePublic, setNotePublic] = useState(true);
  const [actor, setActor] = useState("值班承辦");
  const [photoKind, setPhotoKind] = useState<"before" | "scene" | "after">("after");
  const [manualOpen, setManualOpen] = useState(false);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [vehicles, setVehicles] = useState<VehicleItem[]>([]);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(() => {
    api.getCase(caseId).then(setDetail).catch((e) => setError((e as Error).message));
  }, [caseId]);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [load]);
  useEffect(() => {
    const loadLive = () => {
      api.consoleRoutes(id).then((r) => setRoutes(r.features.filter((f) => f.properties.case_id === caseId))).catch(() => undefined);
      api.consoleVehicles(id).then((r) => setVehicles(r.items.filter((v) => v.case_id === caseId))).catch(() => undefined);
    };
    loadLive();
    const t = window.setInterval(loadLive, 3000);
    return () => window.clearInterval(t);
  }, [id, caseId]);

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
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

  const timelineItems = useMemo<PublicTimelineItem[]>(
    () =>
      (detail?.events || []).map((e) => ({
        event_type: e.event_type,
        label: (e.event_type === "status_changed" && e.to_status_label) || EVENT_LABEL[e.event_type] || e.event_type,
        note: [e.note, e.actor_name ? `— ${e.actor_name}` : "", e.public ? "" : "（內部）"].filter(Boolean).join(" "),
        to_status: (e.to_status as CaseStatus) || null,
        at: e.created_at,
      })),
    [detail]
  );

  const progress = useMemo(() => {
    if (!detail) return [];
    const order: CaseStatus[] = ["reported", "threshold_reached", "awaiting_dispatch", "assigned", "on_site", "processing", "resolved"];
    const reached: Record<string, string> = {};
    for (const e of detail.events) {
      if (e.to_status && !reached[e.to_status]) reached[e.to_status] = e.created_at;
      if (e.event_type === "report.received" && !reached.reported) reached.reported = e.created_at;
    }
    const cur = order.indexOf(detail.case.status === "en_route" ? "assigned" : (detail.case.status as CaseStatus));
    return order.map((k, i) => ({ key: k, label: STATUS_LABEL[k], reached: Boolean(reached[k]) || (cur >= 0 && i <= cur), current: cur === i, at: reached[k] || null }));
  }, [detail]);

  if (!detail) {
    return (
      <ConsoleShell crumbs={[{ href: "/console", label: "平台總覽" }, { href: `/console/platforms/${id}`, label: "指揮中心" }, { label: "案件" }]}>
        {error ? <ErrorBox message={error} onRetry={load} /> : <Skeleton className="h-80" />}
      </ConsoleShell>
    );
  }
  const c = detail.case;
  const canAssign = !["closed", "dismissed"].includes(c.status);

  return (
    <ConsoleShell wide crumbs={[{ href: "/console", label: "平台總覽" }, { href: `/console/platforms/${id}`, label: "指揮中心" }, { label: c.case_number }]}>
      {error ? (
        <div className="mb-3">
          <ErrorBox message={error} />
        </div>
      ) : null}
      <div className="af-panel mb-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-mono text-[11px] text-[var(--muted)]">{c.case_number}</div>
            <h1 className="text-xl font-semibold">{c.title}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-[var(--ink-2)]">
              <StatusPill status={c.status} phase={c.phase} />
              <SeverityTag severity={c.severity} />
              <span>{c.unique_reporter_count} 人回報（{c.report_count} 筆）</span>
              <span>{c.town} · {c.location_label}</span>
              <span className="font-mono text-[var(--muted)]">
                {c.lat.toFixed(5)}, {c.lon.toFixed(5)}
              </span>
            </div>
          </div>
          <div className="text-right text-[11px] text-[var(--muted)]">
            <div>成案 {fmtTime(c.created_at)}</div>
            {c.dispatched_at ? <div>派工 {fmtTime(c.dispatched_at)}</div> : null}
            {c.resolved_at ? <div>完成 {fmtTime(c.resolved_at)}</div> : null}
            {c.assigned_unit ? <div className="mt-1 font-medium text-[var(--ink-2)]">處理單位：{c.assigned_unit}</div> : null}
            <Link href={`/p/${""}`} className="hidden" />
          </div>
        </div>
        <div className="mt-4">
          <ProgressSteps steps={progress} />
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        {/* actions */}
        <div className="space-y-3 xl:col-span-4">
          <ResponderPanel caseId={c.id} disabled={!canAssign} actorName={actor} onDispatched={() => load()} />

          <section className="af-panel p-3">
            <button type="button" className="flex w-full items-center justify-between text-left text-xs font-medium text-[var(--ink-2)]" onClick={() => setManualOpen((v) => !v)} aria-expanded={manualOpen}>
              <span>手動指定處理單位（不在建議名單內）</span>
              <span className="text-[var(--muted)]">{manualOpen ? "收合 ▾" : "展開 ▸"}</span>
            </button>
            {manualOpen ? (
              <div className="mt-3">
            {canAssign ? (
              <div className="space-y-2">
                <input className="af-input" list="unit-presets" placeholder="處理單位（例：仁愛鄉公所民政課）" value={unit} onChange={(e) => setUnit(e.target.value)} />
                <datalist id="unit-presets">
                  {UNIT_PRESETS.map((u) => (
                    <option key={u} value={u} />
                  ))}
                </datalist>
                <div className="grid grid-cols-2 gap-2">
                  <input className="af-input" placeholder="帶隊人員（內部）" value={lead} onChange={(e) => setLead(e.target.value)} />
                  <input className="af-input" placeholder="聯絡方式（內部）" value={contact} onChange={(e) => setContact(e.target.value)} />
                </div>
                <input className="af-input" placeholder="派工備註（選填）" value={assignNote} onChange={(e) => setAssignNote(e.target.value)} />
                <button
                  type="button"
                  className="af-btn af-btn-primary w-full"
                  disabled={!unit.trim() || busy === "assign"}
                  onClick={() =>
                    run("assign", async () => {
                      await api.assignCase(c.id, { unit_name: unit.trim(), team_lead: lead || undefined, contact: contact || undefined, note: assignNote || undefined, actor_name: actor });
                      setUnit("");
                      setLead("");
                      setContact("");
                      setAssignNote("");
                    })
                  }
                >
                  {c.status === "awaiting_dispatch" ? "確認成案並派遣" : "派遣／改派"}
                </button>
                <div className="text-[11px] text-[var(--muted)]">派工後公開網站立即顯示「已派員」與處理單位名稱；人員聯絡方式不公開。</div>
              </div>
            ) : (
              <div className="text-xs text-[var(--muted)]">此案件已結案或不成案。</div>
            )}
              </div>
            ) : null}
          </section>

          <section className="af-panel p-4">
            <h2 className="af-h2 mb-2">更新處理狀態</h2>
            <div className="flex flex-wrap gap-1.5">
              {c.next_statuses.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`af-btn ${s === "dismissed" ? "af-btn-danger" : s === "resolved" || s === "closed" ? "af-btn-primary" : "af-btn-secondary"} text-xs`}
                  disabled={busy === s || (s === "assigned" && !c.assigned_unit)}
                  title={s === "assigned" && !c.assigned_unit ? "請先指定處理單位" : undefined}
                  onClick={() => run(s, () => api.transitionCase(c.id, { status: s, actor_name: actor, public: true }))}
                >
                  {ACTION_LABEL[s] || STATUS_LABEL[s]}
                </button>
              ))}
              {c.next_statuses.length === 0 ? <span className="text-xs text-[var(--muted)]">已無可用的狀態轉換。</span> : null}
            </div>
            <div className="mt-2 text-[11px] text-[var(--muted)]">僅允許狀態機定義的轉換；每次變更寫入公開時間軸與稽核軌跡。</div>
          </section>

          <section className="af-panel p-4">
            <h2 className="af-h2 mb-2">處理紀錄／公開進度</h2>
            <textarea className="af-input" placeholder="例如：重機具進場清除土石，單線通行預計 2 小時後恢復" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" checked={notePublic} onChange={() => setNotePublic(true)} /> 公開顯示
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" checked={!notePublic} onChange={() => setNotePublic(false)} /> 僅內部
              </label>
              <input className="af-input !w-32 !py-1 text-xs" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="操作者" />
              <button
                type="button"
                className="af-btn af-btn-secondary ml-auto"
                disabled={!note.trim() || busy === "note"}
                onClick={() =>
                  run("note", async () => {
                    await api.addCaseUpdate(c.id, { note: note.trim(), public: notePublic, actor_name: actor });
                    setNote("");
                  })
                }
              >
                新增紀錄
              </button>
            </div>
          </section>

          <section className="af-panel overflow-hidden">
            <div className="h-72">
              <TerrainMap center={[c.lat, c.lon]} zoom={13} features={features} visible={{ incident_cases: true, citizen_reports: true, dispatch: true }} enabledLayers={["incident_cases", "citizen_reports"]} routes={routes} vehicles={vehicles} threeD={false} />
            </div>
            {detail.nearby.length ? (
              <div className="p-3">
                <div className="af-eyebrow mb-1">附近案件（2 公里內）</div>
                <ul className="space-y-1 text-xs">
                  {detail.nearby.map((n) => (
                    <li key={n.id} className="flex items-center justify-between gap-2">
                      <Link href={`/console/platforms/${id}/cases/${n.id}`} className="truncate text-[var(--ink)] hover:underline">
                        {n.case_number} {n.title}
                      </Link>
                      <span className="flex items-center gap-2 text-[var(--muted)]">
                        <StatusPill status={n.status} /> {fmtMeters(n.distance_m)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </div>

        {/* reports / photos / timeline */}
        <div className="space-y-3 xl:col-span-8">
          <section className="af-panel">
            <div className="flex items-center justify-between border-b px-3 py-2" style={{ borderColor: "var(--line)" }}>
              <h2 className="af-h2">所有回報（含內部識別資訊）</h2>
              <span className="text-[11px] text-[var(--muted)]">
                {Object.entries(detail.reporter_roles)
                  .map(([k, v]) => `${ROLE_LABEL[k] || k} ${v}`)
                  .join(" · ")}
              </span>
            </div>
            <table className="af-table">
              <thead>
                <tr>
                  <th>時間</th>
                  <th>類別／描述</th>
                  <th>地點</th>
                  <th>回報者</th>
                  <th>分級</th>
                  <th className="text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {detail.reports.map((r) => (
                  <tr key={r.id} className={r.status === "rejected" ? "opacity-50" : ""}>
                    <td className="font-mono text-[11px] text-[var(--muted)]">{fmtTime(r.created_at)}</td>
                    <td>
                      <div className="font-medium">{CATEGORY_LABEL[r.category] || r.category}</div>
                      <div className="text-xs text-[var(--ink-2)]">{r.description || "（無描述）"}</div>
                      {r.photo_count ? <div className="text-[11px] text-[var(--muted)]">{r.photo_count} 張照片</div> : null}
                    </td>
                    <td className="text-xs">
                      {r.address || r.town || "—"}
                      {r.lat != null ? (
                        <div className="font-mono text-[10.5px] text-[var(--muted)]">
                          {r.lat.toFixed(5)}, {r.lon?.toFixed(5)}
                        </div>
                      ) : null}
                    </td>
                    <td className="text-xs">
                      {ROLE_LABEL[r.reporter_role] || r.reporter_role}
                      <div className="text-[11px] text-[var(--muted)]">
                        {r.reporter_name || "—"} {r.reporter_contact || ""}
                        {!r.has_identity ? " · 匿名" : ""}
                      </div>
                    </td>
                    <td>
                      <SeverityTag severity={r.triage_severity} withLabel={false} />
                    </td>
                    <td className="text-right">
                      {r.status !== "rejected" ? (
                        <button type="button" className="af-btn af-btn-ghost !py-0.5 text-[11px]" disabled={busy === `rej-${r.id}`} onClick={() => run(`rej-${r.id}`, () => api.rejectReport(r.id, "承辦判定不可信"))}>
                          排除
                        </button>
                      ) : (
                        <span className="text-[11px] text-[var(--muted)]">已排除</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="af-panel p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="af-h2">照片（處理前／現場／處理後）</h2>
              <div className="flex items-center gap-1.5 text-xs">
                <select className="af-input !w-auto !py-0.5 text-xs" value={photoKind} onChange={(e) => setPhotoKind(e.target.value as typeof photoKind)}>
                  <option value="before">處理前</option>
                  <option value="scene">現場</option>
                  <option value="after">處理後</option>
                </select>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) run("photo", () => api.uploadCasePhoto(c.id, f, photoKind)); e.target.value = ""; }} />
                <button type="button" className="af-btn af-btn-secondary !py-0.5 text-xs" disabled={busy === "photo"} onClick={() => fileRef.current?.click()}>
                  上傳單位照片
                </button>
              </div>
            </div>
            <PhotoStrip photos={detail.photos} emptyText="尚無照片。民眾通報附帶的照片與處理單位上傳的前後對照會顯示於此。" />
          </section>

          <section className="af-panel p-4">
            <h2 className="af-h2 mb-3">完整時間軸（含內部紀錄）</h2>
            <CaseTimeline items={timelineItems} dense />
            {detail.assignments.length ? (
              <div className="mt-4">
                <div className="af-eyebrow mb-1">派工紀錄</div>
                <ul className="space-y-1 text-xs">
                  {detail.assignments.map((a) => (
                    <li key={a.id} className="flex flex-wrap gap-2 text-[var(--ink-2)]">
                      <span className="font-mono text-[var(--muted)]">{fmtTime(a.created_at)}</span>
                      <span className="font-medium text-[var(--ink)]">{a.unit_name}</span>
                      <span>{a.team_lead}</span>
                      <span className="text-[var(--muted)]">{a.contact}</span>
                      <span className="af-chip">{a.status === "active" ? "執行中" : a.status === "completed" ? "已完成" : "已取消"}</span>
                      {a.note ? <span className="text-[var(--muted)]">{a.note}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </ConsoleShell>
  );
}
