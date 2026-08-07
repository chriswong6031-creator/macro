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
import logging
from datetime import date, datetime, timezone

import pandas as pd

from collectors.polygon_options import PolygonOptions
from engine.gex_engine import compute_gex
from lib import config, store, nyse_calendar

log = logging.getLogger(__name__)

GROUP = "polygon_gex"
# the compute_gex summary fields persisted per underlying (matches cboe GexAdapter._row)
SUMMARY_KEYS = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")


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

    # FIRST-WRITER-WINS (2026-08-06). Session stamping means several runs resolve to the
    # SAME session: the Friday evening run, then Saturday's, Sunday's, and Monday's
    # pre-open one all describe Friday. Without this guard each would overwrite Friday's
    # file with a progressively staler and eventually PRE-MARKET snapshot — manufacturing
    # exactly the mixed-tape rows the 2026-08-06 migration had to quarantine. The evening
    # run is closest to the close, so the first writer wins and later ones no-op. Ahead of
    # the fetch, so a repeat run also spends no API quota. `--force` overrides.
    path = _chains_dir() / f"{asof.isoformat()}.parquet"
    if path.exists() and not force:
        print(f"::notice title=polygon-session-present::session {asof} already stored - "
              f"keeping the first (closest-to-close) snapshot, skipping this run "
              f"(pass --force to overwrite)", flush=True)
        log.info("polygon: session %s already stored — no-op (first writer wins)", asof)
        return {"status": "already_present", "date": asof.isoformat(),
                "session": asof.isoformat(), "path": str(path)}

    raw = client.snapshot(symbols, asof)
    if raw.empty:
        log.warning("polygon: snapshot empty — nothing accrued")
        return {"status": "empty", "date": asof.isoformat(),
                "session": asof.isoformat()}

    # 1. raw per-strike chain, session-partitioned (append-only, git-friendly)
    _compact(raw).to_parquet(path)
    log.info("polygon: wrote raw chain %s (%d rows, %d underlyings)",
             path.name, len(raw), raw["underlying"].nunique())

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

    return {"status": "ok", "rows": int(len(raw)),
            "underlyings": int(raw["underlying"].nunique()),
            "summaries": n_summ, "date": asof.isoformat(),
            "session": asof.isoformat()}


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
