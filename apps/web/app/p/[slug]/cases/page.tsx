"use client";

// Case list with the map beside it: the table is the index, the map is the
// context — selecting a row flies the map to that case.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { EmptyState, SeverityTag, Skeleton, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { CategoryBadge } from "@/lib/categoryIcons";
import { fmtAgo, fmtTime } from "@/lib/format";
import { PHASE_LABEL, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/labels";
import type { MapFeature, Phase, PublicCase, PublicPlatform, Severity } from "@/lib/types";

const TerrainMap = dynamic(() => import("@/components/TerrainMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

export default function PortalCasesPage() {
  const { slug } = useParams<{ slug: string }>();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [items, setItems] = useState<PublicCase[] | null>(null);
  const [total, setTotal] = useState(0);
  const [phase, setPhase] = useState<Phase | "all">("all");
  const [category, setCategory] = useState("");
  const [town, setTown] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [sort, setSort] = useState("updated_desc");
  const [mapFeatures, setMapFeatures] = useState<MapFeature[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    api.publicPlatform(slug).then(setPlatform).catch(() => undefined);
    api.publicMap(slug).then((m) => setMapFeatures(m.features.filter((f) => f.properties.layer === "incident_cases"))).catch(() => undefined);
  }, [slug]);
  useEffect(() => {
    setItems(null);
    api
      .publicCases(slug, { phase: phase === "all" ? undefined : phase, category: category || undefined, town: town || undefined, severity: severity || undefined, sort, limit: 200 })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch(() => setItems([]));
  }, [slug, phase, category, town, severity, sort]);

  // only the listed cases appear on the side map
  const features = useMemo(() => {
    const ids = new Set((items || []).map((c) => c.id));
    return mapFeatures.filter((f) => ids.has(String(f.properties.case_id ?? f.properties.id)));
  }, [items, mapFeatures]);
  const mapVisible = useMemo(() => ({ incident_cases: true }), []);

  return (
    <PortalShell platform={platform} slug={slug}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="af-eyebrow">災情案件</div>
          <h1 className="af-h1">全部案件</h1>
        </div>
        <div className="text-xs text-[var(--muted)]">共 {total} 件</div>
      </div>
      <div className="af-panel mb-3 flex flex-wrap items-center gap-2 p-2">
        <div className="flex gap-1">
          {(["all", "pending", "active", "done"] as const).map((p) => (
            <button key={p} type="button" onClick={() => setPhase(p)} className={`af-chip ${phase === p ? "af-chip-on" : ""}`}>
              {p === "all" ? "全部" : PHASE_LABEL[p]}
            </button>
          ))}
        </div>
        <select className="af-input !w-auto !py-1 text-xs" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">所有類別</option>
          {(platform?.report_categories || []).map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
        <select className="af-input !w-auto !py-1 text-xs" value={town} onChange={(e) => setTown(e.target.value)}>
          <option value="">所有鄉鎮</option>
          {(platform?.towns || []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select className="af-input !w-auto !py-1 text-xs" value={severity} onChange={(e) => setSeverity(e.target.value as Severity | "")}>
          <option value="">所有嚴重度</option>
          {SEVERITY_ORDER.map((s) => (
            <option key={s} value={s}>
              {SEVERITY_LABEL[s]}
            </option>
          ))}
        </select>
        <select className="af-input !w-auto !py-1 text-xs" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="updated_desc">最近更新</option>
          <option value="created_desc">最新成案</option>
          <option value="severity_desc">嚴重度</option>
          <option value="reports_desc">回報人數</option>
        </select>
      </div>

      <div className="grid gap-3 xl:grid-cols-12">
        <div className="xl:col-span-7">
          {items === null ? (
            <Skeleton className="h-64" />
          ) : items.length === 0 ? (
            <EmptyState title="沒有符合條件的案件" />
          ) : (
            <div className="af-panel overflow-x-auto">
              <table className="af-table min-w-[640px]">
                <thead>
                  <tr>
                    <th>災情</th>
                    <th>地點</th>
                    <th>嚴重度</th>
                    <th>回報</th>
                    <th>狀態</th>
                    <th>處理單位</th>
                    <th>最近更新</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => {
                    const sel = selectedId === `case:${c.id}`;
                    return (
                      <tr key={c.id} className={`af-row-hover cursor-pointer ${sel ? "bg-[var(--surface-2)]" : ""}`} onClick={() => setSelectedId(`case:${c.id}`)}>
                        <td>
                          <div className="flex items-center gap-2.5">
                            <CategoryBadge category={c.category} size={30} />
                            <div className="min-w-0">
                              <Link href={`/p/${slug}/cases/${c.id}`} className="font-medium text-[var(--ink)] hover:underline" onClick={(e) => e.stopPropagation()}>
                                {c.title}
                              </Link>
                              <div className="whitespace-nowrap text-[11px] text-[var(--muted)]">
                                <span className="font-mono">{c.case_number}</span> · {c.category_label}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="text-xs text-[var(--ink-2)]">{c.location_label || c.town}</td>
                        <td>
                          <SeverityTag severity={c.severity} withLabel={false} />
                        </td>
                        <td className="whitespace-nowrap tabular-nums text-xs">{c.unique_reporter_count} 人</td>
                        <td>
                          <StatusPill status={c.status} phase={c.phase} />
                        </td>
                        <td className="text-xs text-[var(--ink-2)]">{c.assigned_unit || "—"}</td>
                        <td className="whitespace-nowrap text-xs text-[var(--muted)]" title={fmtTime(c.updated_at)}>
                          {fmtAgo(c.updated_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <aside className="hidden xl:col-span-5 xl:block">
          <div className="af-panel sticky top-[64px] overflow-hidden">
            <div className="h-[calc(100vh-150px)] min-h-[420px]">
              {platform ? (
                <TerrainMap center={platform.map.center} zoom={platform.map.zoom} features={features} visible={mapVisible} enabledLayers={["incident_cases"]} selectedId={selectedId} onSelect={(f) => setSelectedId(f ? String(f.id) : null)} threeD fitToData />
              ) : (
                <Skeleton className="h-full w-full" />
              )}
            </div>
            <div className="px-3 py-2 text-[11px] text-[var(--muted)]">點選列表中的案件，地圖會飛到該地點；公開位置已粗化。</div>
          </div>
        </aside>
      </div>
    </PortalShell>
  );
}
