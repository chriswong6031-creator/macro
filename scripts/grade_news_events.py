"""scripts/grade_news_events.py — forward-return calibration for event classes (W4).

Standalone and importable. Reads the PIT event log written by engine.news_event_ledger,
grades forward returns per (event_type, direction) using the SAME price layer qledger uses,
and emits site/news/calibration.json per the pinned contract schema.

ARCHITECTURE NOTES:
  • Price source: engine.ai_desk._close_series + engine.ai_desk._level_asof (same as qledger).
  • Grading convention: next-bar fill (same as qledger FILL_NEXT_BAR) — entry = first close
    STRICTLY AFTER first_seen_utc.date; exit = close on/before fill+horizon_d. No grade when
    exit not yet covered (not matured).
  • Direction convention for hit: bullish → SPY-relative return > 0; bearish → < 0.
    informational/mixed → no directional hit (n_graded stays 0 for that row).
  • Events without tickers are counted in n but not graded in v1 (macro_release, etc.).
    This is documented honestly in the artifact: n vs n_graded shows the split.
  • Reject sample graded per reason by SPY-relative return averaged over all tickers.
  • Wilson 95% CI on hit_5d: lower/upper bounds.
  • Verdict: n_graded < 30 → insufficient; wilson_low_5d > 0.50 → candidate;
    wilson_high_5d < 0.50 → no_edge; else → context_only.
  • Day-1 reality: event_log starts empty; all verdicts will be 'insufficient' with zeros.
    The contract requires this valid empty state. Never fabricate history.
  • NUMPY-CAST GUARD: every numeric value in the emitted JSON is cast to int()/float()
    at the artifact boundary. Parquet-derived numpy scalars crash json.dumps silently
    (known prod bug — qledger claims.jsonl incident). This is tested explicitly.

Run:  python scripts/grade_news_events.py
      python scripts/grade_news_events.py --root /path/to/repo
      python scripts/grade_news_events.py --dry-run  # print JSON, don't write

is_context_only = True  (artifact schema contract)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("grade_news_events")

# --------------------------------------------------------------------------- #
# Contract constants
# --------------------------------------------------------------------------- #
SCHEMA = "news_event_calibration.v1"
GRADE_HORIZONS = (1, 5, 21)      # 1d included so the ledger accrues fast
VERDICT_N_GRADED_MIN = 30        # n_graded < 30 → insufficient
SPY = "SPY"

_OUTPUT_REL = ("site", "news", "calibration.json")


# --------------------------------------------------------------------------- #
# Root helper
# --------------------------------------------------------------------------- #
def _root(root=None) -> Path:
    return Path(root) if root else config.ROOT


# --------------------------------------------------------------------------- #
# Price helpers (reuse qledger machinery)
# --------------------------------------------------------------------------- #
def _close_series_safe(ticker: str, root: Path):
    """Return the price series for `ticker`, or None on any error."""
    try:
        from engine import ai_desk as _ad  # noqa: PLC0415
        s = _ad._close_series(ticker, root)
        return s if (s is not None and len(s) > 0) else None
    except Exception as exc:  # noqa: BLE001
        log.debug("_close_series_safe(%s): %s", ticker, exc)
        return None


def _fwd_ret_relative(
    ticker: str,
    bench: str,
    root: Path,
    entry_date: str,
    horizon_d: int,
) -> float | None:
    """SPY-relative forward return for `ticker` over `horizon_d` calendar days.

    Entry anchor: first close STRICTLY AFTER entry_date (next-bar fill — same
    as qledger FILL_NEXT_BAR). Exit: close on/before fill_ts + horizon_d.
    Returns None when series absent, maturity not reached, or price missing.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        # Make tz-aware (UTC) so comparisons with tz-aware index don't raise.
        ts0 = pd.Timestamp(entry_date, tz="UTC")

        subj = _close_series_safe(ticker, root)
        if subj is None:
            return None
        bench_s = _close_series_safe(bench, root)
        if bench_s is None:
            return None

        # Normalise index timezone to UTC for consistent comparisons.
        if subj.index.tzinfo is None:
            subj = subj.tz_localize("UTC")
        else:
            subj = subj.tz_convert("UTC")
        if bench_s.index.tzinfo is None:
            bench_s = bench_s.tz_localize("UTC")
        else:
            bench_s = bench_s.tz_convert("UTC")

        # next-bar fill for subject
        fwd_subj = subj[subj.index > ts0]
        if not len(fwd_subj):
            return None
        fill_ts = fwd_subj.index[0]
        e0 = float(fwd_subj.iloc[0])

        # same fill_ts for bench
        fwd_bench = bench_s[bench_s.index >= fill_ts]
        if not len(fwd_bench):
            return None
        b0 = float(fwd_bench.iloc[0])
        if not b0:
            return None

        end_ts = fill_ts + pd.Timedelta(days=horizon_d)
        # maturity check — exit day must be covered by BOTH series
        if subj.index.max() < end_ts or bench_s.index.max() < end_ts:
            return None

        w_subj = subj[subj.index <= end_ts]
        w_bench = bench_s[bench_s.index <= end_ts]
        if not len(w_subj) or not len(w_bench):
            return None

        e1 = float(w_subj.iloc[-1])
        b1 = float(w_bench.iloc[-1])
        if not e0:
            return None
        subj_ret = e1 / e0 - 1.0
        bench_ret = b1 / b0 - 1.0
        return round(subj_ret - bench_ret, 6)
    except Exception as exc:  # noqa: BLE001
        log.debug("_fwd_ret_relative(%s,%s): %s", ticker, entry_date, exc)
        return None


