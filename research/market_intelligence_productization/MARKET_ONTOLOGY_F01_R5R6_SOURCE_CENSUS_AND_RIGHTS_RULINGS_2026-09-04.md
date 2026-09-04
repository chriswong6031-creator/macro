# MARKET ONTOLOGY F01 — R5/R6 Source/Rights/Clock Census + CEO Rights Rulings (2026-09-04)

- **Operation**: `marketontology-f01-macro-markets-20260826-fable-001` (WS:MARKET-OS)
- **Record type**: census return + rulings (records-only; no product/runtime effect)
- **Gate discharged**: architecture §12.4 — "Housing, Consumer and Debt each require a
  source/rights/clock census before writes." This document IS that census. It does NOT
  by itself clear producer writes; the per-workspace scopes below do.
- **Method**: three parallel read-only census agents (one per workspace) over the macro
  estate (`config.yml` fred.series registry, collectors/, engine/, data/ on the runner
  checkout, `docs/QUAL_DATA_COMPLIANCE.md`), findings cross-verified by a fourth agent
  against `config.yml:211-214,271-272,295-296,364,367,484,4082-4143` and repo-wide
  greps. Housing parquet freshness leaned on fetch-stamp/audit JSON proxies (that
  agent had no shell) — flagged (unverified) where it matters.
- **Authority note**: rulings below are issued under the 09-04 Chairman full-authority
  grant to this Claude CEO session (Meta-CEO authorization, no-prompt mandate).
  They are conservative continuations of existing estate practice, recorded so a
  later Sol/Chairman pass can overturn them explicitly rather than discover them.

## 1. Headline verdict

None of Housing (§10.10), Consumer & Payments (§10.11), National Debt (§10.12) is
build-ready **as specified**. Each has a thin composable core inside a much larger
required-composition gap. All three ship v1 as **composable-core + typed-ABSENT
remainder** under the `mastermind.macro_workspace_snapshot.v1` contract — the §7
presence/null vocabularies exist precisely so partial workspaces publish honestly
instead of waiting for completeness. Scenario engines and alert logic are ABSENT in
all three (suite-wide net-new work, not per-workspace gaps).

## 2. Housing & Real Estate (§10.10)

**Composable core today**: MORTGAGE30US, HOUST, PERMIT, CSUSHPISA (SA — see ruling
R-1), national ZORI rent. Level/trend panel only.

**Reruns, not new code**: `scripts/collect_redfin_hf.py` exists and is nightly-wired
but `data/redfin_hf/` was EMPTY on the checked runner (silent-fail try/except);
`collect_zori.py` writes metro+national but only `national.parquet` exists. Both need
a populate/heal pass and a loud-fail follow-up.

**New collectors needed**: completions (no COMPUTSA-equivalent registered anywhere);
existing/pending home sales — NAR is rights-blocked for storage (see R-3), so build
from Census New Residential Sales; an in-house affordability construct (never claim
it as "the NAR index").

**Clock/PIT traps (inherit, do not rediscover — `scripts/housing_hf_phase0.py`)**:
no ALFRED vintage capture exists for ANY housing series today; Redfin needs a +50-day
PIT lag (30 days was proven optimistic by 2–3 weeks); Redfin price-drops share is
~34.5% pure seasonality if not deseasonalized; Case-Shiller is a ~2-month-lagged
3-month moving average; CSUSHPISA is SA while Redfin/ZORI are NSA — no mixing without
normalization. Four distinct cadences (weekly/monthly×3 lags) on one workspace: every
metric carries its own reference_period/available_at clocks per §7, no shared "asof".

**Phase-0 prior**: the Redfin-signals-vs-XHB conditioning study returned NULL. The
workspace is a state describer, not a signal claim — do not resurrect the null result
as implied alpha.

## 3. Consumer & Payments (§10.11)

**Composable core today**: UMich sentiment + PCE price momentum (PCEPI/PCEPILFE) +
W875RX1 real income ex-transfers (label it exactly that — it is NOT headline real or
disposable income), all PIT-safe via existing ALFRED machinery.

**The bottleneck is config completeness, not engineering**: G.19 credit
(TOTALSL/REVOLSL/NONREVSL), PSAVERT, DSPIC96, PCEC96, DRCCLACBS/DRSFRMACBS are plain
`config.yml` fred.series appends on the existing generic FRED collector.

**Code fix owed**: RSAFS data landed (fresh through 2026-07) but
`engine/release_targets_v11.py:363-390` still hard-codes `no_data` with a stale
2026-07-08 comment — re-wire. `scripts/official_release_parsers.py:329-896` parses the
BEA Personal Income & Outlays release but extracts only the PCE price fields; income/
DPI/spending/saving-rate are in the same release, unparsed.

**Payments proxies (required-composition item 5)**: PERMANENTLY ABSENT per the
standing, dated ruling `docs/QUAL_DATA_COMPLIANCE.md` §2.3 excluding card/transaction
panels (Yipit, Earnest, Consumer Edge, Second Measure and equivalents) by name. That
ruling satisfies the architecture's rights-ruling requirement for this item; the v1
workspace publishes the slot as typed ABSENT with the ruling cited. Household
delinquency comes rights-safe from the NY Fed Quarterly Household Debt & Credit
Report (public; PDF/xlsx collector — net-new, low frequency).

