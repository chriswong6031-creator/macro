"""Authenticated, read-only API for the Prophet Operator Lab (LAB-0 / V4-B5A).

``GET /api/prophet/lab/v1`` is the projection plane the Chairman's
operator-only LIVE|LAB mode reads: it joins canonical Radar live output
against canonical Prophet plan data and existing board-read enrichment into
six frozen "Lab boards", all in one response (``research/prophet_v4/
LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md`` §3-§5, ``DEC:PROPHET-LAB-B5A-RECUT``).

``GET /api/prophet/lab/v1/episodes/{episode_id}/intelligence`` is the bounded
D5 detail read: it pins one atomic B1 generation and one exact episode, builds
the canonical current ``IssuerMaster`` reader, then delegates the Earnings
projection to the pure ``engine.prophet_lab.intelligence_vector`` adapter.

This router is a transport boundary only.  Every board is computed by
``engine/prophet_lab`` (a pure projection package — see its module docstrings)
from data read off injectable filesystem roots; this file's only job is
auth, the kill switch, bounded reader composition, path resolution, and
response framing.
It runs NO detector formula, reads NO forward outcome, and writes NO store —
LAB-0 §1's "read / filter / join / decorate only" law, and the reason this
module has no ``open(..., "w")`` anywhere in it.

Auth follows the exact BioCatalyst/site-full pattern (``app/biocatalyst.py``
``require_site_full_user``): ``require_user`` (app/main.py) authenticates
first, then ``enforce_site_full(..., always=True)`` (app/paywall.py) gates on
the paid entitlement even while the global paywall switch is in observe
mode — Lab candidates must never reach an unentitled caller, let alone
anonymous HTML (LAB-0 §5).

``GET /api/hub/prophet`` is a SEPARATE, INTERNAL-ONLY route (DEC:B1-PROPHET-
PUBLIC-SPLIT): it serves the raw bytes of the same canonical local index file
``_resolve_roots()`` above resolves, for the Terminal's server-side ``/api/flow``
route to read the full Prophet plan book without falling through to the public
R2 mirror that exposure closed. It carries NO paywall/user auth — its guard is
same-box-only (loopback TCP peer AND no ``X-MM-Peer`` header; see
``_hub_prophet_authorized``), which is a materially different trust boundary
than every other route in this file and must never be relaxed to a header or
token check a caller could supply from off-box.
"""
from __future__ import annotations

from io import BytesIO
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from engine.prophet_lab import LabRoots, build_lab_response
from engine.prophet_lab.contracts import KILL_SWITCH_ENV
from engine.prophet_lab.intelligence_vector import (
    IntelligenceVectorContractError,
    build_earnings_intelligence_vector,
    load_candidate_episode_store_snapshot,
)
from lib.dataos.identity import IssuerMaster

router = APIRouter()
log = logging.getLogger("macro.prophet_lab")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANDIDATE_EPISODE_STORE_ROOT = _REPO_ROOT / "data" / "us_prophet_rank" / "episodes"
_SECURITY_MASTER_PATH = _REPO_ROOT / "data" / "reference" / "security_master.parquet"

#: INTERNAL-ONLY loopback addresses. macro-api always sits behind Caddy on
#: 127.0.0.1 (app/main.py::_brain_identity docstring), so a bare TCP-peer check
#: alone cannot distinguish an edge-proxied request from a direct same-box call —
#: BOTH show up as 127.0.0.1. See ``_hub_prophet_guard`` below.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})

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


def _load_issuer_master(path: Path) -> IssuerMaster:
    """Build the canonical identity reader from one immutable parquet byte read."""
    import pandas as pd  # noqa: PLC0415 — optional API data dependency, request-scoped

    raw = Path(path).read_bytes()
    records = pd.read_parquet(BytesIO(raw)).to_dict("records")
    return IssuerMaster.from_records(records)


def _source_integrity_failed(payload: Mapping[str, Any]) -> bool:
    receipt = payload.get("assembly_receipt")
    if not isinstance(receipt, Mapping):
        return False
    errors = receipt.get("errors")
    return isinstance(errors, list) and any(
        isinstance(error, Mapping)
        and error.get("type") == "WorkspaceChainIntegrityError"
        for error in errors
    )


# Review N4: case-insensitive OFF set; anything NOT recognized as "off" is
# treated as the switch being ACTIVE (fail TOWARD disabled — an operator
# typo or an unexpected value takes the Lab down rather than silently
# leaving it up).
_KILL_SWITCH_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})


def _kill_switch_active() -> bool:
    """``PROPHET_LAB_DISABLED`` — evaluated PER REQUEST, independent of Radar's
    own ``ENTRY_RADAR_LIVE_ENABLE``/``ENTRY_RADAR_LIVE_DISABLED`` (LAB-0 §5/§7).
    """
    raw = os.environ.get(KILL_SWITCH_ENV, "").strip().casefold()
    return raw not in _KILL_SWITCH_OFF_VALUES


