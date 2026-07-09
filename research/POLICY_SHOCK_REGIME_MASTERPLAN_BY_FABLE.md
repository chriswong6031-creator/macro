# Policy-Shock Regime Program — masterplan by Fable

Status: **BUILD COMPLETE** (chartered, built, reviewed, integration-audited — all on 2026-07-09)
Author: Fable main-loop session, 2026-07-09
Adjudication substrate: 5-lane census + 2 independent Opus critics (workflow `wf_c16c451d-3f8`),
`docs/ACTIVE_BUILD_MAP.md` (2026-07-09 gen), `research/DO_NOT_REBUILD.md`, `config/ruling_graph.yml` queries.

---

## §1 Problem + diagnosis of record

Operator problem (2026-07-08/09): the administration re-struck Iran → oil spiked → inflation
scare → rate-cut odds fell → flows reversed violently from defensives/staples/healthcare into
semis/memory within one session, after semis had taken a 20–30% drawdown that our engines were
positioned around. The rotation engine (60d momentum ranks), pick engine (12-1 residual
momentum), and regime quad (7d hysteresis) cannot react inside a day; the operator asks how to
become alert to this event class and how to configure the system to survive/trade it.

**Findings of record (census-verified, 2026-07-09):**

1. **The information existed in-house.** `data/policy/intel.json` (as_of 2026-06-24) held the
   thesis: sequenced optionality campaign, "Iran haven bid", post-midterm easing pivot, and an
   explicit catalyst warning that the crowded, leveraged semis/memory complex could flush. 39
   open falsifiable predictions attached.
2. **The deterministic shock read printed the sequence nightly.**
   `data/regime/market_drivers_log.parquet`: `oil_shock` (collapsing) 06-17/18 →
   `fed_repricing` (hawkish) 06-22/23 → `ai_semis` unwind 06-25→07-08, peaking HIGH
   confidence / strength 2.81 on 2026-07-07 — the eve of the reversal.
3. **Nothing consumed any of it, and no uncertainty-widening knob exists.** All relevant organs
   are display-tier, nightly, coincident. Ranks either hold or flip; nothing can say "I am
   stale, discount me." The 30-min RTH intraday fastpath refreshes market_state/regime
   `latest.json` but not drivers, ranks, or picks.

**Diagnosis:** the failure was cadence + confidence architecture, not information. The fix is
not a faster directional engine (un-buildable and forbidden — see PS-R1); it is a
conditions-arming layer plus a de-escalation protocol that removes stale confidence on shock
days, and a T+1 confirmation lens that answers chase-vs-fade honestly.

## §2 Identification law (the epistemic core)

No free observable separates "the administration deliberately spikes oil to redirect flows"
from "geopolitical risk repriced and momentum chased." The intent claim is unfalsifiable, and
for trading it is irrelevant: the actionable observables (favored-complex drawdown depth, an
open lever with a technical curl, coherent cross-asset repricing, jawboning cadence) are
identical under both hypotheses. The distinction matters only for predicting the actor's
timing — which is astrology against a discretionary adversarial actor and is FORBIDDEN to
build (PS-R1). Everything in this program is therefore a **conditions read** plus
**de-escalation plumbing**, never a direction or a timing forecast.

## §3 Rulings (PS-R1..R9)

