"""One LLM interface (guardrail 8) with Gemini and OpenAI-compatible adapters, a call cache and a quota guard
(guardrail 7). Models are chosen by role from config (D48); keys come from the environment.

Cache and usage live in a local SQLite file (data/llm.sqlite): durable on the laptop/CI, per-instance on the Space.
"""
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache

import requests
from pydantic import BaseModel, ValidationError

from backend import tracing
from backend.config import ROOT, config, env

DB_PATH = ROOT / "data" / "llm.sqlite"


class QuotaExceeded(RuntimeError):
    """The daily cap for a model is reached; callers degrade (refuse politely) instead of erroring."""


@dataclass
class LLMResult:
    text: str
    parsed: BaseModel | None
    model: str
    input_tokens: int
    output_tokens: int
    cached: bool


@cache
def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("create table if not exists cache (key text primary key, value text, created_at text)")
    conn.execute("create table if not exists usage (day text, model text, requests int, tokens int,"
                 " primary key (day, model))")
    return conn


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _check_quota(model: str) -> None:
    cap = config()["llm"]["daily_request_caps"].get(model)
    row = _db().execute("select requests from usage where day = ? and model = ?", (_today(), model)).fetchone()
    if cap is not None and row and row[0] >= cap:
        raise QuotaExceeded(f"{model}: daily cap of {cap} requests reached")


def _record(model: str, tokens: int) -> None:
    _db().execute(
        """insert into usage values (?, ?, 1, ?) on conflict (day, model)
           do update set requests = requests + 1, tokens = tokens + excluded.tokens""",
        (_today(), model, tokens),
    )
    _db().commit()


class GeminiAdapter:
    def __init__(self, api_key: str):
        from google import genai
        from google.genai import types

        # One attempt per call: generate() already retries, and the SDK's own retries nested inside those let a
        # single question hang for minutes while Gemini was overloaded.
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=config()["llm"]["timeout_seconds"] * 1000, retry_options=types.HttpRetryOptions(attempts=1)))

    def generate(self, model: str, system: str, user: str, schema: type[BaseModel] | None, images: list[bytes]):
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system, temperature=config()["llm"]["temperature"],
            max_output_tokens=config()["llm"]["max_output_tokens"],
            response_mime_type="application/json" if schema else None, response_schema=schema,
        )
        parts = [types.Part.from_bytes(data=img, mime_type="image/webp") for img in images] + [user]
        r = self.client.models.generate_content(model=model, contents=parts, config=cfg)
        u = r.usage_metadata
        return r.text or "", (u.prompt_token_count or 0), (u.candidates_token_count or 0)


class OpenAICompatAdapter:
    """Groq and any other OpenAI-compatible endpoint (the judge, D40/D48)."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url, self.api_key = base_url.rstrip("/"), api_key

    def generate(self, model: str, system: str, user: str, schema: type[BaseModel] | None, images: list[bytes]):
        if images:
            raise ValueError("images are not supported by this adapter")
        body = {"model": model, "temperature": config()["llm"]["temperature"],
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema(), "strict": False}}
        for _ in range(10):
            r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=120,
                              headers={"Authorization": f"Bearer {self.api_key}"})
            wait = float(r.headers.get("retry-after") or 0)
            if r.status_code == 429 and wait <= 60:  # a per-minute limit is waited out; a daily one is not
                time.sleep(wait + 1)
            elif r.status_code == 400 and "json_validate_failed" in r.text:  # output broke the schema: ask again
                time.sleep(1)
            else:
                break
        if r.status_code == 429:
            raise QuotaExceeded(f"{model}: provider rate limit ({r.headers.get('retry-after')}s)")
        if r.status_code >= 400:
            raise requests.HTTPError(f"{r.status_code} from {model}: {r.text[:300]}", response=r)
        d = r.json()
        return d["choices"][0]["message"]["content"] or "", d["usage"]["prompt_tokens"], d["usage"]["completion_tokens"]


@cache
def _adapter(role: str):
    if role == "judge" and env("JUDGE_BASE_URL", required=False):
        return OpenAICompatAdapter(env("JUDGE_BASE_URL"), env("JUDGE_API_KEY"))
    provider = env("LLM_PROVIDER")
    if provider != "gemini":
        raise ValueError(f"unsupported LLM_PROVIDER {provider!r}")
    return GeminiAdapter(env("LLM_API_KEY"))


def generate(role: str, system: str, user: str, schema: type[BaseModel] | None = None,
             images: list[bytes] = (), use_cache: bool = True) -> LLMResult:
    """Call the model configured for `role` (small | answer | judge | judge_backup)."""
    model = config()["llm"]["models"][role]
    adapter = _adapter("judge" if role == "judge" else "gemini")
    # The schema itself, not its name: changing a field must not return answers shaped by the old one.
    key = hashlib.sha256(json.dumps([model, system, user, schema.model_json_schema() if schema else None,
                                     [hashlib.sha256(i).hexdigest() for i in images]]).encode()).hexdigest()
    if use_cache:
        hit = _db().execute("select value from cache where key = ?", (key,)).fetchone()
        if hit:
            v = json.loads(hit[0])
            return LLMResult(v["text"], schema.model_validate_json(v["text"]) if schema else None, model,
                             v["in"], v["out"], cached=True)
    # §6.5: output that fails the schema (e.g. JSON cut off mid-string) is retried with the validation error.
    prompt, parsed = user, None
    for schema_try in range(config()["llm"]["max_retries_schema"] + 1):
        text, tin, tout = _call(adapter, role, model, system, prompt, schema, images)
        if not schema:
            break
        try:
            parsed = schema.model_validate_json(text)
            break
        except ValidationError as e:
            if schema_try == config()["llm"]["max_retries_schema"]:
                raise
            prompt = (f"{user}\n\nYour previous output was not valid JSON for the required schema: "
                      f"{e.errors()[0]['msg'][:200]}. Return complete, valid JSON; if it was cut off, "
                      "use fewer or shorter claims.")
    _db().execute("insert or replace into cache values (?, ?, ?)",
                  (key, json.dumps({"text": text, "in": tin, "out": tout}), datetime.now(UTC).isoformat()))
    _db().commit()
    return LLMResult(text, parsed, model, tin, tout, cached=False)


def _call(adapter, role: str, model: str, system: str, user: str, schema, images) -> tuple[str, int, int]:
    """One traced, counted provider call; transient errors (5xx, overload) are retried with back-off."""
    _check_quota(model)
    with tracing.generation(role, model, system, user) as gen:
        attempts = config()["llm"]["attempts"]
        for attempt in range(attempts):
            try:
                text, tin, tout = adapter.generate(model, system, user, schema, list(images))
                break
            except QuotaExceeded:
                raise
            except Exception as e:  # transient 5xx/overload: back off, then give up loudly
                if attempt == attempts - 1 or "429" in str(e) and "quota" in str(e).lower():
                    raise
                time.sleep(2 ** (attempt + 1))
        gen.update(output=text, usage_details={"input": tin, "output": tout})
    _record(model, tin + tout)
    return text, tin, tout
