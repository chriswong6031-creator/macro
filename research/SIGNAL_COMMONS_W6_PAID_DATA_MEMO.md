# W6 — Paid-Data Decision Memo (Signal Commons)

> **USER DECISION 2026-07-05: SKIP ALL purchases — zero new monthly spend.** Re-buy trigger for FMP Ultimate recorded in `SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md` §7 (needs: a chartered consumer OR measured lead in our own PIT accrual; AND a PIT-integrity audit of FMP history vs our self-recorded snapshots; AND favorable net cost after weighing partial Quiver consolidation). Options-tape classification is not a purchase — ThetaData already entitles the per-trade NBBO tape (R6 amended); it is re-chartered to the options-alpha program as an engineering item.

---

## W6 — Paid-Data Decision Memo (Signal Commons program)

**Status:** DRAFT for one consolidated user decision. Display-only house laws apply to everything these feeds unlock (R7). Do not commit — main session commits.
**Provenance:** grounded in the 5-lane census (`SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md` §5) + live code/probe facts cited inline. Prices marked **UNVERIFIED** could not be pinned to the dollar via web (403/no public snippet); ranges given.

> ### In plain English
> You already pay for 4 data feeds. Before buying anything new, two of these six "gaps" turn out to be non-gaps:
> - **Options trade-by-trade tape (Leg 4): you ALREADY have it.** The ThetaData tier you bought on 2026-07-04 includes the per-trade + NBBO tape — our own calibration script already pulled 16,366 real trades from it. Databento's $199/mo would be paying twice. The work here is engineering, not buying.
> - **ETF creation/redemption flows (Leg 5): buy nothing.** Free government (SEC N-PORT) + ProShares files + the dated ETF-holdings snapshots we already save give a good-enough shares-outstanding proxy.
> The only thing arguably worth **buying now** is FMP's top plan (~$99/mo, UNVERIFIED), because ONE subscription unlocks three of the remaining legs (transcripts, PIT analyst estimates incl. revenue-revision direction, ratings history). Everything else is TRIAL or SKIP. **Recommended BUY-NOW spend: ~$99/mo** (one plan), pending you confirm the exact FMP price on their portal.

### Decision table

| # | Leg (what it is) | Unlocks (parked build) | Best vendor | $/mo | Integration effort | EV verdict |
|---|---|---|---|---|---|---|
| 1 | Earnings-call transcripts | Language-delta engine (R5) | **FMP Ultimate** (transcripts bundled) | ~$99 UNVERIFIED | New adapter; no collector today | TRIAL — bundled w/ Legs 2–3 |
| 2 | PIT analyst estimate/revision history incl. **revenue-revision direction** | Expectation-drift legs (R5); fixes yfinance structural gap + our cold-start | **FMP Ultimate** (or Finnhub Estimates) | ~$99 UNVERIFIED (FMP) / $75 (Finnhub) | New adapter; extends `analyst_revisions.py` | **BUY (via FMP bundle)** — highest EV of the set |
| 3 | Per-analyst accuracy / upgrade-downgrade event feed | Analyst-credibility weighting | **Finnhub** upgrade/downgrade | ~$50–75 | Extends existing `finnhub_altdata.py` key | TRIAL — or free-ride FMP/TipRanks grades |
| 4 | Options per-trade NBBO tape (flow classification) | Options flow classification (R6): sweep/block, buyer/seller-init, open/close | **ThetaData — ALREADY OWNED** | **$0 new** | Scale existing `collectors/thetadata.py trade_quote()` from sample to prod | **BUY-NOW = already paid; SKIP Databento** |
| 5 | ETF creation/redemption flows | ETF flow radar (parked-list row) | **Free**: SEC N-PORT + ProShares + own snapshots | **$0** | New collectors (medium); proxy from existing `data/etf_holdings/` (low) | **SKIP paid** — free proxy suffices |
| 6 | Higher-freq short interest (Ortex/S3) | Faster short-squeeze/de-esc read | Ortex Advanced (real-time) / Basic (delayed) | $129 / $39 | New adapter | **SKIP** — free FINRA (W0) dominates on cost |

