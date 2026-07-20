# Prophet × Stage-Analysis fusion — backtest results (PSF)

Spec: `research/PROPHET_STAGE_FUSION_PREREG.md` · generated 2026-07-20T21:37:56.044582+00:00

## §0 PROXY DISCLOSURE (read first)

> PROXY (PSF §0): Prophet has NO backtestable history (5 live entries post-2026-07-10). This is a FUSION-MECHANISM test on the repo's backing-artifact-backed T1-T4 confluence cascade as a PIT-replayable Prophet-family timing entry — NOT a Prophet replay. A positive result is evidence the mechanism helps Prophet's own entries, to be confirmed forward on live Prophet from go-live (~Dec 2026). Results are display-tier until operator-ratified promotion.

## Universe

- Union universe (baskets/ohlcv ∪ data/stocks, minus SPY bench): **3043** names; with usable prices: **3043**.
- Late-IPO names EXCLUDED (< 45 completed weeks at entry) and COUNTED: **19** (§7). Such names still contribute their fires to Arm A but not to the stageable arms B/B-fresh/C.
- Benchmark: SPY · entry window: 2022-01-01 … 2026-07-17.
- Full universe (no sampling).
- Total fresh fires (T1/T2, all names): **56237**. EC gate (arm C): earnings_call_sent ≥ 24.

### §0 SURVIVORSHIP DISCLOSURE (read before any absolute win-rate)

- Universe is **survivor-LEAN, not full PIT**. Live globs: **2759** names; delisted dead-name tickers UNIONED IN and COUNTED (their mostly-losing fires now graded, not dropped): **+284** (FIX-2).
- Residual gap: **307** S&P-1500 PIT members that traded 2022-01-01–2026-07-17 have NO price source in either the live globs or the dead-name store and remain ABSENT (no series exists to grade); of 1889 PIT members that traded in-window.
- **Consequence:** survivor-LEAN, not full PIT: live globs UNION delisted dead-name tickers (+284 counted); 307 S&P-1500 PIT members that traded 2022-26 have NO price source anywhere and remain absent. Falsifier verdicts are DELTA-based (A→B→C); survivorship inflates all arms' ABSOLUTE win-rates ~symmetrically, so the null on the delta is robust to the residual lean, while absolute win-rates are upward-biased.

## §4 metrics — clean15_126 — positional/hold primary (+15% before −5%, 126 bars)

| Arm | n_entries | n_dates | win-rate | Wilson 95% CI | STOPPED | med fwd63 | med fwd126 | med mdd126 | med bars→liftoff |
|---|---|---|---|---|---|---|---|---|---|
| A | 49201 | 1010 | 30.8% | [30.4%, 31.2%] | 67.1% | 0.7% | 1.8% | -15.3% | 20.0 |
| B | 16173 | 947 | 31.2% | [30.5%, 31.9%] | 66.5% | 0.9% | 3.1% | -13.8% | 24.0 |
| B_fresh | 4823 | 795 | 31.3% | [30.0%, 32.6%] | 66.2% | 0.9% | 2.9% | -13.6% | 23.0 |
| C | 4855 | 789 | 32.5% | [31.2%, 33.9%] | 65.0% | 1.8% | 4.7% | -13.5% | 24.0 |

### §5 falsifier verdicts — clean15_126

- **PSF-H1 (stage quality lifts win-rate, B vs A): `FAIL`** — **PRIMARY: block-bootstrap difference CI (B−A) = [-1.6%, 2.4%] (n_months=49)** [point 0.4%]. Wilson-diff 95% CI [-0.4%, 1.2%] — *anti-conservative (overlapping obs); effective n ≈ N monthly blocks, not n_entries*. n_dates_B=947 (gate ≥25: True). B: 5040/16173 · A: 15140/49201.
- **PSF-H3 (longer holds + lower STOPPED, B vs A): `PASS`** — **UNCONDITIONAL** median bars→MFE-peak (ALL matured fires) B=71.0 vs A=64.0; STOPPED B=66.5% vs A=67.1%. (conditional-on-winning bars→liftoff, confounded, kept for continuity: B=24.0 vs A=20.0). Fails only if hold_B≤hold_A AND STOPPED_B≥STOPPED_A (hold_worse=False, stop_worse=False). **Caveat:** PASS rests on a conditional subset + an AND-both-legs asymmetric falsifier — a quality/right-shift tilt, NOT a clean 'longer holds' win.
- **PSF-H2 (EC adds on top of stage, C vs B): `FAIL`** — **PRIMARY: block-bootstrap difference CI (C−B) = [-0.6%, 3.4%] (n_months=49)** [point 1.4%]. Wilson-diff 95% CI [-0.1%, 2.9%] — *anti-conservative (overlapping obs)*. n_dates_C=789 (gate ≥25: True). C: 1580/4855 · B: 5040/16173.
- **KILL rule: `TRIGGERED`** — negative-lift regimes at n_dates≥50: ['2022_bear', '2025_26'].

## §4 metrics — clean8_21 — rotational (+8% before −5%, 21 bars)

| Arm | n_entries | n_dates | win-rate | Wilson 95% CI | STOPPED | med fwd63 | med fwd126 | med mdd126 | med bars→liftoff |
|---|---|---|---|---|---|---|---|---|---|
| A | 54919 | 1115 | 33.7% | [33.3%, 34.1%] | 47.2% | 1.0% | 1.8% | -15.3% | 8.0 |
| B | 18814 | 1056 | 31.7% | [31.1%, 32.4%] | 45.4% | 1.4% | 3.1% | -13.8% | 8.0 |
| B_fresh | 5346 | 891 | 32.1% | [30.9%, 33.4%] | 44.4% | 1.1% | 2.9% | -13.6% | 8.0 |
| C | 5697 | 890 | 33.2% | [32.0%, 34.5%] | 45.8% | 2.3% | 4.7% | -13.5% | 8.0 |

