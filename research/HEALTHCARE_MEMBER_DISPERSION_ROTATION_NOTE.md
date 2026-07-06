# Healthcare Member-Dispersion Rotation Note

**Status:** operator-tape follow-up, hypothesis-generating only.
**Tape row:** `tape::2026-07-06T02-50-32`.
**Snapshot used:** local generated artifacts as of 2026-07-02, with XLV holdings as of 2026-07-01.

## 1. The observation

The operator sees a defensive healthcare rotation while tech, semis, and memory unwind. The confusing part is not the direction of the flow; it is the construction mismatch:

- `Health Care (Equal-Weight)` appears in the us_stocks action board's buy-zone narrative basket group.
- `XLV / Health Care` appears at the sector-ETF cycle layer as extended or topping: no fresh cross, RSI 69, Stoch 98.
- Healthcare sub-baskets and members are not synchronized. Some leaders have already rerated, while washed-out names like REGN, VEEV, and MCK may still be closer to clean second-wave entries.

That contradiction is real, not a display bug. It is the difference between cap-weighted sector exposure, equal-weight sector breadth, theme/subsector membership, and member-level entry timing.

## 2. Local evidence snapshot

From `site/basketdata/baskets.json`, `us_sector_health` was up 11.7% over 20 days, with 86% of its 59 members positive. The median member was up 11.0%, but the top 10 members averaged +28.3% while the bottom 10 averaged -1.5%. This is broad participation with very large internal dispersion.

Selected named members:

| ticker | 20d return | YTD return | interpretation |
|---|---:|---:|---|
| MRNA | +62.6% | +170.5% | extreme leader; narrative/biotech impulse already repriced |
| UNH | +13.5% | +30.6% | large-cap quality/insurer leader, already repaired |
| LLY | +12.5% | +13.3% | cap-weight anchor; helps XLV mechanically |
| VEEV | +7.8% | -13.7% | second-wave candidate, still washed out |
| ELV | +7.2% | +20.4% | insurer participation, less explosive |
| MCK | +6.3% | -4.1% | defensive distributor, still not fully repaired |
| REGN | +5.7% | -15.0% | clean laggard profile if a turn confirms |

From `data/sector_holdings/XLV.parquet`, XLV's latest top 10 holdings carry 61.35% of ETF weight. LLY alone is 16.34%, JNJ 10.59%, ABBV 7.69%, and UNH 6.71%. So XLV can look extended because a handful of mega-cap anchors ran, even while equal-weight and laggard repair still have work to do.

## 3. First-principles read

A sector is not a single object. It is at least four objects:

1. A cap-weighted ETF that reflects where passive dollars and benchmark allocators go first.
2. An equal-weight basket that measures how many members are participating.
3. A set of theme/subsector baskets that isolate why money is flowing.
4. A member-level opportunity set where actual entries, stops, and idiosyncratic narratives live.

The practical market mechanism is sequential:

1. Institutions first buy liquid anchors and obvious winners. In healthcare, this can be LLY, UNH, JNJ/ABBV, or narrative biotech leaders.
2. The ETF confirms because the heavy weights move.
3. Equal-weight breadth starts improving as managers broaden from safest/liquid names into sector members with better entry location.
4. The cleanest laggards begin catch-up if the rotation is healthy.
5. Exits usually show up first as leader exhaustion, then breadth deterioration, then laggard failure. If laggards never catch up, the rotation may already be late.

The edge is not "buy healthcare because XLV is up." The edge is detecting which phase of the sequence we are in and expressing it through the member cohort with the best asymmetry.

## 4. What this means for current signals

The same healthcare complex can honestly emit both BUY and TOPPING:

- BUY: equal-weight/narrative lens says money is broadening into healthcare.
- TOPPING/EXTENDED: XLV sector-cycle lens says the cap-weighted ETF is late and risky to chase.
- BUYABLE MEMBER: washed-out members that are now turning may have better R than the ETF.
- AVOID MEMBER: leaders that created the signal may be too extended for new money.

So the system should stop trying to collapse these into one verdict. It should display and score them as construction-aware layers.

