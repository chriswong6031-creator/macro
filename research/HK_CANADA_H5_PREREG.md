# H5 — HK Peg-Liquidity Regime — PRE-REGISTRATION

**Battery:** H5 (HK & Canada masterplan §3, trial ledger §6.1 row H5).
**Grade:** CONDITIONER-GRADE ONLY. This sizes HK exposure; it never ranks names.
**Pre-registered by:** quant research agent. **Committed BEFORE any run** — the commit
timestamp is the audit trail. Nothing below is wired into any live engine or board
(masterplan W2 acceptance: reports only).

---

## 0. One-sentence thesis

When HK interbank liquidity is *easy* — the aggregate balance is high relative to its
own recent history AND HIBOR sits well below the pegged-USD funding leg (HIBOR−USD
spread wide-negative) — forward HSI returns are less negatively skewed (shallower
drawdowns) than when liquidity is *tight* (balance drained, HIBOR pulled up toward or
above the USD leg by the peg's convertibility-undertaking arbitrage).

This is a **directional / drawdown-separation** claim, NOT an alpha claim. The
deliverable is a regime label a future W4 conditioner would consume to *size* HK risk.

---

## 1. Why this is conditioner-grade and NOT DSR-gated (pre-stated per masterplan §6.1)

Masterplan §6.1 ledger row H5: "few regimes 2018→ … **Conditioner-grade only**."
Red-team §45/§71-73 confirm: SOFR only exists from 2018-04, so the SOFR-era primary
window is ~8 years; a liquidity regime split of 8 years yields **few independent
episodes** (pre-stated below: expected 4–8 per leg). The masterplan constitution's
`DSR ≥ 0.90` gate is "the only door into *scored seams*." H5 is not a scored seam —
it is an exposure conditioner. Therefore:

- **The pass bar for H5 is: (i) directional consistency of the sign across both the
  1m and 3m horizons, (ii) drawdown separation (tight regime has materially worse
  worst-case / left-tail forward return than easy), and (iii) split-half sign
  stability.** NOT DSR ≥ 0.90.
- We still **compute** DSR (honest program-level `n_trials = 30` per §6 — counting
  every config across both markets, not just this family) and report it, precisely so
  the reader sees H5 does NOT clear a scored-seam bar and is not being smuggled in as
  one. A DSR far below 0.90 is the *expected, pre-registered* result and is not a
  demotion — it is the correct label for a low-episode conditioner.
- Effective-N is measured in **independent regime episodes**, not daily rows. Overlap
  in forward-return windows is HAC-corrected (Newey-West) AND episode-collapsed.

---

## 2. Data (exact sources, ranges verified pre-reg)

| Series | Store / path | Range verified | Role |
|---|---|---|---|
| `agg_balance`, `hibor_on`, `hibor_1m` | `data/hkma/interbank_liquidity.parquet` (idx `end_of_date`) | 2002-01-02 → 2026-06-30 (6274 rows) | HK liquidity leg |
| SOFR | `store.read("ofr","FNYR-SOFR-A")` (col `sofr`) | 2018-04-02 → 2026-06-30 (2059 rows) | USD leg, PRIMARY |
| DFF (effective fed funds, daily) | `store.read("fred","DFF")` (`data/fred/DFF.parquet`) | 1954-07-01 → 2026-06-30 (26298 rows) | USD leg splice, SECONDARY pre-2018 |
| HSI close | `data/hk/_HSI.parquet` (col `close`, idx `Date`) | 1986-12-31 → 2026-07-03 (9747 rows) | forward-return target |
| Southbound aggregate `net` | `data/china_connect/southbound.parquet` (idx `TRADE_DATE`) | 2014-11-17 → 2026-07-03 | EXPLORATORY interaction only |

**HSI note:** yahoo `close` is dividend-adjusted total return for equities; for the
HSI *index* series it is price return. Forward returns are index price returns — this
is the correct target for a risk-sizing conditioner (we size exposure to the index,
not harvest dividends). Stated, not silently assumed.

**USD leg mnemonic honesty:** SOFR (secured overnight repo) and DFF (effective fed
funds, unsecured overnight) are DIFFERENT rates with a small persistent basis. The
splice at 2018-04 is therefore a **labeled discontinuity** (see §4 SECONDARY). The
PRIMARY trial uses SOFR only and never touches DFF, so the primary verdict carries no
splice contamination.

---

## 3. Regime construction (exact, frozen)

All labeling uses **own-history rolling percentiles** (NOT raw levels) because
`agg_balance` is grossly non-stationary (387 in 2002 → ~54,000 in 2026) — a raw-level
threshold would just be a time trend. This is pre-registered to avoid the obvious
non-stationarity confound the red-team would raise.

Let, on each HKMA business day *t*:

- `spread_t = hibor_1m_t − usd_leg_t` (percentage points). USD leg = SOFR (PRIMARY)
  or the DFF-spliced series (SECONDARY). 1-month HIBOR is chosen (not overnight) to
  match the ~1m funding tenor and reduce O/N spike noise; O/N is a pre-registered
  robustness variant reported but NOT counted as a decision trial.
- `bal_pct_t` = percentile rank of `agg_balance_t` within a **trailing 252-business-day
  window** (own-history; the value's rank among the last ~1 year). No look-ahead:
  window ends at *t*.
- `spread_pct_t` = percentile rank of `spread_t` within the trailing 252-day window.
  Low `spread_pct` = HIBOR unusually far below the USD leg = easy funding.

**Composite ease score** `E_t = bal_pct_t − spread_pct_t`, range ~[−100, +100].
High `E_t` = balance high AND spread low = EASY. Low `E_t` = TIGHT. This combines the
two masterplan-named ingredients ("agg_balance high" and "HIBOR−USD wide-negative")
into one monotone score, frozen here before any return is looked at.

**Regime label (frozen thresholds, tercile-style on the composite):**
- `EASY` if `E_t ≥ +33` (top ~third of the composite's own 252d distribution region).
- `TIGHT` if `E_t ≤ −33`.
- `NEUTRAL` otherwise (excluded from the two-regime contrast; reported for completeness).

Thresholds ±33 are pre-registered (not tuned). A single robustness variant at ±25 /
±40 is reported but NOT a decision trial (labeled sensitivity).

**Episode definition (for effective-N honesty):** a regime *episode* is a maximal run
of consecutive same-label business days, after **debouncing**: a label must persist
≥ 10 business days to open an episode, and a ≤ 5-business-day interruption of the
opposite/neutral label inside an episode does not close it (hysteresis). Forward
returns for episode-level stats are sampled **once per episode at its open** to make
episodes independent; the daily-sampled version is also computed but its N is treated
as HAC-corrected daily, and the *binding* effective-N is the episode count from
`bootstrap_effective_t` on the daily strategy series AND the raw debounced episode
count, whichever is smaller.

**Pre-stated episode-count expectation (honesty, before running):** over the ~8-year
SOFR window I expect **4–8 EASY episodes and 4–8 TIGHT episodes** (HK liquidity swings
on multi-month cycles: 2018 tightening, 2019 unrest, 2020 COVID flood, 2021 IPO-boom
drain, 2022–23 US hiking / carry drain, 2024–25 re-liquefication). If the realized
count is materially outside 3–12 per leg I will say so and treat the split as
descriptive only.

---

## 4. Pre-registered trials (exactly 2 decision trials)

Within-family multiple testing controlled by **BH-FDR at α=0.10** across the 2 trials.
Program-level DSR uses **`n_trials = 30`** (masterplan §6 program budget).

**TRIAL (a) — PRIMARY: SOFR-era 2018→.**
USD leg = SOFR. Window = 2018-04-02 → 2026-06-30. Forward HSI returns at **1m (21 bd)**
and **3m (63 bd)** horizons, next-bar fills (see §6). Compare EASY vs TIGHT:
mean forward return, and drawdown profile (min forward return, 5th-percentile forward
return, and realized max-drawdown of a long-HSI-only-in-EASY vs long-HSI-only-in-TIGHT
daily strategy). HAC-t (Newey-West, lags = horizon−1) on the EASY−TIGHT mean
difference. `bootstrap_effective_t` on each regime's daily strategy series.

**TRIAL (b) — SECONDARY (labeled splice, discontinuity): spliced 2002→.**
USD leg = SOFR from 2018-04-02 onward, DFF before 2018-04-02, spliced at the boundary.
The splice is a **labeled discontinuity**: (i) the SOFR−DFF basis over 2018-04→ is
reported so the reader sees the level shift the splice introduces; (ii) episodes that
*straddle* the 2018-04 boundary are flagged and reported separately; (iii) the
percentile windows are computed on the spliced series, so the ~1y after the splice
boundary mixes the two rate conventions — this contamination window is flagged. Same
outputs as (a). This trial is explicitly the weaker of the two and its verdict is
capped at ACCRUE regardless of strength (a spliced-rate conditioner cannot be
decision-grade).

**Robustness variants (reported, NOT decision trials, NOT FDR-counted):**
R1 O/N HIBOR instead of 1m; R2 thresholds ±25/±40; R3 balance-only vs spread-only
composite legs. These probe fragility; a decision trial flipping sign under R1–R3 is
grounds to downgrade the verdict one notch.

---

## 5. Pre-registered GO / NO-GO / KILL / ACCRUE gates

Because H5 is conditioner-grade (§1), the gates are directional + drawdown-separation,
NOT DSR-gated. Evaluated on the **PRIMARY trial (a)** (the SECONDARY is capped at
ACCRUE by construction).

| Verdict | Condition (ALL sub-conditions must hold) |
|---|---|
| **GO** (conditioner-ready) | (1) EASY forward mean > TIGHT forward mean at BOTH 1m and 3m (same-sign directional consistency); (2) drawdown separation: TIGHT 5th-pctile forward return AND TIGHT strategy max-drawdown are materially worse than EASY (gap ≥ 1.5× at 3m, or TIGHT left-tail ≤ EASY left-tail − 5 percentage pts); (3) HAC-t on EASY−TIGHT mean diff ≥ 1.5 at 3m (conditioner bar, NOT 2.0); (4) split-half sign stability: EASY−TIGHT sign agrees in BOTH halves of the SOFR window at 3m; (5) ≥ 4 independent episodes per leg. |
| **ACCRUE** | Direction (1) holds and drawdown separation (2) holds, but HAC-t < 1.5 OR split-half sign flips OR episodes < 4 per leg. i.e. the *shape* is right but the power is structurally too low to call it now → re-run when the SOFR window lengthens. This is the pre-registered HONEST-DEFAULT expectation for H5. |
| **NO-GO** | Direction (1) fails at either horizon (signs disagree across horizons) OR drawdown separation (2) fails (TIGHT is not worse). The conditioner has no usable signal. |
| **KILL** | Direction REVERSES with HAC-t ≥ 1.5 at 3m (EASY reliably *worse* than TIGHT) — the thesis is backwards; do not resurrect. |

**Split-half:** SOFR window split at its median date; require the EASY−TIGHT sign to
agree in both halves at the 3m horizon (sub-condition GO-4). A flip → cannot be GO.

**Effective-N basis:** independent debounced episodes per leg (§3), cross-checked
against `bootstrap_effective_t` on the daily strategy series. The binding N is the
smaller. Reported explicitly; a sub-4-episode leg caps the verdict at ACCRUE.

**Survivorship:** N/A for the target (HSI index has no survivorship — it is the
official index, reconstituted by HSI Ltd, not a current-constituent panel). The
liquidity/rate series have no survivorship. **Stamp: no survivorship bound needed for
H5 — the target is an index level, not a name panel.** (Contrast: H1/H3/H4 need
bounds; H5 does not. Stated explicitly so the absence is a decision, not an omission.)

**Suspension/halt fill rule:** the target is the HSI index, which does not halt for
weeks the way individual HK names do. Still, forward returns are computed on **actual
traded index closes only** — no forward-fill across non-trading gaps; a forward window
that cannot be fully populated with real closes (e.g. runs past the last available
date) is dropped, not padded. `usd_leg` and HKMA series are forward-filled to HK
trading days ONLY within a ≤ 3-business-day staleness cap (a value staler than 3 bd is
treated as missing and that date is excluded) — matching the masterplan §2.6 freshness
principle.

---

## 6. Fill / lookahead discipline

- Regime label on day *t* uses only data through *t* (percentile windows end at *t*).
- Forward return is measured from the **next HK trading day's open-proxy** = next
  available close after *t* (we lack an open series for the deep HSI index; using
  next-day close as the entry reference is a 1-bar-lagged, look-ahead-free
  approximation — stated, not hidden). Horizon-end = the close `h` trading bars later.
- No overlap-inflation: HAC (Newey-West, lags = h−1) on daily-sampled forward returns,
  AND the episode-open-sampled series as the independent-N cross-check.

---

## 7. Exploratory (labeled, non-gated, informs H1 only)

Does southbound aggregate `net` flow run stronger in EASY regimes? Compute mean daily
southbound `net` (and its sign-consistency) within EASY vs TIGHT over the overlap
window (southbound starts 2014-11; intersect with the regime series). This is
**descriptive**, has no gate, and cannot produce a GO — it only flags whether H1's
southbound leg should itself be conditioned on H5's regime. Reported with an explicit
"exploratory, non-evidential" banner.

---

## 8. Deliverable beyond the report

A JSON/py constants block in the report defining the frozen regime labels a W4
conditioner would consume: window, USD-leg source, percentile lookback, composite
formula, thresholds, debounce params, and the empirical EASY/TIGHT day-fractions and
episode boundaries. **NO wiring** — the block is a spec, not an import.

---

## 9. "What this does NOT show" (pre-committed)

- Does NOT show an alpha edge or a name ranking — H5 never ranks.
- Does NOT show a decision-grade (DSR≥0.90) result — by construction it cannot at this
  episode count; a low DSR is expected and reported as such.
- The SECONDARY spliced trial does NOT provide a clean 2002→ history — the SOFR/DFF
  basis and the percentile-window contamination at the splice boundary are
  acknowledged discontinuities; its verdict is capped at ACCRUE.
- Does NOT establish causality (liquidity → returns); the regime is a coincident
  conditioner, and reverse causality / common-driver (global risk-off tightens HK
  funding AND sells HK equities simultaneously) is NOT ruled out and is stated.

---

## 10. Trial accounting (for the DSR n_trials audit trail)

Decision trials in THIS battery: 2 (primary SOFR, secondary splice). Robustness
variants R1–R3: 3 (reported, not decision, not FDR-counted). Program-level DSR
`n_trials = 30` (masterplan §6 — every config across both markets). BH-FDR applied
within the 2-trial H5 family at α=0.10.