### §5 falsifier verdicts — clean8_21

- **PSF-H1 (stage quality lifts win-rate, B vs A): `FAIL`** — **PRIMARY: block-bootstrap difference CI (B−A) = [-4.1%, 0.3%] (n_months=54)** [point -2.0%]. Wilson-diff 95% CI [-2.7%, -1.2%] — *anti-conservative (overlapping obs); effective n ≈ N monthly blocks, not n_entries*. n_dates_B=1056 (gate ≥25: True). B: 5971/18814 · A: 18510/54919.
- **PSF-H3 (longer holds + lower STOPPED, B vs A): `PASS`** — **UNCONDITIONAL** median bars→MFE-peak (ALL matured fires) B=71.0 vs A=64.0; STOPPED B=45.4% vs A=47.2%. (conditional-on-winning bars→liftoff, confounded, kept for continuity: B=8.0 vs A=8.0). Fails only if hold_B≤hold_A AND STOPPED_B≥STOPPED_A (hold_worse=False, stop_worse=False). **Caveat:** PASS rests on a conditional subset + an AND-both-legs asymmetric falsifier — a quality/right-shift tilt, NOT a clean 'longer holds' win.
- **PSF-H2 (EC adds on top of stage, C vs B): `FAIL`** — **PRIMARY: block-bootstrap difference CI (C−B) = [-0.7%, 3.5%] (n_months=54)** [point 1.5%]. Wilson-diff 95% CI [0.1%, 2.9%] — *anti-conservative (overlapping obs)*. n_dates_C=890 (gate ≥25: True). C: 1893/5697 · B: 5971/18814.
- **KILL rule: `TRIGGERED`** — negative-lift regimes at n_dates≥50: ['2022_bear', '2023_24_bull', '2025_26'].

## §6 decision implied (positional clean15_126)

**KILL** — a negative Stage-2 lift persists at n_dates≥50 across ≥2 regimes. Per §5, append a row to DO_NOT_REBUILD §2 closing this specific fusion construction (Stage-2-gate on the T1/T2 timing entry). Stage/EC remain display-context; the search space is NOT closed (this closes only the tested gate).

## Regime robustness (clean15_126, win-rate per arm)

| Regime | A | B | B-fresh | C |
|---|---|---|---|---|
| 2022_bear | 24.8% (n_d=250) | 21.2% (n_d=210) | 23.9% (n_d=162) | 21.3% (n_d=148) |
| 2023_24_bull | 32.7% (n_d=502) | 32.9% (n_d=487) | 31.5% (n_d=421) | 35.6% (n_d=415) |
| 2025_26 | 33.0% (n_d=258) | 32.3% (n_d=250) | 34.6% (n_d=212) | 32.0% (n_d=226) |

Block-bootstrap (month-block) win-rate 95% CI, clean15_126:

| Arm | bootstrap mean | 95% CI | n_months |
|---|---|---|---|
| A | 30.7% | [26.9%, 34.8%] | 49 |
| B | 31.1% | [27.3%, 35.3%] | 49 |
| B_fresh | 31.3% | [27.5%, 35.4%] | 49 |
| C | 32.5% | [28.4%, 36.7%] | 49 |

## §FIX-4 dependence disclosure + de-overlapped robustness

- **Per-name fire multiplicity:** 56237 fires across 2926 names — mean **19.2** (median 20.0, max 34) fires/name. Each fire opens an OVERLAPPING 126-bar forward window, so same-name fires are strongly dependent — the Wilson CIs (on n_entries) ignore this; the month-block bootstrap and the de-overlap arm below address it.
- **De-overlap arm (clean15_126, one fire per name per non-overlapping 126-bar window): 25379 fires (from 56237).**
  - PSF-H1 (B−A): `FAIL` — bootstrap-diff CI [-1.2%, 3.0%] (n_months=49) [point 0.8%].
  - PSF-H2 (C−B): `FAIL` — bootstrap-diff CI [-1.4%, 3.6%] (n_months=49) [point 1.2%].
  - KILL: `TRIGGERED`. **The null holds on the de-overlapped set** — the FAIL verdicts are not an artifact of the ~20-fires/name overlapping-window dependence.

## Honest read (nulls printed)

On the positional (clean15_126) ruler, the unfiltered timing entry (Arm A) wins 30.8% of matured fires. Stage-2 (Arm B) wins 31.2%, B-fresh 31.3%, Stage-2∩EC (Arm C) 32.5%. PSF-H1 does NOT clear its falsifier: the Stage-2 win-rate lift over the unfiltered arm is 0.4% with a PRIMARY month-block bootstrap-difference 95% CI of [-1.6%, 2.4%] — the lower bound is not above zero (it straddles 0), so on this timing entry Stage-2 shows no CI-clean win-rate edge once the 49 monthly blocks (not the tens of thousands of overlapping fires) set the effective n. That is a NULL, reported as such: Stage-2 stays display-context (retained as a confluence input, not deleted). PSF-H2 does NOT clear: EC-on-top-of-stage lift is 1.4% (block-bootstrap-diff CI [-0.6%, 3.4%]) — no CI-clean incremental edge from the earnings-call filter once effective-n is honest. Null; EC stays display-context. The return distribution DOES right-shift with the filters (median fwd126 rises 1.8%→4.7% A→C) and STOPPED falls modestly — a quality tilt, not a win-rate gate. Bottom line: Stage-2/EC filtering does NOT add a CI-clean win-rate edge to a validated timing entry; it modestly right-shifts returns and (conditionally) holds longer.