## 5. Implementation opportunities

### A. Basket Construction Divergence

Add a per-basket artifact that decomposes every basket into:

- `cap_weight_phase`: ETF/top-10-weighted cycle state where holdings exist.
- `equal_weight_phase`: current basket-level state.
- `median_member_phase`: median member entry state.
- `leader_phase`: top alpha/top cap/top 20d return cohort.
- `laggard_phase`: washed-out cohort with fresh turn potential.
- `construction_divergence`: cap-weighted state minus equal-weight/member state.

The key alert is: cap-weighted ETF extended while equal-weight breadth and washed-out members are improving. That is not a buy-the-ETF signal; it is a member-routing signal.

### B. Leadership Ladder

Classify members inside a rotating basket:

- Anchor leaders: large-cap, high weight, liquid, already moving.
- Narrative accelerators: not necessarily mega-cap, but with a strong rerating story.
- Clean laggards: washed out, not structurally broken, now entering a cycle turn.
- Damaged laggards: cheap/washed out but failing confirmation.

Existing hooks can seed this: `alpha`, `sector_rank`, `rs_sector_quartile`, `washout_active`, `entry_signal`, `sector_pulse`, liquidity tier, GEX/vol squeeze, and subsector membership.

### C. Sector Entry Router

For Neural Web and Oracle, split sector entries into three routes:

- `ETF route`: only when cap-weighted ETF is early, not extended.
- `leader route`: when the sector is emerging but leadership is not yet crowded.
- `catch_up route`: when ETF/leader confirmation exists but laggards are still in repair.

The current healthcare case is mostly a catch-up-routing problem, not a fresh ETF-entry problem.

### D. Exit Sequencing Model

Build exit signals around the order of deterioration:

- leaders stop making new highs or break support;
- breadth stops expanding;
- laggards fail to confirm after leaders extend;
- cap-weighted ETF loses trend;
- defensive inflows reverse back toward prior donor sectors.

This lets the system avoid the common mistake of selling laggard catch-up just because the ETF is extended, while also avoiding the opposite mistake of buying damaged laggards after leader exhaustion has already started.

### E. UI Reconciliation

On `us_stocks.html`, when the same sector appears in different states, show a compact construction note:

`Health Care: XLV extended; equal-weight breadth improving; member catch-up active.`

This would make the current two-healthcare display useful rather than confusing. It should not hide the conflict; it should explain what layer each conflict belongs to.

## 6. Backtest families to register

1. **Leader-first breadth prediction.** When top-cap or top-alpha members launch first, does equal-weight breadth improve over the next 5-21 sessions?
2. **ETF-extended laggard catch-up.** If cap-weight ETF is extended but equal-weight breadth is rising, do washed-out members with fresh turns outperform random same-sector members?
3. **Second-wave quality filter.** Among laggards, do quality/revisions/liquidity/narrative tags separate clean catch-up from value traps?
4. **Exit order study.** Does leader exhaustion precede equal-weight deterioration, and does laggard failure predict the end of the sector rotation?
5. **Construction-divergence classifier.** Compare cap-weight, equal-weight, and member-median states as predictors of next 21d member opportunity quality.

Each family should use ablations: random members, same member triggers without sector condition, same sector condition without member trigger, and timing-matched placebo windows.

## 7. Neural Web / Oracle integration

Neural Web should ingest construction divergence as context first, not as authority:

- `basket_construction_divergence`
- `leader_lag_spread`
- `cap_weight_concentration`
- `catchup_candidate_count`
- `leader_exhaustion_rate`
- `breadth_confirmation_rate`

Oracle should use it as a member-routing condition for the existing member-transmission lane. The likely grammar is:

`sector_condition x member_trigger x quality/narrative filter x exit_sequence`

For this tape row, the candidate mechanism is:

`healthcare inflow + cap-weight confirmation + laggard washout repair -> second-wave member entries`

The system should not promote this directly. It should convert the tape note into registered specs, screen them, and keep the result display-only until evidence accrues.

## 8. Immediate practical takeaway

