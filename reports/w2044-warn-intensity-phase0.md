# W2-044 WARN Intensity — Phase-0

**Family:** `w2044_warn_intensity`
**Date:** 2026-07-06
**Status:** Wave-2 queue item A5
**Verdict:** DATA-BLOCKED — Step 2 PARKED

---

> **In plain English:** When a public company files a WARN Act notice
> (legally-required 60-day advance notice of mass layoffs or plant closures),
> does its stock underperform over the next 21 or 63 trading days?
> We also ask whether the *intensity* of recent WARN filings (trailing-90-day
> worker-count z-score) carries additional predictive power. The pre-registered
> prior is NEGATIVE returns — WARN notices signal deteriorating business
> fundamentals. This phase-0 cannot run: no consolidated, freely
> machine-accessible, multi-state WARN feed was found. The verdict is
> PARKED pending data access. The pre-registered design is preserved below
> so a future re-run is fully reproducible.

---

## 1. Pre-registered design

**Pre-registered direction:** NEGATIVE peer-adjusted abnormal returns.

**Honest prior (printed before results):** WARN filings are a lagging
indicator — the decision to lay off precedes the notice by months.
Markets may partly price in distress before the notice posts.
Prior probability of clearing all gates: MODERATE (academic literature
finds significant negative returns for mass-layoff announcements,
but effect sizes vary by aggregation level and look-ahead controls).

### Variants (trial grid — logged to ledger at generation, before computation)

| Variant | Signal | Horizon | Direction |
|---------|--------|---------|-----------|
| notice_event_21d | warn_notice_event | 21d | negative |
| notice_event_63d | warn_notice_event | 63d | negative |
| intensity_z_21d | warn_intensity_z_90d | 21d | negative |
| intensity_z_63d | warn_intensity_z_90d | 63d | negative |

### Gates (all must pass for Phase-1 candidacy)

- **G1:** Pre-registered direction NEGATIVE in all 4 cells (printed prior).
- **G2:** |t_HAC| >= 2.0 (date-clustered Newey-West; one obs per event-date per ticker).
- **G3:** BH FDR q <= 0.1 across all 4 cells.
- **G4:** Split-half same-sign: first half vs second half of study window.
- **G5:** Not-driven-by-one-sector: result survives excluding the single
  sector with the most events (robustness vs sector concentration).

### PIT assumptions

- **Availability fence:** state posting date if present in feed; else notice date
  + 7 calendar days. This is conservative — some states post
  within 24h; others take several days to update their online registry.
- **Intensity z:** trailing-90-day worker-count sum, z-scored
  vs own expanding history (min 90 days of history required before scoring).
  Uses ONLY data available on or before avail_date (PIT causal).
- **Beta:** trailing 252 trading days OLS vs SPY + sector ETF (min 120 days).
- **Peer adjustment:** abnormal return = stock return minus (beta_SPY * SPY_return
  + beta_sector * sector_ETF_return).
- **Study window:** 2021-07-06 to 2026-07-02
  (constrained by massive_stock_day store start date).

## 2. Step-1 — Consolidated WARN feed assessment

The adjudication requires a consolidated WARN source (50-state scrape
explicitly rejected). Adequacy criteria:
- Covers all major US states (at minimum CA, TX, NY, FL, IL, PA, OH)
- Machine-accessible without scraping each state agency individually
- Data lag <= 2 months from notice date to availability
- Fields: company name, state, workers affected, notice date, effective date
- Free or within existing infrastructure cost

### Sources assessed

| Source | States | Free machine path? | Lag | Verdict |
|--------|--------|-------------------|-----|---------|
| layoffdata.com | 49 | No | monthly updates | BLOCKED |
| WARN Firehose (warnfirehose.com) | 50 | No | ~24h (scraped daily at 05:00 UTC) | BLOCKED — subscription required for historical bulk access |
| OpenICPSR Cleveland Fed project 155161 V9 | 50 | No | updated bimonthly by researchers | BLOCKED — requires institutional affiliation |
| Dewey Data (deweydata.io/data-partners/warn-database) | 50 | No | bimonthly per layoffdata.com | BLOCKED — paywalled academic channel |
| biglocalnews/warn-scraper (GitHub) | ~40+ (varies by scraper support) | Yes | depends on manual scrape run; per-state lag varies | REJECTED BY DESIGN — adjudication bars scraper approach |
| Kadoa layoffs-tracker (github.com/kadoa-org/layoffs-tracker) | 45 | No | unknown | BLOCKED — no free machine path; also missing 5 states |
| data.gov WARN dataset | 1 | Yes | unknown | INADEQUATE — single city, not national |

### Assessment detail

**layoffdata.com**
- Description: Cleveland Fed-associated consolidated WARN database
- States: 49
- Fields: company, state, workers, notice_date, effective_date
- Lag: monthly updates
- Blocked reason: HTTP 403 Forbidden — subscription required; no free bulk download
- Verdict: **BLOCKED**

**WARN Firehose (warnfirehose.com)**
- Description: Commercial consolidated WARN feed, REST API
- States: 50
- Fields: company, city, county, state, workers, layoff_type, notice_date, effective_date, NAICS
- Lag: ~24h (scraped daily at 05:00 UTC)
- Blocked reason: Free tier = 25 API calls/day, 60-day window only (insufficient); paid from $49/mo
- Verdict: **BLOCKED — subscription required for historical bulk access**

