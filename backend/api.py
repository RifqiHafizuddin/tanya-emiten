"""FastAPI app (MVP 1d, §6.4): POST /ask streams `step` events then one `answer` event; POST /feedback; GET /health;
GET /companies.

Rate limits and the answer cache live in Postgres (D12). A visitor is a salted hash of the IP, never the IP itself
(guardrail 9). Cached answers cost no LLM call, so they don't count against the limits.
"""
import asyncio
import hashlib
import json
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend import answer, llm, retrieval
from backend.config import config, env
from backend.db import connect

GLOBAL = "*"  # rate_limits row shared by every visitor: the answer model's daily budget


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load e5 in the background so a cold Space answers /health at once and the first question doesn't pay for it.
    from backend.ingest.embed import model

    threading.Thread(target=model, daemon=True).start()
    yield


app = FastAPI(title="Tanya Emiten", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    conv_id: UUID | None = None


class FeedbackIn(BaseModel):
    conv_id: UUID
    turn: int = Field(ge=1)
    rating: Literal["up", "down"]
    reason: str | None = Field(None, max_length=500)


LIMIT_MESSAGE = {
    "visitor": {"en": "You've reached today's question limit. Please come back tomorrow.",
                "id": "Batas pertanyaan hari ini sudah tercapai. Silakan kembali besok."},
    "global": {"en": "The demo has reached today's question limit. Please come back tomorrow.",
               "id": "Demo ini sudah mencapai batas pertanyaan hari ini. Silakan kembali besok."},
}


def visitor_hash(request: Request) -> str:
    # The Space sits behind a proxy; the first X-Forwarded-For entry is the client. It can be spoofed, which only
    # moves a visitor to another per-visitor bucket: the global limit still caps LLM use.
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    return hashlib.sha256((env("IP_HASH_SALT") + ip).encode()).hexdigest()


def cache_key(question: str) -> str:
    _, prompt_version = answer.prompt_text("system")
    model = config()["llm"]["models"]["answer"]
    return hashlib.sha256(f"{answer.normalize(question).lower()}|{prompt_version}|{model}".encode()).hexdigest()


class _LimitHit(Exception):
    """Raised inside the transaction so neither counter keeps the increment."""


def take_quota(conn, visitor: str) -> str | None:
    """Count one question for the visitor and globally; returns which limit is hit (counting nothing) or None."""
    limits, today = config()["limits"], datetime.now(UTC).date()
    caps = {visitor: limits["questions_per_visitor_per_day"], GLOBAL: limits["global_questions_per_day"]}
    try:
        with conn.transaction():
            for who, cap in caps.items():
                count = conn.execute(
                    """insert into rate_limits (visitor_hash, day, count) values (%s, %s, 1)
                       on conflict (visitor_hash, day) do update set count = rate_limits.count + 1 returning count""",
                    (who, today)).fetchone()[0]
                if count > cap:
                    raise _LimitHit("global" if who == GLOBAL else "visitor")
    except _LimitHit as e:
        return str(e)
    return None


def save_turn(conv_id: UUID | None, visitor: str, question: str, out: dict) -> tuple[UUID, int]:
    with connect() as conn, conn.transaction():
        row = conn.execute("select conv_id from conversations where conv_id = %s", (conv_id,)).fetchone() \
            if conv_id else None
        if row is None:
            conv_id = conn.execute("insert into conversations (visitor_hash) values (%s) returning conv_id",
                                   (visitor,)).fetchone()[0]
        turn = conn.execute("select coalesce(max(turn), 0) + 1 from messages where conv_id = %s",
                            (conv_id,)).fetchone()[0]
        for role, content in (("user", question), ("assistant", json.dumps(out, ensure_ascii=False))):
            conn.execute("""insert into messages (conv_id, turn, role, content, lang, prompt_version)
                            values (%s, %s, %s, %s, %s, %s)""",
                         (conv_id, turn, role, content, out.get("lang"), out.get("prompt_version")))
    return conv_id, turn


def run_ask(body: AskIn, visitor: str, on_step: Callable[[dict], None]) -> dict:
    """The whole request, blocking (runs in a worker thread): cache -> limits -> answer -> store."""
    key = cache_key(body.question)
    with connect() as conn:
        row = conn.execute("select response from answer_cache where key = %s", (key,)).fetchone()
    if row:
        on_step({"step": "cached"})
        out = {**row[0], "cached": True}
    else:
        lang = retrieval.understand(body.question).lang
        with connect() as conn:
            hit = take_quota(conn, visitor)
        if hit:
            return {"limited": hit, "message": LIMIT_MESSAGE[hit][lang], "lang": lang}
        try:
            out = answer.respond(body.question, on_step)
        except llm.QuotaExceeded:
            return {"limited": "global", "message": LIMIT_MESSAGE["global"][lang], "lang": lang}
        with connect() as conn:
            conn.execute("insert into answer_cache (key, response) values (%s, %s) on conflict (key) do nothing",
                         (key, json.dumps(out, ensure_ascii=False)))
            conn.commit()
        out = {**out, "cached": False}
    conv_id, turn = save_turn(body.conv_id, visitor, body.question, out)
    return {**out, "conv_id": str(conv_id), "turn": turn}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/ask")
async def ask(body: AskIn, request: Request):
    visitor = visitor_hash(request)
    loop, events = asyncio.get_running_loop(), asyncio.Queue()

    def work():
        try:
            out = run_ask(body, visitor, lambda s: loop.call_soon_threadsafe(events.put_nowait, ("step", s)))
            loop.call_soon_threadsafe(events.put_nowait, ("limit" if "limited" in out else "answer", out))
        except Exception as e:  # the client gets a generic error event; the detail stays in the server log
            print(f"/ask failed: {type(e).__name__}: {e}")
            loop.call_soon_threadsafe(events.put_nowait, ("error", {"message": "Something went wrong."}))

    async def stream():
        task = loop.run_in_executor(None, work)
        while True:
            event, data = await events.get()
            yield sse(event, data)
            if event != "step":
                break
        await task

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/feedback")
def feedback(body: FeedbackIn):
    with connect() as conn:
        if not conn.execute("select 1 from messages where conv_id = %s and turn = %s",
                            (body.conv_id, body.turn)).fetchone():
            raise HTTPException(404, "unknown conversation turn")
        conn.execute("insert into feedback (conv_id, turn, rating, reason) values (%s, %s, %s, %s)",
                     (body.conv_id, body.turn, body.rating, body.reason))
        conn.commit()
    return {"ok": True}


@app.get("/health")
def health():
    from backend.ingest.embed import model

    return {"ok": True, "model_loaded": model.cache_info().currsize > 0}


@app.get("/companies")
def companies():
    with connect() as conn:
        rows = conn.execute(
            """select c.ticker, c.name, c.sector_idxic,
                      coalesce(array_agg(d.fiscal_year order by d.fiscal_year)
                               filter (where d.fiscal_year is not null), '{}')
               from companies c left join documents d on d.ticker = c.ticker and d.doc_type = 'annual_report'
               group by c.ticker order by c.ticker""").fetchall()
    return JSONResponse([{"ticker": t, "name": n, "sector": s, "years": y} for t, n, s, y in rows])