Treat XLV as the confirmation layer, not necessarily the entry vehicle. If XLV is extended because LLY/UNH/JNJ/ABBV already carried the move, the higher-quality work is inside the member list:

- avoid chasing the exhausted leaders unless they reset;
- prioritize washed-out members that are turning with clean invalidation;
- require breadth to keep expanding;
- cut the thesis if leaders fail and laggards do not catch up.

The insight is system-level: sector-level signals should emit both a direction and an expression route. "Healthcare up" is not enough; the actionable question is whether to buy the ETF, buy leaders, buy second-wave laggards, hold, or exit.

---

# Adjudication appendix (Fable, 2026-07-06)

Sections 1–8 above are the external (ChatGPT) memo, landed verbatim. Everything below is the house verdict. Tape row `tape::2026-07-06T02-50-32` is committed in `data/oracle/operator_tape.jsonl` alongside this doc (it previously existed only in an ephemeral Codex worktree); its `converted` field flips when the R-1 registration below lands.

## 9. Verdict map (Opus adversarial review + Fable rulings)

**Headline: ~80% of the proposed engine surface is already shipped, already killed, or already ruled DON'T-TEST. Nothing in §5 is built as new engine surface. Two narrow threads survive, both risk-side.**

| Memo section | Ruling | Grounds |
|---|---|---|
| §5A Construction Divergence, §5E UI note, §4 dual-verdict | **SHIPPED** — close | act-now board ruling #1513 (merged the day before the tape row): EW-vs-cap disagreement renders as the 🧩 chip, ruled "information, never collapsed"; EW `us_sector_*` baskets return as `sector_overlay`, never board rows |
| §5B Leadership Ladder (entry legs) | **DEAD BY ADJACENCY** — close | sector_pulse W6 kill-test #1185: leader-momentum tier INVERTED (−0.35pp, t −2.38 = chase penalty); W9-B tailwind DEMOTE (trailing 20d-rel carries no forward info); W9-A washout conditioning = SAFETY_ONLY |
| §5C Sector Entry Router ("ETF-early" route) | **BANNED** — close | rotation-cycle-confluence ruling 2026-07-05 (W0.4 keystone, 8,344 PIT stamps: cycle position predicts nothing at any decile/horizon); `ladder_calibration.json`: FRESH BUY is the *worst*-returning state |
| §6 families 1/2/3/5 | **CLOSED** | fam-1 = the killed heating leg in a wrapper; fam-2/3 = W9-A already answered (safety, not return); fam-5 collides with `baskets_calibration.json` buy-side triple null |
| §2 dispersion table | **NOT EVIDENCE** | top-10 vs bottom-10 spread inside an up-11.7% basket is a ranking tautology — no null, no placebo; n≈1 sector-week |
| §5D exit sequencing / §6 fam-4 | **SALVAGED** → R-2a / R-2b below | the *time-ordering* claim (leader exhaustion leads breadth deterioration) is genuinely distinct from the dead state→return family, and has a validated benchmark to beat (reduce gate, t_HAC −9.65) |
| §7 Oracle grammar | **RESTRICTED, not banned** | Fable narrowing of the Opus review: `sector_condition × member_trigger` is banned only when the sector term is cycle position (W0.4). With the *armed window* as the sector term, the identical grammar is the repo's own live positive (oracle W2 #1509: WR21 65.2% vs 53.6%, p=.002, BH-pass, display-only) → R-3 strata |
| §8 trading posture | **SOUND, ALREADY DE-FACTO** | needs no code to be true |

**The reframe that governs everything below:** every edge that has ever survived a gauntlet in this repo is risk-side (reduce gate, broken timer, SHAKEN, phase-keyed DD, washout-as-safety). Construction divergence therefore gets tested as a **modulator of the validated reduce side** — a candidate de-escalation key, the one integration class LLM/context layers may legally consume — never as a buy engine.

## 10. Additional assessment of the original operator text

Re-reading the operator's raw anecdote (not the ChatGPT memo) surfaces material the memo dropped or under-specified:

