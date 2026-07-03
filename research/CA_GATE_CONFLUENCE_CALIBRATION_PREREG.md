# CA-GATE — Confluence-Gate Calibration on Canada · Phase-0 PRE-REGISTRATION

**Battery:** CA-GATE (HK/Canada masterplan §5.3 entry-layer gate; audit HKCA-1). **Branch:** `hkca-ca2-gate`.
**Author:** research agent (Opus 4.8). **Pre-reg committed:** BEFORE any measurement run (this commit is the audit trail).
**Wiring:** NONE. Report + registry append only. No live engine / board / gate param touched in this PR.

---

## 0. The owner's question, restated as a measurable claim

**Owner's hypothesis (verbatim frame):** *"the US system is able to detect stocks that are about
to go up in Canada."*

The "US system" here is the confluence BUY GATE — `engine/signal_gate.py :: is_buyable` gating on
`engine/confluence_tiers.py :: cascade` — the T1–T4 MACD-2D × StochRSI-3D cascade. It is WIRED for
CA (the CA Standout board calls `is_buyable`) but was calibrated on 110 held-out **US** names
(TIERED_CASCADE.md) and **never measured on Canadian forward returns** (audit HKCA-1).

**Measurable claim.** A freshly-fired BUYABLE cross (tier ∈ {T1,T2,T3}, per exact production logic)
on a Canadian name predicts **positive forward excess return vs `_GSPTSE`** over 1w/2w/4w, and does
so **above the name's own base rate** (matched non-event windows), per tier and pooled.

**Honest prior.** The gate is an entry-HYGIENE / not-topped / freshness filter, NOT an alpha model
(signal_gate docstring §2; it is DISPLAY-ONLY by charter). Sibling CA evidence is sobering:
CA medium-term cross-sectional momentum is ACCRUE-only (C7, DSR 0.37) and CA short-term reversal is
a **KILL with power** (masterplan H4 CN-analogue is dead). So the null-ish prior is: the gate may
show a small positive lift on a fresh, not-topped, oversold-reclaim cross (that is what it is built
to select) but is **unlikely to clear the DSR≥0.90 standalone-alpha bar** on the 5y CA name panel.
This battery reports numbers either way and does not need a GO to be useful — it CALIBRATES an
existing mechanism (§5.3 / §5.3-frame below).

---

## 1. Exact production logic being reconstructed (NO re-implementation of the signal)

The event definition reuses the **shipped** engine, not a re-derivation:

- Per-name/per-ETF per-day tier via `engine.confluence_tiers.tier_stream(daily_close)` — the
  module's own **vectorized, point-in-time, leak-free twin of `cascade`** (its docstring: "on the
  LAST bar of any truncation it reproduces cascade's tier EXACTLY when T1 is taken via the raw-3D-
  cross fallback"; `tests/test_confluence_tier_stream` pins this). It shares every constant, the
  `not_topped` veto, `FRESH_TICKS`, the 2D/3D→daily leak-free known-date mapping, and the tier
  precedence with `cascade`.
- **BUYABLE tiers** = `signal_gate.BUYABLE_TIERS = ("T1","T2","T3")` (T4 excluded by production spec).
- A **BUYABLE-CROSS EVENT** for a name = a day `t` where `tier_stream.tier[t] ∈ {T1,T2,T3}` AND
  `tier[t-1] ∉ {T1,T2,T3}` (a FRESH entry into buyable state — a rising edge). Consecutive buyable
  days are the SAME event (matches `is_buyable`'s "just-crossed / about-to-cross" freshness intent).
- **Per-tier bucket** = the tier on the entry day `t`.

### 1.1 The one documented divergence from the live board (stamped, not hidden)
`tier_stream`'s **T1** uses the **raw 3D RSI-MACD cross as the `take` fallback** (cascade's own
fallback when no §7 `take_date` is supplied). The LIVE board's T1 is the validated §7 master
(`signal_quality.analyze` buy-filter endorsed), which is a **strict subset** of the raw-cross T1.
→ Consequence: the measured **T1 population is a SUPERSET** of production T1 (it includes raw 3D
crosses the buy-filter would have blocked). This is a **conservative dilution** for a T1 verdict:
if raw-cross-T1 shows positive lift, the buy-filter-endorsed subset is weakly expected to be ≥ that;
if raw-cross-T1 is negative, the endorsed subset is NOT necessarily negative. **T2 and T3 are
computed identically in `cascade` and `tier_stream`** (no fallback divergence), so T2/T3 verdicts
map 1:1 to production. This asymmetry is pre-registered here and re-stated in the report's "what this
does NOT show". (A confirmatory §7-master T1 pass via per-day `cascade` is OUT OF SCOPE for phase-0
budget; flagged as follow-up.)

