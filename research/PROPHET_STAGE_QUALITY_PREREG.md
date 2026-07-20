# Prophet × Stage quality re-grade — pre-registration (PSQ)

Registered 2026-07-20 (main-loop Fable). Successor test to PSF
(`research/PROPHET_STAGE_FUSION_PREREG.md`, results
`research/reports/PROPHET_STAGE_FUSION_RESULTS.md`). Executes the leg PSF left open —
DO_NOT_REBUILD §2 PSF row, **LEFT OPEN (ii): "Stage-2 as a return-quality / hold tilt
rather than a win-rate gate."** This registration closes that clause one way or the other.

## 0. Honest framing — same-sample confirmatory re-analysis (read first)

PSF's win-rate falsifiers FAILED (nulls filed, construction-scoped kill on the win-rate
authority). The SAME run showed a return-distribution right-shift: median `fwd_ret_126`
1.8% (Arm A) → 4.7% (Arm C), shallower `fwd_mdd_126`, modestly lower STOPPED. **That
observation is the hypothesis here — it was generated on the same fires this test will
re-grade.** This is therefore NOT an independent-sample test. What makes it a legitimate
gauntlet leg and not goalpost-moving:

1. The estimator, thresholds, economic floor, and promotion consequence are committed in
   this document BEFORE the re-run, and the primary statistic (a bootstrap **difference
   CI**, not a point estimate) can absolutely still fail — a right-shifted point estimate
   with a CI straddling zero is a FAIL and gets filed as one.