- **R-2a (NEW — makes exit-ordering testable NOW).** The operator's mechanism ("leaders run first… once winners are up a lot, laggards start running") implies the cap-weighted construction should *lead* the equal-weight construction on the deterioration side (cap anchors break first). That is a pure two-series lead-lag between SPDR sectors and their Invesco equal-weight counterparts (RYH/RYT/RYE/RYF/RYU/RGI/RHS/RTM/RCD, inceptions ~2006) — no member data, no survivorship problem, ~20y of history. The memo's member-level version (R-2b) is blocked: verified 2026-07-06 that `data/sector_holdings/*.parquet` is **latest-only** (no date column; `holdings_runs.parquet` is a run log) — so leader cohorts cannot be defined retroactively by weight.
- **R-4 (NEW — donor–recipient coupling).** Operator: flows *out of* tech *into* healthcare; memo §5D's last leg ("defensive inflows reverse toward prior donor sectors") is the only leg with no house analog. Testable on the Rotation Time Machine tape (1998→): during a recipient sector's armed window, does the *donor* sector's rs-repair onset predict the recipient rotation's end better than recipient-only deterioration? Exit-timing framing, oracle home. Judge-first (power check) before any build.
- **Quality-factor covariate (fold-in, not standalone).** Operator: "maybe it's a fund preference based on quality factor." Registered as an optional covariate inside R-1 (does within-sector quality-spread state sharpen the divergence split?), inheriting the factor-intelligence panel. Not its own family.
- **Rejected from the original text:** narrative-accelerator cohort (MRNA cancer-vaccine rerating) — narrative momentum is a validated rank-IC≈0 null, trend-gate ruling stands; TGA/Fed/mag-7-FCF macro framing — risk-radar territory, no new collector or signal warranted.
- **Infra gap worth closing regardless (W0b):** a dated PIT snapshot archiver for `data/sector_holdings/` (append-mode, off render path). Cheap, and it un-blocks R-2b in ~1 year.

## 11. Phased plan

**W0 — land + infra (2026-07-06).**
- W0a: this doc + tape row (this PR).
- W0b (sonnet builder): EW sector-ETF price collection (Invesco equal-weight family) into `data/yahoo/` via the existing collector config + dated PIT archiver for sector holdings. No signal surface. Inception dates printed per ETF; XLRE/XLC later starts acknowledged.

**W1 — R-1: construction-divergence as reduce-gate de-escalation key.**
Pre-registration draft (to be red-teamed by Opus BEFORE any harness run; spec locks before results exist):
- **H-R1:** reduce-gate onsets on the cap-weighted construction where the equal-weight counterpart is NOT in a reduce state ("divergent" events) show (a) shallower forward max-drawdown and (b) higher whipsaw rate than events where EW confirms ("confirmed" events). Direction of use: divergence ⇒ *de-escalate* gate severity as context; never suppress the gate, never a buy claim.
- **Universe/window:** 9–11 SPDR sectors × EW counterparts, 2006-07→ (per-pair inception).
- **Events:** shipped reduce-gate definition recomputed as-is on cap series — no re-tuning.
- **Primary condition:** EW construction's own gate state at cap-onset. Secondary (printed, no verdict): EW/cap 20d ratio slope sign.
- **Outcomes:** fwd max-DD and whipsaw (gate reversal within 15 sessions without a −5% leg) at 21/63d; fwd return printed but carries NO verdict (buy claims stay dead).
- **Stats:** divergent-vs-confirmed contrast, cluster bootstrap (cluster = sector-event), HAC where applicable, BH across {2 outcomes × 2 horizons}, effective-n printed, decade splits + post-2018 decay check (W0.4 precedent).
- **Ablations:** condition-label shuffle within sector; placebo condition = a *different* sector's EW state; sector-decade-matched random event dates.
- **Verdict gates:** CONFIRMED only if DD separation passes BH and is sign-stable across splits → `construction_divergence` ships as a calibrated de-escalation key (🧩 chip grade + NW context key, zero rank path). Otherwise the null prints here and the key never ships.
- **Trial family:** `construction_divergence`.

