"""Load config.yml once; everything reads tunables from here."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Local runs read secrets from a gitignored .env; CI uses real env vars,
    which always win over the file."""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@lru_cache(maxsize=1)
def load() -> dict:
    with open(ROOT / "config.yml") as f:
        return yaml.safe_load(f)


def data_dir() -> Path:
    return ROOT / load()["storage"]["data_dir"]


def site_dir() -> Path:
    return ROOT / load()["storage"]["site_dir"]


def secret(name: str) -> str | None:
    """Secrets come from env (GitHub Actions secrets locally via shell env)."""
    v = os.environ.get(name, "").strip()
    return v or None
