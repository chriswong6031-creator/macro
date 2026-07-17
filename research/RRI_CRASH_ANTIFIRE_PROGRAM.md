# RRI — Intl Risk-Radar Crash-Anti-Fire Study Family (W0 cover + family registry)

**Status: DRAFT — awaiting operator ratification. Nothing here is buildable until ratified.**
**Freeze semantics: the gates in the four preregs below freeze on merge of this PR, BEFORE any
construction↔outcome relationship is computed. Only an outcome-blind trigger census was run
pre-freeze (disclosed in §5).**

Drafted 2026-07-17 (session forensics of the 2026-07-17 Asia crash). Program prefix: **RRI**
(risk_radar_intl). Deliverable of this wave: pre-registration documents only — **zero code
changes to the live radar**, per IRD-R1 (scope fence: promotion only through pre-registered
claims), ITR-R1 (no change to `risk_radar_intl` profiles from the display program), and the
RRX-R7 grammar (nothing enters a radar's calibration or moves state without a ruler + a fresh
operator-ratified ruling).

## §1 — The motivating failure (2026-07-17 Asia crash)

KOSPI fell ~6% intraday and Nikkei ~2.8% on 2026-07-17 (Asia session). The intl radars read,
at the 2026-07-16 close:

- **KR: watch, composite 58.9** — while its extension leg *alone* printed **90.3** (inside the
  published leg risk-off band, ≥88) and had been ≥90 for four straight sessions. The composite
  could not reach the 91 alert band because `krw_depreciation` sat at the **17th percentile**
  (KRW had been *strengthening* −3.47%/21d) and rateshock had eased to 65.
- **JP: caution 75.8** — and the sharper fact: JP had printed **risk-off 91.7 / 93.7 / 94.0 on
  07-13/14/15 and de-escalated to caution 75.8 on 07-16, INTO the crash** (yield rally cooled
  the rateshock leg 82→65; the composite percentile fell with it).

Forensic simulation (2026-07-17 session): appending the full crash to the stores moves the KR
composite **58.9→56.9** and JP **75.8→77.6** — the crash *itself* suppresses the radar. Three
self-defeat channels, all structural to the current construction:

1. falling prices reduce the extension percentile (the melt-up leg unwinds as the melt-down begins);
2. safe-haven flows *strengthen* KRW/JPY, so the one-sided depreciation percentile collapses;
3. the flight-to-quality yield rally reduces the rateshock leg.

All three legs must be simultaneously elevated to clear the 91 band (weights rateshock 1.0 /
fx 0.6 / extension 1.0, blended then trailing-percentiled). A crash de-elevates two of them on
day one. Separately (Gap 2): the US radar's `global_breadth` Tier-B leg (C3, US-listed country
ETFs %>200dma) read **87% above 200dma = calm** on 07-16 — EWY +30% and EWT +34% above their
200dma — while our own cn/hk/tw radars stood at 98/91/98. Country ETFs price at the US close:
the US book's global read is structurally a session behind Asia cash and, at a parabolic top,
%>200dma is the wrong lens anyway (extension ≠ breadth breakdown).

Display-tier mitigations shipped separately (2026-07-17 session). **This family is the
scoring-tier study track.**

## §2 — Scope + governance (binding on all four preregs)

- **Scope: the 7 new-market profiles only** (kr/jp/tw/in/au/gb/ez). The cn/hk/ca constructions
  are byte-frozen legacy (`test_legacy_profiles_frozen`) with their own validation lineage and
  accruing logs; extending any RRI winner to them is a separate operator ruling.
