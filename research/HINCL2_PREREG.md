# H-INCL-2 — Stock-Connect (Southbound / 港股通) Inclusion Events — DEEPER-PANEL RE-RUN — PRE-REGISTRATION (AMENDMENT)

**Battery:** H-INCL (HK/Canada masterplan §3). **This is the pre-registered ACCRUE re-run** of
H-INCL on the expanded name panel, amending `research/H_INCL_PREREG.md`.
**Wave:** W3. **Branch:** `hkca-w3-hincl2`.
**Status:** PRE-REGISTERED AMENDMENT — committed BEFORE any statistic on the expanded panel runs.
**Constitution:** masterplan §6 (pre-reg first; HAC t; BH-FDR within family; program-level DSR;
split-half sign-stability; effective-N = independent episodes = review batches; DSR≥0.90 the only
door to a scored GO; survivorship bounds not stamps; suspension-honest fills; verdicts
GO/NO-GO/KILL/ACCRUE). Nothing is wired — reports + registry only (masterplan W3 acceptance).

---

## 0. Why this run exists (the registered accrual path)

The first H-INCL run (`reports/hincl-phase0.md`, PR #1077, merged) was **NO-GO on both gated trials**
with the binding caveat that only **38 of 466 add events** (25 episodes) were studiable on the
157-name in-tree mega-cap panel (`closes_deep`), and that the additions where the marginal-buyer
demand shock is largest — the small/mid caps *entering* Connect — were entirely off-panel. Its
pre-registered ACCRUE path (H_INCL_PREREG §5 ACCRUE clause, §6, §8) was: **re-run once the expanded
HSCI panel (`hk_stocks_ext`) lands and lifts studiable-K.** That store now exists locally
(388 per-ticker deep-OHLCV parquets, gitignored / R2-destined). This is that re-run.

**No mechanism, hypothesis, gate, statistic, episode rule, fill rule, or verdict rule is relaxed
relative to H_INCL_PREREG.** The ONLY changes are: (a) the price panel widens from 157 → the union
of all locally-available HK per-ticker stores; (b) the benchmark is refreshed to the current HSI;
(c) the program DSR trial count is bumped 30 → 32 to reflect the now-larger program ledger (a
STRICTER deflation, never looser). Everything else is inherited verbatim.

---

## 1. Headline feasibility number (pre-stated as THE first thing to report)

Per the run-1 caveat, the headline of this run is the in-panel coverage. Measured BEFORE any
statistic (roster adds vs the union panel columns), recorded here as the pre-registered feasibility
fact:

- Roster: **466 add events / 444 distinct add tickers** (unchanged; in-tree
  `data/hk_connect_roster/roster.parquet`, 796 rows, 2015-09→2026-07).
- Union panel = `data/hk_search/closes_deep.parquet` (157) ∪ `data/hk_stocks/*.HK.parquet` (157) ∪
  `hk_stocks_ext/*.HK.parquet` (388) → **545 distinct names**.
- **Add-ticker coverage on the union panel: 275 / 444 (61.9%)** — vs 38 / 444 on the run-1 panel.
  A **7.2×** coverage lift. This is the headline feasibility number; the report states it first.

(The 169 still-missing add tickers are the delisted / never-in-HSCI micro-caps; they enter the
survivorship lower bound as imputed-0, §5.)

---

## 2. Hypotheses (inherited verbatim from H_INCL_PREREG §1)

Mechanism: when a HK name is **added** to the southbound Connect eligible list, the mainland crowd
becomes able to buy it — a one-off positive demand event. Two pre-registered distinct causal windows:

- **T-ANN (announcement drift, primary, one-sided long):** from the next bar after the announcement
  date, an added name earns POSITIVE index-relative CAR vs HSI over the forward window (front-run of
  the not-yet-effective inclusion).
- **T-EFF (inclusion-day demand, primary, one-sided long):** from the next bar after the effective
  date (first southbound-tradable day), an added name earns POSITIVE index-relative CAR.
- **H0** (each): mean CAR over the window = 0.

**Family = the SAME 2 gated trials {T-ANN, T-EFF}**, one BH-FDR family (α=0.10).

**Exploratory, NON-GATED, labelled** (same as run 1, now with far bigger n): the −10..0
pre-announcement run-up profile (t−10..t0 CAR — run 1 showed +5.3% impounded pre-fill; confirm or
revise) and the REMOVAL (调出) de-rate side.

---

## 3. Constructions (frozen; deltas vs H_INCL_PREREG explicitly tagged)

### 3.1 Roster — UNCHANGED
`data/hk_connect_roster/roster.parquet` exactly as merged. Adds = rows with `action=="add"`.
Anchor dates: `announce_date` (from the notice); effective = the next HK trading day strictly after
`announce_date` in the panel calendar (the SSE fallback rule; the parseable-in-text effective date
was not reliably extractable across 194 notices — inherited limitation, run 1 §4).

### 3.2 Price panel — DELTA: union of all local HK per-ticker stores (was: 157 closes_deep)
Build one wide close matrix over the **union** of:
- `data/hk_search/closes_deep.parquet` columns (157),
- `data/hk_stocks/*.HK.parquet` `close` (157),
- `hk_stocks_ext/*.HK.parquet` `close` (388, read from the absolute ext path — gitignored/R2).

De-duplicate by ticker (a name present in more than one store: prefer the longest non-null close
history; sources agree on adjusted close by construction). Result ≈ 545-name close matrix,
outer-joined on the trading calendar, NaN where a name has no print.

### 3.3 Benchmark — DELTA: refreshed HSI
`data/hk/_HSI.parquet` (`close`, fresh to **2026-07-03**) — replaces the run-1
`_HSI_deep.parquet` which was stale at 2026-06-12 and truncated forward windows near the panel end.
(Same HSI series family; the refresh only extends the tail, adding studiable recent events.)

### 3.4 Fill convention — INHERITED (next-valid-CLOSE), open availability noted as robustness only
The amended brief specifies "next-open → next-valid-close fills … (hk open column is unpopulated —
the H1 battery documented this; follow its precedent)." **Premise check:** the in-tree
`data/hk_stocks/` `open` column IS unpopulated (0.3% non-null, verified) — matching H1's documented
finding. The **ext** store's `open` IS populated (100% non-null, verified). To keep this run
**directly comparable to run 1's gated cells** (which were close-only via `closes_deep`) and to the
H1 precedent, the **primary fill = next-valid-close**: entry at the panel close on the first valid
trading day strictly after the anchor date; forward CAR measured close-to-close from that fill.
An open-anchored variant (feasible on the ext subset) is a **labelled robustness note only, NOT a
gated trial and NOT FDR-corrected** — switching the primary fill mid-program would break
comparability and silently add a researcher DOF. This is the identical convention to run 1.

