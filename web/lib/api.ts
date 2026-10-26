// Client for the FastAPI backend (backend/api.py). POST /ask streams server-sent events, which EventSource can't
// send, so the stream is read with fetch.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Lang = "en" | "id";

export type Step = { step: string; lang?: Lang; tickers?: string[]; years?: number[]; pages?: [string, number][];
  errors?: number };

export type Claim = { text: string; quote: string; chunk_id: string; ticker: string; page: number; doc_id: string };

export type Figure = { figure_id: string; page: number; kind: string; caption: string | null; url: string | null;
  source_url: string; ticker: string; why: string };

export type Answer = {
  question: string;
  lang: Lang;
  prompt_version: string;
  disclaimer: string;
  refusal: boolean;
  refusal_reason: string | null;
  claims: Claim[];
  figures: Figure[];
  closest_pages?: { ticker: string; page: number; doc_id: string }[];
  sources?: Record<string, string>;
  retrieved: { chunk_id: string; ticker: string; page: number; score: number; kind: string }[];
  checks: Record<string, unknown>;
  repair_used: boolean;
  model?: string;
  tokens?: number;
  latency_ms: number;
  cached?: boolean;
  conv_id: string;
  turn: number;
};

export type AskEvent =
  | { event: "step"; data: Step }
  | { event: "answer"; data: Answer }
  | { event: "limit"; data: { message: string; lang: Lang } }
  | { event: "error"; data: { message: string } };

export async function ask(question: string, convId: string | null, onEvent: (e: AskEvent) => void): Promise<void> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, conv_id: convId }),
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const fields = Object.fromEntries(
        block.split("\n").map((line) => [line.slice(0, line.indexOf(": ")), line.slice(line.indexOf(": ") + 2)]),
      );
      if (fields.event && fields.data) onEvent({ event: fields.event, data: JSON.parse(fields.data) } as AskEvent);
    }
  }
}

export async function health(signal?: AbortSignal): Promise<{ ok: boolean; model_loaded: boolean }> {
  const res = await fetch(`${API_URL}/health`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function sendFeedback(convId: string, turn: number, rating: "up" | "down", reason?: string) {
  const res = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conv_id: convId, turn, rating, reason: reason || null }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

/** Link to the cited page of the company's own PDF (D43: the IR copy, not IDX). */
export function pdfLink(url: string | undefined, page: number): string | undefined {
  return url ? `${url}#page=${page}` : undefined;
}
