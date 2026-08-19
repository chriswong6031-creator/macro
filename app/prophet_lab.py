"""Authenticated, read-only API for the Prophet Operator Lab (LAB-0 / V4-B5A).

``GET /api/prophet/lab/v1`` is the projection plane the Chairman's
operator-only LIVE|LAB mode reads: it joins canonical Radar live output
against canonical Prophet plan data and existing board-read enrichment into
six frozen "Lab boards", all in one response (``research/prophet_v4/
LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md`` §3-§5, ``DEC:PROPHET-LAB-B5A-RECUT``).

This router is a transport boundary only.  Every board is computed by
``engine/prophet_lab`` (a pure projection package — see its module docstrings)
from data read off injectable filesystem roots; this file's only job is
auth, the kill switch, path resolution for those roots, and response framing.
It runs NO detector formula, reads NO forward outcome, and writes NO store —
LAB-0 §1's "read / filter / join / decorate only" law, and the reason this
module has no ``open(..., "w")`` anywhere in it.

Auth follows the exact BioCatalyst/site-full pattern (``app/biocatalyst.py``
``require_site_full_user``): ``require_user`` (app/main.py) authenticates
first, then ``enforce_site_full(..., always=True)`` (app/paywall.py) gates on
the paid entitlement even while the global paywall switch is in observe
mode — Lab candidates must never reach an unentitled caller, let alone
anonymous HTML (LAB-0 §5).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from engine.prophet_lab import LabRoots, build_lab_response
from engine.prophet_lab.contracts import KILL_SWITCH_ENV

router = APIRouter()
log = logging.getLogger("macro.prophet_lab")

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate first and enforce the paid payload even while staging.

    Exact shape of ``app/biocatalyst.py::require_site_full_user`` (lines
    270-282 at authoring) — one canonical site-full dependency pattern, not a
    second one invented for this router.
    """
    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415

    try:
        return enforce_site_full(_require_user(authorization), always=True)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=_merged_private_headers(exc.headers),
        ) from exc


def _merged_private_headers(existing: dict[str, str] | None) -> dict[str, str]:
    mandatory = {name.casefold() for name in _PRIVATE_HEADERS}
    merged: dict[str, str] = {}
    vary_tokens: list[str] = []
    for name, value in (existing or {}).items():
        if name.casefold() == "vary":
            vary_tokens.extend(part.strip() for part in value.split(",") if part.strip())
        elif name.casefold() not in mandatory:
            merged[name] = value
    merged.update(_PRIVATE_HEADERS)
    if vary_tokens:
        seen = {token.casefold() for token in vary_tokens}
        if "authorization" not in seen:
            vary_tokens.append("Authorization")
        merged["Vary"] = ", ".join(vary_tokens)
    return merged


def _response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code, headers=_PRIVATE_HEADERS)


def _kill_switch_active() -> bool:
    """``PROPHET_LAB_DISABLED`` — evaluated PER REQUEST, independent of Radar's
    own ``ENTRY_RADAR_LIVE_ENABLE``/``ENTRY_RADAR_LIVE_DISABLED`` (LAB-0 §5/§7).
    """
    return os.environ.get(KILL_SWITCH_ENV, "").strip() not in ("", "0", "false", "False")


def _env_path(name: str, default: Path | None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(raw)
    return default


def _resolve_roots() -> LabRoots:
    """Production path ladder for every injectable root.

    Every root is independently overridable via env var (test/staging), and
    falls back to a repo-relative default that matches the SAME directory the
    artifact's own producer already uses — never a second, invented location:

    * ``radar_spool_dir``   -> ``$PROPHET_LAB_RADAR_SPOOL_DIR``, else
      ``$ENTRY_RADAR_SPOOL_DIR`` (the exact env var Radar's own
      ``EventSpool``/``NominationSpool`` local fallback reads —
      ``engine/entry_radar/spool.py::local_spool_dir``), else unset (no
      repo-relative default: the production spool is never inside the repo
      checkout).
    * ``radar_state_dir``   -> ``$PROPHET_LAB_RADAR_STATE_DIR``, else unset
      (the live runtime state dir is an operator-provisioned path, e.g.
      ``/var/lib/macro-live/state/entry_radar`` per
      ``engine/entry_radar/live_ledger.py``'s own module docstring; this
      router never guesses at it).
    * ``prophet_index_path`` -> ``$PROPHET_LAB_PROPHET_INDEX_PATH``, else
      ``<repo>/site/prophet/index.json`` (``scripts/build_prophet.py``'s own
      ``INDEX_PATH``).
    * ``enrichment_library_root`` -> ``$PROPHET_LAB_ENRICHMENT_ROOT``, else
      ``<repo>/site/stockdata`` (``scripts/build_prophet.py``'s own
      ``STOCKDATA_DIR`` — the exact tree ``engine.prophet_board_read.LibraryIndex``
      already reads for name/sector/spark).  Absent on a host that does not
      mount ``site/`` next to the API process; every enrichment field then
      resolves ``None`` with a health-block note rather than raising.
    * ``observation_baseline_path`` -> ``$PROPHET_LAB_OBSERVATION_BASELINE_PATH``,
      else unset.  No repo-relative default exists on purpose: an absent
      baseline is the fail-honest starting state (LAB-0 §4) — every row is
      ``retrospective_seed`` until an operator provisions this marker.
    """
    return LabRoots(
        radar_spool_dir=_env_path(
            "PROPHET_LAB_RADAR_SPOOL_DIR",
            _env_path("ENTRY_RADAR_SPOOL_DIR", None),
        ),
        radar_state_dir=_env_path("PROPHET_LAB_RADAR_STATE_DIR", None),
        prophet_index_path=_env_path(
            "PROPHET_LAB_PROPHET_INDEX_PATH", _REPO_ROOT / "site" / "prophet" / "index.json",
        ),
        enrichment_library_root=_env_path(
            "PROPHET_LAB_ENRICHMENT_ROOT", _REPO_ROOT / "site" / "stockdata",
        ),
        observation_baseline_path=_env_path("PROPHET_LAB_OBSERVATION_BASELINE_PATH", None),
    )


@router.get("/api/prophet/lab/v1")
def lab_v1(_user: dict = Depends(require_site_full_user)) -> JSONResponse:
    if _kill_switch_active():
        return _response(
            {
                "error": "prophet_lab_disabled",
                "detail": f"the Prophet Operator Lab is stood down ({KILL_SWITCH_ENV}=1)",
            },
            status_code=503,
        )
    try:
        payload = build_lab_response(_resolve_roots())
    except Exception as exc:  # noqa: BLE001 — a projection failure must not 500 blind
        log.warning("prophet_lab: projection failed (%s: %s)", type(exc).__name__, exc)
        return _response(
            {"error": "prophet_lab_unavailable", "detail": "Lab projection temporarily unavailable"},
            status_code=503,
        )
    return _response(payload)


__all__ = ["router", "require_site_full_user"]