| ID | Ruling |
|---|---|
| PS-R1 | **Identification law.** All program surfaces frame outputs as reversal-likelihood CONDITIONS. FORBIDDEN: administration-timing predictors, policy-intent classifiers, LLM-emitted geopolitical re-escalation probabilities. Appended to DO_NOT_REBUILD §1 in this PR. |
| PS-R2 | **Canonical shock read.** `engine/market_drivers.snapshot()` remains the canonical shock read (TI-R1). `repricing_coherence` (W1-A) is a DERIVED reading off it; no parallel classifier may be built. |
| PS-R3 | **De-escalation only.** Consumers of program keys may only REMOVE confidence: stale-marking, band-widening, fresh-entry caution. Originating direction, reordering ranks, or touching sizing is forbidden (A7 ORIGINATE ban; BTC midterm-blackout audit D1–D5). |
| PS-R4 | **Geopolitical legs stay unsigned.** Narrative-only shock legs (Iran/oil re-escalation, tariffs, regulatory) ship as unsigned qualitative display rows; no LLM may classify them into calibrated keys (restates TI-R1). |
| PS-R5 | **D5 folded into D1.** The oil/Iran lever is one row of the policy-lever card's lever table; no standalone per-lever organ. |
| PS-R6 | **Doctrine is text-only.** The D4 short-side doctrine ships as display copy with zero code authority; any sizing version is the laundered-override pattern (BTC D1–D5) and directional shorting (L1 is AVOID-not-SHORT). |
| PS-R7 | **Cadence law.** Intraday passes write `site/` artifacts only; nightly remains the sole advancer of `data/` ledgers (restates house law for all program artifacts). |
| PS-R8 | **n-honesty.** No directional gauntlet on any program key before ≥8 distinct shock episodes exist in the firings ledger. Any future study carries DT-R14 calendar-time control and DT-R16 era awareness. Display/shadow accrual is unrestricted (house epistemics: gauntlet = promotion gate, not build gate). |
| PS-R9 | **v1 threshold freeze.** Trigger thresholds below are descriptively calibrated on the Jun–Jul 2026 episodes, frozen as v1, and forward-graded. Recalibration requires a logged amendment to this file. This is disclosed, not hidden: v1 is a display/shadow tier construct, not a promoted signal. |

## §4 Wave map + build contracts

Six PRs. W1 lanes are independent; W2 lanes depend on W1 merges as noted. Every PR: branch off
fresh `origin/main`, worktree-isolated, local pytest gate, Opus review before merge, same-day
squash-merge.

### W1-A (PR-2) — `repricing_coherence` derived key + intraday drivers pass

Producer: `engine/market_drivers.py`. New pure function computing, from today's classify_day
output + `market_drivers_log.parquet` history:

```
repricing_coherence = {
  score: 0-100,           # sum of components
  state: QUIET|ELEVATED|SHOCK,   # <40 / 40-69 / >=70
  components: {
    driver_flip: 0|30,        # primary != previous print AND min(strength_today, strength_prev) >= 1.0
    strength_extreme: 0|25,   # strength >= p95 of trailing 252 log rows (fallback >=2.0 if <40 rows)
    absorption_spike: 0|20,   # absorption_pctile >= 0.90
    repricing_breadth: 0|25,  # >=3 driver families with |score z| >= 1.5 on the day
  },
  note: "derived reading of market_drivers — de-escalation/display consumer only"
}
```

- Nightly: attach block to `snapshot()` output; extend `append_log()` with `coherence_score`,
  `coherence_state` columns (keep-first per date unchanged).
- Intraday: add a drivers step to the existing 30-min RTH fastpath writing a **site/-side JSON
  only** (PS-R7). Runtime budget: added step <60s on the render box; if `assemble_frame()` is
  too heavy intraday, ship nightly-only and leave a flagged TODO (honest fallback) — do not
  cache-hack under time pressure.
- Synapse/DAG registration for the new key per repo conformance guards.
- Tests: component unit tests on synthetic frames + a regression asserting 2026-07-07/08 rows
  in the committed log yield ELEVATED-or-SHOCK.

### W1-B (PR-3) — commodity technical arming (stoch + basing/coil)

Producer: `engine/commodity_signals.py` (+ `commodity_mtf.py` where natural). Per-asset block:

```
technical_arming = {
  stoch_k, stoch_d,          # 14-3-3 full stochastic, 0-100
  stoch_curl: bool,          # %K crosses above %D with %K < 30
  macd_curl: bool,           # MACD hist rising 3 consecutive bars while below zero
  basing: bool,              # close within 8% of 60d low for >=10 sessions AND 120d drawdown <= -15%
  days_in_base: int,
  armed: bool,               # basing AND (stoch_curl OR macd_curl)
}
```

Deterministic, display-tier, EN/ZH chip on the commodities surface. Parameters are v1-frozen
(PS-R9); print them in the artifact for transparency. `engine/coiled.py` is equity-only —
adapt logic, do not import equity assumptions blindly (different vol/gap structure).

**Amendment PS-A1 (2026-07-09, logged per PS-R9):** Opus review of PR #2007 demonstrated v1 `basing` arms on falling knives (proximity-to-trailing-low is satisfied by an ongoing decline; 15.5% false-arm rate on noisy monotone-decline seeds) and `macd_curl` can fire on float jitter of near-constant histograms. v1.1 adds a flatness gate (`base_flat_max_abs_return`, default 0.06 over `min(days_in_base, 4 × base_min_days)` sessions) and a scale-invariant minimum-rise epsilon on the MACD curl (`macd_rise_min_frac`, default 0.02, with a price-commensurate absolute floor). Reviewer-identified construct fix, applied before first consumer (W2-F) ships.

