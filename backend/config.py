"""config.yaml + .env loading. Environment variables win over .env (so CI and the Space can inject secrets)."""
import os
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@cache
def config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@cache
def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs if not k.lstrip().startswith("#")}


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name) or _dotenv().get(name) or None
    if required and not value:
        raise RuntimeError(f"{name} is not set (add it to .env)")
    return value
