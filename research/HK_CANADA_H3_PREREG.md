# H3 — A/H Discount Tilt — PRE-REGISTRATION

**Battery:** H3 (HK & Canada masterplan §3, trial ledger §6.1 row H3).
**Grade:** Borderline GO/ACCRUE per §6.1 — the deepest-history HK edge candidate.
**Pre-registered by:** quant research agent. **Committed BEFORE any run** — the commit
timestamp is the audit trail. Nothing below is wired into any live engine or board
(masterplan W3 acceptance: reports only).

---

## 0. One-sentence thesis

Among the H-share legs of dual-listed A/H pairs, the legs whose A/H **premium sits high
in its OWN trailing history** (H unusually cheap relative to its matched A-share, after
FX) subsequently **outperform the HSI** over the next 1–3 months — a cross-sectional
mean-reversion of the H discount toward its own norm.

Premium := A_price / (H_price × FX) − 1. Higher premium ⇒ H cheaper ⇒ candidate long.
This is an **alpha / cross-sectional-ranking** claim (unlike H5, which is conditioner-grade).

---

## 1. Why this is DSR-gated but expected borderline (pre-stated per §6.1)

Masterplan §6.1 ledger row H3: "~130 monthly xsec, unbalanced pairs … Borderline —
GO/ACCRUE." Red-team (HK_CANADA_REDTEAM_FINDINGS.md, multiple reviewers) independently
flagged: (a) the older "2006→ per-pair" premise was **false on the store then cited**
(china_search/closes.parquet started 2021-06-15); (b) with only ~25 pairs the deepest-
discount quintile is ~5 names, so cross-sectional dispersion is thin; (c) the size
factor "explains ~45% of the premium *level*" — a level tilt would be a size bet in
disguise; (d) the 2024–2026 southbound **dividend-tax rumor cycles** are a named
confound that moves the whole A/H complex; (e) HK names **suspend** (H legs halt) and
naive forward-fill fabricates returns.

**The #1057 panel resolves (a):** `data/hk_ah_panel/premium.parquet` is 5,711 dates ×
25 pairs, **2001-07 → 2026-07**, verified pre-reg. Monthly resample yields **301** total
month-ends, **235** months with ≥8 pairs (first ≥8-pair month = 2007-01), **260** with
≥5 pairs (first = 2004-12). So the usable monthly panel is ~19 years / ~235 cross-sections
— deeper than the §6.1 "~130" estimate, NOT the ~60 the older red-team feared.

Confounds (b)–(e) remain and are why the honest prior is **GO/ACCRUE, not GO**:
- (b) thin quintiles → we use **rank-weighted long top-5 H legs** (masterplan §3 H3
  instruction for ~25 pairs), not a 5-vs-5 L/S, as the PRIMARY; a rank-IC and a
  top-minus-bottom-tercile L/S are reported as corroboration, not the decision leg.
- (c) size → **own-history percentile** (each pair vs its own trailing ≥2y premium
  distribution) is the primary transform precisely because it differences out the
  time-invariant size *level* of the premium. We additionally residualize the
  cross-section against a **PIT-safe log-price size proxy** (§3) and report both; we
  state plainly that a true PIT mktcap does not exist in-tree (fundamentals are a single
  static 2026-06-18 snapshot → look-ahead → NOT used).
- (d) dividend-tax cycle → reported as a **named confound**; a 2021→ vs pre-2021
  split-half is run so the reader sees whether the edge is a 2021-2026 artifact.
- (e) suspension → strict next-valid-print rule (§5), NO forward-fill across halts.

We compute program-level **DSR at n_trials = 30** (masterplan §6 program budget, every
config across both markets) and require **DSR ≥ 0.90** as the only door into a GO. A DSR
below 0.90 with the right *shape* (positive IC, HAC-t ≥ 1.5, split-half sign stability)
is the pre-registered **ACCRUE** result — respectable, not tortured into a GO.

---

## 2. Data (exact sources, ranges verified pre-reg)

| Series | Store / path | Range verified | Role |
|---|---|---|---|
| A/H premium (25 pairs) | `data/hk_ah_panel/premium.parquet` (idx `Date`, cols = H tickers) | 2001-07-16 → 2026-07-03, 5711 rows | signal source |
| pair map (A↔H, joint_start) | `data/hk_ah_panel/pairs.json` (list of {a,h,joint_start,n_days}) | 25 pairs, listing-date PIT | universe / inception |
| H-leg closes (157 names) | `data/hk_search/closes_deep.parquet` (cols = H tickers) | 1986-12-31 → 2026-06-18 | forward H returns |
| HSI close | `data/hk/_HSI.parquet` (col `close`, idx `Date`) | 1986-12-31 → 2026-07-03 | benchmark |

