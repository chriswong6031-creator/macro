"""engine/neuralweb/bottom_sensors.py — Bottom-sensor envelope for the US board.

Amendment 1, Lane B0, PR-1.  Display-only — is_display_only=True.
labels_version=labels_v1.  Ranked nothing, gates nothing, alerts nothing.

Source-of-truth document: research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md §C2.

Bind-first law (Amendment §C2 ⟦RV⟧):
  Every field that an existing engine already emits is BOUND read-only from its
  authoritative artifact.  Exactly two new computed columns are introduced here:
    - dist_21d_low_pct  : pct distance of current close above rolling 21-day low
    - dist_126d_high_pct: pct distance of current close below rolling 126-day high
  These are the ONLY rolling operations on price series in this module.

Field sources (source_artifacts column in output):
  trigger_tier / trigger_age_ticks  → site/factordata/signal_gate.json
  coiled / star / coiled_fire       → site/factordata/us_standouts.json (buy rows)
  donor_state                       → site/factordata/us_standouts.json (.donor)
  entry_quality_band                → site/factordata/us_standouts.json (conviction.potential.band)
  squeeze_state                     → site/factordata/us_standouts.json (conviction.vol_squeeze.state)
  hold_state (BIND from hold.py)    → site/factordata/us_standouts.json (.hold)
  knife (for KNIFE_RISK fallback)   → site/factordata/us_standouts.json (conviction.alignment.knife)
  bars_to_cross                     → site/factordata/signal_gate.json and us_standouts
  earnings_next_date/days_to        → data/earnings/earnings.parquet
  dist_21d_low_pct                  → computed here (rolling 21d; close series from data/stocks/*.parquet)
  dist_126d_high_pct                → computed here (rolling 126d; close series from data/stocks/*.parquet)
  rs_repair_state                   → stamped unavailable (W0.4 of #1302 not yet shipped)
  sponsorship_state                 → stamped unavailable (B2 lane not yet complete)

KNIFE condition binding law (Amendment §C2):
  The _ALIGN_KNIFE_BLOCK constant (cycles.py: _ALIGN_KNIFE_BLOCK = 0.7) defines the
  HARD-exclude threshold.  When the alignment.knife field is available from us_standouts
  (bound from scripts/build_stock_library.py ~2030 where it is computed via washout()),
  we bind it.  When absent (name not in us_standouts), we fall back to dist_126d_high_pct
  >= 15% AND dist_21d_low_pct < 0 (close below 21d low), exactly per the Amendment.

Never raises publicly.  All failures degrade gracefully (return empty frame / partial rows).
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Labels version (frozen in this PR) ────────────────────────────────────────
LABELS_VERSION = "labels_v1"
IS_DISPLAY_ONLY = True
REGION = "US"

# ── Path helpers ─────────────────────────────────────────────────────────────
def _repo_root() -> Path:
    """Repo root: three levels up from engine/neuralweb/bottom_sensors.py."""
    return Path(__file__).resolve().parent.parent.parent


def _site_factordata(root: Path) -> Path:
    return root / "site" / "factordata"


def _data_neuralweb(root: Path) -> Path:
    return root / "data" / "neuralweb"


def _site_neuralwebdata(root: Path) -> Path:
    return root / "site" / "neuralwebdata"


def _data_stocks(root: Path) -> Path:
    return root / "data" / "stocks"


def _data_earnings(root: Path) -> Path:
    return root / "data" / "earnings" / "earnings.parquet"


# ── Knife threshold (bind from cycles.py; never reimport to avoid circular) ───
_ALIGN_KNIFE_BLOCK = 0.7   # mirrors engine/cycles.py:1892

# ── EVENT_BLACKOUT window (per Amendment §C2 overlay rule) ───────────────────
_BLACKOUT_DAYS = 3  # earnings within <= 3 trading days


# ── Source loading ─────────────────────────────────────────────────────────────

def _load_signal_gate(root: Path) -> tuple[dict[str, dict], str]:
    """Load site/factordata/signal_gate.json.
    Returns (verdicts_dict, as_of_str).  Never raises (returns {}, "" on failure).
    """
    path = _site_factordata(root) / "signal_gate.json"
    try:
        with open(path) as fh:
            raw = json.load(fh)
        verdicts = raw.get("verdicts") or {}
        as_of = raw.get("as_of") or ""
        return verdicts, str(as_of)
    except Exception as exc:  # noqa: BLE001
        log.warning("signal_gate.json load failed: %s", exc)
        return {}, ""


def _load_us_standouts(root: Path) -> dict:
    """Load site/factordata/us_standouts.json.
    Returns the full dict (with 'buy', 'watch', 'laggards', 'donor').
    Never raises (returns {} on failure).
    """
    path = _site_factordata(root) / "us_standouts.json"
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log.warning("us_standouts.json load failed: %s", exc)
        return {}


def _load_earnings(root: Path) -> pd.DataFrame:
    """Load data/earnings/earnings.parquet.
    Index = ticker.  Columns: next_date (str), as_of (str), etc.
    Never raises (returns empty DataFrame on failure).
    """
    path = _data_earnings(root)
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings.parquet load failed: %s", exc)
        return pd.DataFrame()


def _load_close(root: Path, ticker: str) -> pd.Series | None:
    """Load close series for a ticker from data/stocks/<TICKER>.parquet.
    Returns daily close as a DatetimeIndex pd.Series, or None on failure.
    """
    safe = ticker.replace("/", "_").replace("=", "_")
    path = _data_stocks(root) / f"{safe}.parquet"
    try:
        df = pd.read_parquet(path)
        c = df["close"] if "close" in df.columns else df.iloc[:, 0]
        c = c.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        c = c.sort_index()
        return c
    except Exception:  # noqa: BLE001
        return None


# ── Rolling distance columns (the ONLY two new computed columns) ──────────────

def _dist_21d_low_pct(close: pd.Series) -> float | None:
    """Pct distance of today's close above its 21-bar rolling low.
    > 0 means above the 21d low (the lower the number the closer to the low).
    Returns None when insufficient data.
    """
    if close is None or len(close) < 21:
        return None
    roll_min = float(close.rolling(21).min().iloc[-1])
    last_close = float(close.iloc[-1])
    if roll_min <= 0 or np.isnan(roll_min):
        return None
    return round((last_close / roll_min - 1.0) * 100.0, 2)


def _dist_126d_high_pct(close: pd.Series) -> float | None:
    """Pct distance of today's close below its 126-bar rolling high (negative or zero).
    0 = at the high; -15 = 15% below the high.
    Returns None when insufficient data.
    """
    if close is None or len(close) < 126:
        return None
    roll_max = float(close.rolling(126).max().iloc[-1])
    last_close = float(close.iloc[-1])
    if roll_max <= 0 or np.isnan(roll_max):
        return None
    return round((last_close / roll_max - 1.0) * 100.0, 2)


# ── Earnings freshness ─────────────────────────────────────────────────────────

def _earnings_info(
    ticker: str,
    earnings_df: pd.DataFrame,
    today: datetime.date,
) -> tuple[str | None, int | None, bool]:
    """Return (next_date_str, days_to, is_blackout) for a ticker.

    Per-row fresh rule (Amendment §C2, masterplan §3 F1):
      - Drop passed dates (next_date <= today).
      - Blackout if days_to <= _BLACKOUT_DAYS.

    Returns (None, None, False) when data absent.
    """
    if earnings_df.empty or ticker not in earnings_df.index:
        return None, None, False
    try:
        row = earnings_df.loc[ticker]
        nd = row.get("next_date") if isinstance(row, pd.Series) else None
        if nd is None:
            return None, None, False
        next_dt = pd.to_datetime(nd).date()
        if next_dt <= today:
            return None, None, False
        days = (next_dt - today).days
        blackout = days <= _BLACKOUT_DAYS
        return str(next_dt), int(days), blackout
    except Exception:  # noqa: BLE001
        return None, None, False


# ── Label computation (frozen labels_v1) ──────────────────────────────────────

def _classify_labels_v1(
    *,
    hold_state: str | None,
    hold_days_basing: int | None,
    hold_ret: float | None,
    trigger_tier: str | None,
    ticks: int | None,
    coiled: bool,
    dist_21d_low: float | None,
    dist_126d_high: float | None,
    bars_to_cross: float | None,
    knife_score: float | None,
    knife_available: bool,
) -> str:
    """Frozen labels_v1 decision table (Amendment §C2).

    Precedence top-down; returns state string.
    Inputs with value None mean field unavailable for that name.
    """
    # ── 1. HOLD_LAUNCHED (highest precedence) ────────────────────────────────
    # BIND: hold["state"] == "launched" (engine/hold.py:188-195)
    if hold_state == "launched":
        return "HOLD_LAUNCHED"

    # ── helpers ──────────────────────────────────────────────────────────────
    has_fresh_tier = (
        trigger_tier in ("T1", "T2", "T3")
        and ticks is not None
        and ticks <= 2
    )
    # dist_21d_low: > 0 means above the low.  <= 12 means within 12% of low.
    # "dist_21d_low <= 12%" in spec means pct distance above 21d low is <=12.
    within_12_of_low = (
        dist_21d_low is not None and dist_21d_low <= 12.0
    )
    drawdown_15_from_126d = (
        dist_126d_high is not None and dist_126d_high <= -15.0
    )

    # ── 2. FRESH_FIRE_DURABLE_CAND ───────────────────────────────────────────
    # fresh T1-T3 (ticks <= 2) AND COILED AND dist_21d_low <= 12%
    if has_fresh_tier and coiled and within_12_of_low:
        return "FRESH_FIRE_DURABLE_CAND"

    # ── 3. FRESH_FIRE_TACTICAL ───────────────────────────────────────────────
    # fresh T1-T3 (ticks <= 2) AND NOT COILED AND dist_21d_low <= 12%
    if has_fresh_tier and not coiled and within_12_of_low:
        return "FRESH_FIRE_TACTICAL"

    # ── 4. CHASE_RISK ─────────────────────────────────────────────────────────
    # T1-T3 present AND (ticks > 2 OR dist_21d_low > 12%) AND not HOLD_LAUNCHED
    has_any_tier = trigger_tier in ("T1", "T2", "T3")
    if has_any_tier:
        ticks_stale = ticks is None or ticks > 2
        dist_far = dist_21d_low is None or dist_21d_low > 12.0
        if ticks_stale or dist_far:
            return "CHASE_RISK"

    # ── 5. DEAD_MONEY_RISK ────────────────────────────────────────────────────
    # BIND: hold state intact/basing, days_basing 15-40, abs(ret_since_take) < 4%
    # Where hold fields absent for a name, stamp unavailable (not recomputed).
    if hold_state in ("intact",):
        if (
            hold_days_basing is not None
            and 15 <= hold_days_basing <= 40
            and hold_ret is not None
            and abs(hold_ret) < 4.0
        ):
            return "DEAD_MONEY_RISK"

    # ── 6. EARLY_WATCH ────────────────────────────────────────────────────────
    # drawdown >= 15% from 126d high AND bars_to_cross <= 2 (T3/T4 rows only)
    # AND no fresh T1-T3.  The 2D hist-curl arm is DEFERRED until engine emits it.
    if (
        not has_fresh_tier
        and drawdown_15_from_126d
        and bars_to_cross is not None
        and bars_to_cross <= 2.0
    ):
        return "EARLY_WATCH"

    # ── 7. KNIFE_RISK ─────────────────────────────────────────────────────────
    # BIND: the existing _ALIGN_KNIFE_BLOCK condition when knife_available.
    # Fallback: drawdown >= 15% from 126d high AND close < prior 21d rolling low
    # (dist_21d_low <= 0) AND no fresh tier.
    if not has_fresh_tier:
        if knife_available and knife_score is not None and knife_score >= _ALIGN_KNIFE_BLOCK:
            return "KNIFE_RISK"
        if not knife_available:
            # fallback to dist-based rule when knife not available
            below_21d_low = dist_21d_low is not None and dist_21d_low <= 0.0
            if drawdown_15_from_126d and below_21d_low:
                return "KNIFE_RISK"

    # ── 8. WATCH (default) ────────────────────────────────────────────────────
    return "WATCH"


# ── Build one row ──────────────────────────────────────────────────────────────

def _build_row(
    ticker: str,
    sg_verdict: dict,
    standout_row: dict | None,
    standout_donor: dict | None,
    earnings_df: pd.DataFrame,
    today: datetime.date,
    root: Path,
) -> dict[str, Any]:
    """Assemble one bottom-sensor row for a ticker.

    sg_verdict  : from signal_gate.json['verdicts'][ticker]
    standout_row: the buy/watch/laggard row from us_standouts.json (may be None)
    standout_donor: the top-level donor dict from us_standouts.json (board-level)
    """
    row: dict[str, Any] = {
        "symbol": ticker,
        "as_of": today.isoformat(),
        "region": REGION,
        "labels_version": LABELS_VERSION,
        "is_display_only": IS_DISPLAY_ONLY,
        # rs_repair_state and sponsorship_state stamped unavailable in this PR
        "rs_repair_state": "unavailable",
        "sponsorship_state": "unavailable",
    }

    # ── Trigger tier + ticks (source: signal_gate.json) ─────────────────────
    row["trigger_tier"] = sg_verdict.get("tier_cascade")          # T1/T2/T3/T4/None
    row["trigger_age_ticks"] = sg_verdict.get("ticks")            # int or None
    row["source_artifacts"] = "signal_gate.json"

    # ── bars_to_cross (prefer signal_gate; standout fallback) ────────────────
    bars_to_cross = sg_verdict.get("bars_to_cross")
    if bars_to_cross is None and standout_row:
        sig = standout_row.get("signal") or {}
        bars_to_cross = sig.get("bars_to_cross")
    row["bars_to_cross"] = bars_to_cross

    # ── Coiled / STAR / coiled_fire (source: us_standouts.json buy rows) ─────
    coiled_dict = (standout_row or {}).get("coiled") or {}
    row["coiled"] = bool(coiled_dict.get("coiled", False))
    row["star"] = bool(coiled_dict.get("star", False))
    row["coiled_fire"] = bool(coiled_dict.get("fire", False))
    if standout_row:
        row["source_artifacts"] += ";us_standouts.json"

    # ── Donor state (board-level, source: us_standouts.json top-level .donor) ─
    donor_dict = standout_donor or {}
    row["donor_state"] = donor_dict.get("state")   # "intact"/"cracking"/None

    # ── Hold state (BIND from hold.py output in us_standouts.json) ───────────
    hold_dict = (standout_row or {}).get("hold") or {}
    hold_state_val = hold_dict.get("state") if hold_dict else None
    row["hold_state"] = hold_state_val
    row["hold_days_basing"] = hold_dict.get("days_basing") if hold_dict else None
    row["hold_maxup_pct"] = hold_dict.get("maxup_pct") if hold_dict else None

    # ── Entry quality band (source: conviction.potential.band in standout) ────
    conv = (standout_row or {}).get("conviction") or {}
    potential = conv.get("potential") or {}
    row["entry_quality_band"] = potential.get("band")  # high/constructive/neutral/low

    # ── Squeeze state (source: conviction.vol_squeeze.state) ─────────────────
    vs = conv.get("vol_squeeze") or {}
    row["squeeze_state"] = vs.get("state")   # COILED/COMPRESSED/EXPANSION/NONE/etc.

    # ── Knife score (source: conviction.alignment.knife) ─────────────────────
    alignment = conv.get("alignment") or {}
    knife_score = alignment.get("knife")
    knife_available = knife_score is not None
    row["knife_score"] = knife_score

    # ── Rolling distance columns (the ONLY two new computed columns) ──────────
    close = _load_close(root, ticker)
    dist_21 = _dist_21d_low_pct(close)
    dist_126 = _dist_126d_high_pct(close)
    row["dist_21d_low_pct"] = dist_21
    row["dist_126d_high_pct"] = dist_126
    if close is not None:
        row["source_artifacts"] += ";data/stocks/<TICKER>.parquet"

    # ── Earnings (source: data/earnings/earnings.parquet) ────────────────────
    e_date, e_days, e_blackout = _earnings_info(ticker, earnings_df, today)
    row["earnings_next_date"] = e_date
    row["earnings_days_to"] = e_days
    if not earnings_df.empty:
        row["source_artifacts"] += ";data/earnings/earnings.parquet"

    # ── Overlay flags ─────────────────────────────────────────────────────────
    overlays: list[str] = []
    if e_blackout:
        overlays.append("EVENT_BLACKOUT")
    if row["coiled"]:
        overlays.append("COILED")
    if row["star"]:
        overlays.append("STAR")
    row["overlay_flags"] = ",".join(overlays) if overlays else None

    # ── State label (labels_v1 frozen decision table) ─────────────────────────
    # hold_ret_since_take: approximate from maxup_pct when intact/basing.
    # The spec says "abs(ret since take) < 4%" — bind maxup_pct as the closest
    # available proxy (it's max-favorable, so using it is conservative).
    hold_ret_proxy = row.get("hold_maxup_pct")

    row["bottom_state"] = _classify_labels_v1(
        hold_state=hold_state_val,
        hold_days_basing=row["hold_days_basing"],
        hold_ret=hold_ret_proxy,
        trigger_tier=row["trigger_tier"],
        ticks=row["trigger_age_ticks"],
        coiled=row["coiled"],
        dist_21d_low=dist_21,
        dist_126d_high=dist_126,
        bars_to_cross=bars_to_cross,
        knife_score=knife_score,
        knife_available=knife_available,
    )

    return row


# ── Main assembly ──────────────────────────────────────────────────────────────

def assemble(
    root: Path | None = None,
    today: datetime.date | None = None,
) -> pd.DataFrame:
    """Assemble the bottom-sensor envelope for all US board names.

    Reads:
      - site/factordata/signal_gate.json  (trigger tier + ticks for full universe)
      - site/factordata/us_standouts.json  (coiled/hold/squeeze/donor for board names)
      - data/earnings/earnings.parquet    (earnings next_date)
      - data/stocks/<TICKER>.parquet      (rolling distance columns)

    Returns a DataFrame with one row per ticker in signal_gate.json universe.
    Never raises; partial failures degrade gracefully.
    """
    if root is None:
        root = _repo_root()
    root = Path(root)
    if today is None:
        today = datetime.date.today()

    log.info("bottom_sensors.assemble: root=%s, today=%s", root, today)

    # Load sources
    sg_verdicts, sg_asof = _load_signal_gate(root)
    if not sg_verdicts:
        log.error("signal_gate.json empty/missing — cannot build envelope")
        return pd.DataFrame()

    standouts = _load_us_standouts(root)
    earnings_df = _load_earnings(root)

    # Build per-ticker dicts from standouts
    buy_rows: dict[str, dict] = {}
    for r in standouts.get("buy", []):
        t = r.get("ticker")
        if t:
            buy_rows[t] = r
    # watch/laggards: they have fewer fields but we include them for field binding
    watch_rows: dict[str, dict] = {}
    for r in standouts.get("watch", []) + standouts.get("laggards", []):
        t = r.get("ticker")
        if t:
            watch_rows[t] = r

    standout_donor = standouts.get("donor") or {}

    rows: list[dict] = []
    n_ok = 0
    n_fail = 0

    for ticker, sg_v in sg_verdicts.items():
        try:
            # Prefer buy row (richer fields); fallback to watch row
            standout_row = buy_rows.get(ticker) or watch_rows.get(ticker)
            row = _build_row(
                ticker=ticker,
                sg_verdict=sg_v,
                standout_row=standout_row,
                standout_donor=standout_donor,
                earnings_df=earnings_df,
                today=today,
                root=root,
            )
            rows.append(row)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("bottom_sensors row failed for %s: %s", ticker, exc)
            n_fail += 1

    if not rows:
        log.error("bottom_sensors.assemble: zero rows built")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index("symbol")

    # stamp as_of from signal_gate
    meta_as_of = sg_asof or today.isoformat()

    log.info(
        "bottom_sensors.assemble done: %d rows (ok=%d fail=%d) as_of=%s",
        len(df), n_ok, n_fail, meta_as_of,
    )

    # Store as metadata attribute (accessible for the runner)
    df.attrs["as_of"] = meta_as_of
    df.attrs["labels_version"] = LABELS_VERSION
    df.attrs["is_display_only"] = IS_DISPLAY_ONLY

    return df
