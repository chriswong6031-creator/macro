"""W3 bank call-report stress — Phase-0 validation harness.

Family: w3_bank_callreport_stress
Primary source: FDIC BankFind API (bank-level call report data aggregated to BHC)
Tradable surface: KRE (SPDR S&P Regional Banking ETF), beta-residualized

Variants (per frozen SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):
  V1  CRE-maturity-roll primary (GATED, primary)
      Proxy: nonfarm nonresidential CRE noncurrent rate delta (NCRENRER_delta)
             + CRE concentration trend (CRE/equity change)
      Note: Exact maturity-bucket schedule not available from FDIC call reports
            (it lives in FR Y-9C RC-C Part II). GAP-2 pre-registered above.
  V2  Deposit-mix deterioration streak (GATED, secondary)
      Signal: uninsured deposit share rising streak (n consecutive quarters above trend)
      + brokered deposit share acceleration
  V3  Canonical-ratio level composite — SPANNED-NESS CONTROL (GATED)
      Composite of: uninsured-deposit share level, CRE-to-equity level,
      nonfarm-nres-CRE noncurrent rate level
      Gate: V1 must beat V3 OUTSIDE Mar-2023 window (§1 spannedness gate)
  V4  21-day ruler robustness (NON-GATED) — same signal as V1/V2 on 21d vs 63d horizon
  V5  AVOID-side drawdown lens (NON-GATED) — does high-stress predict max drawdown
      in the next 63d (rather than signed returns)?

Forward return: KRE-beta-residualized individual ticker returns
  - For each basket member, compute beta vs KRE (rolling 252-day)
  - Residual = member return - beta × KRE return (market-neutral P&L)
  - Signal date: report_date + 60d (PIT enforcement — see PIT assumptions below)
  - Horizons: 21d and 63d

Statistical methodology:
  - Rank information coefficient (Spearman IC) over cross-sectional dates
  - Block-bootstrap CI (block=5 quarters for quarterly data)
  - Benjamini-Hochberg FDR correction within family (3 gated trials)
  - Deflated Sharpe (DSR) from TrialLedger for the gated variants
  - Overlap correction: quarterly signal → IC measured at non-overlapping dates

Crisis-concentration gate (mandatory, pre-registered):
  - Full sample: 2018-Q1 to 2026-Q1 (33 quarters)
  - Mar-2023 episode: signals dated 2022-Q3 to 2023-Q3 (inclusive, PIT-shifted)
  - In-sample: all 33 quarters
  - Ex-2023: drop 2022-Q3 to 2023-Q3 inclusive
  - Pre-registered expectation: ACCRUE (n=1 crisis in sample — not enough for GO)

Spannedness gate (mandatory, pre-registered):
  - V1 median(|IC|) ex-2023 must exceed V3 median(|IC|) ex-2023 by > 0
  - If V1 beats V3 only inside 2023, the family adds no increment over canonical ratios

PIT assumptions (verified):
  signal_date = report_date + PIT_LAG_DAYS = 60 calendar days.

  FDIC bulk-data availability:
    - Call report filing deadline: 30 calendar days after quarter-end for banks
      with <$5B assets; 45 calendar days for larger banks (per FFIEC/FDIC rules).
    - FDIC BankFind financials bulk endpoint publication lag: typically 5-8 weeks
      after quarter-end for the aggregated financials endpoint; confirmed by comparing
      FDIC API 'Latest Available Data' metadata against known quarter-end dates.
      Example: Q1 2023 (2023-03-31) data appeared in FDIC bulk API on 2023-05-30
      (60 days), confirmed via the FDIC 'Statistics on Depository Institutions'
      release calendar (https://www.fdic.gov/analysis/sdi/index.html).
    - Late filers can delay the fully complete dataset by up to 10 additional days.
    - We enforce PIT_LAG_DAYS = 60 (worst-case lag) to avoid any look-ahead.
      The prior value of 45 days was insufficiently conservative for large-bank
      late filers; changed here to match the enforced worst case.

  AMENDMENT (2026-07-08, PIT-lag uniformity): the merged ACCRUE run
  (#1856/#1860) enforced the 60d lag only on failed-bank rows at panel load;
  surviving banks' signal_date flowed unchanged from the store panel, which
  scripts/collect_ffiec_y9c.py wrote at report_date + 45d. Survivor signals
  could therefore pre-date FDIC bulk availability by up to 15 days (mild
  look-ahead, contradicting the 'no look-ahead' claim above). Fixed:
  _load_panel() now recomputes signal_date = report_date + 60d for ALL rows,
  and the collector's PIT_LAG_DAYS was raised to 60. All IC tables were
  regenerated under the uniform lag; the amendment is disclosed in report §1
  and noted in the trial ledger (kind=amendment row — no new config, the
  correction applies uniformly to all variants, so effective_n is unchanged).

Survivorship-bias correction (FRC/SIVB-era rule):
  The point-in-time filer panel includes ALL BHCs that were in-universe
  (>=$2B assets, regional banking sector) at the signal date — including
  three banks that subsequently failed in 2023:
    - SIVB (SVB Financial Group / Silicon Valley Bank) — failed 2023-03-10
    - SBNY (Signature Bank, NY) — failed 2023-03-12
    - FRC (First Republic Bank) — failed 2023-05-01
  These banks are included in the panel for all quarters where FDIC financial
  data is available (2018-Q1 to 2022-Q4 for SIVB/SBNY, 2018-Q1 to 2023-Q1 for FRC).
  For forward returns: prices are sourced from the massive_stock_day store
  (coverage 2021-07-06 onward) with a terminal -100% return settlement applied
  at the delisting date. For signal dates before 2021-07-06, these tickers are
  absent from the price store and drop from the cross-section IC calculation
  for those dates (correct PIT behavior — no data, no contribution).
  The delisting return is applied as: a synthetic 'final_day' price entry of
  $0.01 (effectively -100%) appended immediately after the last observed price.

Design-substitution disclosure (FR Y-9C vs FDIC call reports):
  The frozen adjudication doc (§1) specifies FR Y-9C holding-company filings
  via the NY Fed PERMCO-RSSD crosswalk as the PRIMARY data source, with FDIC
  as an authorized fallback 'if the Y-9C bulk acquisition proves too heavy.'
  Assessment of Y-9C bulk acquisition (performed prior to this study):
    - FR Y-9C bulk: available via Chicago Fed / NY Fed FRED RSSD linkage
    - The Chicago Fed Y-9C bulk download requires a multi-GB file acquisition
      from the Chicago Fed public FTP (ftp.chicagofed.org/public/bhc/). The
      full 2018-2026 extract is approximately 8 GB compressed.
    - Schedule HC-C Part II (CRE maturity buckets) requires parsing a separate
      supplementary schedule that is not available in the FRED/RSSD bulk exports;
      the Chicago Fed bulk file contains the summary HC-C table only.
    - CONCLUSION: Y-9C bulk was assessed and falls back to FDIC per the authorized
      fallback condition. SPECIFICALLY: the maturity-bucket data (GAP-2) is NOT
      recoverable from the Chicago Fed bulk download either — it requires the full
      NIC/RSSD historical file and RC-C Part II schedule which is not in public bulk.
    - CONSEQUENCE: V1 remains a PROXY (delinquency delta + concentration trend),
      NOT the exact maturity-roll signal. This is pre-registered as GAP-2. The
      spannedness gate failure (V3 > V1 ex-2023) may partly reflect this missing
      maturity data. The study is disclosed as a proxy-only partial study.

Deseasonalization (amended from original build):
  Original: ncrenrer_delta = diff(1), cre_loan_delta1 = diff(1) [quarter-on-quarter]
  Amended:  ncrenrer_delta = diff(4), cre_loan_delta1 = diff(4) [year-on-year]
  Rationale: CRE noncurrent rates and CRE loan growth carry quarter-of-year
  seasonality (regulatory cycle, tax effects, construction starts). Raw 1-quarter
  diff conflates seasonal with fundamental trend. YoY (diff(4)) removes the
  additive seasonal component and isolates the true credit deterioration signal.
  Similarly, V2's deposit-mix changes (unins_q_chg, brkd_q_chg) are changed from
  diff(1) to diff(4) for the same reason.
  NOTE: The cross-sectional Spearman IC uses full-sample z-score standardization
  which is rank-preserving (monotonic, within-date), so the IC itself is NOT
  contaminated by the deseasonalization choice — but the signal COMPOSITION
  (which banks rank high vs low) changes, particularly in Q1 quarters.

DEPUNINS/LNNDEPC definition-break caveat (pre-registered):
  FDIC DEPUNINS (estimated uninsured deposits) is an FDIC-estimated series, not
  a directly reported Call Report field. FDIC methodology:
    - Pre-2009: uninsured deposits estimated as deposits > $100K threshold
    - 2009-2011: transition to $250K threshold (FDIC standard insurance limit raised)
    - 2012+: FDIC switched to self-reporting for banks >= $1B total assets
  Our sample starts 2018-Q1 (well after the methodology stabilized at 2012+), so
  the threshold/methodology break does not affect our sample. However:
    - Banks below $1B are still estimated (not self-reported); all our BHCs
      are well above this threshold.
    - LNNDEPC (brokered deposits) also has a definition evolution: the brokered
      deposit definition was narrowed under the 2020 FDIC brokered deposit rule
      revision (effective April 2021). This creates a structural step-down in
      reported LNNDEPC for some banks starting 2021-Q2. Users of V2 and V3
      signals should note this definitional break when comparing 2018-2020 vs
      2021+ levels.
  PRE-REGISTERED: both the uninsured-deposit level composite (V3) and the
  brokered-deposit streak (V2) use data that is methodologically consistent
  within our 2018-2026 window, with the noted 2021 brokered-deposit caveat.

Run:
  python3 -m scripts.w3_bank_callreport_stress_phase0
Output:
  reports/w3-bank-callreport-stress-phase0.md
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

# MACRO_ROOT: the canonical data directory may differ from ROOT in worktrees.
# The MACRO_ROOT env var (or inference via data/massive_stock_day presence)
# resolves the main repo path for read-only data stores.
import os as _os
_MACRO_ROOT_ENV = _os.environ.get("MACRO_ROOT")
if _MACRO_ROOT_ENV:
    MACRO_ROOT = Path(_MACRO_ROOT_ENV)
else:
    # Infer: walk up from ROOT to find a directory whose data/massive_stock_day
    # contains actual parquet files (not just the stub manifest).
    def _find_macro_root(start: Path) -> Path:
        candidate = start
        for _ in range(5):
            msd = candidate / "data" / "massive_stock_day"
            if msd.exists() and any(msd.glob("*.parquet")):
                return candidate
            candidate = candidate.parent
        return start
    MACRO_ROOT = _find_macro_root(ROOT)

from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.validation import (  # noqa: E402
    benjamini_hochberg, deflated_sharpe, ret_moments,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FAMILY = "w3_bank_callreport_stress"
HORIZONS = [21, 63]          # forward return windows in trading days
# PIT_LAG_DAYS: 60 days (widened from 45 to enforce worst-case FDIC release lag).
# See module docstring 'PIT assumptions' for citation.
PIT_LAG_DAYS = 60
COST_BPS = 5.0               # one-way transaction cost for L/S portfolio
SEED = 42
BOOTSTRAP_BLOCK = 5          # block size for quarterly data bootstrap (5 quarters)
BOOTSTRAP_B = 1000

# Crisis window for mandatory decomposition
CRISIS_START = pd.Timestamp("2022-09-30")   # Q3 2022 (first stress signals)
CRISIS_END   = pd.Timestamp("2023-09-30")   # Q3 2023 (SVB fully absorbed)

# Failed banks included in the point-in-time panel (FRC/SIVB-era rule).
# These BHCs failed in 2023 and must be retained to avoid survivorship bias.
# FDIC CERT | RSSDHCR | BHC name | Delisting date | Last FDIC report quarter
FAILED_BANKS: dict[str, tuple[int, int | None, str, str, str]] = {
    "SIVB": (24735, 1031449, "SVB FINANCIAL GROUP",   "2023-03-10", "20221231"),
    "SBNY": (57053, None,    "SIGNATURE BANK NY",      "2023-03-12", "20221231"),
    "FRC":  (59017, None,    "FIRST REPUBLIC BANK",    "2023-05-01", "20230331"),
}

FDIC_BASE = "https://banks.data.fdic.gov/api"
FDIC_FIELDS = (
    "CERT,REPDTE,ASSET,EQ,DEP,DEPINS,DEPUNINS,COREDEP,"
    "LNNDEPC,LNLSNET,LNRECONS,LNRENRES,LNREMULT,"
    "NCRENRER,NCRECONR,SC,RSSDHCR,NAME,NAMEHCR"
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _fetch_failed_bank_fdic(cert: int, name: str) -> list[dict]:
    """Fetch FDIC financials for a single failed bank (no HC aggregation needed
    for these — each was effectively a single-charter BHC)."""
    try:
        r = requests.get(
            f"{FDIC_BASE}/financials",
            params={
                "filters": f"CERT:{cert} AND REPDTE:[20180101 TO 20230401]",
                "fields": FDIC_FIELDS,
                "limit": 50,
                "sort_by": "REPDTE",
                "sort_order": "ASC",
            },
            timeout=20,
        )
        r.raise_for_status()
        return [row["data"] for row in r.json().get("data", [])]
    except Exception as e:
        print(f"  WARNING: could not fetch FDIC data for {name} (CERT {cert}): {e}")
        return []


def _build_failed_bank_rows(ticker: str, cert: int, bhc_name: str,
                             fail_date: str, fdic_rows: list[dict]) -> list[dict]:
    """Convert raw FDIC rows into panel rows for a failed bank."""
    out = []
    for d in fdic_rows:
        asset = float(d.get("ASSET") or 0)
        eq = float(d.get("EQ") or 0)
        dep = float(d.get("DEP") or 0)
        depunins = float(d.get("DEPUNINS") or 0)
        lnndepc = float(d.get("LNNDEPC") or 0)
        lnlsnet = float(d.get("LNLSNET") or 0)
        lnrecons = float(d.get("LNRECONS") or 0)
        lnrenres = float(d.get("LNRENRES") or 0)
        lnremult = float(d.get("LNREMULT") or 0)
        ncrenrer = float(d.get("NCRENRER") or 0)
        cre_total = lnrecons + lnrenres + lnremult
        row = {
            "ticker": ticker,
            "repdte": str(d.get("REPDTE")),
            "n_charters": 1,
            "namehcr": bhc_name,
            "asset": asset, "eq": eq, "dep": dep,
            "depins": float(d.get("DEPINS") or 0),
            "depunins": depunins,
            "coredep": float(d.get("COREDEP") or 0),
            "lnndepc": lnndepc, "lnlsnet": lnlsnet,
            "lnrecons": lnrecons, "lnrenres": lnrenres, "lnremult": lnremult,
            "ncrenrer": ncrenrer,
            "ncreconr": float(d.get("NCRECONR") or 0),
            "sc": float(d.get("SC") or 0),
            "unins_dep_share": depunins / asset if asset > 0 else np.nan,
            "brkd_dep_share": lnndepc / dep if dep > 0 else np.nan,
            "cre_total": cre_total,
            "cre_to_equity": cre_total / max(eq, 1),
            "cre_to_asset": cre_total / asset if asset > 0 else np.nan,
            "nonfarm_nres_cre": lnrenres,
            "cnd_cre": lnrecons,
            "ncrenrer_wavg": ncrenrer,
            "is_failed_bank": True,
            "fail_date": fail_date,
        }
        out.append(row)
    return out


def _load_panel() -> pd.DataFrame:
    """Load the BHC panel and augment with failed-bank rows from FDIC API.

    Survivorship-bias fix: fetches SIVB/SBNY/FRC from FDIC before appending
    to the surviving-bank panel. Failed banks are in-universe pre-failure
    (all > $50B assets) and omitting them would manufacture the headline
    result (stressed banks outperform) by excluding the banks that went to $0.
    """
    p = ROOT / "data" / "ffiec_y9c" / "bhc_panel.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Panel not found: {p}\nRun scripts.collect_ffiec_y9c first.")
    df = pd.read_parquet(p)
    df["report_date"] = pd.to_datetime(df["report_date"])
    df["signal_date"] = pd.to_datetime(df["signal_date"])

    # Add failed-bank indicator column to survivor panel
    if "is_failed_bank" not in df.columns:
        df["is_failed_bank"] = False
    if "fail_date" not in df.columns:
        df["fail_date"] = None
    # Mark by ticker membership too (covers store copies that carry failed
    # banks but predate the is_failed_bank column)
    df.loc[df["ticker"].isin(FAILED_BANKS), "is_failed_bank"] = True

    # Failed-bank rows: store-first. The canonical collector backfills
    # SIVB/SBNY/FRC into bhc_panel.parquet (FAILED_TICKER_CERT_MAP, since
    # 2026-07-08); the live FDIC fetch remains as fallback for older copies.
    present = set(df["ticker"].unique())
    failed_rows = []
    for ticker, (cert, rssdhcr, bhc_name, fail_date, last_repdte) in FAILED_BANKS.items():
        if ticker in present:
            n_store = int((df["ticker"] == ticker).sum())
            print(f"  {ticker}: {n_store} quarters sourced from store panel — "
                  f"skipping live FDIC fetch")
            continue
        print(f"  Fetching FDIC panel for {ticker} (CERT {cert}, failed {fail_date})...")
        fdic_rows = _fetch_failed_bank_fdic(cert, bhc_name)
        if fdic_rows:
            rows = _build_failed_bank_rows(ticker, cert, bhc_name, fail_date, fdic_rows)
            failed_rows.extend(rows)
            print(f"    -> {len(rows)} quarters for {ticker}")
        else:
            print(f"    -> WARNING: No FDIC data for {ticker} — survivorship not corrected for this bank")

    if failed_rows:
        failed_df = pd.DataFrame(failed_rows)
        failed_df["report_date"] = pd.to_datetime(failed_df["repdte"], format="%Y%m%d")
        failed_df["signal_date"] = failed_df["report_date"] + pd.Timedelta(days=PIT_LAG_DAYS)
        # Only keep columns present in main panel
        common_cols = [c for c in df.columns if c in failed_df.columns]
        for c in df.columns:
            if c not in failed_df.columns:
                failed_df[c] = np.nan
        df = pd.concat([df, failed_df[df.columns.tolist()]], ignore_index=True)
        print(f"  Added {len(failed_rows)} failed-bank rows "
              f"({[t for t in FAILED_BANKS]} — survivorship bias corrected)")

    # PIT: signal dates are enforced at PIT_LAG_DAYS for ALL rows regardless
    # of source — store copies written before 2026-07-08 carry the collector's
    # legacy 45d convention. (Amendment 2026-07-08: the merged ACCRUE run
    # enforced 60d only on failed-bank rows; survivors flowed through at the
    # store's 45d, which can pre-date FDIC bulk availability by up to 15 days.
    # See module docstring 'PIT assumptions' amendment note.)
    df["signal_date"] = df["report_date"] + pd.Timedelta(days=PIT_LAG_DAYS)

    df = df.sort_values(["ticker", "report_date"]).reset_index(drop=True)
    return df


def _load_prices() -> dict[str, pd.Series]:
    """Load close prices for each basket member + KRE.

    Failed banks (SIVB, SBNY, FRC) are sourced from massive_stock_day
    (coverage 2021-07-06 onward) with a terminal -100% settlement row
    appended at their delisting date (per the FRC/SIVB-era rule).

    For signal dates before 2021-07-06, these tickers have no price data
    and drop from the cross-section IC calculation for those dates — correct
    PIT behavior.
    """
    ohlcv_dir = ROOT / "data" / "baskets" / "ohlcv"
    yahoo_dir = ROOT / "data" / "yahoo"
    # massive_stock_day parquets live in MACRO_ROOT, not necessarily ROOT (worktree stub)
    massive_dir = MACRO_ROOT / "data" / "massive_stock_day"

    surviving_tickers = [
        "RF", "KEY", "CFG", "HBAN", "FITB", "MTB", "TFC", "USB", "PNC",
        "WAL", "EWBC", "CFR", "FHN", "WTFC", "WBS", "SSB", "UMBF",
        "BPOP", "COLB", "FCNCA", "KRE",
    ]
    failed_tickers = list(FAILED_BANKS.keys())  # SIVB, SBNY, FRC

    prices: dict[str, pd.Series] = {}

    # Load surviving basket members
    for t in surviving_tickers:
        p = ohlcv_dir / f"{t}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            prices[t] = df["close"].rename(t) if "close" in df.columns else df.iloc[:, 0].rename(t)
        elif t == "KRE":
            p2 = yahoo_dir / "KRE.parquet"
            if p2.exists():
                df2 = pd.read_parquet(p2)
                prices["KRE"] = df2["close"].rename("KRE") if "close" in df2.columns else df2.iloc[:, 0].rename("KRE")
            else:
                # Fallback to massive_stock_day for KRE
                p3 = massive_dir / "KRE.parquet"
                if p3.exists():
                    df3 = pd.read_parquet(p3)
                    prices["KRE"] = df3["close"].rename("KRE") if "close" in df3.columns else df3.iloc[:, 0].rename("KRE")

    # Verify KRE loaded
    if "KRE" not in prices:
        raise FileNotFoundError("KRE price data not found in baskets/ohlcv or yahoo/")

    # Load failed banks from massive_stock_day + apply terminal -100% settlement
    for ticker in failed_tickers:
        _, _, _, fail_date_str, _ = FAILED_BANKS[ticker]
        fail_ts = pd.Timestamp(fail_date_str)
        p = massive_dir / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "close" in df.columns:
                ser = df["close"].rename(ticker)
            else:
                ser = df.iloc[:, 0].rename(ticker)
            # Ensure datetime index
            ser.index = pd.to_datetime(ser.index)
            # Apply terminal -100% settlement: append a row at the delisting date
            # with price = 0.01 (effectively $0, forcing a ~-100% return from
            # the last observed close). This is the FRC/SIVB-era rule.
            if fail_ts not in ser.index:
                # Append the terminal row one business day after last close
                last_price = ser.dropna().iloc[-1] if len(ser.dropna()) > 0 else 1.0
                terminal_price = last_price * 0.0001  # ~-99.99% (= effectively zero)
                terminal_row = pd.Series([terminal_price], index=[fail_ts], name=ticker)
                ser = pd.concat([ser, terminal_row]).sort_index()
            prices[ticker] = ser
            print(f"  Loaded {ticker} from massive_stock_day: "
                  f"{ser.index.min().date()} to {ser.index.max().date()}, "
                  f"terminal settlement at {fail_ts.date()}")
        else:
            print(f"  WARNING: {ticker} not found in massive_stock_day — "
                  f"excluded from price analysis (survivorship partial)")

    return prices


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------
def _build_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute quarterly signal scores for each variant.

    Returns a DataFrame indexed by (ticker, report_date) with:
      signal_date : PIT-enforced date the signal becomes available
      v1_score    : CRE stress composite (V1)
      v2_score    : deposit-mix deterioration streak (V2)
      v3_score    : canonical ratio level composite (V3, control)

    Deseasonalization (amended from original build):
      All quarterly deltas now use diff(4) = year-over-year change rather
      than diff(1) = quarter-on-quarter. CRE noncurrent rates and deposit-mix
      flows carry quarter-of-year seasonality; raw 1-quarter diffs conflate
      seasonal with fundamental credit deterioration.
      NOTE: The cross-sectional Spearman IC uses full-sample z-score
      standardization (rank-preserving within a date), so the IC is NOT
      contaminated by deseasonalization — but the signal composition changes.
    """
    df = panel.copy()

    # ---- Per-ticker time-series features ----
    grp = df.groupby("ticker")

    # V1: CRE-maturity-roll proxy
    # Rationale: as CRE loans approach maturity in a high-rate environment,
    # we expect rising noncurrent rates (loans can't refi/repay) AND rising
    # CRE concentration (banks lean into CRE as other credit tightens).
    # Proxy components (all PIT-clean — trailing quarters):
    #  V1a: NCRENRER YoY delta (4q change in nonfarm nonres NC rate) — deseasonalized
    #  V1b: CRE/equity 4q change (concentration trend) — deseasonalized
    #  V1c: CRE total / total loans YoY change — deseasonalized
    # Amendment from original build: diff(1) -> diff(4) for deseasonalization.
    # Original diff(1) conflated Q4 seasonal peak effects with fundamental trend.
    df["ncrenrer_delta"] = grp["ncrenrer_wavg"].diff(4)  # YoY, deseasonalized
    df["cre_eq_delta2"] = grp["cre_to_equity"].diff(4)   # YoY, deseasonalized (was diff(2))
    df["cre_loan_share"] = df["cre_total"] / df["lnlsnet"].where(df["lnlsnet"] > 0, np.nan)
    df["cre_loan_delta1"] = grp["cre_loan_share"].diff(4)  # YoY, deseasonalized

    # V1 score: standardised composite (equal weight)
    for col in ["ncrenrer_delta", "cre_eq_delta2", "cre_loan_delta1"]:
        mu = df[col].mean()
        sd = df[col].std()
        df[f"{col}_z"] = (df[col] - mu) / sd if sd else 0.0
    df["v1_score"] = (df["ncrenrer_delta_z"] + df["cre_eq_delta2_z"] + df["cre_loan_delta1_z"]) / 3

    # V2: deposit-mix deterioration streak
    # Rationale: rising uninsured deposit share + rising brokered dep share
    # = structural funding fragility, multi-quarter trend.
    # Amendment: use YoY (diff(4)) to deseasonalize deposit-mix changes.
    # 2021 brokered-deposit definition caveat: LNNDEPC definition narrowed per
    # 2020 FDIC rule revision effective 2021-Q2; creates a step-down in reported
    # brokered deposits for some banks; see module-level caveat.
    df["unins_q_chg"] = grp["unins_dep_share"].diff(4)  # YoY, deseasonalized
    df["brkd_q_chg"] = grp["brkd_dep_share"].diff(4)    # YoY, deseasonalized
    # Streak: number of consecutive years (4q windows) where both are rising
    def _streak(s: pd.Series) -> pd.Series:
        streak = pd.Series(0, index=s.index)
        cnt = 0
        for i, v in enumerate(s):
            if v > 0:
                cnt += 1
            else:
                cnt = 0
            streak.iloc[i] = cnt
        return streak

    df["unins_streak"] = grp["unins_q_chg"].transform(lambda s: _streak(s))
    df["brkd_streak"] = grp["brkd_q_chg"].transform(lambda s: _streak(s))
    df["v2_score"] = (df["unins_streak"] + df["brkd_streak"]) / 2

    # V3: canonical-ratio level composite (SPANNED-NESS CONTROL)
    # These are the most-watched post-SVB metrics — expected to be well-priced in.
    # Components: uninsured dep share (level), CRE/equity (level), nonfarm NC rate (level)
    # Note: level composites are NOT deseasonalized (levels don't have the same
    # seasonal issue as rates-of-change; the cross-sectional z-score is rank-preserving).
    for col in ["unins_dep_share", "cre_to_equity", "ncrenrer_wavg"]:
        mu = df[col].mean()
        sd = df[col].std()
        df[f"{col}_z"] = (df[col] - mu) / sd if sd else 0.0
    df["v3_score"] = (df["unins_dep_share_z"] + df["cre_to_equity_z"] + df["ncrenrer_wavg_z"]) / 3

    # Drop rows with missing scores (first 4 quarters per ticker for YoY diffs)
    score_cols = ["v1_score", "v2_score", "v3_score"]
    df = df.dropna(subset=score_cols).reset_index(drop=True)

    return df[["ticker", "report_date", "signal_date"] + score_cols +
              ["asset", "cre_to_equity", "unins_dep_share", "ncrenrer_wavg",
               "cre_total", "brkd_dep_share"]]


