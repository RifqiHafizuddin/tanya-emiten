import pytest

from backend import llm


class Overloaded:
    calls = 0

    def generate(self, *args):
        self.calls += 1
        raise RuntimeError("503 UNAVAILABLE")


def test_an_overloaded_model_is_tried_config_attempts_times_then_the_error_is_raised(monkeypatch):
    adapter = Overloaded()
    monkeypatch.setattr(llm, "_adapter", lambda role: adapter)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="503"):
        llm.generate("answer", "system", "user", use_cache=False)
    assert adapter.calls == llm.config()["llm"]["attempts"] == 2


class CutOff:
    def __init__(self):
        self.prompts = []

    def generate(self, model, system, user, schema, images):
        self.prompts.append(user)
        return ('{"ok": tr' if len(self.prompts) == 1 else '{"ok": true}'), 1, 1


def test_output_that_fails_the_schema_is_retried_with_the_error(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool

    adapter = CutOff()
    monkeypatch.setattr(llm, "_adapter", lambda role: adapter)
    monkeypatch.setattr(llm, "_record", lambda model, tokens: None)
    monkeypatch.setattr(llm, "_check_quota", lambda model: None)
    res = llm.generate("answer", "system", "user", schema=Out, use_cache=False)
    assert res.parsed.ok and len(adapter.prompts) == 2
    assert adapter.prompts[1].startswith("user\n\nYour previous output was not valid JSON")
