# W5-A — Within-sector 3M reversal RE-DERIVE on the raw plane — Phase-0 Report

The program's ONE validated name-selection edge (phase0-verdicts.md #1) re-derived on the survivorship-clean(er) RAW substrate `data/china_stocks_raw` (append-only, RAW/UNADJUSTED prices, real OHLCV to the 1990s) — because the published ann-Sharpe-0.58 headline is an UNREPRODUCIBLE UPPER BOUND (closes_deep.parquet absent; china_search retroactively deletes dropped names; total-return closes). **NOTHING wired; the shadow sleeve build + ledger untouched.**

**MACHINE VERDICT: CONFIRM-ON-AVAILABLE-PLANE** — long-leg spread +0.426%/reb, t_HAC=3.29>=2 full AND same sign both halves (early +0.597/late +0.314)

## Substrate honesty (mandatory — it qualifies the verdict)
- Raw store holds **1469 names**; **0 (0.0%)** end >20 sessions before the panel max 2026-07-03 — i.e. the raw plane is ESSENTIALLY A PURE-SURVIVOR plane on the delisting axis.
- Trimmed `china_search`: 1514 names, starts 2021-06-15, 0 ending >20 sessions early (its trim deletes droppers — CN-2).
- **Raw-price-plane check:** 0.0105% of daily obs are |ret|>25% (unadjusted corporate-action jumps are PRESENT) — confirming the raw store is genuine RAW prices, so there is **no total-return / adjusted-close seam** to bias rev_z (the china_search plane's known defect). The raw plane's real advantages are therefore (a) RAW prices and (b) history back to 1990-12-19 vs china_search's 2021-06-15 — **NOT** delisting capture, which neither plane has.
- Because the delisting-failure tail the reversal signal BUYS is under-represented on BOTH planes, this number is still an **upper bound** — tighter than the china_search one, but not survivorship-free. Hence the verdict is reported **-ON-AVAILABLE-PLANE**.

## Headline (the honest number to carry)
- **Deepest-quintile LONG leg, universe-EW-relative, fill-realistic T+1: 0.426%/reb, t_HAC 3.29, ann Sharpe 0.57, hit 0.539, n=349 monthly rebalances** (full raw-plane depth). Halves: early 0.597%/t 2.97, late 0.314%/t 1.92.
- CSI300-relative reference (2012-05+ only): 1.052%/reb, t_HAC 2.49, Sharpe 0.67, n=169.
- Reference deepest-minus-shallowest L/S (universe-relative, full): 0.686%/reb, t_HAC 2.52, Sharpe 0.44.
- **Recent-era caveat (honest):** the pre/post-2024 split is NOT symmetric — pre-2024 is strong (0.534%/reb, t 4.17) but the 29-rebalance 2024+ tail is NEGATIVE (-0.772%/reb, t -1.6). CONFIRM keys on the two time-HALVES (both positive) per the pre-registration; the recent flat/negative window is small (n=29) but flagged, not buried.

## Mandatory checks
- **Fill tax:** close-to-close 0.51%/reb vs fill-realistic 0.426%/reb (T+1 (H+L)/2 entry, locked-limit excluded).
- **Per-name drawdown (re-derive of the published -37.6%):** the -37.6% reproduces as the CSI300-relative spread-NAV maxDD (-37.7%); the universe-relative full-DEPTH NAV is deeper (-62.8%) because it spans the 1990s A-share bears china_search never reaches. Per-name left tail: worst name-leg fwd return -62.1%, p1 -26.6%, p5 -17.3% — the sleeve buys weakness, so the per-name left tail is deep by construction.
- **Known-result control (momentum 12-1 long quintile):** full -0.031%/reb, t_HAC -0.17 => DEAD/flat, reproducing #5/#6 (harness sane).
- **2000-perm placebo:** real t_HAC 3.29, null mean -0.004 sd 1.017, perm_p 0.0005.

## Direct comparison vs the shadow-sleeve backcast (survivorship gap as a number)
- Trimmed-plane sleeve backcast (upper bound): excess 0.97%/mo, Sharpe 0.89, maxDD -11.5%, n_legs 24.

```
W5-A within-sector 3M reversal RE-DERIVE · substrate china_stocks_raw (RAW/unadjusted)
universe 1278 names after hygiene (excluded {'history': 44, 'locked': 5, 'adv': 142, 'no_sector': 98, 'st': 1, 'mcap': 0}) · raw history 1990-12-19->2026-07-03

== SUBSTRATE HONESTY (how survivorship-clean is the raw plane, really?) ==
raw store: 1469 names; 0 (0.0%) end >20 sessions before panel max 2026-07-03 => CAPTURED delistings/suspensions
trimmed china_search: 1514 names, starts 2021-06-15, 0 end >20 sessions early
raw-price-plane check: 0.0105% of daily obs are |ret|>25% (unadjusted corporate-action jumps present => RAW prices, no total-return/adjustment seam)
=> raw plane is ESSENTIALLY PURE-SURVIVOR on the delisting axis; advantage over china_search = RAW prices + 1990-12-19 depth, NOT delisting capture.

== PRIMARY · deepest-quintile within-sector reversal LONG leg — UNIVERSE-EW-relative ==
   (cross-sectional SKILL: leg EW fwd return minus the equal-weight universe; fill-realistic T+1)
era           n    mean%   t_HAC  Sharpe   maxDD%    hit
full        349    0.426    3.29    0.57    -62.8  0.539
early       138    0.597    2.97    0.73    -62.8  0.507
late        211    0.314    1.92    0.46    -37.7  0.559
pre-2024    320    0.534    4.17    0.73    -62.8   0.55
2024+        29   -0.772    -1.6   -0.97    -21.4  0.414

== CSI300-relative reference (shorter window — bench availability bounds it to 2012-05+) ==
era           n    mean%   t_HAC  Sharpe   maxDD%    hit
full        169    1.052    2.49    0.67    -37.7  0.556
early         0   (thin)
late        169    1.052    2.49    0.67    -37.7  0.556
pre-2024    140    1.233    2.61    0.75    -37.7  0.557
2024+        29    0.176    0.21    0.15    -21.4  0.552

== reference L/S (deepest-minus-shallowest quintile, universe-relative, full) ==
mean 0.686%/reb  t_HAC 2.52  Sharpe 0.44  hit 0.55  n 349

== fill-realistic vs close-to-close (long-leg universe-relative, full) ==
fill-realistic mean 0.426%/reb (t 3.29); close-to-close mean 0.51%/reb (t 3.64); grading tax = 0.084pp/reb

== per-name forward-return distribution of the long-leg holdings (fill-realistic, full) ==
  n name-legs 43644  mean 1.9%  worst -62.1%  best 441.5%
  pct  p1 -26.6  p5 -17.3  p25 -6.3  p50 0.5  p75 8.3  p95 25.6  p99 46.5
  drawdown re-derive of the published -37.6%: CSI300-relative spread NAV maxDD -37.7% (matches -37.6%); universe-relative full-DEPTH spread NAV maxDD -62.8% (deeper — spans 1990s bears); absolute-leg NAV maxDD -62.8%

== KNOWN-RESULT CONTROL · 12-1 momentum long quintile (must reproduce ~0/negative) ==
  full   mean -0.031%/reb  t_HAC -0.17  Sharpe -0.03  n 343
  early  mean -0.116%/reb  t_HAC -0.44  Sharpe -0.11  n 137
  late   mean 0.026%/reb  t_HAC 0.11  Sharpe 0.03  n 206
  => momentum DEAD/flat (control reproduces #5/#6)

== 2000-permutation placebo (seed=5) on the primary long-leg universe-relative spread ==
real t_HAC 3.29  |  null mean -0.004 sd 1.017  perm_p 0.0005

== DIRECT COMPARISON · shadow-sleeve backcast on the TRIMMED china_search plane (same product) ==
  trimmed-plane sleeve backcast (upper bound): excess 0.97%/mo, Sharpe 0.89, maxDD -11.5%, hit 62.5%, n_legs 24 (csi300_excess)
  raw-plane re-derive (CSI300-relative, matched ~24mo): excess -0.067%/reb, Sharpe -0.05, maxDD -17.7%, hit 0.5, n 26
  => SURVIVORSHIP/ADJUSTMENT GAP (trimmed minus raw, matched window) = 1.037pp/mo

== PRE-REGISTERED MACHINE VERDICT (qualified ON-AVAILABLE-PLANE — see substrate honesty) ==
VERDICT: CONFIRM-ON-AVAILABLE-PLANE  (long-leg spread +0.426%/reb, t_HAC=3.29>=2 full AND same sign both halves (early +0.597/late +0.314))
control check: momentum reproduced ~0/negative (harness sane); placebo perm_p=0.0005
```

## Honest caveats
- The universe-relative spread is cross-sectional SKILL (excess over the EW universe), GROSS of cost; the reversal family is high-turnover so a net-of-cost pass is required before any sizing claim (the sleeve page already frames this).
- Raw plane is UNADJUSTED: |ret|>25% corporate-action jumps are zeroed in the return metric (not the signal) per the measurement constitution.
- Verdict is **-ON-AVAILABLE-PLANE**: both substrates are pure-survivor on the delisting axis, so the deepest-decliner failure tail is under-represented; the true out-of-sample number is at or below this one.