### W1-C (PR-4) — T+1 flip-confirmation lens (D6)

Producer: new `engine/flip_confirmation.py` + nightly build step.

- Flip detection: 1-day return spread between defensive composite (mean XLP/XLU/XLV) and
  offense composite (mean SMH/XLK), |spread z| >= 2.5 vs trailing 252d.
- T+1 attribution: `{spread_persistence (sign of next-day spread), breadth_follow_through,
  absorption_delta, leadership_continuity}` → verdict `CONFIRMED | FADED | MIXED`. Descriptive
  vocabulary only — the verdict describes what the tape did, it does not recommend.
- Ledger: nightly append-only event ledger (`data/flip_confirmation/events.jsonl`, keep-first
  per event date); qledger claim per event (family `flip_confirmation.v1`), graded at 5d/21d:
  did the T+1 verdict align with the subsequent spread direction. Forward accrual only.
- Display block near the market_drivers card on the US market-state surface, EN/ZH.

**Amendment PS-A2 (2026-07-09, logged per PS-R9):** Opus review of PR #2008 found (a) the v1 build backfilled the events ledger + qledger from 2024 and re-backfilled nightly with ungradeable SNAPSHOT_DATE claims, contradicting forward-only accrual — fixed: ship-date cutoff 2026-07-09 on all data/ writes, 2024→ scan is site-artifact descriptive only, forward claims registered gradeable at 5d/21d; (b) the CONFIRMED/FADED/MIXED taxonomy was degenerate (MIXED unreachable) — fixed: v1.1 verdict rule CONFIRMED = same-sign AND |t1_z| >= 0.5, MIXED = same-sign AND |t1_z| < 0.5, FADED = opposite sign. Minor: event-day z windows are trailing-inclusive of the current bar (conservative, no look-ahead; event set identical when excluded) — documented, not changed. Round-2 (same day): claims re-registered as one 21d claim per CONFIRMED/FADED event on the priceable XLP-vs-XLK proxy pair (composite spread not directly priceable by the grader; true composite is EW(XLP,XLU,XLV) − EW(SMH,XLK)); MIXED abstains (weak follow-through makes no directional call); two-row-per-event design (v1) removed to avoid double-counting (chassis grades 21d claim at 5d + 21d automatically via in_scope_horizons).

### W1-D (PR-5) — D4 doctrine copy + policy staleness + desk cadence

- Port the doctrine text from §7 VERBATIM (EN/ZH) onto the Neural Web doctrine surface
  (`committee.html` family — respect template↔site pairing law; run
  `python -m scripts.check_template_site_sync --fix` if a paired asset is touched).
- Staleness chip on the policy-intent/Fed-Policy-Watch surface: show `as_of` age of
  `data/policy/intel.json`; amber >7d, red >14d.
- Cadence: `policy_intent_desk` default `interval_days` 7→3 (change the `_cfg()` base default;
  note in PR body that the desk stays default-off without `DEEPSEEK_API_KEY` — ops decision).
- No translated text in `title=` attributes (CI guard).

### W2-E (PR-6) — shock de-escalation protocol (D3) — BLOCKED BY W1-A

Producer: new `engine/shock_deescalation.py` consuming `repricing_coherence`.

- Trigger (frozen v1, PS-R9): `state == SHOCK`, OR two consecutive prints `ELEVATED` with
  `driver_flip` set.
- Emissions: `data/reflexes/shock_deescalation/firings.jsonl` (nightly-only writer, keep-first
  per date) + site-side `shock_state = {active, score, since, expires (t+3 sessions), reason}`.
- Consumers (all display de-escalation, PS-R3): (a) subsector-rotation / sector-rank surfaces
  get a "SHOCK — ranks computed on pre-shock data, discount" banner while active; (b) US
  action-board fresh-entry rows get a caution chip (no reordering, no removal); (c) Oracle
  panel staleness note. Nothing reorders, nothing sizes.
- Reflex registration in `config/reflexes.yml` (tier `shadow`, `graded: true`, own
  `firings_jsonl` + `claim_family: reflex.shock_deescalation`) following the existing schema —
  study `factor_deescalation_shadow` and `whitehouse_alert` entries; NEVER write to another
  reflex's ledger (single-writer contracts are sacred).
