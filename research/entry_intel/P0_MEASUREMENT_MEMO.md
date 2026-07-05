# P0 Measurement Memo — Survivorship Bias Adjudication

**Program:** Entry Intelligence (EI) — Phase 0, Task P0.2 (memo half)
**Version:** v1.0 — 2026-07-04
**Produced by:** Opus (adjudication subagent), consuming the P0.2 Survivorship Census
**Consumes:** `research/entry_intel/P0_2_SURVIVORSHIP_CENSUS.md`
**Constitution:** EI masterplan §3 (inherited law — survivor-bias stamps where delisted coverage absent), §4/P0.2, R8, R9. Setup Species constitution §1.
**Status:** LAW for Phase 1. Every P1 PREREG (P1.1–P1.5) MUST cite this memo's era table by version + date. Amendable only by Fable.

> **Adjudication stance (house law):** where the census is ambiguous, the **stricter stamp wins**. This memo does not offer a menu; it renders verdicts. Coverage percentages alone do not buy a verdict grade — *delisted* coverage is what bounds survivorship bias, and delisted coverage is the axis this memo grades on.

---

## §0 The one fact that drives everything

Survivorship bias is not bounded by *overall* price coverage. It is bounded by whether the **removed / delisted / acquired names** carry price history in the panel the replay actually reads. A panel can cover 90% of member-months and still be lethally biased if the missing 10% is disproportionately the names that failed or were acquired.

The census establishes exactly one store that achieves **verifiable near-total delisted recall**: the Massive whole-market store (`data/massive_stock_day/`, 20,476 tickers), on its **rolling 5-year window 2021-07-06 → 2026-07-02**. Within that window, **17/17 (100%)** probed 2021–2026 S&P 500 delistings/acquisitions are present with complete history through their last trading day (SIVB, FRC, ATVI, SGEN, VMW, SPLK, TWTR, CERN, XLNX, MXIM, NUAN, ZNGA, PBCT, Y, JNPR, NLSN, CTLT), and all 105 names removed from the S&P 500 since the window start are present. Every store other than Massive has **no verifiable delisted-recall floor** and, per the census, leaves **92.7% of delisted member-months invisible to the production panel** and **~31% invisible even to the full research panel**.

Therefore the verdict-grade floor is a **hard calendar boundary: 2021-07-06**, and it is **conditional on the replay reading Massive directly for delisted names.** This is the axis on which the era table below is built.

---

## §1 THE ERA TABLE (authoritative — cite by version)

**P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04).** Grades apply to the terminal-state / MAE-MFE / hit-rate verdict claims each P1 study computes.

| Era | Grade | Prod-panel cov | Full-research-panel cov | Delisted recall (Massive) | Census justification |
|-----|-------|---------------|------------------------|--------------------------|----------------------|
| **2021+** (2021-07-06 → present) | **VERDICT-GRADE** — *conditional* (see §1.1) | 90% | 96% | **100%** (17/17 probe; 105/105 removals) | Massive rolling-5y window covers this era with verified 100% delisted recall; only 9.7% of member-months missing from prod panel and every tested removal is present. Bias is bounded AND stampable. |
| **2012–2020** | **CONTEXT-ONLY** — survivor-stamp on ALL verdicts | 69% | 83% | **0%** (window does not reach) | No delisted store reaches before 2021-07-06. 31.3% of member-months missing from prod panel; ~31% of *delisted* member-months invisible even to the full research panel. `_closes_delisted` is a 199-ticker manual backfill with no recall guarantee. Bias direction indeterminate, magnitude unbounded → cannot certify. |
| **pre-2012** | **FORBIDDEN** for verdict-grade; CONTEXT-ONLY with heavy caveat | 46% | 72% | **0%** | Census verbatim: "the true magnitude of win-rate inflation is unknown. Cannot make verdict-grade claims." 54% of member-months missing from prod panel; 28.5% missing even from full panel. No delisted recall floor of any kind. Stricter-wins → FORBIDDEN. |

### §1.1 The 2021+ conditionality clause (BINDING)

2021+ is verdict-grade **only for replay rows whose price series was sourced from the Massive store** (or a store with an equivalent, audited delisted-recall floor). The census is explicit that the production panel alone leaves **92.7% of delisted member-months invisible**; a 2021+ replay that reads only `data/stocks + _closes_cache + yahoo` is **NOT verdict-grade** despite the 90% headline coverage, because the missing 10% is concentrated in exactly the removed names.

Operationally, for a 2021+ row to earn `survivor_bias = false`, BOTH must hold:
1. **Source condition:** the row's price series (through its terminal-state horizon) was read from the Massive store, OR from a store proven to contain the name's full history through its last trading day.
2. **Window condition:** the signal date AND the full grading horizon (up to 126d forward) fall inside 2021-07-06 → last-full-replay-date. A signal near the window's leading edge whose 126d horizon spills past the last replay date is **right-censored, not survivor-biased** — that is a separate `horizon_censored` flag, not a survivor stamp, and such rows are excluded from horizon-dependent verdicts at the censored horizon only.

