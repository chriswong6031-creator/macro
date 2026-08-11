# Top Anatomy — W2 Tier-Widening Report (`top_anatomy_w2`)

Research/display tier, zero scored authority; AVOID-not-SHORT (`DNR:KILL-DIRECTIONAL-SHORTING`); no rank, no size, no gate, no exit rule; nothing here is a probability or a call. Prereg: `research/top_anatomy/TOPA_W2_PREREG.md`, frozen on this branch BEFORE any W2 number existed (commit order is the proof). Charter: `reports/top-anatomy-phase0.md` §12 item 2 — "No W1 claim generalizes until W2 reports." This is that report.

## §1 The coverage answer (read first)

Phase-0's registered cohort was fast small/mid-caps by construction: the +50%/126d bar excluded every motivating exemplar — zero gold/PGM miners, zero extended AI leaders. W2 asked whether lowering the bar admits them, and the answer splits in two:

**Historically — yes, almost completely.** Under `r63≥+0.35`, 14 of 14 watched AI leaders and 15 of 16 miners hold at least one arm episode on the tape (GOLD alone never qualifies); under `(c−MA200)/ATR63≥6`, all 30 of 30 do. The widened panels contain the moderate-velocity cohort the program was chartered to understand — 3,190 R63 episodes and 11,360 ATRZ episodes with ZERO extended-day overlap with phase-0's cohort.

**On the vintage date — no exemplar is extended,** on either arm (R63 roster 295 names, ATRZ roster 848, both 2026-07-02). This is a stale-tape fact, not a bar-width fact: the store ends 2026-07-02, all 16 miners show *negative* trailing-63 returns at that date (the miner rally the operator traded is a July–August move, entirely after the tape ends), and the AI complex sits in drawdown-recovery shapes that fail the near-high term. Tier-widening answers the historical-anatomy question below; the "who is extended today" question stays open until the store refresh lands. No W2 claim about today's market should be read from this report.

**Current-regime read on the confirmed leg (post-hoc, descriptive, as of the stale vintage — §5 for detail):** the widened rosters were running hot. 56 of 295 R63 names (19.0%) and 143 of 848 ATRZ names (16.9%) sat at or beyond their arm's topped-typical B2 fire threshold — 1.7–1.9× the 10% control-tail base rate — and the R63 roster's *median* name (RSI-14 67.6) matched the disjoint topped-episode median (68.1) rather than the matched-control median (65.3). The ATRZ roster is control-typical in aggregate (63.4 vs 63.1) with the elevated tail. Watch-language only; five weeks stale; re-read after the store refresh.

## §2 Arms, panels, and what "travels" means

Both arms re-ran the frozen phase-0 pipeline (same tape vintage 2021-07-06 → 2026-07-02, same sanity-segmented identities, race, features, matching procedure, B=2000 seed 20260810, floors) with the §4.1 trigger as the ONLY moved variable. Declared census quantities reproduced exactly: R63 = 151,325 EXT days (95,307 shared with primary / 56,018 new), ATRZ = 652,410 (150,011 shared / 502,399 new).

| | R63 (`r63≥+0.35`) | ATRZ (`(c−MA200)/ATR63≥6`) |
|---|---|---|
| Episodes | 8,244 (3,190 disjoint / 2,623 partial / 2,431 fully-shared) | 17,232 (11,360 / 3,873 / 1,999) |
| FULL panel | 2,121 episodes / 47 peak-months | 4,032 / 48 |
| DISJOINT panel | 323 episodes / 39 peak-months (floor ≥12 met) | 1,409 / 47 (met) |
| Wall | 1,065 s | 2,669 s (no deferral) |

DISJOINT = episodes sharing zero (segment, session) EXT-days with phase-0's cohort — new episodes, mostly moderate-velocity names. It is the primary panel for every generalization claim. FULL panels are partial re-measurement of phase-0 episodes by construction and are supporting evidence only. Scope (frozen in the prereg): "travels" means cross-tier transfer on the same 2022H2–2026 tape — the disjoint episodes are new names-and-times within the same era, not a new era. Out-of-time replication stays open until the store extends.

## §3 Confirmatory verdict — one leg travels, and it is not the registered one

Five phase-0 survivors, one-sided in their phase-0-observed directions, BH-FDR q≤0.10 within each (arm × panel) family of 5. All twenty cells printed; confirmations and failures at equal prominence.

