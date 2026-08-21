# IMCE-HB-0 — Metric definition crosswalk (denominator crosswalk, not a standardized column)

**Wave:** A3 / IMCE-HB-0. Records-only.
**Authority:** freeze §7.2 conditions (1) and (4); contract §2 Homebuilders (a)–(b) [A17], [A18].
**Governing instruction:** *build a denominator crosswalk, not a false standardized column.* Where two
issuers' same-named metrics are not economically identical, **the distinction is preserved**.

**Evidence — full 12-field tables, ~21 metrics × 6 issuers, preserved verbatim:**
`evidence/L2_defs_DHI_LEN.md` · `evidence/L3_defs_PHM_NVR.md` · `evidence/L4_defs_KBH_TOL.md`
Each carries its own VERIFIED / SOURCE CLAIM / INFERENCE tiering and its own gaps table. **This
document is the adjudication layer; those files are the evidence.** No price, return or outcome data
appears in either layer.

---

## 1. The headline result

**Six issuers. Six different cancellation-rate disclosure regimes. No two alike.**

This is not a nuance discovered in a footnote — it is the central finding of the census, and it
vindicates the "no standardized column" instruction on the single most mechanism-relevant homebuilder
metric.

| Issuer | Where disclosed | Formula stated? | Denominator | Era of the stated formula |
|---|---|---|---|---|
| **DHI** | 10-K **and** press release | **Yes** — "cancelled sales orders divided by gross sales orders" | gross orders in period | current era verified |
| **PHM** | 10-K | **Yes** — "canceled orders for the period divided by gross new orders for the period" | gross orders in period | **FY2016+**; FY2005 gives a bare % with no formula |
| **NVR** | 10-K | **Yes** — "total of all cancellations… as a percentage of gross sales during the period" | gross sales in period **plus a second, opening-backlog measure disclosed alongside** | **FY2016+**; FY2005 gives bare %s |
| **KBH** | 10-K, **footnoted** | **Yes** — "contracts… cancelled during a period divided by the total (gross) orders… generated during the same period" | gross orders in period | **FY2008+**; FY2005–07 give a % with no stated denominator |
| **TOL** | **Press release ONLY — no cancellation rate or formula appears anywhere in the 10-K** | Two rates, side by side | **BOTH** % of beginning-quarter backlog **and** % of signed contracts in quarter (2.8% vs 5.4%, Q1 FY2026) | dual format's first year unverified |
| **LEN** | 10-K MD&A only (bare 14%); **absent from press releases** | **No — none found anywhere** | **UNKNOWN** | n/a |

A column headed "cancellation rate" populated from these six sources would contain a ratio to gross
orders, a ratio to gross sales, a ratio to *opening backlog*, a press-release-only dual measure, and
one number whose denominator nobody has stated. **That column would be a fabrication.**

---

## 2. The freeze's four homebuilder conditions, audited against evidence

### Condition (1) — LEN excluded from cancellation cells

**Confirmed, but the stated reason needs correcting.** Lennar's cancellation rate is absent from its
press releases (verified across three FY2025 EX-99.1 exhibits, zero "cancel" hits) but **is disclosed
in the 10-K MD&A at 14% for FY2025 and FY2024**. It is missing from a *channel*, not from the record.

The robust ground for exclusion is different and stronger: **Lennar states no formula anywhere**, so
under condition (4) there is nothing to freeze without inventing a denominator. Full adjudication and
the proposed amendment: cohort identity census §5.

### Condition (2) — NVR is a mechanism outlier, never pooled

**Confirmed with specifics.** NVR reports **no standing "lots owned" KPI** (the only owned-land figure
found is an incidental ~2,600 lots), **no community-level spec/completed split** (only a combined
dollar bucket), **no cycle time**, and **no starts**. Its land-impairment analogue —
"contract land deposit impairment" — writes down an at-risk *deposit* capped at ~10% of lot price,
**not** an owned real-estate carrying value. Pooling NVR's "controlled lots" with a peer's treats a
≤10%-at-risk contractual right as equivalent to a 100%-at-risk owned asset.

