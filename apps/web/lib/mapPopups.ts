// HTML popup builders shared by the Leaflet and MapLibre maps. All values
// are escaped — popup content comes from user-submitted reports.

import { CATEGORY_LABEL, LAYERS, PHASE_HEX, SEVERITY_LABEL, STATUS_LABEL } from "./labels";
import { fmtTime } from "./format";
import type { GeoFeature, Severity } from "./types";

export const esc = (v: unknown): string =>
  String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

export function casePopup(p: Record<string, any>): string {
  return `<div style="min-width:180px">
    <div style="font-size:11px;color:#667085">${esc(p.case_number)}</div>
    <div style="font-size:13px;font-weight:600;color:#101828">${esc(p.title)}</div>
    <div style="margin-top:4px;display:flex;gap:6px;flex-wrap:wrap">
      <span style="display:inline-flex;align-items:center;gap:4px"><span style="width:8px;height:8px;border-radius:9999px;background:${PHASE_HEX[p.phase as keyof typeof PHASE_HEX] || "#667085"}"></span>${esc(STATUS_LABEL[p.status as keyof typeof STATUS_LABEL] || p.status_label)}</span>
      <span style="color:#667085">嚴重度 ${esc(SEVERITY_LABEL[p.severity as Severity] || p.severity)}</span>
    </div>
    <div style="margin-top:4px;color:#344054">${esc(p.unique_reporter_count)} 人回報 · ${esc(p.location_label || p.town || "")}</div>
    ${p.assigned_unit ? `<div style="color:#344054">處理單位：${esc(p.assigned_unit)}</div>` : ""}
    <div style="margin-top:4px;font-size:11px;color:#98a2b3">${esc(fmtTime(p.created_at))}</div>
  </div>`;
}

export function clusterPopup(p: Record<string, any>): string {
  return `<div style="min-width:160px">
    <div style="font-size:13px;font-weight:600;color:#101828">${esc(p.category_label || CATEGORY_LABEL[p.category] || p.category)}</div>
    <div style="color:#344054">${esc(p.unique_reporter_count)} 位回報者 · ${esc(p.report_count)} 筆通報</div>
    <div style="color:#667085;font-size:11px">尚未達成案門檻 · ${esc(p.town || "")}</div>
    <div style="margin-top:4px;font-size:11px;color:#98a2b3">最近 ${esc(fmtTime(p.last_reported_at))}</div>
  </div>`;
}

export function reportPopup(p: Record<string, any>): string {
  return `<div style="min-width:160px">
    <div style="font-size:13px;font-weight:600;color:#101828">${esc(p.category_label || CATEGORY_LABEL[p.category] || p.category)}</div>
    ${p.description ? `<div style="color:#344054">${esc(p.description)}</div>` : ""}
    <div style="color:#667085;font-size:11px">${esc(p.location_label || p.address || p.town || "")}</div>
    <div style="margin-top:4px;font-size:11px;color:#98a2b3">${esc(fmtTime(p.created_at))}${p.photo_count ? ` · ${esc(p.photo_count)} 張照片` : ""}</div>
  </div>`;
}

