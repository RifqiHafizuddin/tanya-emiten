import json

from fastapi.testclient import TestClient

from backend import api


def events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_ask_streams_steps_then_one_answer(monkeypatch):
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")

    def fake_run(body, visitor, on_step):
        on_step({"step": "understanding"})
        on_step({"step": "searching", "tickers": ["BBRI"], "years": [2025]})
        return {"question": body.question, "claims": [], "refusal": True, "conv_id": "c", "turn": 1}

    monkeypatch.setattr(api, "run_ask", fake_run)
    r = TestClient(api.app).post("/ask", json={"question": "Apa strategi BBRI?"})
    assert r.headers["content-type"].startswith("text/event-stream")
    got = events(r.text)
    assert [e for e, _ in got] == ["step", "step", "answer"]
    assert got[1][1]["tickers"] == ["BBRI"]


def test_a_limit_ends_the_stream_with_a_limit_event(monkeypatch):
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")
    monkeypatch.setattr(api, "run_ask", lambda body, visitor, on_step: {"limited": "visitor", "message": "m"})
    assert [e for e, _ in events(TestClient(api.app).post("/ask", json={"question": "Why?"}).text)] == ["limit"]


def test_visitor_is_a_salted_hash_not_the_ip(monkeypatch):
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")
    seen = []
    monkeypatch.setattr(api, "run_ask", lambda body, visitor, on_step: seen.append(visitor) or {"x": 1})
    TestClient(api.app).post("/ask", json={"question": "Why?"}, headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert len(seen[0]) == 64 and "203.0.113.7" not in seen[0]
    monkeypatch.setenv("IP_HASH_SALT", "other-salt")
    TestClient(api.app).post("/ask", json={"question": "Why?"}, headers={"x-forwarded-for": "203.0.113.7"})
    assert seen[1] != seen[0]


def test_questions_are_validated():
    assert TestClient(api.app).post("/ask", json={"question": "x" * 501}).status_code == 422