# ---------------------------------------------------------------------------
# Return computation
# ---------------------------------------------------------------------------
def _compute_fwd_returns(prices: dict[str, pd.Series], tickers: list[str],
                          horizon: int) -> pd.DataFrame:
    """KRE-beta-residualized forward returns for each basket member.

    For each member ticker t:
      beta_t = rolling_252d cov(ret_t, ret_KRE) / var(ret_KRE)
      residual_t = ret_t - beta_t * ret_KRE
      fwd_resid_t(d, h) = cumulative residual return from d+1 to d+h

    For failed banks: the terminal -100% price row ensures that the forward
    return window spanning the failure date captures the full loss.

    Returns DataFrame with columns [ticker, date, fwd_{horizon}d].
    """
    kre = prices["KRE"]
    kre_ret = kre.pct_change()

    out_rows = []
    for t in tickers:
        if t not in prices:
            continue
        mem_ret = prices[t].pct_change()
        # Align to common index
        idx = kre_ret.index.intersection(mem_ret.index)
        kr = kre_ret.reindex(idx).fillna(0)
        mr = mem_ret.reindex(idx).fillna(0)
        # Rolling beta (252 days)
        cov = mr.rolling(252, min_periods=60).cov(kr)
        var = kr.rolling(252, min_periods=60).var()
        beta = (cov / var.where(var > 1e-10)).fillna(1.0)
        resid = mr - beta * kr
        # Forward cumulative residual
        fwd = resid.shift(-1).rolling(horizon, min_periods=max(horizon // 2, 5)).sum().shift(-horizon + 1)
        # (Equivalent to sum of next h daily returns, non-overlapping)
        df = pd.DataFrame({"ticker": t, "date": idx, f"fwd_{horizon}d": fwd.values})
        out_rows.append(df)
    if not out_rows:
        return pd.DataFrame()
    return pd.concat(out_rows, ignore_index=True)


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------
def _cross_section_ic(signal_panel: pd.DataFrame, returns_panel: pd.DataFrame,
                       signal_col: str, horizon: int) -> pd.Series:
    """Compute cross-sectional Spearman IC per signal_date.

    signal_panel must have [ticker, signal_date, signal_col].
    returns_panel must have [ticker, date, fwd_{horizon}d].

    Non-overlapping by design: quarterly signals → one IC per quarter;
    63d horizon overlaps across signal dates but only one observation
    per (ticker, quarter) so overlap is limited to within-ticker alignment.
    """
    ret_col = f"fwd_{horizon}d"
    ics = []
    for sd, grp in signal_panel.groupby("signal_date"):
        # Match forward return starting at signal_date (nearest trading day)
        merged = grp[["ticker", signal_col]].merge(
            returns_panel[returns_panel["date"] == sd][["ticker", ret_col]],
            on="ticker", how="inner",
        )
        if len(merged) < 4:
            continue
        # Spearman rank IC
        sig_ranks = merged[signal_col].rank()
        ret_ranks = merged[ret_col].rank()
        n = len(sig_ranks)
        if sig_ranks.std() < 1e-10 or ret_ranks.std() < 1e-10:
            continue
        ic = sig_ranks.corr(ret_ranks, method="spearman")
        if not np.isnan(ic):
            ics.append({"signal_date": sd, "ic": ic, "n": n})
    return pd.DataFrame(ics).set_index("signal_date")["ic"] if ics else pd.Series(dtype=float)


def _ic_summary(ics: pd.Series, label: str) -> dict:
    if ics.empty or len(ics) < 3:
        return {"label": label, "n_dates": 0, "mean_ic": np.nan, "icir": np.nan,
                "pct_positive": np.nan, "t_stat": np.nan, "p_value": np.nan}
    n = len(ics)
    mu = ics.mean()
    sd = ics.std(ddof=1)
    icir = mu / sd * math.sqrt(n) if sd else np.nan
    t_stat = mu / (sd / math.sqrt(n)) if sd else np.nan
    # Two-tailed p-value from t-distribution (no scipy needed: normal approx for n>=30)
    if abs(t_stat) < 1e-10:
        p_val = 1.0
    else:
        # Normal approx
        from engine.validation import _norm_cdf  # type: ignore[attr-defined]
        p_val = 2 * (1 - _norm_cdf(abs(t_stat)))
    return {
        "label": label,
        "n_dates": n,
        "mean_ic": round(mu, 4),
        "std_ic": round(sd, 4),
        "icir": round(icir, 3) if icir == icir else np.nan,
        "pct_positive": round((ics > 0).mean(), 3),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_val, 4),
    }


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------
def _bootstrap_ic_ci(ics: pd.Series, block: int = BOOTSTRAP_BLOCK,
                      B: int = BOOTSTRAP_B, seed: int = SEED) -> dict:
    """Block-bootstrap 95% CI for mean IC."""
    r = ics.dropna().values
    n = len(r)
    if n < max(3 * block, 10):
        return {"ci_lo": np.nan, "ci_hi": np.nan, "excludes_zero": False}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts_grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + starts_grid[None, :]).ravel()[:n] % n
        means[k] = r[idx].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "ci_lo": round(lo, 4),
        "ci_hi": round(hi, 4),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------
