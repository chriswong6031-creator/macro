# P-B3 — persistence-robust certification (2026-08-15)

Status: **NULL=12, UNINFORMATIVE=8**

> P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR. The numbers below are P-B3 verdicts on a new estimand and a new null.

Authority: `none_research_display_only`. display / research tier — a persistence-robust certification of within-name transition timing (A, primary) and occupancy-to-outcome association under a no-merge spell-sequence null (B, corroborative); not a promotion, not a gate, not a ranker, not a sizing input, and no production consumer exists or is proposed.

Governing: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`; program home `research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md (the P-B3 row)`; `DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`; `DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`.

A is primary (within-name state-transition contrast). B is corroborative (no-merge spell-sequence shuffle; coarse-df PERM-INERT). Scope is the frozen 20 cells. Most-specific §10 row wins.

## 1. Pins, freeze, run

| object | sha256 prefix / stamp |
| --- | --- |
| W-P0 `washout_onset_w1.py` | 11ac61de71f0f595 |
| P-B `pb_case_decomposition.py` | f42b0566beb60bec |
| P-B2 prereg | 043a85d69f76ea86 |
| P-B3 prereg (this contract) | 75fb38e1e6b5aefe |
| freeze commit (un-amended text) | 6419ca5ed5744d562b7c22093b52065502f802f3 |
| run head | b473cad20da08a274a3c7914b2edec1827433783 |
| SEED / TZ | 20260815 / UTC |
| N_PERM / N_ASSIGN | 2000 / 2000 |

Build-time numbered amendments (not silent re-choices):
- **A9** — §10 table has no row for (A NULL, B NOT_EVALUABLE/INSUFFICIENT) or for A status UNINFORMATIVE (G6/concentration cap). Those cells take an existing headline: A NULL + B silent → NULL; A UNINFORMATIVE → UNINFORMATIVE. CERTIFIED_TIMING + B NULL with df on a short-spell footprint uses the same UNINFORMATIVE / A_B_CONTRADICT close as row 8 (contradiction is not rescued because the footprint is short).
- **A10** — B's N_PERM distribution is computed on FIT and HOLDOUT only. AUDIT prints observed excess and the inert/retention census; it does not draw the permutation. AUDIT never gates (prereg §3).
- **A11** — The non-gating S∈{250,500,1000} diagnostic calls P-B2 shift_footprints after setting pb2.FKEYS_ORDER from the loaded P-B FKEYS. P-B2 only fills that tuple inside its own main(); leaving it empty KeyErrors and voids the receipt. A shift exception is recorded and does not prevent the receipt write. §11.5's probe asserts 'A is still null' as n_onsets==0 after dropping session-regime matching (A's estimand), not as a 0.05pp unmatched y-excess. §11.1's probe plants a dwell-legal 6-bar flip, not a one-bar flicker the dwell rule would ignore. §11.2–§11.4 planted A z uses the nearest same-regime stay-FALSE control, not the first-in-name bar (that control is biased and left |z| alive after a 20–60 session shift). Planted A z uses a session-clustered SE (plants on the same first-board wave are not independent pairs). §11.4 'drop below 1.96' is the planted positive direction, not |z|. §11.3 uses the same planted-direction fallback (z < 1.96) and scores A on moved onsets of the transition estimand, not unmatched occupancy.

## 2. Transition / support census (Design A, honest-N first)

| cell | edge | FIT events | FIT matched | FIT names | FIT unmatched | HOLD matched | A status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DD20|main|H10 | onset | 16998 | 9424 | 1107 | 0.4456 | 2681 | NULL |
| DD20|main|H5 | onset | 17335 | 9650 | 1109 | 0.4433 | 2705 | NULL |
| DD20|chinext20|H10 | onset | 1422 | 593 | 196 | 0.583 | 735 | NOT_EVALUABLE |
| DD20|chinext20|H5 | onset | 1423 | 594 | 196 | 0.5826 | 740 | NOT_EVALUABLE |
| DD35|main|H10 | onset | 14388 | 9454 | 1146 | 0.3429 | 1569 | NULL |
| DD35|main|H5 | onset | 14675 | 9666 | 1147 | 0.3413 | 1595 | UNINFORMATIVE |
| DD35|chinext20|H10 | onset | 1535 | 821 | 242 | 0.4651 | 764 | UNINFORMATIVE |
| DD35|chinext20|H5 | onset | 1536 | 822 | 242 | 0.4648 | 768 | NULL |
| MA200|main|H10 | exit | 12284 | 6630 | 1117 | 0.4603 | 1038 | CERTIFIED_TIMING |
| MA200|main|H5 | exit | 12505 | 6781 | 1118 | 0.4577 | 1042 | CERTIFIED_TIMING |
| MA200|chinext20|H10 | exit | 1358 | 506 | 221 | 0.6274 | 355 | NOT_EVALUABLE |
| MA200|chinext20|H5 | exit | 1360 | 508 | 222 | 0.6265 | 356 | NOT_EVALUABLE |
| QB|main|H10 | onset | 29452 | 24395 | 1184 | 0.1717 | 4920 | CERTIFIED_TIMING |
| QB|main|H5 | onset | 29929 | 24874 | 1184 | 0.1689 | 4951 | CERTIFIED_TIMING |
| QB|chinext20|H10 | onset | 2808 | 2187 | 286 | 0.2212 | 1935 | UNINFORMATIVE |
| QB|chinext20|H5 | onset | 2809 | 2188 | 286 | 0.2211 | 1935 | CERTIFIED_TIMING |
| VZ|main|H10 | onset | 117426 | 30591 | 1186 | 0.7395 | 4488 | NOT_EVALUABLE |
| VZ|main|H5 | onset | 119324 | 31364 | 1186 | 0.7372 | 4542 | NOT_EVALUABLE |
| VZ|chinext20|H10 | onset | 10915 | 2497 | 282 | 0.7712 | 1878 | NOT_EVALUABLE |
| VZ|chinext20|H5 | onset | 10922 | 2498 | 282 | 0.7713 | 1887 | NOT_EVALUABLE |

## 3. Design B — persistence-preserving occupancy (corroborative)

| cell | inert names | retained | ret. ep share | FIT excess pp | FIT perm p | B status | B stamp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DD20|main|H10 | 207 | 1483 | 0.9891 | 1.0481 | 0.192904 | NULL |  |
| DD20|main|H5 | 207 | 1483 | 0.9892 | 0.5354 | 0.084958 | NULL |  |
| DD20|chinext20|H10 | 207 | 1483 | 0.9622 | -0.4428 | 0.001 | NULL |  |
| DD20|chinext20|H5 | 207 | 1483 | 0.9585 | -0.3328 | 0.001 | NULL |  |
| DD35|main|H10 | 128 | 1562 | 0.9952 | 2.9242 | 0.001 | NULL |  |
| DD35|main|H5 | 128 | 1562 | 0.9951 | 1.5526 | 0.001 | NULL |  |
| DD35|chinext20|H10 | 128 | 1562 | 0.976 | 0.1991 | 0.807596 | NULL |  |
| DD35|chinext20|H5 | 128 | 1562 | 0.9801 | 0.0779 | 0.965517 | NULL |  |
| MA200|main|H10 | 105 | 1585 | 0.9961 | -2.7345 | 0.001 | NULL |  |
| MA200|main|H5 | 105 | 1585 | 0.9961 | -1.6077 | 0.001 | NULL |  |
| MA200|chinext20|H10 | 105 | 1585 | 0.9888 | -0.7541 | 0.013993 | NULL |  |
| MA200|chinext20|H5 | 105 | 1585 | 0.9872 | -0.3109 | 0.110945 | NULL |  |
| QB|main|H10 | 38 | 1640 | 0.9993 | -1.4658 | 0.001 | NULL |  |
| QB|main|H5 | 38 | 1640 | 0.9991 | -0.8895 | 0.001 | NULL |  |
| QB|chinext20|H10 | 38 | 1640 | 0.9847 | -0.7564 | 0.001999 | NULL |  |
| QB|chinext20|H5 | 38 | 1640 | 0.9811 | -0.432 | 0.001 | NULL |  |
| VZ|main|H10 | 9 | 1732 | 1.0 | 1.4052 | 0.001 | NULL |  |
| VZ|main|H5 | 9 | 1732 | 1.0 | 1.0129 | 0.001 | NULL |  |
| VZ|chinext20|H10 | 9 | 1732 | 1.0 | 0.7258 | 0.001 | NULL | NAME_PROPENSITY |
| VZ|chinext20|H5 | 9 | 1732 | 1.0 | 0.4667 | 0.001 | NULL | NAME_PROPENSITY |

## 4. Calibration proof for the new null

B's null is a no-merge spell-sequence shuffle (A4), not P-B2's S ∈ {250, 500, 1000} feature shift. Coarse-df names are PERM-INERT (A5). G6B is cross-name path assignment (A6), not `F − p_i`. The §11 battery is the calibration proof that this null can fail:

| §11 control | passed | probe detected |
| --- | --- | --- |
| persistent_state_null | yes | yes |
| planted_timing | yes | yes |
| permuted_plant_falls_back | yes | yes |
| mutated_transition_timing | yes | yes |
| regime_placebo | yes | yes |
| name_propensity_constant | yes | yes |

## 5. Certified / null / uninformative table (prereg §10)

| cell | A | B | headline | stamp | §10 row | timing language |
| --- | --- | --- | --- | --- | --- | --- |
| DD20|main|H10 | NULL | NULL | NULL | — | 5 | no |
| DD20|main|H5 | NULL | NULL | NULL | — | 5 | no |
| DD20|chinext20|H10 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| DD20|chinext20|H5 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| DD35|main|H10 | NULL | NULL | NULL | — | 5 | no |
| DD35|main|H5 | UNINFORMATIVE | NULL | UNINFORMATIVE | PROPENSITY_CONCENTRATED | A9 | no |
| DD35|chinext20|H10 | UNINFORMATIVE | NULL | UNINFORMATIVE | PROPENSITY_CONCENTRATED | A9 | no |
| DD35|chinext20|H5 | NULL | NULL | NULL | — | 5 | no |
| MA200|main|H10 | CERTIFIED_TIMING | NULL | UNINFORMATIVE | A_B_CONTRADICT | 8 | no |
| MA200|main|H5 | CERTIFIED_TIMING | NULL | UNINFORMATIVE | A_B_CONTRADICT | 8 | no |
| MA200|chinext20|H10 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| MA200|chinext20|H5 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| QB|main|H10 | CERTIFIED_TIMING | NULL | UNINFORMATIVE | A_B_CONTRADICT | A9 | no |
| QB|main|H5 | CERTIFIED_TIMING | NULL | UNINFORMATIVE | A_B_CONTRADICT | A9 | no |
| QB|chinext20|H10 | UNINFORMATIVE | NULL | UNINFORMATIVE | PROPENSITY_CONCENTRATED | A9 | no |
| QB|chinext20|H5 | CERTIFIED_TIMING | NULL | UNINFORMATIVE | A_B_CONTRADICT | A9 | no |
| VZ|main|H10 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| VZ|main|H5 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| VZ|chinext20|H10 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |
| VZ|chinext20|H5 | NOT_EVALUABLE | NULL | NULL | A_SILENT_B_NULL | 6 | no |

**Tally:** NULL=12, UNINFORMATIVE=8

## 6. Name-propensity and carrier controls

| cell | A top-tercile share | A G6 | G6B p | G6B stamp | M3 (carrier) | headline stamp |
| --- | --- | --- | --- | --- | --- | --- |
| DD20|main|H10 | 0.16882427843803055 | yes |  | — | NOT_APPLICABLE | — |
| DD20|main|H5 | 0.17046632124352332 | yes |  | — | NOT_APPLICABLE | — |
| DD20|chinext20|H10 | 0.2748735244519393 | yes |  | — | NOT_APPLICABLE | A_SILENT_B_NULL |
| DD20|chinext20|H5 | 0.2760942760942761 | yes |  | — | NOT_APPLICABLE | A_SILENT_B_NULL |
| DD35|main|H10 | 0.30664269092447644 | yes | 0.0005 | — | NOT_APPLICABLE | — |
| DD35|main|H5 | 0.3063314711359404 | FAIL | 0.0005 | — | NOT_APPLICABLE | PROPENSITY_CONCENTRATED |
| DD35|chinext20|H10 | 0.26552984165651644 | FAIL |  | — | NOT_APPLICABLE | PROPENSITY_CONCENTRATED |
| DD35|chinext20|H5 | 0.26520681265206814 | yes |  | — | NOT_APPLICABLE | — |
| MA200|main|H10 | 0.34901960784313724 | yes | 0.0005 | — | tested | A_B_CONTRADICT |
| MA200|main|H5 | 0.34935850169591504 | yes | 0.0005 | — | tested | A_B_CONTRADICT |
| MA200|chinext20|H10 | 0.3339920948616601 | yes |  | — | tested | A_SILENT_B_NULL |
| MA200|chinext20|H5 | 0.33267716535433073 | yes |  | — | tested | A_SILENT_B_NULL |
| QB|main|H10 | 0.26743185078909615 | yes | 0.0005 | — | tested | A_B_CONTRADICT |
| QB|main|H5 | 0.26618155503738844 | yes | 0.0005 | — | tested | A_B_CONTRADICT |
| QB|chinext20|H10 | 0.2706904435299497 | FAIL | 0.098451 | — | tested | PROPENSITY_CONCENTRATED |
| QB|chinext20|H5 | 0.27056672760511885 | yes | 0.071964 | — | tested | A_B_CONTRADICT |
| VZ|main|H10 | 0.36187113857016767 | yes | 0.0005 | — | tested | A_SILENT_B_NULL |
| VZ|main|H5 | 0.3628682565999235 | yes | 0.0005 | — | tested | A_SILENT_B_NULL |
| VZ|chinext20|H10 | 0.3872647176611934 | yes | 0.111944 | NAME_PROPENSITY | tested | A_SILENT_B_NULL |
| VZ|chinext20|H5 | 0.3875100080064051 | yes | 0.117941 | NAME_PROPENSITY | tested | A_SILENT_B_NULL |

## 7. Regime decomposition

Session-regime terciles are one U1-fraction per FIT session, PIT cuts, HOLDOUT/AUDIT clipped, ties to the lower tercile (A8). M4-only survival is NULL / `REGIME` and is not an instrument effect.

| cell | §8 mechanism | note |
| --- | --- | --- |
| DD20|main|H10 | — | no surviving mechanism |
| DD20|main|H5 | — | no surviving mechanism |
| DD20|chinext20|H10 | — | no surviving mechanism |
| DD20|chinext20|H5 | — | no surviving mechanism |
| DD35|main|H10 | — | no surviving mechanism |
| DD35|main|H5 | M2 | name propensity / persistent level |
| DD35|chinext20|H10 | M2 | name propensity / persistent level |
| DD35|chinext20|H5 | — | no surviving mechanism |
| MA200|main|H10 | M1 | persistent structural state or certified occupancy after G6B |
| MA200|main|H5 | M1 | persistent structural state or certified occupancy after G6B |
| MA200|chinext20|H10 | — | no surviving mechanism |
| MA200|chinext20|H5 | — | no surviving mechanism |
| QB|main|H10 | M1 | persistent structural state or certified occupancy after G6B |
| QB|main|H5 | M1 | persistent structural state or certified occupancy after G6B |
| QB|chinext20|H10 | M2 | name propensity / persistent level |
| QB|chinext20|H5 | M1 | persistent structural state or certified occupancy after G6B |
| VZ|main|H10 | — | no surviving mechanism |
| VZ|main|H5 | — | no surviving mechanism |
| VZ|chinext20|H10 | M2 | name propensity / persistent level |
| VZ|chinext20|H5 | M2 | name propensity / persistent level |

## 8. Adversarial dispositions

| §11 control | why | passed | probe |
| --- | --- | --- | --- |
| persistent_state_null | prereg §11.1 — synthetic F = name-level constant (FIT median dd250 ≤ −0.35) | yes | detected |
| planted_timing | prereg §11.2 — short-spell dummy 5 sessions before a random 5% of first boards | yes | detected |
| permuted_plant_falls_back | prereg §11.3 — apply the no-merge shuffle to the planted feature | yes | detected |
| mutated_transition_timing | prereg §11.4 — move each planted transition by ± Uniform{20,…,60} | yes | detected |
| regime_placebo | prereg §11.5 — F = 1 on sessions whose U1 fraction exceeds the FIT-session median | yes | detected |
| name_propensity_constant | prereg §11.6 — F = 1 iff the name's FIT-only under_ma200 fraction exceeds the median | yes | detected |

Verification battery: 19/19 checks passed; 19/19 probes detected.

## 9. Diagnostic long-horizon shift (non-gating)

S ∈ {250, 500, 1000} on DD20/DD35 only. This is not a certification null and does not upgrade or downgrade any §10 headline (`DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`).

| cell | real FIT excess pp | shifted FIT excess pp |
| --- | --- | --- |
| S250|DD20|main|H10 | 1.0433 | 0.8379 |
| S250|DD20|main|H5 | 0.5321 | 0.4265 |
| S250|DD20|chinext20|H10 | -0.4991 | 0.4477 |
| S250|DD20|chinext20|H5 | -0.3591 | 0.228 |
| S250|DD35|main|H10 | 2.9544 | 0.7975 |
| S250|DD35|main|H5 | 1.5682 | 0.4321 |
| S250|DD35|chinext20|H10 | 0.1402 | 0.2751 |
| S250|DD35|chinext20|H5 | 0.0447 | 0.1387 |
| S500|DD20|main|H10 | 1.0433 | 1.0563 |
| S500|DD20|main|H5 | 0.5321 | 0.5565 |
| S500|DD20|chinext20|H10 | -0.4991 | 0.5934 |
| S500|DD20|chinext20|H5 | -0.3591 | 0.2461 |
| S500|DD35|main|H10 | 2.9544 | 1.1075 |
| S500|DD35|main|H5 | 1.5682 | 0.5709 |
| S500|DD35|chinext20|H10 | 0.1402 | 0.6262 |
| S500|DD35|chinext20|H5 | 0.0447 | 0.3486 |
| S1000|DD20|main|H10 | 1.0433 | 0.3635 |
| S1000|DD20|main|H5 | 0.5321 | 0.1727 |
| S1000|DD20|chinext20|H10 | -0.4991 | 0.2406 |
| S1000|DD20|chinext20|H5 | -0.3591 | 0.1113 |
| S1000|DD35|main|H10 | 2.9544 | 0.8921 |
| S1000|DD35|main|H5 | 1.5682 | 0.4672 |
| S1000|DD35|chinext20|H10 | 0.1402 | 0.3208 |
| S1000|DD35|chinext20|H5 | 0.0447 | 0.1876 |

## 10. Exact implication for P-D

TIMING-stamped cells are eligible P-D timing-family inputs. Occupancy-stamped cells are eligible only as named occupancy covariates; P-D must still beat name propensity and the washout carrier. A CARRIER_SERIES cell is not incremental information over the washout carrier. NULL is not a P-D input and is not re-shopped. INSUFFICIENT SUPPORT is not a P-D input and not a kill of the search space. UNINFORMATIVE is an instrument defect. Nothing here is production authority. P-D is not opened.

| bucket | cells |
| --- | --- |
| timing-family inputs | — |
| occupancy covariates only | — |
| NULL (not a P-D input; do not re-shop) | DD20|main|H10, DD20|main|H5, DD20|chinext20|H10, DD20|chinext20|H5, DD35|main|H10, DD35|chinext20|H5, MA200|chinext20|H10, MA200|chinext20|H5, VZ|main|H10, VZ|main|H5, VZ|chinext20|H10, VZ|chinext20|H5 |
| INSUFFICIENT SUPPORT (not a P-D input; not a kill) | — |
| UNINFORMATIVE (instrument defect) | DD35|main|H5, DD35|chinext20|H10, MA200|main|H10, MA200|main|H5, QB|main|H10, QB|main|H5, QB|chinext20|H10, QB|chinext20|H5 |
| CARRIER_SERIES (not incremental to washout) | — |

P-D is **not** opened by this session.

## 11. Inherited limits

- Back-adjusted basis; tolerant-detector cohort, not exchange-exact.
- Curated large-cap survivor slice; delisted names are absent.
- Current-membership sector map travels with the panel (SECT is out of scope).
- VZ coincident-indicator stamp (median arming lead 1 session) travels with every VZ verdict.

---

*P-B3 certification run. SEED=20260815. Artifact date 2026-08-15 (frozen, not wall-clock). TZ=UTC.*
