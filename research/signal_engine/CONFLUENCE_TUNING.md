# Confluence Tuning — Earlier-Trigger Entry Study

> Companion to `CHARTER.md`. Read the charter first. This study honors §2 (risk tool,
> not return engine), §3 (generalization is the verdict; pre-committed kill rule), and
> §4 (faithful RSI-MACD + stoch-of-RSI math only). Backtests here are a **microscope**,
> not a verdict machine.

**Date:** 2026-06-27 · **Panel:** 110–114 deep-history US names in `data/stocks/`
(all held out — the buy-filter was designed on Tencent/BABA, which are not in the panel).

---

## 0. TL;DR

The owner's hypothesis — **MACD on the 2D (faster TF, fires earlier) + StochRSI on the 3D
(turns at the bottom)** — is **mechanically TRUE but does not generalize on the metrics
that matter.** Earlier triggers genuinely enter the *same* moves **~3.7–4.9 trading days
earlier, at a ~1.5–2.6% cheaper price, ~80% of the time** (clean, count-neutral evidence).
But "earlier" ≠ "better located": across the held-out panel every earlier/looser trigger
**deepens drawdown, worsens forward entry location, and raises the shake-out rate.** On the
charter's verdict gate (majority of held-out names improved on **drawdown** *and* **location**)
**no variant passes** — they win on a *minority* of names (~21–30% shallower-DD, ~33–42%
better-located). The single axis that improves is *chase* (entering before the breakout),
which is the mechanical pre-cross artifact, not risk reduction.

**Per the §3 kill rule: ship the simpler baseline. `base3d` stays. Promote nothing into the
scored buy gate.** The one clean, useful by-product (the 3–5 day lead) is proposed below as a
**display-only "early-anticipation" marker** — never a tradeable buy — with an explicit
deeper-drawdown health warning.

This is the same lesson as the killed regime router (CHARTER §5): a plausible improvement
that looks good on a few names and fails the held-out generalization gate. **The 3D MACD's
lag is partly load-bearing** — it is a selectivity filter; speeding it up admits more
not-yet-confirmed moves that shake out.

**Follow-up (§5b): a secondary location guard was tested and also killed.** Adding
ATR%-contraction / Kaufman-efficiency / higher-low / rising-50MA guards to the early trigger
*does* cut drawdown sharply — but the exposure-confound check proves it is an **exposure
artifact** (it draws down less because it trades 3–6× less, not because it enters better):
`corr(DD-gain, signal-drop) ≈ +0.3 to +0.5`, and at **matched trade-count the DD edge is ~0
(−1pp)**. Per-entry location never improves on a majority of names. No guard flips the gate.

---

## 1. What was tested

Baseline = **`base3d`**, the incumbent confirmed BUY: 3D RSI-MACD bull cross + recent 3D
StochRSI cross-from-oversold + weekly/RSI gates (the live `engine/signal_quality.py` logic).

| variant | MACD TF | StochRSI TF | trigger | idea |
|---|---|---|---|---|
| `base3d` | 3D | 3D | confirmed MACD cross | **incumbent** |
| `m2d_s3d` | **2D** | 3D | confirmed MACD cross | **owner's hypothesis** — faster MACD, fires earlier |
| `m2d_s2d` | 2D | 2D | confirmed MACD cross | everything faster |
| `m1d_s3d` | **1D** | 3D | confirmed MACD cross | fastest MACD |
| `m2d_s3d_early` | 2D | 3D | **anticipation** | fire on the 3D StochRSI bottom-turn while the 2D MACD *histogram is only rising* (pre-cross) |
| `stochlead3d` | 2D | 3D | leading-leg | StochRSI bull-from-OS, MACD merely not-falling |
| `m2d_s3d_brk` | 2D | 3D | cross **+ 3rd indicator** | owner's trigger + a micro price-structure breakout confirm |

---

## 2. Methodology (shared, singular — `tuning_harness.py` + `tuning_lead.py`)

Everything is computed with the **faithful** math (RSI-MACD = `EMA(RSI14,14) − EMA(RSI14,60)`,
`signal = EMA(macd,5)`; StochRSI = `SMA(stoch(RSI14,14),3)` then `SMA(·,3)`). NOT price MACD.

**Leak-free cross-grid protocol (the crux of comparing 2D vs 3D fairly).** `resample("{n}B")`
labels a bar by the bin's *left edge*, but the bar's close is only **known** on the last daily
date in the bin. Each TF bar is therefore mapped to its true `known_date`, and the **fill is the
first daily close strictly after `known_date`**. All metrics and the trade-sim then run on the
*same daily close series with the same fill rule*, so a 2D trigger and a 3D trigger are compared
apples-to-apples. (Verified by the code-leak audit, §4.)

**Entry-isolation.** Every variant uses the **same common exit** (the base 3D oscillator sell/cut,
mapped to daily) so differences are attributable to *entry timing only* — matching the charter's
lesson that drawdown control is an entry-filtering problem, and `test_buyfilter.py`'s "same exit,
vary the buy" design.

**Metrics (charter-aligned, never beat-buy-and-hold):**
- `dd` — max drawdown of the traded equity (**primary metric**).
- `locw` — entry's location in its forward 40-day close range (0 = bought the eventual low; **lower = better**).
- `chase` — % of entries where price was *already* above its prior 20-day high at the fill (entered into/after the breakout; **lower = better**).
- `shake` — % of entries that hit −8% before +8% (shake-out rate; **lower = better**).
- `runup`, `mae`, `mfe`, `wr`, `avgloss`, `avg_signals` — context.
- **Count-neutral LEAD** (`tuning_lead.py`): pairs each baseline buy with the candidate's nearest buy on the *same move* and measures days-earlier and price-improvement — immune to the candidate simply firing more often.