### 3.5 Suspension / halt / missing-bar rule — UNCHANGED (mandatory, HK-specific)
Need a valid print within **5 sessions** after the intended fill bar (else EXCLUDE — never
forward-fill through a halt). Within a window, cumulate over PRESENT bars only on the
stock∩index date intersection; require ≥ max(3, h//2) common bars. If the forward window runs past
the panel's last bar, DROP the event (no partial window).

### 3.6 Abnormal return — UNCHANGED
Index-relative CAR (market-model β≡1): stock cumulative log-return − HSI cumulative log-return over
the identical calendar window. β-adjusted market model = labelled robustness, not primary.

### 3.7 Event window & horizons — UNCHANGED
−10 … +60 sessions around the fill. **Primary decision horizon = +20 sessions.** Robustness curve
+5, +10, +40, +60 (nuisance dimension, NOT separate FDR slots).

### 3.8 Effective-N: episode = review batch — UNCHANGED
An *episode* = one distinct anchor date (announce-date for T-ANN, effective-date for T-EFF). Event
CARs are averaged within each episode date → ONE observation per episode. HAC / DSR / split-half run
on the **episode-level** CAR series. K = distinct anchor-dates with ≥1 studiable panel name.
**Pre-state expectation (from the semi-annual review cadence + 275 studiable tickers): K ≈ 20–24.**
This is the honest power ceiling — the coverage lift multiplies studiable *tickers* ~7×, but review
batches collapse many same-date adds into single episodes, so episode-K rises far less than ticker-N.

### 3.9 Survivorship bound — UNCHANGED method, wider studiable set
Report (a) the panel-studiable estimate (upper bound) and (b) the lower bound: impute every roster
add ticker **missing from BOTH the union panel and never studiable** as CAR=0 at horizon (the honest
worst case for an inclusion long — the missing micro-caps did nothing). A GO requires the LOWER
bound to still clear the gate. With 275/444 covered the imputed-0 mass is far smaller than run 1.

---

## 4. Statistics (frozen — identical to H_INCL_PREREG §4, one deflation delta)

On the episode-level CAR series, primary horizon +20d, for each gated trial:
1. **HAC t** (`newey_west_tstat`, lags=4). Report mean CAR, HAC se, t, p.
2. **BH-FDR** (`benjamini_hochberg`, α=0.10) across the 2 gated one-sided p-values.
3. **block-bootstrap 90% CI** of the episode-mean (block=4, B=5000, seed=7).
4. **`bootstrap_effective_t`** for colour.
5. **DSR** (`deflated_sharpe`) at **n_trials=32** — DELTA vs run 1's 30. The program ledger now
   carries ~30+ trials across both markets; **32** is used to be honest (a STRICTER deflation).
   DSR≥0.90 is the ONLY door to a scored GO.
6. **Split-half sign-stability:** chronological halves at the median episode index; GO requires SAME
   SIGN in both halves.
7. **Survivorship lower bound** (§3.9); the GO must survive on the lower bound (mean POSITIVE,
   HAC t ≥ 1.0).

---

## 5. Pre-registered GATES & verdict rule (frozen — identical to H_INCL_PREREG §5)

Per-trial (T-ANN, T-EFF):
- **GO** — ALL of: HAC t ≥ **+2.0** (one-sided positive) AND passes BH-FDR at 0.10 AND
  **DSR ≥ 0.90** at n_trials=32 AND split-half SAME-SIGN AND episode-K ≥ **8** AND the survivorship
  LOWER bound mean CAR still POSITIVE with HAC t ≥ 1.0.
- **ACCRUE** — mean CAR POSITIVE and (HAC t in [+1.0, +2.0) OR DSR in [0.50, 0.90) OR episode-K < 8
  OR survivorship band flips the lower-bound sign).
- **NO-GO** — mean CAR ≤ 0 at +20d, OR split-half SIGN-FLIPS, OR HAC t < 1.0 with DSR < 0.50.
- **KILL** — mean CAR significantly NEGATIVE (HAC t ≤ −2.0) at the primary horizon.

Battery verdict = the set {T-ANN, T-EFF}. **No wiring.**

## 6. Honest prior (pre-stated)

Mechanism impound is expected to PERSIST → **NO-GO remains the likely outcome**: the demand is
front-run into the pre-fill window (run 1: +5.3% t−10..t0), and a nightly-rendered dashboard's
next-close fill lands *after* the pop. The open question this deeper panel answers: **does a slower
post-inclusion drift exist in the small/mid caps that the mega-cap panel lacked?** The seed to watch
is the **T-ANN +5d cell (HAC t=1.65 on run 1)** — if the small/mid-cap additions carry a real
post-fill drift, it should strengthen there; if it stays sub-threshold or the mechanism is still
pre-impounded, the battery is a context chip, never a ranker.

## 7. What this does NOT show (pre-committed)

- Not a full-universe result — 545 names ≈ current HSCI + legacy panel; delisted micro-caps still
  unobserved (imputed-0 lower bound, not a correctable bias).
- Not causal ID beyond timing; not tradeable net of costs/borrow (gross index-relative CAR).
- Not out-of-sample walk-forward; split-half is in-sample chronological sign-stability.
- Ext-store adjusted-close is assumed dividend-adjusted consistent with `closes_deep`; if a source
  mixes raw/adjusted the CARs on those names carry that noise (a labelled data-quality caveat).
- SZSE (深港通) adds cross-checked, not exhaustively unioned (SSE record; ~90% overlap).

## 8. Registry

**Update the EXISTING** `data/experiments/registry_seed.json` entry
`hkca_h_incl_connect_events` (do NOT duplicate) with the re-run result, verdict, and the new
studiable-K / coverage. No new forward ledger (in-tree backtest on committed roster + local panel).
