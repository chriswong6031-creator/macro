# C1b — Bearish Commodity-Flip PROTECTIVE Gate — Phase-0 Report

**VERDICT: Zero GO-for-demote. P1 (sector) ACCRUE — a real, split-half-stable, FDR-passing oil→XEG de-rate at HAC t = −1.78 (4w), one notch short of the −2.0 demote bar. P2 (name) NON-DECISION — only 5 independent oil-bear episodes exist on the 5y CA name panel (below the n<8 HAC floor), directionally protective but unpowered.** No demote gate is earned; nothing wired.

**Battery:** C1b (HK/Canada masterplan §4.1, W7-pre). **Branch:** `hkca-w7pre-c1b`.
**Pre-registration:** `research/C1b_COMMODITY_FLIP_PROTECTIVE_PREREG.md` — committed BEFORE any run
(audit trail `757b0b4879`). **Harness:** `scripts/c1b_commodity_flip_protective_phase0.py`.
**Reuses the C1 episode construction VERBATIM** (imported from `scripts/c1_commodity_sector_phase0.py`:
`slope_z`/`regime_state`/`confirmed_flips(target=-1)`/`fwd_excess`; pre-reg `4c583f7`). **NO WIRING.**

**Local data state (stamped):** `CL_F` 2000-08-23→**2026-07-02**; `XEG.TO` 2001-03-23→**2026-06-30**;
`_GSPTSE` 1979-06-29→2026-06-30; `canada_search/closes` 2021-06-14→**2026-06-30** (1267×219);
`canada_search/members` 219 names (**Energy = 38**).

---

## VERDICT (detail)

- **P1 — oil BEAR flip → XEG de-rate — ACCRUE.** On the SAME episode machinery C1 used for its
  validated long side (`target=-1`), XEG *under*performs `_GSPTSE` after oil turns bearish:
  mean **−1.16%/4w**, **HAC t = −1.78**, protective hit **62.5%**, one-sided-negative p = 0.038,
  **passes BH-FDR** at 0.10 (q = 0.038, reject), **split-half same-sign NEGATIVE** (pre-2013
  −0.45% / post-2013 −1.96%), bootstrap **P(de-rate) = 0.93**. It is real and direction-confirmed —
  but **t = −1.78 does not clear the H4 demote bar of −2.0**, and the protective Sharpe DSR is 0.24
  (far below 0.90). This is the sign-mirror of C1's oil→XEG **long** ACCRUE (t +2.75) and lands the
  same way: a genuine but sub-threshold signal → **ACCRUE, register, come back** — not a tortured
  GO-for-demote. The de-rate *builds* like the long side (t −1.31 at 2w → −1.78 at 4w → −1.64 at 6w),
  coherent with "the sector re-rates down over the following month," not a 2-week drop.

- **P2 — within-Energy HIGH−LOW oil-beta protective differential — NON-DECISION (NO-GO on power).**
  The 5-year CA name panel (2021-06→) contains only **7 confirmed oil-bear flips**, collapsing to
  **5 non-overlapping 4w episodes** — **below the `newey_west_tstat` n<8 floor**, so no HAC t can be
  computed and the pre-registered **N ≥ 8 power floor fails outright**. The raw differential is
  **directionally protective** (HIGH oil-beta names underperform LOW by raw mean **−1.8%/4w**,
  **−5.2%/6w**, protective hit rising to **0.8 at 6w**, split-half same-sign-negative at 4/6/8w) —
  consistent with the red-team's contemporaneity finding (fast transmission → high-beta names de-rate
  fast) — but at n=5 this is **descriptive, not decision-grade**. The name tier is **unrunnable at
  decision grade on this panel**; it needs the panel to lengthen. This is the pre-registered
  power-limited prior landing exactly where it was flagged.

---

## Pre-registered gates vs results (primary horizon = 4w; DEMOTE direction)

GATED family (2 trials, BH-FDR within family, DSR-protective at ledger budget n_trials=36):

