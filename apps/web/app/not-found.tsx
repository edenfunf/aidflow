import Link from "next/link";

// Unknown paths must answer 404, not a soft 200 (Nessus plugin 10386).
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-[620px] flex-col justify-center px-5 py-10">
      <p className="text-[15px] font-semibold tracking-[0.12em] text-[var(--muted)]">404</p>
      <h1 className="mt-2 text-[28px] font-bold text-[var(--ink)]">找不到這個頁面</h1>
      <p className="mt-2 text-[17px] leading-relaxed text-[var(--ink-2)]">
        連結可能已經失效，或災害平台已經結束通報。您可以回首頁查看目前開放通報的災害事件。
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link href="/" className="af-btn af-btn-primary af-btn-lg">
          回首頁
        </Link>
      </div>
      <p className="mt-6 text-[15px] text-[var(--muted)]">
        災情危及生命請撥打 <a href="tel:119" className="font-semibold underline">119</a>。
      </p>
    </main>
  );
}
