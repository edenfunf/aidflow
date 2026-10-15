"use client";

// The 3D situation map (MapLibre GL). Touches `window` — import via
// next/dynamic with { ssr: false }.
//
// Basemap: OpenFreeMap "liberty" (vector, no key) with labels forced to
// Chinese; terrain + hillshade from AWS Terrain Tiles (terrarium, no key).
// Data is encoded into form, not text:
//   - formal cases      → an upright pin (DOM marker: faces the camera, tip on
//                         the terrain; colour = category, number = reporters,
//                         corner dot = status) over a ground disc draped on the
//                         terrain whose size grows with the reporter count
//   - report clusters   → hollow rings (below threshold)
//   - citizen reports   → small dots
//   - density           → heat layer draped on the terrain
//   - rainfall stations → columns by 24h accumulation; water stations →
//                         discs by alert level; CAP alerts → polygons
// A time cutoff lets the portal replay the last 24 hours.

import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, LayerSpecification, Map as MLMap, StyleSpecification } from "maplibre-gl";
import type { GeoFeature, LayerResponse, MapFeature } from "@/lib/types";
import { LAYERS, PHASE_HEX, layerHex } from "@/lib/labels";
import { clusterPopup, esc, officialPopup, reportPopup } from "@/lib/mapPopups";
import { BASEMAP_ATTRIBUTION, TERRAIN_TILES, ZH_LABEL, collapseAttribution, loadStyle } from "@/lib/mapStyle";
import { categoryIcon } from "@/lib/categoryIcons";
import { api } from "@/lib/api";

export interface TerrainMapProps {
  center: [number, number]; // [lat, lon]
  zoom: number;
  features: MapFeature[];
  officialLayers?: Record<string, LayerResponse | undefined>;
  visible: Record<string, boolean>;
  enabledLayers: string[];
  selectedId?: string | null;
  onSelect?: (feature: MapFeature | GeoFeature | null) => void;
  timeCutoff?: number | null; // epoch ms; features created after it are hidden
  threeD?: boolean;
  fitToData?: boolean;
  /** showcase mode: the camera slowly circles the scene; pauses on interaction */
  orbit?: boolean;
  /** no navigation controls — hero / wall / embedded views */
  minimal?: boolean;
  /** screen-space padding (px) kept clear when fitting to data; defaults suit the portal layout */
  fitPadding?: { top: number; bottom: number; left: number; right: number };
  /** keep this many pixels on the left out of the camera's reckoning (hero card) */
  padLeft?: number;
  className?: string;
  onReady?: () => void;
}


const WATER_STATUS_HEX: Record<string, string> = { alert1: "#7a0c16", alert2: "#d92d20", alert3: "#dc8a0c", normal: "#0369a1", unknown: "#98a2b3" };
const RAIN_LEVEL_HEX: Record<string, string> = { extreme: "#312e81", torrential: "#3730a3", heavy: "#1d4ed8", moderate: "#3b82f6", light: "#93c5fd" };

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function ts(iso: string | null | undefined): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : 0;
}

/** Regular polygon (metres) around a point — the footprint of a column. */
function hexagon(lon: number, lat: number, radiusM: number): number[][] {
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring: number[][] = [];
  for (let i = 0; i <= 6; i++) {
    const a = (Math.PI / 3) * i + Math.PI / 6;
    ring.push([lon + Math.cos(a) * dLon, lat + Math.sin(a) * dLat]);
  }
  return ring;
}

function categoryVisible(visible: Record<string, boolean>, enabled: string[], catLayer: string | undefined): boolean {
  if (!catLayer || !enabled.includes(catLayer)) return true;
  return visible[catLayer] !== false;
}

interface Built {
  reports: GeoJSON.FeatureCollection;
  clusters: GeoJSON.FeatureCollection;
  casePts: GeoJSON.FeatureCollection;
  heat: GeoJSON.FeatureCollection;
}

/** Column footprint in metres for a given zoom — wide enough to read at county scale, tight at street scale. */
function footprintM(zoom: number): number {
  return Math.min(900, Math.max(60, 75 * Math.pow(2, 13 - zoom)));
}

