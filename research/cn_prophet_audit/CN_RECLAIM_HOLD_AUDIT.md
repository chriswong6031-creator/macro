# CN reclaim-and-hold audit — the board's PRIMARY buy blocker, measured (2026-08-05)

## DECISION-RELEVANT SUMMARY

1. **The family is confirmed as CN's primary blocker: 2,684 of 5,157 fires — 52.1%**, against the
   bearish-divergence veto's 743 (14.4%). Deleting it outright would be **+155% takes**.
2. **Overall: the family FAILS its keep at BOTH horizons, and the failure is strong.** Fires it
   blocks that every other leg admits (n=2,436/2,163) beat today's takes (n=1,681/1,633) at H=10
   (49.9% vs 47.4%) and match them at H=21 (43.0% vs 43.9%, inside the 3pp bar); catastrophic and
   MAE-p10 both favour the *blocked* side (−1.6pp/−2.3pp; +1.8pp/+2.2pp). At both horizons the
   blocked cell's Wilson CI **excludes** the keep bar — protection is ruled out at 95%, though at
   H=21 by only 0.07pp.
3. **Unlike the divergence audit, this verdict survives the half-split.** FAILS in H1 and H2, at
   both horizons. That is the one robustness leg the divergence study could not clear.
4. **But "fails to protect" is not "is blocking winners".** MFE-p90 — carried because the HK
   postmortem records a retraction for reading a bounce on endpoint alone — is **lower in the
   blocked cell in 83 of 84 stratum cells** (family −8.9pp/−13.0pp; range −33.5pp to +1.9pp, the
   lone positive being HOLD/deepest-tercile/H=21). The family selects a *lower-amplitude*
   population, thinner on both tails. HK's product case for removal was peak-after-entry; on CN
   that argument runs the other way.
5. **The two sub-legs split, and it is the RECLAIM leg that keeps anything.** RECLAIM: FAILS at
   H=10 (+3.8pp, CI excludes), **EARNS at H=21** (−3.80pp, just past the −3pp bar). HOLD: FAILS at
   both (−1.2pp / +1.4pp). BLOCKED_BY_BOTH: FAILS at both.
6. **Read that EARNS narrowly.** It is a return-leg-only pass whose two risk legs point the *other*
   way past the same margin (catastrophic −3.7pp, MAE-p10 +3.9pp — the blocked cell is safer), its
   CI does **not** exclude the bar, and it is carried entirely by H2 (H1 +2.4pp FAILS, H2 −5.0pp).
   Same regime-oscillation the divergence audit found; treat it as a hypothesis, not a finding.
7. **CONTINUATION cell (trail_63 > 0) — the family EARNS at H=10 and FAILS at H=21.** n=637/613;
   Δwin −3.10pp then +1.29pp. A horizon-split, not a keep.
8. **And the leg doing that work is the HOLD leg, not the 200-reclaim leg.** In the continuation
   cell HOLD is n=581 (EARNS H=10 / FAILS H=21) while RECLAIM is **n=29** — 4.5% of its decision
   set. The reclaim rule structurally almost never fires on an uptrending name.
9. **§2.7's premise does not survive its own receipt: 0 of 8 flip.** Replayed through the
   production cascade on all 18 era board dates, **none** of the 8 never-eligible runners tagged
   `counter-trend, no 200-reclaim/hold` becomes eligible under HK's `reclaim_veto=False`. Six flip
   their reason to `failed next-bar hold`; two are stopped downstream by the freshness/topped gate.
   HK's analogous receipt was **6 of 9 flipping** — the HK mechanism does not transfer to this cohort.
10. **002155.SZ points the same way.** At its buy bar it was **5.2% above** its 200-day mean, so the
    counter-trend branch never opened and no reclaim was tested. Its second blocker (after the
    divergence veto) is the **HOLD** leg on the main path. Removing the 200-reclaim leg leaves it
    blocked; removing the hold admits it.
11. **The shipped reason strings cannot carry a removal decision.** Of the 1,590 blocks reading
    `counter-trend, no 200-reclaim/hold`, only **639 (40.2%)** are relieved by dropping the reclaim
    rule — 922 fail the hold too and 29 fail *only* the hold. And all 1,094
    `failed reclaim-and-hold` blocks sit on the main path, where **no reclaim is tested**.
12. **Where the leg *does* look protective is not where it is being complained about**: the
    RECLAIM leg is 2.9× over-represented on Recovery+/Trough+ names (50.4% vs 17.3% of mapped) and
    EARNS at H=21 above MA50 — while in the deepest-drawdown tercile the family blocks the *best*
    cell in the study (+13.0pp win, −9.2pp catastrophic).
