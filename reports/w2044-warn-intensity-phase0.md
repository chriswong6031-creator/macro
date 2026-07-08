# W2-044 WARN Intensity — Phase-0

**Family:** `w2044_warn_intensity`
**Date:** 2026-07-08
**Status:** Wave-2 queue item A5 — LANE W MANDATE
**Verdict:** NULL — direction gate failed

---

> **In plain English:** When a public company files a WARN Act notice
> (legally-required 60-day advance notice of mass layoffs or plant closures),
> does its stock underperform over the next 21 or 63 trading days?
> We also ask whether the *intensity* of recent WARN filings (trailing-90-day
> worker-count z-score) carries additional predictive power. The pre-registered
> prior is NEGATIVE returns — WARN notices signal deteriorating business
> fundamentals.

---

## 1. Acquisition ladder (Lane W mandate)

Operator mandate (2026-07-08): biglocalnews/warn-scraper is explicitly approved.
Previous DATA-BLOCKED verdict on scraper path is superseded.

**Rung 1 [OK]: biglocalnews/warn-scraper v1.2.143 (pip install warn-scraper)**
  Top-15 states covered: CA(18842), IL(4866), NJ(2352), WA(1481), IN(1218), TN(1055); NC/MN unsupported by scraper; TX/PA/GA blocked by CloudFlare/WAF from Mac IP; OH/FL/MI/CO/ID/KY/LA/VA scraper bugs (state sites changed structure); NE/NM DNS resolution failures.

**Rung 2 [ATTEMPTED]: BLN published data artifacts (GCS bucket bln-data-public/warn-layoffs/)**
  GCS bucket requires Google auth; state-level files (tx.csv, pa.csv) returned HTTP 404. MI archive (mi-before-20251125.zip) returned 200 but body is Google login page.

**Rung 3 [ATTEMPTED]: Direct grey scraping for blocked states (TX, PA, MN, NC)**
  TX (twc.texas.gov): HTTP 202 CloudFlare challenge loop — no data obtained. PA (pa.gov): HTTP 403 IP block — no data obtained. MN (mn.gov/deed): hCaptcha CloudFlare challenge — no data obtained. NC (des.nc.gov): HTTP 404 + challenge — no data obtained.

## 2. Panel coverage (honest per-state summary)

| State | Rows | Status |
|-------|------|--------|
| AK | 66 | OK |
| AL | 1,065 | OK |
| AZ | 755 | OK |
| CA | 18,842 | OK |
| CT | 28 | OK |
| DC | 140 | OK |
| DE | 107 | OK |
| HI | 451 | OK |
| IA | 411 | OK |
| IL | 4,866 | OK |
| IN | 1,218 | OK |
| KS | 794 | OK |
| MD | 1,397 | OK |
| ME | 92 | OK |
| MT | 44 | OK |
| NJ | 2,351 | OK |
| NY | 160 | OK |
| OK | 217 | OK |
| OR | 1,352 | OK |
| RI | 124 | OK |
| SC | 598 | OK |
| SD | 79 | OK |
| TN | 1,055 | OK |
| UT | 279 | OK |
| VT | 100 | OK |
| WA | 1,481 | OK |
| WI | 624 | OK |
| FL | 0 | MISSING: Scraper bug (div not found) |
| GA | 0 | MISSING: TCP timeout to tcsg.edu |
| MI | 0 | MISSING: Scraper bug (KeyError: Site address) |
| MN | 0 | MISSING: Not in scraper + hCaptcha |
| NC | 0 | MISSING: Not in scraper + CloudFlare |
| OH | 0 | MISSING: Scraper bug (JSON div not found) |
| PA | 0 | MISSING: IP block (HTTP 403) |
| TX | 0 | MISSING: CloudFlare block (HTTP 202) |

**Total rows acquired: 38,696**
**States in panel: 27**
**Missing top-15 states: FL, GA, MI, MN, NC, OH, PA, TX**

**Coverage caveat:** TX, PA, FL, MI, OH, GA, NC, MN are missing. These 8 states
collectively represent ~45-55% of national WARN volume by count (CA/IL/NJ/WA/IN
provide the bulk of our sample). Results are NOT nationally representative.
Gate interpretations are panel-conditional (not a national estimate).