2. The promotion earned by a PASS is explicitly **provisional** (§6): the binding
   out-of-sample confirmation is the live-Prophet forward shadow
   (`engine/prophet_stage_shadow.py`, #3157), which accrues on real picks with no
   hindsight and carries an **auto-demote clause** here.
3. Residual same-sample optimism is disclosed on every surfaced result: the point
   estimates below were known before registration; only the CI machinery and pass lines
   were not.

Proxy disclosure from PSF §0 applies verbatim: this grades a *mechanism proxy* of the
Prophet entry (T1/T2 fresh fires), not replayed Prophet picks.

## 1. Hypotheses (committed before the re-run)

- **PSQ-H1 (PRIMARY — quality tilt).** Among matured T1/T2 fresh fires, the Stage-2∩EC
  arm (PSF Arm C) has a **higher median `fwd_ret_126`** than the unfiltered arm (Arm A),
  by a margin that is CI-clean under the month-block bootstrap AND economically material
  (≥ +1.5pp). This is the only promotion-bearing falsifier.
- **PSQ-H2 (secondary — excursion asymmetry).** Per-fire excursion asymmetry
  `EA = fwd_mfe_126 + fwd_mdd_126` (MFE is ≥ 0, MDD is ≤ 0, so EA = favorable excursion
  net of adverse excursion) has a higher median in Arm C than Arm A, CI-clean.
- **PSQ-H3 (secondary — loss shape).** Arm C has a **lower STOPPED rate** (clean15_126
  parameterization) than Arm A, CI-clean.

H2/H3 are supporting evidence only; they carry no promotion power alone and their failure
does not veto a PSQ-H1 PASS (it gets printed in the verdict and weighed in adjudication).

## 2. Arms, universe, entry events — incorporated by reference, FROZEN

Identical to PSF §2 in every respect: Arm A (all T1/T2 fresh fires), Arm B (∩ Stage-2),
B-fresh (∩ weeks_in_stage ≤ 10), Arm C (∩ `earnings_call_sent ≥ 24`). Universe, PIT
membership, EC join (`call_date < entry_date`, most-recent row), and the 2022-01-01…
2026-07-17 window are unchanged. **No arm, filter, or threshold may differ from the PSF
run.** The primary comparison is **C vs A** (the full confluence filter vs control — the
operating rule a promotion would actually create). B−A and C−B are printed as
decomposition diagnostics with CIs but carry **no verdicts**.

## 3. Ruler — incorporated by reference, FROZEN

PSF §3 verbatim (`engine/grading.py`: next-bar fill, forward-only windows,
delisting-imputed, PIT membership). All PSQ continuous statistics are computed on
**matured fires only** (full 126-bar strictly-forward window available). `fwd_ret_126`,
`fwd_mfe_126`, `fwd_mdd_126` are parameterization-independent; STOPPED is evaluated under
**clean15_126** (the positional ruler — the hold thesis this tilt would serve).
clean8_21 is out of scope (PSF already filed its nulls; a 21-bar rotational hold has no
use for a hold-length tilt).

## 4. Estimator (the new machinery — committed)

**Month-block paired bootstrap of a continuous statistic difference.** Extends the PSF
§4 win-rate difference bootstrap (`block_bootstrap_diff_ci`) to arbitrary per-fire
statistics, preserving its independence logic (effective n = entry months, not
overlapping fires):

1. Group matured fires by **entry month** (identical month key to PSF `_month_outcomes`).
2. One resample per replicate: draw months with replacement from the union of months in
   which either arm has ≥ 1 matured fire. The same drawn month set feeds BOTH arms
   (paired-by-block, preserving cross-arm correlation exactly as in PSF).
3. Pool per-fire values across drawn months per arm; compute the arm statistic (median
   for H1/H2; STOPPED fraction for H3); take the difference (C − A).
4. `n_boot = 10,000`, fixed `seed = 20260720`, percentile CI (2.5%, 97.5%).
5. Degenerate guard: < 24 distinct months in the union → NO VERDICT (report only).

Printed for every comparison: full-sample point difference, per-arm point statistics,
bootstrap mean/SE, percentile CI, n_fires and n_months per arm. Robustness leg
(supporting only): the H1 statistic recomputed on the de-overlapped fire subset per the
PSF §FIX-4 dependence disclosure.

Reproducibility artifact: the run dumps the per-fire matured table (ticker, entry date,
arm memberships, `fwd_ret_126`, `fwd_mfe_126`, `fwd_mdd_126`, terminal state) to
`data/research/psf_fires.parquet` if ≤ 20 MB (else gitignored and documented). Existing
PSF win-rate code paths and their tests are untouched.

## 5. Falsifiers + kill rules (committed)

- **PSQ-H1 FAILS** iff, at ≥ 24 month blocks, the bootstrap-diff 2.5% bound of
  median-`fwd_ret_126`(C − A) is ≤ 0, **or** the full-sample point difference is
  < +1.5pp (economic floor: half the PSF-observed +2.9pp shift; the smallest tilt that
  moves a ≤ 1.25× sizing decision after costs). FAIL → no promotion; Stage/EC stay
  display-tier confluence context (a null never deletes the layer); LEFT-OPEN (ii)
  closes as **tested-null on the backtest proxy** with the forward shadow still accruing
  as the definitive test.
- **PSQ-H2 / PSQ-H3 FAIL** independently iff their CI crosses zero the wrong way
  (H2 lower bound ≤ 0; H3 upper bound ≥ 0). Printed; no promotion power; no kill power.
- **KILL** (append DO_NOT_REBUILD §2, construction-scoped: "Stage-2∩EC as a
  return-quality/hold tilt on the T1/T2 timing entry") iff the H1 full-sample point
  difference is ≤ 0, or is negative in ≥ 2 regimes at n_dates ≥ 50 (regime partition
  identical to PSF). A KILL here does NOT touch the forward shadow (different signal,
  keeps accruing) and does NOT delete Stage/EC display surfaces.
- Regime leg (supporting): H1 point difference printed per PSF regime; sign flips are
  quoted in the verdict but do not by themselves overturn a PASS.

Multiplicity: exactly ONE promotion-bearing test (H1, one comparison, one statistic).
H2/H3/decompositions/robustness are labeled supporting throughout.

## 6. Promotion consequence (committed — what a PASS buys, and its leash)

**On PASS:** Stage-2∩EC earns a **provisional quality/hold-tilt authority** on Prophet:

- Scope: a position-**size multiplier** (cap ≤ 1.25×) and/or a **hold-leash extension**
  on picks that are Stage-2∩EC-positive at entry. **Never an entry veto, never a rank
  suppression or negative gate on non-Stage picks** (PSF killed exactly that authority;
  30.8% of unfiltered fires still win — the filter's absence is not evidence against a
  pick).
- Implementation is chartered as a separate follow-up wave (design + wiring PR of its
  own); nothing in this lane touches Prophet live code.
- **Auto-demote clause:** the forward shadow (#3157) is the binding out-of-sample
  confirmation. At the shadow's own maturity gate (~2026-12 per its config), if the
  shadow's median-return tilt point estimate for Stage-2∩EC-tagged picks is ≤ 0, the
  provisional authority reverts to display-tier automatically — no new ruling required.
  If the shadow confirms (> 0), provisional drops and the tilt stands as gauntleted.

**On FAIL/KILL:** everything stays exactly as today (display-tier context), verdicts
filed, registry updated.

## 7. Look-ahead controls & amendment law

PSF §7 applies verbatim (all inputs truncated at entry bar; late-IPO exclusions counted;
"validated" reserved). No new data inputs are introduced by this test. This document is
frozen at registration; any change is a dated amendment row below, added before the
affected re-run.

| Amendment | Date | Change | Reason |
|---|---|---|---|
| — | — | — | — |
