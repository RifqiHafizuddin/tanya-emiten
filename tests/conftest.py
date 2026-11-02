import pytest

from backend import tracing


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    """The laptop's .env has Langfuse keys: tests must never send traces."""
    monkeypatch.setattr(tracing, "client", lambda: None)