- **Shadow-variant law.** No candidate may mutate the live construction. If a prereg's replay
  gauntlet passes, the candidate runs as a SHADOW variant on the nightly: computed beside the
  incumbent from the same `composite_series` substrate, logged to
  `data/risk_radar_intl/<mkt>_forward_log_<variant>.jsonl`. Shadow appends obey the same
  `ledger_lane_armed()` gate as the live log (LETHAL trap: asia-close sets NO COLLECT_LANE —
  arm inline per-invocation or the shadow log silently freezes, the #2688/#2693 class).
- **Two-stage promotion.** Stage A = frozen replay gauntlet (per-prereg gates). Stage B =
  shadow forward confirmation: ≥25 graded shadow rows AND shadow do-no-harm vs incumbent on the
  same dates, then an explicit operator ruling swaps the construction. On swap, forward-log rows
  carry a `construction` version field; existing graded rows are keep-first-permanent and
  describe v1; `can_force` counters (MIN_GRADED_FORCE=30 / MIN_ALERTS_FORCE=8 / Wilson Article-3)
  restart per construction version.
- **prob_cal stays FLAT AT BASE** (2026-07-16 ruling) regardless of any RRI verdict: no
  in-sample per-state probability re-bake; the live forward log + bounded tuner own the surface.
- **Word law:** no RRI construction is called "validated" anywhere; nulls are printed, not
  hidden; a KILL appends a construction-specific row to `research/DO_NOT_REBUILD.md` §2 (with
  compiled blocklists regenerated in the same PR).
- **LLM non-origination:** every trigger/leg here is a deterministic transform of committed
  store data.
- A NULL on any candidate closes that *construction*, not the search space (house law): the
  candidate is retained as a confluence/display input where its prereg says so.

## §3 — Shared rulers (frozen)

**R-A · Day-level forward ruler** (identical to the live audit,
`engine/risk_radar_intl_audit.py`): outcome = ≥5% index drawdown from the as-of close within
h5/h10/h21 business days; primary horizon h21; alert = gated state ∈ {elevated, risk-off}.
Statistics on replay are **cluster-honest** (the #2369 precedent): trigger/alert days are
clustered with a 21-session gap rule; a cluster HITS if any constituent day hits; the Wilson
lower bound (z=1.645, one-sided 90%) is computed on cluster hit rates, never on overlapping
day counts.

**R-B · Episode ruler.** A drawdown episode: onset day t = first day with
close(t) ≤ 0.98 × max(close[t−63 … t−1]) whose forward path reaches
min(close[t … t+21]) ≤ 0.92 × that same reference high; subsequent onsets are suppressed until
either 21 sessions pass or a new 63-session high prints. (−2% entry / −8% confirmation, the US
radar's drawdown-onset grammar.) **Latency** = sessions from onset to the first loud-tier day
within [onset−10, onset+15]; never-loud is censored at +15 and counted as 15.

**R-C · Null machinery (the ONLY comparison base).** Per market: take the FINAL trigger
boolean mask (gate- and state-conditioning already baked in), hold the outcome series fixed,
and circularly shift the mask by a random offset drawn independently per market and per
permutation (uniform over the window; this preserves the mask's day count and its run/cluster
structure). 2,000 permutations. Each permutation re-applies the identical 21-session-gap
clustering (R-A) to the shifted mask and computes the cluster hit rate with the same estimator
as the observed side; the pooled null statistic is the cluster-count-weighted pooled
cluster-hit rate across the 7 markets. One-sided p = fraction of permutations with pooled
cluster-hit rate ≥ observed. **"Base"/"chance" in every H1 means exactly this permutation-null
mean pooled cluster-hit rate — no other denominator exists in any gate.** The lift gate is
observed cluster-Wilson-LB ≥ **1.25 × the null mean** (Article-3 grammar with the null mean as
the honest overlapping-window base). Known limitation, accepted: a location-shift null breaks
the trigger↔regime coupling by design (it asks "same trigger structure, random location");
regime robustness is carried by the era/split-half gates, not by the permutation.

**R-D · Replay window.** Full committed store history per market (the same windows the
2026-07-16 calibration harness printed, e.g. KR 1998-02→, JP 1997-07→, IN 2008-10→); era split
at 2016-01-01; split-half = first/second half of each market's window. All replays run through
`engine.risk_radar_intl.composite_series` — no parallel reimplementation of the substrate.

**N floors:** a primary cell needs ≥8 non-overlapping trigger clusters pooled across the 7
markets; below floor the cell prints **ERA-SPARSE → ACCRUE** (registered, unfilled; not a pass,
not a kill). Per-market secondaries need ≥3 clusters each.

## §4 — Family accounting (frozen)

New declared family **`rri_2026h2`** — 8 cells, BH-FDR at α = 0.10 within the family. Ranked
ascending, cell k must clear p_k ≤ (k/8) × 0.10; the single most-significant cell therefore
needs p ≤ 0.0125. **Cell p-gates are conjunctive:** a cell must clear BOTH the p < 0.05 hard
floor stated in its prereg AND its BH rank threshold — whichever is stricter binds.

| # | Study | Cell | Role |
|---|-------|------|------|
| 1 | S1 | any-leg ≥0.88 floor-to-elevated (pooled 7) | **primary** |
| 2 | S1 | ext+fx legs only ≥0.88 | secondary |
| 3 | S1 | any-leg ≥0.95 | secondary |
| 4 | S1 | ext+fx legs only ≥0.95 | secondary |
| 5 | S2 | gate-conditional two-sided FX max-blend (pooled 7) | **primary** |
| 6 | S2 | two-sided FX always | secondary |
| 7 | S3 | dd-velocity leg, −ret10 percentile, weight 0.6 (pooled 7) | **primary** |
| 8 | S3 | dd-velocity on −ret21 | secondary |

Per-market breakdowns inside any cell are **exploratory receipts** (printed, never gated,
never counted). Amend-on-add: any later cell re-states the family total and re-ranks every
posted p-value at the tighter threshold. **S4 is NOT in this family**: it is two new claims
declared into the existing `intl_bridge` trial-ledger family (`engine/intl_claims.FAMILY`),
whose Deflated-Sharpe declared-N discipline absorbs them (see RRI-S4 doc). The two families
are budgeted separately by construction — BH-FDR for the radar cells, DSR declared-N for the
US claims; no cell or claim is double-counted, and both corrections are stated here so the
whole 2026h2 wave's multiple-testing picture is in one place.

## §5 — Pre-freeze census disclosure (outcome-blind)

Computed 2026-07-17 before freeze, from `composite_series` over the committed stores: trigger
and state **frequencies only — no forward returns were joined; no candidate↔outcome
relationship has been computed as of this freeze.** Method: gated-state replay identical to
`compute()` (band + gate cap), leg score = mean of sub-leg percentiles ×100, last-10-year
shares unless noted. Numbers the FP budgets in the preregs are sized against:

- Incumbent loud-tier (elevated+) day share, last 10y: kr 13.3% · jp 6.0% · tw 10.0% ·
  in 5.2% · au 4.8% · gb 7.8% · ez 4.5%.
- S1 trigger (any leg ≥88, gate open, composite below elevated): mean 10.1% of days across the
  7 (kr 15.4% … au 6.8%); at ≥95 mean 6.0%; ext+fx-only at ≥88 mean 8.0%.
- S2 anti-fire days (gate open, fx leg ≤25th pctile): 5.4–12.0%; two-sided-flip days (two-sided
  ≥85 while one-sided ≤50, gate open): 1.6–3.6%.
- S3 velocity ≥95th pctile days: 4.8–6.4% full-history; of those, below-alert share 4.7–6.1%.
- S4 cross-market gated alert count (≥8 of 10 markets reporting): ≥3 alerts on 9.0% of
  last-10y days, 32 non-overlapping episodes full-history; local-bench %>200dma ≤40% on 28.2%
  of days (too loose alone — level+slope construction declared in the S4 claims).
- 21-session-gap trigger clusters (the N-floor unit), pooled across the 7,
  full-history / last-10y: S1@0.88 **355 / 111** · S2 two-sided-flip **156 / 62** ·
  S3 velocity **374 / 108** — every primary cell sits far above the ≥8 pooled floor.
- Forensic anchor (live store tail, 07-13→07-16): KR composite 73.0/72.8/71.3/58.9 with
  extension 90.2/91.4/92.1/90.3 and fx 23.2/28.4/17.1/16.9; JP composite 91.7/93.7/94.0/75.8
  (risk-off → caution into the crash); KR −ret10 velocity percentile 100/100/98.6/97.0.

## §6 — Shared verdict grammar

- **GO** — all of the cell's frozen gates pass → candidate advances to Stage-B shadow accrual.
- **ACCRUE** — right sign but under-powered (N floor, or LB in [1.0×, 1.25×) null mean) →
  shadow accrual WITHOUT any promotion clock; re-graded when the forward log matures.
- **NO-GO** — lift gate fails or FP budget blown → candidate parks as display/confluence
  input only (where its prereg says so); printed.
- **KILL** — escalated/added days' cluster hit rate significantly BELOW the null mean
  (Wilson UPPER bound < null mean) or a do-no-harm gate fails → construction-specific
  DO_NOT_REBUILD row appended.

Verdicts, whatever they are, are printed to `data/risk_radar_intl/rri_study_results.json` +
a RESULTS doc that reports against this family without rewriting it (dated-append idiom).

## §7 — Clocks

- **Ratification gate:** no study code runs until the operator ratifies the four preregs.
- **+2 weeks after ratification** — Stage-A replay results due (all 8 cells; one PR).
- **Stage-B**: ≥25 graded shadow rows per promoted candidate — earliest ≈ 5 weeks of nightlies
  after shadow wiring (grading lags h21).
- **2026-10-15** — family come-back review rides the existing RRX/IRD clock; ungraded cells
  print ERA-SPARSE, not silence.

## Ratification

- Drafted: Fable (main loop), 2026-07-17, from the 2026-07-17 crash forensics session.
- Pre-freeze compute: outcome-blind census only (§5).
- **What ratifying costs:** nothing live — it authorizes replay compute + shadow logs only;
  zero alert-day change until a later per-candidate swap ruling. If everything eventually GOes
  and wires, S1 dominates the potential steady-state cost (~+10pp loud-day share, census-priced);
  S2/S3 add roughly +2–8pp each; S4 touches only the US book's Tier-B escalator.
- Operator ruling: ☐ ratify all four · ☐ ratify subset · ☐ decline (docs stand as record).
