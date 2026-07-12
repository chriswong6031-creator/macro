"""engine/pricing_power_monitor.py — LHB-W3 A2 Pricing-Power Pilot: quarterly peer-relative
double-confirmation gross-margin monitor.

DISPLAY-ONLY — horizon_role=hold_thesis (LHB-R3, LHB-W3 adjudication).
These outputs MUST NOT feed board ordering, alert triage, top-setups gates,
or push floor. No composite score is produced.

Design contract (research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md §A2
                  + research/FALSIFIER_FIELD_BOOK_ADJUDICATION_BY_FABLE.md FFB-R7/R8/R9)
---------------------------------------------------------------------
Gross-margin leg ONLY (receivables leg waits for LHB-R6 quarterly backfill).

Observable (FFB §Observable conventions):
  gross_margin_yoy_change: filed gross_profit/revenue for one fiscal quarter
    MINUS gross_profit/revenue for the SAME fiscal quarter PRIOR YEAR (fiscal-aligned,
    never calendar-adjacent). Basis points (100 * (gm_cur - gm_prior)).

Fire condition (review-opener, FFB-R7 — magnitude alone does not separate; peer gate
is the discriminator per FFB-R9):
  (a) revenue YoY growth > 0 (i.e. revenue is not declining — revenue shrink excluded)
  (b) gross-margin YoY change <= -100 bp (deterioration)
  (c) peer gate: same-sector peer MEDIAN gross-margin YoY change > company's change + 50 bp
      (company deterioration is company-specific, not sector-wide)
  => TWO consecutive filed quarters must BOTH satisfy (a)+(b)+(c)

State enum (LHB-R3):
  not_observed     — <2 qualifying quarters OR fire condition not met
  challenged       — two consecutive filed quarters satisfy (a)+(b)+(c)
  unverifiable     — <2 computable quarters OR peer coverage < 15 names
  (NEVER 'broken' from this monitor — LHB-R3)

Point-in-time gating:
  statements_quarterly.parquet carries a 'filed' column (real SEC filed date).
  A quarter is visible ONLY from its filed date (not period_end + 120d approximation
  — the real filed date is available and must be used for PIT correctness).
  asof_date=None gates against today (live display path).
  Caveat: backfill_edgar_quarterly.py deduplicates to the LATEST filing per
  (ticker, fy, fq). An amended quarter's original values and original filed-date
  are therefore overwritten by the amendment's filed date. PIT gating is faithful
  to the surviving (amended) row — not strictly amendment-PIT-faithful.

Fiscal alignment:
  Quarters are matched by (fiscal_year, fiscal_quarter) — same fiscal quarter
  year over year. Q2 2024 is compared ONLY to Q2 2023, never Q1 2023 or Q3 2023.

Peer coverage:
  Peers = all tickers with the same GICS sector label in the visible-as-of window
  that have a computable gross-margin YoY change for the same (fiscal_quarter, prior_fy)
  pair. If <15 peers compute, state = unverifiable.

Output per ticker: dict with
  ticker, asof_date, state (not_observed|challenged|unverifiable),
  trigger_quarters (list of up to 2 filing dicts), peer_n, peer_median_change_bp,
  coverage_n_quarters (number of PIT-visible quarters for the ticker),
  _display_only, _horizon_role, _version, _schema

Usage
-----
  from engine.pricing_power_monitor import compute_pricing_power_state

  result = compute_pricing_power_state(
      ticker="UAA",
      ticker_sector="Consumer Discretionary",
      quarterly_df=df_all_tickers,
      sector_peers_df=df_all_tickers,   # same source, filtered internally
      asof_date="2017-01-01",
  )

Standalone smoke-test:
  python -m engine.pricing_power_monitor AAPL
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── firewall constants ────────────────────────────────────────────────────────
_HORIZON_ROLE = "hold_thesis"
_DISPLAY_ONLY = True
_VERSION = "v1"
_SCHEMA = "pricing_power.v1"

# ── thresholds (FFB-R7: review-openers, never auto-broken) ───────────────────
_MIN_PEER_N = 15                       # min same-sector peer count for computable peer gate
_REV_GROWTH_FLOOR_PCT = 0.0            # revenue YoY growth must be > 0 (strictly positive)
_GM_DETERIORATION_THRESHOLD_BP = -100  # gross-margin YoY change <= -100 bp to qualify
_PEER_GAP_BP = 50                      # peer median must exceed company change by >= 50 bp


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_asof(asof_date: str | None) -> "pd.Timestamp":
    """Return the as-of timestamp for PIT gating.

    None -> today (live display path). Unparseable -> today (fail-open).
    """
    if asof_date is None:
        return pd.Timestamp.now().normalize()
    try:
        return pd.to_datetime(asof_date).normalize()
    except Exception:  # noqa: BLE001
        return pd.Timestamp.now().normalize()


def _gm_pct(gross_profit: float | None, revenue: float | None) -> float | None:
    """Gross margin as a fraction (0–1).  Returns None when inputs are invalid."""
    if revenue is None or pd.isna(revenue) or abs(float(revenue)) < 1e-9:
        return None
    if gross_profit is None or pd.isna(gross_profit):
        return None
    return float(gross_profit) / float(revenue)


def _pct_change(new_val: float | None, old_val: float | None) -> float | None:
    """YoY fractional change (e.g. 0.05 = 5%).  None if old_val ~0 or missing."""
    if old_val is None or pd.isna(old_val) or abs(float(old_val)) < 1e-9:
        return None
    if new_val is None or pd.isna(new_val):
        return None
    return float(new_val - old_val) / abs(float(old_val))


def _quarter_gm_yoy(
    cur_row: pd.Series,
    prior_row: pd.Series,
) -> dict | None:
    """Compute one quarter's gross-margin YoY change (bp) and revenue YoY growth.

    Returns None if insufficient data.  Returns a dict with:
      gm_cur_pct, gm_prior_pct, gm_change_bp, rev_yoy_pct, revenue_positive
    """
    rev_yoy = _pct_change(cur_row.get("revenue"), prior_row.get("revenue"))
    gm_cur = _gm_pct(cur_row.get("gross_profit"), cur_row.get("revenue"))
    gm_prior = _gm_pct(prior_row.get("gross_profit"), prior_row.get("revenue"))

    if rev_yoy is None or gm_cur is None or gm_prior is None:
        return None

    gm_change_bp = (gm_cur - gm_prior) * 10_000.0  # basis points

    return {
        "gm_cur_pct": round(gm_cur, 6),
        "gm_prior_pct": round(gm_prior, 6),
        "gm_change_bp": round(gm_change_bp, 2),
        "rev_yoy_pct": round(rev_yoy, 6),
        "revenue_positive": bool(rev_yoy > _REV_GROWTH_FLOOR_PCT),
    }


# ── peer gate helpers ─────────────────────────────────────────────────────────

def _compute_peer_gm_changes(
    ticker: str,
    fiscal_year: int,
    fiscal_quarter: int,
    quarterly_df: pd.DataFrame,
    asof_ts: pd.Timestamp,
) -> tuple[int, float | None]:
    """Compute peer median gross-margin YoY change (bp) for same fiscal quarter.

    Peers = all tickers EXCEPT the target ticker that:
      1. Have a filed date <= asof_ts for the (fiscal_year, fiscal_quarter) row
      2. Have a filed date <= asof_ts for the (fiscal_year - 1, fiscal_quarter) row
      3. Can compute a valid gm_change_bp

    Returns (peer_n, peer_median_bp).  peer_median_bp is None when peer_n < _MIN_PEER_N.
    """
    prior_fy = fiscal_year - 1

    # Filter to peers (exclude self)
    peer_df = quarterly_df[quarterly_df["ticker"] != ticker].copy()
    if peer_df.empty:
        return 0, None

    # Ensure filed is parsed
    peer_df = peer_df.copy()
    peer_df["_filed_ts"] = pd.to_datetime(peer_df["filed"], errors="coerce")

    # Rows visible as-of for current quarter
    cur_mask = (
        (peer_df["fiscal_year"] == fiscal_year)
        & (peer_df["fiscal_quarter"] == fiscal_quarter)
        & (peer_df["_filed_ts"] <= asof_ts)
    )
    cur_rows = peer_df[cur_mask].set_index("ticker")

    # Rows visible as-of for prior-year same quarter
    prior_mask = (
        (peer_df["fiscal_year"] == prior_fy)
        & (peer_df["fiscal_quarter"] == fiscal_quarter)
        & (peer_df["_filed_ts"] <= asof_ts)
    )
    prior_rows = peer_df[prior_mask].set_index("ticker")

    # Only peers with BOTH current and prior rows
    common_tickers = cur_rows.index.intersection(prior_rows.index)
    if len(common_tickers) == 0:
        return 0, None

    changes_bp: list[float] = []
    for peer_tk in common_tickers:
        cur_r = cur_rows.loc[peer_tk]
        prior_r = prior_rows.loc[peer_tk]
        # Handle duplicate index (take first)
        if isinstance(cur_r, pd.DataFrame):
            cur_r = cur_r.iloc[0]
        if isinstance(prior_r, pd.DataFrame):
            prior_r = prior_r.iloc[0]

        gm_cur = _gm_pct(cur_r.get("gross_profit"), cur_r.get("revenue"))
        gm_prior = _gm_pct(prior_r.get("gross_profit"), prior_r.get("revenue"))
        if gm_cur is None or gm_prior is None:
            continue
        changes_bp.append((gm_cur - gm_prior) * 10_000.0)

    peer_n = len(changes_bp)
    if peer_n < _MIN_PEER_N:
        return peer_n, None

    peer_median = float(pd.Series(changes_bp).median())
    return peer_n, peer_median


# ── main per-ticker function ──────────────────────────────────────────────────

def compute_pricing_power_state(
    ticker: str,
    ticker_sector: str,
    quarterly_df: pd.DataFrame,
    sector_peers_df: pd.DataFrame,
    asof_date: str | None = None,
) -> dict[str, Any]:
    """Compute gross-margin pricing-power double-confirmation state for one ticker.

    Parameters
    ----------
    ticker:
        Ticker symbol (upper-cased internally).
    ticker_sector:
        GICS sector label for this ticker (used to select peer universe).
    quarterly_df:
        Rows for THIS ticker only from statements_quarterly.parquet.
        Must have columns: fiscal_year, fiscal_quarter, revenue, gross_profit, filed.
    sector_peers_df:
        All rows (all tickers in same sector) from statements_quarterly.parquet.
        Must have the same schema as quarterly_df.
        PIT filtering is applied internally using the 'filed' column.
    asof_date:
        ISO date string for PIT evaluation.  None = today (live display path).

    Returns
    -------
    dict with all output fields + stamps.
    """
    ticker = str(ticker).upper().strip()
    asof_ts = _resolve_asof(asof_date)
    asof_str = str(asof_ts.date())

    # PIT filter ticker rows by filed date
    if quarterly_df is None or quarterly_df.empty:
        return _result(ticker, asof_str, "unverifiable", [], 0, None, 0,
                       reason="no quarterly data for ticker")

    df = quarterly_df.copy()
    df["_filed_ts"] = pd.to_datetime(df["filed"], errors="coerce")
    visible = df[df["_filed_ts"] <= asof_ts].copy()

    if visible.empty:
        return _result(ticker, asof_str, "unverifiable", [], 0, None, 0,
                       reason="no PIT-visible quarters as of asof_date")

    coverage_n = len(visible)
    if coverage_n < 2:
        return _result(ticker, asof_str, "unverifiable", [], 0, None, coverage_n,
                       reason=f"only {coverage_n} PIT-visible quarter(s); need >= 2")

    # Sort by (fiscal_year, fiscal_quarter) descending for recency-first scan
    visible = visible.sort_values(["fiscal_year", "fiscal_quarter"], ascending=False).reset_index(drop=True)

    # Build a lookup for prior-year same quarter
    def _prior_row(fy: int, fq: int) -> pd.Series | None:
        """Find the PIT-visible row for (fy-1, fq)."""
        mask = (
            (visible["fiscal_year"] == fy - 1)
            & (visible["fiscal_quarter"] == fq)
        )
        matches = visible[mask]
        if matches.empty:
            return None
        return matches.iloc[0]

    # Evaluate each visible quarter (most recent first) — look for two CONSECUTIVE
    # fiscally-adjacent quarters that BOTH satisfy (a)+(b)+(c).
    #
    # "Consecutive" = two quarters that differ by exactly ONE fiscal quarter in
    # (fiscal_year, fiscal_quarter) space (e.g. Q2→Q1 same year, or Q1→Q4 prev year).
    #
    # Chain rule (uniform, Findings 1+2):
    #   - Scan most-recent-first (sorted by fy/fq desc).
    #   - ANY evaluable quarter that does NOT fire all three gates (a)+(b)+(c) RESETS
    #     the chain once we have started one. "Evaluable" = has a computable prior-year
    #     row and computable gm_yoy values.
    #   - A quarter with no prior-year row (cannot compute) is SKIPPED without
    #     breaking the chain (it is not evaluable — the docstring treats coverage gaps
    #     as "not observable", neither confirming nor breaking).
    #   - A quarter with computable values that fails (a), (b), or (c) DOES break
    #     the chain, making the gap explicit.
    #
    # This ensures revenue-shrink, thin-peers, and sector-wide quarters are treated
    # identically once a chain has started: they all reset it.

    qualifying: list[dict] = []   # all evaluable quarters (a+b satisfied), pre-peer-gate
    peer_gate_fired: list[dict] = []  # current consecutive run of (a)+(b)+(c) quarters

    # We scan from most recent filed quarter backwards
    for _, cur_row in visible.iterrows():
        fy = int(cur_row["fiscal_year"])
        fq = int(cur_row["fiscal_quarter"])

        prior_row = _prior_row(fy, fq)
        if prior_row is None:
            # No prior-year comparable: not evaluable — skip without breaking chain
            continue

        calc = _quarter_gm_yoy(cur_row, prior_row)
        if calc is None:
            # Insufficient data: not evaluable — skip without breaking chain
            continue

        # This quarter IS evaluable: any failure below breaks the chain.
        # Capture chain-break helper (resets peer_gate_fired to empty).
        def _reset_chain_if_started() -> None:
            nonlocal peer_gate_fired
            if peer_gate_fired:
                peer_gate_fired = []

        # (a) revenue YoY growth > 0
        if not calc["revenue_positive"]:
            _reset_chain_if_started()
            continue  # keep scanning older quarters

        # (b) gross-margin YoY change <= -100 bp
        if calc["gm_change_bp"] > _GM_DETERIORATION_THRESHOLD_BP:
            _reset_chain_if_started()
            continue  # keep scanning older quarters

        # Quarter satisfies (a)+(b): compute peer gate
        peer_n, peer_median_bp = _compute_peer_gm_changes(
            ticker, fy, fq, sector_peers_df, asof_ts
        )

        q_info = {
            "fiscal_year": fy,
            "fiscal_quarter": fq,
            "filed": str(cur_row["_filed_ts"].date()),
            "gm_change_bp": calc["gm_change_bp"],
            "gm_cur_pct": calc["gm_cur_pct"],
            "gm_prior_pct": calc["gm_prior_pct"],
            "rev_yoy_pct": calc["rev_yoy_pct"],
            "peer_n": peer_n,
            "peer_median_change_bp": peer_median_bp,
        }
        qualifying.append(q_info)

        # (c) peer gate: thin peers → unverifiable; resets chain (not observable)
        if peer_median_bp is None:
            q_info["peer_gate"] = "unverifiable_thin_peers"
            _reset_chain_if_started()
            continue

        # peer gate: peer median > company change + 50 bp
        company_plus_gap = calc["gm_change_bp"] + _PEER_GAP_BP
        if peer_median_bp > company_plus_gap:
            q_info["peer_gate"] = "fired"
            peer_gate_fired.append(q_info)
            # Early exit once we have 2 consecutive fired quarters
            if len(peer_gate_fired) >= 2:
                break
        else:
            # Sector-wide compression — peer gate does NOT fire; resets chain
            q_info["peer_gate"] = "suppressed_sector_wide"
            _reset_chain_if_started()
            continue  # keep scanning older quarters

    # Enforce fiscal adjacency: the two fired quarters must be exactly one fiscal
    # quarter apart (Q_k and Q_{k-1} in fiscal calendar).
    def _fiscally_adjacent(q_newer: dict, q_older: dict) -> bool:
        """True when q_newer is exactly one fiscal quarter after q_older."""
        fy_n, fq_n = q_newer["fiscal_year"], q_newer["fiscal_quarter"]
        fy_o, fq_o = q_older["fiscal_year"], q_older["fiscal_quarter"]
        if fq_n > 1:
            return fy_o == fy_n and fq_o == fq_n - 1
        # fq_n == 1: the previous quarter is Q4 of the prior year
        return fy_o == fy_n - 1 and fq_o == 4

    # Determine state
    # Unverifiable conditions:
    # 1. Thin peer coverage on the most recent qualifying quarter
    if qualifying:
        # Check if the most recent qualifying quarter has thin peers
        most_recent_q = qualifying[0]
        if most_recent_q.get("peer_gate") == "unverifiable_thin_peers":
            # peer_n for that quarter
            return _result(
                ticker, asof_str, "unverifiable",
                qualifying[:2],
                most_recent_q["peer_n"], most_recent_q["peer_median_change_bp"],
                coverage_n,
                reason=f"peer coverage thin (n={most_recent_q['peer_n']} < {_MIN_PEER_N})",
            )

    # Challenged: two consecutive (fiscally adjacent) peer_gate_fired quarters.
    # The chain-reset logic above ensures peer_gate_fired only holds contiguous
    # fired quarters; we still verify adjacency as a belt-and-suspenders guard.
    if len(peer_gate_fired) >= 2:
        q_newer, q_older = peer_gate_fired[0], peer_gate_fired[1]
        if _fiscally_adjacent(q_newer, q_older):
            two_quarters = [q_newer, q_older]
            recent_q = two_quarters[0]
            return _result(
                ticker, asof_str, "challenged",
                two_quarters,
                recent_q["peer_n"], recent_q["peer_median_change_bp"],
                coverage_n,
            )
        # Non-adjacent fired quarters: chain was not truly consecutive → not_observed

    # If <2 qualifying quarters at all — not_observed
    if coverage_n < 2 or len(qualifying) < 2:
        return _result(ticker, asof_str, "not_observed", qualifying[:2],
                       0, None, coverage_n)

    # One or zero peer_gate_fired quarters
    return _result(ticker, asof_str, "not_observed",
                   peer_gate_fired[:2] if peer_gate_fired else qualifying[:2],
                   qualifying[0]["peer_n"] if qualifying else 0,
                   qualifying[0].get("peer_median_change_bp") if qualifying else None,
                   coverage_n)


def _result(
    ticker: str,
    asof_date: str,
    state: str,
    trigger_quarters: list[dict],
    peer_n: int,
    peer_median_change_bp: float | None,
    coverage_n_quarters: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build a standardised result dict."""
    out: dict[str, Any] = {
        "ticker": ticker,
        "asof_date": asof_date,
        "state": state,
        "trigger_quarters": trigger_quarters,
        "peer_n": peer_n,
        "peer_median_change_bp": peer_median_change_bp,
        "coverage_n_quarters": coverage_n_quarters,
        "_display_only": _DISPLAY_ONLY,
        "_horizon_role": _HORIZON_ROLE,
        "_version": _VERSION,
        "_schema": _SCHEMA,
    }
    if reason is not None:
        out["_reason"] = reason
    return out