function buildInternal(features: MapFeature[], visible: Record<string, boolean>, enabled: string[], cutoff: number | null | undefined, selectedId: string | null | undefined, zoom: number): Built {
  const reports: GeoJSON.Feature[] = [];
  const clusters: GeoJSON.Feature[] = [];
  const casePts: GeoJSON.Feature[] = [];
  const heat: GeoJSON.Feature[] = [];
  const govOnly = visible.government_processing === true;
  const showCases = visible.incident_cases !== false;
  const showClusters = visible.report_clusters !== false;
  const showReports = visible.citizen_reports !== false;

  for (const f of features) {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    if (!categoryVisible(visible, enabled, p.category_layer)) continue;
    const created = ts(p.created_at || p.first_reported_at);
    if (cutoff && created > cutoff) continue;
    const color = layerHex(p.category_layer);
    const selected = selectedId === f.id;
    if (p.layer === "incident_cases") {
      const dimmed = govOnly && p.phase !== "active";
      heat.push({ type: "Feature", geometry: f.geometry, properties: { w: p.severity === "critical" ? 1 : p.severity === "high" ? 0.8 : 0.5 } });
      if (!showCases) continue;
      const n = Math.max(1, Number(p.unique_reporter_count) || 1);
      const base = { ...p, id: f.id, color, phaseColor: PHASE_HEX[p.phase as keyof typeof PHASE_HEX] || "#667085", n, selected: selected ? 1 : 0, dim: dimmed ? 1 : 0, critical: p.severity === "critical" && p.phase !== "done" ? 1 : 0, pulse: (p.severity === "critical" || p.phase === "pending") && p.phase !== "done" && !dimmed ? 1 : 0 };
      casePts.push({ type: "Feature", geometry: f.geometry, properties: base });
    } else if (p.layer === "report_clusters") {
      heat.push({ type: "Feature", geometry: f.geometry, properties: { w: 0.4 } });
      if (!showClusters || govOnly) continue;
      clusters.push({ type: "Feature", geometry: f.geometry, properties: { ...p, id: f.id, color, n: p.unique_reporter_count, selected: selected ? 1 : 0 } });
    } else if (p.layer === "citizen_reports") {
      heat.push({ type: "Feature", geometry: f.geometry, properties: { w: 0.3 } });
      if (!showReports || govOnly) continue;
      reports.push({ type: "Feature", geometry: f.geometry, properties: { ...p, id: f.id, color, selected: selected ? 1 : 0 } });
    }
  }
  const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
  return { reports: fc(reports), clusters: fc(clusters), casePts: fc(casePts), heat: fc(heat) };
}

const RESERVOIR_HEX: Record<string, string> = { releasing: "#b91c1c", high: "#d97706", normal: "#0e7490", low: "#64748b", unknown: "#94a3b8" };
const DEBRIS_ALERT_HEX: Record<string, string> = { red: "#dc2626", yellow: "#f59e0b" };
const DEBRIS_RISK_HEX: Record<string, string> = { 高: "#b45309", 中: "#c2871b", 低: "#d4a04a", 持續觀察: "#a16207" };

interface RadarFrame {
  url: string;
  coords: number[][];
  time: string;
  stamp: string;
}

function officialToGeoJSON(layer: LayerResponse | undefined, zoom: number): { points: GeoJSON.FeatureCollection; polys: GeoJSON.FeatureCollection; cols: GeoJSON.FeatureCollection; lines: GeoJSON.FeatureCollection; rasters: RadarFrame[] } {
  const points: GeoJSON.Feature[] = [];
  const polys: GeoJSON.Feature[] = [];
  const cols: GeoJSON.Feature[] = [];
  const lines: GeoJSON.Feature[] = [];
  const rasters: RadarFrame[] = [];
  for (const f of layer?.features || []) {
    const p = f.properties || {};
    if (f.type === "Raster") {
      rasters.push({ url: api.mediaUrl(String(p.image_url)), coords: f.coordinates, time: String(p.time || ""), stamp: String(p.stamp || "") });
    } else if (f.type === "Polygon") {
      let color = LAYERS[f.layer]?.hex || "#c2410c";
      let opacity = 0.14;
      if (f.layer === "debris_flow" || f.layer === "landslide_zone") {
        color = DEBRIS_ALERT_HEX[p.alert] || (f.layer === "landslide_zone" ? "#7c2d12" : DEBRIS_RISK_HEX[p.risk] || "#b45309");
        opacity = p.alert ? 0.38 : f.layer === "landslide_zone" ? 0.22 : 0.16;
      }
      polys.push({ type: "Feature", geometry: { type: "Polygon", coordinates: f.coordinates }, properties: { ...p, id: f.id, layer: f.layer, color, opacity, alerted: p.alert ? 1 : 0 } });
    } else if (f.type === "LineString") {
      const alert = p.alert as string | undefined;
      const color = DEBRIS_ALERT_HEX[alert || ""] || DEBRIS_RISK_HEX[p.risk] || LAYERS[f.layer]?.hex || "#b45309";
      lines.push({ type: "Feature", geometry: { type: "LineString", coordinates: f.coordinates }, properties: { ...p, id: f.id, layer: f.layer, color, width: alert === "red" ? 4.5 : alert === "yellow" ? 3.5 : p.risk === "高" ? 2.2 : 1.6, alerted: alert ? 1 : 0 } });
      // a potential stream is only a few hundred metres long: at county zoom the
      // line is a pixel, so its downstream end also gets a small dot (risk-sized)
      // only an *alerted* stream earns a marker at county zoom; the static
      // potential network is context that appears once the viewer zooms in
      if (f.layer === "debris_flow" && alert && Array.isArray(f.coordinates) && f.coordinates.length) {
        const [lon, lat] = f.coordinates[f.coordinates.length - 1];
        points.push({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { ...p, id: f.id, layer: f.layer, color, size: 9, label: `${p.town || ""}${alert === "red" ? " 紅色警戒" : " 黃色警戒"}`, glyph: "警" } });
      }
    } else if (f.type === "Point") {
      const [lon, lat] = f.coordinates as [number, number];
      let color = LAYERS[f.layer]?.hex || "#667085";
      let size = 6;
      let label = "";
      if (f.layer === "water") {
        color = WATER_STATUS_HEX[p.status] || WATER_STATUS_HEX.unknown;
        size = String(p.status).startsWith("alert") ? 9 : 6;
      } else if (f.layer === "rainfall") {
        color = RAIN_LEVEL_HEX[p.level] || RAIN_LEVEL_HEX.light;
        const mm = Math.max(0, Number(p.rain_24h_mm) || 0);
        cols.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [hexagon(lon, lat, footprintM(zoom) * 0.7)] }, properties: { ...p, id: f.id, layer: f.layer, color, height: 80 + mm * 4 } });
        size = 5;
      } else if (f.layer === "official_alert") {
        size = 9;
      } else if (f.layer === "reservoir") {
        color = RESERVOIR_HEX[p.status] || RESERVOIR_HEX.unknown;
        size = p.status === "releasing" ? 11 : 9;
        label = `${p.name}\n${p.storage_pct != null ? `${p.storage_pct}%` : ""}`;
      } else if (f.layer === "population") {
        const pop = Number(p.population) || 0;
        size = Math.max(6, Math.min(30, 4 + Math.sqrt(pop) / 14));
        label = `${p.town}\n${(pop / 10000).toFixed(1)} 萬人`;
      } else if (f.layer === "road_traffic") {
        if (p.kind !== "cctv") continue; // road news is a feed, not a dot at the county centre
        size = 5;
      } else if (f.layer === "power_outage") {
        size = Math.min(14, 5 + Number(p.count || 0));
        label = `${p.town} 停電 ${p.count}`;
      } else if (f.layer === "debris_flow") {
        color = DEBRIS_ALERT_HEX[p.alert] || "#b45309";
        size = 9;
      }
      points.push({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { ...p, id: f.id, layer: f.layer, color, size, label, glyph: LAYERS[f.layer]?.glyph || "" } });
    }
  }
  const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
  return { points: fc(points), polys: fc(polys), cols: fc(cols), lines: fc(lines), rasters };
}