**W2 — R-2a: construction-pair deterioration lead-lag.** Onset-time deltas of the validated deterioration states between cap and EW constructions per sector; does the leading construction's fire improve exits on the lagging one vs acting on the lagging one alone (benchmark = incumbent reduce gate)? Pre-registered after R-1 verdict (its design inherits R-1's event tooling). Only proceeds if R-1 shows the divergence axis carries *any* conditional information.

**W3 — R-3 + R-4.**
- R-3 (descriptive now, verdict later): `washout_active` strata added to oracle W2's armed-window member lane — pre-registered strata on an already-positive display-only result; prior from W9-A says expect a safety separation, not a return one; no verdict before effective-n grows past ~31 windows (≈Q4-2026).
- R-4 (judge-first): Opus power/feasibility memo on donor–recipient coupling over the TM tape before any harness is authorized.

**Dormant:** R-2b (member-level leader exhaustion) until the W0b holdings archive matures (~2027-07).

**Routing:** Fable (main loop) adjudicates specs and verdicts; Opus red-teams registrations and reviews results; Sonnet builds harnesses and collectors; nothing spawns at frontier tier.

---

# §12. R-1 registration — red-team record + LOCKED spec (2026-07-06)

**Red-team verdict on the §11-W1 draft (Opus, 2026-07-06): DO-NOT-LOCK.** Three blockers and four majors, all folded below. The draft is superseded by this section; it stays above as the audit trail.

