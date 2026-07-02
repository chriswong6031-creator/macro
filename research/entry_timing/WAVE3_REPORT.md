# Wave-3 Report — CN/HK Replication of the COILED Ranking Bonus + Trigger-Speed Study

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE spec; §8 ledger carries the
> **Wave-3 pre-registration (2026-07-02)** block that defines the gates below) and
> `research/entry_timing/WAVE2_REPORT.md` (the US wave-2 SHIP). Machinery reused: `wave1.py` /
> `wave2.py` (labels, features, fires via `tuning_harness`, per-fire outcomes, cohort matrices,
> multiprocessing), extended by `wave3.py`.
>
> **Mandate (spec §8 Wave-3 pre-registration):** (A) replicate the wave-2 COILED edge on CN and HK
> close-only panels and ship per-market iff that market passes its gate + robustness; (B) study
> faster triggers inside vs outside the COILED state on the deep US panel to inform wave-4 fire-layer
> design (nothing from B ships this wave). Gates are graded **exactly as written — no
> re-interpretation, no threshold edits** (spec §7). Close-only markets: `low_stop5` + H4 skipped.

---

## 0. Verdict at a glance

| gate | market | verdict | headline |
|---|---|---|---|
| **G-CN** | CN | **PASS** | clean15 spread +7.33pp; both halves + (+6.07 / +11.45); stop5 −6.21pp (better); n_COILED=10,784; per-name maj 59.26%; clean10/20 + and dead-money lower |
| **G-HK** | HK | **FAIL** | clean15 spread **−0.84pp** (< 3pp); half-sign **flips** (pre −2.99, post +1.63); per-name maj **46.05%** (< 55%); clean10 spread **−1.69** (robustness fails) |
| **B** (trigger study) | US | 2 of 4 PASS | `m1d_s3d` PASS (only trigger that shrinks the FP tax inside COILED); `m2d_s3d_early` PASS; `stochlead3d` FAIL (clean15 −2.06 > 2pp); `m2d_s2d` FAIL (no capture gain) |

**SHIP RULE (pre-committed):** ship the CN/HK COILED bonus per-market iff that market passes gate + robustness.
- **CN → SHIP** the COILED ranking bonus (with the pre-declared 3.3y single-regime caveat).
- **HK → DO NOT SHIP.** The edge does not replicate on HK; the wave-2 US SHIP does not extend here.

---

## 1. Config & panels

Produced by `research/entry_timing/wave3.py` (reuses `wave1.py`/`wave2.py` labels, features, outcomes,
cohort matrices). Dates round-tripped as ISO strings in worker args (the wave-2 ms→ns DatetimeIndex
serialization bug class was explicitly avoided).

| | **CN** (`wave3_cn`) | **HK** (`wave3_hk`) | **Triggers** (`wave3_triggers`, US) |
|---|---|---|---|
| panel | `china_search/closes.parquet` | `hk_search/closes_deep.parquet` | `data/stocks/*.parquet` |
| names (≥ min_bars) | 1,382 | 157 | 211 |
| min_bars | 800 | 800 | 1,500 |
| eval_start | 2022-09-01 | 2012-01-01 | 2012-01-01 |
| half cut | 2024-09-24 (stimulus pivot) | 2020-01-01 | ticker even/odd |
| sector cohort | `china_search/members.parquet` (12 sectors) | `hk_breadth/constituents.parquet` | `constituents.parquet` |
| theme cohort | `baskets_china/membership.json` | — | — |
| m2d_s3d fires | 20,502 | 8,576 | 12,797 |
| runtime | 323.3s (6w) | 38.0s (6w) | 205.1s (6w) |

- **Trigger:** `m2d_s3d` (2D MACD × 3D StochRSI), the wave-1/2 gate passer; `base3d` carried as reference.
- **COILED (sector):** `in_washout_ctx AND h6_cohort_sector ≥ 0.40`.
- **noncoiled_washout (NCW):** `in_washout_ctx AND h6_cohort_sector < 0.40`.
- **STAR:** `COILED AND bull_div`.
- Close-only panels → `low_stop5` and all H4 (volume) features skipped, exactly as pre-declared.

---

## 2. Verbatim gate grading

### G-CN
> *COILED-vs-noncoiled_washout clean15 spread ≥ 3pp; same sign in BOTH halves (2024-09-24 split); COILED
> stop5 not worse by > 1pp; n_COILED ≥ 400; per-name majority ≥ 55% (names with ≥ 3 fires each side).
> Robustness: spread sign preserved at clean10 AND clean20; COILED dead_money < noncoiled.*