// ── radar replay: the cached CWA frames cycle on the image source ──
const radarState = new WeakMap<MLMap, { frames: RadarFrame[]; idx: number; last: number; on: boolean; el: HTMLDivElement | null }>();

function radarStampEl(map: MLMap): HTMLDivElement {
  const st = radarState.get(map)!;
  if (st.el) return st.el;
  const el = document.createElement("div");
  el.className = "af-radar-stamp";
  map.getContainer().appendChild(el);
  st.el = el;
  return el;
}

function syncRadar(map: MLMap, frames: RadarFrame[], on: boolean): void {
  let st = radarState.get(map);
  if (!st) {
    st = { frames: [], idx: 0, last: 0, on: false, el: null };
    radarState.set(map, st);
  }
  st.frames = frames;
  st.on = on && frames.length > 0;
  st.idx = Math.min(st.idx, Math.max(0, frames.length - 1));
  const latest = frames[frames.length - 1];
  if (latest && !map.getSource("af-radar")) {
    map.addSource("af-radar", { type: "image", url: latest.url, coordinates: latest.coords as [[number, number], [number, number], [number, number], [number, number]] });
    map.addLayer({ id: "af-radar", type: "raster", source: "af-radar", paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.42, 12, 0.36, 14, 0.25], "raster-fade-duration": 0, "raster-resampling": "linear" } }, map.getLayer("af-reports") ? "af-reports" : undefined);
    st.idx = frames.length - 1;
  }
  if (map.getLayer("af-radar")) map.setLayoutProperty("af-radar", "visibility", st.on ? "visible" : "none");
  const el = radarStampEl(map);
  el.style.display = st.on ? "block" : "none";
  if (st.on) radarShow(map, st.idx);
}

function radarShow(map: MLMap, idx: number): void {
  const st = radarState.get(map);
  const f = st?.frames[idx];
  const src = map.getSource("af-radar") as maplibregl.ImageSource | undefined;
  if (!st || !f || !src) return;
  src.updateImage({ url: f.url, coordinates: f.coords as [[number, number], [number, number], [number, number], [number, number]] });
  const t = f.time ? new Date(f.time) : null;
  const hhmm = t && !Number.isNaN(t.getTime()) ? t.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false }) : f.stamp;
  radarStampEl(map).textContent = `雷達回波 ${hhmm}${st.frames.length > 1 ? `　${idx + 1}/${st.frames.length}` : ""}　中央氣象署`;
}

function radarTick(map: MLMap, now: number): void {
  const st = radarState.get(map);
  if (!st || !st.on || st.frames.length < 2) return;
  const hold = st.idx === st.frames.length - 1 ? 1800 : 650;
  if (now - st.last < hold) return;
  st.last = now;
  st.idx = (st.idx + 1) % st.frames.length;
  radarShow(map, st.idx);
}

const OFFICIAL_KEYS = ["official_alert", "rainfall", "water", "reservoir", "debris_flow", "landslide_zone", "road_traffic", "population", "power_outage", "shelter", "fire_station"];
const LABELLED_KEYS = ["reservoir", "population", "power_outage", "debris_flow"];

