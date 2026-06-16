"""Repo paths + local .env loading, shared across the admin modules.

The admin package lives at <repo>/admin, so the repo root is this file's grandparent.
We replicate lib/config.py's .env convention (load <repo>/.env into os.environ,
without overriding real env vars) so a local GH_TOKEN / GA4 creds can live in .env.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yml"
DATA = ROOT / "data"
SITE = ROOT / "site"
STATIC = Path(__file__).resolve().parent / "static"


def _load_dotenv() -> None:
    """Mirror lib/config.py: real env vars always win over the .env file."""
    p = ROOT / ".env"
    if not p.exists():
        return
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:  # noqa: BLE001 — never block startup on a malformed .env
        pass


_load_dotenv()
