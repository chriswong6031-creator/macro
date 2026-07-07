# DT-W2: 64-Year Month-Block Time-Control Re-Run — DT-R13 Settlement

**Authority:** research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7 (DT-R13, DT-R14)  
**Run date:** 2026-07-07T00:02:10.770884+00:00  
**Study:** DT-W2  
**Family:** dt_replication_64y | m=4 | BH q=0.10

---

## DT-W2 Prereg (VERBATIM — frozen at dispatch by Fable, 2026-07-06)

- **Panel:** the ORIGINAL phase-0 universe — the 114 large-cap US names hardcoded/loaded
  in scripts/dannytrades_phase0.py (_load), full available history (~1962-2026), via a
  rebuilt yfinance OHLCV cache (auto-adjusted, as the original). /tmp/dtcache is gone
  — rebuild it with the same loader (network fetch; be patient/rate-limit tolerant; if
  a handful of tickers fail, proceed and stamp the count; if >20% fail, STOP and report).
- **Metric & events:** identical to DT-W1a and scripts/dannytrades_whale.py — whale_buy_fraction
  monthly (ME, win=6), whale_chg = 3-month diff, non-overlapping fwd_1m. Tests, family
  dt_replication_64y (m=4, BH q=0.10): H1 whale_chg>+10 fade (expected negative),
  H2 whale_chg<-10 bounce (expected positive), H3 level>75 fade (expected negative),
  H4 per-month cross-sectional whale-level decile Spearman (expected negative).
- **Inference:** TIME-CONTROLLED PRIMARY per DT-R14 — within-month cross-sectional demeaning
  of fwd_1m + month-block bootstrap (resample months) for CIs; real one-sided bootstrap
  tail-fraction p-values; controls: within-ticker time permutation for H1/H2,
  within-month cross-ticker permutation for H3/H4, positive +2pp injection on the H2
  mask. Also report the raw ticker-cluster basis as superseded context. Reuse the DT-W1a
  repaired machinery: scripts/research/dt_w1_whale_replication.py is on main — adapt its
  functions (loader swap: yfinance cache instead of massive store; no PIT membership —
  this is EXPLICITLY a survivor panel, stamp that prominently).
- **Verdict rule per test:** SURVIVES iff CI excludes zero at expected sign AND BH-survives.
  Pre-registered consequences (Fable-ratified at dispatch): (a) if H1-H3 all FAIL →
  DT-R13 restoration path CLOSED permanently (whale family closed); (b) if H4 FAILS →
  the chip's extension band loses its remaining evidential basis → pre-registered
  consequence: fade/bounce states removed, chip becomes a descriptive extension-percentile
  chip only (do NOT implement the chip change — report the verdict; Fable applies
  consequences); (c) if any read SURVIVES → it becomes eligible for a restoration prereg,
  display-only ceiling unchanged. Note: with ~770 months this is a powered test —
  UNDERPOWERED path applies only if usable months < 240 (stamp month count).
- **Survivorship framing (mandatory in report):** this panel deliberately retains the ORIGINAL
  survivor bias to isolate the TIME-CONTROL question — a survival here means 'not a
  calendar artifact on the long panel' but still survivor-flattered; both caveats print
  together.

---

## !! SURVIVORSHIP BIAS WARNING — READ BEFORE INTERPRETING !!

**This panel is DELIBERATELY survivor-biased.** The 114 tickers are large-cap US names
that SURVIVED from the 1960s to 2026. Any positive result (SURVIVES) means:
  1. Not a calendar-time artifact on the long panel (time-control question answered), AND
  2. STILL survivor-flattered — the panel excludes all companies that failed or were acquired.

**Both caveats must be cited together wherever this study is referenced.**
A SURVIVES verdict does NOT mean the signal is valid on an honest out-of-sample panel.
DT-W1a established that the signal FAILS on a survivorship-honest 2021+ panel.

---

## Coverage Stamps

| Item | Value |
|------|-------|
| Prereg universe (phase-0 tickers attempted) | 115 |
| Tickers successfully fetched | 112 (97.4%) |
| Fetch failures (listed below) | 3 |
| Tickers with usable monthly data | 112 |
| Total pool ticker-months | 54199 |
| Pool rows with both whale and fwd_1m | 53216 |
| Calendar months in panel | 775 (effective independent N) |
| Panel fwd_1m range across months | -25.1% to +25.7% |
| Gap-excluded months (calendar-continuity guard) | 0 |
| Approx history span | ~1962-2026 (65 years) |
| Store latest date | 2026-07-06 |
| Store earliest date | 1962-01-02 |
| Power status | POWERED (months >= 240) |

**Failed fetches:** RE, ABC, PXD

**Panel type:** SURVIVOR PANEL (deliberate) — retains original survivorship to isolate
time-control question. See survivorship warning above.

---

## Sign Convention

**lift = P(up|event) − P(up|all)  [on the time-controlled / month-demeaned basis]**  
NEGATIVE lift = event group underperforms the panel base rate after month demean.  
H1 and H3 expect NEGATIVE lift (extended/hot whale → mean-reversion).  
H2 expects POSITIVE lift (whales leaving → bounce).  
H4 expects NEGATIVE Spearman (higher whale decile → lower fwd_1m).

---

## H1–H4 Results — Time-Controlled (Primary Basis, DT-R14 compliant)

**Family:** dt_replication_64y | **m=4** | **BH q=0.1** | **Inference:** month-block bootstrap on cross-sectionally demeaned fwd_1m