# ── standalone smoke-test ─────────────────────────────────────────────────────

def main() -> int:
    """Smoke-test: load statements_quarterly.parquet, run one ticker."""
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    try:
        from lib import config  # noqa: PLC0415
    except ImportError:
        print("Cannot import lib.config — run from repo root.", file=sys.stderr)
        return 1

    from lib.procutil import hard_exit  # noqa: PLC0415

    path = config.data_dir() / "edgar" / "statements_quarterly.parquet"
    if not path.exists():
        print(f"statements_quarterly not found: {path}", file=sys.stderr)
        return 1

    df = pd.read_parquet(path)

    # Load sector map
    sector_path = config.data_dir() / "breadth" / "ticker_sectors.parquet"
    sector_of: dict[str, str] = {}
    if sector_path.exists():
        sec_df = pd.read_parquet(sector_path)
        if "ticker" in sec_df.columns and "sector" in sec_df.columns:
            sector_of = dict(zip(sec_df["ticker"].astype(str), sec_df["sector"].astype(str)))

    ticker = ticker_arg.upper()
    sector = sector_of.get(ticker, "")
    if not sector:
        print(f"No sector for {ticker} — using all tickers as peers (not realistic)", file=sys.stderr)
        sector_peers = df
    else:
        sector_peers = df[df["ticker"].isin(
            [t for t, s in sector_of.items() if s == sector]
        )]

    ticker_df = df[df["ticker"] == ticker]
    result = compute_pricing_power_state(ticker, sector, ticker_df, sector_peers)
    print(json.dumps(result, indent=2, default=str))
    hard_exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