- Would-have-fired: descriptive backscan over `market_drivers_log.parquet` (2026-06→) shipped
  as a report section in the artifact — labeled descriptive; the ledger itself starts at ship
  date (PS-R7 forward-only).

### W2-F (PR-7) — policy-lever ARMED/QUIET card (D1, folds D5) — BLOCKED BY W1-B

Producer: new nightly builder (standalone `scripts/build_policy_lever.py` or folded into the
market-state build — builder's call, declared in DAG) → `site/policy_lever.json` + card on the
US market-state surface, EN/ZH.

```
policy_lever = {
  favored_complex: { basket: [SMH, SOXX], drawdown_pct, drawdown_z, note },
  jawboning: { n_7d, n_30d, last_alert_ts, last_alert_summary },   # READ-ONLY from data/whitehouse/alerts.jsonl
  calendar: { days_to_midterm, context_note },                     # display context; election-cycle is context-only by prior ruling
  levers: [
    { name: "Iran / oil", asset: "CL=F", arming: <W1-B block>, watch: <unsigned qualitative text> },
    { name: "China / tariffs", arming: null, watch: <unsigned qualitative text> },
  ],
  state: QUIET | ELEVATED | ARMED,
  framing: "Conditions under which violent reversals are more likely — not intent, not timing."
}
```

- ARMED rule (frozen v1): `favored_complex.drawdown_pct <= -15%` AND any `lever.arming.armed`
  → ARMED; exactly one of the two → ELEVATED; else QUIET.
- `data/whitehouse/alerts.jsonl` is SACRED single-writer (the sentinel) — this builder reads
  only, never writes, never rotates.
- Card copy may not READ or ATTRIBUTE intent (PS-R1); the canonical framing disclaimer
  ("not intent, not timing") is the required exemption. **Amendment PS-A3 (2026-07-09,
  close-out):** the original literal-token ban self-contradicted the mandated framing
  string; the ban is on intent-classification, not the token. No probabilities anywhere (PS-R4).
- Synapse/NW registration as display-only context artifact.
- UI quality bar: browser-verify the rendered card against prod-shaped data and screenshot
  (Playwright direct; the preview browser is known to hang on index).

## §5 Grading + clocks

- Firings ledger + qledger families accrue from ship date; **come-back 2026-08-09** (first
  month of shock/flip firings, sanity review), **2026-10-09** (grading review + threshold
  amendment window), promotion question earliest 2027 and only at n≥8 episodes (PS-R8).
- The flip-confirmation family's first graded rows mature ~26 trading days after the first
  post-ship flip event; do not read the track record before then.

## §6 Redundancy / collision record

- ACTIVE_BUILD_MAP (2026-07-09): no open lane on policy shock / narrative velocity; open PR
  #1780 (policy intel content refresh) is content-only and CONFLICTING — this program does not
  touch `data/policy/intel.json` content and must not hijack that branch.
- Existing organs REUSED, not rebuilt: `policy_intent_desk` (admin-actor accountable leans),
  `whitehouse_alert` reflex (hourly jawboning tape), `market_drivers.snapshot()` (canonical
  shock fingerprints + absorption), `commodity_signals`/`commodity_mtf` (oil technicals),
  election-cycle context (context-only by prior ruling), qledger (grading chassis).
- Prior kills honored: parallel shock classifier (TI-R1 REJECT-REDUNDANT), shock→shelter maps
  (TI-R5 KILLED), LLM narrative-shock classification (TI-R1/A7 FORBIDDEN), NDI narrative-regime
  family (RETIRED 2026-07-02 — not revived here; `repricing_coherence` is price/driver-derived,
  not lexical), election cycle as signal (REFUTED — used as display context only), China
  policy-event transmission gates (null — nothing here gates on policy events).

## §7 Doctrine copy of record (D4 — ship verbatim, EN/ZH)

**EN:** *Policy-put doctrine (2026-07). In a regime where a single actor can reprice
expectations intraday, direction is not forecastable — only conditions are. (1) Never short
the admin-favored complex without a pre-stated falsifier level and defined risk; being right
about the destination does not protect you from the path. (2) Treat defensive leadership as a
rental, not a residence — trim into strength when reversal conditions are armed. (3) On shock
days the correct engine move is de-escalation: discount stale ranks, defer fresh entries, and
wait for T+1 confirmation before chasing or fading. (4) No surface in this system predicts
policy timing or reads intent; the midterm-blackout audit (BTC D1–D5) stands as precedent that
conviction may never be laundered into sizing.*

**ZH:** *政策托底守则（2026-07）。当单一行为体可以在日内重定价市场预期时，方向不可预测——只有条件可以评估。
（1）没有事先声明的证伪价位与限定风险，绝不做空政府偏好的板块；看对终点并不能保护你扛过路径。
（2）把防御板块的领涨当作"租借"而非"常驻"——当反转条件进入待命状态时，应逢强减仓。
（3）冲击日里引擎的正确动作是降级：对陈旧排名打折、推迟新入场，等待T+1确认后再决定追或退。
（4）本系统任何界面都不预测政策时点、不解读意图；中期选举封锁期审计（BTC D1–D5）作为判例：
主观信念永远不得偷渡进仓位决策。*

## §8 Builder ground rules (every lane)

- Work ONLY in your assigned worktree (absolute path given at dispatch); never touch the main
  checkout's git state; no bare `git stash`.
- Many small Edits, never one giant Write (32k output cap kills half-applied trees).
- Local `pytest` on touched modules before push; CI guards to expect: dag-conformance, synapse
  count, `check_validated_claims` (never write "validated" in user-facing text), inline-js
  (check `.j2` sources by hand — CI only checks `site/*.html`), template↔site sync for paired
  assets, no translated `title=` attributes.
- Bilingual EN/ZH for every user-facing string.
- Commit → push → open PR (base main) with a body citing this masterplan §; do NOT merge —
  the orchestrator adjudicates and merges.

## §9 Build record (close-out, 2026-07-09)

Seven PRs, all merged same-day: #2003 (W0 masterplan + kill-registry row), #2005 (W1-D
doctrine + staleness chip + desk cadence 7d→3d), #2006 (W1-A repricing_coherence + intraday
pass), #2007 (W1-B technical_arming v1.1), #2008 (W1-C flip-confirmation lens + qledger
family), #2015 (W2-E shock de-escalation protocol), #2016 (W2-F policy-lever card).
Every build PR was adversarially reviewed (Opus) before merge; a program-level integration
audit ran on the assembled main.