| Test | Event | N events | N months | Lift (time-ctrl) | 95% CI | Exact p | BH survived | CI excl zero | Verdict |
|------|-------|----------|----------|-----------------|--------|---------|-------------|--------------|---------|
| H1 | whale_chg > +10 | 10914 | 774 | -0.0141 | [-0.0252, -0.0031] | 0.004 | Yes | Yes | **SURVIVES** |
| H2 | whale_chg < -10 | 10922 | 774 | +0.0053 | [-0.0046, +0.0157] | 0.149 | No | No | **FAILED** |
| H3 | whale > 75 | 2715 | 774 | -0.0135 | [-0.0394, +0.0124] | 0.169 | No | No | **FAILED** |
| H4 | whale decile monotonicity | 53552 obs | 770 | Spearman=0.0083 | [-0.0266, +0.0401] | 0.665 | No | No | **FAILED** |

**H4 side-by-side (per-month primary vs pooled comparisons):**

| Method | Spearman | CI 95% |
|--------|----------|--------|
| Per-month mean (PRIMARY) | 0.0083 | [-0.0266, +0.0401] |
| Pooled equal-count | -0.9636 | (not bootstrapped) |
| Pooled equal-width | -0.9758 | (not bootstrapped) |

---

## H1–H4 Results — Raw Basis (Ticker-Cluster Only, Superseded Context)

Shown for comparison with the original 64y result (t≈−3.9, no time control).
**Do not use for verdict purposes.** Calendar-time confound not removed.

| Test | N events | Lift (raw) | 95% CI (raw) |
|------|----------|-----------|--------------|
| H1 | 10914 | -0.0226 | [-0.0323, -0.0139] |
| H2 | 10922 | +0.0198 | [+0.0119, +0.0278] |
| H3 | 2715 | -0.0295 | [-0.0494, -0.0107] |

---

## Calibration Controls (4 Total, per DT-R14)

### C1: Within-Ticker Time Permutation (H1/H2, raw basis)

Shuffles temporal order of whale within each ticker. Appropriate for change tests.

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H1 (permuted) | 14839 | -0.0014 | [-0.0080, +0.0047] | PASS |
| H2 (permuted) | 14976 | -0.0020 | [-0.0085, +0.0047] | PASS |

### C2: Within-Month Cross-Ticker Whale Permutation (H3/H4, level tests)

Breaks ticker-selection channel (correct null for level tests).

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H3 (cross-ticker permuted) | 2715 | -0.0151 | [-0.0364, +0.0060] | PASS |

### C3: Within-Ticker Time Permutation on Demeaned Series (H1/H2, TC basis)

Validates time-controlled bootstrap machinery. Should produce lifts near zero.

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H1 (demeaned, permuted) | 15067 | -0.0016 | [-0.0076, +0.0049] | PASS |
| H2 (demeaned, permuted) | 15013 | -0.0029 | [-0.0095, +0.0036] | PASS |

### C4: Positive Injection (H2, +2pp injected into fwd_1m on H2-mask rows)

H2 must detect the injected signal (CI excludes zero above).

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H2 (+2pp injected) | 10922 | +0.0984 | [+0.0882, +0.1094] | PASS |

---

## Pre-Registered Consequence Branch

**Branch fired:** C: SURVIVES — H1 survive time control on 64y survivor panel

**Rationale:** H1 survive month-block time control on 64y panel. Each surviving read is eligible for a restoration prereg (display-only ceiling unchanged). DT-R13: restoration path open for surviving reads only. Caveat: survivor-flattered panel — must be replicated on honest panel before any chip change.

**Required action:** Report to Fable for adjudication; do NOT touch engine/dannytrades_chip.py.

---

## DT-W2 vs DT-W1a Comparison

| Test | DT-W1a (2021+ honest panel) | DT-W2 (64y survivor panel) |
|------|---------------------------|--------------------------|
| H1 | FAILED (lift -0.0062) | SURVIVES (lift -0.0141) |
| H2 | FAILED | FAILED (lift +0.0053) |
| H3 | FAILED | FAILED (lift -0.0135) |
| H4 | FAILED (sp +0.0548) | FAILED (sp 0.0083) |

DT-W1a survivorship-honest result (FAILED all 4) is the operative verdict for
display purposes. DT-W2 settles whether the 64y result was a calendar artifact.

---

## Implementation Notes

- **DT-W2:** 64-year panel month-block re-run. Settles DT-R13.
- **Universe:** PHASE0_UNIVERSE (114 tickers, same as scripts/dannytrades_phase0.py).
  yfinance OHLCV cache rebuilt from network (auto-adjusted prices).
- **No PIT filter:** explicit survivor panel to isolate time-control question.
- **Time control:** cross-sectional monthly demeaning + month-block bootstrap (primary).
- **BH p-values:** exact one-sided bootstrap tail fractions.
- **H4:** per-month cross-sectional decile Spearman (mean across months) with
  month-block bootstrap CI. Consistent with DT-W1a.
- **Controls:** C1 within-ticker permutation (H1/H2), C2 within-month cross-ticker
  permutation (H3/H4), C3 within-ticker permutation on demeaned (H1/H2 TC), C4 injection.
- **Calendar-continuity guard:** months with gap > 14 calendar days excluded.
- **Thresholds:** frozen at prereg values (entering=10, leaving=-10, hot=75, win=6,
  diff=3, BH q=0.10, n_boot=1000, seed=11). Nothing tuned.
- **Survivorship bias:** deliberate survivor panel. Both caveats (survivor-flattered +
  no time-control in original t≈−3.9) must be cited with this study.