# --------------------------------------------------------------------------- #
# Wilson CI
# --------------------------------------------------------------------------- #
def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """(lower, upper) of Wilson 95% CI. Both None when n == 0."""
    if n <= 0:
        return None, None
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)
    low = round((centre - margin) / denom, 6)
    high = round((centre + margin) / denom, 6)
    return low, high


def _verdict(n_graded: int, w_low: float | None, w_high: float | None) -> str:
    """Verdict per pinned contract rules."""
    if n_graded < VERDICT_N_GRADED_MIN:
        return "insufficient"
    if w_low is not None and w_low > 0.50:
        return "candidate"
    if w_high is not None and w_high < 0.50:
        return "no_edge"
    return "context_only"


# --------------------------------------------------------------------------- #
# Grade events: aggregate per (event_type, direction)
# --------------------------------------------------------------------------- #
def _grade_events(df, root: Path, today: date) -> list[dict]:
    """Compute per-(event_type, direction) calibration rows.

    Returns list of class dicts matching the contract schema.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        return []

    # Group rows into (event_type, direction) buckets
    # For each event with tickers, compute 5d and 21d relative returns
    # n = total events logged; n_graded = events with >= 1 ticker and matured price

    # accumulator: key=(event_type, direction) -> {n, returns_5d:[], returns_21d:[]}
    from collections import defaultdict  # noqa: PLC0415
    acc: dict = defaultdict(lambda: {"n": 0, "rets_5d": [], "rets_21d": []})

    for _, row in df.iterrows():
        et = str(row.get("event_type") or "")
        direction = str(row.get("direction") or "informational")
        if not et:
            continue
        key = (et, direction)
        acc[key]["n"] += 1

        tickers_raw = row.get("tickers")
        if not tickers_raw:
            continue
        try:
            tickers = json.loads(str(tickers_raw))
        except Exception:  # noqa: BLE001
            continue
        if not tickers:
            continue

        first_seen = str(row.get("first_seen_utc") or row.get("seendate") or "")
        if not first_seen:
            continue
        try:
            # Use UTC-aware Timestamp then take .date() so entry_date is a plain ISO string.
            ts_seen = pd.Timestamp(first_seen)
            if ts_seen.tzinfo is None:
                ts_seen = ts_seen.tz_localize("UTC")
            entry_date = ts_seen.date().isoformat()
        except Exception:  # noqa: BLE001
            continue

        # Collect returns per ticker; take the mean across tickers for this event
        r5_vals: list[float] = []
        r21_vals: list[float] = []
        for t in tickers:
            r5 = _fwd_ret_relative(t, SPY, root, entry_date, 5)
            if r5 is not None:
                r5_vals.append(r5)
            r21 = _fwd_ret_relative(t, SPY, root, entry_date, 21)
            if r21 is not None:
                r21_vals.append(r21)

        if r5_vals:
            acc[key]["rets_5d"].append(float(sum(r5_vals) / len(r5_vals)))
        if r21_vals:
            acc[key]["rets_21d"].append(float(sum(r21_vals) / len(r21_vals)))

    result: list[dict] = []
    for (et, direction), agg in sorted(acc.items()):
        n = int(agg["n"])
        rets_5d: list[float] = agg["rets_5d"]
        rets_21d: list[float] = agg["rets_21d"]
        n_graded = int(len(rets_5d))  # graded = has at least one 5d return

        # Hit rate: sign convention per direction
        # bullish → positive rel-return is a hit; bearish → negative is a hit
        # mixed/informational → no directional grading
        hits_5d = 0
        if direction in ("bullish", "bearish"):
            for r in rets_5d:
                if direction == "bullish" and r > 0:
                    hits_5d += 1
                elif direction == "bearish" and r < 0:
                    hits_5d += 1

        # 21d hits (same logic; n_graded_21 may differ from n_graded_5)
        hits_21d = 0
        n_graded_21 = int(len(rets_21d))
        if direction in ("bullish", "bearish"):
            for r in rets_21d:
                if direction == "bullish" and r > 0:
                    hits_21d += 1
                elif direction == "bearish" and r < 0:
                    hits_21d += 1

        # Use n_graded (5d) as the primary graded count for verdict
        hit_5d: float | None = float(hits_5d / n_graded) if n_graded > 0 else None
        hit_21d: float | None = float(hits_21d / n_graded_21) if n_graded_21 > 0 else None
        avg_5d: float | None = float(sum(rets_5d) / n_graded) if n_graded > 0 else None
        avg_21d: float | None = float(sum(rets_21d) / n_graded_21) if n_graded_21 > 0 else None
        w_low_5d, w_high_5d = (
            _wilson_ci(hits_5d, n_graded)
            if direction in ("bullish", "bearish") and n_graded > 0
            else (None, None)
        )

        result.append({
            "event_type": str(et),
            "direction": str(direction),
            "n": n,
            "n_graded": n_graded,
            "hit_5d": hit_5d,
            "hit_21d": hit_21d,
            "avg_rel_5d": avg_5d,
            "avg_rel_21d": avg_21d,
            "wilson_low_5d": w_low_5d,
            "wilson_high_5d": w_high_5d,
            "verdict": _verdict(n_graded, w_low_5d, w_high_5d),
        })

    return result


# --------------------------------------------------------------------------- #
# Grade reject sample: aggregate per reason
# --------------------------------------------------------------------------- #
def _grade_rejects(df, root: Path) -> dict:
    """Grade the reject sample by reason; return reject_audit dict."""
    try:
        from collections import defaultdict  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        return {"n_sampled": 0, "n_graded": 0, "classes": []}

    n_sampled = int(len(df))
    acc: dict = defaultdict(lambda: {"rets_21d": []})

    for _, row in df.iterrows():
        reason = str(row.get("reason") or "unknown")
        tickers_raw = row.get("tickers")
        if not tickers_raw:
            continue
        try:
            tickers = json.loads(str(tickers_raw))
        except Exception:  # noqa: BLE001
            continue
        if not tickers:
            continue
        first_seen = str(row.get("first_seen_utc") or row.get("seendate") or "")
        if not first_seen:
            continue
        try:
            ts_seen = pd.Timestamp(first_seen)
            if ts_seen.tzinfo is None:
                ts_seen = ts_seen.tz_localize("UTC")
            entry_date = ts_seen.date().isoformat()
        except Exception:  # noqa: BLE001
            continue
        r21_vals: list[float] = []
        for t in tickers:
            r21 = _fwd_ret_relative(t, SPY, root, entry_date, 21)
            if r21 is not None:
                r21_vals.append(r21)
        if r21_vals:
            acc[reason]["rets_21d"].append(float(sum(r21_vals) / len(r21_vals)))

    classes: list[dict] = []
    n_graded_total = 0
    for reason in sorted(acc):
        rets = acc[reason]["rets_21d"]
        ng = int(len(rets))
        n_graded_total += ng
        avg = float(sum(rets) / ng) if ng > 0 else None
        note = (
            "Rejected headlines with tickers graded for SPY-relative 21d return. "
            "Positive avg_rel_21d means rejected items had positive forward returns — "
            "a high rate of that would indicate the reject filter is too aggressive."
            if ng > 0 else
            "No tickers available for grading in this reject class."
        )
        classes.append({
            "reason": str(reason),
            "n_graded": ng,
            "avg_rel_21d": avg,
            "note": note,
        })

    return {
        "n_sampled": n_sampled,
        "n_graded": n_graded_total,
        "classes": classes,
    }


# --------------------------------------------------------------------------- #
# Artifact builder
# --------------------------------------------------------------------------- #
def build_calibration(
    root: Path | str | None = None,
    today: date | None = None,
) -> dict:
    """Build the calibration artifact dict (does not write; caller writes).

    Always returns a valid contract-shaped dict:
      - On empty/missing event_log: n_events_logged=0, all classes=[], verdicts=insufficient.
      - On any partial failure: degrades gracefully, never raises.

    NUMPY-CAST GUARD: every numeric value is explicitly cast to int()/float()
    before being placed into the return dict. No numpy scalar can leak through.
    """
    root_p = _root(root)
    today_dt = today or date.today()
    asof_iso = today_dt.isoformat()

    # Defaults — valid empty artifact
    artifact: dict = {
        "schema": SCHEMA,
        "is_context_only": True,
        "asof": asof_iso,
        "n_events_logged": 0,
        "n_events_graded": 0,
        "classes": [],
        "reject_audit": {"n_sampled": 0, "n_graded": 0, "classes": []},
    }

    try:
        from engine.news_event_ledger import (  # noqa: PLC0415
            load_event_log,
            load_reject_sample,
        )

        ev_df = load_event_log(root_p)
        if ev_df is None or len(ev_df) == 0:
            return artifact  # valid empty state — Day-1 reality

        n_logged = int(len(ev_df))
        artifact["n_events_logged"] = n_logged

        # Grade events
        classes = _grade_events(ev_df, root_p, today_dt)
        # Cast all numerics to native Python types (numpy-cast guard)
        classes = [_cast_class_row(c) for c in classes]
        n_graded = int(sum(c["n_graded"] for c in classes))
        artifact["n_events_graded"] = n_graded
        artifact["classes"] = classes

        # Grade reject sample
        rej_df = load_reject_sample(root_p)
        if rej_df is not None and len(rej_df) > 0:
            reject_audit = _grade_rejects(rej_df, root_p)
            reject_audit = _cast_reject_audit(reject_audit)
            artifact["reject_audit"] = reject_audit

    except Exception as exc:  # noqa: BLE001 — degrade-never-raise
        log.warning("build_calibration degraded (%s): %s", type(exc).__name__, exc)
        # Return the (possibly partial) artifact as built so far

    return artifact


def _cast_class_row(c: dict) -> dict:
    """Cast all numeric values in a class row to native Python types."""
    return {
        "event_type": str(c.get("event_type") or ""),
        "direction": str(c.get("direction") or ""),
        "n": int(c.get("n") or 0),
        "n_graded": int(c.get("n_graded") or 0),
        "hit_5d": float(c["hit_5d"]) if c.get("hit_5d") is not None else None,
        "hit_21d": float(c["hit_21d"]) if c.get("hit_21d") is not None else None,
        "avg_rel_5d": float(c["avg_rel_5d"]) if c.get("avg_rel_5d") is not None else None,
        "avg_rel_21d": float(c["avg_rel_21d"]) if c.get("avg_rel_21d") is not None else None,
        "wilson_low_5d": float(c["wilson_low_5d"]) if c.get("wilson_low_5d") is not None else None,
        "wilson_high_5d": float(c["wilson_high_5d"]) if c.get("wilson_high_5d") is not None else None,
        "verdict": str(c.get("verdict") or "insufficient"),
    }


def _cast_reject_audit(ra: dict) -> dict:
    """Cast all numeric values in reject_audit to native Python types."""
    classes = []
    for item in ra.get("classes") or []:
        avg = item.get("avg_rel_21d")
        classes.append({
            "reason": str(item.get("reason") or ""),
            "n_graded": int(item.get("n_graded") or 0),
            "avg_rel_21d": float(avg) if avg is not None else None,
            "note": str(item.get("note") or ""),
        })
    return {
        "n_sampled": int(ra.get("n_sampled") or 0),
        "n_graded": int(ra.get("n_graded") or 0),
        "classes": classes,
    }


# --------------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------------- #
def emit_calibration(
    root: Path | str | None = None,
    today: date | None = None,
) -> dict:
    """Build and write site/news/calibration.json. Returns the payload."""
    root_p = _root(root)
    artifact = build_calibration(root_p, today)
    out = root_p.joinpath(*_OUTPUT_REL)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Final safety: json.dumps with NO default= — any remaining numpy scalar
    # will raise TypeError here before it silently corrupts the file.
    text = json.dumps(artifact, ensure_ascii=False, indent=2)
    out.write_text(text, encoding="utf-8")
    log.info(
        "calibration.json: n_events_logged=%d n_events_graded=%d classes=%d",
        artifact.get("n_events_logged", 0),
        artifact.get("n_events_graded", 0),
        len(artifact.get("classes") or []),
    )
    return artifact


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Grade news events and emit site/news/calibration.json.")
    p.add_argument("--root", default=None, help="Repo root (default: lib.config.ROOT).")
    p.add_argument("--dry-run", action="store_true",
                   help="Build artifact but do not write to disk; print to stdout.")
    p.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    today_dt = date.fromisoformat(args.today) if args.today else None
    if args.dry_run:
        artifact = build_calibration(root=args.root, today=today_dt)
        print(json.dumps(artifact, indent=2))
        return 0
    emit_calibration(root=args.root, today=today_dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