**Amendments logged:** PS-A1 (flatness gate + MACD epsilon after review proved v1 armed on
falling knives — 15.5% false-arm rate on monotone-decline seeds), PS-A2 (ship-date
forward-only ledger + priceable XLP-vs-XLK claim proxy + real 3-way verdict after review
proved v1 claims could never grade and MIXED was unreachable), PS-A3 (intent-token exemption
for the canonical framing disclaimer).

**Outcomes of record:**
- Would-have-fired backscan (descriptive): 2026-06-25 ELEVATED(50, two-consecutive-ELEVATED
  with flip), 2026-07-07 SHOCK(75, state==SHOCK) — the eve of the reversal that motivated
  the program. Firings ledger starts empty 2026-07-09; forward accrual only.
- Flip-confirmation base rates 2024→ (descriptive, 26 events): 6 CONFIRMED / 15 FADED /
  5 MIXED — violent sector flips fade ~58% of the time; the chase is the minority outcome.
  Latest event 2026-07-02 (defensive, z=3.00) → FADED.
- Policy-lever card first print (2026-07-09): QUIET — favored complex (SMH/SOXX returns-EW)
  drawdown −12.8% (above the −15% line post-bounce), oil lever NOT armed (v1.1 flatness
  16.8% over the in-band window: the June decline never formed a genuine base; the reversal
  was event-driven, not technical). Honest print: the put already fired; conditions reset.
- Integration audit: one assembled-state BLOCKER found and fixed in this close-out PR (the
  flip card shipped with zero CSS — never rendered together in any per-PR CI); conformance
  battery green at synapse pin 294; forward-only law verified; all three dashboard blocks
  coexist (shock banner + lever card + flip card) without collision.

**Known pre-existing red (NOT this program):** tests/test_template_items_footgun.py fails on
main flagging namespace-attribute false positives in dashboard/news templates (PR #1548 era)
— spun off to its own lane.

**Clocks (restated from §5):** 2026-08-09 first-month firings sanity review; 2026-10-09
grading review + threshold amendment window; promotion question earliest 2027 at n>=8
episodes (PS-R8).
