"""Langfuse traces (D18, §9 online): one trace per /ask with a span per UI step and each LLM call as a generation,
plus the visitor's thumbs up/down as a score on that trace. Without the LANGFUSE_* keys (tests, CI) every helper is
a no-op. LLM calls outside an /ask (eval runs, the CLI) are not traced, so they don't spend the free-tier events.
"""
from contextlib import contextmanager
from functools import cache

from backend.config import env


@cache
def client():
    if not (env("LANGFUSE_PUBLIC_KEY", required=False) and env("LANGFUSE_SECRET_KEY", required=False)):
        return None
    from langfuse import Langfuse

    return Langfuse(public_key=env("LANGFUSE_PUBLIC_KEY"), secret_key=env("LANGFUSE_SECRET_KEY"),
                    host=env("LANGFUSE_HOST", required=False) or "https://cloud.langfuse.com")


class _NoOp:
    trace_id = None

    def update(self, **kwargs) -> None:
        pass


class AskTrace:
    """The root span of one /ask. Each `step` closes the previous step span, so every UI step shows its duration."""

    def __init__(self, root=None):
        self.root, self.trace_id, self._step = root, root.trace_id if root else None, None

    def step(self, event: dict) -> None:
        if self.root:
            self._close_step()
            self._step = self.root.start_observation(name=event["step"], metadata=event)

    def _close_step(self) -> None:
        if self._step:
            self._step.end()
            self._step = None

    def finish(self, out: dict) -> None:
        if not self.root:
            return
        from langfuse import propagate_attributes

        self._close_step()
        # Tags drive the dashboards (§9): refusal rate, repair rate, cache hits, limit hits.
        tags = [t for t, on in (("refusal", out.get("refusal")), ("repair", out.get("repair_used")),
                                ("cached", out.get("cached")), ("limited", "limited" in out)) if on]
        with propagate_attributes(session_id=out.get("conv_id"), tags=tags):
            pass
        self.root.update(
            output={"refusal_reason": out.get("refusal_reason") or out.get("message"),
                    "claims": [f"{c['text']} [{c['ticker']} p.{c['page']}]" for c in out.get("claims", [])]},
            metadata={k: out.get(k) for k in ("lang", "prompt_version", "model", "tokens", "latency_ms", "checks",
                                              "retrieved", "turn", "limited") if k in out})


@contextmanager
def ask_trace(question: str, visitor: str):
    lf = client()
    if lf is None:
        yield AskTrace()
        return
    from langfuse import propagate_attributes

    with lf.start_as_current_observation(name="ask", as_type="agent", input={"question": question}) as root, \
            propagate_attributes(user_id=visitor, trace_name="ask"):
        trace = AskTrace(root)
        try:
            yield trace
        except Exception as e:
            root.update(level="ERROR", status_message=f"{type(e).__name__}: {e}")
            raise
        finally:
            trace._close_step()


@contextmanager
def generation(name: str, model: str, system: str, user: str):
    lf = client()
    # Ask OpenTelemetry directly: lf.get_current_trace_id() logs a "Context error" on every untraced call.
    from opentelemetry import trace as otel

    if lf is None or not otel.get_current_span().get_span_context().is_valid:
        yield _NoOp()
        return
    with lf.start_as_current_observation(name=name, as_type="generation", model=model,
                                         input=[{"role": "system", "content": system},
                                                {"role": "user", "content": user}]) as g:
        yield g


def score(trace_id: str | None, rating: str, reason: str | None) -> None:
    lf = client()
    if lf and trace_id:
        lf.create_score(trace_id=trace_id, name="user_feedback", value=1 if rating == "up" else 0,
                        data_type="BOOLEAN", comment=reason)


def flush() -> None:
    if client():
        client().flush()