13. **RECOMMENDATION: do NOT remove anything. Prereg + display-tier relief.** The one keep the data
    grant (RECLAIM at H=21) is half-split-unstable and risk-leg-contradicted; the one door the
    product wants (continuation) is gated by the HOLD leg, which HK kept on both policies and which
    nothing here licenses touching. The cheap, honest fix is to name **every** failing leg on a
    blocked row rather than the first match.

---

## Status and scope

MEASUREMENT ONLY — in-sample, motivating-only, **no promotion and no gate change**. Verdict
language is "the leg earns / fails its keep on this window"; it feeds a prereg + ratification,
never a hot removal. Instrument: `research/cn_prophet_audit/cn_reclaim_hold_audit.py`; frozen
numbers: `research/cn_prophet_audit/cn_reclaim_hold_results.json` (rerun:
`python3 research/cn_prophet_audit/cn_reclaim_hold_audit.py`, ~355s).

Direct mirror of `research/cn_prophet_audit/cn_divergence_veto_audit.py` (PR #4576) — same window,
panel, anchor, fill, metrics, keep rule and funnel-decomposition discipline — applied to the other
side of the same filter.

**Trigger.** The divergence audit measured CN's buy funnel and found the leg it was auditing is
*not* the board's primary blocker: 743 blocks against this family's **2,684** (its
`ADMITTED_FAILED_OTHER_LEG` counter). Three receipts point here:

* 002155.SZ (湖南黄金) — the operator's gold-miner case. Its shipped `gate_reason` names the
  divergence veto, but the divergence audit's counterfactual left it **still blocked —
  `failed reclaim-and-hold`**.
* `research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §2.7 — of 17 never-eligible
  top-150 era runners, **8** carry `counter-trend, no 200-reclaim/hold` and 2 more carry
  `failed reclaim-and-hold`. §2.7 calls the cohort "the continuation/rotation shape the family
  structurally cannot admit"; R4 proposes a continuation door for it.
* **HK removed its sibling leg after measurement** — PR #4470 / `e337d95f312`, operator ruling
  2026-08-03, era stamp `hk_prophet_v1 → v2`, scoped by the very `reclaim_veto` parameter this
  study uses as its counterfactual. CN's has never been measured.

## The family, re-derived from production (not approximated)

`engine/signal_quality.py:178` `_buy_filter(i, sig, bear, n, *, reclaim_veto: bool = True)`. After
the divergence veto returns (lines 208-209) the **entire remainder of the function is this family**
— there is no third leg:

```python
212  held = bool(c.iloc[i + 1] > c.iloc[i])
213  below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
214  if below and wkdn:                                    # the COUNTER-TREND branch
215      if reclaim_veto:
218          reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
219          ok = held and reclaim
220          return ok, (... else "counter-trend, no 200-reclaim/hold")
224      return held, (... else "failed next-bar hold")     # reclaim_veto=False (HK)
225  return held, (... else "failed reclaim-and-hold")      # the MAIN path
```

`above200` (`engine/signal_quality.py:99`) is the 3B close over the **200-day** rolling mean of the
daily close; `w_bull` (`:97`) is the W-FRI RSI-MACD ≥ its signal, shifted one week.

**Two sub-legs, audited each and together.**

| | condition | separable? | counterfactual |
|---|---|---|---|
| **R — RECLAIM** | `signal_quality.py:214-220` — a name BOTH below its 200-day average AND weekly-down must close back above that average at bar i+1 or i+2 | **yes, by a production parameter** | `_buy_filter(..., reclaim_veto=False)` — the shipped HK call (`signal_gate.py:155` exposes it, `build_hk_library.py` ships it, `tests/test_hk_reclaim_veto_policy.py:46-59` pins the flip, `:83-90` pins branch-identity off the counter-trend path) |
| **H — HOLD** | `signal_quality.py:212` `held = close[i+1] > close[i]`, consumed at `:219` and `:225` | **no** — no shipped caller can switch it off | `_cf_filter(..., hold=False)`, a 6-line re-derivation, **parity-gated on 100% of fires** |
| **FAMILY** | R ∪ H | — | `_cf_filter(hold=False, reclaim=False)` = the whole tail deleted |

**P0-B — the re-derivation cannot drift unseen.** A mirrored counterfactual that nothing can see
fail is worthless (`mirrored-guard-test-is-vacuous-on-indirection`). So on **every one of the 5,157
in-window fires** the instrument asserts the full `(take, reason)` tuple:
`_cf_filter(hold=True, reclaim=True)` == production's `reclaim_veto=True`, and
`_cf_filter(hold=True, reclaim=False)` == production's `reclaim_veto=False`. **0/0 mismatches.**
Three further invariants ran clean: `pending` is structurally unreachable at this anchor (0),
RECLAIM_ADMIT ∩ HOLD_ADMIT = ∅ (0), and the family counterfactual admits every non-bear fire (0).
Any violation aborts the leg-H and family numbers.

**CN call site and policy.** `scripts/build_china_library.py:1960`
`sig_verdict[ticker] = signal_gate.gate(ticker, close)` → `engine/signal_gate.py:155`
`gate(..., reclaim_veto: bool = True)` (the DEFAULT path — CN never passes `False`) →
`analyze(ticker, daily_close)` **with no `daily_high`/`daily_low`**. The instrument reproduces that
exactly (close-only).

## Design (pre-registered; nothing below was chosen after seeing a result)

| | |
|---|---|
| Panel | `data/china_stocks/*.parquet`, ≥250 bars → **1,637 names** (41 skipped thin) |
| Window | anchor date in 2025-08-01 … 2026-07-31 · frozen replay at GRADE_ASOF 2026-08-04 |
| Fire | the production buy event `CB[i] or revBuy[i]` (`signal_quality.py:267`) |
| Cells | `ADMITTED` = production take · `RECLAIM_ADMIT` = blocked, admitted by removing R alone · `HOLD_ADMIT` = blocked, admitted by removing H alone · `BLOCKED_BY_BOTH` = neither alone · `FAMILY_ADMIT` = their union. Every decision cell has passed **identical** other legs; only the audited leg's state differs |
| Anchor | last daily session of 3B bar **i+2** — the first close at which the label is knowable |
| Ruler | T+1 **HL2** fill, locked-limit (T+1 high==low==close) **excluded**; CSI300-relative (510300.SS) excess at H=10 / H=21 |
| Metrics | n · win% + Wilson 95% CI · median/mean excess · MAE-p10 · catastrophic (**absolute** ≤ −15%) · **MFE-p90** (reported only, never in the rule) |
| Dedup | within-cell, 5 sessions per name; the family cell deduped on its **own** coarse partition |

**Marker-date grading is forbidden** (`engine/signal_quality.py:198-206`; CN-1 §W6-CN). For *this*
family the i+2 anchor is exactly tight, not merely sufficient: `held` is bar i+1 and `reclaim` is
bars i+1/i+2, and nothing later enters the label. `resample("3B")` labels buckets on the **left**
edge, so the anchor is resolved through an explicit bucket→last-daily-date map, never by reading a
bar label as a close date.

**KEEP RULE (pre-registered, byte-identical to the divergence audit's).**

> A blocking leg **EARNS** its keep on a cell iff **either**
> (R) win%(BLOCKED) ≤ win%(ADMITTED) − 3pp, **or**
> (K) catastrophic%(BLOCKED) ≥ catastrophic%(ADMITTED) + 3pp, or MAE-p10 deeper by ≥ 3pp,
> on a cell with **n ≥ 100 on both sides**. Neither leg → **FAILS**. n below the floor →
> **UNDECIDED** (printed, never read as a pass).

Reported alongside (a stricter read, not a rule change): whether the blocked cell's Wilson CI
**excludes** the return-leg keep bar. A FAILS whose CI straddles the bar is "no measurable
protection", not "proven harmful".

**The HK bar, for calibration.** HK deleted leg R on a measurement that cleared this bar in
*neither* direction: the unblocked cohort earned ≈0 excess vs HSI (mean +0.55%/20d, CI crossing
zero) and carried **deeper** drawdown (median 60d MAE −9.0% vs −7.4%; P(excess<−20%) 5.8% → 7.9%).
It shipped as an operator product bet on a regime its own masterplan calls **not gradeable** —
"a bet on that regime, not a finding about it" (`HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md` §0
G6). Precedent for *measuring*; not precedent for removing on a null.

**MFE is carried, and is not in the rule.** The HK postmortem records a retraction on this exact
leg family — endpoint excess is the wrong lens for a bounce — so MAE-p10 ships with its complement.
It changes no verdict.

**P0-A gate (passes before any cycle cell is printed).** The basket-cycle stratifier is
reconstructed through the production path (`baskets_china.compute_china_baskets` →
`china_sector_cycles._basket_series` → `sector_cycles._record_core`, series truncated at each weekly
stamp). It reproduces the shipped 2026-08-03 `cn_gold` read **exactly — Recovery / pos 13.5 /
osc_slope 12.9** — and agrees with the shipped log on **144/154 (93.5%)** overlapping (basket, date)
phase pairs, median |Δosc_slope| = 0.0. Identical to the divergence audit's gate.

**Cross-check against the divergence audit.** Recomputed from the opposite side of the same filter,
all six frozen funnel numbers match: fires 5,157 · vetoed 743 · vetoed-blocked-anyway 575 ·
vetoed-admit 168 · admitted 1,730 · family blocks 2,684. The two instruments agree.

## Funnel — what the family actually costs

| | |
|---|---|
| Fires in window | 5,157 |
| …divergence-vetoed upstream (never reach this family) | 743 |
| Population reaching the family | 4,414 |
| Takes today | 1,730 |
| **Family gross blocks** | **2,684 — 52.1% of all fires** |
| …blocked anyway by a later leg | **0 by construction** — the family *is* the tail of `_buy_filter` |
| Extra takes if the family were deleted | **+155.1%** |
| RECLAIM gross | 1,561 (30.3% of fires) — **922 (59.1%) the HOLD leg blocks anyway** |
| RECLAIM decision set | **639** → +36.9% takes |
| HOLD gross | 2,045 (39.7%) — **922 (45.1%) the RECLAIM leg blocks anyway** |
| HOLD decision set | **1,123** → +64.9% takes |
| Blocked by both | 922 |

The partition reconciles exactly: 639 + 1,123 + 922 = 2,684.

This is HK's headline shape reproduced on CN. HK's reclaim veto was 68% of all HK rejections; this
family is **52.1% of all CN fires** and its reclaim sub-leg alone is 30.3%. The divergence veto, by
comparison, is 14.4%.

### The reason strings cannot carry a removal decision

| shipped string | gross | RECLAIM-only | BOTH | HOLD-only |
|---|---|---|---|---|
| `counter-trend, no 200-reclaim/hold` | 1,590 | **639 (40.2%)** | 922 (58.0%) | 29 (1.8%) |
| `failed reclaim-and-hold` | 1,094 | 0 | 0 | **1,094 (100%)** |

Two distinct defects, both measured:

* The counter-trend string is printed for a failed hold, a failed reclaim, **or both** — so a row
  reading "no 200-reclaim" is relieved by dropping the reclaim rule only **40% of the time**.
* `failed reclaim-and-hold` is the **main-path** string, reached only when the name is *not* both
  below-200 and weekly-down — **no reclaim is tested there at all**. The string mis-names its own
  condition, on 1,094 blocks.

Same family of defect as the divergence audit's first-match finding, and it is why both case
receipts below read the opposite of what their reason strings suggest.

## Headline — decision cell vs ADMITTED

| leg | H | n | names | win% | Wilson 95% | med exc | mean exc | MAE-p10 | MFE-p90 | cat% | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **FAMILY** | 10 | 2,436 | 1,233 | **49.88** | [47.89, 51.86] | −0.03 | +0.77 | −13.05 | +17.59 | 4.06 | **FAILS** (CI excludes) |
| *admitted* | 10 | 1,681 | 1,111 | 47.41 | [45.03, 49.80] | −0.48 | +1.22 | −14.87 | +26.46 | 5.65 | — |
| **FAMILY** | 21 | 2,163 | 1,186 | **43.00** | [40.92, 45.09] | −1.75 | −0.13 | −18.47 | +28.06 | 10.36 | **FAILS** (CI excludes) |
| *admitted* | 21 | 1,633 | 1,091 | 43.85 | [41.46, 46.26] | −1.87 | +1.83 | −20.71 | +41.10 | 12.68 | — |
| **RECLAIM** | 10 | 529 | 432 | 51.23 | [46.98, 55.46] | +0.18 | +0.38 | −11.17 | +14.11 | 3.78 | **FAILS** (CI excludes) |
| **RECLAIM** | 21 | 432 | 373 | 40.05 | [35.53, 44.74] | −2.76 | −1.55 | −16.77 | +20.68 | 9.03 | **EARNS** (CI does *not* exclude) |
| **HOLD** | 10 | 1,088 | 801 | 46.23 | [43.29, 49.20] | −0.76 | +0.74 | −14.92 | +20.92 | 5.51 | **FAILS** |
| **HOLD** | 21 | 1,056 | 790 | 45.27 | [42.29, 48.28] | −1.10 | +1.27 | −19.43 | +35.57 | 10.80 | **FAILS** (CI excludes) |
| BOTH | 10 | 819 | 570 | 53.85 | [50.42, 57.23] | +0.79 | +1.05 | −11.72 | +15.54 | 2.32 | FAILS (CI excludes) |
| BOTH | 21 | 675 | 502 | 41.33 | [37.68, 45.09] | −2.08 | −1.41 | −18.03 | +21.87 | 10.52 | FAILS |

**FAMILY — FAILS at both horizons, on every leg of the rule.** Δwin +2.47pp (H=10) and −0.85pp
(H=21, inside the 3pp bar); Δcatastrophic −1.59pp/−2.32pp and ΔMAE-p10 +1.82pp/+2.24pp both favour
the *blocked* side. Keep bars 44.41% / 40.85%; the blocked CI lies entirely above both — though at
H=21 only just (CI low 40.92 vs bar 40.85, a 0.07pp margin), so read the H=21 exclusion as a
technical pass, not a comfortable one. Name concentration is a non-issue (1,233 names for 2,436
events).

**RECLAIM — the one EARNS in the study, and it is narrow.** At H=21 Δwin = −3.80pp, just past the
−3pp bar. But (a) the CI [35.53, 44.74] straddles the bar, (b) both risk legs point the *opposite*
way past the same margin (Δcatastrophic −3.65pp, ΔMAE-p10 +3.94pp — the blocked cell is safer), and
(c) it inverts at H=10 (+3.82pp, CI excluding the bar). Bounce-then-fade is exactly the shape a
reclaim rule is nominally for; it is also exactly the shape a short window manufactures.

**HOLD — FAILS at both.** Δwin −1.18pp / +1.42pp; risk legs flat-to-adverse.

### Amplitude — what the keep rule cannot see

MFE-p90 is not in the rule and changes no verdict, but it is the single most consistent number in
the study: **the blocked cell has a thinner right tail than its admitted control in 83 of the 84
stratum cells** where both sides are populated (family −8.87pp at H=10 and −13.04pp at H=21; range
−33.49pp to +1.92pp). The lone exception is HOLD in the deepest-drawdown tercile at H=21
(+1.92pp, n=203 vs 154). Restricting to the 54 cells that clear the n≥100-both-sides floor changes
nothing: 53 negative, the same one positive.

Paired with the MAE-p10 gaps, which run the *same* direction (blocked cells are shallower), this
says the family is not separating winners from losers at all: **it is selecting a lower-amplitude
population, thinner on both tails.** A blocked fire still makes a real excursion — p90 is +17.6% at
H=10 and +28.1% at H=21 — but a smaller one than today's takes.

That matters for how the HK precedent transfers. HK's product case for removal was
peak-after-entry: 54 of 54 live blocked names positive, median +5.2%, five ≥ +15%. On CN the
blocked population's peak-after-entry is *below* the admitted population's at every cut. The
argument that carried the HK ruling does not reproduce here, and it would have been invisible on
endpoint excess alone — which is exactly the retraction the HK postmortem records.

**Fill-convention robustness.** Swapping the pinned T+1 HL2 for the production open-preferring fill
moves every headline win% by ≤ 0.94pp and every median by ≤ 0.19pp, and flips no verdict. Not
fill-driven.

> **Read the absolute level with care.** Both sides are near coin-flip because this is the raw
> `signal_gate` fire population across 1,637 names, **not** the Prophet board (which layers rank,
> tier, liquidity, extension and featured gates on top). The comparison is cell-vs-cell; the level
> is not a board win rate.

## Stratification

### The CONTINUATION cell — the operator's question

`trail_63 > 0` at the anchor (`close[d0]/close[d0−63] − 1`, the `v1_runner_coverage_audit.py:88`
convention): an **uptrending** name that the family refuses.

| leg | H | blocked n | blocked win% | admitted win% | Δwin | ΔMFE-p90 | verdict |
|---|---|---|---|---|---|---|---|
| **FAMILY** | 10 | 637 | 42.07 | 45.17 | **−3.10** | −6.04 | **EARNS** |
| **FAMILY** | 21 | 613 | 44.05 | 42.76 | +1.29 | −6.03 | FAILS |
| **HOLD** | 10 | 581 | 41.48 | 45.17 | **−3.69** | −5.11 | **EARNS** |
| **HOLD** | 21 | 566 | 45.05 | 42.76 | +2.29 | −4.42 | FAILS |
| **RECLAIM** | 10 | **29** | 41.38 | 45.17 | −3.79 | −16.90 | UNDECIDED (n) |
| **RECLAIM** | 21 | **25** | 28.00 | 42.76 | −14.76 | −33.49 | UNDECIDED (n) |

Three readings, in order of how much weight they bear:

1. **The family earns its keep here at H=10 and loses it at H=21.** A horizon split of that size on
   the same cell is not a keep; it is an unresolved question. Nothing licenses a change either way.
2. **The leg doing the blocking is the HOLD leg, not the 200-reclaim leg.** RECLAIM contributes
   **29 of the 637** blocked continuation fires — 4.5% of its own decision set. That is mechanical:
   its branch requires the name to be *both* below its 200-day average *and* weekly-down, which an
   uptrending name rarely is. **§2.7 and R4 name "counter-trend/200-reclaim filters" as the
   continuation door's obstacle; on this window the reclaim filter is almost never in the doorway.**
3. **Do not read this cell as §2.7's cohort.** §2.7's never-eligible names sit at median
   trail_63 = **−11.2%** — shallow, not positive. The sign split is a *stricter* continuation
   definition. Per-cell trail_63 medians are printed in every block of the JSON so the two cannot
   be conflated.

### Drawdown tercile — where "unsatisfiable by construction" shows up

| tercile | H | FAM n | FAM win | ADM n | ADM win | Δwin | Δcat | verdict |
|---|---|---|---|---|---|---|---|---|
| T1 deepest (≤ −24.1%) | 10 | 1,110 | 49.28 | 171 | 36.26 | **+13.02** | −9.21 | FAILS |
| T1 deepest | 21 | 886 | 40.18 | 154 | 36.36 | +3.82 | −1.36 | FAILS |
| T2 mid (−24.1…−11.6%) | 10 | 885 | 50.73 | 525 | 51.24 | −0.51 | −1.51 | FAILS |
| T2 mid | 21 | 840 | 42.38 | 509 | 41.06 | +1.32 | −5.00 | FAILS |
| T3 shallowest (> −11.6%) | 10 | 441 | 49.66 | 985 | 47.31 | +2.35 | −0.29 | FAILS |
| T3 shallowest | 21 | 437 | 49.89 | 970 | 46.49 | +3.40 | −3.30 | FAILS |

The deepest tercile is the mechanism made visible. HK's finding — a name 17% below its 200-day line
cannot travel 17% in two sessions, so the rule is arithmetic rather than risk judgement — predicts
exactly this: only **171** admitted fires exist in T1 against 1,110 blocked, and the blocked cell
wins **13pp more** while being **9.2pp less** catastrophic. Deep-drawdown names are close to
unadmittable, and the ones the family refuses there are not the bad ones.

The amplitude read tempers it: in T1 the blocked cell's MFE-p90 is **+17.07% vs +22.96%** admitted
(−5.89pp) and its MAE-p10 is **−14.08% vs −18.53%** (4.45pp shallower). Better win rate, lower
catastrophic share, *and* a smaller upside tail — a quieter population, not a better one.

(This is the one place CN diverges sharply from the divergence audit, whose deepest tercile was the
single cell arguing *for* its leg.)

### MA50 side

| leg | level | H | n | Δwin | Δcat | ΔMAE-p10 | verdict |
|---|---|---|---|---|---|---|---|
| FAMILY | above MA50 | 10 / 21 | 986 / 914 | +1.91 / +0.38 | −0.64 / −1.08 | +0.92 / +1.08 | FAILS / FAILS |
| FAMILY | below MA50 | 10 / 21 | 1,450 / 1,249 | +6.74 / +2.53 | −1.58 / −3.14 | +0.80 / +2.17 | FAILS / FAILS |
| RECLAIM | above MA50 | 21 | 192 | **−6.76** | −3.30 | +4.90 | **EARNS** |
| RECLAIM | below MA50 | 21 | 240 | +2.82 | −3.84 | +3.10 | FAILS |

The RECLAIM leg's H=21 keep concentrates **above** MA50 — a name above its 50-day mean but below
its 200-day and weekly-down, i.e. a partial bounce that has not repaired the long trend. That is a
coherent story and the only one in the study; it is also n=192 on one horizon in one window.

### Basket cycle state (Recovery+/Trough+)

| leg | H | blocked n | blocked win% | admitted n | admitted win% | verdict |
|---|---|---|---|---|---|---|
| FAMILY | 10 | 126 | 58.73 | 44 | 61.36 | UNDECIDED (admitted n) |
| FAMILY | 21 | 100 | 32.00 | 38 | 42.11 | UNDECIDED (admitted n) |
| RECLAIM | 10 / 21 | 52 / 40 | 59.62 / 30.00 | 44 / 38 | 61.36 / 42.11 | UNDECIDED |

Every cell is under the floor on the admitted side; nothing is claimed. **Composition is readable
and it differs from the divergence audit's finding.** Among basket-mapped fires, Recovery+/Trough+
is **50.4% (66/131) of the RECLAIM decision set** against **17.3% (51/295) of admitted** — 2.9×
over-represented. The family overall is 30.8%; the HOLD leg is 13.8% (*under*-represented).
So the "this leg systematically blocks early-Recovery reclaims" premise, which the divergence audit
refuted for its own leg, **holds for the RECLAIM sub-leg specifically**. Coverage caveat: only
~17-21% of fires map to a curated basket, so this is directional.

### Half-split robustness — stable at the family level, unstable for the keep

| leg | half | H | n | Δwin | verdict |
|---|---|---|---|---|---|
| FAMILY | H1 2025-08…2026-01 | 10 / 21 | 966 / 966 | +2.94 / +4.25 | FAILS / FAILS |
| FAMILY | H2 2026-02…2026-07 | 10 / 21 | 1,470 / 1,197 | +3.37 / −2.31 | FAILS / FAILS |
| RECLAIM | H1 | 21 | 176 | +2.39 | FAILS |
| RECLAIM | H2 | 21 | 256 | **−4.95** | **EARNS** |
| HOLD | H1 / H2 | 21 | 590 / 466 | +4.76 / −1.88 | FAILS / FAILS |

**The family's FAILS verdict survives the split** — the robustness leg the divergence audit could
not clear (its sign inverted, and it said so). **The RECLAIM leg's single EARNS does not**: it is
entirely an H2 phenomenon, and H2 is a materially worse tape for everyone. Read it as regime-
conditional, exactly as the divergence audit read its own inversion.

## Case receipts

### 002155.SZ (湖南黄金) on 2026-08-03 — the binding leg is the HOLD, on a path with no reclaim

The name enters this study only through the **composed** counterfactual: in production the
divergence veto fires first, so the family is never reached. Replayed PIT, close-only:

| | |
|---|---|
| Production verdict | `take=False`, `reason="veto: bearish divergence"` |
| Rendered gate reason | `buy blocked by filter: veto: bearish divergence` |
| Reproduces the shipped row byte-for-byte | **yes** (`off_high=−44.3`, `narrative_level=HOT`, `board_definition=cn_prophet_v2`) |
| Last buy bar (3B label / confirmed) | 2026-06-17 / 2026-06-18 |
| At that bar: `above200` / `w_bull` | **True** (26.66 vs a 25.34 200-day mean, +5.2%) / False |
| Branch taken | not both below-200 and weekly-down → **MAIN path** |
| `held` = close[i+1] > close[i] | **False** (26.06 vs 26.66) |
| `reclaim` | **never evaluated** — the main path does not test it |
| + divergence removed | `take=False`, `"failed reclaim-and-hold"` |
| + divergence **and RECLAIM** removed | `take=False`, `"failed reclaim-and-hold"` — **unchanged** |
| + divergence **and HOLD** removed | **`take=True`** |
| dd from 252d high, at the buy bar / at the board date | −34.86% / −44.27% |

**At its buy bar the name was 5.2% *above* its 200-day average**, so the counter-trend branch — and
with it the entire 200-reclaim rule — was never entered. The string that names a reclaim,
`failed reclaim-and-hold`, describes a test that did not run. The binding constraint is the
**next-bar hold**, the leg HK kept on both policies.

Deleting the 200-reclaim rule would not surface 湖南黄金. Nor would deleting the divergence veto
(the divergence audit's finding). Only deleting the hold confirmation would — and this name's close
went 26.66 → 22.81 (−14.4%) between that buy bar and the board date, which is the case the next-bar
hold test exists to make. One name is an illustration, not evidence; the evidence is the HOLD row
of the headline table, which says the leg earns nothing at population level either.

### The §2.7 never-eligible cohort — 0 of 8 flip

All 8 never-eligible top-150 era runners whose frozen `last_reason` is
`counter-trend, no 200-reclaim/hold`, replayed through `signal_gate.gate()` on all **18** V1 era
board dates (2026-06-30 … 2026-07-29) under both policies, series truncated per date:

| ticker | era ret | trail-21 | trail-63 | dd | eligible days `reclaim_veto=True` | `=False` | reason under the HK policy |
|---|---|---|---|---|---|---|---|
| 002003.SZ | +28.6% | −8.4% | −9.3% | −25.9% | 0 | **0** | failed next-bar hold |
| 603871.SS | +28.4% | −10.8% | −28.0% | −35.6% | 0 | **0** | failed next-bar hold |
| **603087.SS** | **+20.0%** | **+8.6%** | −1.3% | −27.3% | 0 | **0** | **failed next-bar hold** |
| 002594.SZ | +19.0% | −17.1% | −22.7% | −30.7% | 0 | **0** | held but topped/rolled-over |
| 600039.SS | +18.7% | −10.7% | −21.1% | −26.1% | 0 | **0** | failed next-bar hold |
| 600422.SS | +18.3% | −12.5% | −30.5% | −47.7% | 0 | **0** | failed next-bar hold |
| 600095.SS | +16.5% | −11.2% | −18.2% | −44.8% | 0 | **0** | failed next-bar hold |
| 002345.SZ | +16.3% | −0.4% | −7.3% | −43.7% | 0 | **0** | held but topped/rolled-over |

**Not one becomes eligible.** Six change their reason to `failed next-bar hold`; two are stopped
downstream by the freshness/not-topped cascade (`signal_gate.py:190-192`) rather than by
`_buy_filter` at all. The featured name — **603087.SS**, the only one of the eight with a positive
21-day trail (+8.6%), the literal continuation shape — is refused by the **hold**, not the reclaim.

The contrast with HK is the point. HK's removal receipt was **6 of 9 witness markers flipping
`block` → `take`** (Xiaomi, Alibaba, Meituan, Ping An, CSPC, China Medical), with BYD and Kingdee
staying blocked on the next-bar hold. **CN's is 0 of 8, all of them BYD-and-Kingdee-shaped.** The
mechanism HK removed is not what is holding this cohort out.

> **This cohort is selected on winners by construction** — it is the top-150 names by era return.
> It can show *which leg* bound; it cannot show what the leg's block rate is worth, because the
> losers it also blocked are not in the list. This is the same defect the HK postmortem records
> about its own `vetoed` display lane ("never cite the vetoed lane as evidence about the veto").
> The unselected evidence is the headline table; this receipt is a mechanism decomposition.

## Verdict

**On this window the reclaim-and-hold family FAILS its keep overall — at both horizons, on all
three legs of the rule, with the blocked cell's CI excluding the keep bar at both, and the verdict
surviving the half-split.** That is a stronger negative than the divergence audit produced for its
own leg.

**In the CONTINUATION cell it EARNS at H=10 (Δwin −3.10pp) and FAILS at H=21 (+1.29pp)** — a
horizon split, not a keep. And the sub-leg carrying that block is the **HOLD** confirmation
(n=581), not the 200-reclaim rule (n=29). The continuation door §2.7 wants is gated by the leg HK
deliberately kept, not the leg HK deleted.

**Do not remove anything.** In-sample, one year, one market; the single EARNS in the study
(RECLAIM at H=21) is risk-leg-contradicted, CI-straddling and carried by one half of the window;
and both motivating receipts point at a leg nobody has proposed touching.

**And be clear about what removal would buy.** "The family fails to protect" is not "the family is
blocking the winners". In 83 of 84 stratum cells the blocked side has a *thinner* right tail than
the admitted control. Deleting the family would add 155% more takes drawn from a lower-amplitude
population — more names, shallower drawdowns, smaller peaks, no measurable edge either way. That is
a breadth decision and a product decision, not a finding this measurement can make.

### What a relief construction would look like

1. **Name every failing leg, not the first match — display-tier, no admission change.** 60% of
   `counter-trend, no 200-reclaim/hold` rows are also failing the hold, and 100% of
   `failed reclaim-and-hold` rows never met a reclaim test. Both case receipts here were misread by
   their own reason strings. This is the cheap, honest fix and it is the same recommendation the
   divergence audit reached from the other side of the filter.
2. **If a continuation door is still wanted, it is a HOLD-leg question.** Candidates worth
   pre-registering (none measured here): a *cadence* relaxation — accept a hold confirmed within
   i+1 **or** i+2 rather than i+1 only — or a trail-conditioned exemption for `trail_63 > 0` names.
   Both are admission changes and neither ships without the prereg below.
3. **Prereg + forward cohort, mirroring `VETO_LEG_AUDIT.md` recommendation 3 and G6.** Register
   this keep rule with an out-of-sample window; accrue `RECLAIM_ADMIT` / `HOLD_ADMIT` fires on the
   CN forward ledger from day one; revisit at ≥100 matured fires spanning ≥2 quarters with the
   half-split repeated. Nothing in this document is out-of-sample.
4. **The RECLAIM-above-MA50 cell (H=21, n=192) is the only positive hypothesis worth carrying
   forward.** Shadow-accrue it; do not act on it.
5. **Whatever is registered, grade it on the path, not the endpoint.** MFE-p90 belongs in the
   prereg's reported set from day one. It is the only metric in this study that speaks with one
   voice (83 of 84 stratum cells), it is invisible to the current keep rule, and reading a bounce
   population without it is the error the HK removal had to retract.

## Limitations

One year, one market, **in-sample**, no out-of-sample holdout — motivating only. The half-split
holds for the family's FAILS but not for the RECLAIM leg's single EARNS, which alone disqualifies
that keep from carrying authority. H=21 cannot mature for fires anchored after ~2026-07-02, so
H=21 cells are smaller and end-loaded. The leg-H and family counterfactuals are re-derivations
rather than production calls — parity-gated on 100% of fires against both branches production *can*
express, which is the strongest check available but is not a shipped code path. Basket membership
is hindsight-curated (`engine/baskets_china.py` module docstring says so) and today's roster is
applied to past dates; cycle/narrative coverage is ~17-21% of fires, so those strata are
directional at best. Name-clustered dependence is not modelled (name spread reported instead:
1,233 names for 2,436 family events). 8 fires were dropped as T+1 locked-limit and 2 for no T+1 bar
— excluded, never fabricated; 156 fires fell inside the last two bars and could not be confirmed at
the i+2 anchor. Downstream board gates (rank, tier, liquidity, extension, freshness) sit outside
this instrument — two of the eight §2.7 names are stopped there, and the absolute win rates are the
raw `signal_gate` fire population, not the Prophet board.
