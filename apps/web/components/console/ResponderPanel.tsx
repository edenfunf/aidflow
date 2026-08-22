"use client";

// Console: suggested responder units for a case → one-click "通報並派遣".
// Rules pick the unit kinds, distance + road route rank them; dispatching
// creates the assignment, routes it, notifies the unit (LINE / webhook /
// simulated) and writes the public timeline + audit trail.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtMeters } from "@/lib/format";
import { UNIT_KIND_HEX, VEHICLE_GLYPH, VEHICLE_HEX } from "@/lib/labels";
import type { DispatchResponse, ResponderSuggestion } from "@/lib/types";

const CHANNEL_LABEL: Record<string, string> = {
  line: "LINE 推播已送出",
  webhook: "已送至出勤系統",
  simulated: "已記錄（模擬通報）",
  error: "通報失敗",
  none: "未通報",
};

export default function ResponderPanel({ caseId, disabled, actorName, onDispatched }: { caseId: string; disabled?: boolean; actorName: string; onDispatched: (r: DispatchResponse) => void }) {
  const [items, setItems] = useState<ResponderSuggestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<DispatchResponse | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    setItems(null);
    api
      .caseResponders(caseId)
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message));
  }, [caseId]);

  async function dispatch(unitId: string) {
    setBusy(unitId);
    setError(null);
    try {
      const r = await api.dispatchCase(caseId, { unit_id: unitId, note: note.trim() || undefined, actor_name: actorName });
      setResult(r);
      onDispatched(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="af-panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="af-h2">建議出勤單位</h2>
        <span className="text-[11px] text-[var(--muted)]">依權責規則 → 距離 → 真實道路 ETA</span>
      </div>
      {error ? <div className="mb-2 text-xs text-[var(--sev-high)]">{error}</div> : null}
      {result ? (
        <div className="mb-3 rounded border px-3 py-2 text-xs" style={{ borderColor: result.notification.status === "failed" ? "#f4b8b3" : "#9fd8b9", background: result.notification.status === "failed" ? "#fef3f2" : "#f0fdf4" }}>
          <div className="font-medium text-[var(--ink)]">
            已派遣 {result.assignment.unit_name} · {CHANNEL_LABEL[result.notification.channel] || result.notification.channel}
          </div>
          <div className="mt-0.5 text-[var(--ink-2)]">
            {result.notification.detail}
            {result.assignment.eta_minutes ? ` · 預計 ${result.assignment.eta_minutes} 分鐘抵達（${fmtMeters(result.assignment.distance_m)}${result.assignment.route_source === "straight_line" ? "，直線估算" : "，道路路徑"}）` : ""}
          </div>
          <div className="mt-0.5 text-[var(--muted)]">出勤車輛：{(result.assignment.vehicles || []).map((v) => VEHICLE_GLYPH[v.kind]).join("、")} · 公開端已顯示「已派員」與出勤路徑</div>
        </div>
      ) : null}
      <input className="af-input mb-2" placeholder="給出勤單位的備註（選填，會一併送出）" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
      {items === null ? (
        <div className="text-xs text-[var(--muted)]">計算路徑中…</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-[var(--muted)]">此縣市尚無可派遣單位資料。</div>
      ) : (
        <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
          {items.map((s) => (
            <li key={s.unit.id} className="flex items-center gap-3 py-2">
              <span className="h-9 w-1 flex-none rounded-sm" style={{ background: UNIT_KIND_HEX[s.unit.kind] || "#667085" }} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium text-[var(--ink)]">
                  {s.unit.name}
                  {s.primary ? <span className="af-chip !py-0 text-[10px]">權責單位</span> : <span className="af-chip !py-0 text-[10px]">支援</span>}
                  <span className="af-chip !py-0 text-[10px]">{s.unit.kind_label}</span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-[var(--muted)]">
                  <span>
                    {s.eta_minutes ? `約 ${s.eta_minutes} 分鐘 · ${fmtMeters(s.distance_m)}` : `直線 ${fmtMeters(s.straight_m)}`}
                    {s.route_source === "straight_line" ? "（直線估算）" : s.route_source === "osrm" ? "（道路路徑）" : ""}
                  </span>
                  <span>
                    {s.vehicles.map((v) => (
                      <span key={v.kind} className="mr-1 inline-grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold text-white" style={{ background: VEHICLE_HEX[v.kind] }} title={v.label}>
                        {VEHICLE_GLYPH[v.kind]}
                      </span>
                    ))}
                  </span>
                  {s.unit.location_source !== "open_data" ? <span title="位置為鄉鎮示意，非測量座標">示意位置</span> : null}
                  {s.unit.phone ? <span>{s.unit.phone}</span> : null}
                </div>
              </div>
              <button type="button" className={`af-btn ${s.primary ? "af-btn-primary" : "af-btn-secondary"} !py-1 text-xs`} disabled={disabled || busy !== null} onClick={() => dispatch(s.unit.id)}>
                {busy === s.unit.id ? "派遣中…" : "通報並派遣"}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 text-[10.5px] text-[var(--faint)]">通報內容含案號、類別、位置、回報摘要與照片連結，不含回報者姓名電話。未設定 LINE／webhook 時為模擬通報並記錄稽核。</div>
    </section>
  );
}
