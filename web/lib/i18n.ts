// UI text follows the question's language (MVP 1d). The backend sends the language with the first step.
import type { Lang, Step } from "./api";

export const T = {
  en: {
    placeholder: "Ask about an LQ45 company's annual report…",
    send: "Ask",
    waking: "Waking up the server (free tier, this can take up to a minute)…",
    offline: "The server isn't responding. Please try again in a minute.",
    how: "How I answered",
    retrieved: "Pages searched",
    score: "score",
    checks: "Checks",
    repair: "Repair round used",
    yes: "yes",
    no: "no",
    prompt: "Prompt",
    model: "Model",
    latency: "Time",
    cached: "From cache",
    closest: "Closest pages I found:",
    openPdf: "Open the PDF page",
    helpful: "Was this helpful?",
    reasonPrompt: "What was wrong? (optional)",
    sendFeedback: "Send",
    thanks: "Thanks for the feedback.",
    error: "Something went wrong. Please try again.",
    logged: "Questions are logged to improve answers. Please don't include personal data.",
    sourceNote: "Answers come only from FY2025 annual reports of LQ45 companies. Not investment advice.",
    close: "Close",
    figures: "Figures",
  },
  id: {
    placeholder: "Tanyakan isi laporan tahunan emiten LQ45…",
    send: "Tanya",
    waking: "Membangunkan server (tier gratis, bisa sampai satu menit)…",
    offline: "Server tidak merespons. Silakan coba lagi sebentar lagi.",
    how: "Cara saya menjawab",
    retrieved: "Halaman yang dicari",
    score: "skor",
    checks: "Pemeriksaan",
    repair: "Putaran perbaikan dipakai",
    yes: "ya",
    no: "tidak",
    prompt: "Prompt",
    model: "Model",
    latency: "Waktu",
    cached: "Dari cache",
    closest: "Halaman terdekat yang saya temukan:",
    openPdf: "Buka halaman PDF",
    helpful: "Apakah jawaban ini membantu?",
    reasonPrompt: "Apa yang salah? (opsional)",
    sendFeedback: "Kirim",
    thanks: "Terima kasih atas masukannya.",
    error: "Terjadi kesalahan. Silakan coba lagi.",
    logged: "Pertanyaan dicatat untuk memperbaiki jawaban. Jangan sertakan data pribadi.",
    sourceNote: "Jawaban hanya dari laporan tahunan FY2025 emiten LQ45. Bukan saran investasi.",
    close: "Tutup",
    figures: "Gambar",
  },
} satisfies Record<Lang, Record<string, string>>;

export function stepLabel(s: Step, lang: Lang): string {
  const id = lang === "id";
  switch (s.step) {
    case "understanding":
      return id ? "Memahami pertanyaan" : "Understanding the question";
    case "searching": {
      const who = s.tickers?.length ? s.tickers.join(", ") : id ? "semua emiten" : "all companies";
      return id ? `Mencari di laporan ${who} ${s.years?.join(", ") ?? ""}` : `Searching ${who} ${s.years?.join(", ") ?? ""} reports`;
    }
    case "writing":
      return id ? `Menulis jawaban dari ${s.pages?.length ?? 0} halaman` : `Writing from ${s.pages?.length ?? 0} pages`;
    case "checking":
      return id ? "Memeriksa kutipan" : "Checking citations";
    case "repairing":
      return id ? `Memperbaiki ${s.errors} masalah` : `Fixing ${s.errors} failed check(s)`;
    case "cached":
      return id ? "Jawaban tersimpan ditemukan" : "Found a saved answer";
    default:
      return s.step;
  }
}

/** Questions arrive before the backend has said which language they are in; a cheap guess for the first frame. */
export function guessLang(text: string): Lang {
  return /\b(apa|apakah|berapa|bagaimana|kenapa|mengapa|siapa|yang|dan|tahun|laba|pendapatan)\b/i.test(text)
    ? "id"
    : "en";
}