| Leg (declared) | R63 DISJOINT | R63 FULL | ATRZ DISJOINT | ATRZ FULL | Grade (R63 / ATRZ) |
|---|---|---|---|---|---|
| `B2_rsi14` (+) | **+3.87 [+2.56,+5.25] q=0.0025** | +0.76 q=0.012 | **+3.92 [+2.80,+4.79] q=0.0025** | +2.02 q=0.0008 | **CONFIRMED / CONFIRMED** |
| `A4_r252` (−) | −0.044 [−0.078,+0.024] q=0.21 | −0.118 q=0.0008 | **+0.021 [+0.005,+0.033] q=0.98 — sign flip, CI excludes 0 on the wrong side** | −0.033 q=0.0008 | PARTIAL / PARTIAL |
| `C6_tr5_over_tr63` (−) | −0.001 q=0.59 | −0.048 q=0.0008 | +0.006 q=0.68 | −0.012 q=0.17 | PARTIAL / **NOT-CONFIRMED** |
| `D1_dvol_z` (−) | −0.035 q=0.48 | −0.080 q=0.0075 | −0.044 q=0.46 | −0.090 q=0.0008 | PARTIAL / PARTIAL |
| `D3_updown_dvol_ratio21` (−) | **+0.152 [−0.131,+0.357] q=0.85 — sign flip** | −0.125 q=0.0008 | −0.023 [−0.081,+0.066] q=0.46 | −0.065 q=0.018 | PARTIAL / PARTIAL |

Three findings, stated plainly:

1. **Heat travels.** `B2_rsi14` is W2-CONFIRMED on both arms with disjoint effects three times phase-0's (+3.9 RSI-14 points vs +1.29): in moderate-velocity cohorts, topped episodes run measurably hotter than matched continued controls at the same extension, volatility, and liquidity. EARLY lead-time class in all four cells.
2. **The registered leg does not travel.** `D3_updown_dvol_ratio21` — phase-0's only REGISTERED leg — sign-flips on the R63 disjoint panel and is a right-signed null on ATRZ disjoint. Its FULL-panel replications (q=0.0008/0.018) are exactly what contamination predicts when an effect is real in the shared episodes and absent in the new ones. The up/down dollar-volume anatomy is tier-local to the fast small/mid cohort it was registered on.
3. **The "young" leg reverses.** `A4_r252` on ATRZ disjoint shows MORE long-run gain in topped episodes (+0.021, CI excluding zero on the wrong side of the declaration). In the widest cohort the anatomy inverts: what marked tops among fast small-caps (less 252d run-up) marks the opposite among moderate-velocity names. Tier-local structure again — reported as an observed reversal, not a new registration (the declaration was one-sided).

## §4 The heat family is cross-tier structure

The exploratory set (31 features, two-sided within-family BH on FULL; printed unranked on DISJOINT) corroborates §3.1 from outside the confirmatory five. Separating on BOTH arms' disjoint panels: `A1_r21` (short-run heat), `A5_ext_ma50_atr21` (extension above the 50d), `A7_late_gain_share` (late-gain concentration), `E1f_xr63`/`E2f_xr21` (excess return vs the same-day cross-section) — plus `B4_newhigh63_rate21`/`B5_upday_rate21` on R63 and `A2_r63` on ATRZ. This is precisely phase-0's "wrong-sign ore body" (topped = younger/hotter/closer to highs), now surviving out-of-cohort on two independent tier definitions. Phase-1's anchor-matched re-registration charter inherits this as its motivating evidence: the family is real cross-tier structure unless the anchor-artifact explanation survives anchor-matched controls.

## §5 Anatomy vs detection — the ruler moved on one arm

E1b incremental AUC over the r126-only baseline, walk-forward (train past → test future), all paired increments printed:

| Panel | R63 day-level | R63 episode-level | ATRZ day-level | ATRZ episode-level |
|---|---|---|---|---|
| FULL | −0.011 [−0.024,+0.003] | −0.057 | **+0.041 [+0.036,+0.047]** | **+0.020 [+0.014,+0.027]** |
| DISJOINT | −0.021 [−0.050,+0.006] | +0.011 | **+0.011 [+0.003,+0.019]** | +0.005 [−0.004,+0.013] |

On R63 the phase-0 conclusion stands unchanged: no out-of-sample increment — anatomy, not detection. On ATRZ the walk-forward increment is positive with CIs excluding zero in three of four readings — the first such result in this program. Two honesty notes before anyone leans on it: (a) the M0 baseline is trailing-126 return, and the ATRZ bar is the one arm NOT defined on trailing return, so its baseline is structurally weakest there — part of this increment is the baseline getting worse, not the features getting better; (b) a positive AUC increment on a display-tier ruler licenses NOTHING: no probability, no timing, no gate. It is recorded as the strongest lead yet for the phase-1/gauntlet pipeline, where a promotion case would have to survive pre-registered gates it has not yet faced.

