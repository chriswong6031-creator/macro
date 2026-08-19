"""Polygon options-OI accrual — the GEX FOUNDATION (display / research only).

Each run snapshots the configured underlyings' option chains via Polygon and:
  1. writes the RAW per-strike chain to data/polygon_gex/chains/{YYYY-MM-DD}.parquet
     — SESSION-partitioned & append-only (never rewrites history, so the daily
     ``git add data/`` adds exactly one small blob). This is the per-strike OI
     history the Cboe path discards and that CANNOT be backfilled: open interest is
     point-in-time only.
  2. upserts a per-underlying compute_gex summary to data/polygon_gex/summary_{SYM}
     .parquet (1 row/session, mirroring the Cboe gex_{SYM} frames so the two sources
     are directly comparable; feeds the future validate-gated GEX drawdown leg).
  3. appends a per-session health-receipt attempt to
     data/polygon_gex_health/{YYYY-MM-DD}.json (AD-1C0, 2026-08-19) — a sidecar,
     never mutating the chain parquet, that turns a failed/partial capture into a
     diagnosable REASON census instead of a bare empty snapshot. See _health_dir()
     for why it is a SIBLING of data/polygon_gex/ rather than nested inside it.

STAMP = THE SESSION THE SNAPSHOT DESCRIBES, NOT THE RUN DATE (2026-08-06 repair).
The accrual used to stamp ``datetime.now(timezone.utc).date()``. A nightly run that
lands at 01:24 UTC carries the PREVIOUS ET session's closing chain, so the whole store
sat one session forward of the market it measures — and the write-side session gate then
refused every Saturday-UTC run, which is a FRIDAY-evening ET accrual. Session 2026-07-31
(the first Friday after the gate landed) was lost that way: runs fired on both 08-01 and
08-02 and both were refused before the fetch, and polygon OI cannot be backfilled.
``_resolve_session`` fixes both halves at once — see its docstring.

No-op without POLYGON_API_KEY. Never raises into the caller — collect.py wraps this
additively, exactly like the FRED-vintages / basket-extras steps. See
collectors/polygon_options.py and engine/gex_engine.py.

History is FORWARD-ONLY here: this writer never deletes or re-dates a stored file. The
one-off repair of the pre-2026-08-06 run-date stamps lives in its own audited script,
``scripts/migrate_polygon_gex_session_stamps.py``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.polygon_options import PolygonOptions  # noqa: E402
from engine.gex_engine import compute_gex  # noqa: E402
from lib import config, store, nyse_calendar  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "polygon_gex"
# the compute_gex summary fields persisted per underlying (matches cboe GexAdapter._row)
SUMMARY_KEYS = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")

# AD-1C0 — a session's stored capture is HEALTHY at/above this coverage; below it
# (but with rows captured) it is PARTIAL; zero rows captured is FAILED. See the
# FIRST-WRITER QUALITY RULE in accrue() for what each verdict is allowed to do.
SOURCE_HEALTH_FLOOR = 0.90


def _resolve_session(as_of) -> date:
    """The NYSE session a snapshot taken at `as_of` describes.

    A ``datetime`` (or None) is an ACCRUAL INSTANT — "snapshot the chains now" — and the
    session it describes is ``expected_last_session``: the most recent session whose
    16:00 ET close plus a settle buffer has passed. A ``date`` is an EXPLICIT session
    (the ``--date`` CLI path and the tests) and is taken at face value.

    ``nyse_calendar.session_date()`` is the WRONG helper here even though it is the house
    default for artifact stamps. It calls the whole ET calendar day "the session" so that
    the intraday fastpath can stamp the session IN PROGRESS; at 02:24 ET Wednesday it
    returns Wednesday, but a chain snapshotted then carries TUESDAY's closing state.
    Measured: the file stamped 2026-07-08 (committed 07-08 06:24Z) has SPY spot 747.71,
    exactly the yahoo close of 07-07. ``expected_last_session`` returns 07-07.

    ``datetime`` is a subclass of ``date``, so the isinstance checks must be in this order.
    """
    if isinstance(as_of, datetime):
        return nyse_calendar.expected_last_session(as_of)
    if isinstance(as_of, date):
        return as_of
    return nyse_calendar.expected_last_session()


def _chains_dir():
    d = config.data_dir() / GROUP / "chains"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _health_dir():
    # NOT data/polygon_gex/health/ (the FROZEN SPEC's literal path) — a SIBLING top-
    # level directory instead, deliberately outside data/polygon_gex/ (DEVIATION,
    # see the packet's DEVIATIONS section). tests/test_polygon_gex_session_stamps.py
    # ::test_no_stray_files_shadow_the_chains_glob (unowned, pinned, not touched by
    # this packet) hard-fails on ANY entry under data/polygon_gex/ that is not
    # "chains" or a "summary_*.parquet" file; a subdirectory there would break that
    # invariant the first time the nightly ever writes a receipt. This directory is
    # still named/co-located right next to data/polygon_gex/, satisfying the spec's
    # intent ("next to the chain store") without colliding with that check.
    d = config.data_dir() / f"{GROUP}_health"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _receipt_path(session: date) -> Path:
    return _health_dir() / f"{session.isoformat()}.json"


def _read_receipt(session: date) -> list[dict] | None:
    """The stored ``attempts`` list for `session`, or None when no receipt exists
    yet — either a brand-new session, or a LEGACY chains file predating this
    sidecar (rule 4 of the first-writer quality rule treats that as healthy)."""
    path = _receipt_path(session)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    attempts = data.get("attempts") if isinstance(data, dict) else None
    return attempts if isinstance(attempts, list) else None


def _last_write_entry(attempts: list[dict] | None) -> dict | None:
    """The most recent attempt whose decision actually changed the stored
    parquet — i.e. the entry that describes what is CURRENTLY on disk."""
    if not attempts:
        return None
    for entry in reversed(attempts):
        if entry.get("decision") in ("wrote", "replaced_partial", "forced"):
            return entry
    return None


def _stored_health(attempts: list[dict] | None) -> str:
    """Health of whatever is CURRENTLY stored, given its receipt's attempts (or
    None for a session with no receipt at all). A legacy chain file — or a
    receipt carrying no write-decision entry — is treated as healthy: immutable,
    never retro-replaced (rule 4)."""
    last = _last_write_entry(attempts)
    return (last or {}).get("health") or "healthy"


def _carry_forward(entry: dict | None) -> dict | None:
    """Reuse a prior write's census numbers for a SKIP attempt's receipt row, so a
    reader scanning the attempts list sees a continuous picture of the store
    instead of a gap on every no-op run."""
    if entry is None:
        return None
    return {
        "requested_underlyings": entry.get("requested_underlyings"),
        "attempted_underlyings": entry.get("attempted_underlyings"),
        "successful_underlyings": entry.get("successful_underlyings"),
        "coverage_pct": entry.get("coverage_pct"),
        "failure_reasons": entry.get("failure_reasons") or {},
    }


def _health_verdict(coverage_pct: float, captured_rows: int) -> str:
    """healthy: coverage_pct >= SOURCE_HEALTH_FLOOR. partial: rows were captured
    but coverage sits under the floor. failed: zero rows captured — an
    all-symbol failure, which must never again be reasonless."""
    if captured_rows <= 0:
        return "failed"
    return "healthy" if coverage_pct >= SOURCE_HEALTH_FLOOR else "partial"


def _append_health_attempt(session: date, *, decision: str, health: str,
                           census: dict | None) -> None:
    """Append one attempt entry to the session's health-receipt sidecar
    (data/polygon_gex_health/<session>.json — see _health_dir()'s docstring for
    why this is not the nested data/polygon_gex/health/ path). Called on EVERY
    accrual that
    reaches a real trading session — including no-op skips — so a session's
    health history is never reasonless. NEVER mutates the chain parquet; this is
    a sidecar only. Atomic (tmp file + rename) so a crash mid-write cannot leave
    a torn receipt."""
    path = _receipt_path(session)
    attempts = list(_read_receipt(session) or [])
    attempts.append({
        "capture_instant": datetime.now(timezone.utc).isoformat(),
        "requested_underlyings": (census or {}).get("requested_underlyings"),
        "attempted_underlyings": (census or {}).get("attempted_underlyings"),
        "successful_underlyings": (census or {}).get("successful_underlyings"),
        "coverage_pct": (census or {}).get("coverage_pct"),
        "failure_reasons": (census or {}).get("failure_reasons") or {},
        "decision": decision,
        "health": health,
    })
    payload = {"session": session.isoformat(), "attempts": attempts}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _compact(raw: pd.DataFrame) -> pd.DataFrame:
    """Shrink the daily raw file (it commits every run): float32 numerics + a
    categorical underlying ~halve it with no analytical cost (float32's ~16M-int
    precision covers any OI)."""
    out = raw.copy()
    for c in ("K", "T", "oi", "iv", "gamma", "delta", "volume", "spot"):
        if c in out.columns:
            out[c] = out[c].astype("float32")
    out["underlying"] = out["underlying"].astype("category")
    return out


def _summarize(raw: pd.DataFrame, sym: str, cfg: dict) -> pd.DataFrame | None:
    """compute_gex over one underlying's stored chain -> 1-row/day summary frame.
    Returns None when the chain has no iv-bearing strikes to trust."""
    sub = raw[raw["underlying"] == sym].dropna(subset=["iv"])
    if sub.empty:
        return None
    spot = float(sub["spot"].iloc[0])
    gx = cfg["gex"]
    ecfg = {k: gx[k] for k in ("contract_multiplier", "pct_move",
                               "strike_window_pct", "max_expiry_days") if k in gx}
    ecfg["r"] = gx.get("r", 0.043)
    ecfg["q"] = (cfg.get("div_yield") or {}).get(sym, 0.0)
    summ = compute_gex(sub[["K", "T", "iv", "oi", "is_call", "expiry"]], spot, ecfg, symbol=sym)
    asof = pd.Timestamp(sub["asof"].iloc[0]).normalize()
    return pd.DataFrame({k: [summ.get(k)] for k in SUMMARY_KEYS}, index=[asof])


def accrue(as_of=None, *, force: bool = False) -> dict:
    """Snapshot + persist one SESSION. Returns a small status dict (logging/tests)."""
    cfg = config.load().get("polygon")
    if not cfg:
        log.info("polygon: no config section — skip")
        return {"status": "no_config"}
    client = PolygonOptions()
    if not client.enabled():
        log.info("polygon: POLYGON_API_KEY absent — skip (no-op)")
        return {"status": "no_key"}

    asof = _resolve_session(as_of)
    from engine.options_universe import gex_symbols
    symbols = gex_symbols(cfg.get("gex"))
    log.info("polygon: snapshotting %d underlyings for session %s "
             "(%d anchors + baskets=%s)", len(symbols), asof,
             len(cfg["gex"].get("symbols") or []),
             cfg["gex"].get("include_baskets", False))
    # WRITE-SIDE SESSION GATE (M7 2026-07-29; re-scoped 2026-08-06). `asof` is now the
    # SESSION the snapshot describes (see _resolve_session), not the UTC run date, so on
    # the datetime path — every scheduled run — this gate is ALWAYS TRUE and never fires.
    # That is the point: it used to reject Saturday/Sunday UTC, i.e. the Friday-evening
    # and weekend ET runs, and session 2026-07-31 was permanently lost to it. What still
    # routes through here is the EXPLICIT `--date`/test path, where a caller can name a
    # day the market never opened; that is a caller error and is still refused.
    if not nyse_calendar.is_session(asof):
        # Bare line-start print (never a logger — see tests/test_gh_annotation_line_start).
        print(f"::notice title=polygon-session-gate::{asof} is not an NYSE session - "
              f"chain snapshot and summaries skipped, store left unadvanced", flush=True)
        log.info("polygon: %s is not a trading session — nothing accrued", asof)
        return {"status": "non_session", "date": asof.isoformat(),
                "session": asof.isoformat()}

    # FIRST-WRITER QUALITY RULE (2026-08-19, AD-1C0 — supersedes the plain
    # 2026-08-06 first-writer-wins guard). Session stamping means several runs
    # resolve to the SAME session: the Friday evening run, then Saturday's,
    # Sunday's, and Monday's pre-open one all describe Friday. A stored HEALTHY
    # session (>=SOURCE_HEALTH_FLOOR coverage) is IMMUTABLE — checked here, BEFORE
    # the fetch, so a repeat run of an already-good session still spends no API
    # quota, same as before. A stored PARTIAL session is the one case that needs a
    # fetch before deciding: only a STRICTLY better capture may replace it (see the
    # decision block below), so control falls through instead of returning here. A
    # LEGACY chain file with no receipt at all is treated as healthy (immutable) —
    # it predates this sidecar and must never be retro-replaced. `--force` keeps
    # full override semantics regardless of any of the above.
    path = _chains_dir() / f"{asof.isoformat()}.parquet"
    stored_attempts: list[dict] | None = None
    stored_last: dict | None = None
    stored_health: str | None = None
    if path.exists() and not force:
        stored_attempts = _read_receipt(asof)
        stored_last = _last_write_entry(stored_attempts)
        stored_health = _stored_health(stored_attempts)
        if stored_health != "partial":
            print(f"::notice title=polygon-session-present::session {asof} already stored - "
                  f"keeping the first (closest-to-close) snapshot, skipping this run "
                  f"(pass --force to overwrite)", flush=True)
            log.info("polygon: session %s already stored — no-op (first writer wins)", asof)
            _append_health_attempt(asof, decision="skipped_already_healthy",
                                   health=stored_health, census=_carry_forward(stored_last))
            return {"status": "already_present", "date": asof.isoformat(),
                    "session": asof.isoformat(), "path": str(path)}
        log.info("polygon: session %s stored capture is PARTIAL (below the %.0f%% floor) "
                 "— re-fetching to check for a strictly-better replacement",
                 asof, SOURCE_HEALTH_FLOOR * 100)

    result = client.snapshot(symbols, asof)
    # New contract: snapshot() returns (raw_df, census), and requested_underlyings
    # is ALWAYS the current gex_symbols() resolution (never hard-coded). A legacy/
    # test double may still return a bare DataFrame (the pre-AD-1C0 contract): it
    # cannot report a true attempt/failure census against the full universe, so
    # rather than inventing a bogus PARTIAL verdict against symbols it never even
    # tried, treat whatever it returned as complete — this is exactly the old
    # first-writer-wins semantics, preserved for any caller not yet upgraded to
    # the (raw, census) contract.
    if isinstance(result, tuple):
        raw, census = result
        census = dict(census)
        census["requested_underlyings"] = len(symbols)
    else:
        raw = result
        successful = (int(raw["underlying"].nunique())
                     if not raw.empty and "underlying" in raw.columns else 0)
        census = {
            "attempted_underlyings": successful, "successful_underlyings": successful,
            "requested_underlyings": successful,
            "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        }
    census["coverage_pct"] = (round(census["successful_underlyings"]
                                    / census["requested_underlyings"], 4)
                              if census["requested_underlyings"] else 0.0)

    if raw.empty:
        # Zero-capture runs keep status "empty" for consumer compat, but now carry
        # health "failed" plus the full census — an all-symbol failure can never
        # again be reasonless. Nothing is written; a stored partial (if any) is
        # untouched, so this is recorded as "not better" than what is already there.
        health = _health_verdict(census["coverage_pct"], 0)
        log.warning("polygon: snapshot empty — nothing accrued (%s)", census)
        _append_health_attempt(asof, decision="skipped_not_better", health=health, census=census)
        return {"status": "empty", "date": asof.isoformat(), "session": asof.isoformat(),
                "health": health, "census": census}

    health = _health_verdict(census["coverage_pct"], len(raw))
    if force:
        decision = "forced"
    elif stored_health != "partial":
        # No prior file existed (stored_health is None here — the branch above
        # already returned for every case where a file existed and was immutable).
        decision = "wrote"
    else:
        stored_successful = (stored_last or {}).get("successful_underlyings") or 0
        stored_coverage = (stored_last or {}).get("coverage_pct") or 0.0
        if (census["successful_underlyings"] > stored_successful
                and (health == "healthy" or census["coverage_pct"] - stored_coverage >= 0.10)):
            decision = "replaced_partial"
        else:
            decision = "skipped_not_better"

    if decision == "skipped_not_better":
        log.info("polygon: session %s new capture (%d ok, %.1f%% coverage) is not strictly "
                 "better than the stored partial — keeping the existing file",
                 asof, census["successful_underlyings"], census["coverage_pct"] * 100)
        _append_health_attempt(asof, decision=decision, health=stored_health, census=census)
        return {"status": "already_present", "date": asof.isoformat(), "session": asof.isoformat(),
                "path": str(path), "health": stored_health, "census": census}

    # 1. raw per-strike chain, session-partitioned (append-only, git-friendly).
    # `decision` is one of wrote/replaced_partial/forced here — a single-vintage
    # overwrite either way, never a merge of captures.
    _compact(raw).to_parquet(path)
    log.info("polygon: wrote raw chain %s (%d rows, %d underlyings) decision=%s health=%s",
             path.name, len(raw), raw["underlying"].nunique(), decision, health)

    # 2. per-underlying compute_gex summary (reuse the engine — no new math)
    n_summ = 0
    for sym in symbols:
        try:
            row = _summarize(raw, sym, cfg)
            if row is not None:
                store.upsert(GROUP, f"summary_{sym}", row, outlier_col=None)
                n_summ += 1
        except Exception as e:  # noqa: BLE001 — one symbol must not abort the rest
            log.warning("polygon summary %s failed: %s", sym, e)

    _append_health_attempt(asof, decision=decision, health=health, census=census)
    return {"status": "ok", "rows": int(len(raw)),
            "underlyings": int(raw["underlying"].nunique()),
            "summaries": n_summ, "date": asof.isoformat(),
            "session": asof.isoformat(), "health": health, "census": census}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="",
                    help="YYYY-MM-DD SESSION to store (default: the session the current "
                         "instant describes, per nyse_calendar.expected_last_session)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an already-stored session (default: first writer wins)")
    args = ap.parse_args()
    asof = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    log.info("polygon accrual: %s", accrue(asof, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