If the P0.1 replay harness does **not** read Massive for delisted names in the 2021+ window, then 2021+ collapses to CONTEXT-ONLY and this memo must be amended before any P1 verdict is rendered. The P0.1 PIT audit (R8) is the gate that confirms which store fed each row; P1 studies inherit that provenance via the replay's per-row source stamp.

### §1.2 Why not a "2015-present" primary window?

The PREREG drafts (written before this memo) hypothesized a **2015–present** or "PIT-certified" primary window and a **pre-2015** survivor-stamp boundary. **That hypothesis is REJECTED by the census.** There is no delisted-recall evidence anywhere between 2012 and 2021-07-06 — `_closes_delisted` is a 199-name manual backfill with no audited recall, and Massive does not reach back that far. A 2015-2020 sub-window would carry the same unbounded delisted bias as 2012-2014. Under stricter-wins, the boundary is **2021-07-06, not 2015-01-01.** P1 studies MUST use the 2021-07-06 boundary and MUST NOT fall back to the PREREG's placeholder 2015 date. Where a PREREG text says "pre-2015," read it as "outside the 2021+ Massive-sourced window."

---

## §2 STAMP RULES (exact, machine-checkable)

The replay artifact (`data/replay/…`, per R9) carries a per-row boolean. PREREGs reference it under three names — `survivor_bias`, `survivor_stamp`, `survivor_biased` — all denote the **same** condition defined here. (P1.2 uses the string value `survivor_priced` for the stamped state; that is the string form of `survivor_bias = true`.)

### §2.1 A row is UNSTAMPED (`survivor_bias = false`) if and only if ALL hold:

- **S1 — Era:** signal_date ≥ 2021-07-06.
- **S2 — Source:** the price series used to grade the row (signal bar through its evaluated horizon) was read from the Massive store, or from a store audited to contain the name's full history through its last trading day.
- **S3 — Horizon integrity:** the evaluated horizon does not extend past the last-full-replay-date (else the row is `horizon_censored` at that horizon; see §1.1(2)). A row may be unstamped at 21d and censored at 126d simultaneously — the stamp is evaluated per horizon.

If any of S1/S2 fails → the row is **STAMPED** (`survivor_bias = true`).

### §2.2 The stamp is STRICT (default-true on ambiguity)

- Any row whose price source cannot be positively confirmed as Massive-or-equivalent → **STAMPED.** Absence of a source stamp is treated as failure of S2, not as a pass.
- Any 2012–2020 or pre-2012 row → **STAMPED**, unconditionally. No 2012–2020 row is ever unstamped, regardless of that name's individual coverage, because the *era* lacks a delisted-recall floor. (Per-name coverage cannot rescue an era with no delisted store — the survivorship you cannot see is in the names you no longer have, not the ones you do.)
- Corollary: the P1.5 PREREG's per-name gate ("coverage ≥ 50% of PIT member-months") is a **necessary-not-sufficient** hygiene filter *within* the 2021+ verdict window. It never unstamps a pre-2021 row.

### §2.3 The stamp text (inherited-law mandate, §4/P0.2)

Every stamped replay output and every context-appendix table MUST carry:

> **survivor-biased panel: [X]% of member-months lack price history for this era; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade.**

with `[X]` = the era's prod-panel missing fraction from the census (**54.0%** pre-2012, **31.3%** 2012–2020). If the study reads the full research panel, it may additionally print the full-panel missing fraction (**28.5%** / **17.2%**) but the stamp remains — reduced coverage is not bounded bias.

### §2.4 How P1 studies MUST handle stamped rows (BINDING on all five PREREGs)

1. **Primary results run on UNSTAMPED rows only** (the 2021+ Massive-sourced window). All verdict-grade statistics — terminal-state rates, MAE/MFE, hit rates, Wilson bounds, BH p-values, GO/NO-GO and flip-criterion evaluations — are computed exclusively on `survivor_bias = false` rows.
2. **Stamped rows go to a CONTEXT APPENDIX ONLY**, labeled verbatim: **"PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE."** They are printed for directional transparency.
3. **Stamped rows are EXCLUDED from every BH family**, from both-halves sign-stability tests, from episode-cluster n-floors used for verdicts, and from any promotion / demotion / flip decision. No GO/NO-GO or keep/demote/flip language may attach to a stamped-row statistic.
4. **No mixing.** A statistic computed on a union of stamped and unstamped rows is a protocol violation; report the two partitions separately or not at all.
5. **Era citation.** Each study's preamble prints: this memo's version+date, the exact primary window (2021-07-06 → last-full-replay-date), the count of unstamped rows, the count of stamped rows excluded, and the count of `horizon_censored` rows excluded per horizon.
6. **Thin-window honesty.** The 2021+ window is short (~5 years, ~30k member-months of prod coverage) and episode-clustered n will be small. Studies that cannot reach their PREREG'd episode-clustered n floor on unstamped rows return **INSUFFICIENT-POWER**, NOT a verdict borrowed from stamped rows. Under-power is an honest null; laundering it with pre-2021 data is forbidden (R3 laundering prohibition applies by analogy — foreign-era evidence transfers as hypothesis, not validation).

