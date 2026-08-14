# Site Semantics: the stretch / extension oracles

**The word "stretched" / "extended" names FOUR different measurements in this repo.**
Two of them render adjacently in the per-ticker drawer and disagree on ~38% of names.
This file is the divergence contract: what each one measures, which of them may license
which sentence, and the gate that keeps a consumer from asserting a cause it did not
measure.

Enforced by `scripts/check_stretch_oracle_contract.py` (nightly counter + gate) and
`tests/test_stretch_oracle_contract.py`.

---

## The four oracles

| # | Field | Produced by | What it actually measures |
|---|---|---|---|
| **O1** | `ladder.alignment.overextended` (bool) | `engine/cycles.py` `_overextension_legs` | A 4-leg OR **entry-timing brake**. Three legs are fast oscillators (daily StochRSI > 80, 3-day StochRSI > 80, daily RSI14 > 62); one leg is distance (`pct_vs_200dma ≥ +30`). Oscillator legs are suppressed when price is ≤ −10% below the 200-day (range-compression guard, #2509). |
| **O2** | `entry_signal.status == "extended"` | `engine/entry_signal.py` `_STATUS_BY_URGENCY` | **Not a measurement.** It is the relabel of `ladder.entry.urgency == "caution"` — one token in a 14-token status vocabulary. |
| **O3** | scoring clamp | `engine/stock_score.py` `_overextended(rec)` | Pure distance: `pct_vs_200dma ≥ +30`. Same function name as O1, different definition. |
| **O4** | `ext.grade in ("stretched","parabolic")` | `engine/extension.py` `grade()` | **Self-relative** stretch: `ext_z`, the z-score of `price/SMA200 − 1` against the name's own history. `stretched` = 1–2σ, `parabolic` = >2σ. US listings only. |

#### O1 — what fires, in practice

Measured on the served US store (1,628 names, vintage 2026-07-02), re-derived under
current code:

| basis | n |
|---|---|
| `oscillator` (no distance leg at all) | 662 |
| `stretch` (distance leg only) | 108 |
| `both` | 102 |

**76% of O1 flags carry no distance leg.** O1 is oscillator-DOMINANT. It answers
"is momentum hot right now?", not "how far above trend is this?".

#### O2 — a bucket, not a reading

`urgency == "caution"` is assigned from at least four structurally different places in
`engine/cycles.py`:

1. `state == "TOP WATCH"` → TAKE PROFITS — genuinely late/extended.
2. the `extended_gate` route → DON'T CHASE — genuinely extended.
3. `state == "COUNTERTREND BOUNCE"` → UNCONFIRMED, HIGH RISK — a washed-out name
   usually far **below** trend. The opposite of extended. (Split off to the honest
   `bounce_wait` status by #2512.)
4. the below-MA10 de-escalation branch → `BOTTOMING · UNCONFIRMED — WAIT` when
   higher-timeframe momentum is fading and oscillators are **not** overbought.

So `status == "extended"` means "the ladder said caution", and at least two of its
sources are not extension at all.

---

## The measured divergence

Both oracles present on 1,598 of 1,628 names.

| | as SHIPPED in the store (vintage 2026-07-02) | re-derived under CURRENT code |
|---|---|---|
| O1 ∧ O2 | 392 | 260 |
| O1 ∧ ¬O2 | **607** | **609** |
| ¬O1 ∧ O2 | 195 | 41 |
| neither | 404 | 688 |
| **total disagreement** | **802 / 1,598 = 50.2%** | **650 / 1,598 = 40.7%** |

Two vintage warnings, both load-bearing:

- The store that produced the widely-quoted **"607 / 1,629 = 37.3%"** has asof
  `2026-07-01/02`. Both de-collision fixes — **#2509** (oscillator-exempt below −10%)
  and **#2512** (`bounce_wait` for COUNTERTREND BOUNCE) — landed **2026-07-13**, i.e.
  11 days *after* that store was baked. `site/stockdata/` is gitignored and regenerated
  at build time, so a local checkout's copy can be arbitrarily old.
- Re-deriving both oracles under current code moves the *reverse* cell hard
  (195 → 41) but leaves the quoted cell essentially unchanged (607 → 609). **The
  headline disagreement survives both fixes.** The contamination was real and the
  finding is real; the two facts are independent.

Never quote a divergence number without its store vintage. The nightly counter
(below) exists so this number is always fresh.

---

## Verdict: legitimate divergence, not a producer defect

Neither producer is arithmetically wrong. The disagreement is the expected result of
comparing a **measurement** (O1) to a **bucket label** (O2).

The residual 609-name cell decomposes cleanly by ladder state:

| ladder.state | n | post-fix `entry_signal.status` |
|---|---|---|
| TURN SIGNALED | 263 | `await_confluence` 234, `buy_soon` 117 … |
| FRESH BUY | 119 | |
| TOP WATCH | 84 | |
| RALLY ON | 83 | |
| COUNTERTREND BOUNCE | 69 | `bounce_wait` 69 |

The dominant cell is **fresh turns off a low whose fast oscillators are already
overbought** — the ladder still reads a confirmed low while the alignment gate refuses
to put the name on the standout strip. That combination is *designed*, and the house
has already adjudicated it once on the China board: `engine/setup_tier.py`
`assign_stage` rule 2a (**ruling F6**) admits `buy_now + overextended` as legitimate and
resolves it with a `RAN_LATE` stage plus `muted_entry`, rather than treating either
input as a bug.

Note the cross-market inconsistency that same docstring records: F6 pins the China
`overextended` input to the **price**-extension read and says explicitly *"NOT the
daily-RSI gauge"*, because the RSI gauge demotes exactly the freshest base breakouts.
O1 — the universal fallback every non-US market renders — **is** that daily-RSI gauge.
Unifying the two is authority-tier work and needs the gauntlet; it is deliberately out
of scope here (see "Not done here").

---

## Blast radius — the two oracles are NOT symmetric

This is why the fix here is disclosure rather than a rename or a unification.

**O1 is display-only downstream.** `engine/cycles.py` is the sole writer
(`mtf_alignment` → `cycle_state`); every other module only reads or copies it forward
(`engine/stock_score.py` stamps it into `conviction.alignment`, `engine/postmortem.py`
builds a `bought_extended` label from it). No consumer ranks or gates on the *field*.
Note the value still gates *inside* the producer — `mtf_alignment` refuses a
PRIME/ARMED/APPROACHING tier when `over` is true, and `engine/setups.py` selects the
standout strip on `aligned`/`near` — which is exactly why the boolean was left
bit-identical here.

**O2 is authority-tier in five separate subsystems.** `entry_signal.status == "extended"`
is read as a scored or gating input by:

| consumer | effect |
|---|---|
| `engine/us_board_rank.py` `_ENTRY_VALUE` / `_RAN_STATUSES` | score leg = 0.0; buckets the row into `STAGE_RAN` |
| `engine/china_board_rank.py` `_ENTRY_VALUE` / `_FEATURED_ENTRY_STATUSES` | score leg = 0.3; blocks the featured shelf |
| `engine/name_score.py` `_ENTRY_CONFIRM` | halves the trigger score (× 0.50) |
| `engine/prophet_bridge.py` `admission_class` | hard refusal, receipt code `ran_too_far` |
| `engine/watchlist_sentinel.py` via `scripts/run_watchlist_sentinel.py` | maps the status to `ext_grade="stretched"`, vetoing the alert window |

So renaming or re-pointing O2 is a promotion-tier change across five scored surfaces.
Note also the last row: the sentinel translates an O2 *status* into an O4-shaped
*grade* word — a sixth crossing of the same vocabulary.

## The consumer contract

**A renderer must branch on `ladder.alignment.overextended_basis`, never on
`overextended` alone.**

| `overextended_basis` | may say | must NOT say |
|---|---|---|
| `oscillator` | "ran hot", "momentum is stretched", "don't chase the thrust" | anything about the 200-day line, "far above its trend", a distance figure as the cause |
| `stretch` | "far above its 200-day line", distance prose, a `pct_vs_200dma` figure | "momentum is overbought" |
| `both` | either | — |
| `null` | nothing — not flagged | — |

Additional standing rules:

- **O2 is not an extension reading.** A surface that renders `status == "extended"` as
  "ran hard / entries here have chased before" is wrong for every COUNTERTREND BOUNCE
  and every below-MA10 de-escalation row. Render O2 as a *stance* ("wait", "protect
  gains"), never as a distance claim.
- **O4's grade and `tech.pct_vs_200dma` are different quantities.** The grade word comes
  from `ext_z` (z-score vs the name's own history); the number is the raw percentage.
  A low-volatility name can grade `stretched` at +8%, and a high-volatility name can
  grade `steady` at +40%. Pairing the grade word with the raw number as its *cause* is
  the same error as the O1 case. (`templates/portfolio.js` carries a comment verifying
  that `ext.ext` equals `pct_vs_200dma` — true, but the *grade* is not derived from
  `ext.ext`, so that check does not license the pairing.)
- **Never print a stretch chip above a "% **below** its 200-day line" sentence.**
- **The stretch lane carries further than its own row.** In
  `templates/watchlist_risk.js`, `lanes.stretch.state` feeds `roleBadge`, which raises
  the Risk Desk **trim_review** ("Take-profit review") and generic **review** rungs; and
  `templates/portfolio.js` `roleOf` renders that same badge. So an O2 mis-read does not
  stop at one chip — it changes the stance the user is shown.

#### Fields (added 2026-08-13, additive — `overextended` itself is unchanged)

```
ladder.alignment.overextended        bool        unchanged; still the strip's SELECTION gate
ladder.alignment.overextended_legs   list[str]   which legs fired, evaluation order
ladder.alignment.overextended_basis  str|null    "oscillator" | "stretch" | "both" | null
ladder.alignment.ext_pct_used        float|null  the distance the brake actually saw
```

Leg vocabulary: `daily_stochrsi_overbought`, `three_day_stochrsi_overbought`,
`daily_rsi14_hot`, `stretch_vs_200dma`.

`_overextended()` is `bool(_overextension_legs(...))` **by construction**, so the brake
and its disclosed cause cannot drift apart. `ext_pct_used` is `null` for callers that
pass no distance (the ladder de-escalation gate) — for those calls the distance leg is
structurally unreachable and the brake is oscillator-only by definition.

---

## Known open defects (display-tier, owned by the watchlist lane)

These are **not** fixed here — `templates/portfolio.js` and `templates/watchlist_risk.js`
are held by the open W4 drawer PR (#5568) and editing them from a second lane would
deadlock it. They are recorded so the owning lane can close them with the fields above.

- **D2 — wrong-cause narration.** `portfolio.js` `extGradeOf` maps
  `alignment.overextended === true` → grade `stretched` for every non-US name, then
  `extensionSentence` narrates `tech.pct_vs_200dma` as the cause. On the served store,
  147 of the 176 alignment-fallback rows print a 200-day-distance cause with no distance
  leg fired. **30 of them still contradict after #2509** (`−10% < pct_vs_200dma < 0`):
  a "Stretched" chip above a sentence reading "about X% *below* its 200-day line"
  (SYK −9.6, NRG −9.5, TAL −9.4, VST −9.2, CRH −8.4, LOW −8.3 …). Remedy: branch on
  `overextended_basis`.
- **D4 — dead risk rules.** `portfolio.js` `extGradeOf` returns only
  `intrend|steady|stretched|parabolic`, but three call sites test
  `g === 'high' || g === 'extreme'` — values no extension vocabulary in this repo ever
  produces. The "Stretched" attention flag and Risk Desk **Rules 1 and 3** are
  therefore unreachable in the current build.

## Not done here

Unifying O1 and O3/O4, or changing which legs O1 fires on, is a **promotion-tier**
change: O1's value decides the alignment tier that `engine/setups.py` selects the
standout strip from, and `stock_score._overextended` clamps a scored tilt. Per house
epistemics that needs the gauntlet (pre-registered gates, held-out evidence), not a
display-tier PR — so the boolean here is bit-identical to its pre-disclosure value
(pinned by `test_matches_the_pre_disclosure_implementation`).

Renaming the shipped fields was considered and rejected. O2 in particular is a scored or
gating input in five subsystems (table above); renaming it moves ranking, staging,
admission and alerting at once, for no epistemic gain. An additive basis makes the
meaning unambiguous to every consumer without moving a scored field.

Also left open, deliberately: the F6 cross-market inconsistency (O1 is the daily-RSI
gauge that the China ruling explicitly rejected as an extension read), and whether
`prophet_bridge`'s `ran_too_far` refusal is still the right receipt for the
`bounce_wait` rows that #2512 split out of O2. Both need the gauntlet.
