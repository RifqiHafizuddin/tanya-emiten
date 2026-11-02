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
    TestClient(api.app).post("/ask", json={"question": "Why?"}, headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert seen[1] != seen[0]


def test_a_spoofed_forwarded_for_entry_does_not_change_the_visitor(monkeypatch):
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")
    seen = []
    monkeypatch.setattr(api, "run_ask", lambda body, visitor, on_step: seen.append(visitor) or {"x": 1})
    for spoof in ("198.51.100.1, ", "198.51.100.2, ", ""):  # the proxy appends the real client last
        TestClient(api.app).post("/ask", json={"question": "Why?"}, headers={"x-forwarded-for": spoof + "203.0.113.7"})
    assert len(set(seen)) == 1


def test_questions_are_validated():
    assert TestClient(api.app).post("/ask", json={"question": "x" * 501}).status_code == 422


def test_cache_key_is_the_text_retrieval_sees():
    assert api.cache_key("Berapa rasio NPL BBCA?") == api.cache_key("  Berapa rasio  NPL BBCA? ")
    assert api.cache_key("Berapa rasio NPL BBCA?") != api.cache_key("Berapa rasio NPL BB- CA?")
    assert api.cache_key("Berapa rasio NPL BBCA?") != api.cache_key("berapa RASIO npl BBCA?")


def test_only_clean_answers_are_cached():
    clean = {"refusal": False, "checks": {"errors_after_repair": []}}
    assert api.cacheable(clean)
    assert not api.cacheable({**clean, "refusal": True})
    assert not api.cacheable({**clean, "checks": {"errors_after_repair": ["Claim 1 ..."]}})
    assert not api.cacheable({"refusal": True, "checks": {"coverage": {"unknown": ["DOID"]}}})


def test_large_bodies_are_rejected_before_parsing():
    r = TestClient(api.app).post("/ask", content=b'{"question": "' + b"x" * 20_000 + b'"}',
                                 headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_a_slow_answer_ends_with_an_error_event(monkeypatch):
    import time

    monkeypatch.setenv("IP_HASH_SALT", "test-salt")
    monkeypatch.setitem(api.config()["limits"], "request_timeout_seconds", 0.2)
    monkeypatch.setattr(api, "run_ask", lambda body, visitor, on_step: time.sleep(1) or {"x": 1})
    got = events(TestClient(api.app).post("/ask", json={"question": "Why?"}).text)
    assert [e for e, _ in got] == ["error"] and "too long" in got[0][1]["message"]


def test_api_docs_are_off_and_cors_is_limited_to_the_site():
    client = TestClient(api.app)
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404
    pre = {"access-control-request-method": "POST"}
    ok = client.options("/ask", headers={**pre, "origin": "https://tanya-emiten.vercel.app"})
    assert ok.headers.get("access-control-allow-origin") == "https://tanya-emiten.vercel.app"
    assert "access-control-allow-origin" not in client.options("/ask", headers={**pre, "origin": "https://evil.example"}).headers