### Condition (3) — calendar-month re-key

**Discharged** in `IMCE_HB0_FISCAL_CALENDAR_MAP.md`, with the misalignment measured at up to a full
three-month quarter under identical fiscal labels.

### Condition (4) — one canonical denominator per issuer + alternate-convention sensitivity

**Partially constructible. This is the condition the census puts at risk — see §4.**

| Issuer | Canonical denominator freezable? | Alternate convention available? |
|---|---|---|
| DHI | Yes — gross orders, stated | Must be **constructed** (backlog-based) from disclosed tables |
| PHM | Yes (FY2016+) — gross new orders | Must be constructed |
| KBH | Yes (FY2008+) — gross orders | Must be constructed |
| **NVR** | Yes — gross sales | **Already disclosed in-source** (opening-backlog measure) |
| **TOL** | Ambiguous — **two** canonical candidates | **Already disclosed in-source** (both denominators printed side by side) |
| **LEN** | **NO — no denominator stated** | n/a |

**A genuinely useful discovery:** NVR and TOL each publish *both* conventions themselves, so the
mandated sensitivity re-run is directly executable for those two rather than requiring a reconstruction.

---

## 3. Named cross-issuer incompatibilities (the crosswalk proper)

Each row is a case where the same metric name denotes economically different things. **None of these
is to be normalized away.**

| # | Metric | The incompatibility |
|---|---|---|
| X1 | **Net orders** | **TOL's "Net Signed Contracts" nets ALL cancellations occurring in the period — including cancellations of contracts signed in PRIOR periods — and credits newly-selected options on old contracts as current-period sales.** Every peer nets only current-period cancellations against current-period gross. TOL's figure can be driven down by a cancellation of a contract signed many quarters earlier. **This is a different formula, not a different level.** |
| X2 | **Cancellation rate** | Six regimes, §1. Denominators span gross orders, gross sales, opening backlog, and unknown. |
| X3 | **Lots controlled** | DHI's bucket is partly populated by lots owned by **Forestar, its own consolidated subsidiary**, under intercompany contract/ROFO. LEN's is populated by third-party options and — post Feb 2025 — options back from a **former subsidiary** (Millrose). NVR's is ~100% third-party option rights with loss capped at a ≤10% deposit. Three different economic relationships under one column name. |
| X4 | **Lots owned** | **NVR has no standing lots-owned metric at all** (`not_applicable`). LEN's fell **85,428 → 9,525 (−89%)** in one quarter on the Millrose spin-off with no change in land access. |
| X5 | **Land impairment** | Peers write down owned community inventory to fair value under an ASC 360 undiscounted-cash-flow test — a real-asset markdown at full carrying value. **NVR writes down a deposit asset, capped at ~10% of lot price.** Different asset, different maximum loss. |
| X6 | **Homes in inventory** | DHI reports one nested all-stage figure (29,600 at FYE25) containing unsold/completed-unsold sub-counts. **LEN has no equivalent combined figure.** PHM reports a unit-level "Homes in production" table (Sold / Unsold split into Under construction + Completed / Models). **NVR reports only combined dollar buckets, not unit counts.** TOL reports a composite home-sites figure. |
| X7 | **Completed unsold inventory** | PHM splits it out as a unit line. **NVR does not separate it** from under-construction-unsold. **TOL: `missing`.** Not reconstructable across the cohort. |
| X8 | **Community count** | **LEN** publishes a formally defined, footnoted point-in-time "Active Communities" count with the JV-built subset quantified. **DHI publishes no equivalent numeric count at all.** PHM and NVR publish period **averages**; KBH publishes **both** average and ending; TOL (in exhibits reviewed) only period-end. An average and a period-end are different estimators of a moving quantity. |
| X9 | **Cycle / build time** | **KBH quantifies it** — "average build time of four to five months from construction start to home completion", plus a six-to-seven-month sale-to-delivery window. **PHM discusses it only qualitatively. NVR and TOL disclose no numeric figure at all** (both verified by full-text search, not assumed). A cohort cycle-time series does not exist. |
| X10 | **JV inclusion** | **TOL excludes unconsolidated JV activity from every headline metric** under a "Total Consolidated" framing, while carrying $956.5M of JV investments — so its headline metrics understate its total controlled footprint. **LEN quantifies its JV backlog share in a footnote every period** (79 homes / $86.0M at FYE25). **TOL publishes no equivalent JV unit count** (verified absence). **DHI's backlog carries no JV carve-out found.** |
| X11 | **Incentives** | **LEN tabulates a discrete "Average Sales Incentives Per home"**, explicitly excluding unconsolidated-entity deliveries from its denominator. **DHI discloses incentives narratively only** — no isolated figure. **NVR uses "closing cost assistance"** with no defining policy paragraph. PHM has an explicit Note-1 sales-incentives policy but no isolated figure. |
| X12 | **Spec inventory (conceptual)** | **KBH frames non-BTO homes as a residual** — "homes started without a corresponding buyer and partially constructed homes where the initial buyer cancelled" — i.e. overflow, not strategy. For a volume builder, spec is a deliberate speed-to-close position. A rising KBH spec share signals something different from a rising DHI spec share. |
| X13 | **Closings terminology** | NVR says "settlements" exclusively and always. PHM **drifted** from "settlements" (FY2005–10) to "closings" (FY2016+) with no formal redefinition and no stated effective date. Same event; the label moved. |
| X14 | **SG&A denominator — a CONVERGENCE, recorded so it is not mistaken for a divergence** | DHI, LEN and PHM all use **home-sales revenue**. **NVR uses total revenue.** Five of six converge; NVR does not. Recorded explicitly so a later wave neither over-corrects nor misses the one real difference. |