---

## 2. Panels, benchmark, fills (data reality per masterplan §1)

- **(a) CA name panel:** `data/canada_search/closes.parquet` — 219 names, 2021-06-14→2026-06-30
  (all `.TO`, zero TSXV; Financials ≈29% wt — a stamped concentration caveat). Expect thousands of
  events. **Modern-only** (2021→) — this is the ONLY history the panel has.
- **(b) 12 TSX sector ETFs (deep control):** `data/canada/{XEG,XFN,XGD,XMA,XIT,XUT,XRE,XST,XCG,XCD,ZEB,XBM}.TO.parquet`
  — inceptions 2001→ (XEG/XFN/XGD/XIT 2001; XBM/XUT/XST 2012; others between). Deep-history control
  answers "does the gate work on Canadian instruments across a full multi-cycle sample" where the
  name panel cannot (only 5y). ETFs use their own tier_stream events; benchmark still `_GSPTSE`.
- **Benchmark:** `data/canada/_GSPTSE.parquet` `close` (S&P/TSX Composite; index level, 1979→).
- **Fills:** forward window opens at the **next valid close** AFTER the cross day `t` (i.e.
  entry = close[t+1]; the cross is only known at close[t]). Horizons **1w=5, 2w=10, 4w=21 trading
  bars** measured close[t+1]→close[t+1+h].