| Trial | n (non-ovlp ep) | mean | HAC t | BH-FDR reject? | split-half same-sign-NEG | DSR-protective (n=36) | Verdict |
|---|---|---|---|---|---|---|---|
| **P1 oil BEAR→XEG** | 32 | **−1.16%** | **−1.78** | **YES** (q=0.038) | **YES** (−0.45% / −1.96%) | 0.24 | **ACCRUE** |
| P2 Energy HIGH−LOW β | **5** | −1.80%* | **n/a (n<8)** | — | YES (2/3 halves, n tiny) | 0.04 | NO-GO (insufficient episodes) |

\* P2 mean is the raw episode average; `newey_west_tstat` returns None for n<8, so no HAC t / one-sided
p / FDR slot exists for P2 — it is excluded from the FDR family by the n-floor, not by choice. **Because
P2 produced no p-value, the BH-FDR family collapsed to a single member (P1), so P1's q = p = 0.038
without a second-slot correction** — noted for transparency; P1's ACCRUE verdict does not turn on FDR
(the binding miss is the t-bar, −1.78 > −2.0), and program-level multiplicity is still carried by the
DSR ledger budget (n_trials = 36).

**Gate reference (pre-reg §5, H4 demote bar):** GO-for-DEMOTE requires HAC **t ≤ −2.0** AND BH-FDR
reject AND split-half same-sign-negative AND **N ≥ 8**. **P1 clears FDR + split-half + N but misses
the t-bar (−1.78 > −2.0) → ACCRUE.** **P2 fails the N-floor (5 < 8) → NO-GO/non-decision.** No trial
reaches GO-for-demote.

### Horizon curve (robustness within the same test — nuisance dimension, not FDR slots)
| Trial | 2w | 4w (primary) | 6w | 8w |
|---|---|---|---|---|
| P1 oil→XEG (mean / t / ss-neg) | −0.8% / −1.31 / Y | **−1.2% / −1.78 / Y** | −2.2% / −1.64 / Y | −1.3% / −1.03 / N |
| P2 HIGH−LOW (raw mean / n / hit_neg) | −1.2% / 6 / 0.33 | **−1.8% / 5 / 0.60** | −5.2% / 5 / 0.80 | −5.3% / 5 / 0.60 |

P1's de-rate is present 2w→6w and fades by 8w (t −1.03, split-half flips) — a month-scale de-rate,
not permanent. P2's raw differential deepens 4w→6w (−1.8%→−5.2%, hit 0.6→0.8) — directionally
encouraging but n=5 makes any t meaningless.

---

## Effective-N honesty (pre-stated §4.6)

| Trial | raw bear flips | confirmed episodes | **non-overlapping 4w episodes** | daily t_eff / raw | median cross-section |
|---|---|---|---|---|---|
| P1 oil→XEG | 35 | 33 | **32** | 640 / 640 (ratio 1.00) | n/a (ETF) |
| P2 HIGH−LOW | 35 | 33 (7 in panel) | **5** | 100 / — | 37 names/episode |

- **P1** reproduces C1's exploratory oil→XEG BEAR leg **bit-identically** (n=32, mean −1.16%, t=−1.777
  — C1 report reported n=32, −1.16%, −1.78): the harness reuse is faithful (positive control, §3.4).
  Non-overlap already removed window-overlap autocorrelation (t_eff = raw, ratio 1.00), so no further
  effective-N deflation applies.
- **P2 surprise, reported not hidden (§6.1):** the 5-year name panel yields only **7 oil-bear flips**
  (33 exist over full history; only 7 fall inside 2021-06→), **5** after the non-overlap filter — the
  pre-reg's stated power-limited prior, realized. The median per-episode cross-section is 37 qualifying
  Energy names (terciles ≈12 HIGH / 12 LOW), so the *cross-section* is healthy; it is the *episode
  count* that is starved. `newey_west_tstat`'s n<8 guard is what converts this into an honest
  non-decision rather than a fabricated t on 5 points.

---

## Split-half sign-stability

- **P1 (split 2013-01-01, a-priori per C1):** pre-2013 mean **−0.45%** (n=17) / post-2013 **−1.96%**
  (n=15) — **same-sign NEGATIVE, stable.** The de-rate holds in both halves; the sign-stability a
  demote gate requires is present. (What holds P1 back is the t-magnitude and DSR, not sign-stability.)
- **P2 (split 2023-12-31, panel midpoint, a-priori):** pre −1.29% (n=2) / post −2.14% (n=3) —
  same-sign-negative but on **2 vs 3** episodes: **informational only**, no power. Stated, not excused.

