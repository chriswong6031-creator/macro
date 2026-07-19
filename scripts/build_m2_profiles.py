"""scripts/build_m2_profiles.py — Off-render artifact writer for M2 indicator levels.

Computes per-ticker VWAP / AVWAP / Volume-Profile cache and writes
site/factordata/m2_profiles.json (or --out PATH).

HONESTY CONTRACT
----------------
- Display-tier context only.  Daily-bar approximation over typical price
  (H+L+C)/3 — not intraday-true VWAP.
- SURVIVORSHIP-BIASED universe (mega-cap survivors).
- All indicator math lives in engine.indicators_m2; this module never
  re-implements it.
- No 'validated' claims in any user-facing string (CI-guarded).
- Nulls are printed, not hidden.

USAGE
-----
    python scripts/build_m2_profiles.py [--out PATH] [--force]

    --out PATH   write output here (default: site/factordata/m2_profiles.json)
    --force      ignore cache (recompute unconditionally)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from any cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.chdir(_REPO_ROOT)  # engine modules that do relative data/ reads need this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_m2_profiles")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT = _REPO_ROOT / "site" / "factordata" / "m2_profiles.json"
_VERSION = "m2.v1"
_MIN_BARS = 140
_MAX_AGE_D = 3
_PROFILE_WINDOW = 126
_PROFILE_BINS = 24
_AVWAP_LOOKBACK = 63   # earnings proxy lookback
_LOW_52W_BARS = 252    # trailing bars for 52-week low anchor


# ---------------------------------------------------------------------------
# Pure helpers — these accept indicator fn outputs as inputs so they can be
# tested in isolation without engine.indicators_m2 being importable.
# ---------------------------------------------------------------------------

def _fingerprint(max_date: str, sorted_tickers: list[str], version: str) -> str:
    """Stable 16-char sha1 fingerprint over (max_date, sorted ticker list, version).

    Identical inputs always produce the same fingerprint; changing any
    component changes it.
    """
    src = f"{max_date}|{'|'.join(sorted_tickers)}|{version}"
    return hashlib.sha1(src.encode()).hexdigest()[:16]


def should_recompute(
    existing_meta: dict | None,
    fingerprint: str,
    now: datetime,
    max_age_d: int = _MAX_AGE_D,
    force: bool = False,
) -> bool:
    """Return True when the artifact must be regenerated.

    Cache HIT (returns False) when all of:
      - not force
      - existing_meta is not None
      - existing_meta["fingerprint"] matches fingerprint
      - age in days since existing_meta["computed_at"] <= max_age_d

    Everything else returns True (recompute).
    """
    if force:
        return True
    if not existing_meta:
        return True
    if existing_meta.get("fingerprint") != fingerprint:
        return True
    computed_at_str = existing_meta.get("computed_at")
    if not computed_at_str:
        return True
    try:
        computed_at = datetime.fromisoformat(computed_at_str)
        # normalise both to UTC for comparison
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now_utc = now.replace(tzinfo=timezone.utc)
        else:
            now_utc = now
        age_d = (now_utc - computed_at).total_seconds() / 86400
        return age_d > max_age_d
    except (ValueError, TypeError):
        return True


def _sessions_held(close_series, avwap_series) -> int:
    """Count consecutive most-recent bars where close > avwap (run-length from tail).

    Both inputs are pd.Series aligned by index.  Returns 0 when series are
    empty, avwap has no valid values, or the last bar is not above.

    COUNTING CONVENTION (vs the adjacent ``sessions_since`` field): this is an
    INCLUSIVE bar count (the anchor bar itself can be bar #1 when its close sits
    above its own TP-seeded AVWAP), while ``sessions_since`` is the EXCLUSIVE
    gap ``len(df) - 1 - anchor_pos``.  ``sessions_held`` may therefore exceed
    ``sessions_since`` by exactly 1 — consumers must not treat the pair as
    same-base counts.
    """
    import pandas as pd  # noqa: PLC0415 — called at runtime only

    if close_series is None or avwap_series is None:
        return 0
    c = pd.Series(close_series).dropna()
    a = pd.Series(avwap_series).dropna()
    if c.empty or a.empty:
        return 0
    # align on common index labels
    common = c.index.intersection(a.index)
    if common.empty:
        return 0
    c_aligned = c.loc[common]
    a_aligned = a.loc[common]
    above = (c_aligned > a_aligned).values
    # count from the right
    count = 0
    for v in reversed(above):
        if v:
            count += 1
        else:
            break
    return count


def _round_or_null(val, ndigits: int = 4):
    """Return rounded float or None when val is NaN/None."""
    if val is None:
        return None
    try:
        import math  # noqa: PLC0415
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), ndigits)
    except (TypeError, ValueError):
        return None


def _build_ticker_record(
    df,                     # pd.DataFrame — OHLCV, DatetimeIndex, min _MIN_BARS rows
    *,
    avwap_fn,               # anchored_vwap(df, anchor) -> pd.Series
    earnings_proxy_fn,      # earnings_proxy_anchor(df, lookback=63) -> int|None
    week_avwap_fn,          # week_anchored_vwap(df) -> pd.Series
    profile_fn,             # volume_profile(df, window=126, bins=24) -> dict|None
) -> dict[str, Any]:
    """Build one ticker's record dict, calling the injected indicator fns.

    The indicator functions are dependency-injected (not imported) so this
    aggregator is testable with lightweight stubs.  All downstream math assumes
    ascending daily bars, so a non-monotonic index is sorted defensively here —
    otherwise ``df.index[-1]`` / ``.iloc[-1]`` would report the wrong "last" bar.
    """
    import pandas as pd  # noqa: PLC0415

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    last_close = float(df["close"].iloc[-1])
    as_of = str(df.index[-1].date())

    # --- week_anchored_vwap ---
    try:
        vwap_w_series = week_avwap_fn(df)
        vwap_w = _round_or_null(
            float(vwap_w_series.iloc[-1]) if not vwap_w_series.empty else None
        )
    except Exception:  # noqa: BLE001
        vwap_w = None

    # --- volume_profile ---
    profile_rec: dict | None = None
    try:
        prof = profile_fn(df, window=_PROFILE_WINDOW, bins=_PROFILE_BINS)
        if prof is not None:
            poc = prof["poc"]
            va_low = prof["va_low"]
            va_high = prof["va_high"]
            poc_dist_pct = _round_or_null((last_close / poc - 1) * 100, 2) if poc else None
            in_va = (
                va_low <= last_close <= va_high
                if (va_low is not None and va_high is not None)
                else None
            )
            profile_rec = {
                "poc": _round_or_null(poc),
                "va_low": _round_or_null(va_low),
                "va_high": _round_or_null(va_high),
                "window": _PROFILE_WINDOW,
                "poc_dist_pct": poc_dist_pct,
                "in_value_area": bool(in_va) if in_va is not None else None,
            }
    except Exception:  # noqa: BLE001
        profile_rec = None

    # --- avwap anchors ---
    avwap_rec: dict[str, Any] = {}

    # earnings proxy anchor
    try:
        ep_idx = earnings_proxy_fn(df, lookback=_AVWAP_LOOKBACK)
        if ep_idx is not None:
            ep_series = avwap_fn(df, ep_idx)
            ep_value = _round_or_null(float(ep_series.iloc[-1]))
            ep_anchor_date = str(df.index[ep_idx].date())
            sessions_since = int(len(df) - 1 - ep_idx)
            held = _sessions_held(df["close"], ep_series)
            dist_pct = (
                _round_or_null((last_close / float(ep_series.iloc[-1]) - 1) * 100, 2)
                if ep_value is not None
                else None
            )
            avwap_rec["earnings_proxy"] = {
                "value": ep_value,
                "anchor_date": ep_anchor_date,
                "sessions_since": sessions_since,
                "sessions_held": held,
                "dist_pct": dist_pct,
            }
        else:
            avwap_rec["earnings_proxy"] = {
                "value": None,
                "anchor_date": None,
                "sessions_since": None,
                "sessions_held": 0,
                "dist_pct": None,
            }
    except Exception:  # noqa: BLE001
        avwap_rec["earnings_proxy"] = {
            "value": None,
            "anchor_date": None,
            "sessions_since": None,
            "sessions_held": 0,
            "dist_pct": None,
        }

    # YTD anchor — first session of current calendar year
    try:
        current_year = df.index[-1].year
        ytd_mask = df.index.year == current_year
        ytd_start_pos = int(ytd_mask.argmax())  # first True index
        if ytd_mask.any():
            ytd_series = avwap_fn(df, ytd_start_pos)
            ytd_val = _round_or_null(float(ytd_series.iloc[-1]))
            ytd_anchor_date = str(df.index[ytd_start_pos].date())
            ytd_dist = (
                _round_or_null((last_close / float(ytd_series.iloc[-1]) - 1) * 100, 2)
                if ytd_val is not None
                else None
            )
            avwap_rec["ytd"] = {
                "value": ytd_val,
                "anchor_date": ytd_anchor_date,
                "dist_pct": ytd_dist,
            }
        else:
            avwap_rec["ytd"] = {"value": None, "anchor_date": None, "dist_pct": None}
    except Exception:  # noqa: BLE001
        avwap_rec["ytd"] = {"value": None, "anchor_date": None, "dist_pct": None}

    # 52-week low anchor — date of min low over trailing _LOW_52W_BARS bars
    try:
        tail_df = df.tail(_LOW_52W_BARS)
        min_low_pos_in_tail = int(tail_df["low"].values.argmin())
        # map to position in full df
        low_pos_full = int(len(df) - len(tail_df) + min_low_pos_in_tail)
        low_series = avwap_fn(df, low_pos_full)
        low_val = _round_or_null(float(low_series.iloc[-1]))
        low_anchor_date = str(df.index[low_pos_full].date())
        low_dist = (
            _round_or_null((last_close / float(low_series.iloc[-1]) - 1) * 100, 2)
            if low_val is not None
            else None
        )
        avwap_rec["low_52w"] = {
            "value": low_val,
            "anchor_date": low_anchor_date,
            "dist_pct": low_dist,
        }
    except Exception:  # noqa: BLE001
        avwap_rec["low_52w"] = {"value": None, "anchor_date": None, "dist_pct": None}

    return {
        "as_of": as_of,
        "close": _round_or_null(last_close),
        "vwap_w": vwap_w,
        "profile": profile_rec,
        "avwap": avwap_rec,
    }


# ---------------------------------------------------------------------------
# Main entry point (full-universe run; gated behind __main__)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build M2 VWAP/volume-profile level cache artifact."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Output path (default: site/factordata/m2_profiles.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cache and recompute unconditionally.",
    )
    args = parser.parse_args(argv)

    out_path: Path = args.out
    t0 = time.monotonic()

    # --- Import engine modules (deferred so tests can monkeypatch) ---
    from engine import lab  # noqa: PLC0415
    from engine.indicators_m2 import (  # noqa: PLC0415
        anchored_vwap,
        earnings_proxy_anchor,
        week_anchored_vwap,
        volume_profile,
    )

    # --- Load universe ---
    log.info("Loading universe …")
    universe: dict = lab.load("ALL", group="stocks")
    tickers_sorted = sorted(universe.keys())
    universe_n = len(tickers_sorted)
    log.info("Universe: %d tickers", universe_n)

    # --- Compute max common as-of date ---
    import pandas as pd  # noqa: PLC0415

    max_dates = []
    for t, df in universe.items():
        if df is not None and not df.empty:
            max_dates.append(str(df.index.max().date()))
    if not max_dates:
        log.error("Universe is empty — nothing to compute.")
        return 1
    max_date = max(max_dates)

    # --- Fingerprint ---
    fp = _fingerprint(max_date, tickers_sorted, _VERSION)
    log.info("Fingerprint: %s (max_date=%s, n=%d)", fp, max_date, universe_n)

    # --- Cache check ---
    existing_meta: dict | None = None
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
            existing_meta = existing.get("meta")
        except Exception:  # noqa: BLE001
            pass

    now = datetime.now(timezone.utc)
    if not should_recompute(existing_meta, fp, now, max_age_d=_MAX_AGE_D, force=args.force):
        print(f"[build_m2_profiles] cache hit (fp={fp}) — skipping recompute")
        return 0

    # --- Compute per-ticker records ---
    # Two failure modes are counted separately: `skipped` (frame absent or below
    # the minimum bar count — an expected, benign exclusion) and `failed`
    # (record build raised — a genuine corrupt-frame error worth surfacing). A
    # single corrupt frame must never abort the artifact.
    log.info("Computing per-ticker M2 records …")
    profiles: dict[str, Any] = {}
    skipped = 0
    failed = 0

    for ticker in tickers_sorted:
        df = universe.get(ticker)
        if df is None or len(df) < _MIN_BARS:
            skipped += 1
            log.debug("skip %s: %d bars < %d", ticker, len(df) if df is not None else 0, _MIN_BARS)
            continue
        try:
            rec = _build_ticker_record(
                df,
                avwap_fn=anchored_vwap,
                earnings_proxy_fn=earnings_proxy_anchor,
                week_avwap_fn=week_anchored_vwap,
                profile_fn=volume_profile,
            )
            profiles[ticker] = rec
        except Exception as exc:  # noqa: BLE001
            log.warning("fail %s: record build raised: %s", ticker, exc)
            failed += 1

    elapsed = time.monotonic() - t0
    computed_n = len(profiles)
    log.info(
        "Computed %d tickers, skipped %d (too-short), failed %d (build error) in %.1fs",
        computed_n, skipped, failed, elapsed,
    )

    # --- Write artifact ---
    artifact = {
        "meta": {
            "fingerprint": fp,
            "computed_at": now.isoformat(),
            "max_date": max_date,
            "version": _VERSION,
            "universe_n": universe_n,
            "computed_n": computed_n,
            "skipped_n": skipped,
            "failed_n": failed,
            "note": (
                "Daily-bar approximation over typical price (H+L+C)/3 — "
                "not intraday-true VWAP. Display-tier context; not a signal."
            ),
        },
        "profiles": dict(sorted(profiles.items())),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1, sort_keys=False))
    file_kb = out_path.stat().st_size / 1024

    print(
        f"\n[build_m2_profiles] universe={universe_n} | computed={computed_n} | "
        f"skipped={skipped} | failed={failed} | {elapsed:.1f}s | {file_kb:.1f}KB"
    )
    print(f"  Output: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