- **Excess return:** `r_name(t+1→t+1+h) − r_GSPTSE(t+1→t+1+h)`, simple returns, both on the SAME
  trading dates (GSPTSE reindexed to the name's calendar, next-valid-close on missing).
- **yahoo close semantics (memory gotcha):** name/ETF `close` is dividend-ADJUSTED total-return;
  GSPTSE `close` is index level (price). This biases name excess UPWARD by roughly the dividend
  carry over the window (~0.5–0.9%/yr TSX yield → ≈0.01–0.04% over 5–21 bars). Small vs the effect
  sizes we could act on, but **stamped**, and it applies EQUALLY to event and non-event windows, so
  the **base-rate-differenced lift (§3) nets it out** — the differenced lift is the headline.

---

## 3. The natural benchmark — matched non-event windows (base rate, not zero)

The gate's value is **lift over the name's own base rate**, not raw positive return (a name in an
uptrend has positive base excess regardless of the gate). For each name/ETF:

- **Event set E** = all buyable-cross entry days.
- **Matched control set C** = for each event, draw **one** random NON-event day from the SAME name
  that is (i) not within ±5 bars of any event, (ii) has ≥21 forward bars available. Seed fixed
  (`SEED=20260703`) and stated. If a name has `k` events it contributes `k` matched controls
  (same-name matching removes cross-name level differences; same count balances weight).
- **Headline lift** per (tier, horizon) = `mean(excess | event) − mean(excess | matched control)`.
- Pooled across names within each tier and horizon. Also report raw event mean (undifferenced) for
  transparency, but the **DECISION reads the base-rate-DIFFERENCED lift**.

---

## 4. ONE trial family + the gate battery (pre-committed)

**Trial family (multiple-testing budget):** `ca_confluence_gate`. Every reported (tier × horizon ×
panel × differenced/raw) statistic competes to produce the per-tier verdict, so they share ONE
family. **Declared budget** logged via `TrialLedger.with_declared_budget(N, "ca_confluence_gate")`.
Itemized configs: 3 tiers × 3 horizons × 2 panels × 2 (raw + differenced) = **36**; plus the pooled
(all-tier) and per-panel pooled variants and the split-half re-scores counted → **declared budget
N = 40** (program-level ledger is ≈40; this battery is stamped at 40, the conservative ceiling).

**Gates (constitution §6, ALL must be reported; a POSITIVE verdict requires the marked subset):**

| Gate | Rule | Required for a POSITIVE (keep/earn-badge) verdict |
|---|---|---|
| HAC t | `newey_west_tstat` on the per-event **differenced** excess series, lags=4 | **|t| ≥ 2.0** with correct (positive) sign |
| BH-FDR | `benjamini_hochberg` across the 9-cell family (3 tiers × 3 horizons) on the name panel, α=0.10 | **reject=True** (survives FDR within family) |
| DSR | `deflated_sharpe` on the per-event differenced-excess "strategy return" stream, `ledger=with_declared_budget(40,…)`, `t_eff` from `bootstrap_effective_t` | reported for any **standalone-alpha** claim; **DSR≥0.90** REQUIRED only to claim alpha, NOT required for the calibration keep/demote decision (§5) |
| Split-half sign-stability | Split events by calendar median date; both halves must share the lift SIGN | **same sign both halves** |
| Effective-N (independent episodes) | Cluster events within a name that overlap in forward window; count distinct non-overlapping episodes as effN | report effN; **effN ≥ 30** per tier for a decision (else ACCRUE-data) |
| Survivorship stamp | CA panel = current-membership snapshot (delisted names absent). Stamp direction of bias. | stamped, not gating |

## 5. PRE-REGISTERED per-tier verdicts + re-parameterization rule (§5.3 calibration frame)

This calibrates an EXISTING inclusion/hygiene mechanism, so the decision follows the
**calibration-evidence frame (masterplan §5.3)**, distinct from the standalone-alpha DSR frame:

- **KEEP-BADGE (positive):** the tier's differenced lift is **positive, FDR-surviving (reject=True),
  HAC |t|≥2.0, and split-half sign-stable**, with effN≥30. → The tier keeps its `buyable` weight on
  CA. If it ALSO clears DSR≥0.90 it may additionally be cited as standalone CA alpha (a stronger,
  separate claim).
- **DEMOTE-FLAG (negative):** the tier's differenced lift is **negative AND split-half sign-stable
  AND HAC |t|≥2.0** (stable negative with power). → The tier is **FLAGGED for demotion from
  'buyable' ON CANADA** — the exact re-param is: introduce a per-market gate constant
  **`CA_BUYABLE_TIERS`** (precedent: per-market blend knobs `CN_TIER_FRAC`/`CN_WN_FLOOR` in
  `scripts/build_china_library.py`; per-market params are established) set to the US
  `BUYABLE_TIERS` **minus the demoted tier(s)**, applied ONLY on the CA board. NO WIRING in this
  phase-0 PR — the re-param is written as the proposed W-later change with the exact constant + call
  site (`build_canada.py`'s `is_buyable` call), gated on this evidence.
- **ACCRUE / INDETERMINATE:** any tier that is neither stably positive nor stably negative (fails
  sign-stability, or |t|<2.0, or effN<30) → **no change**, badge unchanged, re-test on deeper
  history (name panel matures; ETF deep panel is already the deep read). CA fine-print stays
  "US-calibrated" per §5.3.

**Pooled (all-buyable) verdict** is reported but is NOT a tier decision — it is the direct answer to
the owner's literal question ("does the gate detect names about to go up") as a single lift number
with its gate row.

## 6. What this battery will NOT show (pre-committed honesty)
- NOT whether the LIVE §7-master T1 (buy-filter endorsed) has the measured raw-cross-T1 lift — only
  a superset is measured (§1.1). T2/T3 map 1:1.
- NOT execution alpha net of realistic CA costs/slippage/borrow — differenced excess is gross,
  next-close-fill, no cost model in the headline (a cost-stamped variant may be reported as context).
- NOT a claim about delisted/suspended names (survivorship: current-membership panel).
- NOT causal — the gate CO-OCCURS with oversold-reclaim + not-topped states; the lift (if any) is
  the joint selection, not an isolated MACD-cross treatment effect.
- NOT a re-calibration of tier WEIGHTS (T1..T4 = 1.0..0.4) — only the binary buyable/not-buyable
  membership on CA is in the decision frame here.

## 7. Outputs
- `reports/ca-gate-confluence-phase0.md` — **bold verdict** per tier + pooled, full gates table,
  headline lift numbers, "what this does NOT show" section.
- Registry append (at END): one `ca_confluence_gate` row with real `come_back_on` (name panel 21d
  scoreboard matures ≈ late-Aug 2026 per §5.4; deep-ETF read is final now).
- Runner: `scripts/ca_gate_confluence_phase0.py`. NO engine/board edits.