**All 25 H legs verified present in `closes_deep`** (0 missing, checked pre-reg).

**Total-return vs price-index honesty (stated, not hidden):** per memory
[yahoo close is total return], `closes_deep` H-leg `close` is **dividend-adjusted total
return**; `_HSI` `close` is a **price index**. Therefore "H excess vs HSI" mixes a TR leg
against a price benchmark — the H dividend yield (~2–4%/yr for these SOE/insurer names)
adds a slow POSITIVE drift to every long-H-vs-HSI number. This inflates the *long-only*
excess return by a roughly common additive term. Two mitigations, both pre-registered:
(i) the PRIMARY verdict also requires the **dividend-neutral top-minus-bottom L/S** (both
legs are TR H-legs, so the dividend drift cancels) to carry the same sign; (ii) the
rank-IC leg is **scale/drift-free by construction** (Spearman of signal vs forward
excess). A long-only number that is positive ONLY because of the TR/price gap will show
up as a near-zero rank-IC and a near-zero L/S — and cannot reach GO.

**closes_deep staleness:** last date 2026-06-18 (15 bd stale vs HSI 07-03). The last
monthly rebalance that can be fully populated with a 63-bd forward window ends well
before 2026-06 regardless, so this staleness does not touch any graded cross-section;
stated for completeness.

---

## 3. Signal construction (exact, frozen)

Work on the premium panel `P` (dates × 25 H tickers). All transforms are per-pair,
own-history, look-ahead-free (windows end at t).

**PRIMARY signal — own-history percentile of the premium.**
For pair `j` on date `t`:
`pctile_j,t` = percentile rank of `P[j,t]` within its trailing **504-trading-day**
(~2-year) own window `P[j, t-504 : t]` (window ends at t, inclusive). Require **≥ 252
non-NaN** observations in the window (a pair with < ~1y of history at t is NOT ranked
that date — it enters the cross-section only once it has ≥1y of own history, min-2y
window). `pctile` ∈ [0,1]; **high = H unusually cheap vs its own norm = long candidate.**

**Rationale for own-history (size absorber, pre-stated):** the premium *level* is
dominated by a near-constant per-pair size/liquidity/float term (red-team: ~45% of level
is size). Ranking each pair against ITS OWN trailing distribution differences that
constant out, so the cross-sectional signal is "how cheap is this H vs its own typical
cheapness," not "which names have structurally big premiums." This is the pre-registered
reason own-history is PRIMARY and raw level is not tested at all.

**SECONDARY signal — 1-year premium change (widening vs narrowing).**
`d1y_j,t` = `P[j,t] − P[j, t−252]` (252 td ≈ 1y). Positive = premium widened (H got
cheaper over the year → momentum-of-discount); we test the SAME direction as primary
(wider discount → long H). Require both endpoints non-NaN.

**Size control (PIT-safe proxy, reported alongside primary, NOT a separate decision
trial):** a true PIT market cap is unavailable (fundamentals.parquet is a single static
2026-06-18 snapshot → look-ahead → excluded, stated). As a crude PIT proxy we use
`size_j,t = log(H_close_j,t)` (price level; a proxy for cap only up to the fixed,
per-pair share count — so it is really a *price-level* control, flagged as such). On each
rebalance date we cross-sectionally residualize the signal against `size` via
`engine.validation.cross_sectional_resid` and report the residualized-signal IC beside
the raw-signal IC. If the raw-signal IC is materially killed by residualizing on a mere
log-price proxy, that is evidence the tilt is a size/level bet — reported honestly. This
proxy is weak (it is NOT mktcap); the PRIMARY size defense remains the own-history
transform, per red-team guidance that own-history "largely absorbs the size level effect."

---

## 4. Pre-registered trials (exactly 2 decision trials)

Rebalance **monthly** at each month-end t (301 candidates); enter at the **next trading
day's open-proxy** (§5). Forward horizons: **1m (21 bd)** and **3m (63 bd)**. Within-family
multiple testing controlled by **BH-FDR at α=0.10** across the 2 decision trials × 2
horizons (4 p-values). Program-level DSR uses **n_trials = 30**.

**Forward target = H-leg excess return vs HSI over the horizon:**
`excess_j = (H_j,t+entry+h / H_j,t+entry − 1) − (HSI_t+entry+h / HSI_t+entry − 1)`.