---

## Survivorship & suspension

- **P1 sector tier:** index/ETF-level (XEG vs _GSPTSE). No name-panel survivorship; both live to
  2026-06-30. **Bound: none material at the ETF level** (stamped as in C1 §2.4).
- **P2 name tier:** the `canada_search` panel is **current-constituent** (219 live TSX names, zero
  delisted). A high-oil-beta E&P that de-listed/blew up in an oil crash after a bear flip is **absent**
  → the worst high-beta losers are missing → the measured HIGH-underperformance is a **LOWER bound** on
  the true de-rate. This survivorship bias runs **toward zero**, i.e. **against** the protective finding
  — so P2's directional negativity is if anything *understated*, and any future GO-for-demote on a
  lengthened panel would be conservative. Reported as a **bound**, not a sticker: true |D| ≥ measured.
- **Suspension:** windows past data end DROPPED; leg gaps intersected on present bars, no ffill through
  a gap (P1 reuses C1 `fwd_excess`; P2 mirrors the rule per name). No CA multi-week halts over the
  window, but the rule is enforced in code.

---

## What this does NOT show

- **Not a demote gate earned.** Neither trial clears the H4 bar (t ≤ −2.0 + FDR + split-half + N≥8).
  P1 is one notch short on t; P2 fails the N-floor. **Nothing is wired.**
- **Not a tradeable protective P&L.** Episode excess/differentials are gross buy-and-hold; a real
  demote is costless but the measured de-rate is gross of slippage/borrow.
- **Not causal.** Oil-bear regimes co-move with USD-up / risk-off / rates states that independently
  de-rate TSX energy; P1 is association net of the broad market, P2 net of the common sector move —
  not identified transmission. The name differential is market-neutral by construction but not
  macro-identified.
- **Not out-of-sample (walk-forward).** Split-half is in-sample sign-stability. P2's PIT oil-beta is
  causal (no look-ahead), but the HIGH/LOW edge itself is in-sample.
- **P2 is unrunnable at decision grade.** 5 episodes < the n<8 HAC floor and < the pre-reg N≥8 power
  floor. A NO-GO here does **not** refute the mechanism — it is power-starvation, and the directional
  read (HIGH underperforms LOW, hit 0.8 at 6w) is *consistent* with it. Re-runnable when the CA name
  panel lengthens (name tier is the binding-history leg).
- **Regime-definition-dependent.** All results are conditional on the C1 slope_z + ±0.5 hysteresis +
  20d definition, **frozen and reused verbatim** (no shopping). An alternative turn definition must be
  pre-registered.
- **DSR n_trials.** Program budget **36** via `TrialLedger.with_declared_budget(36, …)` (ledger path,
  not a literal), per the DSR-plumbing regularization — honest conservative multiplicity across both
  markets. The DSR-protective column is measured on the sign-flipped (short) series so a real de-rate
  reads as a positive protective Sharpe; both trials sit far below 0.90 regardless.

---

## Relationship to C1 (the long side)

C1 (#1038) found oil→XEG **long** ACCRUE (t +2.75, DSR 0.54, builds 4→8w). C1b confirms the pair is
**two-sided and symmetric**: oil→XEG **short/protective** is also ACCRUE-grade (t −1.78, split-half
stable, FDR-passing, builds 2→6w). The single commodity→sector pair with a coherent long story also
has a coherent de-rate story — but **both** sit below their respective GO bars (long: DSR; short:
t-magnitude). The honest read across C1 + C1b: **oil↔XEG is a real, direction-confirmed, two-sided,
but multiplicity/power-underpowered transmission channel** — a live context chip (as W1b already
ships, risk-on-gated), not a scored ranker or a hard demote gate.

---

## Registry

Experiment `hkca-c1b-commodity-flip-protective` appended at the END of the
`data/experiments/registry_seed.json` experiments array (kind `phase0_backtest`, program
`hk_canada_stocks`, wave `W7-pre`, phase ACCRUE for P1 / power-starved for P2, `n_trials_program_dsr`
= 36, come_back_on set for a re-run when the CA name panel lengthens — the name tier is the
power-starved leg). No forward ledger (in-tree backtest). **Nothing wired to any live engine or board.**
