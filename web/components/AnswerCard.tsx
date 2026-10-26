"use client";

import { useEffect, useState } from "react";
import { type Answer, type Figure, pdfLink, sendFeedback } from "@/lib/api";
import { T } from "@/lib/i18n";

export function AnswerCard({ a }: { a: Answer }) {
  const t = T[a.lang];
  const [openQuote, setOpenQuote] = useState<number | null>(null);
  const [zoomed, setZoomed] = useState<Figure | null>(null);

  return (
    <div className="space-y-4">
      {a.refusal ? (
        <div className="rounded-lg border border-amber-300/60 bg-amber-50 p-4 text-amber-950 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-100">
          <p>{a.refusal_reason}</p>
          {!!a.closest_pages?.length && (
            <p className="mt-2 text-sm">
              {t.closest}{" "}
              {a.closest_pages.map((p, i) => (
                <a key={i} href={pdfLink(a.sources?.[p.doc_id], p.page)} target="_blank" rel="noreferrer"
                   className="mr-2 underline underline-offset-2">
                  {p.ticker} p.{p.page}
                </a>
              ))}
            </p>
          )}
        </div>
      ) : (
        <ul className="space-y-3">
          {a.claims.map((c, i) => (
            <li key={i} className="leading-relaxed">
              {c.text}{" "}
              <button onClick={() => setOpenQuote(openQuote === i ? null : i)} aria-expanded={openQuote === i}
                      className="ml-1 inline-flex items-center rounded-full bg-sky-100 px-2 py-0.5 align-middle text-xs font-medium text-sky-900 hover:bg-sky-200 dark:bg-sky-900/50 dark:text-sky-100 dark:hover:bg-sky-800/60">
                {c.ticker} p.{c.page}
              </button>
              {openQuote === i && (
                <blockquote className="mt-2 border-l-2 border-sky-400 pl-3 text-sm text-slate-600 dark:text-slate-300">
                  “{c.quote}”
                  {pdfLink(a.sources?.[c.doc_id], c.page) && (
                    <a href={pdfLink(a.sources?.[c.doc_id], c.page)} target="_blank" rel="noreferrer"
                       className="ml-2 whitespace-nowrap text-sky-700 underline underline-offset-2 dark:text-sky-300">
                      {t.openPdf} ↗
                    </a>
                  )}
                </blockquote>
              )}
            </li>
          ))}
        </ul>
      )}

      {a.figures.some((f) => f.url) && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {a.figures.filter((f) => f.url).map((f) => (
            <button key={f.figure_id} onClick={() => setZoomed(f)}
                    className="group overflow-hidden rounded-lg border border-slate-200 bg-white text-left dark:border-slate-700 dark:bg-slate-900">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={f.url!} alt={f.caption ?? f.why} loading="lazy"
                   className="h-32 w-full object-contain p-1 transition group-hover:scale-[1.02]" />
              <span className="block truncate border-t border-slate-100 px-2 py-1 text-xs text-slate-500 dark:border-slate-800">
                {f.ticker} p.{f.page} · {f.why}
              </span>
            </button>
          ))}
        </div>
      )}

      <p className="text-xs text-slate-500">{a.disclaimer}</p>
      <HowPanel a={a} />
      {a.conv_id && <Feedback a={a} />}
      {zoomed && <Lightbox f={zoomed} close={() => setZoomed(null)} label={t.close} openPdf={t.openPdf} />}
    </div>
  );
}

function HowPanel({ a }: { a: Answer }) {
  const t = T[a.lang];
  return (
    <details className="rounded-lg border border-slate-200 text-sm dark:border-slate-700">
      <summary className="cursor-pointer select-none px-3 py-2 text-slate-600 dark:text-slate-300">{t.how}</summary>
      <div className="space-y-3 border-t border-slate-200 px-3 py-3 dark:border-slate-700">
        <div>
          <div className="mb-1 font-medium">{t.retrieved}</div>
          <ul className="grid gap-1 sm:grid-cols-2">
            {a.retrieved.map((r) => (
              <li key={r.chunk_id} className="flex justify-between gap-2 font-mono text-xs">
                <span>{r.ticker} p.{r.page} · {r.kind}</span>
                <span className="text-slate-500">{t.score} {r.score.toFixed(4)}</span>
              </li>
            ))}
          </ul>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          <dt className="text-slate-500">{t.checks}</dt>
          <dd className="font-mono">{JSON.stringify(a.checks)}</dd>
          <dt className="text-slate-500">{t.repair}</dt>
          <dd>{a.repair_used ? t.yes : t.no}</dd>
          <dt className="text-slate-500">{t.prompt}</dt>
          <dd className="font-mono">{a.prompt_version}</dd>
          {a.model && (<><dt className="text-slate-500">{t.model}</dt><dd className="font-mono">{a.model}</dd></>)}
          <dt className="text-slate-500">{t.latency}</dt>
          <dd>{(a.latency_ms / 1000).toFixed(1)} s{a.cached ? ` · ${t.cached}` : ""}</dd>
        </dl>
      </div>
    </details>
  );
}

function Feedback({ a }: { a: Answer }) {
  const t = T[a.lang];
  const [state, setState] = useState<"idle" | "reason" | "sent" | "failed">("idle");
  const [reason, setReason] = useState("");

  const send = async (rating: "up" | "down", why?: string) => {
    try {
      await sendFeedback(a.conv_id, a.turn, rating, why);
      setState("sent");
    } catch {
      setState("failed");
    }
  };

  if (state === "sent") return <p className="text-xs text-slate-500">{t.thanks}</p>;
  if (state === "failed") return <p className="text-xs text-red-600 dark:text-red-400">{t.error}</p>;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
      <span>{t.helpful}</span>
      <button aria-label="thumbs up" onClick={() => send("up")}
              className="rounded-md border border-slate-200 px-2 py-0.5 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">👍</button>
      <button aria-label="thumbs down" onClick={() => setState("reason")}
              className="rounded-md border border-slate-200 px-2 py-0.5 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">👎</button>
      {state === "reason" && (
        <form className="flex w-full gap-2" onSubmit={(e) => { e.preventDefault(); send("down", reason); }}>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder={t.reasonPrompt}
                 className="min-w-0 flex-1 rounded-md border border-slate-300 bg-transparent px-2 py-1 dark:border-slate-600" />
          <button className="rounded-md bg-slate-800 px-3 py-1 text-white dark:bg-slate-200 dark:text-slate-900">
            {t.sendFeedback}
          </button>
        </form>
      )}
    </div>
  );
}

function Lightbox({ f, close, label, openPdf }: { f: Figure; close: () => void; label: string; openPdf: string }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);
  return (
    <div role="dialog" aria-modal="true" onClick={close}
         className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <figure onClick={(e) => e.stopPropagation()}
              className="max-h-full max-w-4xl overflow-auto rounded-lg bg-white p-3 dark:bg-slate-900">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={f.url!} alt={f.caption ?? f.why} className="max-h-[75vh] w-auto" />
        <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>{f.caption ?? f.why} · {f.ticker} p.{f.page}</span>
          <span className="flex gap-3">
            <a href={pdfLink(f.source_url, f.page)} target="_blank" rel="noreferrer"
               className="text-sky-700 underline underline-offset-2 dark:text-sky-300">{openPdf} ↗</a>
            <button onClick={close} className="underline underline-offset-2">{label}</button>
          </span>
        </figcaption>
      </figure>
    </div>
  );
}
