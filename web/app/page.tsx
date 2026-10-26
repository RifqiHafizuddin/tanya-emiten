"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerCard } from "@/components/AnswerCard";
import { type Answer, ask, health, type Lang, type Step } from "@/lib/api";
import { guessLang, stepLabel, T } from "@/lib/i18n";

type Turn = { question: string; lang: Lang; steps: Step[]; answer?: Answer; notice?: string };

const EXAMPLES = [
  "Berapa rasio NPL BBCA tahun 2025?",
  "What drove AMRT's revenue growth in 2025?",
  "Apa strategi transformasi digital BBRI?",
  "How much coal did AADI produce in 2025?",
];

type Server = "checking" | "waking" | "ready" | "offline";

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [server, setServer] = useState<Server>("checking");
  const convId = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // A cold HF Space takes a while to answer its first request: show "waking up" instead of a dead page.
  useEffect(() => {
    let stop = false;
    const slow = setTimeout(() => !stop && setServer((s) => (s === "checking" ? "waking" : s)), 1500);
    (async () => {
      for (let i = 0; i < 40 && !stop; i++) {
        try {
          await health(AbortSignal.timeout(10000));
          if (!stop) setServer("ready");
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
      if (!stop) setServer("offline");
    })();
    return () => { stop = true; clearTimeout(slow); };
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" }); // newer browsers return a Promise: don't hand it to React
  }, [turns]);

  const update = (fn: (t: Turn) => Turn) => setTurns((ts) => [...ts.slice(0, -1), fn(ts[ts.length - 1])]);

  async function submit(question: string) {
    question = question.trim();
    if (question.length < 3 || busy) return;
    setInput("");
    setBusy(true);
    setTurns((ts) => [...ts, { question, lang: guessLang(question), steps: [] }]);
    try {
      await ask(question, convId.current, (e) => {
        if (e.event === "step") update((t) => ({ ...t, lang: e.data.lang ?? t.lang, steps: [...t.steps, e.data] }));
        else if (e.event === "answer") {
          convId.current = e.data.conv_id;
          update((t) => ({ ...t, lang: e.data.lang, answer: e.data }));
        } else if (e.event === "limit") update((t) => ({ ...t, lang: e.data.lang, notice: e.data.message }));
        else update((t) => ({ ...t, notice: T[t.lang].error }));
      });
    } catch {
      update((t) => ({ ...t, notice: T[t.lang].error }));
    } finally {
      setBusy(false);
    }
  }

  const uiLang: Lang = turns.length ? turns[turns.length - 1].lang : "en";
  const t = T[uiLang];

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col px-4">
      <header className="py-6">
        <h1 className="text-2xl font-semibold tracking-tight">Tanya Emiten</h1>
        <p className="text-sm text-slate-500">
          Cited answers from LQ45 annual reports · Jawaban bersumber dari laporan tahunan emiten LQ45
        </p>
      </header>

      {server === "waking" && <Banner>{T.en.waking}<br />{T.id.waking}</Banner>}
      {server === "offline" && <Banner>{T.en.offline}<br />{T.id.offline}</Banner>}

      <section className="flex-1 space-y-8 pb-6">
        {!turns.length && (
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => submit(q)} disabled={busy || server !== "ready"}
                      className="rounded-full border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:hover:bg-slate-800">
                {q}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn, i) => (
          <article key={i} className="space-y-3">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-slate-800 px-4 py-2 text-white dark:bg-slate-200 dark:text-slate-900">
              {turn.question}
            </p>
            {!turn.answer && !turn.notice && (
              <ol className="space-y-1 text-sm text-slate-500" aria-live="polite">
                {turn.steps.map((s, j) => (
                  <li key={j} className="flex items-center gap-2">
                    <span aria-hidden className={j === turn.steps.length - 1 ? "animate-pulse" : ""}>
                      {j === turn.steps.length - 1 ? "●" : "✓"}
                    </span>
                    {stepLabel(s, turn.lang)}
                  </li>
                ))}
                {!turn.steps.length && <li className="animate-pulse">…</li>}
              </ol>
            )}
            {turn.notice && <Banner>{turn.notice}</Banner>}
            {turn.answer && <AnswerCard a={turn.answer} />}
          </article>
        ))}
        <div ref={bottom} />
      </section>

      <form onSubmit={(e) => { e.preventDefault(); submit(input); }}
            className="sticky bottom-0 -mx-4 border-t border-slate-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} placeholder={t.placeholder}
                 aria-label={t.placeholder}
                 className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-transparent px-3 py-2 outline-none focus:border-sky-500 dark:border-slate-600" />
          <button disabled={busy || server !== "ready" || input.trim().length < 3}
                  className="rounded-lg bg-sky-700 px-4 py-2 font-medium text-white disabled:opacity-40">
            {t.send}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">{t.sourceNote} {t.logged}</p>
      </form>
    </main>
  );
}

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
      {children}
    </div>
  );
}
