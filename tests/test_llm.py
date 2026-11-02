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