---

## §3 BACKFILL RECOMMENDATION (verdict, not a menu)

**Question:** Is a Massive-store delisted backfill worth doing for 2021+? **VERDICT: YES — and it is the single highest-leverage Phase-0 data action. Do it. It is not optional for 2021+ verdict-grade claims; it is the enabling condition.**

**Reasoning.** The census already proved the payload exists and is complete: Massive holds 100% of 2021–2026 delistings with full history through last trading day. The "backfill" is therefore not a data-acquisition project (no new source, no vendor, no scraping) — it is a **plumbing change**: point the P0.1 replay harness at `data/massive_stock_day/` for the 2021+ window instead of at the 15-month `_closes_cache`. Per the census §2 limitation, the production `universe()` reads only ~15 months from the breadth cache; the replay MUST substitute the whole-market store to see the delisted names at all.

- **Cost:** low. One code path in `scripts/replay_standout_pipeline.py` — read Massive parquets by ticker for 2021+ signal dates and horizons. No git-committed data (R9). Massive is Mac-canonical, already present (20,476 tickers on disk, confirmed). The candidate prefilter (P0.1) keeps compute tractable.
- **Bias reduction:** decisive. It is the difference between 92.7% of delisted member-months **invisible** (prod panel) and **0%** invisible (Massive, 100% recall) for 2021+. Without it, 2021+ is CONTEXT-ONLY and the entire Phase-1 study battery has **zero** verdict-grade rows — the program's whole evidence base collapses to context. With it, 2021+ becomes the sole verdict-grade window and every P1 study has a real primary dataset.

**What NOT to do (the rejected menu items):**
- **Do NOT** attempt a pre-2021 delisted backfill to chase a 2012–2020 verdict window. Massive's rolling-5y entitlement does not reach there; pre-2021 delisted history is not available at any audited recall, and `_closes_delisted` (199 names, manual) has no recall guarantee. Buying 2012–2020 verdict grade would require a delisted source that does not exist in this shop. Parked, not pursued.
- **Do NOT** treat the 261 truly-absent tickers (24,019 MM, 13.2% of total, all pre-2021 removals) as a backfill target for Phase 1. They are pre-2021, hence outside the only verdict window; backfilling them buys context richness, not verdict grade. Lower priority than shipping the 2021+ Massive path.

**One-line verdict:** Wire the P0.1 replay to Massive for 2021+ (cheap, decisive); do not chase pre-2021 delisted history (unavailable, and outside the verdict window regardless).

---

## §4 In plain English

Imagine grading a stock-picking rule by replaying history. If your price database quietly dropped every company that got bought out or went bust, your rule would look better than it really is — you'd only be scoring the survivors. That's survivorship bias, and it's the thing this memo polices.

The census checked our databases and found one clean fact: our whole-market "Massive" store has **every** delisted and acquired S&P 500 name from mid-2021 onward, with full prices right up to their last trading day — Silicon Valley Bank, First Republic, Twitter, Activision, all 17 we spot-checked and all 105 removals. But that store only goes back to **July 6, 2021**. Before that date, the failed and acquired names are simply missing, and we have no way to bound how much they'd change the answer.

So the rule for Phase 1 is simple and strict:
- **2021 onward = trustworthy** — but only if the replay actually reads the Massive store (otherwise it's blind to the very names that matter). This is our one and only "verdict-grade" window.
- **2012 to mid-2021 = context only** — we can look at it for a hint of direction, but we may not make claims from it. It gets a big warning stamp.
- **Before 2012 = do not use for claims at all** — coverage is under half and the bias could point either way by an unknown amount.

Every study result must be split: real conclusions come only from the clean 2021+ Massive-sourced data; anything older goes in a clearly-labeled appendix that you're forbidden to draw conclusions from. If the clean window doesn't have enough data to conclude, the honest answer is "not enough data" — never "borrow from the biased years."

And the one action worth doing right now: point the replay at the Massive store for 2021+. It's a cheap plumbing change and it's the difference between having a real evidence base and having none.

---

## §5 Checklist for P1 PREREG conformance (what each study must confirm it does)

- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` by version and date in its preamble.
- [ ] Primary window = **2021-07-06 → last-full-replay-date** (NOT the PREREG-draft placeholder "2015"; §1.2).
- [ ] Verdict-grade statistics computed ONLY on `survivor_bias = false` rows (§2.1).
- [ ] Confirms via replay per-row source stamp that unstamped 2021+ rows were Massive-sourced (§1.1, S2).
- [ ] All 2012–2020 and pre-2012 rows stamped and routed to the labeled context appendix; excluded from BH family, sign-stability, n-floors, and all GO/NO-GO / flip decisions (§2.2, §2.4).
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately from survivor stamps (§1.1(2), S3).
- [ ] Prints the mandated stamp text with the era's census missing-fraction (§2.3).
- [ ] Returns INSUFFICIENT-POWER (honest null) rather than borrowing pre-2021 rows when the unstamped episode-clustered n floor is not met (§2.4.6).

*This memo is LAW for Phase 1 until amended by Fable.*
