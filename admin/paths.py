"""Repo paths + local .env loading, shared across the admin modules.

The admin package lives at <repo>/admin, so the repo root is this file's grandparent.
We replicate lib/config.py's .env convention (load <repo>/.env into os.environ,
without overriding real env vars) so a local GH_TOKEN / GA4 creds can live in .env.
"""
from __future__ import annotations

import os
from pathlib import Path

# The package always lives at <repo>/admin/paths.py, so the code repo is the
# grandparent regardless of any data-root override below.
_PKG_REPO = Path(__file__).resolve().parent.parent


def _load_dotenv(base: Path) -> None:
    """Mirror lib/config.py: load <base>/.env into os.environ; real env vars win.

    Loaded from the CODE repo (not a data-root override) and BEFORE ROOT is
    resolved, so MACRO_ADMIN_ROOT / GH_TOKEN / GA4 creds may all live in a local
    gitignored .env. Never blocks startup on a malformed file.
    """
    p = base / ".env"
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


_load_dotenv(_PKG_REPO)

# MACRO_ADMIN_ROOT overrides the data root for a seeded dev/demo run
# (`MACRO_ADMIN_ROOT=<tmp> python -m admin`, or the same var in a local .env) —
# the same escape hatch the panel functions honour via their `root=` argument,
# so a demo never has to touch real data/. Falls back to the code repo.
_env_root = os.environ.get("MACRO_ADMIN_ROOT", "").strip()
ROOT = Path(_env_root).resolve() if _env_root else _PKG_REPO
CONFIG = ROOT / "config.yml"
DATA = ROOT / "data"
SITE = ROOT / "site"
STATIC = Path(__file__).resolve().parent / "static"
