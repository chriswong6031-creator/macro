#!/usr/bin/env python3
"""scripts/build_options_intel_brief.py — AD-1 Daily EOD Options Intelligence Brief producer.

Repository adapter for ``engine/options_intel_brief.py`` (the pure scoring engine).
Contract: ``contracts/options/OPTIONS_INTEL_BRIEF_V1.md``. This script owns 100% of the
file I/O (reads §2 inputs through their existing loaders/paths, never re-ingests, never
calls a collector), then hands fully materialised in-memory frames/dicts to the engine
and writes its returned payload to ``site/options_intel_brief.json``. Zero network calls.

NYSE-session arithmetic is the repository's canonical calendar module,
``lib/nyse_calendar.py`` — R1 of ``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION
_BY_FABLE.md`` ("pure rule arithmetic, zero data dependencies"; already the reference
every other nightly builder anchors sessions against, e.g. ``engine/session_anchor.py``).
This is the ONE canonical trading-calendar helper in the repo (grepped: no other module
defines a competing ``next_nyse_session``); we reuse ``session_n_forward(d, 1)`` for
"the next NYSE session" and ``sessions_apart`` for session-count arithmetic. No new
calendar is minted here (contract §1).

Atomic-write idiom mirrors the house pattern already used by
``scripts/reconcile_entry_radar.py::write_json_atomic`` (temp file in the same
directory, fsync, ``os.replace`` — a reader never observes a torn file), with the
contract's semantic no-op rule layered on top (§7): a rerun producing an identical
``receipt_id`` AND identical payload (module ``built_at_utc`` and the diagnostic-only
``_run`` block) leaves the committed bytes untouched.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import tempfile
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import nyse_calendar as nc  # noqa: E402
from engine import options_intel_brief as brief  # noqa: E402
from engine import gex_confirm  # noqa: E402 — read-only use per contract §2 input #3

CHAINS_DIR = _REPO_ROOT / "data" / "polygon_gex" / "chains"
SUMMARY_GLOB = str(_REPO_ROOT / "data" / "polygon_gex" / "summary_{sym}.parquet")
GEX_JSON_GLOB = str(_REPO_ROOT / "site" / "gex" / "{sym}.json")
EARNINGS_PATH = _REPO_ROOT / "data" / "earnings" / "earnings.parquet"
PROPHET_INDEX_PATH = _REPO_ROOT / "site" / "prophet" / "index.json"
SIGNING_GATE_PATH = _REPO_ROOT / "data" / "options_flow" / "signing_gate.json"
OUT_PATH = _REPO_ROOT / "site" / "options_intel_brief.json"

_ET = ZoneInfo("America/New_York")
_CLOSE_PLUS_SETTLE_ET = dt_time(17, 0)   # matches lib.nyse_calendar's own settle buffer
_STALE_AFTER_HOURS = 36                  # contract §4 input #1 "absent >36h after close"


# ─────────────────────────────────────────────────────────────────────────────
# File discovery / hashing.
# ─────────────────────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _committed_chain_sessions() -> list[str]:
    """Every session date with a chain parquet on disk, filtered to real NYSE sessions
    (a non-session filename is silently excluded — never fabricated as a scoreable day;
    mirrors ``lib.nyse_calendar.session_dates``' filename-keyed convention)."""
    files = sorted(glob.glob(str(CHAINS_DIR / "*.parquet")))
    stems = [Path(f).stem for f in files]
    return nc.session_dates(stems, label="options_intel_brief chains")


def _lawful_pairs(sessions: list[str]) -> dict[str, str]:
    sset = set(sessions)
    out = {}
    for a in sessions:
        b = nc.session_n_forward(date.fromisoformat(a), 1)
        if b is not None and b.isoformat() in sset:
            out[a] = b.isoformat()
    return out


def _load_chain(session: str) -> pd.DataFrame:
    return pd.read_parquet(CHAINS_DIR / f"{session}.parquet")


def _load_summary_spot(symbol: str, upto_session: str) -> list[float]:
    fp = Path(SUMMARY_GLOB.format(sym=symbol))
    if not fp.exists():
        return []
    df = pd.read_parquet(fp, columns=["spot"])
    idx = pd.to_datetime(df.index, errors="coerce")
    keep = idx.notna() & (idx.date <= date.fromisoformat(upto_session))
    vals = df.loc[keep, "spot"].astype(float)
    vals = vals[np.isfinite(vals)]
    return [float(v) for v in vals.tolist()]


def _load_gex_verdicts(symbols: list[str], as_of_session: str) -> tuple[dict[str, str | None], bool]:
    """Read ``site/gex/{SYM}.json`` and call the EXISTING ``engine.gex_confirm.assess``
    (contract §2 input #3). A verdict is kept ONLY when the artifact's own ``meta.asof``
    binds to S — otherwise the mechanics family is ABSENT for that symbol (contract §1:
    "GEX mechanics may set M_gex only when its evidence binds to S"; never borrowed).
    """
    out: dict[str, str | None] = {}
    any_bound = False
    for sym in symbols:
        fp = Path(GEX_JSON_GLOB.format(sym=sym))
        if not fp.exists():
            out[sym] = None
            continue
        try:
            payload = json.loads(fp.read_text())
        except Exception:
            out[sym] = None
            continue
        meta_asof = (payload.get("meta") or {}).get("asof")
        if meta_asof != as_of_session:
            out[sym] = None
            continue
        try:
            verdict = gex_confirm.assess(payload, direction="up")
        except Exception:
            verdict = None
        out[sym] = (verdict.get("verdict") if isinstance(verdict, dict) else None)
        any_bound = True
    return out, any_bound


def _load_earnings(symbols: list[str]) -> tuple[dict[str, str | None], bool]:
    if not EARNINGS_PATH.exists():
        return {s: None for s in symbols}, False
    try:
        df = pd.read_parquet(EARNINGS_PATH, columns=["next_date"])
    except Exception:
        return {s: None for s in symbols}, False
    nd = df["next_date"].to_dict()
    return {s: nd.get(s) for s in symbols}, True


def _load_prophet() -> tuple[dict[str, str | None], str | None]:
    if not PROPHET_INDEX_PATH.exists():
        return {}, None
    try:
        payload = json.loads(PROPHET_INDEX_PATH.read_text())
    except Exception:
        return {}, None
    plans = payload.get("plans") or []
    states = {}
    for pl in plans:
        asset = pl.get("asset")
        if asset:
            states[asset] = pl.get("entry_status")
    return states, payload.get("asof")


def _load_signing_gate() -> tuple[bool, str | None]:
    if not SIGNING_GATE_PATH.exists():
        return False, None
    try:
        payload = json.loads(SIGNING_GATE_PATH.read_text())
    except Exception:
        return False, None
    return bool(payload.get("direction_reliable")), payload.get("asof")


# ─────────────────────────────────────────────────────────────────────────────
# Staleness (wall-clock; the ONE place `now` may be read — engine never sees it).
# ─────────────────────────────────────────────────────────────────────────────


def _sessions_apart_str(a: str | None, b: str | None) -> int | None:
    """String-date wrapper for ``lib.nyse_calendar.sessions_apart`` — the engine deals
    only in ISO session strings (it never imports a calendar module itself)."""
    if a is None or b is None:
        return None
    return nc.sessions_apart(date.fromisoformat(a), date.fromisoformat(b))


def _session_n_forward_str(d: str, n: int) -> str:
    got = nc.session_n_forward(date.fromisoformat(d), n)
    return got.isoformat() if got is not None else d


def _is_stale(newest_session: str, now: datetime) -> bool:
    close_dt = datetime.combine(date.fromisoformat(newest_session), _CLOSE_PLUS_SETTLE_ET, tzinfo=_ET)
    hours = (now.astimezone(timezone.utc) - close_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    return hours > _STALE_AFTER_HOURS


# ─────────────────────────────────────────────────────────────────────────────
# Atomic write + semantic no-op (house idiom, contract §7).
# ─────────────────────────────────────────────────────────────────────────────


def write_json_atomic(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        body = json.dumps(payload, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _semantic_unchanged(existing_path: Path, new_payload: dict[str, Any]) -> bool:
    """True iff a prior artifact exists with the same receipt_id AND identical payload
    once ``built_at_utc`` is excluded (contract §7 — never churn git on a semantic no-op)."""
    if not existing_path.exists():
        return False
    try:
        old = json.loads(existing_path.read_text())
    except Exception:
        return False
    if old.get("receipt_id") != new_payload.get("receipt_id"):
        return False
    strip = lambda d: {k: v for k, v in d.items() if k != "built_at_utc"}  # noqa: E731
    return strip(old) == strip(new_payload)


# ─────────────────────────────────────────────────────────────────────────────
# Main.
# ─────────────────────────────────────────────────────────────────────────────


def build(*, now: datetime | None = None, out_path: Path = OUT_PATH,
          ignore_staleness: bool = False) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    sessions = _committed_chain_sessions()
    S, D, pending = brief.select_settled_pair(sessions, lambda d: (
        nc.session_n_forward(date.fromisoformat(d), 1).isoformat()
        if nc.session_n_forward(date.fromisoformat(d), 1) else None
    ))

    lawful_pairs = _lawful_pairs(sessions)
    input_receipts: list[dict[str, Any]] = []

    if S is None:
        # No lawful pair at all — MIXED_VINTAGE. Engine handles this branch directly
        # off a SessionPanel with as_of_session=None; still supply a receipt so the
        # header/receipt path is exercised honestly (empty watermark set).
        panel = brief.SessionPanel(
            as_of_session=None, oi_counted_date=None, pending_session=pending,
            pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
            chains_by_session={}, chain_next=None, lawful_pairs=lawful_pairs,
        )
        watermarks = {"chains_session_S": None, "chains_session_D": None,
                      "summaries_max_session": None, "events_loaded": False,
                      "prophet_asof": None, "signing_gate_asof": None}
        return brief.build_intel_brief(
            panel, source_watermarks=watermarks, input_receipts=input_receipts,
            built_at_utc=now.isoformat(), sessions_apart_fn=_sessions_apart_str,
            session_n_forward_fn=_session_n_forward_str,
        )

    # Load every committed chain session up to and including S (our real store is
    # small — 28 sessions / ~115MB total; the census in the AD-1 handoff §5.4 already
    # measured this feasible in one process).
    chains_by_session = {s: _load_chain(s) for s in sessions if s <= S}
    chain_D = _load_chain(D) if D not in chains_by_session else chains_by_session[D]

    for s, fp in ((S, CHAINS_DIR / f"{S}.parquet"), (D, CHAINS_DIR / f"{D}.parquet")):
        input_receipts.append({
            "logical_source": f"chains_{('S' if s == S else 'D')}", "path": str(fp.relative_to(_REPO_ROOT)),
            "asof": s, "sha256": _sha256_file(fp), "state": "ok" if fp.exists() else "missing",
        })

    present_names = sorted(brief.session_metrics(chains_by_session[S]).keys())

    summary_spot = {sym: _load_summary_spot(sym, S) for sym in present_names}
    summaries_max_session = None
    for sym in present_names:
        fp = Path(SUMMARY_GLOB.format(sym=sym))
        if fp.exists():
            try:
                df = pd.read_parquet(fp, columns=[])
                last = str(pd.to_datetime(df.index).max().date())
                if summaries_max_session is None or last > summaries_max_session:
                    summaries_max_session = last
            except Exception:
                continue

    gex_verdict, gex_any_bound = _load_gex_verdicts(present_names, S)
    event_date, events_loaded = _load_earnings(present_names)
    prophet_states, prophet_asof = _load_prophet()
    direction_reliable, signing_gate_asof = _load_signing_gate()

    input_receipts.append({
        "logical_source": "earnings", "path": str(EARNINGS_PATH.relative_to(_REPO_ROOT)),
        "asof": S, "sha256": _sha256_file(EARNINGS_PATH),
        "state": "ok" if events_loaded else "missing",
    })
    input_receipts.append({
        "logical_source": "prophet_index", "path": str(PROPHET_INDEX_PATH.relative_to(_REPO_ROOT)),
        "asof": prophet_asof, "sha256": _sha256_file(PROPHET_INDEX_PATH),
        "state": "ok" if PROPHET_INDEX_PATH.exists() else "missing",
    })
    input_receipts.append({
        "logical_source": "signing_gate", "path": str(SIGNING_GATE_PATH.relative_to(_REPO_ROOT)),
        "asof": signing_gate_asof, "sha256": _sha256_file(SIGNING_GATE_PATH),
        "state": "ok" if SIGNING_GATE_PATH.exists() else "missing",
    })

    stale = (not ignore_staleness) and _is_stale(max(sessions), now)

    panel = brief.SessionPanel(
        as_of_session=S, oi_counted_date=D, pending_session=pending,
        pending_reason=("OI_NOT_YET_SETTLED" if pending else None),
        chains_by_session=chains_by_session, chain_next=chain_D, lawful_pairs=lawful_pairs,
        summary_spot=summary_spot, gex_verdict=gex_verdict, gex_bound_to_S=True,
        event_date=event_date, events_loaded=events_loaded,
        prophet_entry_status=prophet_states, prophet_asof=prophet_asof,
        signing_gate_direction_reliable=direction_reliable, signing_gate_asof=signing_gate_asof,
        stale=stale,
    )

    watermarks = {
        "chains_session_S": S, "chains_session_D": D,
        "summaries_max_session": summaries_max_session,
        "events_loaded": events_loaded, "prophet_asof": prophet_asof,
        "signing_gate_asof": signing_gate_asof,
    }

    payload = brief.build_intel_brief(
        panel, source_watermarks=watermarks, input_receipts=input_receipts,
        built_at_utc=now.isoformat(), sessions_apart_fn=_sessions_apart_str,
        session_n_forward_fn=_session_n_forward_str,
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--ignore-staleness", action="store_true",
                     help="diagnostic only: score the newest committed session even if "
                          "it is older than the >36h freshness rule. Never used by the "
                          "nightly lane; for local verification of the scoring math "
                          "against a deliberately frozen test store.")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    payload = build(out_path=out_path, ignore_staleness=args.ignore_staleness)

    if _semantic_unchanged(out_path, payload):
        print(f"::notice title=options-intel-brief::semantic no-op — {out_path} unchanged "
              f"(receipt_id={payload.get('receipt_id')})", flush=True)
    else:
        write_json_atomic(out_path, payload)
        print(f"::notice title=options-intel-brief::wrote {out_path} "
              f"(receipt_id={payload.get('receipt_id')})", flush=True)

    print("=== options.intel_brief/v1 header ===")
    for k in ("as_of_session", "oi_counted_date", "pending_session", "pending_reason",
              "board_state", "board_reason", "eligibility", "receipt_id", "config_hash"):
        print(f"  {k}: {payload.get(k)}")
    print("state counts:")
    print(f"  opportunities={len(payload.get('opportunities') or [])} "
          f"(overflow={payload.get('opportunities_overflow')}) "
          f"event_board={len(payload.get('event_board') or [])} "
          f"risk_warnings={len(payload.get('risk_warnings') or [])} "
          f"no_signal_exemplar={'yes' if payload.get('no_signal_exemplar') else 'no'}")
    print("top-6 opportunities:")
    for c in (payload.get("opportunities") or [])[:6]:
        print(f"  {c['symbol']:6s} {c['direction']:10s} R={c['research_priority_score']:4d} "
              f"es={c['evidence_strength']:.3f} ec={c['evidence_confidence']:.3f} "
              f"({c['evidence_confidence_band']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
