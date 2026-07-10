"""Manager turnover / lag-durability diagnostics for the Smart Money v2 Ownership
Intelligence Desk.

HONESTY CONTRACT (printed on every surface this feeds):
* All tiers and metrics are DESCRIPTIVE — they characterize the observable filing
  history of a fund, not its future skill or lag tolerance.
* SURVIVOR-COHORT CAVEAT: the roster is curated as of 2026 from CURRENT filers. Funds
  that closed or stopped filing are absent from the universe, so grades are descriptive
  of survivors only — this is NOT a manager-selection edge.
* PIT anchors: every function that reads disk uses `filing_date` as the look-ahead-free
  anchor; period-end dates are NEVER used as action timestamps. Cross-sectional
  comparison is meaningful ONLY within the same filing cycle.
* Issuer-level collapse: share-class pairs (BRK.A/B, GOOG/GOOGL, …) are collapsed to
  a single canonical issuer via `engine.smart_money.issuer_key` before turnover math —
  without this, a dual-class position double-counts.
* When a fund has fewer than 3 snapshot pairs, `lag_tier` falls back to the config
  `turnover_hint`; the source is marked 'hint' in the return dict so the caller can
  surface this limitation to the reader.
"""
from __future__ import annotations

import logging
import statistics as _st
from typing import Sequence