---

## 4. The era finding that constrains the cell budget

**Stated denominators are a LATE-ERA artifact. The GFC-era blocks have none.**

| Issuer | Cancellation formula first confirmed | FY2005-era disclosure |
|---|---|---|
| PHM | **FY2016** | bare % narrative, no formula |
| NVR | **FY2016** | bare %s — and **two different ones** in FY2005 (12% in a backlog context, 25% in a mortgage-pipeline context) with neither denominator stated |
| KBH | **FY2008** | % with no stated denominator (FY2005–07) |
| TOL | dual format's first year unverified | unverified |
| LEN | never | never |

**Consequence.** Blocks 1 (`hb_gfc_bust`, 2006–2009) and 2 (`hb_gfc_recovery`, 2010–2013) largely
**predate the stated-denominator era**. A cancellation-rate cell cannot be frozen on a verified
denominator for those blocks — only on an assumption that the unstated early convention matched the
later stated one. **That assumption is exactly the flattening this census exists to prevent, and it is
unverified.**

So for the cancellation-rate cell specifically:
- Denominator-verifiable blocks: **3** (`hb_grind` from FY2016, `hb_pandemic_boom`, `hb_rate_shock`)
- Not: blocks 1 and 2
- Poolable issuers: **m = 4** (LEN excluded, NVR separate stratum)

**The cancellation cell's honest historical block count is ~3, not 5.** Carried into the A4 cell budget.

**KBH carries an additional, sharper problem.** Its FY2008 10-K uses "cancellation rate based on **net**
orders" in one place and "based on **gross** orders" in a segment-table caption — **both verified from
the same filing**. KBH's early-era denominator is not merely unstated; it is internally contradicted in
the one filing that states it. Blocks 1–2 for KBH are `not_reconstructable` on this metric.

---

## 5. Era-correlated disclosure appearance — a cohort-wide hazard

The concern the freeze raised for LEN's cancellation rate — *missingness correlated with era, so a
missing-indicator becomes an era proxy* [A18] — is **not unique to LEN**. The census found the same
structure on several metrics:

