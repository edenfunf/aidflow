"use client";

// Agent planner: brief → analysis + suggestions → human edits → compose.
// The plan never touches production; only the approved draft is executed.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ConsoleShell from "@/components/ConsoleShell";
import { ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { CATEGORY_LABEL, DOMAIN_LABEL, HAZARD_LABEL, LAYERS, MODULE_TYPE_LABEL, ROLE_LABEL, categoryHex } from "@/lib/labels";
import { CategoryIcon } from "@/lib/categoryIcons";
import type { AgentExecuteResponse, AgentPlan, PlatformDraft } from "@/lib/types";


const EXAMPLE =
  "南投縣仁愛鄉因颱風帶來連續豪雨，多處山區道路可能發生坍方、土石流與積淹水，部分偏遠部落可能交通中斷，希望民眾、村里長、防災士與志工都可以共同回報災情。";

const DOMAIN_ORDER = ["reporting", "processing", "dispatch", "visualization", "public_transparency", "analytics", "official_data", "privacy", "notification"];


function SystemRow({ no, title, href, action, summary, listLabel, list }: { no: string; title: string; href: string; action: string; summary: string; listLabel: string; list: string }) {
  return (
    <>
      <span className="af-sys-no">{no}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-4">
          <span className="af-sys-title">{title}</span>
          <span className="af-sys-go">
            {action}
            <span className="af-sys-arrow">→</span>
          </span>
        </span>
        <span className="mt-1 block font-mono text-[11px] text-[var(--muted)]">{href}</span>
        <span className="mt-2 block text-[12.5px] leading-relaxed text-[var(--ink-2)]">{summary}</span>
        {list ? (
          <span className="af-sys-meta">
            <span className="af-doc-kicker flex-none pt-[1px]">{listLabel}</span>
            <span className="text-[var(--muted)]">{list}</span>
          </span>
        ) : null}
      </span>
    </>
  );
}

export default function NewPlatformPage() {
  const [brief, setBrief] = useState("");
  const [seeding, setSeeding] = useState(false);
  const [seeded, setSeeded] = useState<string | null>(null);
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [draft, setDraft] = useState<PlatformDraft | null>(null);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [phase, setPhase] = useState<"idle" | "composing" | "seeding">("idle");
  // a generated platform is empty; for a demonstration it should arrive alive
  const [withDemo, setWithDemo] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<AgentExecuteResponse | null>(null);

  async function runPlan(text?: string) {
    const input = (text ?? brief).trim();
    if (!input) return;
    setPlanning(true);
    setError(null);
    setPlan(null);
    setDraft(null);
    try {
      const p = await api.agentPlan(input);
      setPlan(p);
      setDraft({ ...p.draft, configuration: null });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPlanning(false);
    }
  }

  // arriving from the system console: prefill the brief and analyse it at once
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("brief");
    if (!q) return;
    setBrief(q);
    runPlan(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runExecute() {
    if (!draft) return;
    setExecuting(true);
    setPhase("composing");
    setError(null);
    setSeeded(null);
    try {
      const created = await api.agentExecute(draft);
      if (withDemo) {
        // land on a platform that already tells its story, rather than an
        // empty map the operator has to fill by hand
        setPhase("seeding");
        try {
          const r = await api.seedPlatformDemo(created.platform.id);
          setSeeded(`已自動帶入示範資料：${r.reports} 筆通報、${r.cases} 件案件${r.translated ? "（已平移到本縣）" : ""}`);
        } catch {
          setSeeded("示範資料未帶入（DEMO_MODE 關閉或帶入失敗），平台本身已建立完成。");
        }
      }
      setDone(created);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExecuting(false);
      setPhase("idle");
    }
  }

  const modulesByDomain = useMemo(() => {
    const out: Record<string, AgentPlan["suggested_modules"]> = {};
    for (const m of plan?.suggested_modules || []) (out[m.domain] ||= []).push(m);
    return out;
  }, [plan]);

  const toggleIn = (key: "modules" | "layers" | "report_categories", id: string) =>
    setDraft((d) => {
      if (!d) return d;
      const cur = d[key] || [];
      return { ...d, [key]: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] };
    });

  if (done) {
    const publicHref = `/p/${done.platform.slug}`;
    const consoleHref = `/console/platforms/${done.platform.id}`;
    const cfg = done.platform.configuration || {};
    const policy = cfg.cluster_policy;
    const categories = ((done.platform.scenario?.report_categories as { key: string; label: string }[]) || []);
    const layerKeys = (done.platform.layers || []).filter((k) => LAYERS[k]);
    const hazards = (cfg.hazard_labels as string[] | undefined)?.join("、") || done.platform.hazards.map((h) => HAZARD_LABEL[h] || h).join("、");
    const stats: [string, string][] = [
      [String(done.enabled_modules), "啟用模組"],
      [String(done.enabled_layers), "地圖圖層"],
      [String(categories.length), "通報類別"],
      [`${policy?.required_unique_reporters ?? 2}`, "成案門檻（人）"],
    ];
    const systems = [
      {
        no: "01",
        accent: "#2e5aac",
        tint: "#f5f8fd",
        tintHover: "#eaf1fb",
        title: "民眾通報網站",
        href: publicHref,
        external: true,
        action: "開啟",
        summary: "3D 災情態勢圖・我要通報（照片與定位）・案件公開處理進度・戰情牆",
        listLabel: "可回報類別",
        list: categories.map((c) => c.label || CATEGORY_LABEL[c.key] || c.key).join("、"),
      },
      {
        no: "02",
        accent: "#0b2545",
        tint: "#f5f6f9",
        tintHover: "#eceff4",
        title: "政府管理後台",
        href: consoleHref,
        external: false,
        action: "進入",
        summary: "案件佇列與篩選・一鍵通報並派遣・官方情資圖層・稽核軌跡",
        listLabel: "啟用圖層",
        list: layerKeys.map((k) => LAYERS[k].label).join("、"),
      },
    ];

    return (
      <ConsoleShell>
        <div className="af-page mx-auto max-w-[980px] pb-10">
          <article className="af-doc">
            <header className="af-doc-head">
              <span className="af-doc-kicker">AidFlow · 平台生成紀錄</span>
              <span className="font-mono text-[11px] text-[var(--muted)]">{fmtTime(done.platform.created_at)}</span>
            </header>

            <div className="px-7 pb-8 pt-8 sm:px-12">
              <div className="flex items-center gap-2">
                <span className="af-check grid h-[18px] w-[18px] place-items-center rounded-full text-white" style={{ background: "var(--st-done)" }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12.5 10 17.5 19 7" />
                  </svg>
                </span>
                <span className="af-doc-kicker !text-[var(--st-done)]">已生成並發布</span>
              </div>
              <h1 className="mt-3 text-[27px] font-semibold leading-[1.25] tracking-[-0.015em] text-[var(--ink)] sm:text-[31px]">{done.platform.name}</h1>
              <p className="mt-2 text-[13px] text-[var(--ink-2)]">
                {done.platform.county}
                {done.platform.towns.length ? ` ${done.platform.towns.join("、")}` : ""} · {hazards} · {done.platform.status === "published" ? "已發布" : "草稿"}
              </p>

              <dl className="mt-8 grid grid-cols-2 border-y sm:grid-cols-4" style={{ borderColor: "var(--line)" }}>
                {stats.map(([v, l], i) => (
                  <div key={l} className={`px-5 py-4 first:pl-0 ${i ? "sm:border-l" : ""}`} style={{ borderColor: "var(--line)" }}>
                    <dd className="text-[26px] font-semibold leading-none tabular-nums tracking-tight text-[var(--ink)]">{v}</dd>
                    <dt className="af-doc-kicker mt-2 block">{l}</dt>
                  </div>
                ))}
              </dl>
            </div>

            <section className="px-7 pb-1 sm:px-12">
              <h2 className="af-doc-kicker">生成項目</h2>
              <div className="mt-3.5 space-y-3">
                {systems.map((sys) => {
                  const style = { ["--sys-accent" as string]: sys.accent, ["--sys-tint" as string]: sys.tint, ["--sys-tint-hover" as string]: sys.tintHover };
                  return sys.external ? (
                    <a key={sys.no} href={sys.href} target="_blank" rel="noreferrer" className="af-sys" style={style}>
                      <SystemRow {...sys} />
                    </a>
                  ) : (
                    <Link key={sys.no} href={sys.href} className="af-sys" style={style}>
                      <SystemRow {...sys} />
                    </Link>
                  );
                })}
              </div>
            </section>

            {policy ? (
              <section className="mt-8 px-7 pb-8 sm:px-12">
                <h2 className="af-doc-kicker">成案規則</h2>
                <p className="mt-2.5 text-[13.5px] leading-relaxed text-[var(--ink-2)]">
                  同一地點 <b className="font-semibold tabular-nums text-[var(--ink)]">{policy.radius_meters}</b> 公尺內、
                  <b className="font-semibold tabular-nums text-[var(--ink)]">{policy.time_window_minutes}</b> 分鐘內，有{" "}
                  <b className="font-semibold tabular-nums text-[var(--ink)]">{policy.required_unique_reporters}</b>{" "}
                  位不同民眾回報同類災情，即自動成案並通知政府派工。
                </p>
                <p className="mt-1.5 text-[11.5px] text-[var(--faint)]">本規則為確定性判斷，不經模型推論；可於政府管理後台調整。</p>
              </section>
            ) : null}

            <footer className="af-doc-foot">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="af-btn af-btn-primary"
                  disabled={seeding}
                  onClick={async () => {
                    setSeeding(true);
                    try {
                      // re-running must replace, not stack a second copy
                    const r = await api.seedPlatformDemo(done.platform.id, Boolean(seeded));
                      setSeeded(`已帶入 ${r.reports} 筆示範通報、${r.cases} 件案件${r.translated ? "（已平移到本縣）" : ""}`);
                    } catch (e) {
                      setSeeded((e as Error).message);
                    } finally {
                      setSeeding(false);
                    }
                  }}
                >
                  {seeding ? (
                    <>
                      <span className="af-spinner" /> 帶入中…
                    </>
                  ) : seeded ? (
                    "重新帶入示範資料"
                  ) : (
                    "帶入示範資料"
                  )}
                </button>
                <Link href="/" className="af-btn af-btn-secondary">
                  回系統控制台
                </Link>
                <button type="button" className="af-btn af-btn-ghost text-xs" onClick={() => { setDone(null); setPlan(null); setDraft(null); setBrief(""); setSeeded(null); }}>
                  再建立一個平台
                </button>
              </div>
              <div className="text-[11px] leading-snug text-[var(--faint)] sm:text-right">
                {seeded ? <span className="font-medium text-[var(--st-done)]">{seeded}</span> : "示範資料會走完整的成案與派遣流程，並標示為「示範」。"}
              </div>
            </footer>
          </article>
        </div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title="建立災情平台" crumbs={[{ href: "/", label: "系統控制台" }, { label: "建立平台" }]}>
      <div className="grid gap-4 lg:grid-cols-12">
        {/* brief */}
        <section className="af-panel p-4 lg:col-span-4">
          <div className="af-eyebrow">STEP 1 · 災害背景描述</div>
          <p className="mt-1 text-xs text-[var(--muted)]">描述地區、災害類型、可能災情與希望誰能回報。系統會理解情境並從模組註冊表建議適合的功能與圖層。</p>
          <textarea className="af-input mt-2 min-h-[160px]" value={brief} onChange={(e) => setBrief(e.target.value)} placeholder={EXAMPLE} maxLength={4000} />
          <div className="mt-2 flex items-center gap-2">
            <button type="button" className="af-btn af-btn-primary" disabled={!brief.trim() || planning} onClick={() => runPlan()}>
              {planning ? (
                <>
                  <span className="af-spinner" /> 分析中…
                </>
              ) : (
                "分析情境並提出規劃"
              )}
            </button>
            <button type="button" className="af-btn af-btn-ghost text-xs" onClick={() => setBrief(EXAMPLE)}>
              帶入範例
            </button>
          </div>
          {error ? (
            <div className="mt-3">
              <ErrorBox message={error} />
            </div>
          ) : null}
          {plan ? (
            <div className="mt-4 space-y-3 text-xs">
              <div className="af-eyebrow">情境理解（{plan.intent_mode === "ai" ? "AI 解析" : "規則解析"}）</div>
              {plan.note ? <div className="rounded bg-[var(--surface-2)] px-2 py-1.5 text-[var(--muted)]">{plan.note}</div> : null}
              <dl className="grid grid-cols-[4.5rem_1fr] gap-y-1.5">
                <dt className="text-[var(--muted)]">地區</dt>
                <dd className="text-[var(--ink)]">
                  {plan.scenario.region.county || "未指定"} {plan.scenario.region.towns.join("、")}
                </dd>
                <dt className="text-[var(--muted)]">災害</dt>
                <dd className="text-[var(--ink)]">{plan.scenario.hazard_labels.join("、") || "—"}</dd>
                <dt className="text-[var(--muted)]">主要災情</dt>
                <dd className="text-[var(--ink)]">{plan.scenario.impact_labels.join("、") || "—"}</dd>
                <dt className="text-[var(--muted)]">回報者</dt>
                <dd className="text-[var(--ink)]">{plan.scenario.reporter_roles.map((r) => ROLE_LABEL[r] || r).join("、")}</dd>
                <dt className="text-[var(--muted)]">需要資料</dt>
                <dd className="text-[var(--ink-2)]">{plan.scenario.data_needs.join("、")}</dd>
              </dl>
              <div>
                <div className="af-eyebrow mb-1">規劃說明</div>
                <ul className="list-disc space-y-1 pl-4 text-[var(--ink-2)]">
                  {plan.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="af-eyebrow mb-1">政府處理流程</div>
                <ol className="space-y-1">
                  {plan.suggested_workflow.map((w, i) => (
                    <li key={w.step} className="flex gap-2">
                      <span className="w-4 flex-none font-mono text-[var(--faint)]">{i + 1}</span>
                      <span>
                        <span className="font-medium text-[var(--ink)]">{w.label}</span>
                        <span className="text-[var(--muted)]"> — {w.detail}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          ) : null}
        </section>

        {/* review / approve */}
        <section className="lg:col-span-8">
          {!plan || !draft ? (
            <div className="af-subtle flex h-full min-h-[320px] flex-col justify-center p-6">
              <div className="af-eyebrow mb-3">送出描述後會發生什麼</div>
              <ol className="grid gap-3 sm:grid-cols-3">
                {[
                  ["2", "系統理解並規劃", "辨識災害類型、縣市鄉鎮與通報對象；有 API Key 時用 LLM，沒有就用關鍵字規則，兩者結果格式相同。"],
                  ["3", "人工確認", "從模組註冊表挑出通報類別、官方圖層（雨量、河川、避難所、警戒）與成案規則，逐項可改。"],
                  ["4", "生成兩套系統", "民眾通報網站（態勢圖、通報表單、處理進度）與政府管理後台（案件佇列、派遣、官方情資）同時產生。"],
                ].map(([n, t, d]) => (
                  <li key={n} className="af-panel p-3">
                    <div className="mb-1 grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold text-white" style={{ background: "var(--brand)" }}>
                      {n}
                    </div>
                    <div className="text-sm font-semibold text-[var(--ink)]">{t}</div>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">{d}</p>
                  </li>
                ))}
              </ol>
              <p className="mt-4 text-[11px] text-[var(--faint)]">成案規則（幾位不同民眾、幾公尺內、幾分鐘內）永遠是確定性規則，不交給模型判斷。</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="af-panel p-4">
                <div className="af-eyebrow">2. 確認平台設定</div>
                <div className="mt-2 grid gap-3 sm:grid-cols-3">
                  <label className="sm:col-span-2">
                    <span className="af-label">平台名稱</span>
                    <input className="af-input mt-1" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                  </label>
                  <label>
                    <span className="af-label">發布</span>
                    <select className="af-input mt-1" value={draft.publish ? "1" : "0"} onChange={(e) => setDraft({ ...draft, publish: e.target.value === "1" })}>
                      <option value="1">建立後立即公開</option>
                      <option value="0">先存為草稿</option>
                    </select>
                  </label>
                </div>
                <div className="mt-3 text-xs text-[var(--ink-2)]">
                  災害類型：{draft.hazards.map((h) => HAZARD_LABEL[h] || h).join("、")} · 地區：{draft.county || "未指定"} {draft.towns.join("、")}
                </div>
              </div>

              <div className="af-panel p-4">
                <div className="flex items-center justify-between">
                  <div className="af-eyebrow">通報表單類別</div>
                  <span className="text-[11px] text-[var(--muted)]">已選 {draft.report_categories?.length ?? 0} 項，「其他」永遠保留</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {plan.suggested_report_categories.map((c) => {
                    const on = (draft.report_categories || []).includes(c.key);
                    return (
                      <button key={c.key} type="button" onClick={() => toggleIn("report_categories", c.key)} className={`af-chip !px-2.5 !py-1 !text-xs ${on ? "af-chip-on" : ""}`} aria-pressed={on} title={c.recommended ? "系統建議" : "情境外類別"}>
                        {c.label}
                        {c.recommended && !on ? " ·建議" : ""}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="af-panel p-4">
                <div className="af-eyebrow">成案規則（同地點多人回報）</div>
                <div className="mt-2 grid grid-cols-3 gap-3">
                  {(
                    [
                      ["required_unique_reporters", "不同回報者門檻（人）", 1, 20],
                      ["radius_meters", "聚類半徑（公尺）", 10, 5000],
                      ["time_window_minutes", "時間窗（分鐘）", 1, 10080],
                    ] as const
                  ).map(([k, label, min, max]) => (
                    <label key={k}>
                      <span className="af-label">{label}</span>
                      <input
                        type="number"
                        min={min}
                        max={max}
                        className="af-input mt-1"
                        value={draft.cluster_policy?.[k] ?? ""}
                        onChange={(e) => setDraft({ ...draft, cluster_policy: { ...(draft.cluster_policy || {}), [k]: Number(e.target.value) } })}
                      />
                    </label>
                  ))}
                </div>
                <div className="mt-1.5 text-[11px] text-[var(--muted)]">同一人重複送出只計一次；規則由系統確定性執行，不經模型判斷。建立後仍可在指揮中心調整。</div>
              </div>

              <div className="af-panel p-4">
                <div className="af-eyebrow">地圖圖層</div>
                <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                  {plan.suggested_layers.map((l) => {
                    const on = (draft.layers || []).includes(l.key);
                    return (
                      <label key={l.key} className={`flex cursor-pointer items-start gap-2 rounded border px-2.5 py-2 text-xs ${on ? "border-[var(--brand)] bg-[var(--surface-2)]" : "border-[var(--line)]"} ${l.core ? "opacity-90" : ""}`}>
                        <input type="checkbox" className="mt-0.5" checked={on || l.core} disabled={l.core} onChange={() => toggleIn("layers", l.key)} />
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5 font-medium text-[var(--ink)]">
                            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LAYERS[l.key]?.hex || "#667085" }} />
                            {l.name}
                            {l.core ? <span className="af-chip !py-0 text-[10px]">核心</span> : null}
                            {l.live === false ? <span className="af-chip !py-0 text-[10px]" style={{ color: "var(--st-pending)" }}>需金鑰</span> : null}
                            {l.live === true ? <span className="af-chip !py-0 text-[10px]" style={{ color: "var(--st-done)" }}>即時</span> : null}
                          </span>
                          <span className="block text-[var(--muted)]">{l.reason}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="af-panel p-4">
                <div className="af-eyebrow">功能模組</div>
                <div className="mt-2 space-y-3">
                  {DOMAIN_ORDER.filter((d) => modulesByDomain[d]?.length).map((d) => (
                    <div key={d}>
                      <div className="mb-1 text-[11px] font-semibold text-[var(--ink-2)]">{DOMAIN_LABEL[d] || d}</div>
                      <div className="grid gap-1.5 sm:grid-cols-2">
                        {modulesByDomain[d].map((m) => {
                          const on = (draft.modules || []).includes(m.id);
                          return (
                            <label key={m.id} className={`flex cursor-pointer items-start gap-2 rounded border px-2.5 py-2 text-xs ${on || m.core ? "border-[var(--brand)] bg-[var(--surface-2)]" : "border-[var(--line)]"}`}>
                              <input type="checkbox" className="mt-0.5" checked={on || m.core} disabled={m.core} onChange={() => toggleIn("modules", m.id)} />
                              <span className="min-w-0">
                                <span className="flex flex-wrap items-center gap-1.5 font-medium text-[var(--ink)]">
                                  {m.name}
                                  <span className="af-chip !py-0 text-[10px]">{MODULE_TYPE_LABEL[m.module_type] || m.module_type}</span>
                                  {m.core ? <span className="af-chip !py-0 text-[10px]">核心</span> : null}
                                </span>
                                <span className="block text-[var(--muted)]">{m.reason}</span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="af-panel sticky bottom-2 flex items-center justify-between gap-3 p-3 shadow-md">
                <div className="text-xs text-[var(--muted)]">
                  3. 人工確認後生成：{(draft.modules || []).length} 個模組、{(draft.layers || []).length} 個圖層、{(draft.report_categories || []).length} 個通報類別。核心模組與相依模組會自動補齊。
                </div>
                <button type="button" className="af-btn af-btn-primary af-btn-lg" disabled={executing || !draft.name.trim()} onClick={runExecute}>
                  {executing ? (
                    <>
                      <span className="af-spinner" /> 系統生成中…
                    </>
                  ) : (
                    "確認並建立平台"
                  )}
                </button>
                {executing ? (
                  <ol className="af-gensteps">
                    {[
                      ["組建模組、圖層與成案規則", phase === "composing" ? "run" : "done"],
                      ["生成公開災情網站與政府後台", phase === "composing" ? "wait" : "done"],
                      [withDemo ? "產生示範災情、成案與派遣紀錄" : "等待第一筆民眾通報", phase === "seeding" ? "run" : phase === "composing" ? "wait" : "done"],
                    ].map(([label, state]) => (
                      <li key={String(label)} className={`af-genstep af-genstep-${state}`}>
                        <span className="af-genstep-dot">{state === "done" ? "✓" : state === "run" ? <span className="af-spinner !h-3 !w-3" /> : null}</span>
                        {label}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <label className="flex items-center gap-2 text-xs text-[var(--ink-2)]">
                    <input type="checkbox" checked={withDemo} onChange={(e) => setWithDemo(e.target.checked)} className="h-3.5 w-3.5 accent-[var(--brand)]" />
                    一併產生示範災情資料
                    <span className="text-[var(--faint)]">（走完整的成案與派遣流程，標示為「示範」；可在管理後台清除）</span>
                  </label>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </ConsoleShell>
  );
}