import pandas as pd

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Share-class collapse helper (re-exported from smart_money to avoid circular  #
# imports if the caller already has the table loaded)                           #
# --------------------------------------------------------------------------- #

def _issuer_key(ticker: str | None, cusip: str | None,
                equiv_table: dict[str, str] | None = None) -> str:
    """Collapse a ticker to its canonical share-class representative, then fall
    back to the 6-character CUSIP stem. Returns a non-empty string suitable as a
    grouping key. PURE."""
    t = str(ticker or "").strip().upper()
    if equiv_table and t in equiv_table:
        t = equiv_table[t]
    c = str(cusip or "").strip().upper()
    # If two resolved tickers share a CUSIP stem, the stem is the safer key.
    stem = c[:6] if len(c) >= 6 else ""
    return t if t and t not in ("", "NAN", "NONE") else (stem or "UNKNOWN")


def _load_equiv_table() -> dict[str, str]:
    """Load the share_class_equiv.yml table from config/, returning {ticker:canonical}.
    Silent-degrades to empty dict if missing (then only CUSIP-stem collapse applies)."""
    try:
        import pathlib
        import yaml
        # Project root is one level above engine/
        root = pathlib.Path(__file__).resolve().parent.parent
        p = root / "config" / "share_class_equiv.yml"
        if not p.exists():
            return {}
        with open(p) as fh:
            data = yaml.safe_load(fh) or {}
        equiv: dict[str, str] = {}
        for entry in data.get("equivalences", []):
            t = str(entry.get("ticker", "")).strip().upper()
            c = str(entry.get("canonical", "")).strip().upper()
            if t and c and t != c:
                equiv[t] = c
        return equiv
    except Exception:  # noqa: BLE001
        log.debug("share_class_equiv.yml load failed — falling back to CUSIP-stem only")
        return {}


# --------------------------------------------------------------------------- #
# Pure computation — all functions accept in-memory DataFrames for testability  #
# --------------------------------------------------------------------------- #

def quarterly_turnover(prev_snap: pd.DataFrame, cur_snap: pd.DataFrame,
                       equiv_table: dict[str, str] | None = None) -> float:
    """Turnover for a single consecutive quarter pair: Σ|Δposition_value| / (2 × avg book).

    Turnover is computed at the ISSUER level (after share-class collapse) to prevent
    dual-class pairs from inflating the numerator. PURE — callers inject the two frames.

    Parameters
    ----------
    prev_snap, cur_snap : DataFrames with at least [cusip, ticker, value_usd, sh_type]
    equiv_table         : ticker→canonical mapping (from load_equiv_table); None → CUSIP only

    Returns
    -------
    float in [0, ∞) — 0.0 when both snapshots are empty or identical.
    """
    if equiv_table is None:
        equiv_table = {}

    def _collapse(df: pd.DataFrame) -> dict[str, float]:
        """issuer_key -> total USD value (SH only, issuer-collapsed)."""
        eq = df[df.get("sh_type", pd.Series(["SH"] * len(df))) == "SH"].copy()
        if eq.empty:
            return {}
        eq["_key"] = [_issuer_key(r.get("ticker"), r.get("cusip"), equiv_table)
                      for r in eq.to_dict("records")]
        return eq.groupby("_key")["value_usd"].sum().to_dict()

    prev_val = _collapse(prev_snap)
    cur_val = _collapse(cur_snap)
    all_keys = set(prev_val) | set(cur_val)
    if not all_keys:
        return 0.0
    total_delta = sum(abs(cur_val.get(k, 0.0) - prev_val.get(k, 0.0)) for k in all_keys)
    avg_book = (sum(prev_val.values()) + sum(cur_val.values())) / 2.0
    if avg_book <= 0:
        return 0.0
    return float(total_delta / (2.0 * avg_book))


def _read_all_snaps_for_lag(slug: str) -> list[tuple[str, str, pd.DataFrame]]:
    """Thin wrapper exposing _read_all for callers that don't want to import smart_money
    directly. Returns (period_end, filing_date, df) tuples ascending by period."""
    from engine.smart_money import _read_all  # lazy import to avoid circular
    return _read_all(slug)


def fund_turnover(slug: str, equiv_table: dict[str, str] | None = None
                  ) -> dict:
    """Mean quarterly turnover over ALL available consecutive snapshot pairs for a fund.

    Returns dict with keys:
      - mean_turnover_pct: float (0–100) or None if < 1 pair
      - n_pairs: int
      - raw_pairs: list[float] (each pair's turnover fraction × 100)
    """
    from engine.smart_money import _read_all  # lazy import to avoid circular
    snaps = _read_all(slug)  # (period_end, filing_date, df) ascending
    if len(snaps) < 2:
        return {"mean_turnover_pct": None, "n_pairs": 0, "raw_pairs": []}
    if equiv_table is None:
        equiv_table = _load_equiv_table()
    raw = []
    for i in range(len(snaps) - 1):
        _, _, prev = snaps[i]
        _, _, cur = snaps[i + 1]
        try:
            t = quarterly_turnover(prev, cur, equiv_table)
            raw.append(round(t * 100.0, 1))
        except Exception:  # noqa: BLE001
            log.debug("quarterly_turnover failed for %s pair %d", slug, i)
    if not raw:
        return {"mean_turnover_pct": None, "n_pairs": 0, "raw_pairs": []}
    return {
        "mean_turnover_pct": round(_st.mean(raw), 1),
        "n_pairs": len(raw),
        "raw_pairs": raw,
    }


def effective_holding_period(fund_snaps: Sequence[tuple[str, str, pd.DataFrame]],
                             equiv_table: dict[str, str] | None = None) -> float | None:
    """Median run-length in quarters that positions are held, at the ISSUER level.

    A 'run' is consecutive quarters in which an issuer appears in the portfolio. The
    holding-period is the number of consecutive snapshots in each such run.

    Returns None when there is insufficient history (< 2 snapshots). PURE.
    """
    if len(fund_snaps) < 2:
        return None
    if equiv_table is None:
        equiv_table = {}
    # Build {issuer_key: set of quarter indices where the position exists}
    presence: dict[str, list[bool]] = {}
    n = len(fund_snaps)
    for qi, (_, _, snap) in enumerate(fund_snaps):
        eq = snap[snap.get("sh_type", pd.Series(["SH"] * len(snap))) == "SH"]
        for r in eq.to_dict("records"):
            k = _issuer_key(r.get("ticker"), r.get("cusip"), equiv_table)
            if k not in presence:
                presence[k] = [False] * n
            presence[k][qi] = True

    run_lengths: list[int] = []
    for bools in presence.values():
        run = 0
        for held in bools:
            if held:
                run += 1
            else:
                if run > 0:
                    run_lengths.append(run)
                run = 0
        if run > 0:
            run_lengths.append(run)

    return round(_st.median(run_lengths), 1) if run_lengths else None


def lag_tier(turnover_pct: float | None, holding_period_q: float | None,
             hint: str | None = None, n_pairs: int = 0
             ) -> dict:
    """Classify a fund's lag durability into 'low', 'med', or 'high' turnover tier.

    Rules (from masterplan §4):
      - low  : turnover < 25 %/qtr  OR  holding period >= 4 quarters
      - high : turnover > 75 %/qtr
      - med  : everything else
    When n_pairs < 3, there is insufficient history to compute from data. In that case:
      - if a `hint` is provided ('low', 'med', 'high') use it, mark source='hint'
      - else return source='insufficient'

    Returns dict with:
      - tier   : 'low' | 'med' | 'high'
      - source : 'data' | 'hint' | 'insufficient'
      - note   : short human-readable note for the UI
    """
    if n_pairs < 3:
        if hint and hint in ("low", "med", "high"):
            return {"tier": hint, "source": "hint",
                    "note": f"config hint (only {n_pairs} snapshot pair(s) available)"}
        return {"tier": "med", "source": "insufficient",
                "note": f"insufficient history ({n_pairs} pair(s)); defaulting to med"}

    # Data-driven
    tp = float(turnover_pct) if turnover_pct is not None else 50.0
    hp = float(holding_period_q) if holding_period_q is not None else 0.0

    if tp < 25.0 or hp >= 4.0:
        tier = "low"
    elif tp > 75.0:
        tier = "high"
    else:
        tier = "med"
    return {"tier": tier, "source": "data",
            "note": f"{round(tp, 1)}%/qtr turnover, {round(hp, 1)}q median hold"}


def concentration_top10(snap: pd.DataFrame,
                        equiv_table: dict[str, str] | None = None) -> float | None:
    """Fraction of the book in the top-10 issuers (by value_usd). PURE.

    Returns None if the snapshot is empty or has no priced SH rows. The value is in
    [0, 100] — 100 means the whole book is in 10 names.
    """
    if equiv_table is None:
        equiv_table = {}
    eq = snap[snap.get("sh_type", pd.Series(["SH"] * len(snap))) == "SH"].copy()
    if eq.empty:
        return None
    eq["_key"] = [_issuer_key(r.get("ticker"), r.get("cusip"), equiv_table)
                  for r in eq.to_dict("records")]
    by_issuer = eq.groupby("_key")["value_usd"].sum().sort_values(ascending=False)
    total = float(by_issuer.sum())
    if total <= 0:
        return None
    top10 = float(by_issuer.head(10).sum())
    return round(100.0 * top10 / total, 1)


def n_holdings(snap: pd.DataFrame, equiv_table: dict[str, str] | None = None) -> int:
    """Distinct issuer count in the snapshot (SH rows, issuer-collapsed). PURE."""
    if equiv_table is None:
        equiv_table = {}
    eq = snap[snap.get("sh_type", pd.Series(["SH"] * len(snap))) == "SH"].copy()
    if eq.empty:
        return 0
    keys = {_issuer_key(r.get("ticker"), r.get("cusip"), equiv_table)
            for r in eq.to_dict("records")}
    return len(keys)