**Verdict gate (the only thing that decides promotion):** on the **held-out panel**, is the
candidate **shallower-DD on a majority of names AND better-located on a majority of names**,
on both the full panel and the strict subset excluding the 5 hand-examined exit-cases
(JNJ/LLY/WMT/MCD/NVDA)? Pre-committed kill rule: if not, ship `base3d`.

---

## 3. Results

### 3a. The mechanism IS real — earlier and cheaper (clean LEAD evidence)

Count-neutral, raw signals only (no forward-peeking filter), 919 baseline buys across the panel:

| candidate | coverage of base moves | days earlier (mean) | % earlier | avg price improvement | % cheaper |
|---|---|---|---|---|---|
| `m2d_s3d` (owner) | 87.9% | **+3.68 d** | 81.7% | **+1.50%** | 65.3% |
| `m2d_s2d` | 77.4% | +3.96 d | 83.5% | +1.53% | 66.1% |
| `m1d_s3d` | 68.6% | +3.42 d | 76.3% | +2.55% | 70.8% |
| `m2d_s3d_early` (anticip.) | 49.9% | **+4.89 d** | 78.0% | **+2.56%** | 65.6% |
| `stochlead3d` | 57.1% | +4.19 d | 73.1% | +2.28% | 62.3% |
| `m2d_s3d_brk` | 68.2% | +3.45 d | 80.5% | +1.29% | 62.5% |

→ The owner is right that the 2D MACD fires **before** the lagging 3D MACD on the same move,
and gets in cheaper. The hypothesis is confirmed *at the mechanism level.*

### 3b. …but it FAILS the verdict gate (held-out generalization — independently re-verified)

Per-name, candidate vs `base3d`, filtered, aligned by ticker. **Bold = passes the >50% bar.**

| candidate | DD-shallower | median dd delta | location-better | shake-better | chase-better |
|---|---|---|---|---|---|
| `m2d_s3d` (owner) | 21.4% | −3.23 pp | 41.8% | 21.4% | **57.1%** |
| `m2d_s3d_early` | 29.9% | −2.93 pp | 34.0% | 22.7% | **73.2%** |
| `m2d_s2d` | 28.6% | −3.09 pp | 41.8% | 21.4% | **57.1%** |
| `m1d_s3d` | 17.3% | −8.65 pp | 37.8% | 24.5% | **72.4%** |
| `stochlead3d` | 27.8% | −3.09 pp | 33.0% | 22.7% | **71.1%** |
| `m2d_s3d_brk` | 28.9% | −2.74 pp | 38.1% | 22.7% | **53.6%** |

**No variant** is shallower-DD or better-located on a majority of held-out names. The typical
name draws down **~3 pp deeper** under every candidate (m1d is far worse, −8.65 pp). The strict
held-out subset (excl. JNJ/LLY/WMT/MCD/NVDA) is essentially identical (e.g. m2d_s3d_early 29.3%
shallower-DD, median −3.01 pp). The *only* majority-win is **chase** — the candidates do enter
before the breakout, but that earlier entry lands in worse locations and deeper drawdowns.

### 3c. Full-panel aggregates (filtered, ~110 held-out names)

| variant | avg_signals | **dd** | **locw** ↓ | chase ↓ | **shake** ↓ | wr |
|---|---|---|---|---|---|---|
| **`base3d`** (incumbent) | 2.34 | **−12.48** | **0.284** | 0.522 | **0.140** | 66.8 |
| `m2d_s3d` (owner) | 3.87 | −17.34 | 0.330 | 0.407 | 0.203 | 64.0 |
| `m2d_s3d_early` | 3.41 | −16.61 | 0.371 | **0.161** | 0.230 | 69.9 |
| `m2d_s2d` | 3.49 | −17.37 | 0.341 | 0.384 | 0.204 | 63.2 |
| `m1d_s3d` | 8.74 | −21.53 | 0.353 | 0.259 | 0.226 | 67.9 |
| `stochlead3d` | 3.82 | −16.81 | 0.358 | 0.193 | 0.217 | 70.8 |
| `m2d_s3d_brk` | 3.16 | −15.96 | 0.336 | 0.427 | 0.211 | 61.9 |

`base3d` posts the **shallowest drawdown, best location, and lowest shake-out of the entire
field.** Every candidate degrades DD by 3.5–9 pp and location by 0.05–0.09. The higher win-rates
on the early/stochlead variants do *not* rescue them (locw and shake both worsen; and WR is the
one axis the charter explicitly says not to chase). Raw (unfiltered) aggregates tell the same
story: `base3d` dd −24.45 is the shallowest; every candidate is −26 to −29.

---

## 4. Leak audit — which numbers to trust

Adversarial code audit verdict: **mixed**, and confirmed against the source.

- **RAW path and the LEAD analysis are LEAK-FREE.** Raw buys use only `.shift`-guarded crosses,
  the known-date `to_daily` mapping (bin labeled by its max daily date), the `.shift(1)` weekly
  gate (prior closed week, no repaint), and fill at `i+1`. LEAD reads raw `buy` and only compares
  the two fill prices — no forward window in the decision. **§3a (lead) and the raw aggregates
  are fully trustworthy.**