- **BLOCKER-1 (domain transfer):** the incumbent validated reduce gate is NOT a price gate — it is `engine.theme_scoring._label ∈ {fading, deteriorating}` computed on a *relative-strength* series (`lvl/SPY`) plus panel breadth, via `run_proxy` in `scripts/calibrate_baskets.py` (`universe: proxy_spdr_sectors`, `car_metric: fwd_dd_21d`). "Recompute on cap series as-is" was undefined. Fixed by pinning events to the exact implementation at a frozen SHA.
- **BLOCKER-2 (no EW PIT data):** the Invesco EW family was absent from `data/yahoo/` at review time (W0b #1529 landed the collectors the same day; first parquets arrive with the next nightly collect). The hindsight-curated `us_sector_*` GICS baskets (`MEMBER_ADDED 2023-05-09`) are **BANNED** as the EW condition source.
- **BLOCKER-3 (power):** ~390 de-overlapped onsets 2006→, with a badly imbalanced divergent/confirmed split (RSP-proxy estimate ~87/13). Power floor added; no verdict on <40-event cohorts.
- **MAJOR-1 (direction):** the operator's own mechanism (leaders break first) means cap-onset-while-EW-fine is the *validated early exit* — the de-escalation candidate carries an explicit null prior; the reverse leg (EW cracks first under a still-firm cap) is escalation-shaped and stays descriptive (house law: context layers cannot originate escalations).
- **MAJOR-2 (laundered stay-long):** mean-DD-shallower is not a legal de-escalation gate; tail-safety conditions added (p10/p25 DD + P(DD<−8%) no-worse), since a missed exit costs more than a tolerated whipsaw.
- **MAJOR-3 (whipsaw magic numbers):** −5%/15-session whipsaw had no validated source and contradicted the gate's own `DD_RISK = −8%`; demoted to descriptive-only.
- **MAJOR-4 (systemic confound):** "confirmed" events concentrate in market-wide stress (divergent-rate ~96% calm vs ~77% stressed, RSP proxy) — naive contrasts would measure systemic-vs-idiosyncratic selloff type. Calendar-block bootstrap + SPY-stress stratification added; the key cannot ship on the pooled contrast alone.
- MINORs: condition timing pinned to close `t` modulating `t+1+` only; BH family = DD verdict tests only; dividend-adjusted `close` on both legs; per-pair inception truncation.

## LOCKED registration (status: DESCRIPTIVE/ACCRUAL — not verdict-eligible)

**Trial family:** `construction_divergence`.

**H-R1 (dual-direction, verdict potential on one leg only).** On the SPDR-vs-SPY relative-strength reduce gate (`engine.theme_scoring._label ∈ {fading, deteriorating}` recomputed via `run_proxy`'s PIT path; benchmark SPY; implementation frozen at commit `9a31b78ad0` of `scripts/calibrate_baskets.py` + `engine/theme_scoring.py`; no re-tuning), classify each de-overlapped onset by the paired Invesco EW ETF's own recomputed gate state (rs = EW/SPY, breadth = EW-ETF panel) at the same close `t`:
- **cap-leads-EW ("divergent"):** cap onset, EW not reducing. *Prior: the validated early exit — expect NO de-escalation.* Sole de-escalation candidate.
- **cap-lags-EW:** EW reduce-onset, cap not reducing. Descriptive escalation context only; never a key.
- **confirmed:** both reducing.

**Universe (verified tickers + inceptions, #1529):** XLK/RSPT, XLE/RSPG, XLF/RSPF, XLV/RSPH, XLY/RSPD, XLP/RSPS, XLU/RSPU, XLB/RSPM (all EW 2006-11-07→); XLI/RGI (2009-01-02→; RSPI not served by Yahoo); XLC/RSPC (2018-11-07→); XLRE/RSPR (2015-08-14→). Per-pair window = `max(cap_inception, EW_inception)`; XLC/XLRE pairs excluded from pre-2018 decade cells. Both legs dividend-adjusted `close`.

**Data precondition:** runs only once the EW parquets exist in `data/yahoo/` with genuine (non-backfilled) history. `us_sector_*` baskets banned as condition source.

**Events:** first `_label ∈ {fading, deteriorating}` after ≥15 trading days out of state. Condition evaluated at close `t`; de-escalation modulates `t+1+` actions only; audit prints max feature index ≤ `t`.

**Covariate (mandatory):** SPY-stress flag = SPY below its own 200d MA. Secondary (descriptive): EW/cap 20d ratio slope sign.

**Outcomes:** forward max absolute DD at 21/63d (the only verdict-bearing outcome). Whipsaw (leg = `DD_RISK` −8%, reversal grid {10,15,21} sessions) and fwd return: descriptive, excluded from BH.

**Stats:** divergent-vs-confirmed DD contrast; calendar-time block bootstrap (onsets co-firing within 7 trading days collapse to one block; print `bootstrap_effective_t`, raw n, and the divergent/confirmed × stress/calm 2×2 counts); BH family = {DD × 2 horizons}; decade splits + post-2018 decay check.

**Power floor:** smaller cohort ≥40 de-overlapped onsets across ≥2 decades on genuine EW history, else `INSUFFICIENT_POWER → descriptive` prints and no verdict exists.

**Ablations:** condition-label shuffle within sector; placebo = a different sector's EW state; sector-decade-matched random event dates.

**Verdict gates (all required for CONFIRMED):** (i) BH-pass on DD; (ii) sign-stable across decade splits AND within the SPY-stress stratum, not only pooled; (iii) tail-safety — divergent p10 AND p25 fwd max-DD no worse than confirmed (one-sided block-bootstrap CI) and `P(fwd_DD21<−8%)` no higher; (iv) power floor met. Failure modes print as `TAIL_UNSAFE` / `SYSTEMIC_CONFOUND` / `INSUFFICIENT_POWER`. On CONFIRMED: `construction_divergence` ships as a de-escalation-only context key (🧩 chip severity downgrade + NW context key; zero rank path, zero hold/buy path; never suppresses the gate firing).

## Program status ledger

- W0a doc+tape row: #1527 MERGED. W0b infra (EW collectors + PIT holdings archiver): #1529 MERGED; first EW parquets + first `history.parquet` rows arrive with the next nightly collect.
- R-1: LOCKED as descriptive/accrual (this section). Descriptive harness authorized; verdict deferred to data + power preconditions.
- R-2a: design inherits R-1 event tooling; pre-register only after R-1 descriptive tables exist.
- R-3: upgraded home — oracle W2 member-transmission lane was formally registered and CONFIRMED (display-with-edge, temporal holdout) in #1533 the same day; washout strata graft onto `scripts/oracle_member_transmission_w2.py`.
- R-4: judge-first Opus power memo before any build. R-2b: dormant until the #1529 holdings archive matures (~2027-07).