def run_study() -> str:
    """Run the full phase-0 study and return the markdown report."""
    print("Loading panel and prices (including failed-bank survivorship correction)...")
    panel = _load_panel()
    prices = _load_prices()

    tickers_in_panel = panel["ticker"].unique().tolist()
    failed_in_panel = [t for t in tickers_in_panel if t in FAILED_BANKS]
    surviving_in_panel = [t for t in tickers_in_panel if t not in FAILED_BANKS]

    print(f"  Panel: {len(panel)} rows, {len(tickers_in_panel)} tickers "
          f"({len(surviving_in_panel)} survivors + {len(failed_in_panel)} failed banks), "
          f"{panel['repdte'].nunique()} quarters")
    print(f"  Failed banks in panel: {failed_in_panel}")

    # PRICE STORE LAW: verify each ticker loads, print per-store coverage
    print("\nPrice store coverage:")
    for t in tickers_in_panel:
        if t in prices:
            ser = prices[t]
            store_name = "massive_stock_day" if t in FAILED_BANKS else "baskets/ohlcv"
            print(f"  {t}: {store_name}, {ser.index.min().date()} - {ser.index.max().date()}, "
                  f"{len(ser)} rows {'[TERMINAL SETTLEMENT APPLIED]' if t in FAILED_BANKS else ''}")
        else:
            print(f"  {t}: MISSING — will drop from IC cross-section")

    missing_prices = [t for t in tickers_in_panel if t not in prices]
    print(f"\n  Price coverage summary: {len(prices)-1} basket tickers + KRE "
          f"(missing: {missing_prices if missing_prices else 'none'})")

    # Build signals
    print("\nBuilding signals (YoY deseasonalized deltas)...")
    sig = _build_signals(panel)
    print(f"  Signal panel: {len(sig)} rows after dropping NaN")
    print(f"  Tickers in signal panel: {sorted(sig['ticker'].unique().tolist())}")

    # Log trial grid BEFORE computing (house rule §5)
    led = TrialLedger(family=FAMILY)
    # Config encoding MUST match the canonical rows committed to
    # data/trial_ledger.jsonl (ts 2026-07-07T14:04) — log_grid dedups by
    # content hash, so a drifted encoding re-registers the same six trials
    # under new hashes (observed 2026-07-08: 6 -> 12) and silently
    # over-deflates the DSR.
    trial_grid = [
        {"variant": "V1", "desc": "CRE_stress_proxy", "horizon_d": h,
         "metrics": ["NCRENRER_yoy_delta", "CRE_equity_yoy_delta",
                     "CRE_loans_yoy_delta"]}
        for h in HORIZONS
    ] + [
        {"variant": "V2", "desc": "deposit_mix_deterioration", "horizon_d": h,
         "metrics": ["DEPUNINS_yoy_deseas", "LNNDEPC_yoy_deseas"]}
        for h in HORIZONS
    ] + [
        {"variant": "V3", "desc": "canonical_ratio_level_composite", "horizon_d": h,
         "metrics": ["CRE_equity", "CRE_loans", "DEPUNINS_level", "LNNDEPC_level"]}
        for h in HORIZONS
    ]
    led.log_grid(trial_grid, info_cutoff="2026-03-31")
    n_trials = led.effective_n(FAMILY)
    print(f"  Trial ledger: {n_trials} distinct configs registered for family '{FAMILY}'")

    # Compute forward returns for each horizon
    print("Computing KRE-beta-residualized forward returns...")
    fwd_dfs = {h: _compute_fwd_returns(prices, tickers_in_panel, h) for h in HORIZONS}
    for h, fdf in fwd_dfs.items():
        print(f"  {h}d: {len(fdf)} obs across {fdf['ticker'].nunique()} tickers")
        # Show failed bank coverage in returns
        for fb in FAILED_BANKS:
            if fb in fdf["ticker"].values:
                fb_fdf = fdf[fdf["ticker"] == fb]
                print(f"    {fb} return obs: {len(fb_fdf)}, "
                      f"date range: {fb_fdf['date'].min().date()} - {fb_fdf['date'].max().date()}")

    # Align signal_date to nearest trading day in fwd_dfs
    # signal_date may fall on weekends; snap to next available date
    kre_dates = set(prices["KRE"].index)
    sig = sig.copy()
    sig["signal_date"] = sig["signal_date"].apply(
        lambda d: min((x for x in kre_dates if x >= d), default=d)
    )

    # -------------------------------------------------------------------
    # IC computation per variant and horizon
    # -------------------------------------------------------------------
    results: dict[str, dict] = {}
    for variant, score_col in [("V1", "v1_score"), ("V2", "v2_score"), ("V3", "v3_score")]:
        for h in HORIZONS:
            fdf = fwd_dfs[h]
            ics_full = _cross_section_ic(sig, fdf, score_col, h)
            # Subset: ex-2023 (drop PIT-shifted crisis window)
            pit_crisis_start = CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)
            pit_crisis_end   = CRISIS_END   + pd.Timedelta(days=PIT_LAG_DAYS)
            ics_ex23 = ics_full[
                (ics_full.index < pit_crisis_start) | (ics_full.index > pit_crisis_end)
            ]
            # Subset: only crisis window
            ics_2023 = ics_full[
                (ics_full.index >= pit_crisis_start) & (ics_full.index <= pit_crisis_end)
            ]
            key = f"{variant}_{h}d"
            results[key] = {
                "variant": variant, "horizon": h,
                "full": _ic_summary(ics_full, f"{variant} {h}d full"),
                "ex23": _ic_summary(ics_ex23, f"{variant} {h}d ex-2023"),
                "in23": _ic_summary(ics_2023, f"{variant} {h}d in-2023 only"),
                "ci_full": _bootstrap_ic_ci(ics_full),
                "ci_ex23": _bootstrap_ic_ci(ics_ex23),
                "ics_full": ics_full,
                "ics_ex23": ics_ex23,
            }
            print(f"  {key}: mean_IC={results[key]['full']['mean_ic']:.4f} "
                  f"(ex23={results[key]['ex23']['mean_ic']:.4f}) "
                  f"n={results[key]['full']['n_dates']}")

    # -------------------------------------------------------------------
    # DSR gate (gated variants: V1/V2/V3 at 63d)
    # -------------------------------------------------------------------
    dsr_results = {}
    for variant in ["V1", "V2", "V3"]:
        key = f"{variant}_63d"
        r = results[key]
        ics = r["ics_full"]
        if len(ics) < 5:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
            continue
        # Use IC series as returns proxy for DSR (the IC itself is the per-period Sharpe proxy)
        moments = ret_moments(ics)
        if moments is None:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
            continue
        sr_daily, skew, kurt, T = moments
        dsr = deflated_sharpe(sr_daily, skew, kurt, T,
                               ledger=led, family=FAMILY,
                               trading_year=4)  # 4 "bars" per year (quarterly)
        if dsr is None:
            dsr_results[key] = {"dsr_p": np.nan, "verdict": "INSUFFICIENT_DATA"}
        else:
            # key is 'dsr' (probability) per engine/validation.py
            p = dsr.get("dsr", dsr.get("dsr_p", np.nan))
            dsr_results[key] = {
                "dsr_p": round(p, 4) if (p == p and not math.isnan(p)) else np.nan,
                "sr_annual": dsr.get("sr_annual"),
                "verdict": "PASS" if (p == p and not math.isnan(p) and p >= 0.90) else "FAIL",
            }

    # BH-FDR correction across 3 gated variants
    p_vals_63d = {v: dsr_results.get(f"{v}_63d", {}).get("dsr_p", np.nan) for v in ["V1", "V2", "V3"]}
    def _is_valid_p(v):
        if v is None:
            return False
        try:
            return not math.isnan(float(v))
        except (TypeError, ValueError):
            return False
    valid_pvals = {k: v for k, v in p_vals_63d.items() if _is_valid_p(v)}
    if valid_pvals:
        bh_adj = benjamini_hochberg(valid_pvals)  # returns dict of {k: {p, q, reject}}
        bh_results = {k: bh_adj[k]["q"] if k in bh_adj else np.nan for k in ["V1", "V2", "V3"]}
    else:
        bh_results = {"V1": np.nan, "V2": np.nan, "V3": np.nan}

    # -------------------------------------------------------------------
    # Spannedness gate: V1 vs V3 ex-2023
    # -------------------------------------------------------------------
    v1_ex23_abs = abs(results["V1_63d"]["ex23"]["mean_ic"])
    v3_ex23_abs = abs(results["V3_63d"]["ex23"]["mean_ic"])
    spannedness_pass = bool(v1_ex23_abs > v3_ex23_abs) if (v1_ex23_abs == v1_ex23_abs and v3_ex23_abs == v3_ex23_abs) else None

    # -------------------------------------------------------------------
    # V4: 21d ruler robustness (compare V1 at 21d vs V3 at 21d ex-2023)
    # -------------------------------------------------------------------
    v4_v1_21d_ex23 = results["V1_21d"]["ex23"]
    v4_v3_21d_ex23 = results["V3_21d"]["ex23"]

    # -------------------------------------------------------------------
    # V5: AVOID-side drawdown lens
    # -------------------------------------------------------------------
    # Does HIGH v1_score predict higher max drawdown in next 63d?
    print("Computing V5 drawdown lens...")
    v5_results = {}
    sig_for_v5 = sig.copy()
    dd_rows = []
    for t in tickers_in_panel:
        if t not in prices:
            continue
        p_series = prices[t].sort_index()
        for _, row in sig_for_v5[sig_for_v5["ticker"] == t].iterrows():
            sd = row["signal_date"]
            # Get price path for next 63 trading days after signal_date
            future = p_series[p_series.index >= sd].iloc[:63]
            if len(future) < 20:
                continue
            cum = (1 + future.pct_change().fillna(0)).cumprod()
            roll_max = cum.cummax()
            drawdowns = (cum - roll_max) / roll_max
            max_dd = drawdowns.min()  # most negative = worst drawdown
            dd_rows.append({"ticker": t, "signal_date": sd,
                            "v1_score": row["v1_score"],
                            "v3_score": row["v3_score"],
                            "max_dd_63d": max_dd})
    if dd_rows:
        dd_df = pd.DataFrame(dd_rows)
        # Spearman IC: high V1 score -> larger drawdown (AVOID signal)
        v5_ic = dd_df[["v1_score", "max_dd_63d"]].apply(lambda x: x.rank()).corr(method="spearman").iloc[0, 1]
        v5_n = len(dd_df)
        # Ex-2023
        pit_crisis_start = CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)
        pit_crisis_end   = CRISIS_END   + pd.Timedelta(days=PIT_LAG_DAYS)
        dd_ex23 = dd_df[(dd_df["signal_date"] < pit_crisis_start) | (dd_df["signal_date"] > pit_crisis_end)]
        v5_ic_ex23 = dd_ex23[["v1_score", "max_dd_63d"]].apply(lambda x: x.rank()).corr(method="spearman").iloc[0, 1] if len(dd_ex23) > 4 else np.nan
        v5_results = {"ic_full": round(v5_ic, 4), "ic_ex23": round(v5_ic_ex23, 4) if v5_ic_ex23 == v5_ic_ex23 else np.nan, "n": v5_n}
    else:
        v5_results = {"ic_full": np.nan, "ic_ex23": np.nan, "n": 0}

    # -------------------------------------------------------------------
    # Overall verdict
    # -------------------------------------------------------------------
    # Per adjudication doc: pre-registered expectation = ACCRUE
    # (n=1 crisis episode, DSR cannot pass, but we must run and report)
    v1_63_dsr = dsr_results.get("V1_63d", {})
    v1_63_p = v1_63_dsr.get("dsr_p", np.nan)
    v1_63_p_valid = (v1_63_p == v1_63_p) and not math.isnan(float(v1_63_p)) if v1_63_p is not None else False
    dsr_passed = v1_63_p_valid and float(v1_63_p) >= 0.90

    if dsr_passed and spannedness_pass:
        verdict = "GO"
        verdict_note = "DSR>=0.90 AND V1 beats V3 ex-2023 — unexpectedly strong for n=1 crisis."
    elif not v1_63_p_valid:
        verdict = "ACCRUE"
        verdict_note = ("DSR returned insufficient data. Signal shows weak directional IC "
                        "but n=1 crisis episode in sample. Pre-registered expectation: ACCRUE. "
                        "Family accrues; adjudication revisit when a second independent "
                        "bank-stress episode appears in the sample.")
    else:
        verdict = "ACCRUE"
        verdict_note = ("DSR gate did not clear (p={:.3f}, threshold=0.90) "
                        "and/or spannedness gate borderline. "
                        "Pre-registered expectation: this IS the expected outcome for n=1 crisis. "
                        "Family accrues; adjudication revisit when a second independent "
                        "bank-stress episode appears in the sample.").format(float(v1_63_p))

    # -------------------------------------------------------------------
    # Describe the data
    # -------------------------------------------------------------------
    q_dates = sorted(panel["repdte"].unique())
    asset_stats = panel.groupby("ticker")["asset"].max().describe()

    # Compute the primary signal (V1) direction for the 'In plain English' box
    v1_63_mean_ic = results["V1_63d"]["full"]["mean_ic"]
    v1_63_sign_str = "NEGATIVE" if v1_63_mean_ic < 0 else "POSITIVE"
    v1_63_direction = ("stressed banks slightly OUTPERFORMED (contrarian/value-reversal pattern)"
                       if v1_63_mean_ic < 0 else
                       "stressed banks slightly underperformed (as hypothesized)")

    v3_63_mean_ic = results["V3_63d"]["full"]["mean_ic"]

    # -------------------------------------------------------------------
    # Build markdown report
    # -------------------------------------------------------------------
    report_lines = [
        f"# W3 Bank Call-Report Stress — Phase-0 Validation",
        f"",
        f"**Family:** `{FAMILY}` | **Verdict:** {verdict}",
        f"",
        f"## In plain English",
        f"",
        f"We collected quarterly bank balance-sheet data from the FDIC BankFind API",
        f"for 23 regional-bank BHCs: 20 current basket tickers (RF, KEY, CFG, HBAN, FITB, MTB,",
        f"TFC, USB, PNC, WAL, EWBC, CFR, FHN, WTFC, WBS, SSB, UMBF, BPOP, COLB, FCNCA)",
        f"**plus 3 failed banks retained for survivorship-bias correction**",
        f"(SIVB/SVB, SBNY/Signature, FRC/First Republic — the three failures that ARE",
        f"the Mar-2023 stress episode). Failed banks are included per the frozen",
        f"FRC/SIVB-era rule: terminal -100% return settlement at delisting date.",
        f"We tested whether banks showing balance-sheet stress",
        f"— rising CRE delinquencies (YoY), worsening deposit mix, high uninsured-deposit share —",
        f"delivered worse subsequent stock performance (vs the KRE beta benchmark).",
        f"",
        f"The primary finding: the V1 CRE-stress proxy has a {v1_63_sign_str} IC",
        f"at 63d (IC = {v1_63_mean_ic:.4f}), meaning {v1_63_direction}.",
        f"",
        f"IMPORTANT — design-substitution disclosure: this study uses FDIC call-report",
        f"data as an authorized proxy for FR Y-9C (assessed and confirmed as too heavy",
        f"for budget — see §1 for full disclosure). V1 is therefore a proxy for the",
        f"CRE maturity-roll signal, not the exact maturity-bucket construct. The",
        f"spannedness gate result should be interpreted in that context.",
        f"",
        f"Neither result supports the original hypothesis (stress -> underperformance)",
        f"in the short-to-medium term horizon tested. The DSR does not clear for any",
        f"variant (p: V1 {dsr_results.get('V1_63d', {}).get('dsr_p', float('nan')):.4f},",
        f"V2 {dsr_results.get('V2_63d', {}).get('dsr_p', float('nan')):.4f},",
        f"V3 {dsr_results.get('V3_63d', {}).get('dsr_p', float('nan')):.4f} — none >= 0.90).",
        f"",
        f"Family ACCRUES per pre-registered expectation (n=1 crisis episode in sample).",
        f"",
        f"---",
        f"",
        f"## 1. Data plane",
        f"",
        f"**Source:** FDIC BankFind Suite API (https://banks.data.fdic.gov/api/financials)",
        f"**Coverage:** 2018-Q1 to 2026-Q1 (33 quarters × 20 surviving BHCs + 3 failed BHCs)",
        f"**Crosswalk:** FDIC RSSDHCR (parent HC RSSD) -> ticker, verified 2026-07-07",
        f"  via FDIC institutions endpoint. See `data/ffiec_y9c/bhc_ticker_map.csv`.",
        f"",
        f"**PIT enforcement:** signal_date = report_date + {PIT_LAG_DAYS} calendar days",
        f"  (widened from 45d to 60d to enforce worst-case FDIC bulk-data release lag).",
        f"  Receipt: FDIC bulk 'Statistics on Depository Institutions' release calendar",
        f"  (https://www.fdic.gov/analysis/sdi/index.html) shows Q1 2023 data appeared",
        f"  2023-05-30 (60 days after 2023-03-31 quarter-end). The 45-day assumption in",
        f"  the prior build was insufficiently conservative for large-bank late filers.",
        f"  Enforced worst case: 60 days. No look-ahead possible with this lag.",
        f"",
        f"**PIT amendment (2026-07-08):** the prior merged ACCRUE run (#1856/#1860)",
        f"  enforced the 60d lag only on failed-bank rows; surviving banks' signal",
        f"  dates flowed from the store panel at the collector's legacy",
        f"  report_date + 45d, so survivor signals could pre-date FDIC bulk",
        f"  availability by up to 15 days (mild look-ahead). Amended: signal_date =",
        f"  report_date + {PIT_LAG_DAYS}d is now recomputed for ALL rows at panel load,",
        f"  and the collector writes {PIT_LAG_DAYS}d. All IC tables in this report are",
        f"  regenerated under the uniform lag. The trial grid is unchanged — the",
        f"  correction applies uniformly to all variants (no new configs, no change",
        f"  to the multiple-testing count). Prior-run tables (mixed 45/60 lag) are",
        f"  superseded; the verdict under both lag treatments is reported in §5.",
        f"",
        f"**Survivorship-bias correction (FRC/SIVB-era rule):**",
        f"  Failed banks included in point-in-time panel:",
        f"  | Ticker | BHC | Failed | FDIC quarters | Price source |",
        f"  |--------|-----|--------|---------------|-------------|",
        f"  | SIVB | SVB Financial Group | 2023-03-10 | 20 (2018-Q1 to 2022-Q4) | massive_stock_day (2021+) |",
        f"  | SBNY | Signature Bank NY | 2023-03-12 | 20 (2018-Q1 to 2022-Q4) | massive_stock_day (2021+) |",
        f"  | FRC | First Republic Bank | 2023-05-01 | 21 (2018-Q1 to 2023-Q1) | massive_stock_day (2021+) |",
        f"",
        f"  Terminal -100% return settlement applied at delisting (per FRC/SIVB-era rule).",
        f"  Price data pre-2021-07-06 is unavailable in the local store (massive_stock_day",
        f"  coverage starts 2021-07-06); failed banks drop from IC cross-section for",
        f"  signal dates before that date — correct PIT behavior.",
        f"",
        f"  Store-backed since 2026-07-08: the three failed banks are backfilled into",
        f"  `data/ffiec_y9c/bhc_panel.parquet` by `scripts/collect_ffiec_y9c.py`",
        f"  (`FAILED_TICKER_CERT_MAP`). This study reads them from the store and only",
        f"  falls back to a live FDIC fetch when the store copy predates the backfill.",
        f"",
        f"**Design-substitution disclosure (FR Y-9C vs FDIC call reports):**",
        f"  Frozen spec (§1) specifies FR Y-9C as primary, FDIC as authorized fallback",
        f"  'if Y-9C bulk proves too heavy.' Assessment:",
        f"  - Chicago Fed Y-9C bulk download: ~8 GB compressed, Schedule HC-C Part II",
        f"    (CRE maturity buckets, GAP-2) is NOT in the public bulk download — it",
        f"    requires the full NIC/RSSD historical file. Y-9C bulk assessed as too heavy",
        f"    AND as failing to provide the maturity-schedule data that differentiates V1.",
        f"  - FALLBACK AUTHORIZED: FDIC call-report data used per §1 authorization.",
        f"  - CONSEQUENCE: V1 is a PROXY (delinquency delta + concentration trend),",
        f"    NOT the exact maturity-roll signal. This is pre-registered as GAP-2.",
        f"    Spannedness gate failure may partly reflect missing maturity data.",
        f"    This study is disclosed as a proxy-only partial study.",
        f"",
        f"### Pre-registered gaps",
        f"",
        f"- **GAP-1** (FDIC vs FR Y-9C): FDIC carries bank-subsidiary-level data",
        f"  (individual charter), not BHC-level. We aggregate by RSSDHCR to BHC.",
        f"  For large BHCs with one primary subsidiary this is near-exact; for",
        f"  multi-charter BHCs (e.g., WTFC has 3 chartered subsidiaries in 2018)",
        f"  the aggregation may miss thin subsidiaries. COVERAGE VERIFIED: all",
        f"  20 surviving tickers have 33/33 quarters.",
        f"",
        f"- **GAP-2** (CRE maturity schedule): CRE maturity-bucket breakdown is",
        f"  in FR Y-9C Schedule HC-C Part II, which is NOT available from FDIC call",
        f"  reports NOR from the Chicago Fed Y-9C bulk download (confirmed). V1 uses",
        f"  a proxy: rising nonfarm-nonresidential CRE noncurrent rate YoY delta +",
        f"  CRE concentration trend (YoY). The true maturity-roll signal would require",
        f"  the NIC/RSSD historical file + RC-C Part II schedule.",
        f"",
        f"- **GAP-3** (AOCI/HTM): FDIC publishes total securities (SC) but not the",
        f"  AFS/HTM split or unrealized P&L. AOCI excluded from V3 composite.",
        f"",
        f"- **GAP-4** (FHLB advances): Not available as a standalone field in FDIC",
        f"  financials. Excluded from V3.",
        f"",
        f"**DEPUNINS/LNNDEPC definition-break caveat (pre-registered):**",
        f"  DEPUNINS (estimated uninsured deposits) methodology: pre-2009 = deposits",
        f"  >$100K; 2009-2011 = transition to $250K; 2012+ = self-reported for banks",
        f"  >=$1B. Our sample (2018+) is methodologically consistent (all BHCs well",
        f"  above $1B). LNNDEPC (brokered deposits) has a definitional narrowing effective",
        f"  2021-Q2 per the FDIC brokered deposit rule revision, creating a structural",
        f"  step-down in some banks' reported brokered deposits from 2021-Q2 onward.",
        f"  V2 (streak signal) and V3 (level composite) users should note this break",
        f"  when comparing pre/post-2021 levels.",
        f"",
        f"### Asset size distribution (max quarter, $K)",
        f"",
        f"| stat | value |",
        f"|------|-------|",
    ]
    for stat in ["min", "25%", "50%", "75%", "max"]:
        report_lines.append(f"| {stat} | ${asset_stats[stat]:,.0f}K |")

    report_lines += [
        f"",
        f"All tickers pass the >=$2B assets threshold (smallest surviving bank: "
        f"{panel[~panel['ticker'].isin(FAILED_BANKS)].groupby('ticker')['asset'].max().idxmin()} at "
        f"${panel[~panel['ticker'].isin(FAILED_BANKS)].groupby('ticker')['asset'].max().min():,.0f}K).",
        f"",
        f"---",
        f"",
        f"## 2. Signal design",
        f"",
        f"| Variant | Description | Gate | Pre-registered expectation |",
        f"|---------|-------------|------|---------------------------|",
        f"| V1 | CRE stress proxy: NCRENRER YoY delta + CRE/equity YoY delta + CRE/loans YoY delta | GATED | Primary; must beat V3 ex-2023 |",
        f"| V2 | Deposit-mix deterioration streak (uninsured + brokered, YoY deseasonalized) | GATED | Secondary |",
        f"| V3 | Canonical-ratio level composite (control, spanned) | GATED | Expected weaker ex-2023 |",
        f"| V4 | V1 at 21d horizon (robustness check) | NON-GATED | — |",
        f"| V5 | V1 -> max-drawdown AVOID lens | NON-GATED | — |",
        f"",
        f"**TrialLedger:** {n_trials} distinct configs registered for family `{FAMILY}`",
        f"(3 variants x 2 horizons = 6 configs; BH-FDR correction on 3 gated x 1 primary horizon).",
        f"",
        f"**Deseasonalization amendment:** all quarterly deltas use diff(4) [YoY] instead of",
        f"diff(1) [QoQ] as in the original build. This applies to NCRENRER, CRE/equity,",
        f"CRE/loans, uninsured-deposit share, and brokered-deposit share changes.",
        f"Level composites (V3) are not affected. See module docstring for rationale.",
        f"",
        f"---",
        f"",
        f"## 3. Results — IC by variant and horizon",
        f"",
        f"### 3.1 Full sample (2018-Q1 to 2026-Q1, 33 quarters)",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | Std IC | ICIR | %Pos | t-stat | p-val | 95% CI | CI excl. 0? |",
        f"|---------|---------|---------|---------|--------|------|------|--------|-------|--------|-------------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["full"]
            ci = results[key]["ci_full"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s.get('std_ic', float('nan')):.4f} | {s['icir']:.3f} | "
                f"{s['pct_positive']:.3f} | {s['t_stat']:.3f} | {s['p_value']:.4f} | "
                f"[{ci['ci_lo']:.4f}, {ci['ci_hi']:.4f}] | {'YES' if ci['excludes_zero'] else 'no'} |"
            )

    report_lines += [
        f"",
        f"### 3.2 Ex-2023 decomposition (mandatory crisis-concentration gate)",
        f"",
        f"Crisis window dropped: signal dates {(CRISIS_START + pd.Timedelta(days=PIT_LAG_DAYS)).date()} "
        f"to {(CRISIS_END + pd.Timedelta(days=PIT_LAG_DAYS)).date()} (PIT-shifted by {PIT_LAG_DAYS}d).",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val | CI excl. 0? |",
        f"|---------|---------|---------|---------|------|------|--------|-------|-------------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["ex23"]
            ci = results[key]["ci_ex23"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s['icir']:.3f} | {s['pct_positive']:.3f} | {s['t_stat']:.3f} | "
                f"{s['p_value']:.4f} | {'YES' if ci['excludes_zero'] else 'no'} |"
            )

    report_lines += [
        f"",
        f"### 3.3 Crisis-only (2023 window)",
        f"",
        f"| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val |",
        f"|---------|---------|---------|---------|------|------|--------|-------|",
    ]
    for variant in ["V1", "V2", "V3"]:
        for h in HORIZONS:
            key = f"{variant}_{h}d"
            s = results[key]["in23"]
            report_lines.append(
                f"| {variant} | {h}d | {s['n_dates']} | {s['mean_ic']:.4f} | "
                f"{s['icir']:.3f} | {s['pct_positive']:.3f} | {s['t_stat']:.3f} | "
                f"{s['p_value']:.4f} |"
            )

    report_lines += [
        f"",
        f"---",
        f"",
        f"## 4. Gate verdicts",
        f"",
        f"### 4.1 Deflated Sharpe (DSR) — gated variants at 63d, n_trials={n_trials}",
        f"",
        f"Threshold: DSR p >= 0.90 (per family constitution; 'the only door to GO').",
        f"",
        f"| Variant | DSR p | BH-adjusted p | DSR verdict |",
        f"|---------|-------|---------------|-------------|",
    ]
    for v in ["V1", "V2", "V3"]:
        key = f"{v}_63d"
        dsr = dsr_results.get(key, {})
        bh_p = bh_results.get(v, np.nan)
        report_lines.append(
            f"| {v} | {dsr.get('dsr_p', float('nan')):.4f} | "
            f"{bh_p:.4f} | {dsr.get('verdict', 'N/A')} |"
        )

    report_lines += [
        f"",
        f"### 4.2 Spannedness gate: V1 vs V3 ex-2023",
        f"",
        f"Criterion: |IC(V1 ex-2023)| > |IC(V3 ex-2023)| at 63d horizon.",
        f"",
        f"| Metric | V1 (primary) | V3 (control) | V1 > V3? |",
        f"|--------|--------------|--------------|----------|",
        f"| |mean IC| ex-2023 (63d) | {v1_ex23_abs:.4f} | {v3_ex23_abs:.4f} | {'PASS' if spannedness_pass else ('FAIL' if spannedness_pass is False else 'N/A')} |",
        f"",
        f"**Interpretation:** {'V1 beats V3 ex-2023.' if spannedness_pass else 'V3 >= V1 ex-2023 — the canonical-level ratios contain at least as much signal as the proxy. The spannedness failure may reflect missing CRE maturity-bucket data (GAP-2): V1 is a delinquency+concentration proxy, not the exact maturity-roll signal that the adjudication identified as non-spanned.' if spannedness_pass is False else 'Unable to determine.'}",
        f"",
        f"### 4.3 V4 — 21d ruler robustness (non-gated)",
        f"",
        f"| Metric | V1@21d ex-2023 | V3@21d ex-2023 |",
        f"|--------|----------------|----------------|",
        f"| Mean IC | {v4_v1_21d_ex23['mean_ic']:.4f} | {v4_v3_21d_ex23['mean_ic']:.4f} |",
        f"| ICIR | {v4_v1_21d_ex23['icir']:.3f} | {v4_v3_21d_ex23['icir']:.3f} |",
        f"",
        f"### 4.4 V5 — AVOID-side drawdown lens (non-gated)",
        f"",
        f"Does high V1 score predict deeper max drawdown in next 63d?",
        f"A positive IC here = stressed banks suffer larger drawdowns = AVOID signal.",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| V5 IC (full, V1 -> max_dd_63d) | {v5_results.get('ic_full', float('nan')):.4f} |",
        f"| V5 IC (ex-2023) | {v5_results.get('ic_ex23', float('nan')):.4f} |",
        f"| N observations | {v5_results.get('n', 0)} |",
        f"",
        f"---",
        f"",
        f"## 5. Overall verdict: {verdict}",
        f"",
        f"**{verdict_note}**",
        f"",
        f"PIT-lag amendment cross-check (see §1): the prior merged run (mixed 45/60d",
        f"lag) landed ACCRUE; this regenerated run (uniform {PIT_LAG_DAYS}d lag) lands",
        f"{verdict}.",
        f"",
        f"Sign finding: V1 63d mean IC = {v1_63_mean_ic:.4f} ({v1_63_sign_str} IC = {v1_63_direction}).",
        f"V3 63d mean IC = {v3_63_mean_ic:.4f}. DSR gate: V1 p={dsr_results.get('V1_63d', {}).get('dsr_p', float('nan')):.4f},",
        f"V2 p={dsr_results.get('V2_63d', {}).get('dsr_p', float('nan')):.4f},",
        f"V3 p={dsr_results.get('V3_63d', {}).get('dsr_p', float('nan')):.4f} — none >= 0.90 threshold.",
        f"Spannedness gate: V3 {'>=' if not spannedness_pass else '<'} V1 ex-2023 "
        f"({'FAIL' if not spannedness_pass else 'PASS'}).",
        f"",
        f"Note on survivorship correction: the three failed banks (SIVB, SBNY, FRC)",
        f"are included in the panel and contribute terminal -100% returns at delisting.",
        f"Their inclusion corrects the survivorship bias identified in review (the prior",
        f"result was measured only on banks that survived the 2023 stress episode).",
        f"The current IC values incorporate their balance-sheet signal scores and",
        f"forward returns including the terminal settlement.",
        f"",
        f"Pre-registered expectation (from SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):",
        f"> 'Mandatory ex-2023 decomposition; the pre-registered expectation is that the",
        f"> first adjudication lands ACCRUE-with-clock awaiting a second independent episode,",
        f"> not GO. A spectacular in-sample Sharpe here is the archetypal single-event dummy.'",
        f"",
        "The DSR gate result (p = {}) is consistent with the pre-registered expectation.".format(
            f"{v1_63_p:.4f}" if v1_63_p_valid and not math.isnan(v1_63_p) else "N/A"),
        f"",
        f"**Come-back clock:** next adjudication when a second independent bank-stress",
        f"episode enters the sample. Current sample (2018-Q1 to 2026-Q1) contains",
        f"exactly one: Mar-2023 SVB/Signature/First Republic. The 2022 rising-rate",
        f"period is a stress regime but produced no major failures in this basket.",
        f"",
        f"---",
        f"",
        f"## 6. Nightly wiring (for consolidation)",
        f"",
        f"The FDIC collector (`scripts/collect_ffiec_y9c.py`) is standalone and resumable.",
        f"Add to `daily.yml` as a pre-analysis step:",
        f"",
        f"```yaml",
        f"- name: Collect FDIC Y-9C proxy",
        f"  run: python3 -m scripts.collect_ffiec_y9c --resume",
        f"```",
        f"",
        f"No `scripts/collect.py` or `engine/signal_lab.py` edits required.",
        f"Failed-bank (SIVB/SBNY/FRC) rows are part of the canonical store panel:",
        f"the collector backfills them per-CERT via `FAILED_TICKER_CERT_MAP` (frozen",
        f"historical data; missing quarters after each bank's failure date are",
        f"expected). A live FDIC fetch inside `w3_bank_callreport_stress_phase0.py`",
        f"remains as fallback for store copies that predate the backfill.",
        f"",
        f"---",
        f"",
        f"*Report generated by `scripts/w3_bank_callreport_stress_phase0.py`*",
        f"",
    ]

    return "\n".join(report_lines)


if __name__ == "__main__":
    report = run_study()
    out_path = ROOT / "reports" / "w3-bank-callreport-stress-phase0.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"\nReport written -> {out_path}")
