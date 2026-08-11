# W2 — Exposure-decomposition probe (R1): preregistration

Committed BEFORE any probe computation (the results commit must postdate this file).
Program: GMI Theme Graph (`research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §6 R1, §7 W2).
Binding gates: §0 all; specifically G0.2 (era honesty), G0.3 (no parallel organs — assemble from
owner planes), G0.4 (CN planes), G0.6 (no LLM numbers), G0.7 (off render path), G0.11 (no
user-exposed magnitude ordering; research-internal analysis tables exempt, no surface ships from W2).

## 0. Question under test (R1, verbatim scope)

Do the three exposure axes' **continuous quantities** (`economic_share`, `trading_beta`,
`attention_share`) disagree **measurably & stably** on our data? The probe runs on
independently-computed quantities, never curated enums. §319's disagreement-alpha framing stays
PARKED — this probe establishes (or refuses) the axes as stable measurements; it makes no return
claims and no directional claims (that is R5, blocked on this).

A null here closes the specific construction tested, narrows W4's edge-annotation charter, and
never kills the rail (ore law).

## 1. Pilot slots (fixed for program year 1 — named per §6 pilot rule)

Membership source: `data/theme_graph/edges.parquet` at the branch-base main commit, latest-belief
view (max `belief_time` per `edge_id`); live = `valid_to` null; closed members INCLUDED in any
period their `[valid_from, valid_to)` covers. Counts are live members at prereg time.

| Slot | Theme | Basket node(s) | N live | closed |
|---|---|---|---|---|
| US-mature-broad | fintech_payments | `basket:baskets:payments_fintech` | 21 | 1 |
| US-young-narrow | nuclear_power | `basket:baskets:nuclear_power` | 9 | 0 |
| US-institutional (GovRev-adjacent) | defense_aerospace | `basket:baskets:defense` | 21 | 1 |
| CN-mature | solar | `basket:baskets_china:cn_solar` | 15 | 0 |
| CN-young-speculative | robotics_automation | `basket:baskets_china:cn_robotics` | 11 | 0 |
| Cross-market pair | ai_semiconductors | US `basket:baskets:ai_semiconductors` (12) + `basket:baskets:ai_infra` (24); CN `basket:baskets_china:cn_semis` (22) + `basket:baskets_china:cn_ai_compute` (17) | ~65 net of overlap | 0 |

Six DISTINCT themes spanning maturity × breadth × market; two slots carry closed edges so
survivorship handling is non-vacuous in-slate. Maturity/phase context grounded in the live TIL
phase tape (`data/neuralweb/theme_phase_history.jsonl`), not curator priors. Slots were picked by
slot DEFINITION; a slot×axis cell failing its coverage floor prints ABSTAIN — it does not re-pick
the slot. Cross-market pair: each side's members are measured against their OWN side's basket
(cross-market lead-lag is R7, not W2).

## 2. Axis constructions (formula ids minted here; census receipts in §11-linked reports)

**economic_share — HONEST NULL, no formula minted.** Census (2026-08-11, three-lane sweep)
found no per-company theme/segment revenue source on either market: US has geography-only
dimensional parsing (`collectors/edgar_geo_revenue.py`, 637/1,549 tickers — geography ≠ theme);
no `StatementBusinessSegmentsAxis`/`ProductOrServiceAxis` production parser exists
(`engine/fundamental_forensics/` has the kernel but is forensics-purposed, 32-ticker-bounded);
CN fundamentals are company-aggregate only (`data/china_fundamentals/`, 1,039 tickers, no
segments). `engine/company_theme_exposure/` is by its own contract a membership projection, not
a score; `engine/theme_fingerprint.py` is theme-grain physical tightness, wrong grain.
`DNR:HOLD-TICKER-EXPOSURE-TAGS` stands adjacent to any revival. H1-economic therefore ABSTAINS
by construction; H2/H3 pairs involving economic are vacuous. Ore ledger (constructions mapped,
none tested): segment-axis XBRL ingestion atop the forensics kernel; receipted exact-substring
extraction from filing text (R-TIL-5 form); CN annual-report segment tables. W4 must not charter
economic_share annotations until one of these is built and separately adjudicated.

**trading_beta.v0** — per member `i` in slot basket `B`, month-end stamped:
raw OLS beta of daily log returns of `i` vs the EX-SELF equal-weight basket return
`r_B∖i = mean(r_j, j ∈ B_t, j ≠ i)` over a rolling 63-session window, minimum 40 overlapping
sessions, estimate at month `m` uses sessions through the last session of `m` shifted one day
(the house causal-shift idiom — mirror `engine/cn_global_beta.py:_causal_beta`'s cov/var
construction EXACTLY; that module is the incumbent plane for CN betas and its input store choice
is followed, not re-decided). RAW beta is the probe quantity (Vasicek-shrunk companion reported
display-only — shrinkage compresses dispersion and would overstate H3 stability by construction).
`B_t` = PIT membership at month `m` where the graph knows it; the backcast uses current live +
closed-window members and is era=reconstruction throughout (see §4). US member prices:
`data/baskets/ohlcv/` (fallback `data/stocks/`); CN: the same store `engine/cn_global_beta.py`
reads (builder verifies and records it; adjusted series are correct for return co-movement —
the unadjusted-plane law G0.4 governs LIMIT truth, and no limit computation occurs here).
History: US from 2023-06 (membership seed era), CN from 2024-01; earlier basket compositions are
unknowable and not backcast further.

**attention_share.cn.comment.v0** — member share of slot attention from the 千股千评 关注指数
(`data/china_comment/attention_hist.parquet`, append-only PIT, ~full A-share universe):
`a_i,m = mean_days(关注指数_i,d) / Σ_{j∈B} mean_days(关注指数_j,d)` per month `m`. Dense but
shallow (34 daily stamps from 2026-06-18): 1–2 monthly periods → H3 on this construction is
UNDERPOWERED-BY-DEPTH today and says so; the accrual re-probe (§6) answers it.

**attention_share.cn.lhb.v0** — member share of slot dragon-tiger presence
(`data/china_lhb/events.parquet`, 2024-07→present, 436 dates): `a_i,m` = member's LHB appearance
count in month `m` / basket total appearances. Sparse tail-event attention (most members zero in
most months — % nonzero printed per cell); deep enough for a real H3 answer (24 monthly periods).

**attention_share.us.wsb.v0** — member share of WSB mentions
(`data/quiver/wallstreetbets.parquet`, 307 tickers, 44 collection days): monthly mention-count
share. **attention_share.us.flare.v0** — member share of news counts from
`data/narrative_flare/witness_hist.parquet` (448 tickers, 25 days; gitignored-local store —
receipts record row counts + date range for reproducibility). Both shallow (1–2 periods) and
coverage-risky outside meme/tech names — expected ABSTAIN cells in defense/nuclear/fintech are
the probe working, not failing.

**Refused substitutions (binding):** `china_narrative_radar`/`narrative_rotation` outputs are
price-momentum wearing a narrative label — they are NOT attention and must not enter any
attention construction. `contagion_key` is country-grain financial-stress spillover — not
attention (masterplan A3 erratum recorded in §11 at verdict time). Membership
`mapping_qualifier` enums never enter any axis (R1's own text).

## 3. Hypotheses and frozen thresholds

- **H1 (computability):** per (slot × axis-construction) cell, coverage = fraction of the
  period's members with a computed value. Floor **0.70**: below it the cell prints ABSTAIN
  (coverage-floor law; no imputation anywhere). LHB zeros are values (0 share), not missing;
  missing = ticker absent from the source universe.
- **H2 (distinctness):** within-slot Spearman ρ between `trading_beta` and each computable
  `attention_share` construction, on the latest common month. "Measurably disagree" =
  median |ρ| across computable slots **≤ 0.70** AND ≥1 slot with |ρ| **≤ 0.50**. If median
  |ρ| **> 0.90** → the pair is redundant on our data (null → W4 keeps one annotation, not both).
  Between: "partially distinct," reported without a promotion claim. Economic pairs: vacuous.
- **H3 (stability):** same-construction adjacent-month rank autocorrelation (Spearman) within
  slot. "Stable measurement" = median across adjacent pairs **≥ 0.60**; below **0.30** = noise
  (null for that construction as a measurement); between = "weakly stable," accrual re-probe
  decides. Constructions with < 3 adjacent pairs print UNDERPOWERED-BY-DEPTH (expected: both
  dense attention constructions; the LHB and beta constructions have real answers).
- **Inference honesty:** N per cross-section is 9–24 — exact small-sample Spearman p-values
  reported per slot, but the VERDICT keys on effect sizes + cross-slot consistency, never on a
  single significance star. Time dependence: H3 medians get a moving-block bootstrap over months
  (block 3) for an 80% CI; repeated cross-sections are never pooled as independent.
- **Honest-N:** distinct companies per slot, distinct months per construction, % nonzero for
  sparse constructions — all printed per cell. Episode = one (slot, month) cross-section.

## 4. Era and survivorship statement

All membership-dependent history before 2026-08-11 rides era=reconstruction membership
(`date_provenance` predominantly `seed_constant` — the graph does NOT know 2024's true basket
composition; W1b §11). Every backcast statistic carries `era=reconstruction`; the observed era
is ~0 months deep at probe time and accrues nightly from here. The verdict's stability sentences
name the era explicitly ("stable on reconstruction-era membership"). Survivorship: closed-edge
members enter every period their validity window covers (defense 1, payments_fintech 1); the
report prints per-slot dead-member counts and names. The attention/price tapes themselves are
authentic PIT data (their own dates are real); reconstruction applies to MEMBERSHIP, and the
report never conflates the two.

## 5. Exemplar gate (adjudication coverage — answered BEFORE the verdict is written)

Directional expectations named now; computed values that invert obvious reality indicate a
measurement defect, not a discovery:
1. Cross-market pair, US side: NVDA must not rank bottom-quartile on attention share within its
   baskets (it is the most-discussed name in the complex); its beta should be near or above 1.
2. CN robotics: the 涨停-prone small caps should carry attention shares well above the index-heavy
   members relative to their beta ranks — if attention and beta ranks are IDENTICAL here, suspect
   the attention source is price-derived contamination.
3. Defense: at least one prime (LMT/NOC/GD class) should show high beta-to-basket but modest
   WSB attention share vs any retail-favored name in the slot — the axes' whole point.
The verdict LEADS with these three answers against the current regime (TIL phase tape at probe
date) before any aggregate statistic.

## 6. Outputs, verdict form, and what W2 does NOT do

- Probe script `scripts/probe_theme_exposure_axes.py` (one-shot, argparse, NOT wired into any
  workflow; reads owner stores read-only) + `tests/test_theme_exposure_probe.py` (pure-math
  unit tests, registered in legacy-jobs) + receipts under `research/theme_graph/w2_probe/`
  (per-cell CSV/JSON + a written report). Store SHAs + row counts + date ranges recorded.
- **No store mutation:** `edges.parquet`'s axis columns STAY reserved-null; population is a
  later wave gated on this verdict. No synapse edits (no conscious-census tolls). No user
  surface. Unregistered attention primitives (`china_comment`, `china_lhb`, `china_zt_pool`)
  and the local-only `narrative_flare` history are FILED to their owners, not fixed here.
- **Verdict form:** per (axis-construction × market) cell — MEASURABLE-NOW / UNDERPOWERED-BY-DEPTH
  (with the accrual date that unlocks it) / BLOCKED-ON-INGESTION (with the named ingestion).
  W4 may charter edge annotations only from MEASURABLE-NOW cells. Accrual re-probe checkpoints:
  +3 months (2026-11) for dense attention H3, +6 months (2027-02) for observed-era beta H3.
- The word "validated" appears nowhere in W2 outputs.
