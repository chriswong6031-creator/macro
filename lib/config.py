"""Load config.yml once; everything reads tunables from here."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load() -> dict:
    with open(ROOT / "config.yml") as f:
        return yaml.safe_load(f)


def data_dir() -> Path:
    return ROOT / load()["storage"]["data_dir"]


def secret(name: str) -> str | None:
    """Secrets come from env (GitHub Actions secrets locally via shell env)."""
    v = os.environ.get(name, "").strip()
    return v or None
