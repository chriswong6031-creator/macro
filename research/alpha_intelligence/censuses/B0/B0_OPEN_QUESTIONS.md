# B0 — Open questions

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`

Preserved UNKNOWN / ACCRUING / BLOCKED states. Not a build list.

---

## BLOCKED (do not resolve inside B)

| ID | Question | Blocker | What would unblock |
|---|---|---|---|
| BQ1 | May B couple to issuer `submissions.zip` / broad EDGAR submissions for manager identity? | FF-1P2 STOP #5898; `DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE` | Sol bound or an alternate design that is not that zip |
| BQ2 | May B write into fundamentals-truth / FIF stores? | FIF-1R3 #5889 DO NOT MERGE | Sol review of FIF |
| BQ3 | May a manager ontology be frozen while #5822 is open? | PASS-0 collision #4 | #5822 concluded or an explicit reconcile note from the CN owner |
| BQ4 | May any 13F-derived family enter Prophet ranking? | `context_only`; `DNR:KILL-OWNERSHIP-BREAKAWAY`; `may_feed_prophet: false` | Eval OS / conditional-fusion gauntlet at K5 — **not a B decision** |

---

## UNKNOWN (this session)

| ID | Question | Why unknown | Cheapest check |
|---|---|---|---|
| U1 | Is `data/ibkr_borrow/daily/` actually accruing on main / the runner? | Sparse worktree omits `data/` | Full checkout `ls` + git log on that path |
| U2 | Is nightly `etf_holdings` completing per sponsor this week? | No production read | Collector run_status / last parquet mtimes |
| U3 | Does `yf_analyst` append dated rows or overwrite one parquet? | Docstring says vendor has no history; write shape unread in full | Read the write path + `git log -- data/analyst/targets.parquet` |
| U4 | Is `QUIVER_API_KEY` present in production? | Env | Runner secret inventory (operator) |
| U5 | ARK Terms of Use — may we snapshot and retain CSVs / trade emails? | Cloudflare on `ark-invest.com/terms` | Fetch from a non-blocked client; Data OS rights pass |
| U6 | Do ARK official CSVs include shares outstanding? | File not fetched this session | One GET of the configured ARKK URL |
| U7 | True `S_f,t` for Global X / Roundhill / SSGA — is it on the same file we already parse? | Columns not re-audited | Header dump of one live file per sponsor |
| U8 | CUSIP→ticker resolution rate on the *universal* census vs the featured desk | Public summary floor is 20%; bench floor 80%; live rates unread | `census_latest.json` coverage fields on a full checkout |
| U9 | Is `share_class_equiv.yml` complete for the featured book? | File not opened | Read + test list |
| U10 | Live atom census health after the 2026-08-18 cadence cut | Postmortem is why it was cut; post-cut success not watched here | `gh run list --workflow smart-money-13f-census.yml` |
| U11 | Does `altdata_models.weighted_score` (which still includes `smart_money_13f` at 0.85 over Quiver `ReportPeriod`) reach Prophet, allocation, or only altdata display? | The channel **exists** (CODE VERIFIED). Fusion file had no hit. Downstream of `altdata_signals.build` / `by_ticker.json` not fully walked. | Trace `weighted_score` consumers; if any scored path remains, that is an altdata-owner defect, not a B new-store |
| U12 | Research-bench R2 private bucket — deployed or empty? | Separate credential namespace in code | Env + one list-objects (operator) |
| U13 | Form ADV / CRD — is there any house store at all? | Filename census found none | Confirm with `context_index` / broader grep |
| U14 | ProShares `psdlyhld.csv` and `historical_nav.csv` — still live, still keyless? | Recon dated 2026-06-13 | One HTTP HEAD/GET |
| U15 | China southbound / holder-count PIT quality at a level B should cite as prior art | Collectors exist; artifacts unread | CN owner or #5822 full read |

---

## ACCRUING (facts that only time answers)

| ID | Question | Clock |
|---|---|---|
| C1 | Does the 700-filing atom budget stay honest on the next 13F deadline day? | Next mid-month 13F crush (~4 days/year) |
| C2 | Dated-ETF CDN floors (Global X ~2026-04-09) — do they advance and erase history? | Monthly HEAD of the oldest URL we still have |
| C3 | Research-bench candidates — will any clear `point_in_time_history_required_for_promotion`? | Quarters, not days |
| C4 | Featured-desk paired-reporter majority clock each filing season | Current quarter +45d |

---

## Open product / ontology questions (do not decide in B0)

| ID | Question | Default if forced |
|---|---|---|
| O1 | Is Coatue / Altimeter class 1 or 2? | Leave **mixed / tiger_crossover** until name-count + turnover are measured |
| O2 | Should ARK's 13F and ARK ETFs share one `complex_id`? | **Yes** as a draft default (duplication D1) |
| O3 | Are class-5 reconstitution residuals in or out of any later "intent" family? | **Out of intent; in as a theme-membership sensor** |
| O4 | Who owns true `S_f,t` if captured — etf_holdings or a new series? | **etf_holdings / holdings existing owner**, new column, not a new store |
| O5 | Linkage to expert-value learning (J) | **Eval OS + Stock Identity at K6**, prospective only |

---

## Questions this census is *not* asking (settled)

- Is 13F perishable? **No.**
- Should B build a second 13F store? **No.**
- Should B expand `smart_money.funds` to thousands? **No.**
- Should missing filers be zero? **No.**
- Should 13F be a positive signal? **No.**
- Should we re-derive the atom 700-filing budget? **No.**
- Should we headless-break iShares? **No.**