## 3. Pre-registered design (frozen before results)

**Pre-registered direction:** NEGATIVE peer-adjusted abnormal returns.

**Honest prior:** WARN filings are a lagging indicator — the decision to lay off
precedes the notice by months. Markets may partly price in distress before the
notice posts. Prior probability of clearing all gates: MODERATE (academic
literature finds significant negative returns for mass-layoff announcements,
but effect sizes vary by aggregation level and look-ahead controls).

### Trial grid

| Variant | Signal | Horizon | Direction |
|---------|--------|---------|-----------|
| notice_event_21d | warn_notice_event | 21d | negative |
| notice_event_63d | warn_notice_event | 63d | negative |
| intensity_z_21d | warn_intensity_z_90d | 21d | negative |
| intensity_z_63d | warn_intensity_z_90d | 63d | negative |

### Gates

- **G1:** Pre-registered direction NEGATIVE in all 4 cells.
- **G2:** |t_HAC| >= 2.0 (date-clustered).
- **G3:** BH FDR q <= 0.1 across all 4 cells.
- **G4:** Split-half same-sign: first vs second half of study window.
- **G5:** Not-driven-by-one-sector: result survives sector exclusion.

### PIT assumptions

- **Availability fence:** notice date + 7 calendar days (no state posting date in raw data).
- **Intensity z:** trailing-90d worker-count z vs own expanding history (PIT).
- **Beta:** trailing 252 trading days OLS vs SPY (min 120 days).
- **Study window:** 2021-07-06 to 2026-07-02.

## 4. Event study results

| Variant | N | Mean AR | t-stat | SE | p-val | BH-q | G1 | G2 | G3 | G4 |
|---------|---|---------|--------|-----|-------|------|----|----|----|----|
| notice_event_21d | 605 | 0.0031 | 0.59 | 0.0053 | 0.5559 | 0.9651 | FAIL | FAIL | FAIL | — |
| notice_event_63d | 571 | 0.0004 | 0.04 | 0.0097 | 0.9651 | 0.9651 | FAIL | FAIL | FAIL | — |
| intensity_z_21d | 434 | 0.0079 | 0.72 | 0.0081 | 0.4745 | 0.9651 | FAIL | FAIL | FAIL | — |
| intensity_z_63d | 400 | 0.0111 | 0.19 | 0.0140 | 0.8491 | 0.9651 | FAIL | FAIL | FAIL | — |

## 5. Verdict

**NULL — direction gate failed**

Gate G5 (not-driven-by-one-sector) deferred — sector ETF mapping required.

## 6. VPS fallback design (not yet deployed)

Two major-volume states (TX, PA) and two unsupported states (MN, NC) are blocked.
Deploy trigger: >=3 major states blocked simultaneously.
Current count: 2 IP-blocked major states + 2 unsupported = 4 affected, but only
2 are IP-level blocks from this Mac. VPS not yet deployed.

**VPS cron design (146.190.142.17):**
```bash
# /home/deploy/scripts/warn_vps_scrape.sh
#!/bin/bash
WARN_DATA=/home/deploy/warn-raw
WARN_CACHE=/home/deploy/warn-cache
VENV=/home/deploy/.venv-warn/bin/warn-scraper

# Run blocked states weekly
for state in tx pa oh fl mi; do
  $VENV --data-dir $WARN_DATA --cache-dir $WARN_CACHE --log-level warning $state
done

# rsync back to Mac
rsync -avz $WARN_DATA/ mac-local:data/warn/raw-vps/
```
```
# crontab -e on VPS
0 6 * * 1 /home/deploy/scripts/warn_vps_scrape.sh >> /home/deploy/logs/warn_vps.log 2>&1
```

---

*Harness script: `scripts/w2044_warn_intensity_phase0.py`*
*Collector: `collectors/warn_notices.py`*
*Ticker map: `scripts/w2044_warn_ticker_map.csv`*
*Trial grid logged to family `w2044_warn_intensity` (pre-results)*
*Study window: 2021-07-06 to 2026-07-02*
*Data store: data/warn/notices.parquet (NOT committed to git — large binary)*

Generated with [Claude Code](https://claude.com/claude-code)