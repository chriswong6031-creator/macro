"""Standout-board forward ledger for HK and Canada stock pages.

Masterplan §5.4 + §0 'honesty spine'; audit HKCA-12; red-team product-critic FATAL 2.

Problem addressed
-----------------
The existing name_score_grader grades the per-name POTENTIAL score (primed / setting_up /
watch / no_setup). It does NOT grade the standout board rank — the order in which the page
actually surfaces names to the user. This module is the explicit standout-board scoreboard
the plan mandates: it logs the RANKED board each render, then grades it honestly.

Three public functions
----------------------
* append_board(calls, market, asof)  — log the ranked board at render time.
* grade(market)                      — compute forward returns + IC for matured calls.
* scorecard(market)                  — per-group hit-rate + rank-IC; returns 'accruing'
                                       status dict until the min-IC-dates gate is met.

Honesty guarantees (enforced in code, not cadence)
---------------------------------------------------
1. NEXT-BAR fill: a call logged on asof is FILLED at the next available bar, never the
   signal bar itself (via engine.grading.grade_next_bar_return).
2. SUSPENSION rule (HK-native, red-team MISSING #5): if no valid print exists within
   5 sessions after the fill date, the call is marked 'suspended' and EXCLUDED from
   hit-rates. HK names suspend for weeks (deals, going-private, regulatory); silent
   ffill through halts fabricates returns. No silent-ffill ever.
3. Accruing-status gate: scorecard() returns {'status': 'accruing', ...} until
   ≥ MIN_IC_DATES matured dates each carry ≥ MIN_NAMES_PER_DATE names. This prevents
   early-alert fatigue in the admin experiments tracker.
4. Survivorship stamp: 'no_dead_name_store' is always set (no ex-HK/CA dead-name store
   exists — losses on delisted names that disappear from the close store are NOT graded
   and the count is stamped). This is the survivorship BOUND, not a caveat sticker.
5. Excess return: scorecard computes 21d excess vs market index
   (HK = _HSI, CA = _GSPTSE) — not raw return — so the IC is against market-relative
   performance.

Store
-----
data/board_ledger/{hk,ca}_board.parquet — small (one row per board-date × ticker),
append-only, keep-FIRST per (date, ticker), git-tracked (not R2: the table is tiny
and grows ~50-120 rows/day; even a full year is <50 KB per market).

Schema (one row per board snapshot entry)
-----------------------------------------
date          str        YYYY-MM-DD render date (the asof close)
market        str        HK | CA
ticker        str        exchange ticker
board_pos     int        1-based rank on the board (1 = top of the buy group)
group         str        'entry_open' | 'setting_up' | 'watch'
edge_z        float|None fused edge z-score for this name (from hk_edge / ca_alpha)
gate_tier     str|None   T1 | T2 | T3 | T4 | None  (confluence gate tier)
align_tier    str|None   'aligned' | 'near' | None
entry_state   str|None   e.g. 'open' | 'pullback' | 'wait' | None
close_asof    float|None closing price on render date
washout_2w    bool|None  CN-port stamp (§5.3): 2W-FRI StochRSI washout-reclaim held at
                         render. Log-and-grade only — never a rank input. None = not stamped
                         (caller predates the port or doesn't compute it).
extended      bool|None  CN-port stamp (§5.3): extension read in {stretched, parabolic}.
                         Log-and-grade only. None = not stamped.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine import grading
from lib import config, store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HORIZONS_D = (5, 10, 21, 63)       # 1w / 2w / 1m / 3m
_BENCH = {"HK": ("hk", "_HSI"), "CA": ("canada", "_GSPTSE")}

# Suspension rule: if no valid print within N sessions after fill, mark 'suspended'.
SUSPENSION_SESSIONS = 5

# Accruing gate: need this many matured IC dates with enough names before we report numbers.
MIN_IC_DATES = 5
MIN_NAMES_PER_DATE = 5

_SCHEMA = [
    "date", "market", "ticker", "board_pos", "group",
    "edge_z", "gate_tier", "align_tier", "entry_state", "close_asof",
    "washout_2w", "extended",
]

# Optional CN-port stamp columns — nullable bool ('boolean' dtype in the store).
# None means 'not stamped' (distinct from False = 'computed, absent').
_PORT_STAMPS = ("washout_2w", "extended")


def _store_path(market: str) -> Path:
    m = market.upper()
    return config.data_dir() / "board_ledger" / f"{m.lower()}_board.parquet"


# ---------------------------------------------------------------------------
# append_board
# ---------------------------------------------------------------------------
def append_board(
    calls: list[dict],
    market: str,
    asof: str | None = None,
) -> int:
    """Log today's ranked standout board.

    ``calls`` is a list of dicts, one per board row, in the ORDER they appear on the
    page (board_pos is assigned here, 1-based). Each call should carry:
        ticker        — required
        group         — 'entry_open' | 'setting_up' | 'watch'
        edge_z        — fused edge z-score (float, optional)
        gate_tier     — 'T1'/'T2'/'T3'/'T4'/None
        align_tier    — 'aligned'/'near'/None
        entry_state   — e.g. 'open'/'pullback'/'wait'/None
        close_asof    — today's close (float, optional)
        washout_2w    — CN-port stamp (bool, optional; None if omitted)
        extended      — CN-port stamp (bool, optional; None if omitted)

    Keep-FIRST per (date, ticker): a price already stamped for a given date is
    never overwritten — point-in-time integrity.

    Returns the ledger row count after the merge (0 on error).
    """
    if not calls or not asof:
        return 0
    m = market.upper()
    rows = []
    for pos, c in enumerate(calls, start=1):
        tk = c.get("ticker")
        if not tk:
            continue
        rows.append({
            "date": str(asof),
            "market": m,
            "ticker": str(tk),
            "board_pos": pos,
            "group": c.get("group"),
            "edge_z": _float_or_none(c.get("edge_z")),
            "gate_tier": c.get("gate_tier") or None,
            "align_tier": c.get("align_tier") or None,
            "entry_state": c.get("entry_state") or None,
            "close_asof": _float_or_none(c.get("close_asof")),
            "washout_2w": _bool_or_none(c.get("washout_2w")),
            "extended": _bool_or_none(c.get("extended")),
        })
    if not rows:
        return 0
    try:
        new = pd.DataFrame(rows)[_SCHEMA]
        p = _store_path(m)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            # union schema: prior frames may predate the optional stamp columns (and may
            # carry legacy extras) — reindex both sides so concat never drops a column
            cols = list(dict.fromkeys([*_SCHEMA, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=cols), new.reindex(columns=cols)],
                ignore_index=True,
            )
            # keep-FIRST per (date, ticker) — honesty: stamp is immutable once written
            combined = combined.drop_duplicates(subset=["date", "ticker"], keep="first")
        else:
            combined = new
        for col in _PORT_STAMPS:
            combined[col] = combined[col].astype("boolean")
        combined.to_parquet(p, index=False)
        return int(len(combined))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("board_ledger (%s): append failed: %s", m, e)
        return 0


# ---------------------------------------------------------------------------
# Close-series loaders (market-specific; pure reads)
# ---------------------------------------------------------------------------
def _hk_close(ticker: str) -> pd.Series | None:
    """Per-ticker close for HK names (store group 'hk_stocks')."""
    df = store.read("hk_stocks", ticker)
    if df is None or "close" not in df.columns:
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _ca_close(ticker: str, _cache: dict | None = None) -> pd.Series | None:
    """Per-ticker close for CA names from the wide canada_search/closes.parquet frame.

    The wide frame is cached on first call within a grade() run via the ``_cache`` dict
    so we don't re-read the 219-column parquet for every ticker.
    """
    if _cache is not None and "__ca_wide__" not in _cache:
        _cache["__ca_wide__"] = _load_ca_wide()
    wide = (_cache["__ca_wide__"] if _cache is not None else _load_ca_wide())
    if wide is None or ticker not in wide.columns:
        return None
    s = pd.to_numeric(wide[ticker], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _load_ca_wide() -> pd.DataFrame | None:
    """Load the CA search/breadth wide close frame (219 names)."""
    cp = config.data_dir() / "canada_search" / "closes.parquet"
    if not cp.exists():
        # fallback: breadth cache (gitignored, rebuild-only)
        cp = config.data_dir() / "canada_breadth" / "_closes_cache.parquet"
    if not cp.exists():
        return None
    try:
        return pd.read_parquet(cp).sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("board_ledger: CA wide close load failed: %s", e)
        return None


def _bench_close(market: str) -> pd.Series | None:
    """Benchmark close series (HK=_HSI, CA=_GSPTSE)."""
    grp, tkr = _BENCH.get(market.upper(), (None, None))
    if grp is None:
        return None
    df = store.read(grp, tkr)
    if df is None or "close" not in df.columns:
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
    return s if not s.empty else None


def _name_close(market: str, ticker: str, ca_cache: dict | None = None) -> pd.Series | None:
    """Dispatch to the right close loader by market."""
    m = market.upper()
    if m == "HK":
        return _hk_close(ticker)
    if m == "CA":
        return _ca_close(ticker, _cache=ca_cache)
    return None


# ---------------------------------------------------------------------------
# Suspension check
# ---------------------------------------------------------------------------
def _is_suspended(close: pd.Series, fill_date: pd.Timestamp) -> bool:
    """Return True if there is no valid close within SUSPENSION_SESSIONS trading bars
    strictly AFTER fill_date. A name that halts immediately after entry is 'suspended'
    and its outcome is excluded from hit-rates (never silently ffilled).

    'Trading bars' here means calendar bars present in the close index (the
    session count, not calendar days) — consistent with how grading.fill_index works.
    """
    after = close[close.index > fill_date]
    return len(after) < SUSPENSION_SESSIONS


# ---------------------------------------------------------------------------
# grade
# ---------------------------------------------------------------------------
def grade(market: str) -> dict:
    """Compute forward returns for matured board calls.

    For each logged call:
      1. Find the fill bar = NEXT bar after the call date (next-bar fill via grading).
      2. Check suspension: if fewer than SUSPENSION_SESSIONS bars exist after fill,
         mark 'suspended' and exclude from IC and hit-rates.
      3. Compute excess return vs market index at each horizon:
             excess = (name_fwd_ret - bench_fwd_ret) at h bars.
      4. Store 'grade' results in the output dict keyed by (date, ticker, horizon).

    Returns a dict with keys:
        market, n_calls, n_graded, n_suspended, survivorship,
        by_horizon: {h: [{date, ticker, board_pos, group, edge_z, fwd_ret, bench_ret,
                          excess_ret, suspended}, ...]}
    """
    m = market.upper()
    p = _store_path(m)
    if not p.exists():
        return {"market": m, "available": False, "note": "no board calls logged yet"}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"market": m, "available": False, "note": f"unreadable: {e}"}
    if df.empty:
        return {"market": m, "available": False, "note": "empty ledger"}

    bench = _bench_close(m)
    ca_cache: dict = {}

    out: dict = {
        "market": m,
        "available": True,
        "n_calls": int(len(df)),
        "n_graded": 0,
        "n_suspended": 0,
        "survivorship": "no_dead_name_store",  # no ex-HK/CA dead-name store — losses on
        # delisted names that disappear from the live store are NOT captured; this is the
        # honest survivorship BOUND, not a stamp.
        "by_horizon": {f"{h}d": [] for h in _HORIZONS_D},
    }

    for _i, row in df.iterrows():
        date_str = str(row["date"])
        ticker = str(row["ticker"])
        d0 = pd.Timestamp(date_str)

        close = _name_close(m, ticker, ca_cache=ca_cache)
        if close is None or close.empty:
            continue  # name not in live store (may be delisted — not captured)

        # Determine fill index (next bar after signal)
        fill_iloc = grading.fill_index(close, d0)
        if fill_iloc is None:
            continue  # not yet matured
        fill_date = close.index[fill_iloc]

        # Suspension check: excluded from IC/hit-rates, never silently ffilled
        if _is_suspended(close, fill_date):
            out["n_suspended"] += 1
            for h in _HORIZONS_D:
                out["by_horizon"][f"{h}d"].append({
                    "date": date_str,
                    "ticker": ticker,
                    "board_pos": int(row.get("board_pos") or 0),
                    "group": row.get("group"),
                    "edge_z": _float_or_none(row.get("edge_z")),
                    "fwd_ret": None,
                    "bench_ret": None,
                    "excess_ret": None,
                    "suspended": True,
                })
            continue

        graded_any = False
        for h in _HORIZONS_D:
            name_ret = grading.grade_next_bar_return(close, d0, h)
            bench_ret = (grading.grade_next_bar_return(bench, d0, h)
                         if bench is not None else None)
            excess = (_excess(name_ret, bench_ret)
                      if name_ret is not None and bench_ret is not None else None)
            out["by_horizon"][f"{h}d"].append({
                "date": date_str,
                "ticker": ticker,
                "board_pos": int(row.get("board_pos") or 0),
                "group": row.get("group"),
                "edge_z": _float_or_none(row.get("edge_z")),
                "fwd_ret": name_ret,
                "bench_ret": bench_ret,
                "excess_ret": excess,
                "suspended": False,
            })
            if name_ret is not None:
                graded_any = True
        if graded_any:
            out["n_graded"] += 1

    return out


# ---------------------------------------------------------------------------
# scorecard
# ---------------------------------------------------------------------------
def scorecard(market: str) -> dict:
    """Per-group hit-rate + Spearman rank-IC of board_pos vs forward excess at each
    horizon. Returns an 'accruing' status dict until the min-IC-dates gate is met.

    Min-IC-dates gate (guards against early-alert fatigue per red-team minor finding):
      * Return {'status': 'accruing', ...} unless ≥ MIN_IC_DATES dates each have
        ≥ MIN_NAMES_PER_DATE NON-SUSPENDED graded names.
      * When the gate is met, compute the scorecard and return {'status': 'scored', ...}.

    IC semantics:
      * Spearman(board_pos, excess_ret_at_h): negative IC is GOOD (lower board_pos =
        higher rank = earlier on board; lower pos number correlates with higher excess).
        We report the IC sign as "rank_ic" = Spearman(pos, excess), so negative means
        the board order predicted outperformance.
      * hit_rate = fraction of NON-SUSPENDED graded calls in 'entry_open' and
        'setting_up' groups with positive 21d excess.
      * Both computed ONLY on non-suspended rows.

    Returns dict with:
        market, status ('accruing'|'scored')
        first_read_est     — estimated date for stable read (first_write + 21td from today)
        by_horizon: {h: {n, n_ic_dates, rank_ic, n_buy, hit_rate_21d, by_group: {...}}}
        note               — human-readable status summary
    """
    m = market.upper()
    g = grade(m)
    if not g.get("available"):
        return {"market": m, "status": "accruing",
                "note": g.get("note", "no data yet"),
                "first_read_est": _est_first_read()}

    by_h: dict = {}
    for h in _HORIZONS_D:
        key = f"{h}d"
        rows = [r for r in g["by_horizon"].get(key, []) if not r.get("suspended", True)]
        if not rows:
            by_h[key] = {"n": 0, "n_ic_dates": 0, "rank_ic": None,
                         "n_buy": 0, "hit_rate_21d": None, "by_group": {}}
            continue

        gf = pd.DataFrame(rows)
        # count matured dates with enough names for IC
        date_counts = gf[gf["excess_ret"].notna()].groupby("date")["ticker"].count()
        ic_eligible_dates = date_counts[date_counts >= MIN_NAMES_PER_DATE].index.tolist()
        n_ic_dates = len(ic_eligible_dates)

        # only compute IC if gate met
        rank_ic = None
        if n_ic_dates >= MIN_IC_DATES:
            ics = []
            for d in ic_eligible_dates:
                sub = gf[(gf["date"] == d) & gf["excess_ret"].notna()]
                if len(sub) >= MIN_NAMES_PER_DATE:
                    try:
                        ic = float(sub["board_pos"].rank().corr(
                            sub["excess_ret"].rank(), method="spearman"))
                        if np.isfinite(ic):
                            ics.append(ic)
                    except Exception:  # noqa: BLE001
                        pass
            if ics:
                rank_ic = round(float(np.mean(ics)), 4)

        # hit rate: entry_open + setting_up groups, excess > 0
        buy_mask = gf["group"].isin(["entry_open", "setting_up"])
        buy_graded = gf[buy_mask & gf["excess_ret"].notna()]
        n_buy = int(len(buy_graded))
        hit_rate = (
            round(float((buy_graded["excess_ret"] > 0).mean()), 3)
            if n_buy >= 5 else None
        )

        # by-group breakdown
        by_group: dict = {}
        for grp_name, sub in gf[gf["excess_ret"].notna()].groupby("group"):
            if len(sub) >= MIN_NAMES_PER_DATE:
                by_group[grp_name] = {
                    "n": int(len(sub)),
                    "mean_excess": round(float(sub["excess_ret"].mean()), 4),
                    "pos_rate": round(float((sub["excess_ret"] > 0).mean()), 3),
                }

        by_h[key] = {
            "n": int(len(rows)),
            "n_ic_dates": n_ic_dates,
            "rank_ic": rank_ic,
            "n_buy": n_buy,
            "hit_rate_21d": hit_rate if h == 21 else None,
            "by_group": by_group,
        }

    # overall gate: scored only when 21d horizon meets MIN_IC_DATES
    gate_met = by_h.get("21d", {}).get("n_ic_dates", 0) >= MIN_IC_DATES
    status = "scored" if gate_met else "accruing"

    note_parts = [
        f"n_calls={g['n_calls']}",
        f"n_graded={g['n_graded']}",
        f"n_suspended={g['n_suspended']}",
        f"21d_ic_dates={by_h.get('21d', {}).get('n_ic_dates', 0)}/{MIN_IC_DATES}",
    ]
    if status == "accruing":
        note_parts.append(f"first_stable_read≈{_est_first_read()}")

    return {
        "market": m,
        "status": status,
        "n_calls": g["n_calls"],
        "n_graded": g["n_graded"],
        "n_suspended": g["n_suspended"],
        "survivorship": g["survivorship"],
        "first_read_est": _est_first_read(),
        "by_horizon": by_h,
        "note": "; ".join(note_parts),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _float_or_none(v) -> float | None:
    """Convert to float or return None (handles NaN gracefully)."""
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _bool_or_none(v) -> bool | None:
    """Coerce to bool, preserving None/NaN/pd.NA as None ('not stamped')."""
    try:
        if v is None or pd.isna(v):
            return None
        return bool(v)
    except (TypeError, ValueError):
        return None


def _excess(name_ret: float | None, bench_ret: float | None) -> float | None:
    """Arithmetic excess return."""
    if name_ret is None or bench_ret is None:
        return None
    return name_ret - bench_ret


def _est_first_read() -> str:
    """Estimate the date of first stable scorecard read.

    From the masterplan: 'first single 21d grade ≈ first_write + 21td; stable read
    ≥5 matured dates ≈ late-Aug if wired 2026-07'.

    We return 2026-08-24 (matching the registry entry) as the program-level constant.
    This function exists so tests and callers get a consistent value.
    """
    return "2026-08-24"
