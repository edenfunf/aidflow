// Shared vocabulary: labels and the reserved colours for severity, status and
// map layers. Kept free of Leaflet so it can be imported on the server.

import type { CaseStatus, Phase, Severity } from "./types";

export const SEVERITY_LABEL: Record<Severity, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "極高",
};

export const SEVERITY_COLOR: Record<Severity, string> = {
  low: "var(--sev-low)",
  medium: "var(--sev-medium)",
  high: "var(--sev-high)",
  critical: "var(--sev-critical)",
};

// hex copies for canvas / Leaflet (CSS variables are not resolvable there)
export const SEVERITY_HEX: Record<Severity, string> = {
  low: "#98a2b3",
  medium: "#dc8a0c",
  high: "#d92d20",
  critical: "#7a0c16",
};

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export const STATUS_LABEL: Record<CaseStatus, string> = {
  reported: "已通報",
  verifying: "查證中",
  threshold_reached: "已成案",
  awaiting_dispatch: "待派工",
  assigned: "已派員",
  en_route: "前往中",
  on_site: "人員抵達",
  processing: "處理中",
  resolved: "已完成",
  closed: "已結案",
  dismissed: "不成案",
};

export const PHASE_OF: Record<CaseStatus, Phase> = {
  reported: "pending",
  verifying: "pending",
  threshold_reached: "pending",
  awaiting_dispatch: "pending",
  assigned: "active",
  en_route: "active",
  on_site: "active",
  processing: "active",
  resolved: "done",
  closed: "done",
  dismissed: "dismissed",
};

export const PHASE_LABEL: Record<Phase, string> = {
  pending: "待處理",
  active: "處理中",
  done: "已完成",
  dismissed: "不成案",
};

export const PHASE_COLOR: Record<Phase, string> = {
  pending: "var(--st-pending)",
  active: "var(--st-active)",
  done: "var(--st-done)",
  dismissed: "var(--st-dismissed)",
};

export const PHASE_HEX: Record<Phase, string> = {
  pending: "#b54708",
  active: "#1d4ed8",
  done: "#067647",
  dismissed: "#667085",
};

export const ROLE_LABEL: Record<string, string> = {
  citizen: "一般民眾",
  village_chief: "村里長",
  disaster_officer: "防災士",
  volunteer: "志工",
  community_org: "社區組織",
  agency: "公務單位",
};

export const HAZARD_LABEL: Record<string, string> = {
  typhoon: "颱風",
  heavy_rain: "豪雨",
  flood: "淹水",
  landslide: "土石流",
  earthquake: "地震",
  barrier_lake: "堰塞湖",
};

export const CATEGORY_LABEL: Record<string, string> = {
  road_collapse: "道路坍方",
  road_blocked: "道路中斷",
  flooding: "積淹水",
  landslide: "土石流",
  trapped_person: "人員受困",
  bridge_damage: "橋梁受損",
  fallen_tree: "倒木",
  power_outage: "停電",
  water_outage: "停水",
  building_damage: "建築損害",
  fire: "火災",
  gas_leak: "瓦斯外洩",
  embankment_damage: "堤防受損",
  medical_need: "醫療需求",
  other: "其他",
};

// category → map layer (mirrors app/domain/categories.py)
export const CATEGORY_LAYER: Record<string, string> = {
  road_collapse: "road_damage",
  road_blocked: "road_damage",
  bridge_damage: "road_damage",
  fallen_tree: "road_damage",
  flooding: "flooding",
  embankment_damage: "flooding",
  landslide: "landslide",
  trapped_person: "trapped_people",
  medical_need: "trapped_people",
  power_outage: "lifeline",
  water_outage: "lifeline",
  building_damage: "building_damage",
  fire: "building_damage",
  gas_leak: "building_damage",
  other: "other",
};

export interface LayerMeta {
  key: string;
  label: string;
  hex: string;
  kind: "internal" | "category" | "official";
  glyph?: string; // single CJK glyph for square pins
}

