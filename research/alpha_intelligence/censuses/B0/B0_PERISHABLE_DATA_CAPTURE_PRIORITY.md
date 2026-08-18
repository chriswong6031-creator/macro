# B0 — Perishable-data capture priority

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`
**PASS-0 §8 ruling, re-checked against the tree:** there is **no emergency clock on 13F**. The SEC archive is permanent. Amendment lineage already lives in `engine/institutional_census/`. This file adjudicates the *other* clocks PASS-0 named as unconfirmed.

**No capture is authorized here.** A later capture PR still needs: source-rights verdict, Data OS routing, off-render R2 placement, its own PR.

---

## Verdict table

| # | Series | Perishable? | Capture already in-tree? | Tonight's miss recoverable? | Priority if a capture wave is later allowed | Binding stops |
|---|---|---|---|---|---|---|
| P0 | 13F-HR / A / NT + DERA quarterly zips | **No** (archive) | **Yes** — universal census + curated desk | Yes, from EDGAR / DERA | **Do not add capture.** Harden the existing lanes only if they go red. | Do not use `submissions.zip` (FF-1P2 STOP #5898). Do not re-derive atom 700-filing budget. |
| P1 | IBKR borrow fee + available shares | **Yes — no vendor history** | Collector **yes** (`collectors/ibkr_borrow.py`, `scripts/collect.py`). Daily immutable file designed. **PRODUCTION UNKNOWN** whether nightly is actually committing `data/ibkr_borrow/daily/`. No dedicated workflow. | **No** | **P1 — first perishable to *verify*, not rebuild.** Confirm the nightly write + git/R2 persistence. If it is dark, turning it on is recovery, not a new system. | Display/context only. Do not fuse into scores. |
| P2 | Sponsor **current-only** ETF holdings (SSGA, Invesco, VanEck, Sprott, First Trust, ETC, …) | **Yes — current file replaced daily** | Forward collector **yes**. History = nights we ran. | **No** (Wayback irregular; recon already rejected it as a plan) | **P2 — verify nightly `etf_holdings` success rate per sponsor**, then consider adding ProShares one-file dump (rights pending). | iShares/Schwab remain blocked. Vanguard unsupported. Off render path. |
| P3 | ARK EOD holdings CSV | **Yes for history; vendor keeps only current URL** | **Yes** for ARKK+ARKW. Other ARK active ETFs **not** in `holdings.watchlist`. | **No** for a missed day | **P3 — optional vehicle expansion** (ARKG/Q/F/X) inside the existing collector, after ToS read. Trade-email feed is a separate rights question. | Do not duplicate ARK into `etf_holdings`. |
| P4 | Dated ETF holdings (Global X, Roundhill, Amplify) | **Partial.** URLs still serve a lookback (weeks to ~2024). | **Yes** + `scripts/backfill_etf.py` | Mostly yes inside the CDN floor; no beyond it | **P4 — already the right shape.** Keep backfill off the render path. Re-pull near the CDN floor so the floor does not silently advance. | Amplify public Firebase key. Roundhill soft-404 validation. |
| P5 | yfinance analyst consensus (`.info`) | **Yes if the house parquet is overwritten** | Collector **yes**, display-only. Vendor has **no** history. | **No** once overwritten | **P5 — verify storage shape** (append-by-date vs single current row). If single-row, this is a silent perishable. | Never score. Revisions > levels (existing review). |
| P6 | Quiver event streams | **Vendor-dependent.** House keep-first `_first_seen` protects *our* first observation. | **Yes** if `QUIVER_API_KEY` present | Vendor may still serve old events; `_first_seen` is the perishable part | **P6 — confirm key + ingest heartbeat.** Do not add Quiver 13F. | Vendor ToS. |
| P7 | Attention / news-stream states | Mixed | Quiver news adapter exists; marketing press wire is a different owner | Headline streams are perishable; EDGAR/8-K are not | **Out of B's owner box.** Cite, don't capture. | KILL-LLM-ORIGINATION; marketing lanes are occupied. |
| P8 | N-PORT quarterly | **No** (EDGAR) | Mentioned as validation-only; **no live N-PORT collector found** this session | Yes | **Research candidate**, not perishable. Build only as a quarterly audit of P2/P3/P4. | Not a live signal (`collectors/holdings.py` docstring). |
| P9 | ProShares daily holdings + historical_nav SO/AUM | Holdings file current-only; **NAV/SO file is historical** | **No** | Holdings: no. NAV file: yes if still published | **Best new official-adjacent candidate** for true `S_f,t` and class 8 labeling. Rights unread. | Class 8 must not enter conviction boards. |
| P10 | China/HK official daily holder tapes | Varies | **Yes** in CN/HK collectors (southbound, holder counts, LHB) | Some CN vendor snapshots are perishable | **Not a US-B capture.** Reconcile via #5822. | Do not port LHB. |

---

## 13F is not perishable — receipts

- DERA Form 13F data sets on sec.gov this session: **2013-Q2 through 2026 Mar–May zip** (PRIMARY SOURCE VERIFIED).
- Rolling discovery: atom (hourly 12–20Z) + previous-day master index (06:17Z) + Sunday full-index repair (CODE VERIFIED workflow). A missed atom poll fails loud at 700 new filings (`DSC:13F-ATOM-POLL-BUDGET-IS-700-FILINGS`) and the index lanes recover accessions.
- Curated desk: submissions JSON lists every historical 13F-HR for a CIK; originals are re-fetchable.
- Therefore **starting a new 13F scrape today does not save data that would otherwise vanish.**

What *can* go stale is **operations**: a frozen census that stays silent (#5607 tripwire), or the lane starving the nightly (2026-08-17 postmortem). That is a runner-budget problem, already re-cut (#5850), not a capture-priority problem.

---

## Priority if (and only if) a later wave is allowed to touch capture

1. **Prove P1 is accruing.** One command on a full checkout: `ls data/ibkr_borrow/daily | tail`. If the series has gaps after the collector merged, the miss is already unrecoverable — start *forward* persistence, do not backfill fiction.
2. **Prove P2 nightly completeness** per sponsor (ok-count already logged by `EtfHoldingsAdapter.fetch`). Gaps on SSGA/VanEck are lost days.
3. **Read ARK + ProShares ToS**, then decide P3 expansion and P9 SO history.
4. **Fix P5 storage** to dated snapshots if it is a single current parquet.
5. **Do not** start N-PORT, iShares headless, Vanguard, Quiver-13F, or anything that routes around FF-1.

---

## What this session could not verify

- Live existence of `data/ibkr_borrow/daily/*.parquet` on main or on the runner (sparse worktree).
- Live existence of `data/etf_holdings/**` freshness.
- Whether `yf_analyst` appends or overwrites.
- Whether `QUIVER_API_KEY` is present in production.
- ARK Terms of Use body (Cloudflare).
