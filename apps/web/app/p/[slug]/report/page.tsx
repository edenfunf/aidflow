"use client";

// Mobile-first citizen report form. Categories, roles and the map centre all
// come from the platform configuration (Module Registry), not from code.
// Personal data is optional: leaving an e-mail is only needed to receive the
// case's progress.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import PortalShell from "@/components/PortalShell";
import { ErrorBox, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { getClientKey } from "@/lib/clientKey";
import { categoryHex } from "@/lib/labels";
import { CategoryIcon } from "@/lib/categoryIcons";
import ProgressRing from "@/components/ProgressRing";
import type { PublicPlatform, SubmitReportResponse } from "@/lib/types";

const PickerMap = dynamic(() => import("@/components/PickerMap"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> });

type GeoState = "idle" | "locating" | "ok" | "denied" | "manual";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

export default function ReportPage() {
  const { slug } = useParams<{ slug: string }>();
  const [platform, setPlatform] = useState<PublicPlatform | null>(null);
  const [category, setCategory] = useState("");
  const [point, setPoint] = useState<[number, number] | null>(null);
  const [geo, setGeo] = useState<GeoState>("idle");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");
  const [role, setRole] = useState("citizen");
  const [files, setFiles] = useState<File[]>([]);
  const [subscribe, setSubscribe] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitReportResponse | null>(null);
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    api.publicPlatform(slug).then(setPlatform).catch((e) => setError((e as Error).message));
  }, [slug]);

  const previews = useMemo(() => files.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })), [files]);
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews]);

  function locate() {
    if (!navigator.geolocation) {
      setGeo("manual");
      return;
    }
    setGeo("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPoint([pos.coords.latitude, pos.coords.longitude]);
        setAccuracy(Math.round(pos.coords.accuracy));
        setGeo("ok");
      },
      () => setGeo("denied"),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 }
    );
  }

  const emailOk = !subscribe || EMAIL_RE.test(email.trim());
  const emailError = subscribe && email.trim() !== "" && !EMAIL_RE.test(email.trim());

  async function submit() {
    if (!platform || !category || !emailOk) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitReport(slug, {
        category,
        description: description.trim() || null,
        lat: point?.[0] ?? null,
        lon: point?.[1] ?? null,
        address: address.trim() || null,
        reporter_role: role,
        reporter_name: name.trim() || null,
        reporter_contact: phone.trim() || null,
        reporter_email: email.trim() || null,
        notify_opt_in: subscribe && Boolean(email.trim()),
        client_key: getClientKey(),
      });
      setResult(res);
      if (files.length) {
        let ok = 0;
        for (const f of files.slice(0, 5)) {
          try {
            await api.uploadReportPhoto(res.report_id, f);
            ok += 1;
          } catch {
            /* keep going */
          }
        }
        setPhotoNote(ok === files.length ? `已上傳 ${ok} 張照片` : `已上傳 ${ok}/${files.length} 張照片`);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = Boolean(platform && category && !submitting && emailOk);
  const center = point ?? platform?.map.center ?? [23.91, 120.69];

  if (result) {
    const caseHref = result.case_id ? `/p/${slug}/cases/${result.case_id}` : null;
    return (
      <PortalShell platform={platform} slug={slug}>
        <div className="mx-auto max-w-xl">
          <div className="af-panel p-6">
            <div className="flex items-center gap-2.5">
              <span className="af-check grid h-9 w-9 place-items-center rounded-full text-white" style={{ background: "var(--st-done)" }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M5 12.5 10 17.5 19 7" />
                </svg>
              </span>
              <h1 className="text-[26px] font-bold text-[var(--ink)]">通報已送出</h1>
            </div>
            <p className="mt-3 text-[18px] leading-relaxed text-[var(--ink-2)]">{result.message}</p>
            {photoNote ? <p className="mt-1 text-[15px] text-[var(--muted)]">{photoNote}</p> : null}
            {result.cluster_id ? (
              <div className="af-subtle mt-4 flex items-center gap-4 p-4">
                <ProgressRing value={result.unique_reporters} total={result.required_unique_reporters} label="不同回報者" />
                <div className="text-[15px] leading-relaxed text-[var(--ink-2)]">
                  {result.unique_reporters >= result.required_unique_reporters ? (
                    <>
                      <div className="text-[17px] font-semibold text-[var(--st-active)]">已成案，承辦人員審核中</div>
                      承辦人員會判斷由權責單位處理（上報 EMIC），或開放民眾協助處理。
                    </>
                  ) : (
                    <>
                      <div className="text-[17px] font-semibold text-[var(--st-pending)]">縣府承辦人員已收到通知</div>
                      同一地點有 {result.required_unique_reporters} 位以上民眾回報時會自動成案；您可以把通報連結分享給在場的人。
                    </>
                  )}
                </div>
              </div>
            ) : null}
            {result.notify_opt_in ? (
              <div className="mt-3 rounded bg-[var(--surface-2)] px-4 py-3 text-[15px] text-[var(--ink-2)]">
                案件每次更新狀態，都會寄信到 <b>{email}</b>；信中附有取消通知的連結。
              </div>
            ) : null}
            <div className="mt-5 flex flex-col gap-2.5">
              {caseHref ? (
                <Link href={caseHref} className="af-btn af-btn-primary af-btn-lg">
                  查看處理進度 {result.case_number ? `（${result.case_number}）` : ""}
                </Link>
              ) : (
                <Link href={`/p/${slug}`} className="af-btn af-btn-primary af-btn-lg">
                  回到災情地圖
                </Link>
              )}
              <button
                type="button"
                className="af-btn af-btn-secondary af-btn-lg"
                onClick={() => {
                  setResult(null);
                  setCategory("");
                  setDescription("");
                  setFiles([]);
                  setPhotoNote(null);
                }}
              >
                再通報一筆
              </button>
            </div>
            <p className="mt-5 text-[14px] leading-relaxed text-[var(--faint)]">您的姓名、電話與 Email 僅供承辦人員聯繫與寄送進度，不會公開。公開頁面上的位置已粗化、文字已去識別化，照片會移除拍攝位置等資訊。</p>
          </div>
        </div>
      </PortalShell>
    );
  }

  return (
    <PortalShell platform={platform} slug={slug}>
      <div className="mx-auto max-w-xl pb-28 sm:pb-0">
        <div className="mb-4">
          <h1 className="text-[28px] font-bold leading-tight text-[var(--ink)]">我要通報災情</h1>
          <p className="mt-2 rounded-md border px-3 py-2 text-[16px] font-medium" style={{ borderColor: "#fecdca", background: "#fef3f2", color: "#b42318" }}>
            危及生命請先撥打 <a href="tel:119" className="-my-1 inline-block px-1 py-1 font-bold underline">119</a>。
          </p>
          <p className="mt-2 text-[15px] text-[var(--muted)]">免登入、免註冊。承辦人員收到通報後會審核處理方式。</p>
        </div>
        {error ? (
          <div className="mb-3">
            <ErrorBox message={error} />
          </div>
        ) : null}

        {/* 1. what */}
        <section className="af-panel mb-3 p-4 sm:p-5">
          <h2 className="mb-3 text-[19px] font-semibold text-[var(--ink)]">1. 發生什麼事？</h2>
          {!platform ? (
            <Skeleton className="h-28" />
          ) : (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {platform.report_categories.map((c) => {
                const on = category === c.key;
                return (
                  <button
                    key={c.key}
                    type="button"
                    onClick={() => setCategory(c.key)}
                    aria-pressed={on}
                    className="flex min-h-[56px] items-center gap-2.5 rounded-md border px-3 py-3 text-left text-[17px] font-medium transition"
                    style={{
                      borderColor: on ? "var(--brand)" : "var(--line-2)",
                      background: on ? "var(--brand)" : "var(--surface)",
                      color: on ? "#fff" : "var(--ink)",
                    }}
                  >
                    <span className="inline-grid h-9 w-9 flex-none place-items-center rounded-full text-white" style={{ background: on ? "rgba(255,255,255,0.22)" : categoryHex(c.key) }}>
                      <CategoryIcon category={c.key} size={19} />
                    </span>
                    {c.label}
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* 2. where */}
        <section className="af-panel mb-3 p-4 sm:p-5">
          <h2 className="mb-3 text-[19px] font-semibold text-[var(--ink)]">2. 在哪裡？</h2>
          <button type="button" className="af-btn af-btn-primary af-btn-lg w-full" onClick={locate} disabled={geo === "locating"}>
            {geo === "locating" ? (
              <>
                <span className="af-spinner" /> 定位中…
              </>
            ) : (
              "使用目前位置（GPS 定位）"
            )}
          </button>
          <div className="mt-2 text-[15px] text-[var(--muted)]">
            {geo === "ok" && point ? `已定位（誤差約 ${accuracy ?? "?"} 公尺）` : geo === "denied" ? "無法取得定位，請在地圖上點選位置" : "或直接在下方地圖點選位置"}
          </div>
          <div className="mt-2 overflow-hidden rounded-md border" style={{ borderColor: "var(--line)" }}>
            <div className="h-64">
              <PickerMap
                center={center}
                zoom={point ? 15 : platform?.map.zoom ?? 11}
                point={point}
                accuracy={geo === "ok" ? accuracy : null}
                color={category ? categoryHex(category) : undefined}
                onPick={(lat, lon) => {
                  setPoint([lat, lon]);
                  setGeo("manual");
                }}
              />
            </div>
          </div>
          <div className="mt-1.5 text-[14px] text-[var(--muted)]">{point ? `座標 ${point[0].toFixed(5)}, ${point[1].toFixed(5)}` : "尚未選擇位置（有位置的通報才能與附近其他人的回報合併）"}</div>
          <input className="af-input mt-2" placeholder="地點補充（選填，例如：台14甲線 18K 清境下方）" value={address} onChange={(e) => setAddress(e.target.value)} maxLength={300} />
        </section>

        {/* 3. photo */}
        <section className="af-panel mb-3 p-4 sm:p-5">
          <h2 className="mb-3 text-[19px] font-semibold text-[var(--ink)]">3. 現場照片（選填）</h2>
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" multiple className="hidden" onChange={(e) => setFiles([...files, ...Array.from(e.target.files || [])].slice(0, 5))} />
          <div className="flex flex-wrap gap-2.5">
            {previews.map((p, i) => (
              <div key={p.url} className="relative h-24 w-24 overflow-hidden rounded-md border" style={{ borderColor: "var(--line)" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
                <button type="button" className="absolute right-1 top-1 rounded bg-black/60 px-1.5 text-[13px] text-white" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label="移除照片">
                  ✕
                </button>
              </div>
            ))}
            {files.length < 5 ? (
              <button type="button" className="flex h-24 w-24 flex-col items-center justify-center rounded-md border border-dashed text-[15px] text-[var(--muted)]" style={{ borderColor: "var(--line-2)" }} onClick={() => fileInput.current?.click()}>
                <span className="text-2xl leading-none">＋</span>
                拍照／上傳
              </button>
            ) : null}
          </div>
          <div className="mt-2 text-[14px] text-[var(--faint)]">最多 5 張，每張 8 MB 以內。照片會公開於案件頁（已移除拍攝位置等資訊），請避免拍到人臉與車牌。</div>
        </section>

        {/* 4. description */}
        <section className="af-panel mb-3 p-4 sm:p-5">
          <h2 className="mb-3 text-[19px] font-semibold text-[var(--ink)]">4. 簡單描述（選填）</h2>
          <textarea className="af-input" placeholder="例如：路基掏空約 30 公尺，車輛無法通行，仍有落石" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
          <div className="mt-3 text-[15px] font-medium text-[var(--ink-2)]">我是</div>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {(platform?.reporter_roles || []).map((r) => (
              <button key={r.key} type="button" onClick={() => setRole(r.key)} className={`af-chip !px-3.5 !py-2 !text-[15px] ${role === r.key ? "af-chip-on" : ""}`} aria-pressed={role === r.key}>
                {r.label}
              </button>
            ))}
          </div>
        </section>

        {/* 5. progress subscription */}
        <section className="af-panel mb-3 p-4 sm:p-5">
          <h2 className="mb-2 text-[19px] font-semibold text-[var(--ink)]">5. 想知道後續處理進度嗎？（選填）</h2>
          <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3" style={{ borderColor: subscribe ? "var(--brand)" : "var(--line-2)", background: subscribe ? "var(--surface-2)" : undefined }}>
            <input type="checkbox" className="mt-1 h-5 w-5 flex-none accent-[var(--brand)]" checked={subscribe} onChange={(e) => setSubscribe(e.target.checked)} />
            <span>
              <span className="block text-[17px] font-medium text-[var(--ink)]">我要接收案件處理進度通知</span>
              <span className="block text-[14px] text-[var(--muted)]">案件狀態更新時寄信通知您；不留資料也可以正常通報。</span>
            </span>
          </label>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span className="af-label">Email{subscribe ? "（接收通知必填）" : "（選填）"}</span>
              <input className="af-input mt-1" type="email" inputMode="email" autoComplete="email" placeholder="name@example.com" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} aria-invalid={emailError} />
              {emailError ? <span className="mt-1 block text-[14px] text-[var(--sev-high)]">Email 格式不正確</span> : null}
            </label>
            <label>
              <span className="af-label">稱呼（選填）</span>
              <input className="af-input mt-1" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
            </label>
            <label>
              <span className="af-label">電話（選填，供承辦聯繫）</span>
              <input className="af-input mt-1" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={100} />
            </label>
          </div>
          <p className="mt-3 text-[13.5px] leading-relaxed text-[var(--faint)]">
            個人資料蒐集告知：本平台蒐集您選填的稱呼、電話與 Email，僅用於災情查證聯繫及寄送本案處理進度，不會公開或作其他用途；您可隨時透過通知信中的連結取消。依個人資料保護法，您可請求查詢、更正或刪除。
          </p>
        </section>

        <div className="fixed inset-x-0 bottom-0 z-10 border-t bg-[var(--bg)]/95 px-3 py-3 backdrop-blur sm:static sm:border-0 sm:bg-transparent sm:px-0" style={{ borderColor: "var(--line)" }}>
          <button type="button" className="af-btn af-btn-lg w-full !py-4 !text-[20px] font-bold text-white disabled:opacity-60" style={{ background: canSubmit ? "#d92d20" : "var(--brand)" }} disabled={!canSubmit} onClick={submit}>
            {submitting ? (
              <>
                <span className="af-spinner" /> 送出中…
              </>
            ) : category ? (
              `送出通報：${platform?.report_categories.find((c) => c.key === category)?.label ?? ""}`
            ) : (
              "請先選擇災情類別"
            )}
          </button>
        </div>
      </div>
    </PortalShell>
  );
}