- **The FILTERED path FORWARD-PEEKS** — the validated buy-filter's *reclaim-and-hold* reads
  `close[i+1..i+3]` to decide TAKE while the fill is `i+1`, so filtered absolute DD/WR are
  optimistic. **This is inherited from the original keeper** (`refined_buy` in `diagnose_v2.py`
  reads `i+1`/`i+2`); it is a property of any reclaim-and-hold confirmation rule, not a new bug.
  The **relative** ranking still holds because the *same* forward-peeking filter is applied
  identically to base and every candidate — and base *still wins*. The §3b generalization gate
  was re-verified independently from the raw per-name dumps and matches.
- **Fill-offset probe corroborates no fabricated edge.** Delaying the fill 0→1→2 bars degrades
  location/shake gracefully for both base and candidates, and never improves either. On `locw`
  the candidate is worse than base at *every* offset (gap +0.046/+0.055/+0.050, non-shrinking) —
  i.e. there is no fill-dependent timing edge.
- **Sub-panel split (even/odd halves) → "holds" only in the narrow sense** that the direction of
  effect is sign-stable across halves: the candidate is *consistently deeper-DD* and slightly
  better-locw on both halves. That stability confirms the degradation is real, not split noise.

**Bottom line:** lean on RAW + LEAD for any claim. They say: earlier/cheaper entry is real
(§3a); it does not lower drawdown or improve location (§3b/§3c).

---

## 5. Why it fails — the load-bearing lag

The 3D MACD cross lags because it waits for momentum to *confirm*. That lag is doing real work:
it filters out the not-yet-confirmed turns that shake out. Reading the MACD on a faster TF (2D/1D)
or firing on the StochRSI turn before the MACD confirms removes that selectivity — so you catch
the move ~4 days earlier and ~2% cheaper *when it works*, but you also fire on a pile of extra
early turns that drop further before recovering (or fail outright). Net: lower chase, **deeper
drawdown, worse location, more shake-outs.** Trading the lag away trades selectivity away.

---

## 5b. Follow-up — secondary location guard (research avenue #3): tested, also killed

The §6 recommendation flagged one live avenue: tighten `m2d_s3d_early` with a **secondary
location guard** that vetoes the early fires landing in deep-DD locations, then re-run the
gate. Done. Guards tested (universal, persistent-property, leak-free — charter §2e/§5):
`volcontract` (ATR%-percentile ≤ 0.60, calm/coiling not falling-knife), `higherlow` (latest
**confirmed** swing low > prior), `eff` (Kaufman Efficiency Ratio(10) above its rolling
median — trending not chop), `above50` (above a *rising* 50-day MA), and pairwise combos.

**The guards cut drawdown hard** — but for the wrong reason. Filtered, candidate vs `base3d`,
held-out per-name:

| guarded variant | agg dd (base −12.5) | DD-shallower % | location-better % | avg signals (base 2.34) |
|---|---|---|---|---|
| `early_vol_50` | −11.3 | **65.8%** ✓ | 42.1% ✗ | 1.2 |
| `early_50` | −12.6 | 57.7% ✓ | 32.7% ✗ | 1.6 |
| `early_vol_hl` | −10.0 | 57.7% ✓ | 38.5% ✗ | 1.2 |
| `early_hl` | −11.1 | 55.8% ✓ | 48.8% ✗ | 1.2 |
| `m2d_s3d_early` (unguarded) | −16.6 | 29.9% | 34.0% | 3.4 |

Raw is even more dramatic (`early_hl_50` shallower-DD on **93.8%** of names, agg −12.8 vs
−24.5). **But it is an EXPOSURE ARTIFACT, not better entries:**

- `corr(DD-gain, signal-drop)` = **+0.30 to +0.46** — the more trades a guard skips, the more
  its drawdown "improves."
- On names where the guarded variant fires **as many trades as `base3d` (±1)**, the DD edge is
  **−1.0 to −1.3 pp (gone / inverted)**. The drawdown win lives entirely in trading less.
- **Per-entry location (`locw`) never improves on a majority** of held-out names (32–49%), and
  the guards fire **3–6× fewer signals** (1.2–1.6 vs `base3d` 2.34 filtered; 1.4–5.2 vs 8.4 raw).

**Verdict: no guard flips the gate.** A selectivity filter lowers drawdown by participating
less, not by entering at better locations — exactly the thing we set out to fix. Avenue #3 is
closed. (Driver: `tuning_gate.py`; guards in `tuning_harness.py` `_guard_frame` + `early_*`
variants.)

## 6. Recommendation

1. **Promote nothing into the scored buy gate. Keep `base3d`.** The pre-committed §3 kill rule
   fires: no variant beats the simpler baseline on drawdown out-of-sample (or on location), so
   the simpler baseline ships. Add this study to the "tested and killed as a tradeable entry"
   ledger alongside the regime router (CHARTER §5).

