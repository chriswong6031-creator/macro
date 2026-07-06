"""app/hub.py — FastAPI router for the Options Hub nightly analytics.

Provides:
  GET /api/hub/vol/{root}  — IV surface + rank payload (options_hub/vol/{root}.json)
  GET /api/hub/gex/{root}  — Dealer-gamma exposure payload (options_hub/gex/{root}.json)
  GET /api/hub/oi          — OI movers screener (options_hub/oi_movers.json)
  GET /api/hub/hot         — Hottest contracts by premium/volume (options_hub/hot_contracts.json)

All routes are unauthenticated read-throughs of the R2 options_hub/ objects with a
30-second in-memory TTL cache. On fetch failure the last-cached copy is returned with
{"stale": true} merged. 503 only if the object was never successfully fetched.

Mirrors the code style and patterns from app/main.py's /api/flow/* routes exactly:
  - same TTL / UA / stale pattern
  - same r2_base resolver (R2_PUBLIC_BASE env or config.yml)
  - self-contained module; no imports from live_flow_poller
  - unauthenticated; display-tier only

DISPLAY-TIER ONLY: no trading signals, no directional recommendations.
Words 'signal' and 'validated' are banned in user-facing strings.
OI is always t-1 or older per the OI timing law.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

# --------------------------------------------------------------------------- #
# TTL cache (mirrors app/main.py _FLOW_CACHE pattern)
# --------------------------------------------------------------------------- #
_HUB_CACHE: dict[str, tuple[dict, float]] = {}
_HUB_CACHE_TTL = 30.0       # seconds
_HUB_UA = "mastermind-feed/1.0"

# --------------------------------------------------------------------------- #
# R2 base URL resolver (mirrors app/main.py _flow_r2_base)
# --------------------------------------------------------------------------- #

def _hub_r2_base() -> str:
    base = os.environ.get("R2_PUBLIC_BASE", "")
    if base:
        return base.rstrip("/")
    try:
        import yaml  # noqa: PLC0415
        _cfg_path = Path(os.environ.get("MACRO_REPO", "/opt/macro")) / "config.yml"
        if _cfg_path.exists():
            with open(_cfg_path) as f:
                c = yaml.safe_load(f)
            return (c.get("r2_data_plane", {}).get("public_base") or "").rstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return ""


# --------------------------------------------------------------------------- #
# R2 read-through with TTL/stale fallback (mirrors app/main.py _flow_fetch)
# --------------------------------------------------------------------------- #

def _hub_fetch(key: str) -> dict:
    """Fetch options_hub/<key> from R2 with TTL caching and stale fallback.

    Returns the parsed JSON dict. On failure returns last-cached dict with
    {"stale": true} merged. Raises HTTPException(503) only if never fetched.
    """
    cached = _HUB_CACHE.get(key)
    now = time.monotonic()

    # Fresh cache hit
    if cached is not None and (now - cached[1]) < _HUB_CACHE_TTL:
        return cached[0]

    base = _hub_r2_base()
    if not base:
        if cached:
            return {**cached[0], "stale": True}
        raise HTTPException(503, f"hub/{key}: R2 base URL not configured")

    url = f"{base}/options_hub/{key}"
    req = urllib.request.Request(url, headers={"User-Agent": _HUB_UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data: dict = json.loads(resp.read())
        _HUB_CACHE[key] = (data, now)
        return data
    except Exception:  # noqa: BLE001
        if cached:
            return {**cached[0], "stale": True}
        raise HTTPException(503, f"hub/{key} unavailable and no cached copy") from None


# --------------------------------------------------------------------------- #
# parameter sanitization helpers
# --------------------------------------------------------------------------- #

_ROOT_RE = re.compile(r"^[A-Z0-9\^]{1,16}$")


def _sanitize_root(root: str) -> str:
    """Uppercase, strip whitespace, validate against safe root pattern.

    Raises HTTPException(400) on invalid input to prevent path traversal.
    """
    root = root.strip().upper()
    if not _ROOT_RE.match(root):
        raise HTTPException(400, f"Invalid root symbol: {root!r}")
    return root


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #

@router.get("/api/hub/vol/{root}")
def hub_vol(root: str) -> dict[str, Any]:
    """IV surface, IV rank, term structure, smile, RV20, VRP for one root.

    Display-tier analytics. IV rank is percentile vs trailing 252 sessions
    (null when <60 observations). OI used is always t-1 or older.
    """
    root = _sanitize_root(root)
    return _hub_fetch(f"vol/{root}.json")


@router.get("/api/hub/gex/{root}")
def hub_gex(root: str) -> dict[str, Any]:
    """Dealer-gamma exposure profile for one root.

    Dealer long-call / short-put sign convention (unobservable assumption —
    display context only). OI used is always t-1. GEX ladders replicate
    engine/gex_model dealer-sign convention exactly.
    """
    root = _sanitize_root(root)
    return _hub_fetch(f"gex/{root}.json")


@router.get("/api/hub/oi")
def hub_oi() -> dict[str, Any]:
    """Top ΔOI contract movers screener (cross-root, by |ΔOI|).

    Labeled heuristic — large ΔOI may reflect positioning, rolls,
    or expiry activity. Display context only.
    """
    return _hub_fetch("oi_movers.json")


@router.get("/api/hub/hot")
def hub_hot() -> dict[str, Any]:
    """Contracts with highest gross premium or volume for the session.

    Labeled heuristic — high premium or volume may reflect hedging,
    speculation, or rolls. Display context only.
    """
    return _hub_fetch("hot_contracts.json")


@router.get("/api/hub/ctx")
def hub_ctx() -> dict[str, Any]:
    """Options Hub market context: index_gex, fear_greed, sector_etf_flows.

    Nightly-computed aggregate context. Display context only.
    """
    return _hub_fetch("context.json")


@router.get("/api/hub/oiconf")
def hub_oiconf() -> dict[str, Any]:
    """OI-confirmed contracts: prev session notable ∩ today ΔOI movers.

    OI is always t-1 or older per the OI timing law. Display context only.
    """
    return _hub_fetch("oi_confirmed.json")


@router.get("/api/hub/tctx/{root}")
def hub_tctx(root: str) -> dict[str, Any]:
    """Ticker context: tape-flow z-scores for one root.

    z is null when history_n < 20. Display context only.
    """
    root = _sanitize_root(root)
    return _hub_fetch(f"tickers_ctx/{root}.json")