**TRIAL (a) — PRIMARY: own-history percentile tilt.**
Portfolio = **rank-weighted long the top-5 H legs by `pctile`** (deepest own-history
discount), weights ∝ (rank within top-5), normalized to sum 1, measured as excess vs HSI.
Reported at 1m and 3m. Decision statistics:
1. **Rank-IC** (Spearman of `pctile` vs forward excess) per rebalance → `ic_summary`
   (mean IC, IC-IR, HAC-t via Newey-West, hit-rate).
2. **Top-5 rank-weighted excess** series → mean, HAC-t (`newey_west_tstat`, lags = h−1 in
   monthly steps → lags=2 for 3m, lags=0→1 for 1m), block-bootstrap `t_eff`.
3. **Corroborating L/S** (dividend-neutral): top-tercile minus bottom-tercile equal-weight
   H legs. Must share the sign of (2) for a GO (TR/price-drift check, §2).
4. **DSR** on the monthly top-5-excess series at n_trials=30, with `t_eff` from
   `bootstrap_effective_t`.

**TRIAL (b) — SECONDARY: 1y premium-change tilt.**
Same machinery as (a) but signal = `d1y`. Same 4 statistics. This trial is the weaker
prior (momentum-of-discount is more confound-exposed to the 2024–26 dividend-tax cycle)
and its verdict is **capped at ACCRUE** regardless of strength.

**Robustness variants (reported, NOT decision trials, NOT FDR-counted):**
R1 top-3 vs top-5 vs top-7 portfolio width; R2 504d vs 756d (3y) own-window; R3
size-residualized primary IC (§3); R4 pre-2021 vs 2021→ split (dividend-tax-cycle probe).
A decision trial flipping sign under R1–R4 downgrades the verdict one notch.

---

## 5. Fill / lookahead / suspension discipline (core red-team demand)

- **Signal at t** uses only premium data through t (percentile & 1y-Δ windows end at t).
- **Data availability lag:** the premium is computed from same-day A and H closes; both
  are known at each market's close. A monthly signal formed on month-end close t is
  actionable the **next trading day**. Entry = **next trading day's open-proxy** = the
  next available H close *strictly after* t (we lack an HK open series; next-day close is
  a 1-bar-lagged, look-ahead-free entry reference — stated, not hidden). Forward return
  runs from that entry close to the close h trading bars later. This is the masterplan's
  next-open, implementation-lag-honest fill.
- **Suspension / halt rule (HK H legs halt for weeks):** a pair is included in a rebalance
  ONLY if (i) it has a valid entry print within **5 trading sessions** after t (else the
  name is **excluded** from that rebalance — never forward-filled through the halt), AND
  (ii) it has a real H close at horizon end. A forward window that cannot be populated
  with real closes (halt spanning the horizon end, or running past the last available
  date) drops that name-date — **no forward-fill across non-trading gaps, ever.** The
  benchmark HSI leg uses actual traded HSI closes only.
- **Overlap:** monthly rebalance with 3m forward → 3× overlapping windows. HAC
  (Newey-West, lags = 2 for 3m, 0 for 1m on the monthly series) corrects the mean t-stat;
  `bootstrap_effective_t` on the monthly excess series gives the autocorrelation-honest
  effective-N that feeds DSR's `t_eff`.

---

## 6. Effective-N (independent episodes) — pre-stated basis

Effective-N is NOT the 235 monthly cross-sections (they overlap and are cross-sectionally
correlated — all 25 H legs move with HK beta). The binding effective-N is the smaller of:
- `bootstrap_effective_t(monthly_excess_series, block=3)` — the block-bootstrap effective
  count on the top-5 monthly excess series (block=3 months ≈ the 3m forward overlap);
- an **independent-episode** count = number of non-overlapping 3-month blocks in the
  graded window (~235/3 ≈ 78 for 3m, ~235 for 1m), further discounted for the fact that
  the 25-pair cross-section is one correlated HK basket (the cross-section adds breadth,
  not independent time).

**Pre-stated expectation (honesty, before running):** effective-N on the order of
**60–90 independent 3-month episodes**; enough to reach DSR≥0.90 *if* the per-episode IC
is genuinely ~0.05+ with a stable sign, but structurally borderline — a per-episode Sharpe
that is real but modest will land DSR in the 0.7–0.9 band → **ACCRUE**.

---

## 7. Survivorship BOUND (method, pre-stated)

The 25 pairs are **current** dual-listings (pairs.json = pairs that exist today). A pair
that de-listed / was privatized / had its H or A leg suspended permanently is absent →
**survivorship-biased UP** (survivors are the pairs whose discount *did* eventually behave).

