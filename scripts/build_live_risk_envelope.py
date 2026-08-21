#!/usr/bin/env python3
"""scripts/build_live_risk_envelope.py — GD-3 live provisional producer for
`mastermind.risk_envelope/v1`.

    python -m scripts.build_live_risk_envelope           # writes site/live/risk_envelope.json
    python -m scripts.build_live_risk_envelope --print    # compose + print, write nothing

Commission: `research/grey_deer/commissions/GD-3_LIVE_PROVISIONAL_ENVELOPE_COMMISSION_2026-08-20.md`.
Architecture freeze: `research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md`.

SAME COMPOSER, FRESHER OBSERVATIONS
------------------------------------
This module never forks the state logic. It calls the SAME pure composer
(`engine.risk_envelope.compose_envelope`) and the SAME source adapters
(`scripts.build_risk_envelope._market_state_read` / `_leadership_crack_read` /
`_risk_radar_read`) the settled lane uses — reshaping the live plane's own artifacts
into the doc shapes those adapters already expect, and handing each adapter an
explicit `stale_override` computed from the live plane's own clock. No new mapping
from a state word to a hazard stage exists anywhere in this file (guarded:
`tests/test_live_risk_envelope.py` AST-scans this module for exactly that shape).

Authority: DISPLAY / ADVISORY ONLY. All four envelope authority booleans are hard-false
by construction (`engine.risk_envelope._authority()`); this module adds no authority of
its own and never writes a durable forward ledger (guarded: an import-set scan plus a
tmp-ROOT run asserting the only write is `site/live/risk_envelope.json`).

CLOCK LAW
---------
A source whose own clock is AHEAD of the live session it is being read into, or whose
carrying artifact's clock sits more than 120s ahead of wall-clock, is refused —
`unusable`, never a substituted "now". An unknown clock stays `None`; this module never
invents one. Refusing a REQUIRED source nulls the stage via the composer's own null law
(`engine/risk_envelope.py::_hazard_summary`) — it is never worked around here.

WHAT "LIVE SESSION L" IS, AND WHY IT IS NOT A LITERAL FIELD READ
------------------------------------------------------------------
The GD-3 commission and command packet name the source as `risk_state.json["session"]`.
That key is `engine.live_overlay.market_session()`'s advisory `{region, open,
local_time}` dict (scripts/build_risk_state.py:315) — it carries no date, so it cannot
serve as the comparable session identifier the precedence law needs (L > S / L == S /
L < S against the settled envelope's `source_session`, a date string). L is therefore
derived from a date ALREADY inside the explicitly-permitted-to-read artifact —
`risk_state.json["built"]`, the fast lane's own recorded UTC build timestamp — via
`lib.nyse_calendar.session_date()`, the same live-session-date bridge the codebase
already uses elsewhere. This is a deliberate, documented resolution of an underspecified
field (see the PR body / worker report), not a silent redesign: it reads only data the
spec explicitly permits, invents no wall-clock instant of its own, and answers the exact
question the precedence law needs answered ("what trading day is the live plane
watching").

DIVISION OF LABOUR
------------------
`engine/risk_envelope.py` is pure. `scripts/build_risk_envelope.py` owns the settled
I/O AND the only source-adapter authority (never forked here). THIS file owns the live
plane's own I/O: `site/live/risk_state.json` (raw `live` block only — the debounced
`display` block is NEVER read, guarded by source scan + a fixture test), `data/
leadership_crack/latest.json` (no live LC artifact exists; carried forward per the
settled convention), and `data/risk_envelope/latest.json` (the settled bundle this
overlay compares against).

Never fatal: any missing/unreadable input degrades to MISSING coverage the same way the
settled builder does.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.risk_envelope import compose_envelope, canonical_json  # noqa: E402
from lib import config  # noqa: E402
from lib import nyse_calendar  # noqa: E402
from scripts.build_risk_envelope import (  # noqa: E402
    _leadership_crack_read,
    _market_state_read,
    _risk_radar_read,
)

log = logging.getLogger(__name__)

MARKET = "US"
_FUTURE_TOLERANCE_S = 120.0

_DEBOUNCE_TICKS_DEFAULT = 3
_STALE_AFTER_MIN_DEFAULT = 5.0


# ── I/O ────────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — a bad source becomes a missing one
        log.warning("live_risk_envelope: source unreadable %s (%s)", path, e)
        return None


def _atomic_write(path: Path, payload: str) -> None:
    """Write atomically via tmp+rename (mirrors scripts/build_risk_envelope.py)."""
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o644)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        log.warning("live_risk_envelope atomic write to %s failed: %s", path, e)
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:  # noqa: BLE001
                pass


def risk_state_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "site" / "live" / "risk_state.json"


def leadership_crack_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "data" / "leadership_crack" / "latest.json"


def settled_envelope_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "data" / "risk_envelope" / "latest.json"


def out_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "site" / "live" / "risk_envelope.json"


def _risk_envelope_cfg() -> dict[str, Any]:
    try:
        return (config.load().get("live") or {}).get("risk_envelope") or {}
    except Exception:  # noqa: BLE001 — config is optional; defaults still apply
        return {}


# ── pure-ish helpers (clock arithmetic only; every instant is an argument) ──────

def _parse_built(built: str | None) -> datetime | None:
    """Parse risk_state.json's own `built` stamp ("%Y-%m-%d %H:%M:%S UTC")."""
    if not built:
        return None
    try:
        return datetime.strptime(built, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _live_session(built_dt: datetime | None) -> str | None:
    """L: the NYSE trading-day date the live plane's own recorded clock belongs to.

    Derived ONLY from `built_dt` (itself read from risk_state.json, never a fresh
    wall-clock call here) via the codebase's own live-session-date bridge. See the
    module docstring for why this replaces a literal `risk_state.json["session"]`
    read."""
    if built_dt is None:
        return None
    return nyse_calendar.session_date(built_dt).isoformat()


def market_freshness(
    risk_state_doc: dict[str, Any] | None, stale_after_min: float, now: datetime,
) -> dict[str, Any]:
    """The ONE freshness verdict for the market-state/radar leg, computed once and
    reused everywhere it matters (source assembly AND the wrapper) so the two can
    never drift apart. `usable` folds live_active, the stale_after_min horizon, and
    a wall-clock skew guard on the carrying artifact's own `built` clock (>120s
    ahead of wall-clock is refused, same as the general clock law)."""
    live_active = bool((risk_state_doc or {}).get("live_active"))
    built_dt = _parse_built((risk_state_doc or {}).get("built"))
    fresh_enough = bool(built_dt) and (now - built_dt).total_seconds() <= stale_after_min * 60.0
    future_artifact = bool(built_dt) and (built_dt - now).total_seconds() > _FUTURE_TOLERANCE_S
    usable = live_active and fresh_enough and not future_artifact
    return {
        "live_active": live_active, "built_dt": built_dt,
        "fresh_enough": fresh_enough, "future_artifact": future_artifact,
        "usable": usable,
    }


def _is_future(as_of: str | None, ceiling: str | None, wall_now: datetime) -> bool:
    """Clock law: refuse a source whose own clock exceeds `ceiling` (a date string,
    normally L), or whose clock is itself parseable and sits >120s ahead of wall-clock.
    An unknown (`None`) clock is never treated as future — it is simply unusable
    elsewhere via the null law, never invented or substituted here."""
    if as_of is None:
        return False
    if ceiling is not None and str(as_of) > str(ceiling):
        return True
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(str(as_of), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return (parsed - wall_now).total_seconds() > _FUTURE_TOLERANCE_S
    return False


# ── source assembly (pure given its arguments — no clock reads, no disk) ────────

def build_live_sources(
    *,
    risk_state_doc: dict[str, Any] | None,
    leadership_doc: dict[str, Any] | None,
    settled_source_session: str | None,
    live_session: str | None,
    market_usable: bool,
    now: datetime,
) -> list:
    """Reshape the live plane's own artifacts into the SETTLED adapters' doc shapes
    and call them with an explicit `stale_override`. Field re-housing only — no
    state-word -> hazard-stage mapping lives here; that mapping is the settled
    adapters' own (`scripts/build_risk_envelope.py::_LEADERSHIP_STAGE` /
    `_RADAR_STAGE`), imported and reused verbatim.

    `market_usable` is the ONE freshness verdict for the market-state leg (see
    `market_freshness()`), computed once by the caller and reused for the wrapper
    too, so source-level usability and the wrapper's `live_active` can never
    disagree with each other."""
    L, S = live_session, settled_source_session

    market_stale_override = not market_usable
    # "radar live read carries the same freshness verdict as its carrying artifact"
    radar_stale_override = market_stale_override

    ms_doc = None
    radar_doc = None
    if risk_state_doc is not None:
        live_blk = risk_state_doc.get("live") or {}  # RAW block only — never "display"
        ms_doc = {
            "asof": L,
            "verdict": live_blk.get("verdict"),
            "score": live_blk.get("score"),
            "raw_score": live_blk.get("raw_score"),
            "label_en": live_blk.get("label_en"),
            "label_zh": live_blk.get("label_zh"),
            "score_source": "live_fast_lane",
            "capped": False,
            "freshness": {"stale": market_stale_override},
        }
        radar_raw = live_blk.get("radar") or {}
        radar_doc = {
            "state": radar_raw.get("state"),
            "top_score": radar_raw.get("top_score"),
            "label_en": radar_raw.get("label_en"),
            "label_zh": radar_raw.get("label_zh"),
            "is_warning": bool(radar_raw.get("is_warning")),
            "is_loud": bool(radar_raw.get("is_loud")),
        }

    measured = (
        _market_state_read(ms_doc, L, stale_override=market_stale_override)
        if ms_doc is not None
        else _market_state_read(None, L)
    )
    radar = (
        _risk_radar_read(radar_doc, L, L, stale_override=radar_stale_override)
        if radar_doc is not None
        else _risk_radar_read(None, L, None)
    )

    # Leadership Crack: no live artifact exists, so the settled read is carried
    # forward. "usable exactly when it IS the newest settled read" -> its clock is
    # judged against S (the settled session), never L.
    lc_asof = (leadership_doc or {}).get("asof") if leadership_doc else None
    lc_refused_future = _is_future(lc_asof, L, now)
    lc_stale_override = True if lc_refused_future else bool(lc_asof != S)
    leadership = _leadership_crack_read(leadership_doc, S, stale_override=lc_stale_override)
    if lc_refused_future and leadership_doc:
        # Named receipt only — the refusal is already enforced structurally via
        # stale_override=True (SourceRead.usable is False); this just makes the
        # reason auditable in the evidence drawer, same idiom as `capped_sources`.
        leadership = _leadership_crack_read(
            dict(leadership_doc, _refused_reason="refused_future"),
            S, stale_override=True,
        )

    return [measured, leadership, radar]


def _clear_transition(settled_stage: str | None) -> dict[str, Any]:
    return {"stage": settled_stage, "pending": None}


def _advance_transition(
    prev: dict[str, Any] | None,
    *,
    live_session: str | None,
    precedence: str,
    candidate_stage: str | None,
    settled_stage: str | None,
    debounce_ticks: int,
) -> dict[str, Any]:
    """The dwell/debounce state (Grey-Deer-owned; never the composer's).

    * `precedence != "live"` -> the settled bake has caught up to or passed this
      live observation: supersede + CLEAR (stable <- settled stage, no pending, no
      ticking — freeze §GD-3 "no transition ticking").
    * a NEW live trading day (`L` advanced past the persisted session) -> the prior
      day's dwell state does not carry over; re-baseline from the settled stage, and
      if today's first candidate already differs, `pending` appears IMMEDIATELY.
    * otherwise: normal debounce. A null candidate NEVER ticks in any direction
      (frozen, not a calm vote). Symmetric for escalation and de-escalation — the
      logic below does not special-case direction at all.
    """
    prev = prev or {}
    prev_session = prev.get("session")
    prev_stable = prev.get("stable_stage")
    prev_pending = prev.get("pending") or {}

    if precedence != "live":
        stable_stage, pending = settled_stage, None
    elif live_session != prev_session:
        stable_stage = settled_stage
        if candidate_stage is not None and candidate_stage != stable_stage:
            ticks = 1
            if ticks >= max(1, debounce_ticks):
                stable_stage, pending = candidate_stage, None
            else:
                pending = {"stage": candidate_stage, "ticks": ticks, "needs": debounce_ticks}
        else:
            pending = None
    elif candidate_stage is None:
        # outage: freeze exactly as-is — never advance, never clear.
        stable_stage, pending = prev_stable, (prev_pending or None)
    elif candidate_stage == prev_stable:
        stable_stage, pending = prev_stable, None
    else:
        if prev_pending.get("stage") == candidate_stage:
            ticks = int(prev_pending.get("ticks") or 0) + 1
        else:
            ticks = 1
        if ticks >= max(1, debounce_ticks):
            stable_stage, pending = candidate_stage, None
        else:
            stable_stage = prev_stable
            pending = {"stage": candidate_stage, "ticks": ticks, "needs": debounce_ticks}

    return {
        "session": live_session,
        "candidate_stage": candidate_stage,
        "stable_stage": stable_stage,
        "pending": pending,
    }


# ── build / write ────────────────────────────────────────────────────────────────

def build(root: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Read the live plane's own artifacts, compose via the SAME pure composer, and
    return the wrapped `mastermind.risk_envelope/v1` live-provisional envelope."""
    root = root or _REPO_ROOT
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    cfg = _risk_envelope_cfg()
    debounce_ticks = int(cfg.get("debounce_ticks", _DEBOUNCE_TICKS_DEFAULT))
    stale_after_min = float(cfg.get("stale_after_min", _STALE_AFTER_MIN_DEFAULT))

    risk_state_doc = _read_json(risk_state_path(root))
    leadership_doc = _read_json(leadership_crack_path(root))
    settled = _read_json(settled_envelope_path(root)) or {}
    S = settled.get("source_session")
    B = settled.get("bundle_id")
    settled_stage = (settled.get("hazard_summary") or {}).get("stage")

    fresh = market_freshness(risk_state_doc, stale_after_min, now)
    built_dt = fresh["built_dt"]
    L = _live_session(built_dt)

    sources = build_live_sources(
        risk_state_doc=risk_state_doc,
        leadership_doc=leadership_doc,
        settled_source_session=S,
        live_session=L,
        market_usable=fresh["usable"],
        now=now,
    )

    observed_stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    produced_stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    envelope = compose_envelope(
        sources=sources,
        market=MARKET,
        source_session=L,
        as_of=L,
        observed_at=observed_stamp,
        produced_at=produced_stamp,
        stale_after=None,
        revision="live_provisional",
    )
    candidate_stage = envelope["hazard_summary"]["stage"]

    if L is None or S is None:
        precedence = "settled"
    elif L > S:
        precedence = "live"
    else:
        precedence = "settled"  # L == S (just settled) or L < S (older than settled)

    wrapper_live_active = bool(fresh["usable"] and precedence == "live")

    if wrapper_live_active:
        stale_reason = None
    elif risk_state_doc is None:
        stale_reason = "risk_state artifact unavailable"
    elif not fresh["live_active"]:
        stale_reason = "market closed or no fresh live read"
    elif fresh["future_artifact"]:
        stale_reason = "refused_future"
    elif not fresh["fresh_enough"]:
        stale_reason = "stale (older than stale_after_min)"
    elif L is not None and S is not None and L < S:
        stale_reason = "older than settled"
    elif L is not None and S is not None and L == S:
        stale_reason = "session already settled"
    else:
        stale_reason = "not live"

    prev = _read_json(out_path(root)) or {}
    live_transition = _advance_transition(
        prev.get("live_transition"),
        live_session=L,
        precedence=precedence,
        candidate_stage=candidate_stage,
        settled_stage=settled_stage,
        debounce_ticks=debounce_ticks,
    )

    out = dict(envelope)
    out.update({
        "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "live_active": wrapper_live_active,
        "stale_reason": stale_reason,
        "stale_after_min": stale_after_min,
        "precedence": precedence,
        "overlays": {"settled_bundle_id": B, "settled_source_session": S},
        "live_transition": live_transition,
        "clocks": {
            "event_time": built_dt.isoformat().replace("+00:00", "Z") if built_dt else None,
            "observed_at": observed_stamp,
            "produced_at": produced_stamp,
        },
    })
    return out


def write(root: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Build and atomically write. Never raises; returns the envelope (or {})."""
    try:
        env = build(root, now)
        payload = canonical_json(env) + "\n"
        _atomic_write(out_path(root), payload)
        log.info(
            "live_risk_envelope: L=%s precedence=%s live_active=%s hazard=%s pending=%s",
            env.get("source_session"), env.get("precedence"), env.get("live_active"),
            (env.get("hazard_summary") or {}).get("stage"),
            (env.get("live_transition") or {}).get("pending"),
        )
        return env
    except Exception as e:  # noqa: BLE001 — additive artifact, never breaks the lane
        log.warning("live_risk_envelope build failed: %s", e)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="compose and print to stdout; write nothing")
    parser.add_argument("--root", type=Path, default=None, help="repository root override")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.print_only:
        print(json.dumps(build(args.root), indent=2, ensure_ascii=False))
        return
    write(args.root)


if __name__ == "__main__":
    main()