def _env_path(name: str, default: Path | None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if raw:
        return Path(raw)
    return default


def _env_path_labeled(
    primary_name: str, fallback_name: str | None, default: Path | None, default_label: str,
) -> tuple[Path | None, str]:
    """Same ladder as :func:`_env_path`, but also names WHICH source won.

    Review S2 (cheap half): the health block should say which env var/path
    resolved the Radar spool root, or "unconfigured" — not just a boolean.
    """
    raw = os.environ.get(primary_name, "").strip()
    if raw:
        return Path(raw), primary_name
    if fallback_name:
        raw = os.environ.get(fallback_name, "").strip()
        if raw:
            return Path(raw), fallback_name
    return default, default_label


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
    radar_spool_dir, radar_spool_source_label = _env_path_labeled(
        "PROPHET_LAB_RADAR_SPOOL_DIR", "ENTRY_RADAR_SPOOL_DIR", None, "unconfigured",
    )
    return LabRoots(
        radar_spool_dir=radar_spool_dir,
        radar_spool_source_label=radar_spool_source_label,
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


@router.get("/api/prophet/lab/v1/episodes/{episode_id}/intelligence")
def episode_intelligence_v1(
    episode_id: str,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """Project one exact B1 episode through the read-only D5 Earnings adapter."""
    if _kill_switch_active():
        return _response(
            {
                "error": "prophet_lab_disabled",
                "detail": f"the Prophet Operator Lab is stood down ({KILL_SWITCH_ENV}=1)",
            },
            status_code=503,
        )

    try:
        episode_store_root = _env_path(
            "PROPHET_LAB_EPISODE_STORE_ROOT", _CANDIDATE_EPISODE_STORE_ROOT,
        )
        security_master_path = _env_path(
            "PROPHET_LAB_SECURITY_MASTER_PATH", _SECURITY_MASTER_PATH,
        )
        if episode_store_root is None or security_master_path is None:
            raise IntelligenceVectorContractError("D5 read roots must be configured")

        snapshot = load_candidate_episode_store_snapshot(episode_store_root)
        matching_episodes = [
            episode
            for episode in snapshot.generation.episodes
            if episode.get("episode_id") == episode_id
        ]
        if not matching_episodes:
            return _response({"error": "prophet_episode_not_found"}, status_code=404)
        if len(matching_episodes) != 1:
            raise IntelligenceVectorContractError("B1 generation contains duplicate episode identity")

        opened_events = [
            event
            for event in snapshot.generation.events
            if event.get("episode_id") == episode_id and event.get("event_type") == "OPENED"
        ]
        if len(opened_events) != 1:
            raise IntelligenceVectorContractError("B1 episode must have exactly one OPENED event")
        episode_known_at = opened_events[0].get("known_at")
        if not isinstance(episode_known_at, str):
            raise IntelligenceVectorContractError("B1 OPENED event known_at is invalid")

        payload = build_earnings_intelligence_vector(
            episode=matching_episodes[0],
            episode_generation_id=snapshot.generation_id,
            episode_known_at=episode_known_at,
            issuer_master=_load_issuer_master(security_master_path),
        )
        if _source_integrity_failed(payload):
            raise IntelligenceVectorContractError("D5 source integrity receipt is not admissible")
    except Exception as exc:  # noqa: BLE001 — corrupt read chains must not 500 blind
        log.warning(
            "prophet_lab: episode intelligence failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return _response(
            {
                "error": "prophet_episode_intelligence_unavailable",
                "detail": "Episode intelligence temporarily unavailable",
            },
            status_code=503,
        )
    return _response(payload)


def _hub_prophet_authorized(request: Request) -> bool:
    """INTERNAL-ONLY guard for ``/api/hub/prophet`` (DEC:B1-PROPHET-PUBLIC-SPLIT).

    This route exists so the Terminal's server-side ``/api/flow`` route
    (``terminal/app/api/flow/route.ts:83``, which already targets
    ``${FLOW_API_BASE:-http://127.0.0.1:8000}/api/hub/prophet`` as its canonical
    backend) can read the full Prophet plan book without ever touching public R2
    — the very exposure this closure exists to shut. It is NOT a public or even
    an authenticated-user endpoint: it hands back the raw premium plan book with
    no paywall check, so it must be provably unreachable from outside the box.

    Caddy's ``reverse_proxy /api/*`` block REPLACES any inbound ``X-MM-Peer``
    with the real TCP peer on every edge-proxied request (app/deploy/Caddyfile,
    the ``header_up X-MM-Peer {remote_host}`` line under that block) — so a
    request that arrived through the public edge ALWAYS carries the header. A
    direct same-box call to uvicorn (bypassing Caddy entirely, e.g. the
    co-located Terminal process hitting 127.0.0.1:8000 directly) carries no such
    header. Because macro-api always sits behind Caddy on 127.0.0.1, the TCP
    peer alone cannot tell the two apart — both read 127.0.0.1 (same "no
    source-IP check is enough behind Caddy" reasoning as
    ``app/main.py::_brain_identity``). The header's ABSENCE, combined with a
    loopback peer, is therefore the load-bearing half of this guard.
    """
    peer = request.client.host if request.client else None
    if peer not in _LOOPBACK_HOSTS:
        return False
    return request.headers.get("x-mm-peer") is None


@router.get("/api/hub/prophet")
def hub_prophet(request: Request) -> Response:
    if not _hub_prophet_authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    index_path = _resolve_roots().prophet_index_path
    if index_path is None or not index_path.is_file():
        return JSONResponse({"error": "prophet_index_unavailable"}, status_code=503)
    try:
        raw = index_path.read_bytes()
    except OSError as exc:
        log.warning("hub_prophet: index read failed (%s: %s)", type(exc).__name__, exc)
        return JSONResponse({"error": "prophet_index_unavailable"}, status_code=503)
    return Response(
        content=raw,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["router", "require_site_full_user"]
