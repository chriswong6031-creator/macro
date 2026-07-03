# C5 — CIRO Short-Position Δ — Phase-0 Report

**VERDICT: ACCRUE-DATA. The collector was fixed and 19 real CIRO short-position cross-sections landed
(2018-11-30 → 2019-08-31, 38,793 TSX rows), but that is where the reachable archive ends — and those
dates have ZERO overlap with the Canadian name-level price panel (which begins 2021-06-14), so the
pre-registered name-tier short-Δ test is UNRUNNABLE on the historical archive, not merely underpowered.
No gated statistic was computed. C5 becomes a forward-accruing panel: it can reach decision-grade only
once ≥60 semi-monthly cross-sections accrue going forward on dates the name panel covers (≈ 2028).**

Pre-registration: `research/C5_CIRO_SHORT_PREREG.md` (committed before this verdict, branch `hkca-w3-c5`).
Battery: masterplan §4.1 C5. Honest prior going in: genuinely open (US short-interest analogs mixed).

---

## 1. What was actually done this wave

**Part 1 — collector fix (the real work).** `collectors/ciro_short.py` CDX discovery was verified
broken and rewritten. The prior code globbed the Wayback CDX API for `*CSPR*.xls` filenames; those
queries return **zero rows** because the CSPR `.xls` files have opaque GUID filenames (e.g.
`ab44fc63-…_en.xls`) with the report date carried only in the CSPR *page*'s anchor TEXT
(`YYYYMMDD_CSPR_Report`), never in the URL. The collector was silently finding nothing.

The **working route** (verified end-to-end by direct probe, 2026-07-03):
1. CDX-enumerate Wayback snapshots of the CSPR *page*
   (`iiroc.ca/industry/marketmonitoringanalysis/Pages/consolidated-short-position-report.aspx`).
2. Fetch each snapshot's archived HTML; extract every `(report_date, guid_href)` from the anchor list
   (each snapshot lists ~4–10 recent semi-monthly reports).
3. Dedupe by report_date; replay-fetch each file via the full replay host
   `web.archive.org/web/<page_ts>/<href>` (Wayback redirects to the nearest actual capture — the
   `id_` raw variant 404s). Validate OLE2/BIFF magic, parse via `xlrd`.
Polite pacing + exponential backoff on Wayback 503s / connection resets; parquet checkpoint every
5 dates so an interrupted run resumes.

**Part 2 — data landed.** `data/ciro_short/positions.parquet` (548 KB) + `coverage.json` committed
(git-tracked, far under the 20MB R2 threshold). Coverage: **19** distinct report dates,
**2018-11-30 → 2019-08-31**, **38,793** TSX rows, all short_shares populated (100% nonzero after the
column-detection fix, see below). Of the .TO name panel, **71.2%** of tickers map to a CSPR symbol
(**28.8% unmapped** — the panel holds names not short-reported in 2019, plus dual-class/format edge
cases). NOTE the discovery/fetch gap: the page-walk *discovered* **47** report dates (2018-11 →
2021-02), but Wayback *captured the linked .xls files* for only the 2019-era snapshots; the **28**
dates from 2020-03 → 2021-02 return **404** (the files were never crawled).

**Parser bug found and fixed (data-quality gate).** The pre-existing `_parse_xls_bytes` header
detection looked for a "short position" column, but the real CSPR header is
`Security Issue Name | Security Symbol | Exchange Code | No.Shares | Net Change`. It therefore left
`col_shares = None` and emitted a cross-section of **all-zero** short positions. Fixed to match the
real headers (`No.Shares`/`shares`), with Net-Change matched first so it cannot shadow the shares
column, plus a fail-loud guard that raises rather than storing an all-zero cross-section. Verified
against ground truth: BXF short = 63,938 (matches the raw sheet), 2,040 TSX rows/date, 100% nonzero.

**Part 3 — phase-0.** NOT run (gate not met, see §2). Trials pre-registered for the forward-accrual
run and the counterfactual deep-archive.