Bound method (pre-registered): I cannot resurrect dead pairs (no PIT dual-listing
registry in-tree — stated as the bound's limitation). Instead I bound the bias two ways:
(1) **Inception-honest panel** — each pair enters only from its `joint_start`, so no pair
is back-cast before it existed (this removes the *inclusion* look-ahead but not the
*survival* one). (2) **Worst-plausible-haircut bound** — I re-run the PRIMARY excluding
the 5 pairs with the **shortest** joint history (most likely to be recent survivors /
most fragile), and separately report the IC on ONLY the pairs with ≥15y history (the
deep-survivor core). The GO verdict must survive on the ≥8-pair, inception-honest panel;
the haircut runs are the bound. I state explicitly: **this bounds inclusion + fragility,
not true delisting survivorship**, which would require a dead-pair registry we lack — so
the reported IC is an **upper bound** on the tradable edge.

---

## 8. Pre-registered GO / NO-GO / KILL / ACCRUE gates

Evaluated on the **PRIMARY trial (a)** (SECONDARY (b) capped at ACCRUE by construction).
All sub-conditions use the **3m horizon** as the binding horizon (deeper, less noisy),
with 1m required only to agree in sign.

| Verdict | Condition (ALL sub-conditions must hold) |
|---|---|
| **GO** | (1) mean rank-IC > 0 at BOTH 1m and 3m (same-sign); (2) HAC-t on the 3m top-5 excess ≥ 2.0 AND HAC-t on the 3m rank-IC ≥ 2.0; (3) the dividend-neutral top−bottom L/S shares the sign of the top-5 excess at 3m (TR/price-drift not the whole story); (4) **DSR ≥ 0.90** on the 3m monthly excess series at n_trials=30; (5) split-half sign stability: the 3m top-5-excess sign agrees in BOTH halves (median-date split) AND in the pre-2021 / 2021→ split; (6) survivorship: GO survives on the inception-honest ≥8-pair panel (§7). |
| **ACCRUE** | rank-IC > 0 at both horizons AND (HAC-t ≥ 1.5 at 3m on IC or excess) BUT (DSR < 0.90 OR one split-half sign flips OR HAC-t < 2.0). i.e. the *shape* is right, the power is structurally short → re-run when the panel deepens / dividend-tax cycle resolves. **This is the pre-registered honest-default expectation for H3.** |
| **NO-GO** | rank-IC ≤ 0 at either horizon, OR signs disagree across 1m/3m, OR the top-5 excess is indistinguishable from the TR/price dividend drift (L/S sign flips negative while long-only is positive). |
| **KILL** | rank-IC < 0 with HAC-t ≥ 2.0 at 3m (deep-discount H legs reliably *under*perform) — the thesis is backwards; do not resurrect. |

**Split-half:** (i) median-date split of the graded window; (ii) pre-2021 vs 2021→ split
(the dividend-tax-cycle era). A flip in EITHER → cannot be GO (caps at ACCRUE).

**BH-FDR:** applied across the 4 p-values {trial a, trial b} × {1m, 3m} at α=0.10; a GO
requires the primary-3m p-value to survive BH.

---

## 9. "What this does NOT show" (pre-committed)

- Does NOT establish a **causal** A/H convergence mechanism; a positive result is a
  cross-sectional mean-reversion association, confounded with size (proxy-controlled only),
  liquidity, and the southbound **dividend-tax rumor cycle 2024–2026** (named).
- Does NOT use a true PIT market cap — the size control is a **log-price proxy**; a tilt
  that survives own-history ranking but not a *real* PIT-cap control cannot be ruled out.
- Does NOT correct for **delisting survivorship** — the 25 pairs are today's survivors;
  the reported IC is an **upper bound** on the tradable edge (§7).
- The **TR-vs-price** benchmark mismatch means long-only excess carries a positive
  dividend drift; only the rank-IC and dividend-neutral L/S legs are drift-clean, and a
  GO requires them to agree.
- Does NOT show tradability net of HK transaction costs, borrow, or the fact that the
  cheapest-H names are often the least liquid / most halt-prone legs.
- Is **NOT wired** into any engine or board — report only (masterplan W3).

---

## 10. Trial accounting (for the DSR n_trials audit trail)

Decision trials in THIS battery: **2** (primary own-history percentile, secondary 1y-Δ),
each at 2 horizons. Robustness variants R1–R4: reported, NOT decision, NOT FDR-counted.
Program-level DSR **n_trials = 30** (masterplan §6 — every config across both markets).
BH-FDR applied within the H3 family (4 p-values) at α=0.10. The SECONDARY trial's verdict
is capped at ACCRUE by construction. Honest prior (pre-run): **GO/ACCRUE, leaning ACCRUE.**
