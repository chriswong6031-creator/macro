"""W2-044 WARN Intensity Phase-0 — employer WARN notice intensity as a forward-return signal.

Authorized as wave-2 queue item A5. HARD DATA CONDITION: the adjudication authorizes
this ONLY via a CONSOLIDATED WARN source (50-state scrape explicitly rejected as permanent
maintenance burden). This script implements Step 1 (source feasibility) and, if adequate,
Step 2 (event study).

HYPOTHESIS (pre-registered, direction NEGATIVE)
- Family: w2044_warn_intensity
- Signal 1 (notice event): a public-company employer issues a WARN notice (availability =
  state posting date if present, else notice date + 7 calendar days). Prediction: negative
  peer-adjusted AR over 21d and 63d forward.
- Signal 2 (trailing-90d intensity z): employer's trailing-90d WARN worker-count z-score
  vs own history (PIT expanding window). Prediction: higher z -> more negative AR, 21d + 63d.
- 4 cells: {notice_event, intensity_z} x {21d, 63d}.

PIT FENCE
- State posting date if present in feed, else notice date + 7 calendar days (conservative).
- Intensity z: trailing-90d uses only data available on or before avail_date (PIT expanding).
- Beta and sector-ETF adjustment: trailing 252 trading days, PIT.

GATES (all must pass; pre-registered before computation)
- G1: Direction NEGATIVE in all 4 cells (pre-registered prior).
- G2: |t_HAC| >= 2.0 (date-clustered, one obs per event-date per ticker).
- G3: BH FDR q <= 0.10 across all 4 cells.
- G4: Split-half same-sign: first vs second half of study window.
- G5: Not-driven-by-one-sector: result holds excluding the dominant sector.

DATA CONDITION OUTCOME (Step 1, run before Step 2)
  STATUS: DATA-BLOCKED

  Consolidated WARN feed candidates assessed:
  | Source | States | Machine-accessible free? | Lag | Verdict |
  |---|---|---|---|---|
  | layoffdata.com (Cleveland Fed-associated) | 49 | No (403, subscription req'd) | monthly | BLOCKED |
  | WARN Firehose (warnfirehose.com) | 50 | No (API $49/mo; free=60d only) | ~24h | BLOCKED |
  | OpenICPSR Cleveland Fed (project 155161) | 50 | No (institutional login, 403) | bimonthly | BLOCKED |
  | Dewey Data (academic research portal) | 50 | No (institutional access) | bimonthly | BLOCKED |
  | biglocalnews/warn-scraper | ~40+ | IS a 50-state scraper (rejected) | varies | REJECTED BY DESIGN |
  | Kadoa layoffs-tracker (GitHub) | 45 | No ("get in touch" for full data) | varies | BLOCKED |
  | data.gov WARN dataset | 1 (Austin TX) | Yes but single-city only | varies | INADEQUATE |

  None of the candidates meets the adjudication requirement: consolidated (not a 50-state
  scrape), freely machine-accessible, covering major states, with <= 2 month lag.

  VERDICT: PARK. Step 2 (event study) not executed. Report filed per lane instructions.

UNLOCK PATH
  The following would unblock this lane:
  1. A paid subscription to WARN Firehose ($49/mo) or layoffdata.com providing API/bulk CSV.
  2. Institutional access to the Cleveland Fed OpenICPSR project 155161 (V9+).
  3. The BLS or DOL publishing a consolidated machine-readable WARN feed (none exists as of 2026-07).
  Option 1 is the lowest-friction path. Contact: warnfirehose.com Starter+ tier.

NIGHTLY WIRING (for consolidation, once unblocked)
  - Collector: scripts/collect_warn.py (to build) -> data/warn/ (real dir, not symlink)
  - Schedule: nightly after close, after state agency posting windows (~daily lag)
  - Depends on: price store (data/massive_stock_day/), sector ETF map
  - No engine/board wiring until Phase-1 gate pass.

Run:
    python -m scripts.w2044_warn_intensity_phase0

Writes:
    reports/w2044-warn-intensity-phase0.md
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402

# ---------------------------------------------------------------------------
# CONSTANTS (pre-registered; frozen before any computation)
# ---------------------------------------------------------------------------
FAMILY = "w2044_warn_intensity"
REPORT_PATH = ROOT / "reports" / "w2044-warn-intensity-phase0.md"

# Study window (price store constraint: massive_stock_day starts 2021-07-06)
PRICE_START = date(2021, 7, 6)
PRICE_END = date(2026, 7, 2)

# PIT fence
WARN_PIT_FENCE_DAYS = 7      # notice date + 7 calendar days if posting date absent

# Forward return windows (trading days)
FWD_21 = 21
FWD_63 = 63

# Intensity z look-back (calendar days), trailing PIT
INTENSITY_WINDOW_DAYS = 90

# Beta and sector adjustment
BETA_WIN = 252

# Gates (pre-registered direction = NEGATIVE)
GATE_DIRECTION = "negative"
GATE_ABS_T = 2.0
GATE_BH_Q = 0.10

# Trial grid (4 cells; pre-registered, logged BEFORE computation)
TRIAL_GRID = [
    {
        "variant": "notice_event_21d",
        "signal": "warn_notice_event",
        "fwd_days": 21,
        "direction": GATE_DIRECTION,
        "note": "binary event: employer files WARN notice; avail = posting date or notice+7d",
    },
    {
        "variant": "notice_event_63d",
        "signal": "warn_notice_event",
        "fwd_days": 63,
        "direction": GATE_DIRECTION,
        "note": "same event, 63d forward window",
    },
    {
        "variant": "intensity_z_21d",
        "signal": "warn_intensity_z_90d",
        "fwd_days": 21,
        "direction": GATE_DIRECTION,
        "note": "trailing-90d worker-count z vs own expanding history; avail = posting date or notice+7d",
    },
    {
        "variant": "intensity_z_63d",
        "signal": "warn_intensity_z_90d",
        "fwd_days": 63,
        "direction": GATE_DIRECTION,
        "note": "same intensity z signal, 63d forward window",
    },
]

# Data source candidates assessed in Step 1
DATA_SOURCE_ASSESSMENT = [
    {
        "source": "layoffdata.com",
        "description": "Cleveland Fed-associated consolidated WARN database",
        "states": 49,
        "years": "1998-present (varies by state)",
        "fields": "company, state, workers, notice_date, effective_date",
        "lag": "monthly updates",
        "machine_accessible_free": False,
        "reason_blocked": "HTTP 403 Forbidden — subscription required; no free bulk download",
        "verdict": "BLOCKED",
    },
    {
        "source": "WARN Firehose (warnfirehose.com)",
        "description": "Commercial consolidated WARN feed, REST API",
        "states": 50,
        "years": "1988-present",
        "fields": "company, city, county, state, workers, layoff_type, notice_date, effective_date, NAICS",
        "lag": "~24h (scraped daily at 05:00 UTC)",
        "machine_accessible_free": False,
        "reason_blocked": "Free tier = 25 API calls/day, 60-day window only (insufficient); paid from $49/mo",
        "verdict": "BLOCKED — subscription required for historical bulk access",
    },
    {
        "source": "OpenICPSR Cleveland Fed project 155161 V9",
        "description": "Academic research dataset, Krolikowski et al. (2022), all states, 1988+",
        "states": 50,
        "years": "1988-present",
        "fields": "state, month, workers_affected (aggregated); ticker-level map not included",
        "lag": "updated bimonthly by researchers",
        "machine_accessible_free": False,
        "reason_blocked": "HTTP 403 — institutional login required (OpenICPSR academic repository)",
        "verdict": "BLOCKED — requires institutional affiliation",
    },
    {
        "source": "Dewey Data (deweydata.io/data-partners/warn-database)",
        "description": "Premium academic data portal reselling layoffdata.com data",
        "states": 50,
        "years": "1988-present",
        "fields": "company, state, workers, notice_date, effective_date",
        "lag": "bimonthly per layoffdata.com",
        "machine_accessible_free": False,
        "reason_blocked": "Institutional access required; not freely downloadable",
        "verdict": "BLOCKED — paywalled academic channel",
    },
    {
        "source": "biglocalnews/warn-scraper (GitHub)",
        "description": "Open-source CLI that scrapes each state workforce agency website",
        "states": "~40+ (varies by scraper support)",
        "years": "varies by state",
        "fields": "varies by state (non-standardized)",
        "lag": "depends on manual scrape run; per-state lag varies",
        "machine_accessible_free": True,
        "reason_blocked": "IS a 50-state scraper — explicitly rejected by adjudication as permanent maintenance burden",
        "verdict": "REJECTED BY DESIGN — adjudication bars scraper approach",
    },
    {
        "source": "Kadoa layoffs-tracker (github.com/kadoa-org/layoffs-tracker)",
        "description": "Open dataset from 45 state labor departments (~42K notices)",
        "states": 45,
        "years": "varies",
        "fields": "company, state, date (partial)",
        "lag": "unknown",
        "machine_accessible_free": False,
        "reason_blocked": "'Need full historical dataset? Get in touch' — no free bulk download",
        "verdict": "BLOCKED — no free machine path; also missing 5 states",
        "missing_states_concern": True,
    },
    {
        "source": "data.gov WARN dataset",
        "description": "City of Austin TX WARN notices only",
        "states": 1,
        "years": "limited",
        "fields": "partial",
        "lag": "unknown",
        "machine_accessible_free": True,
        "reason_blocked": "Single city (Austin TX) only — grossly inadequate coverage",
        "verdict": "INADEQUATE — single city, not national",
    },
]


def _write_report(status: str = "DATA-BLOCKED") -> None:
    """Write the phase-0 report."""
    lines = []

    lines.append("# W2-044 WARN Intensity — Phase-0")
    lines.append("")
    lines.append(f"**Family:** `{FAMILY}`")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("**Status:** Wave-2 queue item A5")
    lines.append(f"**Verdict:** {status}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Plain English box
    lines.append("> **In plain English:** When a public company files a WARN Act notice")
    lines.append("> (legally-required 60-day advance notice of mass layoffs or plant closures),")
    lines.append("> does its stock underperform over the next 21 or 63 trading days?")
    lines.append("> We also ask whether the *intensity* of recent WARN filings (trailing-90-day")
    lines.append("> worker-count z-score) carries additional predictive power. The pre-registered")
    lines.append("> prior is NEGATIVE returns — WARN notices signal deteriorating business")
    lines.append("> fundamentals. This phase-0 cannot run: no consolidated, freely")
    lines.append("> machine-accessible, multi-state WARN feed was found. The verdict is")
    lines.append("> PARKED pending data access. The pre-registered design is preserved below")
    lines.append("> so a future re-run is fully reproducible.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Section 1: Pre-registered design
    lines.append("## 1. Pre-registered design")
    lines.append("")
    lines.append("**Pre-registered direction:** NEGATIVE peer-adjusted abnormal returns.")
    lines.append("")
    lines.append("**Honest prior (printed before results):** WARN filings are a lagging")
    lines.append("indicator — the decision to lay off precedes the notice by months.")
    lines.append("Markets may partly price in distress before the notice posts.")
    lines.append("Prior probability of clearing all gates: MODERATE (academic literature")
    lines.append("finds significant negative returns for mass-layoff announcements,")
    lines.append("but effect sizes vary by aggregation level and look-ahead controls).")
    lines.append("")
    lines.append("### Variants (trial grid — logged to ledger at generation, before computation)")
    lines.append("")
    lines.append("| Variant | Signal | Horizon | Direction |")
    lines.append("|---------|--------|---------|-----------|")
    for t in TRIAL_GRID:
        lines.append(
            f"| {t['variant']} | {t['signal']} | {t['fwd_days']}d | {t['direction']} |"
        )
    lines.append("")
    lines.append("### Gates (all must pass for Phase-1 candidacy)")
    lines.append("")
    lines.append("- **G1:** Pre-registered direction NEGATIVE in all 4 cells (printed prior).")
    lines.append(f"- **G2:** |t_HAC| >= {GATE_ABS_T} (date-clustered Newey-West; one obs per event-date per ticker).")
    lines.append(f"- **G3:** BH FDR q <= {GATE_BH_Q} across all 4 cells.")
    lines.append("- **G4:** Split-half same-sign: first half vs second half of study window.")
    lines.append("- **G5:** Not-driven-by-one-sector: result survives excluding the single")
    lines.append("  sector with the most events (robustness vs sector concentration).")
    lines.append("")
    lines.append("### PIT assumptions")
    lines.append("")
    lines.append(f"- **Availability fence:** state posting date if present in feed; else notice date")
    lines.append(f"  + {WARN_PIT_FENCE_DAYS} calendar days. This is conservative — some states post")
    lines.append("  within 24h; others take several days to update their online registry.")
    lines.append(f"- **Intensity z:** trailing-{INTENSITY_WINDOW_DAYS}-day worker-count sum, z-scored")
    lines.append("  vs own expanding history (min 90 days of history required before scoring).")
    lines.append(f"  Uses ONLY data available on or before avail_date (PIT causal).")
    lines.append("- **Beta:** trailing 252 trading days OLS vs SPY + sector ETF (min 120 days).")
    lines.append("- **Peer adjustment:** abnormal return = stock return minus (beta_SPY * SPY_return")
    lines.append("  + beta_sector * sector_ETF_return).")
    lines.append(f"- **Study window:** {PRICE_START.isoformat()} to {PRICE_END.isoformat()}")
    lines.append("  (constrained by massive_stock_day store start date).")
    lines.append("")

    # Section 2: Step-1 Data source assessment
    lines.append("## 2. Step-1 — Consolidated WARN feed assessment")
    lines.append("")
    lines.append("The adjudication requires a consolidated WARN source (50-state scrape")
    lines.append("explicitly rejected). Adequacy criteria:")
    lines.append("- Covers all major US states (at minimum CA, TX, NY, FL, IL, PA, OH)")
    lines.append("- Machine-accessible without scraping each state agency individually")
    lines.append("- Data lag <= 2 months from notice date to availability")
    lines.append("- Fields: company name, state, workers affected, notice date, effective date")
    lines.append("- Free or within existing infrastructure cost")
    lines.append("")
    lines.append("### Sources assessed")
    lines.append("")
    lines.append("| Source | States | Free machine path? | Lag | Verdict |")
    lines.append("|--------|--------|-------------------|-----|---------|")
    for src in DATA_SOURCE_ASSESSMENT:
        states = src["states"]
        free = "Yes" if src["machine_accessible_free"] else "No"
        lag = src["lag"]
        verdict = src["verdict"]
        lines.append(f"| {src['source']} | {states} | {free} | {lag} | {verdict} |")
    lines.append("")
    lines.append("### Assessment detail")
    lines.append("")
    for src in DATA_SOURCE_ASSESSMENT:
        lines.append(f"**{src['source']}**")
        lines.append(f"- Description: {src['description']}")
        lines.append(f"- States: {src['states']}")
        lines.append(f"- Fields: {src['fields']}")
        lines.append(f"- Lag: {src['lag']}")
        lines.append(f"- Blocked reason: {src['reason_blocked']}")
        lines.append(f"- Verdict: **{src['verdict']}**")
        lines.append("")

    # Section 3: Coverage adequacy verdict
    lines.append("## 3. Coverage adequacy verdict — DATA-BLOCKED")
    lines.append("")
    lines.append("No candidate meets all four adequacy criteria simultaneously:")
    lines.append("")
    lines.append("1. WARN Firehose meets coverage (50 states, daily lag, correct fields,")
    lines.append("   REST API in JSON/CSV/Parquet) but is paywalled — no historical bulk")
    lines.append("   access without a paid subscription ($49/mo Starter+ minimum).")
    lines.append("")
    lines.append("2. layoffdata.com meets coverage (49 states, correct fields, academic")
    lines.append("   research channel via Dewey Data) but returns HTTP 403 to unauthenticated")
    lines.append("   requests — subscription required.")
    lines.append("")
    lines.append("3. Cleveland Fed OpenICPSR dataset (Krolikowski et al. 2022, project 155161)")
    lines.append("   is the gold-standard academic source (50 states, 1988+, peer-reviewed)")
    lines.append("   but requires institutional affiliation login — HTTP 403.")
    lines.append("")
    lines.append("4. biglocalnews/warn-scraper is the closest to a free, comprehensive source")
    lines.append("   but IS a state-by-state scraper — exactly the pattern the adjudication")
    lines.append("   rejects as a permanent maintenance burden.")
    lines.append("")
    lines.append("**Step 2 (event study) not executed. Verdict: PARK.**")
    lines.append("")

    # Section 4: Unlock path
    lines.append("## 4. Unlock path")
    lines.append("")
    lines.append("Any ONE of the following would unblock this lane:")
    lines.append("")
    lines.append("**Option A (lowest friction):** Subscribe to WARN Firehose Starter+ tier")
    lines.append("($49/mo as of 2026-07). Their REST API returns JSON/CSV/Parquet with all")
    lines.append("required fields (company, state, workers, notice_date, effective_date, NAICS)")
    lines.append("for all 50 states from 1988, updated daily with ~24h lag. A one-time bulk")
    lines.append("historical pull covers the study window; thereafter monthly refresh suffices.")
    lines.append("Contact: warnfirehose.com")
    lines.append("")
    lines.append("**Option B:** Request institutional access to OpenICPSR project 155161 V9")
    lines.append("(Cleveland Fed / Krolikowski et al.). This is a peer-reviewed, citation-traceable")
    lines.append("source updated bimonthly. Fields are state-month aggregates — ticker mapping")
    lines.append("would require a separate employer->ticker crosswalk. Academic channel via")
    lines.append("Dewey Data (deweydata.io) if institutional login is not available.")
    lines.append("")
    lines.append("**Option C:** Wait for a DOL or BLS consolidated WARN API (none exists as of")
    lines.append("2026-07; DOL's own site only indexes compliance information, not the data).")
    lines.append("")

    # Section 5: Employer-ticker map design (for when unblocked)
    lines.append("## 5. Employer-ticker map design (pre-registered for when unblocked)")
    lines.append("")
    lines.append("When a consolidated feed becomes available, the employer->ticker map")
    lines.append("should be constructed as follows:")
    lines.append("")
    lines.append("- **Scope:** Top ~300 public company employers by WARN notice frequency")
    lines.append("  over 2010-2025. Focus on S&P 500 / S&P 1500 members.")
    lines.append("- **Matching:** Fuzzy company-name match against compustat/SEC EDGAR")
    lines.append("  company name universe; verified manually for top-50 by volume.")
    lines.append("- **Validity windows:** Ticker valid_from / valid_to to handle M&A,")
    lines.append("  delistings, spinoffs (same pattern as w2096_nhtsa_make_map.csv).")
    lines.append("- **Subsidiaries:** Map subsidiary employer names to parent ticker")
    lines.append("  (e.g., 'Amazon.com Services LLC' -> AMZN) with a confidence flag.")
    lines.append("- **Exclusions:** Government entities, non-profits, private companies")
    lines.append("  (not publicly traded — excluded from return study).")
    lines.append("- **Coverage estimate:** ~15-25% of WARN notices by count are mappable")
    lines.append("  to public-company tickers (most WARN filers are private employers).")
    lines.append("")

    # Section 6: Nightly wiring
    lines.append("## 6. Nightly wiring (for consolidation, once unblocked)")
    lines.append("")
    lines.append("- **Collector:** `scripts/collect_warn.py` (to build) writes to")
    lines.append("  `data/warn/notices.parquet` (real dir, not symlink; not committed to git).")
    lines.append("- **Schedule:** Nightly at 22:00 ET (after state agency posting windows).")
    lines.append("- **Ticker map:** `scripts/w2044_warn_ticker_map.csv` (to build) with")
    lines.append("  columns: employer_name_pattern, ticker, valid_from, valid_to, confidence.")
    lines.append("- **Phase-1 (if gates pass):** `engine/warn_intensity.py`")
    lines.append("  (signal builder, no board wiring until Phase-1 gate confirmation).")
    lines.append("- **Does NOT edit:** `scripts/collect.py`, `engine/signal_lab.py`, templates.")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Harness script: `scripts/w2044_warn_intensity_phase0.py`*")
    lines.append(f"*Trial grid logged to `engine/trial_ledger.py` family `{FAMILY}` (pre-results)*")
    lines.append(f"*Study window: {PRICE_START.isoformat()} to {PRICE_END.isoformat()}*")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {REPORT_PATH}")


def main() -> None:
    print("=" * 70)
    print("W2-044 WARN Intensity Phase-0")
    print("=" * 70)
    print()

    # Step 0: Log trial grid BEFORE computation (house rule)
    print("[0] Logging trial grid to ledger (pre-results, before any computation)...")
    led = TrialLedger(family=FAMILY)
    n_new = led.log_grid(
        TRIAL_GRID,
        family=FAMILY,
        info_cutoff=str(PRICE_END),
        note="pre-registered W2-044 phase-0 grid; 4 cells logged before data-blocked check",
    )
    print(f"  Logged {n_new} new / {len(TRIAL_GRID)} total configs to family '{FAMILY}'")
    print()

    # Step 1: Data source assessment
    print("[1] Step-1: Consolidated WARN feed assessment...")
    print()
    print("  Assessing sources against adequacy criteria:")
    print("    - All major US states (min: CA, TX, NY, FL, IL, PA, OH)")
    print("    - Machine-accessible without per-state scraping")
    print("    - Lag <= 2 months")
    print("    - Fields: company, state, workers, notice_date, effective_date")
    print("    - Free or within existing infra cost")
    print()

    blocked_count = 0
    adequate_count = 0
    for src in DATA_SOURCE_ASSESSMENT:
        v = src["verdict"]
        free = src["machine_accessible_free"]
        states = src["states"]
        print(f"  [{v[:7]:7s}] {src['source']}")
        print(f"            States={states}, Free={free}, Lag={src['lag']}")
        print(f"            {src['reason_blocked']}")
        print()
        if "BLOCKED" in v or "REJECTED" in v or "INADEQUATE" in v:
            blocked_count += 1
        else:
            adequate_count += 1

    print(f"  Result: {blocked_count} blocked/rejected/inadequate, {adequate_count} adequate")
    print()

    if adequate_count == 0:
        print("[!] DATA-BLOCKED: No adequate consolidated WARN feed found.")
        print("    Step 2 (event study) SKIPPED per lane instructions.")
        print("    Verdict: PARK — report filed, PR still created.")
        print()
        _write_report(status="DATA-BLOCKED — Step 2 PARKED")
    else:
        print("[!] Adequate source found — Step 2 would proceed.")
        print("    (This branch is not expected in current environment.)")
        _write_report(status="DATA-BLOCKED — unexpected adequate source detected, review manually")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
