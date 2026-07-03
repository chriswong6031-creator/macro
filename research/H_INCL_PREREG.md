# H-INCL — Stock-Connect (Southbound / 港股通) Inclusion Events — PRE-REGISTRATION

**Battery:** H-INCL (HK/Canada masterplan §3 "H-INCL — Connect inclusion/exclusion events").
**Wave:** W3 (phase-0 battery B). **Branch:** `hkca-w3-hincl`.
**Author:** quant research agent. **Status:** PRE-REGISTERED — committed BEFORE any event-study run.
**Constitution:** masterplan §6 (pre-reg first; HAC t; BH-FDR within family; program-level DSR
`n_trials=30`; split-half sign-stability; effective-N = independent episodes; DSR≥0.90 the only
door to a scored GO; survivorship bounds not stamps; suspension-honest fills; verdicts
GO/NO-GO/KILL/ACCRUE). Red-team demands honoured verbatim: HK_CANADA_REDTEAM_FINDINGS.md
CRITIC:hk MISSING ("Stock-Connect INCLUSION/exclusion events are absent … a clean, dateable event
study with real n over 2016→, the causal front-run of the very H1 flow"); CRITIC:quant MAJOR
("Connect eligibility CHANGES over time and membership is only known ex-post — using today's list
back to 2017 is a look-ahead/PIT violation … Source or reconstruct point-in-time Connect
southbound eligibility").

---

## 0. STEP-1 gate result (roster feasibility) — recorded here BEFORE STEP-2

The battery's own gate is roster feasibility. **Result: FEASIBLE (roster obtainable free, dated,
2016→).** Documented in full in the report; summary of what was tried and what landed:

- **HKEX "View All Eligible Securities"** (`hkex.com.hk/…/View-All-Eligible-Securities`) — lists
  SSE/SZSE (NORTHBOUND) securities + `Change_of_SSE/SZSE_Securities_Lists.xls`. It does NOT carry
  the SEHK (southbound 港股通) list. Not usable for southbound. (verified by fetch)
- **akshare `stock_hk_ggt_components_em`** — southbound components, but a CURRENT snapshot only
  (Eastmoney `clist/get`, no effective dates, no removal history). Its host `push2.eastmoney.com`
  is WAF/UA-blocked on our network (RemoteDisconnected/502). Snapshot-only → not a dated series.
- **HKEX CCASS "Stock Connect Southbound Shareholding Search By Date"**
  (`www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk`) — the per-date holder search. A name only
  appears once eligible, so the per-date name-set = the roster as-of that date. BUT probed
  empirically: **strict trailing ~365-day rolling window** — `2026/07/03` … `2025/07/03` populate
  (~840 codes), `2025/07/02` and earlier return the 7.5 KB empty page. Cannot reach 2016. (This
  mirrors the Eastmoney 2-y holdings rolling-window red-team finding.) Not usable for deep history.
- **SSE 港股通标的证券调整信息 / 港股通公告 archive** (`sse.com.cn/services/hkexsc/disclo/announ/`) —
  **the usable dated add/remove series.** Paginated `s_list_N.shtml` (15 items/page); page 2→27
  enumerable; **archive floor page 27 = 2015-09** (Connect launch era), latest page 2 = 2026-07.
  Each 标的调整 notice `c/c_YYYYMMDD_ID.shtml` is a structured HTML table: one row per stock with an
  explicit **调入 (add) / 调出 (remove)** action cell + effective-date phrasing ("自下一港股通交易日
  起", "生效"). Verified end-to-end on `c_20260306_10811051.shtml` (41 add / 20 remove parsed). This
  is the SH-HK southbound link's adjustment record; the union southbound roster (SH+SZ) is ~90%
  overlapping and SSE is the cleanly-enumerable authoritative source.
- **SZSE 深港通 adjustments** (`szse.cn/disclosure/notice/…`) parse identically (调入/调出/生效
  verified on `t20250908_615862.html`) — used as a robustness cross-check, NOT the primary
  enumeration (its list API `annList` 500s to our UA; per-notice HTML is fine).

**Gate verdict: PASS → build `data/hk_connect_roster/roster.parquet` and run STEP-2.** (Had the SSE
archive not existed free, the pre-registered fallback was BLOCKED-DATA + an accrual path: capture
the CCASS 1-y rolling window forward from today and re-run the event study in ~2028.)

---

## 1. Hypotheses

The mechanism (masterplan honest prior): when a HK name is **added** to the southbound Connect
eligible list, the mainland retail/institutional crowd **becomes able to buy it** — a one-off
positive demand event. Two pre-registered, distinct causal windows (the masterplan's "two variants
— announcement drift vs inclusion-day demand"):

**H1 (announcement-drift, primary, one-sided long).** From the **next open after the announcement
date**, an added name earns POSITIVE abnormal return vs `_HSI` over the forward window, as the
market front-runs the not-yet-effective inclusion.

**H2 (inclusion-day-demand, primary, one-sided long).** From the **next open after the EFFECTIVE
date** (the first southbound-tradable day), an added name earns POSITIVE abnormal return vs `_HSI`
over the forward window, as the marginal southbound buyer's demand impounds.

**H0** (each): mean cumulative abnormal return (CAR) over the window = 0.

**Exploratory, NON-GATED, labelled:** the −10..0 pre-effective run-up (is the demand already
impounded before the effective date — i.e. does H2 have nothing left?) and the REMOVAL (调出) side
(symmetric de-rate). Neither is in the GATED family, neither FDR-corrected against H1/H2, neither
DSR-gated.

**Family = 2 gated trials {announcement, effective-date}** (as specified in the battery brief).

---

## 2. Constructions (exact, frozen)

### 2.1 Roster construction (`data/hk_connect_roster/roster.parquet`)
- Enumerate SSE `s_list_N.shtml`, N=2..27; keep notices whose title contains 标的 + 调整/名单 (the
  periodic-review AND ad-hoc adjustment notices). Fetch each `c_YYYYMMDD_ID.shtml`.
- Parse the adjustment table: each `<tr>` yielding a **5-digit HK code** + an action cell
  containing **调入** → `action="add"` or **调出** → `action="remove"`. Codes are the HKEX 5-digit
  form (e.g. `02692`); normalize to our panel form `NNNN.HK`/`NNNNN.HK` by left-strip of one
  leading zero where the panel uses 4-digit (`00700`→`0700.HK`).
- **effective_date** = the announcement's stated effective trading day. Announcement wording is
  "自下一港股通交易日起生效" (effective from the next southbound trading day). We record BOTH:
  `announce_date` (from the notice URL `c_YYYYMMDD`) and `effective_date` = the next HK trading day
  present in the `_HSI` calendar strictly after `announce_date` (the notices are published after
  close; the next Connect day is the first tradable day). Where a notice states an explicit later
  effective date in-text, that explicit date overrides (parsed if present; else next-HSI-day rule).
- Columns: `ticker` (NNNN.HK form), `action` (add|remove), `announce_date`, `effective_date`,
  `code5` (raw 5-digit), `source` (`sse`), `notice_url`. One row per (stock, action, notice).
- Provenance note file `data/hk_connect_roster/PROVENANCE.md` (source URLs, archive floor, parse
  method, the CCASS/akshare/HKEX routes that were rejected and why, SZSE cross-check status).
- **Dedup / sanity:** drop exact duplicate (ticker, action, effective_date) rows. Report add/remove
  counts per year and the total distinct add events.

### 2.2 Price panel & abnormal-return construction
- Price panel = `data/hk_search/closes_deep.parquet` (157 names, dividend-adjusted close, 1986→
  2026-06-18) — the **only in-tree HK name panel** (masterplan's `hk_stocks_ext` is a *planned* W1
  collector, NOT in tree; stated as a scope limit, see §7). Benchmark = `_HSI` (`data/hk_search/
  _HSI_deep.parquet`, 1986→2026-06-12).
- An addition event is **STUDIABLE** iff its `ticker` is a panel column AND the panel has a valid
  close on the fill bar AND ≥ the forward window of subsequent valid bars.
- **Fill (next-bar, no look-ahead):**
  - H1: entry at the panel close on the **first trading day strictly after `announce_date`**.
  - H2: entry at the panel close on the **first trading day strictly after `effective_date`**
    (i.e. next open after the data's real-world availability — here we use next *close* as the
    conservative fill since the panel is close-only; stated).
- **Abnormal return** = stock cumulative log-return − `_HSI` cumulative log-return over the SAME
  calendar window (CAR, market-model with beta≡1 / index-relative; a full β-adjusted market model is
  a labelled robustness variant, NOT the primary — beta estimation on thin pre-event windows adds
  noise, index-relative is the pre-registered primary).
- **Event window:** −10 … +60 sessions around the fill bar (per brief). Reported CAR curve.
  **Pre-registered decision horizons:** primary **+20 sessions (≈1 month)**; robustness +5, +10,
  +40, +60 reported as a curve (nuisance dimension, NOT separate FDR slots).
- **Suspension / halt / missing-bar rule (mandatory, HK-specific):** HK names halt for weeks. If
  the panel has **no valid print within 5 sessions after the intended fill bar**, the event is
  **EXCLUDED** (never forward-filled — brief's suspension rule verbatim). Within a window, cumulate
  over PRESENT bars only on the intersection of stock/index available dates; never ffill through a
  gap. If the forward window runs past the panel's last bar (2026-06-18), the event is DROPPED
  (no partial window).

### 2.3 Effective-N: episode clustering (semi-annual review batches)
Semi-annual review batches add many names on the SAME effective date; those events share the same
market state and are NOT independent. **Pre-registered effective-N rule (per brief "treat each
review batch as ONE episode"):** an *episode* = one distinct `effective_date`. The event-level CAR
is first **averaged within each effective_date** (equal-weight across studiable names added that
day) → one CAR observation per episode. HAC / DSR / split-half run on the **episode-level** CAR
series (K = number of distinct add-effective-dates with ≥1 studiable panel name). We ALSO report the
raw event count (studiable names) and `bootstrap_effective_t` on a synthetic daily-excess stream for
context, but the **binding effective-N is the episode count K**.

### 2.4 Survivorship bound (not a stamp)
The panel is current-constituent (157 survivors). For an *inclusion* event this biases toward names
that stayed important enough to be in today's panel — an UPPER bound on the true effect (names added
then delisted/shrank are absent, and those are disproportionately the disappointments).
**Bound method:** report (a) the panel-studiable estimate (upper bound), and (b) a *worst-case
delisted-name* bound — impute every roster addition that is NOT in the panel (the non-survivors +
small-caps) as CAR = 0 at its horizon (a conservative "the effect only exists for survivors" floor
is not defensible; the honest worst case for an inclusion long is that the missing names did
NOTHING), recomputing the mean over (studiable ∪ imputed-0). The gap between (a) and (b) is the
survivorship band. A GO requires the LOWER bound (b) to still clear the gate, not just (a).

---

## 3. Trials & families (frozen trial list)

**GATED FAMILY (H-INCL) — 2 trials, one BH-FDR family (α=0.10):**
| Trial | Event anchor | Fill | Primary horizon | N basis |
|---|---|---|---|---|
| T-ANN | announcement date | next bar after `announce_date` | +20d | episode = distinct announce-date |
| T-EFF | effective date | next bar after `effective_date` | +20d | episode = distinct effective-date |

**EXPLORATORY NON-GATED (labelled, not in any FDR family, not DSR-gated):** pre-effective run-up
(−10..0), removal (调出) de-rate side, β-adjusted market-model variant of T-EFF.

Every variant counts toward the PROGRAM trial ledger; program-level DSR uses **n_trials=30**
(masterplan §6, counts every config across both markets — not just this family).

---

## 4. Statistics (frozen)

For each gated trial (T-ANN, T-EFF), primary horizon +20d, on the **episode-level** CAR series:
1. **HAC t** (`newey_west_tstat`, lags=4) on the episode CAR series. Report mean CAR, HAC se, t, p.
2. **BH-FDR** (`benjamini_hochberg`, α=0.10) across the 2 gated p-values.
3. **`block_bootstrap_ci`** on the episode CARs (block=4, B=5000, seed=7) → distribution-free 90% CI.
4. **`bootstrap_effective_t`** for context (synthetic daily-excess stream); report `t_eff` as colour.
5. **DSR** (`deflated_sharpe`) at **n_trials=30**: Sharpe of the episode-CAR series (mean/std of the
   K episode CARs), its skew/kurt, T=K, t_eff passed through. **DSR≥0.90 is the ONLY door to a
   scored GO.**
6. **Split-half sign-stability:** split episodes at their **median effective_date** (chronological
   halves). Require mean CAR SAME SIGN in both halves for a GO.
7. **Survivorship band:** repeat mean-CAR + sign with the imputed-0 non-panel additions (§2.4 (b));
   the GO must survive on the lower bound.

---

## 5. Pre-registered GATES & verdict rule (frozen)

**Honest prior (brief):** "decision-grade n; mechanism causal … the HK battery most likely to GO —
hold it to the same gates anyway." BUT a documented power risk (pre-stated, not post-hoc): the only
in-tree panel is 157 mega-caps, while most southbound ADDITIONS are small/mid-caps entering Connect
— so the STUDIABLE add-events (panel ∩ roster-adds) may be FEW, and episode-K (distinct add-dates
with a studiable name) fewer still. Effective-N is reported up front (§6) and the verdict is graded
on episode-K, not the raw roster size.

Per-trial verdict (T-ANN, T-EFF):
- **GO** — ALL of: HAC t ≥ **+2.0** (one-sided pre-registered positive) AND passes BH-FDR at 0.10
  AND **DSR ≥ 0.90** at n_trials=30 AND split-half SAME-SIGN AND episode-K ≥ **8** (min power floor)
  AND the survivorship LOWER bound (§2.4 b) mean CAR still POSITIVE with HAC t ≥ 1.0.
- **ACCRUE** — mean CAR POSITIVE and (HAC t in [+1.0, +2.0) OR DSR in [0.50, 0.90) OR episode-K < 8
  OR survivorship band flips the lower bound sign). A real-but-underpowered/thin signal → register +
  come back once `hk_stocks_ext` (the ~500-name expanded HSCI panel, planned W1) lands and lifts
  studiable-K.
- **NO-GO** — mean CAR ≤ 0 at +20d, OR split-half SIGN-FLIPS, OR HAC t < 1.0 with DSR < 0.50.
- **KILL** — mean CAR significantly NEGATIVE (HAC t ≤ −2.0) at the primary horizon.
- **BLOCKED-DATA** — (only if STEP-1 had failed) roster unobtainable; not applicable (gate passed).

Battery verdict = the set {T-ANN, T-EFF}. **No wiring** — reports only (masterplan W3 acceptance).
NOTHING is wired into any engine or board.

---

## 6. Effective-N honesty (pre-stated)

Effective-N for the gated statistic is the **episode count K = distinct add-effective-dates (or
add-announce-dates for T-ANN) with ≥1 studiable panel name**, NOT the roster add count and NOT the
studiable event count. Because most Connect additions are non-panel small/mid caps, we PRE-STATE the
expectation that K is likely **well below the ~200–400 raw add events** the masterplan's honest
prior anticipated for a full-universe panel — possibly into the ACCRUE-by-power range on the
157-name panel. The report states K explicitly and grades on it. Deeper-panel re-run (planned
`hk_stocks_ext`) is the registered accrual path.

## 7. What this test does NOT show (pre-committed)

- Not a full-universe result: the in-tree panel is 157 mega-caps; the small/mid-cap additions where
  the marginal-buyer demand shock is largest are NOT observed. Studiable-K is a floor on power.
- Not causal identification beyond the event timing (index membership changes correlate with size/
  liquidity/A-share events that also move price).
- Not tradeable net of costs/slippage/HK borrow; CAR is gross index-relative buy-and-hold.
- Not out-of-sample walk-forward; split-half is in-sample chronological sign-stability.
- Survivorship: current-constituent panel; §2.4 reports an upper AND a worst-case lower bound, not a
  stamp — but the true small-cap universe is unobserved (a scope limit, not a correctable bias here).
- SZSE (深港通) additions are cross-checked, not exhaustively unioned; the roster is the SSE
  (沪港通) southbound adjustment record (the two lists are ~90% overlapping).

## 8. Registry

Experiment id `hkca_h_incl_connect_events`, maturation = report-date (in-tree backtest on the
committed roster + panel, no forward ledger). `come_back_on` set for a deeper-panel re-run once the
`hk_stocks_ext` ~500-name expanded HSCI panel lands (lifts studiable-K into decision-grade). Pure
append at the END of the `data/experiments/registry_seed.json` array (merge-friendly).
