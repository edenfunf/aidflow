"use client";

import { useEffect, useMemo, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { HAZARD_LABEL, LAYERS, MODULE_TYPE_LABEL } from "@/lib/labels";
import type { DomainItem, ModuleSpecItem } from "@/lib/types";

export default function ModulesPage() {
  const [modules, setModules] = useState<ModuleSpecItem[] | null>(null);
  const [domains, setDomains] = useState<DomainItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState("");
  const [type, setType] = useState("");

  useEffect(() => {
    Promise.all([api.listModules(), api.listDomains()])
      .then(([m, d]) => {
        setModules(m.items);
        setDomains(d.items);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const grouped = useMemo(() => {
    const out: Record<string, ModuleSpecItem[]> = {};
    for (const m of modules || []) {
      if (domain && m.domain !== domain) continue;
      if (type && m.module_type !== type) continue;
      (out[m.domain] ||= []).push(m);
    }
    return out;
  }, [modules, domain, type]);

  return (
    <ConsoleShell title="模組註冊表" crumbs={[{ href: "/console", label: "平台總覽" }, { label: "模組註冊表" }]}>
      <p className="mb-3 max-w-3xl text-sm text-[var(--muted)]">
        每個平台由註冊表中的模組組合而成：規劃器只「建議」模組 id，實際生成由確定性的 composer 依註冊表完成。核心模組不可關閉，相依模組會自動補齊。
      </p>
      {error ? <ErrorBox message={error} /> : null}
      <div className="mb-3 flex flex-wrap gap-1.5">
        <button type="button" className={`af-chip ${domain === "" ? "af-chip-on" : ""}`} onClick={() => setDomain("")}>
          全部領域 {modules?.length ?? ""}
        </button>
        {domains.map((d) => (
          <button key={d.key} type="button" className={`af-chip ${domain === d.key ? "af-chip-on" : ""}`} onClick={() => setDomain(d.key)}>
            {d.label} {d.count}
          </button>
        ))}
        <span className="mx-1 hidden h-5 w-px bg-[var(--line-2)] sm:block" />
        {Object.entries(MODULE_TYPE_LABEL).map(([k, v]) => (
          <button key={k} type="button" className={`af-chip ${type === k ? "af-chip-on" : ""}`} onClick={() => setType(type === k ? "" : k)}>
            {v}
          </button>
        ))}
      </div>
      {modules === null ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="space-y-4">
          {domains
            .filter((d) => grouped[d.key]?.length)
            .map((d) => (
              <section key={d.key} className="af-panel">
                <div className="border-b px-3 py-2" style={{ borderColor: "var(--line)" }}>
                  <h2 className="af-h2">
                    {d.label} <span className="ml-1 font-normal text-[var(--muted)]">{grouped[d.key].length}</span>
                  </h2>
                </div>
                <table className="af-table">
                  <thead>
                    <tr>
                      <th>模組</th>
                      <th>類型</th>
                      <th>適用災害</th>
                      <th>相依</th>
                      <th>預設</th>
                    </tr>
                  </thead>
                  <tbody>
                    {grouped[d.key].map((m) => (
                      <tr key={m.id}>
                        <td>
                          <div className="flex items-center gap-2 font-medium">
                            {m.layer_key ? <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LAYERS[m.layer_key]?.hex || "#667085" }} /> : null}
                            {m.name}
                            {m.core ? <span className="af-chip !py-0 text-[10px]">核心</span> : null}
                            {!m.implemented ? <span className="af-chip !py-0 text-[10px]">規劃中</span> : null}
                          </div>
                          <div className="font-mono text-[11px] text-[var(--muted)]">{m.id}</div>
                          <div className="max-w-xl text-xs text-[var(--ink-2)]">{m.description}</div>
                        </td>
                        <td className="text-xs">{MODULE_TYPE_LABEL[m.module_type]}</td>
                        <td className="text-xs">{m.applicable_hazards.includes("*") ? "所有災害" : m.applicable_hazards.map((h) => HAZARD_LABEL[h] || h).join("、")}</td>
                        <td className="font-mono text-[11px] text-[var(--muted)]">{m.dependencies.join(", ") || "—"}</td>
                        <td className="text-xs">{m.default_enabled ? "建議啟用" : "手動"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
        </div>
      )}
    </ConsoleShell>
  );
}
