"use client";

// The core map shared by the public portal and the console. Touches `window`,
// so import via next/dynamic with { ssr: false }.
//
// Internal layers (cases / report clusters / citizen reports / heat) come from
// the platform's own data; official layers arrive already normalised as
// GeoFeatures. Category keys (flooding, road_damage, …) act as filters on the
// internal layers; "government_processing" dims everything that is not being
// handled right now.

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet.heat";
import { MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { GeoFeature, LayerResponse, MapFeature, Severity } from "@/lib/types";
import {
  CATEGORY_LABEL,
  LAYERS,
  PHASE_HEX,
  SEVERITY_HEX,
  SEVERITY_LABEL,
  STATUS_LABEL,
  layerHex,
} from "@/lib/labels";
import { fmtTime } from "@/lib/format";
import { casePopup, clusterPopup, esc, officialPopup, reportPopup } from "@/lib/mapPopups";

export interface IncidentMapProps {
  center: [number, number];
  zoom: number;
  features: MapFeature[];
  officialLayers?: Record<string, LayerResponse | undefined>;
  visible: Record<string, boolean>;
  enabledLayers: string[];
  selectedId?: string | null;
  onSelect?: (feature: MapFeature | GeoFeature | null) => void;
  height?: number | string;
  fitToData?: boolean;
  pickMode?: boolean;
  pickPoint?: [number, number] | null;
  onPick?: (lat: number, lon: number) => void;
  scrollWheelZoom?: boolean;
  className?: string;
}

const CATEGORY_FILTER_KEYS = ["flooding", "road_damage", "landslide", "trapped_people", "building_damage", "lifeline", "other"];

function categoryVisible(visible: Record<string, boolean>, enabled: string[], catLayer: string | undefined): boolean {
  // a category layer that the platform did not enable is always shown (no
  // toggle exists for it); an enabled one follows its toggle
  if (!catLayer || !enabled.includes(catLayer)) return true;
  return visible[catLayer] !== false;
}

function sizeFor(sev: Severity | undefined, base = 22): number {
  if (sev === "critical") return base + 10;
  if (sev === "high") return base + 4;
  if (sev === "low") return base - 4;
  return base;
}

function caseIcon(p: Record<string, any>, selected: boolean, dimmed: boolean): L.DivIcon {
  const size = sizeFor(p.severity, 26);
  const bg = layerHex(p.category_layer);
  const phase = PHASE_HEX[p.phase as keyof typeof PHASE_HEX] || "#667085";
  const ring = p.severity === "critical" && p.phase !== "done" ? "af-marker-ring" : "";
  const html = `<div class="af-marker af-marker-square ${selected ? "af-marker-selected" : ""} ${ring}" style="position:relative;width:${size}px;height:${size}px;background:${bg};opacity:${dimmed ? 0.35 : 1};color:${bg}">
      <span style="color:#fff">${esc(p.unique_reporter_count ?? "")}</span>
      <span style="position:absolute;right:-4px;top:-4px;width:10px;height:10px;border-radius:9999px;background:${phase};border:2px solid #fff"></span>
    </div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
}

function clusterIcon(p: Record<string, any>, selected: boolean): L.DivIcon {
  const size = 22;
  const bg = layerHex(p.category_layer);
  const html = `<div class="af-marker ${selected ? "af-marker-selected" : ""}" style="width:${size}px;height:${size}px;background:#fff;color:${bg};border:2px solid ${bg};border-style:dashed">${esc(p.unique_reporter_count ?? "")}</div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
}

function reportIcon(p: Record<string, any>, selected: boolean): L.DivIcon {
  const size = 12;
  const bg = layerHex(p.category_layer);
  const html = `<div class="af-marker ${selected ? "af-marker-selected" : ""}" style="width:${size}px;height:${size}px;background:${bg};opacity:0.9"></div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
}

function glyphIcon(glyph: string, color: string, size = 22): L.DivIcon {
  const html = `<div class="af-marker af-marker-square" style="width:${size}px;height:${size}px;background:${color};font-size:11px">${esc(glyph)}</div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
}

const WATER_STATUS_HEX: Record<string, string> = { alert1: "#7a0c16", alert2: "#d92d20", alert3: "#dc8a0c", normal: "#0369a1", unknown: "#98a2b3" };
const RAIN_LEVEL_HEX: Record<string, string> = { extreme: "#312e81", torrential: "#3730a3", heavy: "#1d4ed8", moderate: "#3b82f6", light: "#93c5fd" };

function InternalLayers({ features, visible, enabledLayers, selectedId, onSelect }: Pick<IncidentMapProps, "features" | "visible" | "enabledLayers" | "selectedId" | "onSelect">) {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup | null>(null);
  const clusterRef = useRef<L.MarkerClusterGroup | null>(null);
  const heatRef = useRef<L.HeatLayer | null>(null);

  useEffect(() => {
    const group = L.layerGroup().addTo(map);
    const cluster = L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 40,
      spiderfyOnMaxZoom: true,
      disableClusteringAtZoom: 16,
      iconCreateFunction: (c) => L.divIcon({ className: "marker-cluster", html: `<div>${c.getChildCount()}</div>`, iconSize: [40, 40] }),
    }).addTo(map);
    groupRef.current = group;
    clusterRef.current = cluster;
    return () => {
      group.remove();
      cluster.remove();
      heatRef.current?.remove();
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    const cluster = clusterRef.current;
    if (!group || !cluster) return;
    group.clearLayers();
    cluster.clearLayers();

    const showCases = visible.incident_cases !== false;
    const showClusters = visible.report_clusters !== false;
    const showReports = visible.citizen_reports !== false;
    const showHeat = visible.heatmap === true;
    const govOnly = visible.government_processing === true;
    const heatPoints: Array<[number, number, number]> = [];

    for (const f of features) {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      if (!categoryVisible(visible, enabledLayers, p.category_layer)) continue;
      const selected = selectedId === f.id;
      if (p.layer === "incident_cases") {
        if (!showCases) continue;
        const dimmed = govOnly && p.phase !== "active";
        const m = L.marker([lat, lon], { icon: caseIcon(p, selected, dimmed), zIndexOffset: selected ? 1000 : p.severity === "critical" ? 500 : 200 });
        m.bindPopup(casePopup(p));
        m.on("click", () => onSelect?.(f));
        group.addLayer(m);
        heatPoints.push([lat, lon, p.severity === "critical" ? 1 : p.severity === "high" ? 0.8 : 0.5]);
      } else if (p.layer === "report_clusters") {
        if (!showClusters || govOnly) continue;
        const m = L.marker([lat, lon], { icon: clusterIcon(p, selected), zIndexOffset: 100 });
        m.bindPopup(clusterPopup(p));
        m.on("click", () => onSelect?.(f));
        group.addLayer(m);
        heatPoints.push([lat, lon, 0.4]);
      } else if (p.layer === "citizen_reports") {
        heatPoints.push([lat, lon, 0.3]);
        if (!showReports || govOnly) continue;
        const m = L.marker([lat, lon], { icon: reportIcon(p, selected) });
        m.bindPopup(reportPopup(p));
        m.on("click", () => onSelect?.(f));
        cluster.addLayer(m);
      }
    }

    heatRef.current?.remove();
    heatRef.current = null;
    if (showHeat && heatPoints.length) {
      heatRef.current = L.heatLayer(heatPoints, {
        radius: 28,
        blur: 22,
        maxZoom: 15,
        minOpacity: 0.25,
        gradient: { 0.2: "#fde68a", 0.5: "#f97316", 0.8: "#dc2626", 1: "#7f1d1d" },
      }).addTo(map);
    }
  }, [features, visible, enabledLayers, selectedId, onSelect, map]);

  return null;
}