| Metric | Disclosure appears | Effect |
|---|---|---|
| **TOL "spec homes" / "quick move-in"** | **FY2023 10-K onward; ZERO hits in TOL 10-Ks 2001–2020** (verified via full-text search) | A spec-inventory series for TOL exists only for the last three years. |
| TOL "build-to-order" as a label | FY2024 10-K onward | Same. |
| PHM "Unsold: Under construction / Completed" split | confirmed FY2024; earlier unconfirmed | Completed-unsold may not exist for early blocks. |
| Cancellation formulas | §4 | GFC-era blocks lack denominators. |

**Important nuance, and the census is careful not to overstate it.** TOL's *unhyphenated* "speculative
homes" appears as early as the FY2006 10-K. So TOL always built some spec homes — what changed in
FY2023 is the **labelled terminology and disclosure emphasis**, not necessarily the practice. TOL's
own framing ("over the past three years, we have increased the number of spec homes") points to
roughly FY2022–23 as the *operational* inflection, one to two years before the *terminology*
inflection. **Disclosure onset and business-behaviour onset are different dates and must not be
conflated** — reading the FY2023 terminology change as a FY2023 strategy change would be an artifact.

**Binding rule:** the [A18] missing-indicator ban applies to **every** metric in the table above, not
only to LEN's cancellation rate. A missing-indicator on any of them is an era proxy.

---

## 6. What the census could NOT establish

Stated plainly so no later reader over-reads the crosswalk.

1. **Earliest-coverage archaeology is incomplete.** The lanes opened a representative spine of filings
   (FY2005, FY2009/10, FY2016, FY2024/25 plus press releases), not all 22 years × 6 issuers. Field 12
   ("earliest lawful historical coverage") is verified where stated and typed `missing` /
   `not_reconstructable` elsewhere — **never interpolated**. The DHI/LEN lane returned **PARTIAL** for
   exactly this reason and said so.
2. **Whether early-era denominators differed, or only the prose describing them, is unresolved.** Both
   PHM and NVR may always have computed a gross-orders ratio and merely added the sentence later. The
   census cannot distinguish "methodology changed" from "disclosure improved", and this matters for
   §4's conclusion.
3. **Restatement treatment for CalAtlantic** into LEN's orders/backlog/community count is unverified
   (the general acquisition-method rule implies no restatement — break ledger §1 — but the specific
   filing language was not opened).
4. **TOL's JV-exclusion consistency across the full window** is verified for two periods only.
5. **TOL's City Living consolidation treatment** is community-by-community and ownership-dependent — genuinely unresolved.

---

## 7. Frozen by this wave (pre-outcome)

1. The six cancellation-rate regimes as documented in §1 — **no single canonical cross-issuer
   cancellation rate exists or will be constructed.**
2. Per-issuer canonical denominators where stated (DHI, PHM FY2016+, NVR, KBH FY2008+); **LEN: none
   freezable**; **TOL: two candidates, requiring an A4 election between them with both printed.**
3. The X1–X14 incompatibilities as preserved distinctions, never normalized.
4. The [A18] missing-indicator ban extended to every era-correlated metric in §5.
5. Denominator-verifiable blocks for the cancellation cell: **blocks 3, 4, 5 only**.

**Every one of these requires an amendment-log entry to change.**

---

## 8. Falsifiers

| # | Falsifier | Effect |
|---|---|---|
| F-1 | A LEN filing stating a cancellation-rate formula is found. | Condition (1)'s exclusion may narrow; a canonical LEN denominator becomes freezable. |
| F-2 | Pre-2016 PHM/NVR filings are found stating the formula. | §4's era finding weakens; blocks 1–2 may regain a verified denominator. |
| F-3 | KBH's FY2008 net-vs-gross contradiction is resolved by a later clarifying filing. | KBH's early-era cancellation series becomes usable. |
| F-4 | TOL is found to disclose a numeric cycle time somewhere. | X9's absence narrows. |
| F-5 | An issuer is found to have restated operating metrics across an acquisition. | Break ledger §1's universal rule breaks; X-row comparability changes. |