2. **Optional — a DISPLAY-ONLY "early-anticipation" marker (not a tradeable BUY).** If the owner
   wants the earlier read on the chart, `m2d_s3d_early` is the cleanest candidate for an
   *advance-warning annotation*: it has the **lowest chase (0.161 vs base 0.522)** and the
   **largest lead (+4.9 d / +2.56% cheaper)**, so it is informative that a `base3d` confirmed
   cross is *approaching*. Render it as a **separate, clearly-labeled hollow pre-cross dot** on
   the `site/signals/<T>.json` leaf — **never** folded into conviction, the brain leaf's scored
   `quality`, or an auto-trade trigger (CHARTER §7). It **must** carry a health warning: acting
   on it early is empirically *worse* entry quality — it deepens drawdown on ~70% of names
   (median −2.93 pp) and roughly doubles the shake-out rate. It is context ("a buy may be
   coming"), not a signal to act before confirmation.

3. **The secondary-location-guard avenue is now closed (§5b).** It was the one live lead; tested
   with universal, cross-sectionally-validated guards, it cut drawdown only by trading less
   (exposure artifact, DD edge gone at matched trade-count) and never improved per-entry location
   on a majority of held-out names. `base3d` stays for the scored gate. No remaining avenue
   flips the location gate on this data; treat the earlier trigger as display-only context only.

**Honest caveats.** Backtest is a microscope: ~110 names, a single recent regime window
(entries since 2023-06), common-exit isolation. The filtered *absolute* DD figures are optimistic
(forward-peek, §4) — only the relative base-wins-everywhere conclusion and the raw LEAD timing are
leak-free. The verdict rests on the held-out *minority-win* generalization gate, not any single
aggregate.

---

## 7. Reproduce

```bash
# panel aggregate for one variant (raw or filtered)
python3 research/signal_engine/tuning_harness.py --variant m2d_s3d_early --filter on --json

# count-neutral lead vs base3d (clean, leak-free)
python3 research/signal_engine/tuning_lead.py m2d_s3d_early

# concrete per-name earlier-entry examples
python3 research/signal_engine/tuning_casestudy.py NVDA AMD AAPL

# leak/robustness probe (edge must not appear when you act later)
python3 research/signal_engine/tuning_harness.py --variant m2d_s3d_early --filter on --fill-offset 1 --json

# secondary location guards (§5b): dump a guarded variant, then run the verdict gate vs base3d
python3 research/signal_engine/tuning_harness.py --variant early_vol_50 --filter on --dump /tmp/ev50.json --json
python3 research/signal_engine/tuning_harness.py --variant base3d        --filter on --dump /tmp/base.json --json
python3 research/signal_engine/tuning_gate.py /tmp/base.json /tmp/ev50.json
```

Variant configs live in `VARIANTS` in `tuning_harness.py`. The per-name dumps used for the §3b
gate are written by `--dump <path>` (see `_tuning_out/`). All three drivers import the single
shared harness so the methodology is identical across every experiment.

---

# 8. Reversal Gate — Cut / Re-Buy on the Opposite Cross (Owner's "Liquidity-Sweep" Hypothesis)

> Distinct study, same charter and same `tuning_harness` primitives (leak-audited below). The §3
> kill rule applies unchanged: judged on held-out **drawdown + whipsaw + cut/re-buy quality**,
> never on beating buy-and-hold. Panel: 110 held-out US names, `--json` per variant in
> `_tuning_out/rev/`. Driver: `tuning_reversal.py`.

**The owner's question.** The Pine indicator already *cuts* a position (and later *re-buys*)
when the OPPOSITE signal fires within a few bars of an entry — the intent is to dodge false
breakdowns (MM liquidity sweeps) and to catch the rally after a false sell. The lever tested:
the reversal already exists in the engine (`revBuy`/`revSell`, `REV_BARS=3` on the **lagging
3D MACD** ≈ 9 trading days); does detecting the flip *sooner* — on the **faster 2D MACD** and/or
in **tighter windows** — meaningfully improve held-out drawdown and protect against selling
right before a rally?

## 8.0. Direct answer — NO, it does not considerably improve performance

On the held-out panel **no reversal config — current, faster, or tighter — materially improves
drawdown**, and faster detection actively *worsens* the things that matter. Across all 9 variants
aggregate DD sits in a rounding-error band of **−24.0 to −25.2** vs the no-reversal ablation
(`none` = **−24.45**); the very fastest trigger (`rev1d_6`) buys **+0.43 pp** of DD "improvement"
while shredding compounded return (`cap` 35.1 vs 42.3) and collapsing win-rate (48.2% vs 60.3%).
Worst-loss is essentially flat across the board (−8.5 to −9.4). There is **no considerable
improvement here — there is no improvement at all, on either DD axis.** The lever the owner hoped
for does not exist in this data.

## 8.1. Does the SHIPPED reversal (`rev3d_9`) even beat the no-reversal ablation? — No.

The decisive, leak-free test is the per-name held-out gate vs `none` (the engine with the
reversal logic switched OFF):

- **DD:** `rev3d_9` is shallower-DD on only **30.9%** of names; aggregate DD is **worse** with
  the reversal on (**−24.861** vs `none` **−24.454**).
- **Worst-loss:** `rev3d_9` produces a smaller worst-loss on only **10.0%** of names.
- **Of the 64 names the reversal actually touches** (46 are byte-identical — the logic never
  fires), **38 get DEEPER drawdown vs 26 shallower** (median changed-delta **−0.94 pp**).

So the mechanism **as currently shipped hurts drawdown on the clear majority of the names it
touches, and does not help on a majority overall.** It is not earning its place.

**Does FASTER (2D) detection beat the current 3D?** No — it loses the verdict gate on both axes.
% of names where a faster config is *shallower-DD than `rev3d_9`* (need >50% to "hold"):
`rev3d_6` 26.4 · `rev2d_4` 43.6 · `rev2d_6` 44.5 · `rev2d_9` 38.2 · `rev1d_6` 46.4 — **all <50%**.
% where it gives a *smaller worst-loss* than `rev3d_9`: `rev3d_6` 9.1 · `rev2d_4` 30.9 · `rev2d_6`
29.1 · `rev2d_9` 24.5 · `rev1d_6` 32.7 — **every faster config deepens worst-loss on the
majority of names.** Median DD-delta vs `rev3d_9` is **+0.00 pp** for all (most names untouched).
Faster does not win; it just fires more often into noise.

## 8.2. Whipsaw — the cuts MANUFACTURE head-fakes, they do not dodge drops

The defining metric is **`cut_fwd`** = average forward return *after* a protective cut. A cut
that dodges a real breakdown should show **`cut_fwd` clearly NEGATIVE** (price keeps falling
after we exit). Instead it is **POSITIVE in every single one of the 9 variants** — price *rises*
after the cut. That is the textbook whipsaw signature, and it **scales monotonically with how
fast/tight the trigger is**, which proves the mechanism itself is creating the head-fakes, not
sampling noise:

| trigger speed | variant | `cut_fwd` (NEG=good) | whipsaw % | cap vs `none` (42.29) |
|---|---|---|---|---|
| ablation | `none` | 0.000 | 0.0 | — |
| slow/loose | `rev2d_4` | **+0.118** | 4.8 | +1.24 |
| | `rev2d_6` | **+0.509** | 14.2 | +0.74 |
| | `rev3d_6` | **+1.601** | 24.8 | −3.89 |
| | `rev2d_9` | **+2.246** | 27.1 | −3.90 |
| current | `rev3d_9` | **+2.498** | 31.7 | −5.51 |
| fast/tight | `rev1d_6` | **+3.273** | 35.7 | −7.15 |

`rev1d_6` makes **348 cuts** across the panel, and **>1-in-3 of them see price rally >4% within
20 days.** The tighter the trigger, the worse the head-fake — and it buys **no** drawdown
dividend (DD flat) while paying up to **−7.15 pp** of compounded return.

**Is the re-buy half more useful than the cut half? Yes — but only because it un-does the cut.**
`rebuy_fwd` is positive (+0.31 to +2.57; `rebuy_good_pct` up to 58.8%) — re-buys *do* tend to
re-enter into a rally. But that is the **mirror image of having cut into strength**: the re-buy is
recovering self-inflicted damage, not capturing alpha. The ablations isolate this cleanly:

- **`rev2d_6_cutonly`** (cut, never re-buy): `cut_fwd` **+0.875**, whipsaw 14.3%, **cap 38.69 <
  42.29** — cutting alone is pure whipsaw that destroys return.
- **`rev2d_6_rebuyonly`** (re-buy, never cut): **cap 45.05** — the **only** config that BEATS
  `none`, and it does so by **disabling the cut entirely** (`cut_fwd` 0, one stray re-buy).

In other words the cut leg is a net drag and the re-buy leg is only "good" at cleaning up the
cut leg's mess. **There is no config where the cuts systematically dodge drops.**

## 8.3. Leak audit & subpanel — the verdict is real, not an artifact

- **Leak audit: HOLDS (clean).** Six checks on `tuning_reversal.py` against the `H.*` primitives
  all pass: raw `base3d` confluence buy with no forward-peeking `daily_filter`; reversal crosses
  via `xup`/`xdn` (both `.shift(1)`, strictly backward) mapped by known-date `to_daily("event")`;
  fills at `c[i+1]` with **no same-bar fill**; cut/re-buy windows measured against decision-bar
  indices that are all `≤ i` (backward); `cut_fwd`/`rebuy_fwd` are pure **outcome** metrics that
  never gate entries/exits; `SINCE` boundary consistent. The DD/whipsaw numbers above are
  trustworthy (unlike the §4 *absolute* filtered DD, this sim uses the raw common-exit, so even
  the absolute DD here is leak-free).
- **Subpanel: HOLDS, but only for the inter-config ordering.** Deterministic even/odd ticker
  split (55 names each). The sign of `(rev2d_6 DD − rev3d_9 DD)` is **the same on both halves**
  (A +0.486, B +0.489) — i.e. `rev2d_6` is reproducibly the *gentler of the two reversal
  variants* (higher cap, ~14% whipsaw vs ~28–35%). **But no reversal config beats `none`
  consistently:** `rev2d_6` vs `none` **flips sign across halves** (beats on A +0.232, loses on
  B −0.070). The only stable, reproducible fact is the relative ordering *between reversal
  configs* — not that any of them helps.

## 8.4. Recommendation — keep `REV_BARS=3` on the 3D as a context leg only; promote no faster variant; consider neutering the cut

1. **Promote nothing faster. Do NOT switch the scored gate to 2D or tighten the window.** The §3
   kill rule fires: faster/tighter detection loses the held-out DD *and* worst-loss majority gate
   vs the current `rev3d_9` and vs `none`, and it manufactures more whipsaws (`cut_fwd` and
   whipsaw% both climb monotonically with speed). `rev1d_6`/`rev2d_9` are the **worst** options
   despite firing soonest — earlier detection of the flip is earlier reaction to *noise*.

2. **The honest read on the shipped `rev3d_9` cut: it is a net negative on this panel** (deeper
   DD on the majority of touched names, +2.50 `cut_fwd`, −5.51 pp cap, 31.7% whipsaw). The
   evidence-led move is to **disable the auto-cut leg** (or demote it to display-only "opposite
   signal fired — discretionary review") and, if anything is kept live, keep **only the re-buy
   leg** — `rev2d_6_rebuyonly` is the single config that beat `none` (cap 45.05), precisely
   because it never cuts. If the cut must stay for parity with the owner's Pine, **`rev2d_6` is
   the least-bad cut config** (gentlest: lowest whipsaw among non-inert variants, smallest cap
   loss, reproducible across both subpanels) — but it is a *damage-minimizing* choice, not an
   improvement over `none`.

3. **Charter framing — detect, don't predict (CHARTER §2).** This is the load-bearing point. The
   gate **cannot know** that a breakdown is a market-maker liquidity sweep versus the start of a
   real decline. It only *reacts to the opposite signal flipping* — and on held-out data that
   flip, fired faster, is **more often noise than a real sweep**: the price keeps rising after the
   cut (`cut_fwd > 0`) in every variant. The owner's mechanism is built on a *predictive* claim
   ("this breakdown is fake, hold/re-buy through it") that a reactive signal-flip detector cannot
   make. Speeding it up does not make it more clairvoyant — it makes it react to thinner, noisier
   flips. The lag on the 3D is again **partly load-bearing**: it is what stops the gate from
   cutting on every shallow wobble.

**Honest caveats.** Microscope, not verdict machine: 110 names, single recent regime window
(entries since 2023-06-01, `FWD_K=20`, `WHIP=0.04`), common-exit isolation, daily-bar windows.
The DD band is narrow enough (−24.0 to −25.2) that *no* config is decisively separable on the
aggregate — which is itself the finding: the reversal gate is a **wash on drawdown** and a
**drag on whipsaw + compounding**, in every flavor tested. The one robust, reproducible signal is
directional and unfavorable: faster/tighter ⇒ more whipsaw, less cap, lower win-rate, **no** DD
payoff. Add this to the "tested and killed" ledger alongside the entry-trigger study (§6) and the
regime router (CHARTER §5).

## 8.5. Reproduce

```bash
# variant is a POSITIONAL arg; no arg = print the whole table. Writes _tuning_out/rev/<variant>.json with --dump
python3 research/signal_engine/tuning_reversal.py                       # all 9 configs, one table
python3 research/signal_engine/tuning_reversal.py rev3d_9 --json        # current engine
python3 research/signal_engine/tuning_reversal.py none    --json        # no-reversal ablation
python3 research/signal_engine/tuning_reversal.py rev2d_6 --dump /tmp/rev2d_6.json --json

# the decisive whipsaw read is cut_fwd (must be NEGATIVE to be protective; it is +ve everywhere)
# the verdict gate is per-name %shallower-DD / %smaller-worst-loss vs rev3d_9 AND vs none (need >50%)
```

> **Production note (no code change required).** In the live engine the `cut`/`rebuy` are already
> **display-only markers** (`engine/signal_quality.py` `revSell`/`revBuy` → marker stream), never
> auto-trades — the owner/brain reads them and applies discretion. This study tested *mechanically
> acting* on them; the verdict ("don't go faster; the cut is whipsaw-prone") therefore means **keep
> the markers, keep `REV_BARS=3` on the 3D, and treat the `cut` marker as low-reliability context**,
> not "rip anything out." The owner's ~80–90% manual win-rate comes from judging these cases (charter
> §2c); the mechanical cut reproduces only a whipsaw-prone floor.

---

# 9. Corrected verdict under the OWNER'S risk model — stop-out rate, not held drawdown

## 9.0. Reframe — and an honest revision of §§3–6

The earlier studies (§§3–6) judged every variant on the **max-drawdown of a position held all
the way to the *opposite* confluence signal**. The owner correctly pushed back that **this is not
how they trade.** Their actual process is:

- a **tight hard stop** (≤ −5%, cut decisively the moment the entry thesis breaks),
- their **own manual timing + sector gates** layered on top,
- and the signal used to **pre-emptively surface names onto a standout/watchlist for manual
  eyeballing** — not as an auto-fill.

Under that process the held-to-opposite-cross max-DD is the wrong loss function: a name that dips
−12% before ripping +30% is a **clean win** for them (the stop was never hit on the way they'd
actually size it), while a held-DD metric scores it as a deep drawdown. The metric that matches
their book is the **stop-out rate**: of the entries the signal *surfaces*, how often does price
fake down to −5% first (a bad/fake entry that costs them the stop) versus run favorably without
ever touching the stop (a **clean entry**). Secondary read: **MFE** (median favorable excursion),
i.e. how much room a surfaced name typically offers before any reversal.

**Honest note on what this revises.** The §0/§6 conclusion — *"keep `base3d`; the earlier triggers
are worse on drawdown"* — was **conditional on a risk model the owner does not use.** "Worse on
held drawdown" was true and is *not* retracted; but it was never the deciding question for a
tight-stop watchlist tool. This section re-runs the comparison on the **right** axis (stop-out
rate under a hard −5% / −3% stop, `tuning_stops.py`, same 110 held-out names, leak-audited below).
The headline outcome is **directionally the same** — `base3d` still wins — but for an honest and
*different* reason, and the margins for the "fuller" faster triggers are now thin enough that the
owner's intuition deserves explicit credit (§9.3).

## 9.1. `base3d` vs the key candidates @ −5% hard stop (110 held-out names)

Lower `stop_rate` = fewer fake entries (better). Higher `clean_rate` = more entries that run
without ever touching the stop (better). `med_mfe` = median favorable excursion %, room before
reversal. `avg_signals` = surfaced entries per name (watchlist volume — a tool that surfaces
nothing is useless).

| variant | trigger | avg_signals | stop_rate ↓ | clean_rate ↑ | med_mfe |
|---|---|---|---|---|---|
| **`base3d`** | **incumbent (3D confirmed)** | **8.35** | **38.3** | **45.1** | **5.65** |
| `stochlead3d` | leading-leg (faster) | 11.90 (143%) | 40.1 (+1.8) | 42.0 (−3.1) | 5.35 |
| `m2d_s3d_early` | anticipation (pre-cross) | 10.63 (127%) | 41.0 (+2.7) | 40.6 (−4.5) | 5.19 |
| `m2d_s3d` | 2D MACD (faster) | 13.90 (166%) | 41.4 (+3.1) | 41.2 (−3.9) | 4.96 |
| `early_vol` | **location guard** (ATR-contraction) | 5.25 (63%) | 43.4 (+5.1) | 36.7 (−8.4) | 5.08 |
| `early_hl` | **location guard** (higher-low) | 2.44 (29%) | 42.1 (+3.8) | 35.8 (−9.3) | 5.34 |
| `early_vol_50` | location guard (vol + 50MA) | 1.71 (20%) | 48.3 (+10.0) | 36.7 (−8.4) | 4.96 |
| `early_vol_hl` | location guard (vol + HL) | 1.90 (23%) | 46.0 (+7.7) | 33.9 (−11.2) | 4.71 |

(% = signal count vs base3d. Deltas in parentheses vs base3d's stop_rate/clean_rate.)

**On the aggregate, `base3d` has the lowest stop-out rate (38.3%), the highest clean-entry rate
(45.1%), the highest med-MFE (5.65), *and* a healthy watchlist volume (8.35/name).** It is not a
near-tie on aggregates: every candidate fakes down to −5% *more* often and runs clean *less* often.
The −3% panel is the same shape, just harsher (base 58.6 stop / 33.6 clean; every candidate worse).

## 9.2. The per-name gate — does any earlier/guarded trigger beat base3d on a MAJORITY of names?

The aggregate could hide a candidate that wins on most names by a hair and loses big on a few. So
the decisive test is the **adversarial per-name held-out gate**: align by ticker, and count the
**% of names where the candidate has a *lower* stop_rate than `base3d`** (need **>50%** to "hold").

**No candidate clears 50% — at either stop.** @ −5% (matched-names framing, which already favors the
candidate by dropping names where it emits zero signals):

| candidate | % names lower-stop | median stop-Δ vs base | clean-rate win % | signal count |
|---|---|---|---|---|
| `early_hl` | 47.8% | +0.00 pp | 36.7% | 29% of base ✗ |
| `m2d_s3d_early` | 44.5% | +3.04 pp | 41.8% | 127% |
| `stochlead3d` | 44.5% | +1.90 pp | 41.8% | 143% |
| `early_vol_50` | 46.8% | +12.50 pp | 36.4% | 20% of base ✗ |
| `early_vol_hl` | 46.4% | +0.00 pp | 31.9% | 22% of base ✗ |
| `early_vol` | 39.8% | +7.74 pp | 36.1% | 63% |
| `m2d_s3d` | 38.2% | +3.41 pp | 37.3% | 166% |

Every **median per-name stop-Δ is positive (= more fakeouts than base)**, and every clean-rate
win-% is also <50%. Over the **full** base universe (counting names a candidate never surfaces as
"not better"), the ceiling drops further: best is `stochlead3d` / `m2d_s3d_early` at 44.5%. @ −3%
the picture is the same (best `early_hl` 44.4%, all medians positive).

**Distinguishing the two families:**

- **Plain faster triggers** (`m2d_s3d`, `m2d_s3d_early`, `stochlead3d`): keep or expand the
  watchlist (127–166% of base volume) but **do not reduce fakeouts** — they surface *more* names,
  a larger fraction of which fake down. `stochlead3d` and `m2d_s3d_early` are the **least-bad**
  (44.5% lower-stop, smallest positive median Δ +1.90 / +3.04 pp) — genuinely *close*, but on the
  wrong side of the majority line.
- **Location-guarded variants** (`early_vol`, `early_hl`, `early_vol_50`, `early_vol_hl`): these
  were the live hope — guards meant to surface entries that *survive* a tight stop. The honest
  answer is **no, they do not earn it.** Their headline lower-stop %s (46–48%) are a mirage produced
  by **gutting the watchlist**: 1.7–2.4 signals/name (**20–29% of base**, on 69–90 names not 110).
  They surface so few entries that the per-name comparison is noise — and the ones they do surface
  still fake to −5% on roughly the same fraction. `early_hl` even **flips sign across the subpanel
  split** (Half A +9.4 pp *worse* than base, Half B −1.5 pp better → **UNSTABLE**), confirming the
  thin count is driving it. `early_vol` is the only guarded variant whose stop-Δ sign is *stable*
  across both halves — and it is stably **worse** (+6.6 / +3.7 pp). **Verdict: the location guards
  do not surface tighter-stop-survivable entries; they surface fewer entries.** Same exposure-
  artifact lesson as §5b, now confirmed on the stop-out axis the owner actually cares about.

**Subpanel stability:** deterministic odd/even ticker split, `--stop 0.05`, no code modified.
`base3d` stop_rate is **identical (38.3 / 38.3)** on both halves — the baseline is rock-stable. The
candidates do not produce a *stable* edge on either half; the only stable candidate sign (`early_vol`)
is stably negative.

## 9.3. Watchlist framing — false positives are cheap; earlier/cleaner surfacing is the point

For the owner's *actual* tool — **pre-emptive surfacing → manual eyeball → tight stop → sector
gate** — the cost structure is asymmetric and matters here:

- **A false positive is cheap.** A surfaced name that looks wrong gets discarded at the eyeball
  step (zero cost) or, if taken and it breaks, cut at −5% (small, bounded cost). The owner is
  *paid to throw most surfaced names away.* So a tool is not disqualified by a high raw stop_rate
  — it is disqualified by **surfacing the wrong *set* of names**, or by **surfacing too few**.
- **A false negative — a clean mover never surfaced — is the expensive error.** This is what
  argues *for* earlier/fuller surfacing and against the gutting guards.

Under that cost structure the relevant question is **not** "which variant has the lowest stop_rate
on the names it picks" but **"which variant surfaces the broadest set of clean movers early, for a
human to filter."** On that question:

- The **location guards lose decisively** — they don't lower the fakeout rate *and* they amputate
  the watchlist (20–29% of base). For a surfacing tool, **a guard that throws away 70–80% of
  candidates to achieve no better hit-rate is the worst trade in the table.** The cheap-false-
  positive logic kills them: you do not pay to *suppress* candidates when discarding is free.
- The **earlier/fuller triggers are defensible *as a surfacing layer*** even though they fail the
  scored gate: `stochlead3d` (143% volume, +1.8 pp stop) and `m2d_s3d_early` (127% volume, the
  earliest read) surface *more* clean movers earlier, and the owner's eyeball + sector gate + tight
  stop absorb the extra fakeouts they admit. They are bad *auto-buys* and acceptable *surfacers*.
- The **early-anticipation marker (`m2d_s3d_early`) earns its place — but only in its already-
  intended role.** §6 proposed it as a **display-only hollow pre-cross dot**, never a scored buy.
  The stop-out re-frame *strengthens* that recommendation: a pre-emptive "a `base3d` buy may be
  approaching" annotation is exactly a surfacing aid, the false positives are cheap, and the
  owner's discretion is the gate. It does **not** earn promotion into the scored buy quality (its
  per-name stop-Δ is still +3.04 pp worse), but it **does** earn its keep as the earliest honest
  heads-up on the watchlist.

## 9.4. Honest verdict + recommendation

1. **`base3d` remains the signal to *score* — now confirmed on the owner's own risk axis, not
   just the held-DD axis.** It has the lowest stop-out rate (38.3% @ −5%), highest clean rate
   (45.1%), highest med-MFE, a stable baseline across subpanels, and a healthy surfacing volume.
   No earlier or guarded variant lowers the stop-out rate on a **majority** of held-out names at
   either stop. The §6 "keep base3d" call **survives the re-framing** — for the corrected reason.

2. **Credit where due — the owner's intuition was directionally right, and the margins are thin.**
   The owner argued the earlier triggers were being judged on the wrong metric, and on the *right*
   metric the gap **narrows from "clearly worse on drawdown" to "+1.8–3.0 pp worse stop-rate, fails
   the majority gate by ~5–6 points."** `stochlead3d` and `m2d_s3d_early` are genuinely close
   (44.5% of names lower-stop) **and** surface 127–143% of base volume. They are not good enough to
   *score*, but they are good enough to **surface** — which is the role the owner actually puts them
   in. That is a real, credited revision, not a rubber-stamp of the old conclusion.

3. **Surface the earlier triggers as display-only watchlist context; score none of them.**
   Concretely: keep `base3d` as the scored confirmed BUY; render `m2d_s3d_early` as the **hollow
   pre-cross "early-anticipation" dot** (§6.2) and optionally let `stochlead3d` widen the *standout
   surfacing* set — both clearly labeled, never folded into conviction or `quality`, with the
   health note that they admit more −5% fakeouts and are intended for manual filtering.

4. **The location guards are now closed on BOTH axes.** Killed on held-DD as an exposure artifact
   (§5b); killed here on stop-out rate because they reduce fakeouts only by reducing *exposure*
   (20–29% of base volume), flip sign across subpanels (`early_hl`), or are stably worse
   (`early_vol`). Do not ship them as either a buy or a surfacing layer.

**Honest caveats.**

- **The floor is mechanical, not signal failure.** A ~38–48% stop-out rate at a −5% stop on a
  panel of liquid, mostly high-beta US names is largely **the names, not the signal**: high-beta
  equities routinely wiggle −5% intraday/intraweek, so *any* entry method stops out roughly half
  the time under a tight hard stop. `base3d`'s 38.3% is the *best* in the table, but no signal on
  this universe will push it far below ~one-in-three without giving up the watchlist.
- **The user's process lifts that floor in ways this backtest cannot see.** The stop-out rate here
  is **mechanical entry-at-next-close with a blind −5% stop and no discretion.** The owner's actual
  **manual timing, sector gates, and ≥80% discretionary win-rate (charter §2c)** filter the
  surfaced set further — so the *realized* fake-entry rate on names they actually take is lower than
  any number in this table. This section bounds the **tool's** raw surfacing quality, not the
  **owner's** realized hit-rate.
- **Scope.** 110 held-out names, single recent regime (entries since 2023-06), −5% and −3% stops
  only, common-exit isolation. Leak-audited (§9.5): entry = next daily close, triple-barrier walks
  strictly forward, all guards backward-looking; the only forward-looking input (`daily_filter`,
  HELD=3) is `--filter`-gated *off* by default and not among the 7 audited variants — flag if ever
  scored. MFE captures on the same bar as the stop touch (mild intrabar optimism, not a forward
  leak). The clean-vs-fake conclusion and the relative base-wins ordering are leak-free.

## 9.5. Reproduce

```bash
# stop-out / clean-entry rates per variant at a given hard stop (default 0.05)
python3 research/signal_engine/tuning_stops.py --stop 0.05            # all variants, one table
python3 research/signal_engine/tuning_stops.py --stop 0.03            # tighter stop panel
python3 research/signal_engine/tuning_stops.py --stop 0.05 --dump research/signal_engine/_tuning_out/stop/

# the decisive read is the PER-NAME gate vs base3d: %names lower-stop must be >50% to "hold"
#   (every candidate is <50% at both stops); median per-name stop-Δ must be NEGATIVE (it is +ve everywhere)
# subpanel stability: run per odd/even ticker half at --stop 0.05; base3d is 38.3/38.3, candidate signs must agree
```