**OpenICPSR Cleveland Fed project 155161 V9**
- Description: Academic research dataset, Krolikowski et al. (2022), all states, 1988+
- States: 50
- Fields: state, month, workers_affected (aggregated); ticker-level map not included
- Lag: updated bimonthly by researchers
- Blocked reason: HTTP 403 — institutional login required (OpenICPSR academic repository)
- Verdict: **BLOCKED — requires institutional affiliation**

**Dewey Data (deweydata.io/data-partners/warn-database)**
- Description: Premium academic data portal reselling layoffdata.com data
- States: 50
- Fields: company, state, workers, notice_date, effective_date
- Lag: bimonthly per layoffdata.com
- Blocked reason: Institutional access required; not freely downloadable
- Verdict: **BLOCKED — paywalled academic channel**

**biglocalnews/warn-scraper (GitHub)**
- Description: Open-source CLI that scrapes each state workforce agency website
- States: ~40+ (varies by scraper support)
- Fields: varies by state (non-standardized)
- Lag: depends on manual scrape run; per-state lag varies
- Blocked reason: IS a 50-state scraper — explicitly rejected by adjudication as permanent maintenance burden
- Verdict: **REJECTED BY DESIGN — adjudication bars scraper approach**

**Kadoa layoffs-tracker (github.com/kadoa-org/layoffs-tracker)**
- Description: Open dataset from 45 state labor departments (~42K notices)
- States: 45
- Fields: company, state, date (partial)
- Lag: unknown
- Blocked reason: 'Need full historical dataset? Get in touch' — no free bulk download
- Verdict: **BLOCKED — no free machine path; also missing 5 states**

**data.gov WARN dataset**
- Description: City of Austin TX WARN notices only
- States: 1
- Fields: partial
- Lag: unknown
- Blocked reason: Single city (Austin TX) only — grossly inadequate coverage
- Verdict: **INADEQUATE — single city, not national**

## 3. Coverage adequacy verdict — DATA-BLOCKED

No candidate meets all four adequacy criteria simultaneously:

1. WARN Firehose meets coverage (50 states, daily lag, correct fields,
   REST API in JSON/CSV/Parquet) but is paywalled — no historical bulk
   access without a paid subscription ($49/mo Starter+ minimum).

2. layoffdata.com meets coverage (49 states, correct fields, academic
   research channel via Dewey Data) but returns HTTP 403 to unauthenticated
   requests — subscription required.

3. Cleveland Fed OpenICPSR dataset (Krolikowski et al. 2022, project 155161)
   is the gold-standard academic source (50 states, 1988+, peer-reviewed)
   but requires institutional affiliation login — HTTP 403.

4. biglocalnews/warn-scraper is the closest to a free, comprehensive source
   but IS a state-by-state scraper — exactly the pattern the adjudication
   rejects as a permanent maintenance burden.

**Step 2 (event study) not executed. Verdict: PARK.**

## 4. Unlock path

Any ONE of the following would unblock this lane:

**Option A (lowest friction):** Subscribe to WARN Firehose Starter+ tier
($49/mo as of 2026-07). Their REST API returns JSON/CSV/Parquet with all
required fields (company, state, workers, notice_date, effective_date, NAICS)
for all 50 states from 1988, updated daily with ~24h lag. A one-time bulk
historical pull covers the study window; thereafter monthly refresh suffices.
Contact: warnfirehose.com

**Option B:** Request institutional access to OpenICPSR project 155161 V9
(Cleveland Fed / Krolikowski et al.). This is a peer-reviewed, citation-traceable
source updated bimonthly. Fields are state-month aggregates — ticker mapping
would require a separate employer->ticker crosswalk. Academic channel via
Dewey Data (deweydata.io) if institutional login is not available.

**Option C:** Wait for a DOL or BLS consolidated WARN API (none exists as of
2026-07; DOL's own site only indexes compliance information, not the data).

## 5. Employer-ticker map design (pre-registered for when unblocked)

When a consolidated feed becomes available, the employer->ticker map
should be constructed as follows:

- **Scope:** Top ~300 public company employers by WARN notice frequency
  over 2010-2025. Focus on S&P 500 / S&P 1500 members.
- **Matching:** Fuzzy company-name match against compustat/SEC EDGAR
  company name universe; verified manually for top-50 by volume.
- **Validity windows:** Ticker valid_from / valid_to to handle M&A,
  delistings, spinoffs (same pattern as w2096_nhtsa_make_map.csv).
- **Subsidiaries:** Map subsidiary employer names to parent ticker
  (e.g., 'Amazon.com Services LLC' -> AMZN) with a confidence flag.
- **Exclusions:** Government entities, non-profits, private companies
  (not publicly traded — excluded from return study).
- **Coverage estimate:** ~15-25% of WARN notices by count are mappable
  to public-company tickers (most WARN filers are private employers).

## 6. Nightly wiring (for consolidation, once unblocked)

- **Collector:** `scripts/collect_warn.py` (to build) writes to
  `data/warn/notices.parquet` (real dir, not symlink; not committed to git).
- **Schedule:** Nightly at 22:00 ET (after state agency posting windows).
- **Ticker map:** `scripts/w2044_warn_ticker_map.csv` (to build) with
  columns: employer_name_pattern, ticker, valid_from, valid_to, confidence.
- **Phase-1 (if gates pass):** `engine/warn_intensity.py`
  (signal builder, no board wiring until Phase-1 gate confirmation).
- **Does NOT edit:** `scripts/collect.py`, `engine/signal_lab.py`, templates.

---

*Harness script: `scripts/w2044_warn_intensity_phase0.py`*
*Trial grid logged to `engine/trial_ledger.py` family `w2044_warn_intensity` (pre-results)*
*Study window: 2021-07-06 to 2026-07-02*
