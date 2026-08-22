// One basemap for every map on the site: OpenFreeMap "liberty" (vector, no
// key) with labels forced to Chinese, OSM raster as a fallback when the
// vector host is slow, AWS Terrain Tiles for relief. Shared by the 3D
// situation map, the case-detail map and the report location picker so the
// whole product speaks one visual language.

import type { ExpressionSpecification, Map as MLMap, StyleSpecification } from "maplibre-gl";

export const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
export const TERRAIN_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
export const BASEMAP_ATTRIBUTION = "地形：AWS Terrain Tiles (Mapzen) · 底圖：OpenFreeMap © OpenMapTiles © OpenStreetMap contributors";

export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.9 } }],
};

export async function loadStyle(): Promise<StyleSpecification | string> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 7000);
  try {
    const res = await fetch(STYLE_URL, { signal: ctrl.signal });
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as StyleSpecification;
  } catch {
    return FALLBACK_STYLE;
  } finally {
    window.clearTimeout(timer);
  }
}

export const ZH_LABEL: ExpressionSpecification = ["coalesce", ["get", "name:zh"], ["get", "name:nonlatin"], ["get", "name"]];

/** Force basemap labels to Chinese; returns the font stack the style uses so
 * our own symbol layers match it. */
export function localiseLabels(map: MLMap): string[] {
  const style = map.getStyle() as StyleSpecification;
  let font: string[] = ["Noto Sans Regular"];
  for (const l of style.layers) {
    if (l.type !== "symbol") continue;
    const tf = map.getLayoutProperty(l.id, "text-field");
    if (tf && JSON.stringify(tf).includes("name")) map.setLayoutProperty(l.id, "text-field", ZH_LABEL);
    const f = map.getLayoutProperty(l.id, "text-font");
    if (Array.isArray(f) && f.length && typeof f[0] === "string") font = f as string[];
  }
  return font;
}

/** Add relief (hillshade, optional 3D terrain) under the first symbol layer. */
export function addTerrain(map: MLMap, threeD: boolean, exaggeration = 1.35): void {
  if (map.getSource("terrain")) return;
  const style = map.getStyle() as StyleSpecification;
  const firstSymbol = style.layers.find((l) => l.type === "symbol")?.id;
  map.addSource("terrain", { type: "raster-dem", tiles: [TERRAIN_TILES], tileSize: 256, encoding: "terrarium", maxzoom: 15, attribution: "" });
  map.addLayer(
    { id: "af-hillshade", type: "hillshade", source: "terrain", paint: { "hillshade-exaggeration": 0.5, "hillshade-shadow-color": "#5b6472", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#8b95a5" } },
    firstSymbol
  );
  if (threeD) map.setTerrain({ source: "terrain", exaggeration });
}

/** GeoJSON circle (metres) — accuracy rings, footprints. */
export function circlePolygon(lon: number, lat: number, radiusM: number, steps = 64): GeoJSON.Feature<GeoJSON.Polygon> {
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const ring: number[][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    ring.push([lon + Math.cos(a) * dLon, lat + Math.sin(a) * dLat]);
  }
  return { type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: {} };
}


/** MapLibre expands the compact attribution on load; collapse it to its (i)
 * button (it stays one click away) — once now, and again after the control
 * re-measures itself on the first resize. */
export function collapseAttribution(map: MLMap): void {
  const doIt = () => map.getContainer().querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  doIt();
  map.once("load", doIt);
  map.once("resize", doIt);
  window.setTimeout(doIt, 800);
}