function OfficialLayers({ officialLayers, visible, onSelect }: Pick<IncidentMapProps, "officialLayers" | "visible" | "onSelect">) {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    const group = L.layerGroup().addTo(map);
    groupRef.current = group;
    return () => {
      group.remove();
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    group.clearLayers();
    for (const [key, layer] of Object.entries(officialLayers || {})) {
      if (!layer || visible[key] !== true || layer.status !== "ok") continue;
      const meta = LAYERS[key];
      for (const f of layer.features) {
        const p = f.properties || {};
        let marker: L.Layer | null = null;
        if (f.type === "Polygon") {
          const rings = (f.coordinates as number[][][]).map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number]));
          marker = L.polygon(rings, { color: meta?.hex || "#c2410c", weight: 1.5, fillOpacity: 0.12, dashArray: "6 4" });
        } else if (f.type === "Point") {
          const [lon, lat] = f.coordinates as [number, number];
          if (key === "water") {
            const c = WATER_STATUS_HEX[p.status] || WATER_STATUS_HEX.unknown;
            marker = L.circleMarker([lat, lon], { radius: p.status?.startsWith("alert") ? 9 : 6, color: "#fff", weight: 2, fillColor: c, fillOpacity: 0.95 });
          } else if (key === "rainfall") {
            const c = RAIN_LEVEL_HEX[p.level] || RAIN_LEVEL_HEX.light;
            const r = Math.min(18, 5 + Math.sqrt(Math.max(0, p.rain_24h_mm || 0)) * 0.9);
            marker = L.circleMarker([lat, lon], { radius: r, color: "#fff", weight: 1.5, fillColor: c, fillOpacity: 0.75 });
          } else if (key === "official_alert") {
            marker = L.marker([lat, lon], { icon: glyphIcon("警", meta?.hex || "#c2410c", 24), zIndexOffset: 300 });
          } else {
            marker = L.marker([lat, lon], { icon: glyphIcon(meta?.glyph || "•", meta?.hex || "#667085", 20) });
          }
        }
        if (!marker) continue;
        marker.bindPopup(officialPopup(f));
        marker.on("click", () => onSelect?.(f));
        group.addLayer(marker);
      }
    }
  }, [officialLayers, visible, onSelect, map]);

  return null;
}

