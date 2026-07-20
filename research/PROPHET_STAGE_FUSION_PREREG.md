# Prophet × Stage-Analysis fusion — pre-registration (PSF)

Status: **PRE-REGISTERED** 2026-07-20, committed BEFORE any graded result (house epistemics
law: pre-registered gates; nulls printed, not hidden). Program: SGA phase-2. Operator steer
(2026-07-20): "parallel + compare first" (evidence before wiring) optimizing for **both**
higher entry quality and longer holds.

## 0. Why a mechanism test, not a Prophet replay (honest framing)

Prophet has **no backtestable history**: its forward ledger holds 5 closed entries, all after
the 2026-07-10 US go-live. Its entry gate is nonetheless a *pure* function of price+factor
data (no LLM at runtime; `engine/prophet_bridge.select_candidates` = `band≠low ∧ (act_level≥2
∨ conviction.score≥60)`), but `site/factordata/us_standouts.json` (the gate's input) is a
nightly snapshot with **no historical archive**, and `conviction.score`'s cross-sectional
alpha/z legs are not reliably PIT-reconstructable for 2022.

Therefore PSF tests the **fusion mechanism** — "does Stage-2 + earnings-quality filtering
improve a *validated, PIT-replayable timing entry*?" — using the repo's **validated T1–T4
confluence cascade** (`engine/confluence_tiers`, close-only, the "keeper the whole system is
built around") as the replayable base signal. This is a legitimate Prophet-family timing
entry. If the mechanism adds edge here, it is strong evidence it will help Prophet's own
timing entries — which we then confirm by a **forward-shadow on live Prophet from go-live**
(first clean 126-bar cohort matures ~Dec 2026). If it adds no edge here, Stage/EC stay
display-context and Prophet is unchanged. The proxy nature is disclosed on every result.

## 1. Hypotheses (committed before results)

- **PSF-H1 (stage quality lifts a timing entry).** Among T1/T2 fresh-fire entries over the
  2022-01-01…2026-07-17 US universe, restricting to **Stage-2-at-entry** raises the
  CLEAN_LIFTOFF win-rate **and** the median hold-to-favorable-exit vs the unfiltered set.
- **PSF-H2 (earnings quality adds on top).** Among Stage-2 T1/T2 entries, restricting to
  **positive earnings-call quality at entry** (most-recent `earnings_call_sent ≥ 24` — their
  published gate) further raises the 63d/126d win-rate vs Stage-2 alone.
- **PSF-H3 (longer holds).** Stage-2 (and Stage-2∩EC) entries reach the +15% liftoff band
  with a **longer median favorable-excursion horizon** and a **lower STOPPED rate** than the
  unfiltered arm — the "supports EquityDesk-style ~8-week holds vs our 2–3wk" leg.

## 2. Arms (identical universe, entry events, and ruler; only the filter differs)

Base entry event = a **T1 or T2 fresh fire** (`confluence_tiers` cascade fresh-tick) on a
completed weekly/daily bar for a name in the PIT universe.

- **Arm A — timing alone:** every T1/T2 fresh fire (the control).
- **Arm B — timing ∩ Stage-2:** A filtered to `weinstein_stage.classify` stage==2 at entry.
  Reported twice: B (any Stage-2) and **B-fresh** (Stage-2 ∧ weeks_in_stage ≤ 10 — their
  freshness gate).
- **Arm C — timing ∩ Stage-2 ∩ EC:** B filtered to most-recent `earnings_call_sent ≥ 24`
  (robustness: also at ≥ cross-sectional median). EC joined from
  `data/stage_analysis/backfill/earnings_calls.parquet` on `company_ticker` with
  `call_date < entry_date`, most-recent row (coverage 2022–26: ~10k rows/yr).

## 3. Ruler (the one-grader spine — fixed before results)

`engine/grading.py`: next-bar fill; forward-only windows; delisting-imputed
(`dead_name_prices`); survivorship via `as_of_panel` (`sp1500_pit_membership` for pre-2026).
- **Win** = `terminal_state == CLEAN_LIFTOFF`; **loss** = `STOPPED`; `CUSHIONED`/`DEAD_MONEY`
  = messy middle. Two parameterizations: **clean15_126** (+15% before −5%, 126 bars — the
  positional/hold thesis) and **clean8_21** (+8% before −5%, 21 bars — the rotational).
- **Hold / longer-hold metric** = bars-to-MFE-liftoff (first bar reaching the +15% band) and
  the STOPPED-rate; drawdown = `fwd_mdd_{21,63,126}`; return = `fwd_ret_{21,63,126}`.

## 4. Metrics per arm (all printed, including nulls)

n_entries, **n_dates (independent signal dates, not overlapping obs)**, CLEAN_LIFTOFF
win-rate with **Wilson 95% CI**, STOPPED rate, mean/median `fwd_ret_63`/`fwd_ret_126`,
median `fwd_mdd_126`, median bars-to-liftoff. Reported overall and per regime.

## 5. Falsifiers + kill rules (committed)

- **PSF-H1 FAILS** iff the Wilson-CI lower bound of (win-rate_B − win-rate_A) ≤ 0 at
  n_dates ≥ 25 → Stage-2 adds no win-rate edge on a timing entry → **do NOT gate/bonus**;
  stage stays display-context (retained as confluence input — a null never deletes the layer).
  Symmetric on hold: PSF-H3 fails if median hold_B ≤ hold_A and STOPPED_B ≥ STOPPED_A.
- **PSF-H2 FAILS** iff the Wilson-CI lower bound of (win-rate_C − win-rate_B) ≤ 0 at
  n_dates ≥ 25 → EC filter adds nothing on top of stage → EC stays display-context.
- **KILL** (append DO_NOT_REBUILD §2) iff a negative point estimate persists at n_dates ≥ 50
  across ≥ 2 regimes.

## 6. Decision rule → integration (maps to operator's "compare first")

- **Both B beats A (win-rate ∧ hold, CI-clean) AND C beats B** → recommend a **gauntleted
  confluence bonus** (Stage-2 + positive-EC as a ≤0.10 additive term in Prophet's
  conviction/ranking via `signal_gate.blend_sorted(bonus_of=…)`), NOT a hard veto — a positive
  result still shows non-Stage-2 entries aren't worthless, and a hard veto rejects Prophet
  winners. Confirm forward on live Prophet before promoting past display.
- **B beats A strongly AND non-Stage-2 (esp. Stage-4) entries show materially worse outcomes
  (high STOPPED)** → additionally consider a **hard veto** on Stage-4-at-entry only.
- **Null** → stage/EC remain display-context; Prophet unchanged; the live-Prophet
  forward-shadow (tag every entry from go-live with stage_at_entry + last_ec, grade at
  maturity) continues to accrue as the definitive on-Prophet test.

## 7. Look-ahead controls (audited before ship)

All inputs truncated to the entry bar: `weinstein_stage.classify` on `close[:entry]`;
EC `call_date < entry_date`; next-bar fill; forward-only `fwd_mdd`; PIT membership; late-IPO
names (< 45 completed weeks before entry) excluded from stageable arms and **counted, not
hidden**. Base signal, arms, ruler, and thresholds in §2–§4 are frozen by this commit; any
change is an amendment row here, dated, before re-running. Proxy disclosure (§0) printed on
every surfaced result. The word "validated" is reserved for the T-cascade's existing backing
artifact only — PSF results are display-tier until an operator-ratified promotion.