export const LAYERS: Record<string, LayerMeta> = {
  incident_cases: { key: "incident_cases", label: "正式案件", hex: "#0b2545", kind: "internal" },
  report_clusters: { key: "report_clusters", label: "多人回報聚類", hex: "#475467", kind: "internal" },
  citizen_reports: { key: "citizen_reports", label: "民眾通報", hex: "#667085", kind: "internal" },
  heatmap: { key: "heatmap", label: "災情熱區", hex: "#d92d20", kind: "internal" },
  government_processing: { key: "government_processing", label: "政府處理中", hex: "#1d4ed8", kind: "internal" },
  flooding: { key: "flooding", label: "積淹水", hex: "#2563eb", kind: "category" },
  road_damage: { key: "road_damage", label: "道路災害", hex: "#ea580c", kind: "category" },
  landslide: { key: "landslide", label: "土石流", hex: "#ca8a04", kind: "category" },
  trapped_people: { key: "trapped_people", label: "人員受困", hex: "#be123c", kind: "category" },
  building_damage: { key: "building_damage", label: "建築損害", hex: "#7c3aed", kind: "category" },
  lifeline: { key: "lifeline", label: "維生管線", hex: "#0d9488", kind: "category" },
  other: { key: "other", label: "其他", hex: "#667085", kind: "category" },
  shelter: { key: "shelter", label: "避難收容", hex: "#067647", kind: "official", glyph: "收" },
  fire_station: { key: "fire_station", label: "消防單位", hex: "#9f1239", kind: "official", glyph: "消" },
  official_alert: { key: "official_alert", label: "官方警戒", hex: "#c2410c", kind: "official", glyph: "警" },
  rainfall: { key: "rainfall", label: "雨量", hex: "#1d4ed8", kind: "official", glyph: "雨" },
  water: { key: "water", label: "河川水情", hex: "#0369a1", kind: "official", glyph: "水" },
  radar: { key: "radar", label: "雷達回波", hex: "#334155", kind: "official", glyph: "雷" },
  debris_flow: { key: "debris_flow", label: "土石流潛勢溪流", hex: "#b45309", kind: "official", glyph: "溪" },
  landslide_zone: { key: "landslide_zone", label: "崩塌潛勢區", hex: "#7c2d12", kind: "official", glyph: "崩" },
  road_traffic: { key: "road_traffic", label: "路況 CCTV", hex: "#155e75", kind: "official", glyph: "路" },
  reservoir: { key: "reservoir", label: "水庫水情", hex: "#0e7490", kind: "official", glyph: "庫" },
  population: { key: "population", label: "人口分布", hex: "#64748b", kind: "official", glyph: "人" },
  power_outage: { key: "power_outage", label: "計畫停電", hex: "#1f2937", kind: "official", glyph: "電" },
};

export const OFFICIAL_LAYERS = ["official_alert", "radar", "rainfall", "water", "reservoir", "debris_flow", "landslide_zone", "road_traffic", "population", "power_outage", "shelter", "fire_station"];

export function layerHex(key: string | undefined | null): string {
  return (key && LAYERS[key]?.hex) || "#667085";
}

export function categoryHex(category: string): string {
  return layerHex(CATEGORY_LAYER[category] || "other");
}

export const EVENT_LABEL: Record<string, string> = {
  "report.received": "民眾回報",
  threshold_reached: "達到案件成立門檻",
  "case.created": "正式成案",
  status_changed: "狀態更新",
  public_update: "處理進度",
  internal_note: "內部備註",
  assignment_changed: "改派處理單位",
  dispatch_notified: "已通報處理單位",
};

export const DOMAIN_LABEL: Record<string, string> = {
  reporting: "災情通報",
  processing: "案件處理",
  dispatch: "派工調度",
  visualization: "災情視覺化",
  official_data: "官方資料",
  notification: "通知推播",
  privacy: "隱私保護",
  public_transparency: "公開透明",
  analytics: "統計分析",
};

export const MODULE_TYPE_LABEL: Record<string, string> = {
  feature: "功能",
  layer: "圖層",
  processor: "處理引擎",
  action: "動作",
  connector: "資料介接",
};

export const TREND_LABEL: Record<string, string> = {
  rising: "通報增加中",
  falling: "通報趨緩",
  steady: "情勢平穩",
};

// ── responders / vehicles ──────────────────────────────────────────────
export const UNIT_KIND_LABEL: Record<string, string> = {
  fire: "消防單位",
  police: "警察單位",
  town_office: "鄉鎮公所",
  highway: "公路局工務段",
  river: "水利署河川分署",
  slope: "水保署分署",
  power: "台電",
  water_supply: "自來水公司",
};

// route / vehicle colour by the responsible unit kind (validated set)
export const UNIT_KIND_HEX: Record<string, string> = {
  fire: "#be123c",
  police: "#2563eb",
  town_office: "#ea580c",
  highway: "#ea580c",
  river: "#0d9488",
  slope: "#ca8a04",
  power: "#7c3aed",
  water_supply: "#0d9488",
};

export const VEHICLE_LABEL: Record<string, string> = {
  fire_engine: "消防車",
  ambulance: "救護車",
  police_car: "警車",
  works_truck: "工程車",
};

export const VEHICLE_GLYPH: Record<string, string> = {
  fire_engine: "消",
  ambulance: "救",
  police_car: "警",
  works_truck: "工",
};

export const VEHICLE_HEX: Record<string, string> = {
  fire_engine: "#be123c",
  ambulance: "#dc2626",
  police_car: "#2563eb",
  works_truck: "#ea580c",
};

export const VEHICLE_STATUS_LABEL: Record<string, string> = {
  preparing: "整備出發",
  en_route: "前往中",
  on_site: "已抵達",
  returning: "返隊中",
  live: "即時位置",
};