// ── atmosphere: sky + distance fog give the 3D view its depth ──
const SKY: maplibregl.SkySpecification = {
  "sky-color": "#c9dcef",
  "horizon-color": "#e9eff5",
  "fog-color": "#e3e9ef",
  "fog-ground-blend": 0.42,
  "horizon-fog-blend": 0.65,
  "sky-horizon-blend": 0.75,
  "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 11, 1, 13.5, 0],
};
const REDUCED_MOTION = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
// one DEM source feeds both hillshade and the terrain mesh: a second source
// doubled the tile downloads on first paint for a quality gain nobody sees
const TERRAIN = { source: "terrain", exaggeration: 1.3 };
const PITCH_3D = 46;
/** Cap the backing-store resolution: on a 2K display at 125 % scaling the
 * terrain pass was filling a 3200-px-wide canvas every frame. 1.25 keeps
 * text crisp enough while cutting fill cost by up to half. */
const PIXEL_RATIO = typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 1.25) : 1;

// ── upright pins (DOM markers: always face the camera, tip on the terrain) ──
const pinStore = new WeakMap<MLMap, Map<string, maplibregl.Marker>>();

// ── case beacons: a ground point, a thin stem and a floating badge. In a
// pitched 3D view the stem ties the badge to the exact spot on the terrain
// while the badge (category icon · reporter count · status ring) stays
// upright and readable, never hiding the ground under the incident. ──
function pinSvg(p: Record<string, any>): string {
  const sev = String(p.severity || "medium");
  const w = sev === "critical" ? 46 : sev === "high" ? 42 : 38;
  const h = Math.round(w * 1.6);
  const n = esc(p.n ?? "");
  const color = esc(p.color);
  const phase = esc(p.phaseColor);
  return `<svg width="${w}" height="${h}" viewBox="0 0 40 64" aria-hidden="true">
    <g class="af-beacon-stem">
      <path d="M20 62V33" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/>
      <path d="M20 62V33" stroke="#1d2939" stroke-width="1.4" stroke-linecap="round"/>
      <circle cx="20" cy="61" r="2.6" fill="#1d2939" stroke="#fff" stroke-width="1.6"/>
    </g>
    <g class="af-beacon-head">
      <circle class="af-beacon-ring" cx="20" cy="18" r="16" fill="none" stroke="${phase}" stroke-width="2.4"/>
      <circle cx="20" cy="18" r="13.2" fill="${color}" stroke="#fff" stroke-width="2.2"/>
      <g transform="translate(11.5 9.5) scale(0.71)" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" color="#fff">${categoryIcon(String(p.category || "other"))}</g>
      <circle cx="31.5" cy="6.5" r="6.4" fill="#101828" stroke="#fff" stroke-width="1.6"/>
      <text x="31.5" y="9.4" text-anchor="middle" font-size="8.6" font-weight="700" fill="#fff" font-family="inherit">${n}</text>
    </g>
  </svg>`;
}

function syncPins(map: MLMap, casePts: GeoJSON.FeatureCollection): void {
  let store = pinStore.get(map);
  if (!store) {
    store = new Map();
    pinStore.set(map, store);
  }
  const seen = new Set<string>();
  for (const f of casePts.features) {
    const p = f.properties as Record<string, any>;
    const id = String(p.id);
    seen.add(id);
    const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
    const flags: Record<string, boolean> = { "af-pin-selected": !!p.selected, "af-pin-critical": !!p.critical, "af-pin-dim": !!p.dim };
    let m = store.get(id);
    if (!m) {
      const el = document.createElement("div");
      // never overwrite className later: MapLibre adds its own positioning classes
      el.classList.add("af-pin", "af-pin-enter");
      el.addEventListener("animationend", () => el.classList.remove("af-pin-enter"), { once: true });
      for (const [k, on] of Object.entries(flags)) el.classList.toggle(k, on);
      el.innerHTML = pinSvg(p);
      el.title = `${p.title || ""} · ${p.status_label || ""}`;
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        el.dispatchEvent(new CustomEvent("af-pin-click", { bubbles: true, detail: id }));
      });
      m = new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([lon, lat]).addTo(map);
      // MapLibre tests every marker against the terrain depth buffer with a
      // gl.readPixels (a GPU stall) ~10×/s; beacons are meant to stay visible
      // over ridges anyway, so skip that check entirely
      (m as unknown as { _updateOpacity: () => void })._updateOpacity = () => undefined;
      el.style.opacity = "1";
      store.set(id, m);
    } else {
      const el = m.getElement();
      for (const [k, on] of Object.entries(flags)) el.classList.toggle(k, on);
      const next = pinSvg(p);
      if (el.innerHTML !== next) el.innerHTML = next;
      m.setLngLat([lon, lat]);
    }
  }
  for (const [id, m] of store) {
    if (!seen.has(id)) {
      m.remove();
      store.delete(id);
    }
  }
}


