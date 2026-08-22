"use client";

// Data hooks for the public portal and the console map: platform config,
// situation, map features, lazily-fetched official layers and the visible
// layer state. Polls so the situation picture stays live.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { OFFICIAL_LAYERS } from "./labels";
import type { LayerResponse, LayerStatusItem, MapFeature, MapFeatureCollection, PublicPlatform, Situation } from "./types";

/** What each surface opens with.
 *
 *  public  — "where is it dangerous, and where do I report?" Warnings, rain,
 *            hazardous streams and shelters are on; the government's own
 *            movements (routes, ambulances) are not a citizen's business by
 *            default, though the chip is still there for transparency.
 *  console — an operations picture: dispatch and vehicles on, weather on,
 *            the heavier survey layers a click away.
 */
// shelters are useful but there are ~390 of them in one county: a chip away,
// not a default carpet of dots
const PUBLIC_OFFICIAL_ON = ["official_alert", "radar", "debris_flow"];
const CONSOLE_OFFICIAL_ON = ["official_alert", "radar"];

export function defaultVisibility(layers: string[], surface: "public" | "console" = "public"): Record<string, boolean> {
  const on = surface === "console" ? CONSOLE_OFFICIAL_ON : PUBLIC_OFFICIAL_ON;
  const v: Record<string, boolean> = { dispatch: surface === "console" };
  for (const k of layers) {
    if (k === "heatmap" || k === "government_processing") v[k] = false;
    else if (OFFICIAL_LAYERS.includes(k)) v[k] = on.includes(k);
    else v[k] = true;
  }
  return v;
}

export function useVisibleLayers(layers: string[], surface: "public" | "console" = "public") {
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const initialised = useRef(false);
  useEffect(() => {
    if (!initialised.current && layers.length) {
      setVisible(defaultVisibility(layers, surface));
      initialised.current = true;
    }
  }, [layers, surface]);
  const toggle = useCallback((key: string) => setVisible((v) => ({ ...v, [key]: !(v[key] ?? true) })), []);
  return { visible, toggle, setVisible };
}

export function useOfficialLayers(
  layers: string[],
  visible: Record<string, boolean>,
  fetcher: (layer: string) => Promise<LayerResponse>
) {
  const [data, setData] = useState<Record<string, LayerResponse | undefined>>({});
  const inflight = useRef<Set<string>>(new Set());
  useEffect(() => {
    for (const k of layers) {
      if (!OFFICIAL_LAYERS.includes(k) || visible[k] !== true || data[k] || inflight.current.has(k)) continue;
      inflight.current.add(k);
      fetcher(k)
        .then((res) => setData((d) => ({ ...d, [k]: res })))
        .catch((err) =>
          setData((d) => ({
            ...d,
            [k]: { layer: k, source: "", status: "unavailable", detail: (err as Error).message, attribution: null, fetched_at: null, cached: false, count: 0, features: [] },
          }))
        )
        .finally(() => inflight.current.delete(k));
    }
  }, [layers, visible, data, fetcher]);
  return data;
}

/** Identity of a map payload: polls that return the same picture must not
 * replace the array, or every consumer (and the map's GPU buffers) churns. */
export function featureSignature(fc: MapFeatureCollection | null | undefined): string {
  if (!fc) return "";
  const parts: string[] = [String(fc.features.length)];
  for (const f of fc.features) {
    const p = f.properties as Record<string, unknown>;
    parts.push(`${f.id}:${p.updated_at ?? p.created_at ?? ""}:${p.status ?? ""}:${p.report_count ?? ""}`);
  }
  return parts.join("|");
}

/** Replace only when the content actually differs. */
export function keepIfSame(prev: MapFeatureCollection | null, next: MapFeatureCollection): MapFeatureCollection | null {
  return featureSignature(prev) === featureSignature(next) ? prev : next;
}

export function countsByLayer(features: MapFeature[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const f of features) {
    counts[f.properties.layer] = (counts[f.properties.layer] || 0) + 1;
    const cl = f.properties.category_layer;
    if (cl && f.properties.layer === "incident_cases") counts[cl] = (counts[cl] || 0) + 1;
  }
  return counts;
}

export function usePublicPlatform(slug: string, pollMs = 30000) {
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [situation, setSituation] = useState<Situation | null>(null);
  const [map, setMap] = useState<MapFeatureCollection | null>(null);
  const [statuses, setStatuses] = useState<LayerStatusItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [p, s, m] = await Promise.all([api.publicPlatform(slug), api.situation(slug), api.publicMap(slug)]);
      setPlatform(p);
      setSituation(s);
      setMap((prev) => keepIfSame(prev, m));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
    api.publicLayerStatuses(slug).then((r) => setStatuses(r.items)).catch(() => undefined);
    // a background tab does not need a live situation picture
    const id = window.setInterval(() => {
      if (!document.hidden) load();
    }, pollMs);
    return () => window.clearInterval(id);
  }, [load, slug, pollMs]);

  const layers = useMemo(() => platform?.layers ?? [], [platform]);
  const { visible, toggle } = useVisibleLayers(layers, "public");
  const fetcher = useCallback((layer: string) => api.publicLayer(slug, layer), [slug]);
  const official = useOfficialLayers(layers, visible, fetcher);

  return { platform, situation, map, statuses, error, loading, reload: load, layers, visible, toggle, official };
}