export function officialPopup(f: GeoFeature | { layer: string; properties: Record<string, any> }): string {
  const p = f.properties || {};
  const rows: string[] = [];
  if (f.layer === "shelter") {
    rows.push(`容納 ${esc(p.capacity ?? "—")} 人`, esc(p.address || ""), p.phone ? `電話 ${esc(p.phone)}` : "", (p.hazards || []).join("、"));
  } else if (f.layer === "fire_station") {
    rows.push(esc(p.address || ""), p.phone ? `電話 ${esc(p.phone)}` : "");
  } else if (f.layer === "water") {
    rows.push(`${esc(p.river || "")} · 水位 ${p.water_level_m ?? "—"} m`, `警戒 一級 ${p.alert_level_1 ?? "—"} / 二級 ${p.alert_level_2 ?? "—"} / 三級 ${p.alert_level_3 ?? "—"}`, `觀測 ${esc(fmtTime(p.observed_at))}`);
  } else if (f.layer === "rainfall") {
    rows.push(`1 小時 ${p.rain_1h_mm ?? "—"} mm · 3 小時 ${p.rain_3h_mm ?? "—"} mm`, `24 小時 ${p.rain_24h_mm ?? "—"} mm`, `觀測 ${esc(fmtTime(p.observed_at))}`);
  } else if (f.layer === "official_alert") {
    rows.push(esc(p.headline || ""), esc(p.description || ""), p.valid_to ? `有效至 ${esc(fmtTime(p.valid_to))}` : "", `發布：${esc(p.issuer || "")}`);
  } else if (f.layer === "debris_flow") {
    const alert = p.alert === "red" ? '<b style="color:#dc2626">紅色警戒</b>' : p.alert === "yellow" ? '<b style="color:#b45309">黃色警戒</b>' : "潛勢溪流（未發布警戒）";
    rows.push(`${alert}${p.alert_time ? ` · ${esc(p.alert_time)}` : ""}`, `${esc(p.debris_no || "")} · ${esc(p.town || "")}${esc(p.vill || "")}`, p.kind === "impact" ? `影響範圍 · 保全 ${esc(p.households ?? p.households_class ?? "—")} 戶` : `風險 ${esc(p.risk || "—")} · 保全 ${esc(p.households_class || "—")} · 長 ${p.length_km ?? "—"} km`, [p.road, p.landmark].filter(Boolean).map(esc).join(" · "), "農村發展及水土保持署");
  } else if (f.layer === "landslide_zone") {
    rows.push(p.alert ? `<b style="color:${p.alert === "red" ? "#dc2626" : "#b45309"}">${p.alert === "red" ? "紅色" : "黃色"}警戒</b> · ${esc(p.alert_time || "")}` : "大規模崩塌潛勢區", `${esc(p.zone_no || "")} · ${esc(p.town || "")}${esc(p.vill || "")} · ${esc(p.hazard_type || "")}`, `風險 ${esc(p.risk || "—")} · 保全 ${esc(p.households ?? "—")} 戶 · ${p.area_ha ?? "—"} 公頃`, [p.road, p.landmark].filter(Boolean).map(esc).join(" · "));
  } else if (f.layer === "reservoir") {
    const st = p.status === "releasing" ? `<b style="color:#b91c1c">洩洪中 ${p.spillway_cms ?? ""} cms</b>` : p.status === "high" ? '<b style="color:#d97706">接近滿水位</b>' : p.status === "low" ? "蓄水偏低" : "正常";
    rows.push(st, `蓄水率 ${p.storage_pct ?? "—"}% · 水位 ${p.water_level_m ?? "—"} m`, `有效蓄水 ${p.effective_storage ?? "—"} / ${p.effective_capacity ?? "—"} 萬 m³`, p.inflow_cms != null || p.outflow_cms != null ? `入流 ${p.inflow_cms ?? "—"} · 出流 ${p.outflow_cms ?? "—"} cms` : "", `${esc(p.agency || "")} · 觀測 ${esc(fmtTime(p.observed_at))}`, "位置為鄉鎮示意，非壩址座標");
  } else if (f.layer === "population") {
    rows.push(`人口 ${Number(p.population).toLocaleString()} 人（全縣 ${(Number(p.share) * 100).toFixed(1)}%）`, `男 ${Number(p.male).toLocaleString()} · 女 ${Number(p.female).toLocaleString()} · ${p.villages} 村里`, p.indigenous_mountain ? `山地原住民 ${Number(p.indigenous_mountain).toLocaleString()} 人（${(Number(p.indigenous_share) * 100).toFixed(1)}%）` : "", `戶政司 民國 ${String(p.statistic_month || "").slice(0, 3)} 年 ${String(p.statistic_month || "").slice(3)} 月`);
  } else if (f.layer === "road_traffic") {
    if (p.kind === "cctv") {
      rows.push(p.image_url ? `<img src="${esc(p.image_url)}" alt="" style="width:240px;max-width:100%;border-radius:4px;margin:4px 0" loading="lazy"/>` : "無靜態影像", `${esc(p.road || "")} ${esc(p.mile || "")} · ${p.authority === "highway" ? "公路局" : "縣市"}`, p.stream_url ? `<a href="${esc(p.stream_url)}" target="_blank" rel="noreferrer" style="color:#2e5aac">開啟即時串流 ↗</a>` : "");
    } else {
      rows.push(esc(p.description || ""), `${esc(fmtTime(p.published_at))} · ${p.authority === "highway" ? "公路局" : "縣市"}`);
    }
  } else if (f.layer === "power_outage") {
    rows.push(...(p.items || []).slice(0, 4).map((i: any) => `${esc(i.when || "")} · ${esc(i.area || "")}（${esc(i.work || "")}）`), `計畫性工作停電（非事故） · 查詢 ${esc(p.phone || "1911")}`);
  }
  return `<div style="min-width:170px">
    <div style="font-size:11px;color:#667085">${esc(LAYERS[f.layer]?.label || f.layer)}</div>
    <div style="font-size:13px;font-weight:600;color:#101828">${esc(p.name || "")}</div>
    ${rows.filter(Boolean).map((r) => `<div style="color:#344054">${r}</div>`).join("")}
  </div>`;
}