Databento OPRA Standard $199/mo listed only to show it is **redundant** vs Leg 4.

---

### Per-leg detail

**Leg 1 — Earnings-call transcripts (→ language-delta engine, R5).**
No transcript collector exists today; this is a **new adapter**. Candidates: **FMP** bundles transcripts into its top ("Ultimate") plan (~$99/mo, **UNVERIFIED** exact figure — search confirmed the plan *includes* transcripts and that FMP plans "range from $99/mo", but the portal 403'd on the exact Ultimate line); **Finnhub** offers 15+yr transcripts but gates them behind Fundamentals ($50/mo) + likely Estimates ($75/mo) — so on Finnhub transcripts are *not* cheaper than FMP once you need Legs 2–3 too; **API-Ninjas** has a cheap standalone transcript endpoint (Developer/Business tiers, **UNVERIFIED** — pricing page gave no per-month figure; historically ~$20–50/mo) but is transcripts-ONLY, no estimates. EV: language-delta is an unbuilt, un-gauntleted research idea — buy transcripts only as a *rider* on a plan you'd buy anyway (FMP for Leg 2), never standalone. **TRIAL** (comes free with the FMP BUY).

**Leg 2 — PIT analyst estimates incl. revenue-revision DIRECTION (→ expectation-drift, R5). HIGHEST EV.**
Census (`engine/analyst_revisions.py` header; §5 "Expectations") confirms the two real gaps: (a) yfinance **structurally lacks** forward revenue-estimate revision direction; (b) our own PIT accrual (yfinance EPS-revision breadth) "recently started" → **cold-start**: no back-history to gauntlet against. A vendor with *historical* PIT estimate panels fixes cold-start instantly (backfill) AND adds revenue-revision direction. **FMP** Ultimate carries estimate history + (via TipRanks partnership) forecasts/targets/grades; **Finnhub** Estimates tier ($75/mo) carries 25yr estimate history; **Zacks** has the canonical revisions product but is enterprise-priced/redistribution-restricted (**UNVERIFIED**, effectively out of budget scope). Effort: new adapter, extends `analyst_revisions.py` (which already normalizes Finnhub recommendation panels). EV: this is the leg that both **unblocks a parked build AND retires a structural yfinance limitation AND kills a cold-start** — the strongest single purchase. **BUY (via FMP).**

**Leg 3 — Per-analyst accuracy / upgrade-downgrade feed.**
The ~$50/mo note in `analyst_revisions.py` is real but refers to Finnhub's *Fundamentals* gate; the **upgrade/downgrade event feed** rides Finnhub Estimates (~$75/mo, verified range $11.99–$99.99 with estimates at $75). Per-individual-analyst accuracy (TipRanks-grade) is enterprise-only on Finnhub. Effort: **low** — extends the existing Finnhub key/`finnhub_altdata.py`. EV: modest; firm-level upgrade/downgrade timing is partly already inferable from the monthly recommendation-trend deltas we collect free. If FMP (Leg 2) is bought, its TipRanks-sourced grades cover much of this. **TRIAL** — evaluate only if FMP's ratings coverage proves thin.

**Leg 4 — Options per-trade NBBO tape. THE STALE PREMISE — already entitled.**
The masterplan R6 ("NBBO tape not entitled") and `engine/options_flow.py:22` ("both 403 on our plan") describe the **old Polygon/massive** plan and are **now stale**. Live facts:
- `collectors/thetadata.py:861` implements `trade_quote()` = "every trade paired with the prevailing NBBO at execution" via `/v3/option/history/trade_quote`.
- `research/THETADATA_PROBE.md` §4.3: the calibration run pulled **16,366 real trade+NBBO records** across 15 SPY contracts (agreement 0.88) under the **ThetaData tier acquired 2026-07-04**. The tape is entitled and working.
- ThetaData public tiers (verified): Value $40 / Standard $80 / Pro $160; Standard+ include "every NBBO quote reported by OPRA" + tick data; Pro adds full trade streaming. The "Professional" tier in our probe = the Pro/$160 line already paid.
So **Databento OPRA Standard ($199/mo, verified) is redundant** — buying it would pay twice for the same OPRA tape. The real gap is **engineering**: today `trade_quote()` is used only for a 15-contract calibration sample; production flow-classification (sweep/block, open/close attribution) needs the collector scaled to full-chain per-name, which is a **compute/render-budget** problem (per-contract iteration is slow: greeks/eod ~9.8 rows/s), not a procurement one — it belongs off the render path with R2 artifacts. **BUY-NOW cost = $0 (already own it). SKIP Databento. Flag: correct R6/`options_flow.py` comment as stale.**

**Leg 5 — ETF creation/redemption flows. Free proxy wins.**
`research/ETF_DATA_SOURCES.md` documents free, dated, keyless sources already scoped: **SEC EDGAR N-PORT** carries *embedded monthly creation/redemption flow* + full holdings (quarterly, ~1–2mo lag, backfillable, needs only a real UA); **ProShares `historical_nav.csv`** = multi-year dated shares-outstanding + AUM = fund-level flow history, keyless. On top of that, we already save **dated `data/etf_holdings/` snapshots** (Global X + Roundhill, live in the collector) — differencing shares-outstanding across dated snapshots is a **free proxy for net creation/redemption** requiring zero new feed (low effort, existing data). No paid ETF-flow feed clears the bar (FMP/Tiingo/EODHD ETF-holdings are paywalled per that doc and would duplicate what N-PORT gives free). **SKIP paid; build the free proxy if a consumer program funds it.**

**Leg 6 — Higher-frequency short interest (Ortex/S3) vs free FINRA (W0).**
W0 makes FINRA a PIT-accruing store on top of two existing free collectors: `collectors/finra.py` (bi-monthly consolidated short **interest**) + `collectors/finra_short_volume.py` (daily consolidated short **volume**, already a rolling panel). Ortex (verified: Basic $39/mo delayed, Advanced $129/mo real-time) buys **estimated** daily short interest + utilization/cost-to-borrow — data FINRA doesn't publish. But: (a) our whole positioning doctrine is display-only-until-gauntleted, and short interest has **no PIT history** to gauntlet (the exact reason R3 forbids the "+74" fusion); (b) W0's free FINRA accrual is *itself* the just-started PIT tape — paying Ortex before that tape has any measured lead is buying an un-testable ingredient. Ortex's utilization/CTB fields are its only genuine additive content, and there's no funded consumer for them. **SKIP** — revisit only if a post-W0 phase-0 shows the free FINRA lead is real and a squeeze-desk consumer demands utilization/CTB.

---

### Recommendation split

**BUY NOW** — total **~$99/mo** (UNVERIFIED exact figure; confirm on FMP portal before purchase):
- **FMP Ultimate (~$99/mo)** — single subscription unlocks **Leg 2** (PIT estimate history + revenue-revision direction; fixes yfinance structural gap + cold-start) and **rides Leg 1** (transcripts) and much of **Leg 3** (TipRanks grades) for free. One plan, three legs.
- **ThetaData options tape (Leg 4): $0 incremental** — already owned; action item is engineering (scale `trade_quote()` to production, off render path) + correcting the stale "not entitled" claim in R6 / `options_flow.py`.

**TRIAL** (buy only if the BUY-NOW plan proves thin on that dimension):
- **Finnhub Estimates ($75/mo)** for Leg 3 upgrade/downgrade events + a second estimate source — only if FMP's ratings/revenue-revision coverage is inadequate on evaluation.
- **API-Ninjas transcripts** (~$20–50/mo, UNVERIFIED) — only if FMP transcript coverage/quality disappoints and you want transcripts standalone.

**SKIP**:
- **Databento OPRA ($199/mo)** — redundant with the ThetaData tape already paid for.
- **Any paid ETF-flow feed** — free N-PORT + ProShares + own dated snapshots suffice (Leg 5).
- **Ortex / S3 ($39–129/mo)** — free FINRA (W0) dominates on cost; short interest has no PIT history to justify paying yet (Leg 6).

**Net new monthly spend if you approve BUY-NOW as recommended: ~$99/mo** (one FMP subscription), versus the ~$400+/mo you'd spend if each leg were bought independently (Databento $199 + Finnhub $75 + Ortex $129 + transcripts).