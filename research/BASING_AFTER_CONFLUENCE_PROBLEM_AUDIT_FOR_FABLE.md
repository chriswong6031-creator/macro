# Basing-After-Confluence — problem audit + solution brainstorm (for Fable)

> **Role split (owner directive):** Opus/Sonnet produced this assessment, context, and
> candidate-direction brainstorm. **Fable** does the second-pass reassessment, novel idea
> generation, and the actual fix. This document is a *fixed input* — it pins the problem and
> the guardrails so the wrong test is hard to run. It does NOT prescribe the solution.
> Authored 2026-07-02. Companion to `signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (read that §3/§8
> ledger first — several adjacent ideas are already falsified there and must not be re-run).

---

## 0. TL;DR

The confluence gate (`engine/confluence_tiers.cascade` + `engine/signal_gate.gate`) admits a name
only in a **narrow "just-crossed or about-to-cross" window**: `FRESH_TICKS = 2` native TF-ticks
(~6 days on the 3D master) **AND** a `not_topped` veto. This correctly kills the *blasted-off-late*
case (the AMAT-at-the-top bug). But it **also kills a distinct, plausibly superior archetype the
owner trades**: a name that crossed **3–4 ticks ago, did NOT launch, and has been basing sideways**
— weak hands shaken out, base built, coiled for a delayed liftoff, *especially when its sector is
now leading*. The owner's examples: **MCD, KO, JNJ, COKE** (surfaced weeks ago, then dropped off).

**The gate cannot currently tell "based-and-coiled-late" apart from "blasted-off-late" — it treats
both as `>2 ticks → stale → drop`.** The discriminator that separates them is **realized price
extension since the cross** (+ overbought state), and it is already measurable. This audit proves
that split on live data and hands Fable the reconciliation problem with the adjacent falsified
findings flagged.

---

## 1. The owner's problem, verbatim intent

- Stocks that met the T1–T4 confluence gate "a while back" fall out of Standout / Top-setups /
  discovery because they're no longer inside the freshness window.
- **US ≠ China here:** US names routinely *base* for a while after a confluence cross before moving.
  A name that crossed ~1 week ago and has been sideways can still offer "ample opportunity to enter."
- The owner's thesis: a name that **based for 3–4 ticks without launching may be MORE durable** than
  a just-crossed / about-to-cross name — it has already shaken out weak hands and built a base.
- **Strongest when the sector is also leading** (ties directly to the shipped cohort-washout /
  sector-wide-rally-after-washout finding — see §4).
- Two requirements, in tension:
  1. **Keep excluding** names that already *blasted off* (the AMAT / JNJ case). ✅ must not regress.
  2. **Re-admit** names that crossed some ticks ago but **have been sideways and have not launched.**
- And: **"how do we ensure they are actually good"** — i.e. validate durability, don't just widen a
  window and re-import the falling knives / dead-money the freshness gate was built to remove.

---

## 2. How the gate works today (verified against current code, 2026-07-02)

`engine/confluence_tiers.cascade` grades a close series into T1..T4. Eligibility is the **AND** of
two independent screens:

**(A) Freshness window — `FRESH_TICKS = 2`** (`confluence_tiers.py:44`). A tier is live only while
its arrow is ≤ 2 native-TF ticks old (1 tick = 3 days on the 3D master, 2 days on the 2D tiers).
- T1 (validated §7 master `take`): `t1_fresh = take_active and t1_ticks <= 2`.
- T2 (2D-MACD just-crossed × 3D-stoch recent): `t2_ticks <= 2`.
- T3/T4: projected (about-to-cross), ticks = 0.
- A `take` that ages past 2 ticks → `signal_gate.gate` sets `eligible=False`, reason literally
  `"held but risen for many days (cross 2+ ticks ago)"` (`signal_gate.py:184-186`).

**(B) `not_topped` veto** (`confluence_tiers.py:199-208`) — rejects if ANY of:
- `stoch_ob` : 3D StochRSI k **or** d ≥ 80 (overbought → extended entry).
- `stoch_bear`: 3D StochRSI **k < d** (rolled over / not crossed up).
- `macd_bear` : 3D RSI-MACD m < s (outright below signal).
If topped → returns blank regardless of tick age.

These are the AMAT guards, and they are correct for their original job. The problem is that **(A)
uses tick-age as the sole proxy for "already ran," and (B)'s `stoch_bear`/`macd_bear` legs fire on
the ordinary intra-base oscillation of a healthy consolidation** — so a name that crossed and then
*went quiet* is indistinguishable, to this gate, from a name that crossed and *ran away*.

**Consumers affected** (where re-admission would surface): (1) `engine/entry_signal.assess` per-card
entry gauge on us_standouts (badge + `await_confluence` downgrade); (2) the **Top-setups** strip
(`setups.json`, hard-gated on `is_buyable`, #736); (3) **discovery** Buy-zone (hard-gated, #736).
US Standout *inclusion* is still `cycles.mtf_alignment` + `_entry_ok`; confluence is a badge there.

---

## 3. Live evidence — the split is real and measurable (asof 2026-07-01 close)

Ran `signal_gate.gate` + `confluence_tiers.cascade` on the owner's examples (COKE absent from
`data/stocks`). Every column is computed leak-free from the same machinery the board uses:

| name | last 3D cross | ticks old | **ext since cross** | 3D stoch k/d | veto tripped | eligible | verdict |
|------|--------------|-----------|--------------------|--------------|--------------|----------|---------|
| **MCD** | 2026-06-09 | 7 | **−4.5%** | 52.3 / 52.7 | `stoch_bear` (k<d by 0.4) | ❌ | *based, drifting flat — WANT to re-admit* |
| **KO**  | 2026-06-10 | 5 | **−2.1%** | 40.3 / 34.1 | `macd_bear` | ❌ | *based, stoch constructive (k>d) — WANT to re-admit* |
| **JNJ** | 2026-06-05 | 7 | **+9.1%** | 95.7 / 81.3 | `stoch_ob` | ❌ | *actually LAUNCHED + overbought — CORRECTLY excluded* |

**Read this table carefully — it is the whole problem in three rows:**

- All three are excluded today for the *same nominal reason* (>2 ticks / topped).
- But **MCD (−4.5%) and KO (−2.1%) never launched** — flat-to-slightly-down, StochRSI mid-range
  (52, 40), not overbought. These are the owner's "based, coiled, weak hands shaken out" case.
- **JNJ (+9.1%, stoch 96) genuinely blasted off** — the gate is *right* to keep it out.
- The clean discriminator between "want" and "don't want" is **extension since cross** (−4.5%/−2.1%
  vs +9.1%) and **OB state** (52/40 vs 96) — NOT tick age (all 5–7). Tick age is a *bad proxy*: it
  fires identically on the coiled base and the runaway.

**A subtlety Fable must not miss — the "based" set is not monolithic:**
- **KO** = a real confluence cross that aged out while basing (clean re-admission candidate).
- **MCD** = its confluence buy was **BLOCKED by `signal_quality`** ("counter-trend, no 200-reclaim/
  hold") — it is below/around its 200MA. Re-admitting MCD is *not only* a freshness problem; it
  needs the 200MA/reclaim filter relaxed too, which is exactly where "sector is leading" might supply
  the missing confirmation the 200MA bar-raiser was standing in for. Different door.
- So the archetype splits into ≥3 sub-forms: (a) aged validated take, (b) aged T2/T3 close-only
  cross, (c) filter-blocked counter-trend base. They likely need different handling.

---

## 4. Prior art — what's already shipped, and what's already FALSIFIED (do not re-run)

This is the most important section. The `DURABLE_BOTTOM_FRAMEWORK` program (Fable, 2026-07-01/02,
4 waves, deep panel + basket OOS + CN replication) already explored the neighborhood. Reconcile
against it or risk re-running dead tests.

**Shipped and reusable as building blocks:**
- `engine/coiled.py` — the **COILED cohort-washout** state machine (H6): `washout_ctx`, `bull_div`,
  `cohort_fractions`, `assess`, `fire_recent`, `COILED_BONUS`. Ships as a **graded ranking bonus +
  display chip + forward-ledger fields** on US + CN (never a hard gate — it recalls only ~7% of
  durable bottoms). This IS the "confluence × sector-wide rally after washout" finding the owner
  referenced. **Sector-cohort washout is validated (+6–7.5pp clean-liftoff, −5.6pp stop-out).**
- China's **`EXT_PENALTY = 0.5`** (`build_china_library.py:1185`, via `china_signals.extension_read`
  + `_cn_bonus` inside `signal_gate.blend_sorted(bonus_of=...)`) — the **inverse lever**: it DEMOTES
  names that already ran. The owner's ask is the *mirror image* — a lever that RE-ADMITS low-extension
  late crosses. The additive `bonus_of` channel in `blend_sorted` is the ready-made wiring.

**Falsified / cautionary (the guardrails):**
- ⚠️ **H2 "washout AGE + basing calm" — FALSIFIED, WRONG SIGN.** "The aged quiet base is where fires
  die, not where they fly" — clean-liftoff −1.4 to −6.4pp, worst stop-outs in the program (46–48%).
  **BUT H2 measured firing INTO a pre-existing calm base (arming on calmness BEFORE the trigger).**
  The owner's case is a *different window*: a confluence cross ALREADY fired, THEN the name based.
  Whether "post-cross basing" is the same object as "pre-cross calm base" is **the open question** —
  it is not obviously the same, but Fable must prove the distinction, not assume it. If it collapses
  to H2, the idea is already dead.
- ⚠️ **Staleness is the worst forward-drawdown band** (`ENTRY_QUALITY.md`, 54k samples): ">20d old
  cross" = worst. MCD/KO are ~15 trading days / 5–7 ticks old — approaching that cliff. The finding
  is NOT extension-stratified, though; the owner's whole thesis is that *conditioning on low
  extension rescues a subset of stale crosses*. Untested — this is the research question.
- ⚠️ **"Near-low + fresh anti-correlates with forward return"; durable-bottom timing has negative
  return-IC** (#812). Consequence: this is a **risk/durability/surfacing** feature, NOT alpha and NOT
  sizing. Any "based names are more durable" claim must be graded on the framework's **per-fire,
  count-fair** axes (stop-out / clean-liftoff / dead-money + recall), **never** round-trip returns.
- ⚠️ **Failure mode (b) dead-money / trap** is the specific risk of re-admitting based names: "based"
  and "slowly bleeding / dead money" (Tencent-style) look alike early. MCD is DOWN 4.5% since its
  cross — is that a constructive base or a slow bleed? The distinction is exactly what must be
  measured, on the dead-money axis the framework defines.

---

## 5. Problem statement, sharpened (the thing Fable is asked to solve)

> Design a **post-cross "based / coiled" re-admission** path that surfaces names which crossed the
> confluence 3–N ticks ago **only when** they have **not launched** (low realized extension since the
> cross) **and remain structurally constructive**, while provably **not re-admitting the blasted-off
> case** (JNJ/AMAT) — and validate that the re-admitted stratum is *actually good* (better or
> non-inferior on stop-out / clean-liftoff / dead-money, with a recall gain), on the
> DURABLE_BOTTOM measurement constitution (§4 of that doc), reconciled against the falsified H2.

Success is NOT "widen `FRESH_TICKS`." That re-imports JNJ/AMAT wholesale. Success is a *conditioned*
re-admission whose condition is the extension/structure discriminator, validated count-fair.

---

## 6. Candidate solution DIRECTIONS (brainstorm — inputs for Fable to refine/replace, not a spec)

These are seeds. Fable should reassess, discard, merge, or invent past them. Each carries a
mechanism story and a validation hook so none can be graded the wrong way.

**D1 — "BASED" as a new post-cross tier (the primary candidate).**
Add a tier below T1–T4: a name whose most-recent confluence cross is `2 < ticks ≤ BASE_TICKS`
(sweep ~4–8), **conditioned on** (i) low extension since cross (|Δ| below a band, e.g. −X%..+Y%,
so JNJ's +9.1% is out), (ii) StochRSI **not** overbought (kills the OB leg but *relaxes* the raw
`stoch_bear` k<d oscillation leg — a base oscillates by construction), (iii) 3D RSI-MACD still ≥
signal *or* re-crossing. Weight it BELOW a fresh T1 (a base is a surfacing exception, never a
stronger buy). Ship as ranking bonus / chip first (mirroring COILED's ship-shape), forward-ledger
graded before it earns hard-gate power. **Open design Q for Fable:** is the veto relaxation
(ii)/(iii) safe, or does it re-admit dead-money? Measure on the dead-money axis.

**D2 — Replace tick-age with an EXTENSION-since-cross screen (attack the bad proxy directly).**
The gate's real intent is "not already run." Tick age is a proxy; extension is the target. Keep the
freshness window for the *fresh* tiers, but add a parallel admission: `crossed within BASE_TICKS`
AND `max drawup since cross < LAUNCH_THRESH` (hasn't launched) AND `not below the cross by more than
BLEED_THRESH` (not bleeding — separates base from slow death). This is the mirror of China's
`EXT_PENALTY`; here it's an *extension-gated re-admit* rather than an extension *demote*.

**D3 — Gate the re-admit on SECTOR LEADERSHIP (the owner's own strongest signal).**
Only re-admit a based name when its sector/cohort is confirmed leading (reuse `coiled.cohort_*` +
the RRG/subsector leadership reads already in the repo). Mechanism: leadership supplies the
confirmation the base itself can't, and it's exactly the "sector leading after washout" cell the
framework already validated (+6–7.5pp). This is likely the **highest-precision** door and the one
most aligned with the owner's live experience ("more apparent when the sector is leading"). Could
also be the specific door that rescues the MCD counter-trend/below-200 sub-form (§3): sector
leadership substitutes for the missing 200-reclaim.

**D4 — "Coiling quality" structural score for the base itself.**
Not all bases are equal. Score the consolidation: volatility contraction since the cross (ATR
compression), tightness of the range, higher-low structure, volume dry-up→pickup. NB: the framework
found *volume dry-up = dying interest* (H4 falsified as a positive filter on the US panel) and
*ATR-contraction trend guards = exposure artifact* — so a naive "quiet base is good" score risks
re-deriving H2/H4. Fable must find the coiling feature that ISN'T already falsified (perhaps
range-tightness conditioned on cohort leadership, which H2 did not test jointly).

**D5 — Re-arm on a FRESH secondary trigger inside the base (avoid staleness entirely).**
Instead of admitting a stale cross, wait for a *new* fast trigger (m1d/m2d re-cross, or the wave-4
**COILED-FIRE** union C2 marker that already ships as a chip) to re-fire *inside* the based name.
This sidesteps the ">20d stale = worst" finding because the operative arrow is always fresh; the
base is just the *context* that makes the fresh re-trigger high quality. Ties the owner's idea to
the already-validated COILED-FIRE machinery. **Possibly the cleanest reconciliation** — it keeps
freshness (the validated axis) and adds the base as an arming state, not as a stale-admit.

**Cross-cutting for all D's — how to prove "actually good" (§4 constitution):**
label durable bottoms, evaluate the based-stratum vs fresh-cross baseline on stop-out / clean-liftoff
(+15% before −5%) / dead-money / recall, per-fire count-fair, on deep US panel + basket OOS + CN
replication, both time-halves and ticker-halves, with the JNJ/blasted-off cohort explicitly held
OUT and confirmed still-excluded. Ship-shape starts as bonus/chip + forward ledger, earns hard-gate
weight only after live grades accrue (the repo's established discipline).

---

## 7. Suggested first moves for Fable

1. **Reconcile the window question first** (cheap, decisive): is "post-cross basing" separable from
   the falsified H2 "pre-cross calm base"? Stratify base3d/m2d fires by *extension-since-cross* ×
   *ticks-since-cross* and read clean-liftoff / dead-money / stop-out per cell. If a low-extension,
   3–8-tick, not-OB cell beats the fresh baseline (or is non-inferior with a recall gain) and does so
   *conditioned on cohort leadership*, the owner's thesis survives and D1/D3/D5 are live. If it looks
   like H2, it's dead — record and stop.
2. Pick the ship-shape door (D1 tier vs D5 re-arm vs D3 leadership-gate) by which cell wins.
3. Keep JNJ/AMAT as the regression fixtures — any candidate that re-admits them fails on sight.

**Reproduce §3's evidence:** `PYTHONPATH=$PWD python3` a script importing `engine.signal_gate` /
`engine.confluence_tiers`, load `data/stocks/{MCD,KO,JNJ}.parquet` `close`, call `gate()` +
`cascade()` and the `_tf_bars`/`_stoch_rsi_kd`/`_rsi_macd` internals for the veto legs + extension
since the last 3D `_xup(m3,s3)` cross. (The diagnostic used for the table above.)