CN, `m2d_s3d` (T1 pooled + T3 halves + T4 per-name):

| metric | COILED | NCW | clause | verdict |
|---|---:|---:|---|:--|
| clean15 (pooled) | 35.57 (n=10,784) | 28.24 (n=6,490) | spread **+7.33** ≥ 3pp | ✓ |
| pre-half clean15 (→2024-09-24) | 29.79 (n=7,388) | 23.72 (n=4,225) | spread **+6.07** (+) | ✓ |
| post-half clean15 (2024-09-24→) | 48.14 (n=3,396) | 36.69 (n=2,265) | spread **+11.45** (+) | ✓ |
| both halves same sign (positive) | — | — | required | ✓ |
| stop5 | 45.72 | 51.93 | COILED **−6.21pp (better)** ≤ +1pp | ✓ |
| n_COILED | **10,784** | — | ≥ 400 | ✓ |
| per-name majority (T4, ≥3 each) | **59.26%** of 1,139 names | — | ≥ 55% | ✓ |
| **robustness** clean10 | 43.03 | 34.88 | spread **+8.15** (+) | ✓ |
| **robustness** clean20 | 29.95 | 23.17 | spread **+6.78** (+) | ✓ |
| **robustness** dead_money | 5.06 | 6.36 | COILED < NCW | ✓ |

**G-CN = PASS.** Every clause clears with margin. Shape identical to the US wave-2 SHIP: COILED cleans
more, stops less, dead-moneys less, per-name majority ~2:1, both regime halves positive. The post-half
(post-stimulus) spread is the larger (+11.45), i.e. the edge is strongest in the very regime the owner
most cares about — but see caveat §5.1 (both halves live inside one macro cycle).

### G-HK
> *Same as G-CN with n_COILED ≥ 200 (2020-01-01 split).*

HK, `m2d_s3d`:

| metric | COILED | NCW | clause | verdict |
|---|---:|---:|---|:--|
| clean15 (pooled) | 32.76 (n=3,446) | 33.60 (n=2,723) | spread **−0.84** ≥ 3pp | ✗ |
| pre-half clean15 (→2020-01-01) | 34.66 (n=1,532) | 37.65 (n=1,352) | spread **−2.99** (−) | — |
| post-half clean15 (2020-01-01→) | 31.24 (n=1,914) | 29.61 (n=1,371) | spread **+1.63** (+) | — |
| both halves same sign | — | — | **flips (− then +)** | ✗ |
| stop5 | 46.89 | 46.13 | COILED +0.76pp worse ≤ +1pp | ✓ |
| n_COILED | 3,446 | — | ≥ 200 | ✓ |
| per-name majority (T4, ≥3 each) | **46.05%** of 152 names | — | ≥ 55% | ✗ |
| **robustness** clean10 | 40.25 | 41.94 | spread **−1.69** (−) | ✗ |
| **robustness** clean20 | 27.60 | 27.07 | spread +0.53 (+) | ✓ |
| **robustness** dead_money | 4.82 | 5.62 | COILED < NCW | ✓ |

**G-HK = FAIL.** Four independent clauses fail: the pooled spread is negative (−0.84, well below the +3pp
bar), the half-sign flips, the per-name majority is a *coin-flip loser* (46.05%, i.e. COILED wins on a
minority of names), and clean10 robustness inverts. The only clauses HK passes are stop5 (a wash, +0.76pp)
and dead-money — not enough. On HK, COILED does not discriminate durable troughs from lone washouts; the
cohort-arming mechanism that carried US and CN does not survive here. (Mechanistic note: HK's `in_washout`
stratum is already the strong cell — clean15 33.15 vs ALL 33.24 — and adding the sector-cohort screen
neither cleans more nor stops less; the HK sector-cohort matrix from `hk_breadth/constituents.parquet`
may simply be too coarse / too few members per sector to mark a real crowd washout.)

### B — trigger-speed study (deep US panel; informs wave-4, ships nothing)
> *Per faster trigger, vs `m2d_s3d`-inside-COILED baseline. B-PASS iff inside COILED: clean15 within 2pp
> of baseline, stop5 not worse by > 2pp, capture better (median premium-over-trough lower OR recall_B15
> higher), ticker-half sign-stable. Also report the interaction: for each fast trigger, the
> (fast − m2d_s3d) stop5 gap inside vs outside COILED — did the state shrink the FP tax?*

