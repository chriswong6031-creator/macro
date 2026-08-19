#!/usr/bin/env python3
"""scripts/build_risk_envelope.py — settled producer for `mastermind.risk_envelope/v1`.

    python -m scripts.build_risk_envelope           # writes both copies
    python -m scripts.build_risk_envelope --print   # compose + print, write nothing

This is the SETTLED lane only.  The live provisional lane (`site/live/risk_envelope.json`)
is GD-3 and is gated on this wave's production acceptance; it will call the SAME pure
composer with fresher observations and must never fork the state logic.

Division of labour
------------------
`engine/risk_envelope.py` is pure: states in, envelope out, no clock, no disk.  THIS
file owns everything impure — reading the settled artifacts, reading the clock, and the
atomic dual write.  The adapters below are the only place that knows how a given organ
spells its state, and each one carries that organ's read through VERBATIM.

Output paths (freeze §5.1 + the risk_radar_scorecard dual-write convention):
  * ``data/risk_envelope/latest.json``  — durable settled copy
  * ``site/riskdata/risk_envelope.json`` — public/cross-repository contract

Both are written with tmp+os.replace, so no reader ever sees a partial file.

Never fatal: a missing source becomes a MISSING coverage entry and (if required) nulls
the hazard stage.  That is the honest answer, and it is why the builder does not need
to guess.
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
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.risk_envelope import (  # noqa: E402
    SourceRead,
    compose_envelope,
    canonical_json,
)

log = logging.getLogger(__name__)

MARKET = "US"

# Freshness horizon for the settled lane: a settled artifact whose own clock predates
# the session we are baking is off-session, and a required off-session source cannot
# hold the hazard stage open.  Expressed in sessions (date strings), never wall-clock,
# because settled organs stamp dates.
_MEASURED_SOURCE = "market-state-latest"
_LEADERSHIP_SOURCE = "leadership-crack-latest"
_RADAR_SOURCE = "risk-radar-us"


# ── source adapters ────────────────────────────────────────────────────────────
# Each adapter answers exactly one question: "what did this organ publish, and what
# descriptive V0 stage does its OWN state vocabulary mean?".  Adapters never threshold
# a score into a stage and never look at another organ.

def _market_state_read(doc: Mapping[str, Any] | None, session: str | None) -> SourceRead:
    """Market State — the slow confirmed trend.  Carried verbatim, never recomputed."""
    if not doc:
        return SourceRead(
            source_id=_MEASURED_SOURCE, role="measured_state",
            present=False, required=True,
        )
    fresh = doc.get("freshness") or {}
    as_of = doc.get("asof")
    # Two independent staleness signals, both from the organ itself: its own
    # `freshness.stale` verdict, and whether its clock matches the session we bake.
    stale = bool(fresh.get("stale")) or (bool(session) and bool(as_of) and as_of != session)
    return SourceRead(
        source_id=_MEASURED_SOURCE,
        role="measured_state",
        state=doc.get("verdict"),
        score=doc.get("score"),
        as_of=as_of,
        stale=stale,
        required=True,
        # label_* names the SOURCE (what the drawer's "Source" column says).
        # The organ's own bilingual STATE label rides in detail, so the band can
        # print the state in the organ's own words without renaming the source.
        label_en="Market state",
        label_zh="市场状态",
        detail={
            "state_label_en": doc.get("label_en"),
            "state_label_zh": doc.get("label_zh"),
            "raw_score": doc.get("raw_score"),
            "capped": bool(doc.get("capped")),
            "score_source": doc.get("score_source"),
            "expected_asof": fresh.get("expected_asof"),
            "any_input_stale": bool(fresh.get("any_input_stale")),
            "worst_input_age_days": fresh.get("worst_input_age_days"),
        },
    )


# Leadership Crack's own state vocabulary -> the V0 descriptive stage.  This is a
# TRANSLATION of one organ's published vocabulary, not a judgement: BROKEN means the
# tracked leadership cohort has already taken measured damage, which is a present-tense
# observation (FRAGILE), never an anticipatory claim.
_LEADERSHIP_STAGE = {
    "INTACT": "NONE",
    "OK": "NONE",
    "REPAIRING": "NONE",
    "STRAINED": "FRAGILE",
    "CRACKED": "FRAGILE",
    "BROKEN": "FRAGILE",
}


def _leadership_crack_read(doc: Mapping[str, Any] | None, session: str | None) -> SourceRead:
    """Leadership Crack — has the leadership cohort taken damage this session?"""
    if not doc:
        return SourceRead(
            source_id=_LEADERSHIP_SOURCE, role="hazard_evidence",
            present=False, required=True,
        )
    as_of = doc.get("asof")
    state = doc.get("state")
    stale = bool(session) and bool(as_of) and as_of != session
    stage = _LEADERSHIP_STAGE.get(str(state).upper()) if state else None
    # A BROKEN cohort that is also dislocated is damage that has already spread beyond
    # the cohort's own members — a present-tense TRANSMITTING observation, still
    # descriptive (it reports what the tape did, not what it will do).
    if stage == "FRAGILE" and str(state).upper() == "BROKEN" and doc.get("dislocation"):
        stage = "TRANSMITTING"
    return SourceRead(
        source_id=_LEADERSHIP_SOURCE,
        role="hazard_evidence",
        state=state,
        score=None,
        as_of=as_of,
        stale=stale,
        required=True,
        hazard_stage=stage,
        label_en="Leadership cohort",
        label_zh="龙头股群体",
        detail={
            "state_since": doc.get("state_since"),
            "cohort_role": doc.get("cohort_role"),
            "n_fresh": doc.get("n_fresh"),
            "n_total": doc.get("n_total"),
            "dislocation": bool(doc.get("dislocation")),
            "high_window_sessions": doc.get("high_window_sessions"),
        },
    )


# Risk Radar's own state vocabulary -> the V0 descriptive stage.
_RADAR_STAGE = {
    "calm": "NONE",
    "watch": "NONE",
    "caution": "FRAGILE",
    "warning": "FRAGILE",
    "alert": "TRANSMITTING",
    "loud": "TRANSMITTING",
    "severe": "BREAKDOWN",
}


def _risk_radar_read(radar: Mapping[str, Any] | None, session: str | None,
                     ms_asof: str | None) -> SourceRead:
    """US Risk Radar — the cross-asset scare monitor, source-native on Market State.

    Optional coverage: the radar corroborates but is not required for the stage to be
    knowable, so its absence degrades coverage rather than nulling the answer.
    """
    if not radar:
        return SourceRead(
            source_id=_RADAR_SOURCE, role="hazard_evidence",
            present=False, required=False,
        )
    state = radar.get("state")
    stale = bool(session) and bool(ms_asof) and ms_asof != session
    return SourceRead(
        source_id=_RADAR_SOURCE,
        role="hazard_evidence",
        state=state,
        score=radar.get("top_score"),
        as_of=ms_asof,
        stale=stale,
        required=False,
        hazard_stage=_RADAR_STAGE.get(str(state).lower()) if state else None,
        label_en="Cross-asset scares",
        label_zh="跨资产风险扫描",
        detail={
            "is_warning": bool(radar.get("is_warning")),
            "is_loud": bool(radar.get("is_loud")),
            "label_en": radar.get("label_en"),
            "label_zh": radar.get("label_zh"),
        },
    )


def build_sources(
    market_state: Mapping[str, Any] | None,
    leadership_crack: Mapping[str, Any] | None,
    session: str | None,
) -> list[SourceRead]:
    """Adapt the settled artifacts into source-native reads. Pure; no I/O."""
    ms_asof = (market_state or {}).get("asof")
    return [
        _market_state_read(market_state, session),
        _leadership_crack_read(leadership_crack, session),
        _risk_radar_read((market_state or {}).get("radar"), session, ms_asof),
    ]


# ── I/O ────────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            log.warning("risk_envelope: source missing %s", path)
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — a bad source becomes MISSING coverage
        log.warning("risk_envelope: source unreadable %s (%s)", path, e)
        return None


def _atomic_write(path: Path, payload: str) -> None:
    """Write atomically via tmp+rename. Never raises (mirrors risk_radar_scorecard)."""
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
        # mkstemp creates 0600; site/riskdata/ is publicly served, so a 0600 artifact
        # written by the nightly would 403 for the web user until the next git checkout
        # reset the mode. Never fatal.
        try:
            os.chmod(path, 0o644)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        log.warning("risk_envelope atomic write to %s failed: %s", path, e)
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:  # noqa: BLE001
                pass


def data_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "data" / "risk_envelope" / "latest.json"


def site_path(root: Path | None = None) -> Path:
    return (root or _REPO_ROOT) / "site" / "riskdata" / "risk_envelope.json"


def build(root: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Read the settled artifacts and compose the envelope. Returns the envelope dict."""
    root = root or _REPO_ROOT
    now = now or datetime.now(timezone.utc)
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    market_state = _read_json(root / "data" / "market_state" / "latest.json")
    leadership = _read_json(root / "data" / "leadership_crack" / "latest.json")

    # The settled session is the market-state organ's own session: it is the artifact
    # that defines "this settled session" for the US market.  Every other source is
    # then measured AGAINST that session rather than against wall-clock time.
    session = (market_state or {}).get("asof")

    sources = build_sources(market_state, leadership, session)
    return compose_envelope(
        sources=sources,
        market=MARKET,
        source_session=session,
        observed_at=stamp,
        produced_at=stamp,
        as_of=session,
        stale_after=None,
        revision="settled",
    )


def write(root: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Build and atomically write both copies. Never raises; returns the envelope."""
    try:
        env = build(root, now)
        payload = canonical_json(env) + "\n"
        _atomic_write(data_path(root), payload)
        _atomic_write(site_path(root), payload)
        log.info(
            "risk_envelope: session=%s measured=%s hazard=%s coherence=%s data=%s bundle=%s",
            env.get("source_session"),
            (env.get("measured_state") or {}).get("verdict"),
            (env.get("hazard_summary") or {}).get("stage"),
            (env.get("coherence") or {}).get("state"),
            env.get("data_state"),
            env.get("bundle_id"),
        )
        return env
    except Exception as e:  # noqa: BLE001 — additive artifact, never breaks the bake
        log.warning("risk_envelope build failed: %s", e)
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