**Clock traps**: BEA PCE/income lag ≈ 59 calendar days (ALFRED median,
`engine/pit.py:119-120`) vs CPI ≈ 32 business days; UMich preliminary-vs-final prints
are not distinguished today (lag_bd: 0 treats mid-month prelim as final); no SA-
methodology-change handling for PCE/retail/credit. Nominal/real mislabeling is live:
PCEPI is a price index, W875RX1 is real — no real spending LEVEL exists yet to
cross-check a naive composer.

## 4. National Debt & Liabilities (§10.12)

**Composable core today, no new collector**: TGA/cash-flow panel (treasury_watch.v1
is already a live, threshold-gated production alert — the one real alert leg in the
suite, and the internal precedent for stock-vs-flow discipline); auction-demand panel
(bid-to-cover / indirect / dealer shares, 758 auctions through 09-03) — needs
extraction from its bonds.html inline embed into a standalone `site/*.json` contract;
debt/GDP + deficit/GDP from IMF WEO (see trap below); BIS credit-gap/DSR strip
(attribution-only license — every surface showing BIS figures carries attribution,
`config.yml:4082`).

**Load-bearing gap**: the estate has NO debt STOCK anywhere — only issuance flow.
Required-composition item 1 is impossible without a **Debt to the Penny** collector
(`fiscaldata.treasury.gov/api/v2/accounting/od/debt_to_penny`, public, keyless).
Also net-new: Monthly Treasury Statement family ($-level receipts/outlays → net
interest burden), TIC foreign holdings by country, MSPD/WAM maturity ladder,
contingent liabilities (Trustees reports, low-frequency), and a structured
debt-limit/X-date detector ("debt ceiling" is only a news-tone keyword today).

**Clock traps**: IMF WEO mixes history and projections in one unflagged column
through 2031 — split into observed vs projected (distinct value_status) before any
"last row" read; any future MTS collector tags fiscal-year (Oct–Sep) from day one
(nothing in the codebase does this); extraordinary-measures periods distort raw
Debt-to-the-Penny during debt-limit episodes — the detector and the series ship
together; auction preliminary-vs-final unguarded (currently unexercised).

## 5. CEO rights rulings (recorded for later overturn, not silent)

- **R-1 (Case-Shiller via FRED)** — CONTINUE current-practice use of the
  FRED-published CSUSHPISA series: derived/aggregate display with source attribution,
  no bulk redistribution of the underlying S&P DJI dataset, no city-tier expansion
  without written clearance. Basis: the series already flows through shipped estate
  surfaces (`engine/cycle_proxies.py:299-302` bottleneck band); this ruling adds no
  new exposure class, and FRED's own redistribution of the series is the transport.
  Risk accepted and recorded; the open safe-harbor question stays flagged for a
  Sol/Chairman legal pass. Escalation trigger: any S&P DJI takedown or license
  contact → pull the surface same-day.
- **R-2 (Freddie PMMS via FRED)** — same posture and basis as R-1 for MORTGAGE30US
  (already ingested daily estate-wide). Same escalation trigger.
- **R-3 (NAR)** — AFFIRM the prior audit: NAR terms bar storage in a retrieval
  system, not merely redistribution ⇒ rights_blocked for storage. No NAR-derived
  series enters the store; the affordability leg is built in-house from public
  inputs and never labeled as NAR's index. (Prior art:
  `research/imce/hb0/evidence/L7_source_pit_vintage.md`,
  `agentos/discoveries/DSC-NAR-TERMS-BAR-STORAGE-NOT-ONLY-REDISTRIBUTION.md`.)
- **R-4 (card/payments panels)** — AFFIRM `docs/QUAL_DATA_COMPLIANCE.md` §2.3 as
  binding; Consumer item 5 is typed ABSENT, not pending.
- **R-5 (Redfin/Zillow ToS capture)** — both are collected in practice with no ToS
  text captured in-repo; the R5 producer child captures the current public-terms text
  into the evidence directory at build time (one-time, low cost) so the posture is
  auditable.

## 6. Producer scopes cleared by this census

- **R5-Housing child**: core panel (5 series) + heal-reruns + typed-ABSENT remainder;
  new collectors (completions, New Residential Sales) may land in the same child or a
  follow-up; NAR excluded per R-3.
- **R5-Consumer child**: config appends (G.19/PSAVERT/DSPIC96/PCEC96/delinquency
  rates) + RSAFS nowcast re-wire + core panel; BEA parser extension and NY Fed QHDC
  collector as follow-ups; item 5 typed ABSENT per R-4.
- **R6-Debt child**: Debt-to-the-Penny collector (the unblocking brick) + TGA/auction
  panels from existing data + IMF split + BIS attribution; MTS/TIC/WAM/contingent as
  follow-ups; debt-limit detector ships with the Penny series.

All three children publish under `mastermind.macro_workspace_snapshot.v1` with the
R1A composer pattern (post-fix-wave head) and are sequenced after the R2 MCS wave per
§12. Every ABSENT slot carries its null_reason and, where rights-based, cites the
ruling above by ID.
