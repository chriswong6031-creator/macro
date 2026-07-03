# H4 Phase-0 — Within-Universe Reversal on the Expanded HK Universe

**VERDICT: KILL (small-cap primary). The pre-registered short-horizon reversal signal has the WRONG SIGN with power on the expanded HK universe — the deepest-loser quintile UNDERPERFORMS the shallowest by −0.9%/mo (t_HAC −2.14, DSR 0.00, split-half sign-stable). This is 1-month momentum, not reversal. Controls confirm the kill: the mega-cap panel is weakly-negative/insignificant (t −1.03), reproducing the known `rev_st` NO-GO. NOT wired.**

Pre-registration: `research/H4_PREREG.md` (committed before any run, separate commit `aacd836`).
Harness: `scripts/h4_reversal_phase0.py`. Raw run: `reports/artifacts/h4-phase0-run.json`.

---

## Data state STAMP (exact local state read)

- **Union = 545 names** = `data/hk_stocks_ext/*.parquet` (**388** ext, deep OHLCV) ∪ `data/hk_stocks/*.parquet`
  (**157** mega-cap); overlap = 0.
- `hk_stocks_ext` is **GITIGNORED (R2-destined)**; the isolated worktree's copy is a stub (`_checkpoint.json
  n_fetched=0`). The 388 real parquets were read locally from the fetched sibling worktree
  `.../worktrees/amazing-blackburn-5d2027/data/hk_stocks_ext/`. Store max date **2026-07-03**.
- Return-usable panel range after HSI clip: **2000-01-03 → 2026-06-12**.
- Benchmark `_HSI` (`data/hk_search/_HSI_deep.parquet`) ends **2026-06-12** (18 days staler than the price
  store) → panel clipped to the last HSI date for HSI-relative returns. Stamped.
- Control-2 source `data/hk_search/closes_deep.parquet`: **67 names first-valid pre-2005** (survivorship-selected,
  stale 2026-06-18, close-only).

---

## Gates-vs-results table

| Trial | fill | n_months | L/S mean/mo | t_HAC | rank-IC | DSR (n_trials=30) | split-half sign | eff-N | med held | Gate outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| **PRIMARY** (low-ADV cohort, whole-univ z) | next-open | 308 | **−0.92%** | **−2.14** | −0.016 | **0.00** | stable (−/−) | 308 | 20 | **KILL** — sig. negative, DSR fail |
| **SECONDARY** (low-ADV, within 13-sector z, non-PIT) | next-open | 314 | −1.13% | −2.46 | −0.020 | 0.00 | stable (−/−) | 276 | 18 | **KILL** — sig. negative |
| CONTROL 1 (157 mega-cap, whole panel) | next-close* | 314 | −0.40% | −1.03 | −0.004 | 0.0012 | stable (−/−) | 314 | 23 | NO-GO (insig.) — confirms kill |
| CONTROL 2 (deep-67, survivorship ceiling) | next-close* | 314 | −0.46% | −1.25 | −0.002 | 0.0007 | stable (−/−) | 314 | 14 | NO-GO (insig.) — labelled |

\* **Fill deviation (labelled):** the pre-reg mandated next-open fills. The `hk_stocks` mega store has `open`
populated in only 22 of 6603 rows (~99.9% NaN historical), and `closes_deep` is close-only — so next-open fills
are impossible for both controls. Controls fall back to a **next-close fill** (enter t+1 close), disclosed here;
controls are not decision-grade (confirm-a-kill / survivorship ceiling), so the fill downgrade does not affect the
verdict. PRIMARY/SECONDARY keep the pre-registered next-open fill (ext store has opens).

**GO gate (pre-registered):** BH-reject AND DSR≥0.90 AND split-half sign-stable AND eff-N≥12 AND HAC-t
supports (|t|≥2 **same/positive sign**). The reversal hypothesis predicts a **positive** L/S (deepest losers
rebound). The observed L/S is significantly **negative** on both gated trials → the GO gate fails on the sign,
not the power. BH-FDR rejects both (PRIMARY q=0.032, SECONDARY q=0.028) — but rejection here means "significantly
non-zero in the wrong direction," which is a **KILL**, not a GO.

---

## Split-half sign-stability

Both halves of every trial carry the SAME negative sign — the anti-reversal effect is not a sub-period artifact:
- PRIMARY: H1 −0.80%/mo, H2 −1.04%/mo (both negative).
- SECONDARY: H1 −1.15%, H2 −1.11%.
- CONTROL1: stable negative; CONTROL2: stable negative.

## Effective-N (independent episodes)

Monthly non-overlapping holds → each month is an independent episode. `bootstrap_effective_t` (block=6) on the
monthly spread returned t_eff = n for PRIMARY/CONTROLs (little residual autocorrelation at the monthly step) and
276 of 314 for SECONDARY. Effective-N is 276–314 episodes — far above the ≥12 floor; the KILL is well-powered.

## Survivorship BOUND (pre-registered phantom-loser injection)

Per the pre-reg, phantom delisted losers (−30% terminal 1m return, injected at 2× a 0.25%/month base rate =
0.5%/month of the held count) were added to the deepest-quintile LONG leg each month. Because reversal buys the
losers, survivorship bias would inflate the long leg **upward** — the bound tests whether removing that inflation
strengthens the (already negative) verdict. Result: the bound moves the L/S by <0.001/mo and does **not** flip the
sign on any trial (PRIMARY bounded L/S −0.92%/mo, t −2.14, no sign flip). The survivorship correction only makes
the anti-reversal result marginally more negative. The KILL is survivorship-robust.

**Effect-size RANGE (observed → survivorship-bounded), L/S mean/mo:**
PRIMARY [−0.920% → −0.920%]; SECONDARY [−1.131% → −1.131%]; CONTROL1 [−0.404% → −0.404%]; CONTROL2 [−0.455% → −0.455%].
(The bound is small because the phantom count 0.5%/mo × ~20 held ≈ 0.1 name/month is tiny relative to the leg; a
larger delist assumption would deepen, never reverse, the negative verdict.)

## Robustness: fill convention is not the driver

Re-running PRIMARY with the controls' next-close fill (apples-to-apples): L/S −0.79%/mo, t_HAC −2.08, rank-IC
−0.016 — the negative sign, magnitude, and significance survive the fill change. The anti-reversal (short-horizon
momentum) effect is stable across fill convention, across the ADV-cohort split, and across sector-neutralization.

---

## Interpretation

The literature reversal effect the masterplan hoped to find in small/illiquid HK names is **not present at the
1-month horizon on this universe** — and the cross-section actually exhibits weak short-horizon **momentum**
(recent 3-month losers continue to underperform recent winners over the next month). This holds on the low-ADV
cohort (PRIMARY), within-sector (SECONDARY), on mega-caps (CONTROL1, weaker/insignificant), and on the deep
survivorship-selected panel (CONTROL2). The masterplan's honest prior — "NO-GO near-certain on Control 1; the
small-cap primary is genuinely open" — resolves: Control 1 confirms the kill, and the small-cap primary is not
just null but sign-negative. **The reversal leg is refuted; it must not be wired as a ranker.**

## What this does NOT show

- **It does not test a shorter (weekly/1–5 day) reversal horizon.** The pre-reg fixed 3-month formation / 1-month
  hold. Classic short-term reversal often lives at the 1-week horizon; that is a *different, unregistered* test.
  This result kills the 3M-formation / 1M-hold construction only.
- **It does not establish a tradable momentum edge.** The negative L/S is the mirror image of the failed reversal;
  it was not pre-registered as a momentum hypothesis, carries the same DSR-fail (DSR 0.00 for the *reversal* long
  leg), and the masterplan already KILLED HK residual momentum (§0). Do not read a momentum GO out of this.
- **It is not a clean small-cap test.** Even the union's low-ADV cohort is HSCI-constituent (curated, current);
  there is no true HK micro-cap panel in-tree, and the universe is current-constituents (survivorship). The
  phantom bound addresses the *reversal* direction of that bias only.
- **The sector-neutralization (SECONDARY) uses a CURRENT, non-PIT 13-sector map** (HK has no PIT taxonomy) —
  it is a labelled robustness check, not decision-grade on its own; it agrees with PRIMARY.
- **Controls use next-close fills** (open data absent), so their magnitudes are not strictly comparable to the
  next-open PRIMARY; they are directional confirm-a-kill only.
- **HSI benchmark is close-to-close** (HSI has no open); both L/S legs share it, so the spread is
  benchmark-invariant, but the long-only leg's HSI-relative level inherits a small entry-timing approximation.

## Registry

Appended to `data/experiments/registry_seed.json`: id `hk-h4-reversal-phase0`, verdict KILL, no maturation
(decision-grade now), come_back_on 2027-01-03 (only if a *weekly-horizon* reversal re-scope is ever pre-registered
— this construction is closed).
