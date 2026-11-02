import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend import tracing


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    lf = Langfuse(public_key="pk-test", secret_key="sk-test", host="http://localhost:9", span_exporter=exporter)
    monkeypatch.setattr(tracing, "client", lambda: lf)
    yield lambda: (lf.flush(), {s.name: s for s in exporter.get_finished_spans()})[1]
    lf.shutdown()


def test_without_keys_everything_is_a_no_op():
    with tracing.ask_trace("q", "visitor") as t:
        t.step({"step": "searching"})
        with tracing.generation("answer", "m", "sys", "user") as g:
            g.update(output="x")
        t.finish({"claims": []})
    assert t.trace_id is None
    tracing.score(None, "up", None)


def test_an_ask_is_one_trace_with_step_spans_and_the_llm_call_inside(spans):
    with tracing.ask_trace("Berapa NPL BBCA?", "visitor") as t:
        t.step({"step": "searching"})
        with tracing.generation("answer", "gemini-x", "sys", "user") as g:
            g.update(output="{}", usage_details={"input": 10, "output": 5})
        t.step({"step": "checking"})
        t.finish({"refusal": False, "claims": [{"text": "1,7%", "ticker": "BBCA", "page": 95}], "conv_id": "c1"})
    got = spans()
    assert {"ask", "searching", "checking", "answer"} <= set(got)
    assert {s.context.trace_id for s in got.values()} == {got["ask"].context.trace_id}
    assert format(got["ask"].context.trace_id, "032x") == t.trace_id
    assert got["answer"].parent.span_id == got["ask"].context.span_id


def test_llm_calls_outside_an_ask_are_not_traced(spans):
    with tracing.generation("judge", "m", "sys", "user") as g:
        g.update(output="x")
    assert spans() == {}