function FitAndFly({ features, fitToData, selectedId, center, zoom }: Pick<IncidentMapProps, "features" | "fitToData" | "selectedId" | "center" | "zoom">) {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || !fitToData || features.length === 0) return;
    const pts = features.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]] as [number, number]);
    if (pts.length === 1) map.setView(pts[0], Math.max(zoom, 13));
    else map.fitBounds(L.latLngBounds(pts).pad(0.15), { maxZoom: 14 });
    fitted.current = true;
  }, [features, fitToData, map, zoom]);
  useEffect(() => {
    if (!selectedId) return;
    const f = features.find((x) => x.id === selectedId);
    if (f) map.flyTo([f.geometry.coordinates[1], f.geometry.coordinates[0]], Math.max(map.getZoom(), 14), { duration: 0.6 });
  }, [selectedId, features, map]);
  useEffect(() => {
    map.invalidateSize();
  }, [map, center]);
  return null;
}

function Picker({ pickMode, pickPoint, onPick }: Pick<IncidentMapProps, "pickMode" | "pickPoint" | "onPick">) {
  const map = useMap();
  const markerRef = useRef<L.Marker | null>(null);
  useMapEvents({
    click(e) {
      if (pickMode) onPick?.(e.latlng.lat, e.latlng.lng);
    },
  });
  useEffect(() => {
    markerRef.current?.remove();
    markerRef.current = null;
    if (pickPoint) {
      const icon = L.divIcon({
        className: "",
        html: `<div style="width:18px;height:18px;border-radius:9999px;background:#0b2545;border:3px solid #fff;box-shadow:0 0 0 2px #0b2545"></div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      });
      markerRef.current = L.marker(pickPoint, { icon, zIndexOffset: 2000 }).addTo(map);
      map.panTo(pickPoint);
    }
  }, [pickPoint, map]);
  useEffect(() => {
    const el = map.getContainer();
    el.style.cursor = pickMode ? "crosshair" : "";
  }, [pickMode, map]);
  return null;
}

export default function IncidentMap({
  center,
  zoom,
  features,
  officialLayers,
  visible,
  enabledLayers,
  selectedId,
  onSelect,
  height = 520,
  fitToData = false,
  pickMode = false,
  pickPoint = null,
  onPick,
  scrollWheelZoom = true,
  className = "",
}: IncidentMapProps) {
  const safeFeatures = useMemo(() => features.filter((f) => f.geometry?.coordinates?.length === 2), [features]);
  return (
    <div className={`relative overflow-hidden ${className}`} style={{ height }}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={scrollWheelZoom} style={{ height: "100%", width: "100%" }} zoomControl={false} attributionControl={true}>
        {/* OSM standard tiles label Taiwan in local (Chinese) names at every zoom */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
          opacity={0.92}
        />
        <InternalLayers features={safeFeatures} visible={visible} enabledLayers={enabledLayers} selectedId={selectedId} onSelect={onSelect} />
        <OfficialLayers officialLayers={officialLayers} visible={visible} onSelect={onSelect} />
        <FitAndFly features={safeFeatures} fitToData={fitToData} selectedId={selectedId} center={center} zoom={zoom} />
        <Picker pickMode={pickMode} pickPoint={pickPoint} onPick={onPick} />
      </MapContainer>
    </div>
  );
}

export { CATEGORY_FILTER_KEYS };
