"use client";

// Layer toggles + legend for the incident map. The set of toggles is driven
// by the platform's enabled layers (Module Registry), not hard-coded.

import { useState } from "react";
import { LAYERS, PHASE_HEX, PHASE_LABEL } from "@/lib/labels";
import type { LayerResponse, LayerStatusItem } from "@/lib/types";

const INTERNAL_ORDER = ["incident_cases", "report_clusters", "citizen_reports", "heatmap", "government_processing"];
const CATEGORY_ORDER = ["trapped_people", "road_damage", "landslide", "flooding", "building_damage", "lifeline"];
const OFFICIAL_ORDER = ["official_alert", "radar", "rainfall", "water", "reservoir", "debris_flow", "landslide_zone", "road_traffic", "population", "power_outage", "shelter", "fire_station"];

export interface LayerPanelProps {
  enabledLayers: string[];
  visible: Record<string, boolean>;
  onToggle: (key: string) => void;
  counts?: Record<string, number>;
  officialLayers?: Record<string, LayerResponse | undefined>;
  statuses?: LayerStatusItem[];
  compact?: boolean;
}

function Row({ keyName, on, onToggle, count, detail, disabled }: { keyName: string; on: boolean; onToggle: () => void; count?: number; detail?: string | null; disabled?: boolean }) {
  const meta = LAYERS[keyName];
  if (!meta) return null;
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={on}
      className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs transition hover:bg-[var(--surface-3)] disabled:cursor-not-allowed disabled:opacity-50"
      title={detail || undefined}
    >
      <span
        className="inline-block h-3 w-3 flex-none rounded-sm border"
        style={{ background: on ? meta.hex : "transparent", borderColor: on ? meta.hex : "var(--line-2)" }}
      />
      <span className={on ? "text-[var(--ink)]" : "text-[var(--muted)]"}>{meta.label}</span>
      <span className="ml-auto tabular-nums text-[var(--faint)]">{count !== undefined ? count : ""}</span>
    </button>
  );
}

export default function LayerPanel({ enabledLayers, visible, onToggle, counts = {}, officialLayers = {}, statuses = [], compact = false }: LayerPanelProps) {
  const statusOf = (k: string) => statuses.find((s) => s.layer === k);
  const has = (k: string) => enabledLayers.includes(k);
  const internal = INTERNAL_ORDER.filter(has);
  const categories = CATEGORY_ORDER.filter(has);
  const official = OFFICIAL_ORDER.filter(has);
  const [officialOpen, setOfficialOpen] = useState(!compact);
  const officialOn = official.filter((k) => visible[k] === true).length;

  return (
    <div className={`text-xs ${compact ? "space-y-2" : "space-y-3"}`}>
      {internal.length > 0 && (
        <section>
          <div className="af-eyebrow mb-1">災情資料</div>
          {internal.map((k) => (
            <Row key={k} keyName={k} on={visible[k] !== false && (k !== "heatmap" && k !== "government_processing" ? true : visible[k] === true)} onToggle={() => onToggle(k)} count={counts[k]} />
          ))}
        </section>
      )}
      {categories.length > 0 && (
        <section>
          <div className="af-eyebrow mb-1">災情類別篩選</div>
          {categories.map((k) => (
            <Row key={k} keyName={k} on={visible[k] !== false} onToggle={() => onToggle(k)} count={counts[k]} />
          ))}
        </section>
      )}
      {official.length > 0 && (
        <section>
          <button type="button" className="af-eyebrow mb-1 flex w-full items-center justify-between" onClick={() => setOfficialOpen((v) => !v)} aria-expanded={officialOpen}>
            <span>
              官方資料 <span className="font-normal normal-case tracking-normal text-[var(--faint)]">{officialOn}/{official.length} 開啟</span>
            </span>
            <span aria-hidden="true">{officialOpen ? "▴" : "▾"}</span>
          </button>
          {officialOpen && official.map((k) => {
            const st = statusOf(k);
            const data = officialLayers[k];
            const unavailable = st?.status === "disabled" || data?.status === "disabled" || data?.status === "unavailable";
            const detail = data?.detail || st?.detail || null;
            return (
              <div key={k}>
                <Row keyName={k} on={visible[k] === true} onToggle={() => onToggle(k)} count={data?.count} detail={detail} disabled={st?.status === "disabled"} />
                {unavailable && visible[k] !== false && (
                  <div className="ml-6 -mt-0.5 mb-1 text-[10.5px] leading-snug text-[var(--faint)]">
                    {data?.status === "unavailable" ? "上游暫時無法取得" : "尚未設定資料來源金鑰"}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}
      {!compact && (
        <section>
          <div className="af-eyebrow mb-1">案件狀態</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {(["pending", "active", "done"] as const).map((p) => (
              <span key={p} className="inline-flex items-center gap-1.5 text-[var(--ink-2)]">
                <span className="h-2 w-2 rounded-full" style={{ background: PHASE_HEX[p] }} />
                {PHASE_LABEL[p]}
              </span>
            ))}
          </div>
          <div className="mt-1.5 text-[10.5px] leading-snug text-[var(--faint)]">
            方塊＝正式案件（數字為回報人數）；虛線圓＝尚未成案的多人回報；小圓點＝單筆通報。
          </div>
        </section>
      )}
    </div>
  );
}