Baseline `m2d_s3d` inside COILED (T-B): clean15 **39.29**, stop5 **39.07**, dead 7.28, med_premium **7.96**,
recall_B15 **12.48**, ticker halves even 41.00 / odd 37.49 (even > odd).

| trigger (inside COILED) | n | clean15 (Δ vs base, ≤2pp?) | stop5 (Δ, ≤+2pp?) | med_prem (lower?) | recall_B15 (higher?) | capture? | half-stable? | **B verdict** |
|---|---:|---|---|---|---|:--:|:--:|:--:|
| m2d_s3d (baseline) | 3,174 | 39.29 (—) | 39.07 (—) | 7.96 | 12.48 | — | even>odd | — |
| **m2d_s3d_early** | 2,218 | 38.01 (**−1.28** ✓) | 40.22 (**+1.15** ✓) | 6.47 (✓) | 7.93 (✗) | **✓** | even38.81>odd37.19 ✓ | **PASS** |
| **stochlead3d** | 2,517 | 37.23 (**−2.06** ✗) | 40.09 (+1.02 ✓) | 6.40 (✓) | 8.63 (✗) | ✓ | ✓ | **FAIL** (clean15 >2pp below) |
| **m2d_s2d** | 3,041 | 38.05 (−1.24 ✓) | 39.53 (+0.46 ✓) | 8.08 (✗) | 12.08 (✗) | **✗** | ✓ | **FAIL** (no capture gain) |
| **m1d_s3d** | 3,787 | 37.68 (−1.61 ✓) | 37.87 (**−1.20**, better ✓) | 6.43 (✓) | 10.63 (✗) | **✓** | even38.70>odd36.66 ✓ | **PASS** |

**Key interaction read — did the COILED state shrink the false-positive (stop5) tax of the fast trigger?**
For each trigger, `(fast − m2d_s3d)` stop5 gap **inside** vs **outside** COILED:

| trigger | inside-COILED stop5 gap | outside-COILED stop5 gap | did the state shrink the FP tax? |
|---|---:|---:|:--|
| m2d_s3d_early | +1.15 | −0.31 | **No** — slightly worse inside |
| stochlead3d | +1.02 | −0.26 | **No** |
| m2d_s2d | +0.46 | +0.14 | **No** (marginally worse inside) |
| **m1d_s3d** | **−1.20** | +0.51 | **YES** — m1d_s3d stops out *less* than m2d_s3d **only inside** COILED (−1.20), but *more* than m2d_s3d outside (+0.51). The state flips the FP economics of the fastest trigger. |

