# W5-A — Within-sector 3M reversal RE-DERIVE on the raw plane (Phase-0)

*China Alpha Program · Wave W5 (the reversal sleeve, ruling F5) · the program's one-validated-edge
STRESS TEST (open item O4).*
*Harness: `scripts/china_reversal_rederive_phase0.py`. Report: `reports/china-reversal-rederive.md`.
Unit tests: `tests/test_china_reversal_rederive_phase0.py`. Registry:
`data/experiments/registry_seed.json` (id `w5a-reversal-rederive`). NOTHING wired to any page /
board / rank / ledger regardless of outcome — and the existing shadow sleeve
(`engine/cn_reversal_sleeve.py`, `scripts/build_cn_reversal_sleeve.py`) and its forward ledger are
NOT touched. Pure research + measurement.*

---

## 1. Why this exists (open item O4)

The program rests on ONE validated name-selection edge (phase0-verdicts.md #1): **quarterly
within-sector reversal, deepest quintile, NO gates** — published as ann Sharpe **0.58**, +0.56%/mo
excess over the EW universe, hit 56%, maxDD −37.6%, n=388 monthly rebalances, 1990→2026
(`research/CHINA_HK_STOCK_SIGNALS.md` L98-123). That number is an **UNREPRODUCIBLE UPPER BOUND**
(phase0-verdicts.md B(1)):

1. the deep panel `data/china_search/closes_deep.parquet` is **absent** from the repo;
2. `china_search` **retroactively deletes** the price history of names that drop out of the current
   Sina top-N — i.e. it deletes exactly the deep-decliner failures the reversal signal BUYS, so the
   surviving numbers are survivorship-inflated;
3. both `china_search` stores are `auto_adjust=True` **total-return** closes — adjustment seams
   seasonally bias `rev_z` (17/300 names show a >0.4% seam step in 250d, May-dividend clustered).

The sleeve page's backcast is therefore HONESTLY labeled "reconstruction, upper bound". **W5-A
re-derives the number on `data/china_stocks_raw`** (append-only, RAW/UNADJUSTED prices, real OHLCV
back to the 1990s) so the sleeve page can carry an honest headline instead of a number it cannot
reproduce.

## 2. The signal (exact mirror of the engine, with documented deviations)

Signal = **within-sector 3-month (63-session) reversal fuel**, identical math to
`engine/china_reversal.reversal_watch` and `engine/cn_reversal_sleeve._rev_z_at`:

```
ret63 = trailing 63-CN-session simple return (per name)
rev   = -(ret63 - sector_mean(ret63))            # how far BELOW its sector a name sits over 3M
rev_z = (rev / sector_std(rev)).clip(-3, +3)     # sector-standardized reversal fuel
```

The shared function `rev_z_row()` is asserted **byte-for-byte against the engine's own formula** in
the unit tests (`TestRevZRow.test_matches_engine_formula_exactly`) — parity is the whole point, or
the re-derive would be measuring a different signal.

**Documented deviations (unavoidable on the raw plane; each conservative or neutral):**
- **D1 — split-safe `ret63`.** The raw plane is UNADJUSTED, so a naive `close[-1]/close[-64]` ratio
  across an ex-div/split day is a corporate-action artifact, not a return. `ret63` is compounded
  from `clean_daily_ret` (|daily ret|>25% zeroed). This is the split-hygiene the measurement
  constitution mandates; it removes ~0.01% of daily obs, it does not touch the signal's economic
  content. The engine runs on ADJUSTED closes where this does not arise.
- **D2 — sector labels** come from `data/china_search/members.parquet` (the same source the engine
  uses); raw names with no sector map are dropped (mirrors the engine's `sector != "—"` screen).
- **D3 —** thin-sector screen `MIN_SECTOR=6` and `rev_z` clip ±3 are copied VERBATIM from the engine.

## 3. Substrate and measurement constitution (binding — masterplan §4)

- **Substrate:** `data/china_stocks_raw/` — 1568 raw files, RAW/UNADJUSTED, OHLCV incl. `open`, back
  to **1990-12-19**, fresh to 2026-07-03. After hygiene: **1278 names**. NEVER the trimmed
  close-only `china_search` panel (used ONLY for the direct-comparison contrast).
- **Two benchmarks, both reported:**
  - **UNIVERSE-EW-relative** — the leg's EW forward return minus the equal-weight universe's. This
    is the cross-sectional SKILL the published edge is (excess over the EW universe), and it needs no
    external series, so it uses the FULL raw-plane depth (349 rebalances). **This is the PRIMARY
    metric the CONFIRM threshold keys on.**
  - **CSI300-relative** — `510300.SS`; its history begins 2012-05-04, which bounds this benchmark to
    169 rebalances. The SHORTER-window reference, not the primary.
- **Fill realism:** entry at **T+1 (H+L)/2**, **locked-limit rows excluded** (`high==low==close` on
  the raw plane => unfillable). Close-to-close reported ALONGSIDE (the T+1 grading tax).
- **Split hygiene:** raw plane is unadjusted; |daily ret|>25% moves are zeroed before compounding
  (0.0105% of daily obs — corporate-action artifacts, verified present => the plane IS raw).
- **Splits:** time-HALF (early/late) + pre/post-2024.
- **Placebo:** 2000-permutation label-shuffle (seed=5) on the primary long-leg spread.
- **Known-result control:** 12-1 (skip-month) cross-sectional MOMENTUM long quintile through the
  SAME harness — must come out ~0/negative (reproduces the killed momentum result #5/#6).

## 4. Universe filters (pre-registered — mirror the sleeve builder; responsibility, NOT alpha)

- ST fail-closed (`engine.china_reversal.is_st`); sentinel-aware mktcap floor (30.0亿 EXACTLY = the
  CN-2 "unknown" placeholder => kept); ADV floor (trailing-60d median close×volume ≥ 1e8 yuan);
  ≥400 trading days of history; exclude names with >20% locked-limit days.
- **Names are kept AS-OF each formation date** — a name that delists AFTER formation stays in the
  book at its realized returns. This is the whole point of a survivorship-clean re-derive; no
  as-of trim is applied at read time (the STORE's append-only property is what makes it clean, to
  the degree it is — see §6).
- Excluded this run: `{history:44, locked:5, adv:142, no_sector:98, st:1, mcap:0}`.

## 5. Pre-registered verdict thresholds (fixed BEFORE running)

Keyed on the **deepest-quintile long-leg UNIVERSE-relative spread** (the sleeve product):

- **CONFIRM:** spread POSITIVE with NW-HAC t ≥ 2 on the FULL sample **AND** same SIGN in both
  time-halves.
- **WEAKEN:** positive but (t < 2) **OR** (one half flat / sign-broken).
- **REFUTE:** ≤ 0 on the full sample.

Because the raw plane is a pure-survivor plane on the delisting axis (§6), the verdict is reported
**-ON-AVAILABLE-PLANE**: the failure tail the signal buys is under-represented on BOTH planes, so
even this number is an upper bound — tighter than china_search's, but not survivorship-free.

## 6. SUBSTRATE HONESTY — how survivorship-clean is the raw plane, really?

**The decisive finding: the raw plane is ESSENTIALLY A PURE-SURVIVOR plane on the delisting axis.**

- Of **1469** raw names with data, **0 (0.0%)** end more than 20 sessions before the panel max
  (2026-07-03). There are **zero captured delistings/suspensions** — every name is alive today.
- The trimmed `china_search` plane is identical on this axis (0 names ending early) and worse on
  depth (starts 2021-06-15).
- **Raw-price-plane check:** 0.0105% of daily obs are |ret|>25% (unadjusted corporate-action jumps
  are PRESENT) — confirming the raw store holds genuine RAW prices. So the raw plane's real
  advantages over china_search are **(a) no total-return / adjusted-close seam** (china_search's known
  `rev_z` defect) and **(b) history to 1990-12-19** (vs 2021-06-15) — **NOT** delisting capture,
  which neither plane has.

**Consequence for the verdict.** The reversal signal deliberately BUYS the deepest within-sector
decliners — precisely the population most likely to contain the eventual delistings that neither
plane retains. So the re-derived number is still an **upper bound**, materially tighter than the
0.58 headline (raw prices remove the adjustment seam; deep history spans real bears) but not
survivorship-free. The honest label is **CONFIRM-ON-AVAILABLE-PLANE**. A truly clean number needs a
point-in-time membership store that retains delisted names' terminal returns — an F9/W1 substrate
repair, not a W5 deliverable.

## 7. RESULTS

### PRIMARY — deepest-quintile long leg, UNIVERSE-EW-relative, fill-realistic T+1

| era | n | mean%/reb | t_HAC | ann Sharpe | maxDD% | hit |
|---|---|---|---|---|---|---|
| **full** | **349** | **+0.426** | **3.29** | **0.57** | −62.8 | 0.539 |
| early | 138 | +0.597 | 2.97 | 0.73 | −62.8 | 0.507 |
| late | 211 | +0.314 | 1.92 | 0.46 | −37.7 | 0.559 |
| pre-2024 | 320 | +0.534 | 4.17 | 0.73 | −62.8 | 0.550 |
| 2024+ | 29 | **−0.772** | −1.60 | −0.97 | −21.4 | 0.414 |

- **CSI300-relative reference (2012-05+, 169 reb):** +1.052%/reb, t_HAC 2.49, Sharpe 0.67, maxDD −37.7%.
- **Reference L/S (deepest-minus-shallowest quintile, universe-relative, full):** +0.686%/reb,
  t_HAC 2.52, Sharpe 0.44.

### Mandatory checks

- **Fill tax:** close-to-close +0.510%/reb vs fill-realistic +0.426%/reb → tax ≈ 0.084pp/reb
  (mild at the long-leg-spread level; the sleeve's own note cites ~1pp/entry at the name level).
- **Per-name drawdown (re-derive of the published −37.6%):** the −37.6% **reproduces** as the
  CSI300-relative spread-NAV maxDD (**−37.7%**). The universe-relative full-DEPTH NAV is deeper
  (**−62.8%**) because it spans the 1990s A-share bears china_search never reaches. Per-name left
  tail (43,644 name-legs): worst −62.1%, p1 −26.6%, p5 −17.3%, p50 +0.5%, p95 +25.6% — the sleeve
  buys weakness, so the per-name left tail is deep BY CONSTRUCTION (the "size small" framing is
  load-bearing).
- **Known-result control (momentum 12-1 long quintile, same harness):** full **−0.031%/reb,
  t_HAC −0.17** (early −0.116/t −0.44; late +0.026/t +0.11) → **DEAD/flat, reproducing #5/#6**. The
  harness is sane: it does not manufacture an edge from a dead signal.
- **2000-perm placebo:** real t_HAC **3.29** vs a clean null (mean −0.004, sd 1.017) → **perm_p
  0.0005**. The edge sits deep in the tail; it is not a random relabelling.

### Discrimination (does the verification have power? §7.1)

The SAME harness gives reversal t=3.29 and momentum t=−0.17. Opposite results from one instrument
prove it has power — the reversal signal is not a rubber-stamp of any long leg. The placebo
(perm_p 0.0005) and the momentum control (flat) are the two independent discriminations the
measurement constitution requires.

### DIRECT COMPARISON — the survivorship/adjustment gap as a NUMBER

| plane (same ~24-month window) | metric | value |
|---|---|---|
| trimmed `china_search` (shadow-sleeve `backcast()`) | CSI300-excess/mo | **+0.97%** (Sharpe 0.89, maxDD −11.5%, 24 legs) |
| raw plane re-derive (CSI300-relative, matched) | excess/reb | **−0.067%** (Sharpe −0.05, maxDD −17.7%, 26 reb) |
| **GAP (trimmed − raw, matched window)** | | **≈ 1.04 pp/mo** |

The trimmed plane over the SAME recent window shows +0.97%/mo; the raw plane shows ~flat. The
~1pp/mo gap is the combined survivorship-trim + total-return-adjustment inflation the china_search
backcast carries — and it happens to fall in the 2024+ window where reversal is weak on BOTH planes,
so the matched-window contrast is the harshest honest read. **Over the full raw-plane depth**, by
contrast, the edge is real and strongly significant (+0.426%/reb, t 3.29) — the recent 24mo is a
weak regime, not the whole story.

## 8. VERDICT and interpretation

**CONFIRM-ON-AVAILABLE-PLANE.** The one validated edge SURVIVES the survivorship-cleaner raw-plane
stress test: deepest-quintile long-leg universe-relative spread **+0.426%/reb, t_HAC 3.29, ann
Sharpe 0.57, n=349**, both time-halves positive, placebo perm_p 0.0005, momentum control correctly
dead. The published −37.6% maxDD reproduces (−37.7% CSI300-relative).

**The honest headline the sleeve page should carry** (replacing the unreproducible 0.58): **ann
Sharpe ≈ 0.57, +0.43%/reb (universe-relative, fill-realistic), maxDD ≈ −37.7% (CSI300-relative) /
−62.8% (full-depth) — an upper bound on the AVAILABLE plane** (both substrates are pure-survivor on
the delisting axis; the true out-of-sample number is at or below this).

**Two honest caveats that do NOT change the verdict but bound the claim:**
1. **Recent-era weakness.** pre-2024 is strong (+0.534%/reb, t 4.17) but the 29-rebalance 2024+ tail
   is negative (−0.772%/reb, t −1.60). CONFIRM keys on the two time-HALVES (both positive) per the
   pre-registration; the recent flat window is small (n=29) and flagged, not buried. The forward
   ledger (the sleeve's real record) is what adjudicates whether 2024+ is noise or a regime change.
2. **Gross of cost.** The universe-relative spread is cross-sectional SKILL, gross; the reversal
   family is high-turnover. A net-of-cost pass is required before any sizing claim — the sleeve page
   already frames this ("size small, high variance").

**Next step (no wiring this wave).** Hand the honest headline to the sleeve page copy so it carries a
reproducible number. The residual survivorship bias is an F9/W1 substrate repair (a PIT membership
store retaining delisted names' terminal returns), not a W5 task; until it lands, every reversal
number in the program stays labeled an upper bound.
