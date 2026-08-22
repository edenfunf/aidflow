"use client";

// Location picker for the report form — the same vector basemap and relief
// as the situation map, a beacon-style marker and the GPS accuracy ring.
// Touches `window`; import via next/dynamic with { ssr: false }.

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { addTerrain, circlePolygon, collapseAttribution, loadStyle, localiseLabels } from "@/lib/mapStyle";

export interface PickerMapProps {
  center: [number, number]; // [lat, lon]
  zoom: number;
  point: [number, number] | null; // [lat, lon]
  accuracy?: number | null; // metres
  onPick: (lat: number, lon: number) => void;
  color?: string;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function markerEl(color: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "af-pin";
  el.innerHTML = `<svg width="36" height="58" viewBox="0 0 40 64" aria-hidden="true">
    <path d="M20 62V33" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/>
    <path d="M20 62V33" stroke="#1d2939" stroke-width="1.4" stroke-linecap="round"/>
    <circle cx="20" cy="61" r="2.6" fill="#1d2939" stroke="#fff" stroke-width="1.6"/>
    <circle cx="20" cy="18" r="13.2" fill="${color}" stroke="#fff" stroke-width="2.2"/>
    <circle cx="20" cy="18" r="3.2" fill="#fff"/>
  </svg>`;
  return el;
}

export default function PickerMap({ center, zoom, point, accuracy = null, onPick, color = "#0b2545" }: PickerMapProps) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const readyRef = useRef(false);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    if (!boxRef.current || mapRef.current) return;
    let cancelled = false;
    let map: MLMap | null = null;
    loadStyle().then((style) => {
      if (cancelled || !boxRef.current) return;
      map = new maplibregl.Map({ container: boxRef.current, style, center: [center[1], center[0]], zoom, attributionControl: false, canvasContextAttributes: { antialias: true } });
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.scrollZoom.disable();
      mapRef.current = map;
      map.on("style.load", () => {
        if (!map) return;
        localiseLabels(map);
        addTerrain(map, false);
        map.addSource("af-acc", { type: "geojson", data: EMPTY });
        map.addLayer({ id: "af-acc-fill", type: "fill", source: "af-acc", paint: { "fill-color": color, "fill-opacity": 0.12 } });
        map.addLayer({ id: "af-acc-line", type: "line", source: "af-acc", paint: { "line-color": color, "line-width": 1.5, "line-opacity": 0.6, "line-dasharray": [2, 2] } });
        map.on("click", (e) => onPickRef.current(e.lngLat.lat, e.lngLat.lng));
        map.getCanvas().style.cursor = "crosshair";
        collapseAttribution(map);
        readyRef.current = true;
        sync();
      });
    });
    return () => {
      cancelled = true;
      markerRef.current?.remove();
      map?.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sync = () => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    if (point) {
      const ll: [number, number] = [point[1], point[0]];
      if (!markerRef.current) {
        markerRef.current = new maplibregl.Marker({ element: markerEl(color), anchor: "bottom" }).setLngLat(ll).addTo(map);
        (markerRef.current as unknown as { _updateOpacity: () => void })._updateOpacity = () => undefined; // no per-frame depth readback
      }
      else markerRef.current.setLngLat(ll);
      (map.getSource("af-acc") as maplibregl.GeoJSONSource | undefined)?.setData(accuracy && accuracy > 5 ? { type: "FeatureCollection", features: [circlePolygon(ll[0], ll[1], accuracy)] } : EMPTY);
      map.easeTo({ center: ll, zoom: Math.max(map.getZoom(), 15), duration: 600 });
    } else {
      markerRef.current?.remove();
      markerRef.current = null;
      (map.getSource("af-acc") as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY);
    }
  };
  useEffect(() => {
    sync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point, accuracy]);

  return <div ref={boxRef} className="h-full w-full" />;
}