## 2. Why ACCRUE-DATA (two independent nails — both probed, not assumed)

**Nail 1 — depth below the bar.** The iiroc CSPR page was archived only 2019-01 → 2021-05 (it 404s
after the 2021-05 ciro.ca migration). The page-walk *discovered* 47 report dates spanning
2018-11-30 → 2021-02-15, but only the **19** dates whose files Wayback actually captured
(2018-11-30 → 2019-08-31) are *fetchable*; the 28 later dates 404. Either count — 47 discovered or
19 fetchable — is below the pre-registered decision-grade floor of **60**.
Alternative routes all dead-end (each probed 2026-07-03):
- iiroc `.xls` CDX globs (`/Documents/2021/*_en.xls`, `/Documents/2020/*_en.xls`, three specific
  report GUIDs) → all return `[]` (the files were never independently crawled by Wayback; only the
  page was).
- ciro.ca successor: no snapshot under any `consolidated-short-position-report` slug; its files live
  at opaque `/media/<id>/download` URLs that are also uncaptured (`[]`).
- Live ciro.ca: **403 Cloudflare** challenge to a browser UA on all CSPR slugs.

**Nail 2 — zero overlap with the return panel (the dominant constraint).** The CA **name-level**
price panel (`data/canada_search/closes.parquet`, 219 `.TO` names) begins **2021-06-14**. The
reachable CIRO archive **ends 2019-08-31** (fetchable) / 2021-02-15 (discovered).
Every archived short reading's forward window (even the
1-month primary, lag-honored) falls **entirely before** the panel's first bar. So there is **no
(short-reading, forward-return) pair to test** at the name tier — the test is unrunnable, not merely
low-N. A sector-ETF-tier variant (XEG/XGD/XFN go to 2001) would overlap, but CSPR is a per-security
report; aggregating it to sector-ETF short interest is a different construct not in the C5 spec and
not pre-registered.

Running the §3 gated statistic under either condition would be verification theater; the protocol
forbids an underpowered/unrunnable gated test.

## 3. What this does NOT show

- It does **not** show that CIRO short interest lacks a forward edge. No statistic was computed; the
  question is untested, not answered. The honest prior (open, US analogs mixed) is unchanged.
- It does **not** show the archive is permanently 42-deep — it shows the *historical* archive is, and
  that history cannot be joined to the current return panel. **Forward** collection can build a
  joinable panel from now.
- It does **not** wire any C5 signal into any board, score, or card. NO WIRING (masterplan W3 bar).
- The within-sector neutralization (had the test run) would carry a PIT caveat: the sector map in
  `members.parquet` is today's membership, not point-in-time, and the name panel is
  current-constituent (survivorship). Both would be reported as bounds, not stamps.

## 4. Accrual plan (registry)

`data/experiments/registry_seed.json`:
- Existing `ciro-short-panel` (data_collection) entry corrected: its "accruing forward" premise was
  based on the broken collector + a mis-stated ~2021-10 depth; status/notes updated to the true
  frozen-historical + non-overlapping reality.
- New `c5-ciro-short-delta` phase-0 entry appended (status **accrue-data**), come-back ≈ **2028-01**
  (≥60 FORWARD semi-monthly cross-sections on name-panel dates at twice-monthly cadence), min-N alert
  gate so it does not ping early.

## 5. Reproduction

- Discovery only: `python -m collectors.ciro_short --dry-discover`
- Full backfill: `python -m collectors.ciro_short --full-history`
- Probe evidence (2026-07-03): iiroc page = 20 usable snapshots 2019-01→2021-05; one GUID `.xls`
  replay-fetched = 437 KB `application/vnd.ms-excel` OLE2/BIFF; `/Documents/{2020,2021}/*_en.xls`
  CDX globs = `[]`; ciro.ca CSPR slug + `/media/*/download` = `[]`; live ciro.ca = 403 CF.