**B synthesis.** Two triggers pass the pre-registered B gate: `m2d_s3d_early` and `m1d_s3d`. But only
**`m1d_s3d` shrinks the FP tax** — it is the *only* fast trigger whose stop-out advantage exists inside the
COILED state and reverses outside it, which is exactly the COILED thesis (§6): relocate selectivity into
the setup state so a faster trigger can be used without inheriting its false positives. `m1d_s3d` inside
COILED gives +1d-faster lead (3d vs 6d), 1.5pp cheaper entry (premium 6.43 vs 7.96), *lower* stop5
(37.87 vs 39.07), and clean15 within 1.6pp — a genuine earliness win **paid for by the state, not the
trigger's own selectivity**. This is the strongest wave-4 fire-layer candidate. `m2d_s3d_early` passes the
gate but does NOT get the interaction benefit (its lower stop is a property of the trigger everywhere, and
inside COILED it's actually +1.15pp worse than the baseline trigger) — a weaker candidate.
`stochlead3d` narrowly misses on clean15 (−2.06 > 2pp). `m2d_s2d` fails because it buys nothing on the
capture axis (premium *higher*, recall *lower* than baseline) — it is essentially the baseline with a
slightly faster stoch and no advantage. **Nothing from B ships this wave** (per §8 directive); B nominates
`m1d_s3d` as the wave-4 fire-layer trigger to design against.

---

## 3. Supporting tables

### CN — per-stratum economics (T1, m2d_s3d)
The ladder is monotone, matching US: **NCW < in_washout < ALL < coiled_no_div < COILED < STAR** on
clean15, mirrored on stop5.

| stratum | n | stop5 | clean10 | clean15 | clean20 | dead_money | med_mfe63 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL | 20,502 | 47.93 | 39.99 | 32.62 | 27.19 | 6.69 | 12.46 |
| in_washout | 17,357 | 47.99 | 40.02 | 32.86 | 27.44 | 5.55 | 12.89 |
| noncoiled_washout | 6,490 | 51.93 | 34.88 | 28.24 | 23.17 | 6.36 | 9.91 |
| coiled_no_div | 8,284 | 45.93 | 42.56 | 34.97 | 29.54 | 5.21 | 14.33 |
| **COILED** | 10,784 | **45.72** | **43.03** | **35.57** | 29.95 | **5.06** | 14.65 |
| **STAR** | 2,500 | **45.00** | **44.56** | **37.56** | 31.32 | **4.56** | 15.73 |
| div_only_noncoiled | 1,496 | 52.94 | 33.36 | 27.61 | 21.79 | 7.09 | 9.14 |

`div_only_noncoiled` is a dud (clean15 27.61 < ALL 32.62) — the OOS confirmation, again, that H3
(divergence) carries no edge standalone and pays off only inside the cohort washout (STAR). STAR
additivity holds on CN: STAR clean15 37.56 ≥ COILED 35.57, STAR stop5 45.00 ≤ COILED 45.72.

**CN theme cohort (T3):** works but weaker than sector — COILED_theme clean15 34.44 vs ncw_theme 32.37
(+2.07pp), both halves positive (pre +1.93, post +2.32). Sector cohort is the sharper discriminator
(+7.33 vs +2.07); theme is the fallback for unmapped names, same as US.

**CN ranking (T5/G4-analog):** quartiles by cohort intensity clean15 27.87 / 28.63 / 37.95 / 37.00,
Q4−Q1 **+9.13pp**, Spearman **0.8** (p=0.20). Directionally monotone and supportive of a graded bonus,
though the top two quartiles are nearly tied (not the perfect 1.0 seen on US) — the CN discrimination is
more of a step (Q1/Q2 low, Q3/Q4 high) than a smooth ramp.

**CN recall economics (T8, the hard-gate warning):** ALL recalls 49.19% of B15 durable bottoms; COILED
recalls 34.29%, STAR only 8.46%. COILED trap-fire 22.40% vs ALL 38.04%. COILED is higher-precision but —
notably — retains *much more* recall on CN than on US baskets (34% vs 7%), because COILED is a far larger
share of CN fire volume (53% of m2d_s3d fires vs ~7% on US). Still ship as a **graded ranking bonus, not a
hard gate** (a hard gate would still cut recall ~30%, and the directive is a bonus regardless).

### HK — per-stratum economics (T1, m2d_s3d)
The ladder is **broken** — the whole point of the G-HK fail:

| stratum | n | stop5 | clean10 | clean15 | dead_money |
|---|---:|---:|---:|---:|---:|
| ALL | 8,576 | 45.95 | 41.01 | 33.24 | 7.54 |
| in_washout | 6,507 | 46.63 | 40.94 | 33.15 | 4.96 |
| noncoiled_washout | 2,723 | 46.13 | 41.94 | **33.60** | 5.62 |
| COILED | 3,446 | 46.89 | 40.25 | **32.76** | 4.82 |
| STAR | 872 | 48.05 | 38.88 | 32.57 | 4.24 |

COILED clean15 (32.76) is *below* NCW (33.60) and even below in_washout (33.15). STAR is worse still
(32.57 clean15, 48.05 stop5 — the *highest* stop-out). On HK the cohort screen adds noise, not signal.
Only dead-money is directionally right (COILED 4.82 < NCW 5.62), consistent with cohort washout marking
"not-dead" names but failing to mark *liftoff* names. HK T5 Q4−Q1 clean15 spread +0.28, Spearman 0.2
(p=0.80) — flat, no ranking signal.

---

## 4. Tencent case (HK panel, `0700.HK`)

The framework's canonical trap. Question: would COILED have kept the owner OUT of the 2021-23 trap
bounces and admitted the 2024+ turn? Reading the actual `tencent_case` fires (`coiled` / `star` /
`clean15` / `stop5` / `mfe63` on each m2d_s3d fire):

**The 2021-23 structural bear (the trap the owner must avoid) — COILED did NOT protect here.**
Tencent fired 15 times from 2021-01 to 2023-10. The gate labeled **most of them COILED** because the
whole HK internet sector was washed out together (high `h6_cohort_sector`) — cohort washout was exactly
what the owner *shouldn't* have trusted in a genuine structural bear:

- `2021-04-23` COILED=**true** (cohort 0.75) → **stop5=1**, mfe63 +0.48% (a trap bounce that died; COILED said buy)
- `2021-08-11` COILED=true, **STAR=true** (cohort 0.59, bull_div) → **stop5=1**, mfe63 +8.82% (STAR — the *high-conviction* cell — walked into a stop-out)
- `2021-10-08` COILED=true (0.44) → **stop5=1**, mfe63 +2.72%
- `2022-01-12` COILED=true (0.60) → neither clean nor stop, mfe63 +5.02% (dead chop)
- `2022-03-25` COILED=true (0.80) → mfe63 +8.72%, no clean15 (another trap)
- `2023-03-28` COILED=true (0.75) → **stop5=1**, mfe63 +0.88%
- `2023-10-10` COILED=true (0.60) → **stop5=1**, mfe63 +5.85%

Across 2021-2023, COILED=true fires stopped out or went nowhere repeatedly. **COILED did NOT keep the
owner out of the Tencent trap** — it actively flagged the sector-wide washout bounces that failed. The
one genuine 2022 turn it caught (`2022-11-02` COILED=true cohort 0.90 → clean15=1, mfe63 **+97.36%**, the
real bottom) is offset by ~6 COILED stop-outs/dead fires in the same bear. This is the §5-H5 trap lesson
in the flesh: in a structural bear, cohort washout recurs and fails serially — the crowd is washed out
because the *whole sector is broken*, not because a durable bottom is forming.

**The 2024+ turn (the recovery the owner should be admitted to) — COILED did admit it, cleanly.**
- `2024-08-13` coiled=**false** (washout_ctx false) → clean15=1, mfe63 +27.98% (COILED *missed* this one — not washed out on the cohort at fire)
- `2025-01-28` COILED=true, **STAR=true** (cohort 0.45, bull_div) → **clean15=1**, mfe63 **+34.59%** (STAR admitted the real turn cleanly, no stop)
- `2025-05-02` COILED=true (0.80) → **clean15=1**, mfe63 +13.42%
- Non-coiled 2024+ fires (`2024-12-09` stop5=1; `2025-07-17` clean15=1) are mixed — outside COILED it's a coin flip.

**Plain-language story.** On the single most important name in the framework, COILED **fails the trap
half of its mandate and passes the admission half.** It did not keep the owner out of the 2021-23 trap
bounces — it labeled them COILED (and even STAR once, 2021-08) because the entire HK internet complex was
washed out in unison, and those cohort-washed bounces stopped out one after another. It *did* admit the
2024-25 turn (STAR 2025-01-28 → +34.6% clean, COILED 2025-05-02 → +13.4% clean), though it also missed
the first leg (2024-08-13, not washed-out-enough at the fire). This single-name story is fully consistent
with the aggregate G-HK FAIL: **on HK the cohort-washout arming does not separate durable troughs from
trap bounces**, and Tencent is the archetype of why. It is a caution against reading the US/CN SHIP as a
Tencent solution — the exact name that motivated the trap axis is the name where the shipped mechanism
does not help on its home market.

---

## 5. Honest caveats

1. **CN is 3.3 years, one macro regime (pre-declared).** EVAL_START 2022-09-01 → today is ~3.3y. The
   2024-09-24 half split cuts a single stimulus cycle into "before/after policy pivot," NOT two
   independent macro regimes. Both CN halves being positive is real within-cycle robustness but is **not**
   the multi-regime evidence the US wave-2 basket panel (2015-2025, GFC-recovery through COVID through
   2022 bear) provided. The CN SHIP rides on a single-regime pass — treat it as provisional, to be
   re-graded when a second CN regime accrues. This caveat was written into the pre-registration before the
   run; the pass does not retire it.

2. **Close-based barriers (both CN/HK).** stop5/clean15 use close crossings, not intrabar highs/lows (no
   CN/HK intraday, no reliable open) — `low_stop5` was skipped by design. Real fills clip stops slightly
   more often; the bias applies equally to COILED and NCW, so it shifts absolute rates, not the
   COILED-vs-NCW spread verdicts. For CN this leaves the *direction* of G-CN intact; for HK it does not
   rescue an already-negative spread.

3. **Effective n < printed n (both panels).** Fires on the same name days apart share overlapping 126d
   forward windows → serially correlated outcomes; printed n (CN COILED 10,784; HK 3,446) **overstates**
   independent sample size. Defenses: the per-name majority (CN 59.26% of 1,139 names) and both-half
   consistency (CN) show the CN edge is spread across names and both sub-regimes, not a few autocorrelated
   clusters. On HK the per-name majority (46.05%) is itself a fail, so the effective-n concern compounds
   the negative verdict rather than threatening a positive one.

4. **CN cohort is coarse (12 sectors).** `china_search/members.parquet` has 12 sectors; a ≥40% peer
   washout screen on a 12-sector partition is a blunter crowd measure than the US GICS/basket cohorts.
   That G-CN passes anyway is reassuring; but the CN cohort signal is a coarser instrument, and the CN
   T5 near-tie of Q3/Q4 (Spearman 0.8, not 1.0) is likely a symptom of that coarseness.

5. **HK cohort may be under-membered.** The G-HK fail could be genuine (the mechanism doesn't work on HK)
   or an artifact of a thin/coarse `hk_breadth/constituents.parquet` sector map (157 names). The report
   does not adjudicate — under the pre-registered gate, HK **fails as-built**, and that is the shippable
   verdict. A future wave could re-test HK with a richer cohort map before concluding the mechanism is
   dead on HK; nothing here ships for HK in the meantime.

6. **B ships nothing.** Per the §8 directive, the trigger study is wave-4 input only. `m1d_s3d` is the
   nominated fire-layer trigger (the sole FP-tax-shrinking result), but it has not been through
   `walk_forward.py`, label-sensitivity, or an OOS panel — it is a hypothesis for wave-4, not a shippable
   change.

---

## 6. Ship recommendation (per market)

- **CN → SHIP** the COILED ranking bonus (graded, sector-cohort-armed, `bull_div` = STAR high-conviction
  sub-cell), **never a hard gate**, mirroring the US wave-2 ship — with the pre-declared 3.3y
  single-regime caveat stapled to it and a come-back re-grade when a second CN macro regime accrues.
- **HK → DO NOT SHIP.** G-HK fails four clauses (spread negative, half-sign flips, per-name majority a
  minority, clean10 robustness inverts). The Tencent case corroborates: cohort washout does not separate
  durable troughs from trap bounces on HK. The US/CN mechanism does not extend to HK as-built.
- **B → nominate `m1d_s3d` for wave-4** as the fire-layer trigger (only trigger that stops out *less* than
  m2d_s3d inside COILED and *more* outside — the FP-economics inversion the COILED architecture predicts).
  `m2d_s3d_early` is a weaker second (passes the gate, no interaction benefit). Nothing ships from B.

## 7. Ledger entries (for §8 of the spec)

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-02 | **Wave 3 CN** — COILED replication, `china_search` panel (1,382 names, 2022-09-01+, 20,502 m2d fires), half 2024-09-24 | **PASS → SHIP (single-regime caveat)** | clean15 +7.33pp (35.57 vs 28.24); halves +6.07 / +11.45 (both +); stop5 45.72 ≤ 51.93 (−6.21); n_COILED 10,784; per-name maj 59.26%/1,139; clean10 +8.15, clean20 +6.78, dead-money 5.06<6.36 | WAVE3_REPORT.md §2 |
| 2026-07-02 | **Wave 3 HK** — COILED replication, `hk_search` panel (157 names, 2012-01-01+, 8,576 m2d fires), half 2020-01-01 | **FAIL → DO NOT SHIP** | clean15 spread −0.84 (32.76 vs 33.60); half-sign flips (pre −2.99, post +1.63); per-name maj 46.05%/152; clean10 −1.69; stop5 wash (+0.76); only dead-money right (4.82<5.62) | WAVE3_REPORT.md §2 |
| 2026-07-02 | **Wave 3 Tencent case** (`0700.HK`) | trap axis NOT solved on HK | 2021-23: ≥6 COILED stop-outs/dead fires incl STAR 2021-08 stop5; one real 2022-11 turn (+97% mfe). 2024+: STAR 2025-01-28 clean15 +34.6%, COILED 2025-05-02 +13.4% admitted, but missed 2024-08-13 | WAVE3_REPORT.md §4 |
| 2026-07-02 | **Wave 3 B — trigger speed inside COILED** (US deep, 5 triggers × in/out) | 2/4 PASS; `m1d_s3d` sole FP-tax-shrinker; ships nothing | m1d_s3d inside: clean15 37.68 (−1.61), stop5 37.87 (−1.20 better), interaction −1.20 in vs +0.51 out; m2d_s3d_early PASS no interaction; stochlead3d FAIL c15 −2.06; m2d_s2d FAIL no capture | WAVE3_REPORT.md §2/§6 |