`B2_rsi14` ruler detail (fires = topped-typical heat, per-cell): R63 FULL median remaining upside +10.1% (fwd-63 excess −0.4% [−1.6,+1.4]); R63 DISJOINT +3.3% remaining, fwd-63 excess **−2.1% [−3.4,−0.1]** — the program's first negative-excess ruler cell; ATRZ FULL +8.0% (+0.2% [−0.3,+1.3]); ATRZ DISJOINT +4.1% (+0.1% [−0.5,+0.8]). One negative cell of four, with a CI that barely excludes zero — printed, not leaned on. The AVOID-tier reading stays modest: after topped-typical heat in a moderate-velocity name, forward excess has historically been flat-to-slightly-negative, and upside remaining at fire is small.

**Vintage-roster B2 read (post-hoc; `vintage_roster_b2_read` in both arm summaries, `post_hoc: true` with provenance).** Computed with the engine's own feature path after the confirmatory results were read, at the commissioning session's request — descriptive display-tier reporting, not a registered quantity. Fire thresholds are each arm's DISJOINT-panel ruler thresholds, read not recomputed (R63: RSI-14 ≥ 76.2; ATRZ: ≥ 73.1; both the 10% control-tail convention). As of 2026-07-02: R63 roster 56/295 at-or-beyond (19.0%), median 67.6 vs disjoint topped 68.1 / matched-control 65.3; ATRZ roster 143/848 (16.9%), median 63.4 vs topped 67.3 / control 63.1. The at-threshold lists sit in the summaries; the ATRZ list includes large caps (ABBV, ALL, CB, PANW, MRNA among them). The read is five weeks stale by construction and says nothing about any single name; it is the cohort-level "watch" context the confirmed leg supplies, pending the store refresh.

## §6 Instrument and gates

Engine byte-identical to main (`extended_mask` variants were declared and frozen pre-phase-0-results; `git diff origin/main -- engine/` empty). Harness gained plumbing only (`--w2-arm`), committed before any full-arm result. Per-name feature panels are EXT-definition-independent (pure rolling transforms; verified in code) and were shared with the phase-0 cache; every EXT-downstream artifact is arm-keyed through the identity-stamp hard-check (present-and-equal, now carrying `ext_variant`; a panel-only cache can never serve an arm's downstream artifacts, and no arm can read another arm's episodes — 27 new tests, family suite 131). Full-series-vs-prefix parity gate passed on both arms (worst |gap| 9.5e-15). Declared census quantities reproduced exactly. No deferral: both arms finished far inside the 12 h wall. The NASDAQ test-symbol disclosure and every other phase-0 data-plane caveat carry forward unchanged.

Mid-wave instrument note: after both arm summaries were first committed, main landed a fail-closed guard refusing local research reads of a stale `massive_stock_day` mirror (#5319 — the store-refresh workstream's first landing). The W2 harness threads that guard's explicit `--allow-stale` override, declaring the frozen 2026-07-02 vintage deliberate (same-tape comparability, prereg §2); the guard's banner prints the staleness loudly (26 completed sessions behind at run time). Both arms were then RE-RUN end-to-end on the merged instrument as a determinism check, and the committed summaries are those re-runs: every confirmatory cell reproduced the pre-merge values exactly (independently verified to 4 decimals on all five R63 disjoint legs; grades identical), so the #5319 threading is behaviorally inert for the frozen vintage. The `vintage_roster_b2_read` block (§5) was appended post-hoc to both summaries with its own provenance stamp.

## §7 Adjudication

1. **W2b (surface widening) is chartered with a stratified-library MANDATE.** §3.2 is direct evidence that thresholds baked on one tier are wrong on another (D3's anatomy does not travel; A4 reverses). Winner Health may widen to the R63/ATRZ tiers ONLY with per-tier libraries and thresholds, honest no-analog states across tiers, and B2-family legs counted within the same display-tier language. No cross-tier threshold reuse, ever.
2. **Phase-1 (anchor-matched inversion re-registration) inherits W2's evidence** — B2 confirmed cross-tier plus the §4 family — and its prereg should declare B2's disjoint baselines (+3.87/+3.92) as the anchor findings to beat or subsume.
3. **The ATRZ walk-forward increment goes to the gauntlet pipeline as a printed observation.** Any promotion attempt must carry its own preregistration; nothing in this report upgrades authority.
4. **Out-of-time replication remains the binding open question** for every W2 result, B2 included. The store refresh (in flight in a sibling session) is the unblocking event; the first post-refresh wave should re-read the vintage rosters and the exemplar census before anything else.

## §8 Execution log

- 2026-08-11 — prereg frozen pre-results (commit order on branch `claude/topa-w2-tier-widening`); harness plumbing committed pre-results; R63 run (1,065 s) and ATRZ run (2,669 s) on the frozen instrument; this report drafted from the two committed arm summaries; G0.5 adversarial review commissioned before presentation, corrections binding.