function TerrainMapImpl({
  center,
  zoom,
  features,
  officialLayers = {},
  visible,
  enabledLayers,
  selectedId,
  onSelect,
  timeCutoff = null,
  threeD = true,
  fitToData = false,
  orbit = false,
  minimal = false,
  padLeft = 0,
  fitPadding,
  className = "",
  onReady,
}: TerrainMapProps) {
  const orbitRef = useRef(orbit);
  orbitRef.current = orbit;
  const threeDRef = useRef(threeD);
  threeDRef.current = threeD;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const readyRef = useRef(false);
  const fittedRef = useRef(false);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const rafRef = useRef<number | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const featuresRef = useRef(features);
  featuresRef.current = features;
  const officialRef = useRef(officialLayers);
  officialRef.current = officialLayers;

  const [zoomBucket, setZoomBucket] = useState(zoom);
  const [ready, setReady] = useState(false);
  const built = useMemo(() => buildInternal(features, visible, enabledLayers, timeCutoff, selectedId, zoomBucket), [features, visible, enabledLayers, timeCutoff, selectedId, zoomBucket]);
  // ── init ────────────────────────────────────────────────────────────
  // the hero card covers the left of the viewport: tell the camera to ignore
  // that strip so the subject stays in the visible half at any window width
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.setPadding({ top: 0, right: 0, bottom: 0, left: padLeft });
  }, [padLeft]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;
    let map: MLMap | null = null;
    loadStyle().then((style) => {
      if (cancelled || !containerRef.current) return;
      map = createMap(style);
    });
    const createMap = (style: StyleSpecification | string): MLMap => {
    const map = new maplibregl.Map({
      container: containerRef.current!,
      style,
      center: [center[1], center[0]],
      // opening move: start high and flat, then sweep down into the 3D view
      // (the fit-to-data effect finishes the move)
      zoom: fitToData && !REDUCED_MOTION ? Math.max(zoom - 1.6, 6) : zoom,
      pitch: threeD && (!fitToData || REDUCED_MOTION) ? PITCH_3D : 0,
      bearing: threeD && (!fitToData || REDUCED_MOTION) ? -12 : 0,
      maxPitch: 60,
      pixelRatio: PIXEL_RATIO,
      attributionControl: false,
      canvasContextAttributes: { antialias: false },
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: BASEMAP_ATTRIBUTION }), "bottom-right");
    if (!minimal) map.addControl(new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true }), "bottom-right");
    mapRef.current = map;
    if (padLeft > 0) map.setPadding({ top: 0, right: 0, bottom: 0, left: padLeft });
    if (process.env.NODE_ENV !== "production") (window as any).__aidflowMap = map; // dev-only debugging hook

    map.on("style.load", () => {
      const style = map.getStyle() as StyleSpecification;
      let font: string[] = ["Noto Sans Regular"];
      for (const l of style.layers) {
        if (l.type === "symbol") {
          const tf = map.getLayoutProperty(l.id, "text-field");
          if (tf) map.setLayoutProperty(l.id, "text-field", ZH_LABEL);
          const f = map.getLayoutProperty(l.id, "text-font");
          if (Array.isArray(f) && f.length) font = f as string[];
        }
      }
      const firstSymbol = style.layers.find((l) => l.type === "symbol")?.id;
      if (!firstSymbol) font = ["Noto Sans Regular"];

      map.addSource("terrain", { type: "raster-dem", tiles: [TERRAIN_TILES], tileSize: 256, encoding: "terrarium", maxzoom: 15, attribution: "" });
      map.addLayer({ id: "af-hillshade", type: "hillshade", source: "terrain", paint: { "hillshade-exaggeration": 0.5, "hillshade-shadow-color": "#5b6472", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#8b95a5" } }, firstSymbol);
      if (threeD) {
        map.setTerrain(TERRAIN);
        map.setSky(SKY);
      }

      const src = (id: string) => map.addSource(id, { type: "geojson", data: EMPTY });
      ["af-heat", "af-reports", "af-clusters", "af-case-pts"].forEach(src);
      OFFICIAL_KEYS.forEach((k) => {
        src(`af-off-${k}-pts`);
        src(`af-off-${k}-polys`);
        src(`af-off-${k}-cols`);
        src(`af-off-${k}-lines`);
      });

      const layers: LayerSpecification[] = [
        { id: "af-heat", type: "heatmap", source: "af-heat", layout: { visibility: "none" }, paint: { "heatmap-weight": ["get", "w"], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 14, 2], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 18, 14, 40], "heatmap-opacity": 0.65, "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "#fde68a", 0.5, "#f97316", 0.8, "#dc2626", 1, "#7f1d1d"] } },
        // official polygons (CAP alert areas)
        ...OFFICIAL_KEYS.map<LayerSpecification>((k) => ({ id: `af-off-${k}-polys`, type: "fill", source: `af-off-${k}-polys`, paint: { "fill-color": ["coalesce", ["get", "color"], LAYERS[k]?.hex || "#c2410c"], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, ["case", ["==", ["get", "alerted"], 1], ["coalesce", ["get", "opacity"], 0.14], ["case", ["has", "kind"], 0, ["coalesce", ["get", "opacity"], 0.14]]], 12.5, ["coalesce", ["get", "opacity"], 0.14]], "fill-outline-color": ["coalesce", ["get", "color"], LAYERS[k]?.hex || "#c2410c"] } })),
        // official lines (debris-flow potential streams): a soft glow under alerted streams, then the stream itself
        ...OFFICIAL_KEYS.map<LayerSpecification>((k) => ({ id: `af-off-${k}-lines-glow`, type: "line", source: `af-off-${k}-lines`, filter: ["==", ["get", "alerted"], 1], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": ["+", ["get", "width"], 7], "line-opacity": 0.22, "line-blur": 2 } })),
        ...OFFICIAL_KEYS.map<LayerSpecification>((k) => ({ id: `af-off-${k}-lines`, type: "line", source: `af-off-${k}-lines`, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "color"], "line-width": ["interpolate", ["linear"], ["zoom"], 9, ["*", ["get", "width"], 0.7], 13, ["get", "width"], 16, ["*", ["get", "width"], 1.8]], "line-opacity": ["interpolate", ["linear"], ["zoom"], 10.5, ["case", ["==", ["get", "alerted"], 1], 0.95, 0], 12.5, ["case", ["==", ["get", "alerted"], 1], 0.95, 0.8]] } })),
        { id: "af-off-rainfall-cols", type: "fill-extrusion", source: "af-off-rainfall-cols", paint: { "fill-extrusion-color": ["get", "color"], "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 8, ["*", ["get", "height"], 10], 12, ["*", ["get", "height"], 2], 14, ["get", "height"]], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.7 } },
        // citizen reports
        { id: "af-reports", type: "circle", source: "af-reports", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3, 14, 6], "circle-color": ["get", "color"], "circle-opacity": 0.85, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } },
        // clusters below threshold: hollow rings + count
        { id: "af-clusters", type: "circle", source: "af-clusters", paint: { "circle-radius": 11, "circle-color": "#ffffff", "circle-opacity": 0.92, "circle-stroke-color": ["get", "color"], "circle-stroke-width": 2.5 } },
        { id: "af-clusters-label", type: "symbol", source: "af-clusters", layout: { "text-field": ["to-string", ["get", "n"]], "text-font": font, "text-size": 11, "text-allow-overlap": true }, paint: { "text-color": ["get", "color"] } },
        // cases: ground disc (size = reporters, colour = category, rim = status)
        // draped on the terrain; the upright pin is a DOM marker (see below)
        { id: "af-case-pulse", type: "circle", source: "af-case-pts", filter: ["==", ["get", "pulse"], 1], paint: { "circle-pitch-alignment": "map", "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 14, 12, 22, 15, 34], "circle-color": ["case", ["==", ["get", "critical"], 1], "#be123c", ["get", "phaseColor"]], "circle-opacity": 0.12, "circle-stroke-color": ["case", ["==", ["get", "critical"], 1], "#be123c", ["get", "phaseColor"]], "circle-stroke-width": 1.5, "circle-stroke-opacity": 0.45 } },
        { id: "af-case-disc", type: "circle", source: "af-case-pts", paint: { "circle-pitch-alignment": "map", "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, ["+", 5, ["*", ["get", "n"], 1.5]], 11, ["+", 10, ["*", ["get", "n"], 3]], 14, ["+", 26, ["*", ["get", "n"], 7]], 16, ["+", 60, ["*", ["get", "n"], 16]]], "circle-color": ["get", "color"], "circle-opacity": ["case", ["==", ["get", "dim"], 1], 0.08, 0.22], "circle-stroke-color": ["get", "phaseColor"], "circle-stroke-width": ["case", ["==", ["get", "selected"], 1], 3, 2], "circle-stroke-opacity": ["case", ["==", ["get", "dim"], 1], 0.3, 0.95] } },
        { id: "af-case-name", type: "symbol", source: "af-case-pts", minzoom: 11.5, layout: { "text-field": ["get", "title"], "text-font": font, "text-size": 12, "text-anchor": "top", "text-offset": [0, 1.2], "text-optional": true }, paint: { "text-color": "#101828", "text-halo-color": "#ffffff", "text-halo-width": 1.4 } },
        // official points
        ...OFFICIAL_KEYS.filter((k) => k !== "rainfall").map<LayerSpecification>((k) => ({ id: `af-off-${k}-pts`, type: "circle", source: `af-off-${k}-pts`, paint: { "circle-radius": ["get", "size"], "circle-color": ["get", "color"], "circle-opacity": k === "population" ? 0.3 : 0.92, "circle-stroke-color": k === "population" ? ["get", "color"] : "#ffffff", "circle-stroke-width": k === "debris_flow" ? 0.8 : 1.5 } })),
        { id: "af-off-rainfall-pts", type: "circle", source: "af-off-rainfall-pts", paint: { "circle-radius": 4, "circle-color": ["get", "color"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } },
        ...["shelter", "fire_station", "official_alert", "road_traffic", "debris_flow"].map<LayerSpecification>((k) => ({ id: `af-off-${k}-glyph`, type: "symbol", source: `af-off-${k}-pts`, layout: { "text-field": ["get", "glyph"], "text-font": font, "text-size": 9, "text-allow-overlap": true }, paint: { "text-color": "#ffffff" } })),
        // labelled official points (reservoir status, township population, outage counts)
        ...LABELLED_KEYS.map<LayerSpecification>((k) => ({ id: `af-off-${k}-label`, type: "symbol", source: `af-off-${k}-pts`, minzoom: 8.5, layout: { "text-field": ["get", "label"], "text-font": font, "text-size": 10.5, "text-anchor": "top", "text-offset": [0, 1.1], "text-optional": true, "text-line-height": 1.15 }, paint: { "text-color": "#1d2939", "text-halo-color": "#ffffff", "text-halo-width": 1.3 } })),
      ];
      // a thin white veil over the basemap so the data reads first; POI labels
      // only once the viewer is close enough for them to matter
      map.addSource("af-veil", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]] } } });
      map.addLayer({ id: "af-veil", type: "fill", source: "af-veil", paint: { "fill-color": "#ffffff", "fill-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.28, 12, 0.16, 14, 0.06] } });
      for (const l of style.layers) {
        if (l.type === "symbol" && /poi|housenum|place_other|place_hamlet|place_suburb|place_village|water_name_point|mountain/i.test(l.id)) {
          map.setLayerZoomRange(l.id, Math.max(12.5, (l as any).minzoom || 0), 24);
        }
      }
      layers.forEach((l) => map.addLayer(l));
      // interaction
      const interactive = ["af-case-disc", "af-clusters", "af-reports", ...OFFICIAL_KEYS.map((k) => `af-off-${k}-pts`), ...OFFICIAL_KEYS.map((k) => `af-off-${k}-polys`), ...OFFICIAL_KEYS.map((k) => `af-off-${k}-lines`), "af-off-rainfall-cols"];
      for (const id of interactive) {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
      map.on("click", (e: maplibregl.MapMouseEvent) => {
        const hits = map.queryRenderedFeatures(e.point, { layers: interactive.filter((id) => !!map.getLayer(id)) });
        const hit = hits[0];
        popupRef.current?.remove();
        if (!hit) {
          onSelectRef.current?.(null);
          return;
        }
        const props = hit.properties as Record<string, any>;
        let html = "";
        let picked: MapFeature | GeoFeature | null = null;
        if (hit.layer.id.startsWith("af-case")) {
          picked = featuresRef.current.find((f) => f.id === props.id) || null;
          onSelectRef.current?.(picked);
          return;
        } else if (hit.layer.id === "af-clusters") {
          html = clusterPopup(props);
          picked = featuresRef.current.find((f) => f.id === props.id) || null;
        } else if (hit.layer.id === "af-reports") {
          html = reportPopup(props);
          picked = featuresRef.current.find((f) => f.id === props.id) || null;
        } else {
          const key = props.layer as string;
          const parsed = { ...props, hazards: typeof props.hazards === "string" ? safeJson(props.hazards) : props.hazards };
          html = officialPopup({ layer: key, properties: parsed });
          picked = officialRef.current[key]?.features.find((f) => f.id === props.id) || null;
        }
        const lngLat = hit.geometry.type === "Point" ? (hit.geometry.coordinates as [number, number]) : [e.lngLat.lng, e.lngLat.lat];
        popupRef.current = new maplibregl.Popup({ closeButton: false, maxWidth: "280px", offset: 10 }).setLngLat(lngLat as [number, number]).setHTML(html).addTo(map);
        onSelectRef.current?.(picked);
      });

      map.getContainer().addEventListener("af-pin-click", (ev: Event) => {
        const id = (ev as CustomEvent<string>).detail;
        popupRef.current?.remove();
        onSelectRef.current?.(featuresRef.current.find((f) => f.id === id) || null);
      });

      // showcase orbit pauses whenever the viewer touches the map
      let orbitPausedUntil = 0;
      const pauseOrbit = () => {
        orbitPausedUntil = performance.now() + 7000;
      };
      const canvas = map.getCanvasContainer();
      ["mousedown", "wheel", "touchstart"].forEach((ev) => canvas.addEventListener(ev, pauseOrbit, { passive: true }));

      // camera orbit + radar replay
      let lastRadar = 0;
      let lastTick = performance.now();
      const tick = (now: number) => {
        const dt = Math.min(100, now - lastTick);
        lastTick = now;
        // isMoving() covers the v5 isEasing() case plus an in-progress gesture
        if (orbitRef.current && threeDRef.current && !REDUCED_MOTION && now > orbitPausedUntil && !map.isMoving()) {
          map.setBearing(map.getBearing() + 0.0012 * dt); // ≈ 1.2°/s, one lap in ~5 min
        }
        // while the user drags / zooms, nothing that re-bakes terrain tiles may
        // run: the gesture gets the whole frame budget. The ground pulse is
        // static under terrain (the beacon ring already pulses in CSS).
        const gesture = map.isMoving();
        if (now - lastRadar > 100) {
          lastRadar = now;
          if (!gesture) radarTick(map, now);
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);

      map.on("zoomend", () => setZoomBucket(Math.round(map.getZoom() * 2) / 2));
      // small embedded maps: keep the attribution collapsed to its (i) button
      if (minimal || map.getContainer().clientWidth < 700) collapseAttribution(map);
      readyRef.current = true;
      applyData();
      applyVisibility();
      setReady(true);
      onReady?.();
    });
    return map;
    };

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      popupRef.current?.remove();
      if (map) {
        pinStore.get(map)?.forEach((m) => m.remove());
        map.remove();
      }
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── data ────────────────────────────────────────────────────────────
  const pulseRef = useRef(0);
  const setSrc = (map: MLMap, id: string, data: GeoJSON.FeatureCollection) => (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data);

  const applyInternal = () => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    setSrc(map, "af-heat", built.heat);
    setSrc(map, "af-reports", built.reports);
    setSrc(map, "af-clusters", built.clusters);
    setSrc(map, "af-case-pts", built.casePts);
    syncPins(map, built.casePts);
    pulseRef.current = built.casePts.features.filter((f) => (f.properties as any)?.pulse === 1).length;
  };
  const applyOfficial = () => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    for (const k of OFFICIAL_KEYS) {
      const on = visible[k] === true && enabledLayers.includes(k);
      const g = on ? officialToGeoJSON(officialLayers[k], zoomBucket) : { points: EMPTY, polys: EMPTY, cols: EMPTY, lines: EMPTY, rasters: [] };
      setSrc(map, `af-off-${k}-pts`, g.points);
      setSrc(map, `af-off-${k}-polys`, g.polys);
      setSrc(map, `af-off-${k}-cols`, g.cols);
      setSrc(map, `af-off-${k}-lines`, g.lines);
    }
    // radar is a raster, not GeoJSON: frames go to an image source that replays
    const radarOn = visible.radar === true && enabledLayers.includes("radar");
    syncRadar(map, radarOn ? officialToGeoJSON(officialLayers.radar, zoomBucket).rasters : [], radarOn);
  };
  const applyData = () => {
    applyInternal();
    applyOfficial();
  };
  const applyVisibility = () => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const vis = (id: string, on: boolean) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    vis("af-heat", visible.heatmap === true);
    vis("af-off-rainfall-cols", threeD);
    vis("af-off-rainfall-pts", true);
  };
  useEffect(() => {
    applyInternal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [built, ready]);
  useEffect(() => {
    applyOfficial();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [officialLayers, visible, enabledLayers, zoomBucket, ready]);
  useEffect(() => {
    applyVisibility();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, threeD, ready]);

  // ── 3D toggle ───────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    if (threeD) {
      if (map.getSource("terrain")) map.setTerrain(TERRAIN);
      map.setSky(SKY);
      map.easeTo({ pitch: PITCH_3D, bearing: -12, duration: 900 });
    } else {
      map.setTerrain(null);
      map.setSky({ "atmosphere-blend": 0, "fog-ground-blend": 0, "horizon-fog-blend": 0 });
      map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    }
  }, [threeD]);

  // ── camera ──────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current || !fitToData || fittedRef.current || features.length === 0) return;
    const run = () => {
      const b = new maplibregl.LngLatBounds();
      features.forEach((f) => b.extend(f.geometry.coordinates as [number, number]));
      const wide = map.getContainer().clientWidth >= 1024;
      map.fitBounds(b, {
        padding: fitPadding || (wide ? { top: 110, bottom: 120, left: 60, right: 380 } : { top: 150, bottom: 80, left: 30, right: 30 }),
        maxZoom: 12.5,
        duration: REDUCED_MOTION ? 0 : 2600,
        pitch: threeD ? PITCH_3D : 0,
        bearing: threeD ? -12 : 0,
        essential: true,
      });
      fittedRef.current = true;
    };
    run();
  }, [features, fitToData, threeD, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const f = features.find((x) => x.id === selectedId);
    if (!f) return;
    const target = f.geometry.coordinates as [number, number];
    map.flyTo({ center: target, zoom: Math.max(map.getZoom(), 13.5), pitch: threeD ? PITCH_3D + 6 : 0, duration: 1400, essential: true });
    // `center` is a horizontal coordinate: under 3D terrain a point 1,000 m up
    // renders well above the viewport centre. Measure where it actually landed
    // and settle the camera onto it.
    map.once("moveend", () => {
      if (!map.getTerrain()) return;
      // the viewer may have grabbed the map mid-flight: never yank it back
      const c = map.getCenter();
      if (Math.abs(c.lng - target[0]) > 0.02 || Math.abs(c.lat - target[1]) > 0.02) return;
      const box = map.getContainer();
      const want = { x: box.clientWidth / 2, y: box.clientHeight / 2 };
      const p = map.project(target);
      const dx = p.x - want.x;
      const dy = p.y - want.y;
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) map.panBy([dx, dy], { duration: 320 }, { skipFocus: true });
    });
  }, [selectedId, features, threeD, ready]);

  return (
    <div className={`relative h-full w-full ${className}`}>
      <div ref={containerRef} className="h-full w-full" />
      <div className={`af-map-loading ${ready ? "af-map-loading-done" : ""}`} aria-hidden={ready}>
        <div className="af-map-loading-card">
          <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#0b2545" /><path d="M6 24c3-2.2 5-2.2 8 0s5 2.2 8 0 4-2 4-2" fill="none" stroke="#fff" strokeOpacity="0.45" strokeWidth="1.6" strokeLinecap="round" /><path d="M16 21V12" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" /><circle cx="16" cy="9.5" r="4.2" fill="#fff" /><circle cx="16" cy="21.5" r="1.4" fill="#fff" /></svg>
          <div>
            <div className="text-[15px] font-semibold text-[var(--ink)]">載入 3D 地形與即時資料</div>
            <div className="af-map-loading-bar"><span /></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function safeJson(v: string): unknown {
  try {
    return JSON.parse(v);
  } catch {
    return v;
  }
}

/** The console page re-renders on every poll; the map must not follow it. */
const TerrainMap = memo(TerrainMapImpl);
export default TerrainMap;
