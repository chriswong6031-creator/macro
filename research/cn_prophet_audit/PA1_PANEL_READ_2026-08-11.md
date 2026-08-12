# P-A1 — descriptive read of the Prophet pick panel (2026-08-11)

Authority: `none_research_display_only`. Tier: display / audit tier — descriptive counts and episode lists only; not a promotion, not a gate, not a ranker, not a sizing input; no expectancy, no lift and no inference is quoted anywhere in this artifact.

Counts and episode lists only. **No lift, no t-statistic, no interval, no inference row appears anywhere in this artifact** — by charter, because the panel is 27 sessions of one era with a frozen genesis stream. The inference battery (P-A2) is accrual-gated at >=120 sessions AND >=2 regime segments on a single stream; partial peeks are forbidden.

Governing ruling: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`. Spec: `P_A_PANEL_CHARTER_2026-08-11.md`. Pinned definitions: `washout_onset_w1.py` (W-P0), imported — not re-derived.

---

## 1. What was read

Two in-repo point-in-time ledgers, read-only, through an explicit column allowlist. The quarantined columns (`fwd_mfe_*`, `terminal_state_*`, `post_cushion_breach`, `level`) are **never materialised** — they run on the dividend-adjusted plane and are not evidence here. Board outcomes are re-derived from `data/china_stocks_raw` with W-P0's own tolerant detector.

| definition stream | board sessions | board rows | distinct names (honest-N) | span | candidates rows |
|---|---|---|---|---|---|
| `legacy` | 18 | 1082 | 464 | 2026-06-30 → 2026-07-29 | — |
| `cn_prophet_v2` **(frozen)** | 5 | 72 | 47 | 2026-07-30 → 2026-08-05 | 7548 |
| `cn_prophet_v2_shadow` | 4 | 53 | 35 | 2026-08-06 → 2026-08-11 | — |
| `cn_prophet_v3` | 4 | 96 | 61 | 2026-08-06 → 2026-08-11 | 6642 |
| `cn_reversal_watch_v1` | 6 | 182 | 81 | 2026-08-04 → 2026-08-11 | — |

**`cn_prophet_v2` is FROZEN — the genesis stream; superseded by cn_prophet_v3 on 2026-08-06 at 5 sessions. It will not accrue further.** This fact is repeated beside every table below in which it appears; its five sessions are not a small sample of an ongoing process, they are the whole of it.

Streams are never pooled. Each is a different instrument observed over a different, short window.

**Basis, and the standing ruling.** The tolerant detector runs on `data/china_stocks_raw`, which is BACK-ADJUSTED (W-P0's BASIS NOTE) — so this artifact states its basis rather than implying an exchange-exact one. `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` withdrew the adjusted-plane limit tape and its descendants from AUTHORITY: nothing derived from that plane may be graded, ranked, gated, sized, alerted, traded, promoted, or shown as a current probability. P-A1 does none of those things — it is a display-tier count of ledger rows and detector events, the charter's own mandated construction (term 4: re-derive board outcomes from `china_stocks_raw` with the tolerant detector, the W-P0 pattern). The residual cost of the basis is not hidden: it is MEASURED in `verify.detector_vs_zt_pool` and both misses are named. The reopen path to authority-tier limit work is unchanged and this artifact makes no claim to be on it: that requires the unadjusted vendor plane with integer-cent equality and exchange half-up validation, per the ruling's own reopen terms.

## 2. Footprint presence at pick time — the agreement matrix

For every board row, W-P0's pinned footprints are re-derived from bars available at that pick date and crossed with the ledger writer's own stamps. Counts are row counts within the stream. `engine only` = the writer stamped it and the W-P0 footprint did not; `W-P0 only` = the reverse.

Footprint availability: **1483 of 1485** board rows carry a full footprint set at their own pick date. The 2 without one are named in §6.

### `legacy`

honest-N: **18 sessions**, **463 distinct names**, 1081 board rows with footprints.

| engine stamp | W-P0 footprint | both | engine only | W-P0 only | neither | engine true (all) | W-P0 true (all) |
|---|---|---|---|---|---|---|---|
| `engine_washout` | `wp0_washout_dd_le_m20` | 141 | 50 | 759 | 131 | 191 | 900 |
| `engine_washout` | `wp0_washout_dd_le_m35` | 51 | 140 | 452 | 438 | 191 | 503 |
| `engine_washout` | `wp0_under_ma200` | 158 | 33 | 747 | 143 | 191 | 905 |
| `engine_washout` | `wp0_confluence_long` | 148 | 43 | 610 | 280 | 191 | 758 |
| `engine_washout` | `wp0_sector_deep35_ge40` | 124 | 67 | 637 | 253 | 191 | 761 |
| `engine_species_cn_washout` | `wp0_washout_dd_le_m20` | 77 | 35 | 823 | 146 | 112 | 900 |
| `engine_species_cn_washout` | `wp0_under_ma200` | 94 | 18 | 811 | 158 | 112 | 905 |

### `cn_prophet_v2` — **FROZEN STREAM**

honest-N: **5 sessions**, **46 distinct names**, 71 board rows with footprints. FROZEN — the genesis stream; superseded by cn_prophet_v3 on 2026-08-06 at 5 sessions. It will not accrue further.

| engine stamp | W-P0 footprint | both | engine only | W-P0 only | neither | engine true (all) | W-P0 true (all) |
|---|---|---|---|---|---|---|---|
| `engine_washout` | `wp0_washout_dd_le_m20` | 25 | 1 | 35 | 10 | 26 | 60 |
| `engine_washout` | `wp0_washout_dd_le_m35` | 13 | 13 | 6 | 39 | 26 | 19 |
| `engine_washout` | `wp0_under_ma200` | 26 | 0 | 34 | 11 | 26 | 60 |
| `engine_washout` | `wp0_confluence_long` | 24 | 2 | 41 | 4 | 26 | 65 |
| `engine_washout` | `wp0_sector_deep35_ge40` | 12 | 14 | 32 | 13 | 26 | 44 |
| `engine_species_cn_washout` | `wp0_washout_dd_le_m20` | 25 | 1 | 35 | 10 | 26 | 60 |
| `engine_species_cn_washout` | `wp0_under_ma200` | 26 | 0 | 34 | 11 | 26 | 60 |

### `cn_prophet_v2_shadow`

honest-N: **4 sessions**, **35 distinct names**, 53 board rows with footprints.

| engine stamp | W-P0 footprint | both | engine only | W-P0 only | neither | engine true (all) | W-P0 true (all) |
|---|---|---|---|---|---|---|---|
| `engine_washout` | `wp0_washout_dd_le_m20` | 12 | 5 | 24 | 12 | 17 | 36 |
| `engine_washout` | `wp0_washout_dd_le_m35` | 8 | 9 | 9 | 27 | 17 | 17 |
| `engine_washout` | `wp0_under_ma200` | 8 | 9 | 22 | 14 | 17 | 30 |
| `engine_washout` | `wp0_confluence_long` | 17 | 0 | 33 | 3 | 17 | 50 |
| `engine_washout` | `wp0_sector_deep35_ge40` | 13 | 4 | 28 | 8 | 17 | 41 |
| `engine_species_cn_washout` | `wp0_washout_dd_le_m20` | 12 | 5 | 24 | 12 | 17 | 36 |
| `engine_species_cn_washout` | `wp0_under_ma200` | 8 | 9 | 22 | 14 | 17 | 30 |

### `cn_prophet_v3`

honest-N: **4 sessions**, **61 distinct names**, 96 board rows with footprints.

| engine stamp | W-P0 footprint | both | engine only | W-P0 only | neither | engine true (all) | W-P0 true (all) |
|---|---|---|---|---|---|---|---|
| `engine_washout` | `wp0_washout_dd_le_m20` | 3 | 0 | 93 | 0 | 3 | 96 |
| `engine_washout` | `wp0_washout_dd_le_m35` | 2 | 1 | 88 | 5 | 3 | 90 |
| `engine_washout` | `wp0_under_ma200` | 3 | 0 | 92 | 1 | 3 | 95 |
| `engine_washout` | `wp0_confluence_long` | 3 | 0 | 73 | 20 | 3 | 76 |
| `engine_washout` | `wp0_sector_deep35_ge40` | 1 | 2 | 75 | 18 | 3 | 76 |
| `engine_species_cn_washout` | `wp0_washout_dd_le_m20` | 3 | 0 | 93 | 0 | 3 | 96 |
| `engine_species_cn_washout` | `wp0_under_ma200` | 3 | 0 | 92 | 1 | 3 | 95 |

### `cn_reversal_watch_v1`

honest-N: **6 sessions**, **81 distinct names**, 182 board rows with footprints.

| engine stamp | W-P0 footprint | both | engine only | W-P0 only | neither | engine true (all) | W-P0 true (all) |
|---|---|---|---|---|---|---|---|
| `engine_washout` | `wp0_washout_dd_le_m20` | 0 | 0 | 182 | 0 | 0 | 182 |
| `engine_washout` | `wp0_washout_dd_le_m35` | 0 | 0 | 181 | 1 | 0 | 181 |
| `engine_washout` | `wp0_under_ma200` | 0 | 0 | 181 | 1 | 0 | 181 |
| `engine_washout` | `wp0_confluence_long` | 0 | 0 | 182 | 0 | 0 | 182 |
| `engine_washout` | `wp0_sector_deep35_ge40` | 0 | 0 | 176 | 6 | 0 | 176 |
| `engine_species_cn_washout` | `wp0_washout_dd_le_m20` | 0 | 0 | 182 | 0 | 0 | 182 |
| `engine_species_cn_washout` | `wp0_under_ma200` | 0 | 0 | 181 | 1 | 0 | 181 |

### Divergent names — `washout` (engine) vs `dd250 <= -20%` (W-P0)

Divergence is data, not error. The two notions are not the same measurement: the writer's flag is a composite state stamp, W-P0's is a drawdown depth off the 250-session high.

**`legacy`** — honest-N 18 sessions / 463 distinct names / 1081 rows. Engine-only 50 rows (26 names); W-P0-only 759 rows (342 names).

- engine `washout` true, W-P0 drawdown shallower than -20%: `000301.SZ @ 2026-07-08`, `000333.SZ @ 2026-07-07`, `000333.SZ @ 2026-07-08`, `000423.SZ @ 2026-07-13`, `000423.SZ @ 2026-07-14`, `000423.SZ @ 2026-07-15`, `000719.SZ @ 2026-07-21`, `000729.SZ @ 2026-07-15`, `000729.SZ @ 2026-07-16`, `000729.SZ @ 2026-07-17`, `002396.SZ @ 2026-07-07`, `002966.SZ @ 2026-07-14`, `002966.SZ @ 2026-07-15`, `002966.SZ @ 2026-07-16`, `300303.SZ @ 2026-06-30`, `301381.SZ @ 2026-07-15`, `301571.SZ @ 2026-07-10`, `600025.SS @ 2026-07-10`, `600025.SS @ 2026-07-13`, `600025.SS @ 2026-07-14`, `600066.SS @ 2026-07-21`, `600116.SS @ 2026-07-21`, `600116.SS @ 2026-07-23`, `600116.SS @ 2026-07-24`, `600267.SS @ 2026-07-01`, `600267.SS @ 2026-07-02`, `600323.SS @ 2026-07-21`, `600664.SS @ 2026-07-14`, `600664.SS @ 2026-07-15`, `600673.SS @ 2026-07-13`, `600673.SS @ 2026-07-14`, `600795.SS @ 2026-07-21`, `600795.SS @ 2026-07-23`, `600795.SS @ 2026-07-24`, `600908.SS @ 2026-07-13`, `601168.SS @ 2026-07-14`, `601168.SS @ 2026-07-15`, `601168.SS @ 2026-07-16`, `601607.SS @ 2026-07-07`, `601607.SS @ 2026-07-08` … (+10 more; full list in the JSON receipt)
- W-P0 drawdown at/below -20%, engine `washout` false: `000002.SZ @ 2026-07-02`, `000002.SZ @ 2026-07-03`, `000002.SZ @ 2026-07-07`, `000002.SZ @ 2026-07-08`, `000034.SZ @ 2026-06-30`, `000034.SZ @ 2026-07-03`, `000034.SZ @ 2026-07-23`, `000034.SZ @ 2026-07-24`, `000034.SZ @ 2026-07-27`, `000039.SZ @ 2026-07-28`, `000039.SZ @ 2026-07-29`, `000061.SZ @ 2026-06-30`, `000061.SZ @ 2026-07-01`, `000061.SZ @ 2026-07-02`, `000061.SZ @ 2026-07-03`, `000063.SZ @ 2026-07-10`, `000063.SZ @ 2026-07-14`, `000408.SZ @ 2026-07-21`, `000422.SZ @ 2026-06-30`, `000425.SZ @ 2026-07-17`, `000425.SZ @ 2026-07-21`, `000503.SZ @ 2026-07-16`, `000503.SZ @ 2026-07-17`, `000503.SZ @ 2026-07-21`, `000506.SZ @ 2026-07-08`, `000534.SZ @ 2026-07-07`, `000543.SZ @ 2026-07-23`, `000550.SZ @ 2026-07-17`, `000603.SZ @ 2026-07-23`, `000603.SZ @ 2026-07-24`, `000603.SZ @ 2026-07-29`, `000625.SZ @ 2026-06-30`, `000625.SZ @ 2026-07-01`, `000629.SZ @ 2026-07-01`, `000629.SZ @ 2026-07-02`, `000651.SZ @ 2026-06-30`, `000651.SZ @ 2026-07-01`, `000676.SZ @ 2026-07-13`, `000703.SZ @ 2026-07-01`, `000708.SZ @ 2026-07-14` … (+719 more; full list in the JSON receipt)

**`cn_prophet_v2`** (frozen) — honest-N 5 sessions / 46 distinct names / 71 rows. Engine-only 1 rows (1 names); W-P0-only 35 rows (25 names).

- engine `washout` true, W-P0 drawdown shallower than -20%: `000983.SZ @ 2026-08-03`
- W-P0 drawdown at/below -20%, engine `washout` false: `000027.SZ @ 2026-08-03`, `000630.SZ @ 2026-08-05`, `000737.SZ @ 2026-08-03`, `002608.SZ @ 2026-08-03`, `300017.SZ @ 2026-08-04`, `300059.SZ @ 2026-08-05`, `300496.SZ @ 2026-08-04`, `300702.SZ @ 2026-08-04`, `300702.SZ @ 2026-08-05`, `301291.SZ @ 2026-08-03`, `600143.SS @ 2026-08-04`, `600143.SS @ 2026-08-05`, `600157.SS @ 2026-08-03`, `600157.SS @ 2026-08-04`, `600502.SS @ 2026-07-30`, `600575.SS @ 2026-07-30`, `600862.SS @ 2026-08-03`, `600956.SS @ 2026-08-03`, `600958.SS @ 2026-08-03`, `600958.SS @ 2026-08-05`, `601021.SS @ 2026-07-30`, `601021.SS @ 2026-07-31`, `601162.SS @ 2026-08-04`, `601878.SS @ 2026-08-03`, `601878.SS @ 2026-08-04`, `603327.SS @ 2026-08-05`, `603358.SS @ 2026-08-05`, `603605.SS @ 2026-08-03`, `688036.SS @ 2026-07-30`, `688065.SS @ 2026-07-30`, `688065.SS @ 2026-08-03`, `688538.SS @ 2026-07-30`, `688538.SS @ 2026-07-31`, `688538.SS @ 2026-08-03`, `688538.SS @ 2026-08-04`

**`cn_prophet_v2_shadow`** — honest-N 4 sessions / 35 distinct names / 53 rows. Engine-only 5 rows (3 names); W-P0-only 24 rows (19 names).

- engine `washout` true, W-P0 drawdown shallower than -20%: `000301.SZ @ 2026-08-06`, `000301.SZ @ 2026-08-07`, `301345.SZ @ 2026-08-10`, `301345.SZ @ 2026-08-11`, `601233.SS @ 2026-08-10`
- W-P0 drawdown at/below -20%, engine `washout` false: `000060.SZ @ 2026-08-10`, `000534.SZ @ 2026-08-10`, `000795.SZ @ 2026-08-10`, `000887.SZ @ 2026-08-10`, `000887.SZ @ 2026-08-11`, `002738.SZ @ 2026-08-10`, `300017.SZ @ 2026-08-07`, `300024.SZ @ 2026-08-11`, `300058.SZ @ 2026-08-07`, `300059.SZ @ 2026-08-07`, `300182.SZ @ 2026-08-07`, `300276.SZ @ 2026-08-10`, `300276.SZ @ 2026-08-11`, `300474.SZ @ 2026-08-10`, `300702.SZ @ 2026-08-06`, `301236.SZ @ 2026-08-07`, `301236.SZ @ 2026-08-11`, `600509.SS @ 2026-08-10`, `600688.SS @ 2026-08-10`, `603328.SS @ 2026-08-11`, `603358.SS @ 2026-08-07`, `603358.SS @ 2026-08-10`, `603358.SS @ 2026-08-11`, `603997.SS @ 2026-08-07`

**`cn_prophet_v3`** — honest-N 4 sessions / 61 distinct names / 96 rows. Engine-only 0 rows (0 names); W-P0-only 93 rows (58 names).

- engine `washout` true, W-P0 drawdown shallower than -20%: _none_
- W-P0 drawdown at/below -20%, engine `washout` false: `000027.SZ @ 2026-08-07`, `000420.SZ @ 2026-08-11`, `000534.SZ @ 2026-08-06`, `000547.SZ @ 2026-08-07`, `000559.SZ @ 2026-08-06`, `000766.SZ @ 2026-08-10`, `000833.SZ @ 2026-08-10`, `000833.SZ @ 2026-08-11`, `000901.SZ @ 2026-08-06`, `000901.SZ @ 2026-08-07`, `000973.SZ @ 2026-08-07`, `001301.SZ @ 2026-08-10`, `002015.SZ @ 2026-08-06`, `002149.SZ @ 2026-08-11`, `002181.SZ @ 2026-08-10`, `002181.SZ @ 2026-08-11`, `002324.SZ @ 2026-08-06`, `002324.SZ @ 2026-08-10`, `002434.SZ @ 2026-08-06`, `002460.SZ @ 2026-08-10`, `002460.SZ @ 2026-08-11`, `002465.SZ @ 2026-08-10`, `002465.SZ @ 2026-08-11`, `002487.SZ @ 2026-08-07`, `002544.SZ @ 2026-08-07`, `002549.SZ @ 2026-08-10`, `002756.SZ @ 2026-08-10`, `002756.SZ @ 2026-08-11`, `002812.SZ @ 2026-08-10`, `002831.SZ @ 2026-08-10`, `300007.SZ @ 2026-08-06`, `300061.SZ @ 2026-08-07`, `300065.SZ @ 2026-08-10`, `300113.SZ @ 2026-08-06`, `300113.SZ @ 2026-08-07`, `300153.SZ @ 2026-08-06`, `300446.SZ @ 2026-08-06`, `300446.SZ @ 2026-08-07`, `300450.SZ @ 2026-08-10`, `300450.SZ @ 2026-08-11` … (+53 more; full list in the JSON receipt)

**`cn_reversal_watch_v1`** — honest-N 6 sessions / 81 distinct names / 182 rows. Engine-only 0 rows (0 names); W-P0-only 182 rows (81 names).

- engine `washout` true, W-P0 drawdown shallower than -20%: _none_
- W-P0 drawdown at/below -20%, engine `washout` false: `000099.SZ @ 2026-08-05`, `000099.SZ @ 2026-08-07`, `000426.SZ @ 2026-08-04`, `000426.SZ @ 2026-08-05`, `000547.SZ @ 2026-08-10`, `000880.SZ @ 2026-08-10`, `000880.SZ @ 2026-08-11`, `000901.SZ @ 2026-08-10`, `000981.SZ @ 2026-08-10`, `002017.SZ @ 2026-08-05`, `002017.SZ @ 2026-08-06`, `002017.SZ @ 2026-08-07`, `002017.SZ @ 2026-08-11`, `002121.SZ @ 2026-08-06`, `002121.SZ @ 2026-08-07`, `002131.SZ @ 2026-08-05`, `002131.SZ @ 2026-08-06`, `002131.SZ @ 2026-08-07`, `002131.SZ @ 2026-08-10`, `002131.SZ @ 2026-08-11`, `002151.SZ @ 2026-08-10`, `002151.SZ @ 2026-08-11`, `002368.SZ @ 2026-08-04`, `002368.SZ @ 2026-08-05`, `002368.SZ @ 2026-08-06`, `002368.SZ @ 2026-08-11`, `002400.SZ @ 2026-08-05`, `002400.SZ @ 2026-08-06`, `002400.SZ @ 2026-08-07`, `002544.SZ @ 2026-08-05`, `002544.SZ @ 2026-08-06`, `002544.SZ @ 2026-08-10`, `002544.SZ @ 2026-08-11`, `002602.SZ @ 2026-08-04`, `002602.SZ @ 2026-08-07`, `002624.SZ @ 2026-08-05`, `002639.SZ @ 2026-08-06`, `002639.SZ @ 2026-08-10`, `002639.SZ @ 2026-08-11`, `002716.SZ @ 2026-08-05` … (+142 more; full list in the JSON receipt)

## 3. First-board incidence within H ∈ {5, 10} sessions

Re-derived with W-P0's tolerant detector from `china_stocks_raw` — never from an embedded column. **Right-censoring is reported, not counted as a negative:** the store ends at the panel's last session, so a pick made near the end has no complete forward window. A board observed inside an incomplete window is still an observed board; only *absence* is ambiguous there.

`board within H` = a tolerant board occurred in T+1..T+H. `no board (complete)` = the window closed with none. `censored` = window still open, none yet. W-P0's own `fb_H` flag is printed beside them: it requires a complete window, so it counts only the boards in the first column whose window also closed.

### `legacy`

honest-N: **18 sessions**, **463 distinct names**, 1081 picks.

| horizon | picks | board within H | no board (complete) | censored | distinct names w/ board | W-P0 `fb_H` | cold-at-pick: board / picks |
|---|---|---|---|---|---|---|---|
| H=5 | 1081 | 54 | 1027 | 0 | 31 | 54 | 25 / 877 |
| H=10 | 1081 | 119 | 911 | 51 | 59 | 110 | 57 / 877 |

- episodes with a board within H=5: `000503.SZ @ 2026-07-21 (+5 sessions)`, `000596.SZ @ 2026-07-16 (+2 sessions)`, `000603.SZ @ 2026-07-29 (+5 sessions)`, `000676.SZ @ 2026-07-13 (+2 sessions)`, `000712.SZ @ 2026-07-29 (+5 sessions)`, `000977.SZ @ 2026-07-07 (+1 sessions)`, `002020.SZ @ 2026-06-30 (+2 sessions)`, `002020.SZ @ 2026-07-01 (+1 sessions)`, `002127.SZ @ 2026-07-10 (+4 sessions)`, `002127.SZ @ 2026-07-15 (+1 sessions)`, `002202.SZ @ 2026-07-03 (+5 sessions)`, `002250.SZ @ 2026-07-01 (+1 sessions)`, `002379.SZ @ 2026-07-16 (+5 sessions)`, `002396.SZ @ 2026-07-07 (+1 sessions)`, `002847.SZ @ 2026-07-23 (+3 sessions)`, `002945.SZ @ 2026-07-23 (+4 sessions)`, `002945.SZ @ 2026-07-24 (+3 sessions)`, `600113.SS @ 2026-06-30 (+1 sessions)`, `600113.SS @ 2026-07-03 (+5 sessions)`, `600118.SS @ 2026-07-03 (+5 sessions)`, `600129.SS @ 2026-07-01 (+5 sessions)`, `600129.SS @ 2026-07-02 (+4 sessions)`, `600236.SS @ 2026-07-15 (+2 sessions)`, `600475.SS @ 2026-07-23 (+5 sessions)`, `600475.SS @ 2026-07-29 (+1 sessions)`, `600664.SS @ 2026-07-10 (+1 sessions)`, `600664.SS @ 2026-07-13 (+1 sessions)`, `600664.SS @ 2026-07-14 (+1 sessions)`, `600664.SS @ 2026-07-15 (+1 sessions)`, `600733.SS @ 2026-07-24 (+3 sessions)` … (+24 more; full list in the JSON receipt)

### `cn_prophet_v2` — **FROZEN STREAM**

honest-N: **5 sessions**, **46 distinct names**, 71 picks. FROZEN — the genesis stream; superseded by cn_prophet_v3 on 2026-08-06 at 5 sessions. It will not accrue further.

| horizon | picks | board within H | no board (complete) | censored | distinct names w/ board | W-P0 `fb_H` | cold-at-pick: board / picks |
|---|---|---|---|---|---|---|---|
| H=5 | 71 | 2 | 53 | 16 | 2 | 1 | 1 / 67 |
| H=10 | 71 | 2 | 0 | 69 | 2 | 0 | 1 / 67 |

- episodes with a board within H=5: `300363.SZ @ 2026-08-05 (+2 sessions)`, `603228.SS @ 2026-08-04 (+2 sessions)`

### `cn_prophet_v2_shadow`

honest-N: **4 sessions**, **35 distinct names**, 53 picks.

| horizon | picks | board within H | no board (complete) | censored | distinct names w/ board | W-P0 `fb_H` | cold-at-pick: board / picks |
|---|---|---|---|---|---|---|---|
| H=5 | 53 | 1 | 0 | 52 | 1 | 0 | 1 / 46 |
| H=10 | 53 | 1 | 0 | 52 | 1 | 0 | 1 / 46 |

- episodes with a board within H=5: `002458.SZ @ 2026-08-06 (+2 sessions)`

### `cn_prophet_v3`

honest-N: **4 sessions**, **61 distinct names**, 96 picks.

| horizon | picks | board within H | no board (complete) | censored | distinct names w/ board | W-P0 `fb_H` | cold-at-pick: board / picks |
|---|---|---|---|---|---|---|---|
| H=5 | 96 | 1 | 0 | 95 | 1 | 0 | 1 / 92 |
| H=10 | 96 | 1 | 0 | 95 | 1 | 0 | 1 / 92 |

- episodes with a board within H=5: `000973.SZ @ 2026-08-07 (+1 sessions)`

### `cn_reversal_watch_v1`

honest-N: **6 sessions**, **81 distinct names**, 182 picks.

| horizon | picks | board within H | no board (complete) | censored | distinct names w/ board | W-P0 `fb_H` | cold-at-pick: board / picks |
|---|---|---|---|---|---|---|---|
| H=5 | 182 | 6 | 28 | 148 | 2 | 2 | 6 / 153 |
| H=10 | 182 | 6 | 0 | 176 | 2 | 0 | 6 / 153 |

- episodes with a board within H=5: `600651.SS @ 2026-08-04 (+3 sessions)`, `603887.SS @ 2026-08-04 (+5 sessions)`, `603887.SS @ 2026-08-05 (+4 sessions)`, `603887.SS @ 2026-08-06 (+3 sessions)`, `603887.SS @ 2026-08-07 (+2 sessions)`, `603887.SS @ 2026-08-10 (+1 sessions)`

A `cold at pick` row is one with no tolerant board in the prior 20 sessions, so a board inside the window is genuinely that name's FIRST board rather than the continuation of a run.

## 4. Same-day board vs candidates — reported, never reconciled

The two ledgers disagree by construction on some sessions: the board surfaces a name the buyability gate blocks. This is a known, formally flagged defect of the WRITE path. P-A1 prints both readings per stream and corrects neither.

The candidates ledger carries only two definition labels — `cn_prophet_v2` and `cn_prophet_v3`. Because streams are never pooled, a board row from `legacy`, `cn_prophet_v2_shadow` or `cn_reversal_watch_v1` has no same-definition candidates row to disagree with, and the test is simply **not evaluable** on those three. Joining them to another definition's rows would be exactly the pooling this charter forbids, so it is not done.

| stream | honest-N sessions / names | board rows | matched in candidates | contradiction test | surfaced but not buyable | distinct names | gate reasons on blocked rows |
|---|---|---|---|---|---|---|---|
| `legacy` | 18 / 463 | 1081 | 0 | **not evaluable** | 0 | 0 | — |
| `cn_prophet_v2` (frozen) | 5 / 46 | 71 | 71 | yes | 2 | 2 | `buy blocked by filter: counter-trend, no 200-reclaim/hold` (1); `buy blocked by filter: failed reclaim-and-hold` (1) |
| `cn_prophet_v2_shadow` | 4 / 35 | 53 | 0 | **not evaluable** | 0 | 0 | — |
| `cn_prophet_v3` | 4 / 61 | 96 | 96 | yes | 0 | 0 | — |
| `cn_reversal_watch_v1` | 6 / 81 | 182 | 0 | **not evaluable** | 0 | 0 | — |

On the two evaluable streams the contradiction is **rare but real**, and the genesis row-pair (§5) is one of its instances. Rarity is not a defence: the disagreement is between two ledgers written by the same nightly process on the same session, and P-A1 leaves it standing for the write path to own.

## 5. Worked example — `300363.SZ`, pick date 2026-08-05

**Board row (cn_prophet_v2, frozen stream).** rank **1**, lane `featured`, tier `T2`, prophet score 90.32, `washout=True`, `washout_2w=1.0`, `species_id='cn_washout'`, bottom quality 0.4, hold state `launched`, regime `Q3`.

**Candidates row, same session.** score rank **367**, prophet score 44.07, `raw_eligible=False`, `buyable=False`, gate reason *"buy blocked by filter: counter-trend, no 200-reclaim/hold"*, gate state `long-bias`.

The same session, the same name, the same writer: surfaced at board rank 1 by the washout-species lane while the buyability gate blocked it for being a counter-trend name with no 200-day reclaim. Both statements are the ledger's own. P-A1 reconciles neither.

**W-P0 footprints at the pick date** (re-derived from bars available on 2026-08-05):

| footprint | value |
|---|---|
| `dd250` | `-0.4211` |
| `dd_band` | `d2_m35_m50` |
| `under_ma200` | `True` |
| `below_band` | `b3_61_120` |
| `sector` | `Healthcare` |
| `sect35_band` | `s2_40_60` |
| `sect_deep35_pct` | `44.23` |
| `quiet_base` | `False` |
| `confluence_long` | `True` |
| `confluence_cb_recent` | `False` |
| `cold_at_pick` | `True` |
| `dist_next_board_sessions` | `2` |
| `fwd_bars_available` | `4` |
| `H5_status` | `board_within_H` |
| `H5_wp0_fb_flag` | `False` |
| `H5_wp0_win_ok` | `False` |
| `H10_status` | `board_within_H` |
| `H10_wp0_fb_flag` | `False` |
| `H10_wp0_win_ok` | `False` |

The gate's prose and the footprint agree on the substance: `under_ma200=True`, in W-P0's `b3_61_120` band (61-120 consecutive sessions below the 200DMA), 42.1% off its 250-session high, in a sector where 44.23% of the other members are also 35%+ down. The name was exactly what the gate said it was — which is the whole point of the row-pair: the lane surfaced it FOR the state the gate rejected it for.

**Board outcome, re-derived.** The next tolerant board came **2 sessions** after the pick. At H=5 the status is `board_within_H`; W-P0's own `fb_5` flag reads `False` because `win_ok_5` is `False` — only 4 forward sessions exist in the store, so the 5-session window never closed. **This is precisely why the trichotomy exists**: reported as `fb_5` alone, an observed board would have printed as a null.

Forward tape from the pick (tolerant-detector flags only — no price or return claim is made):

| date | tolerant board | dd250 | under 200DMA |
|---|---|---|---|
| 2026-08-05 | False | -0.4211 | True |
| 2026-08-06 | False | -0.4398 | True |
| 2026-08-07 | True | -0.3276 | True |
| 2026-08-10 | False | -0.2878 | False |
| 2026-08-11 | False | -0.2832 | False |

The candidates ledger's own trajectory for the name across the following sessions, including its migration to the `cn_prophet_v3` definition:

| stamp date | definition | score rank | prophet score | buyable | gate reason |
|---|---|---|---|---|---|
| 2026-08-05 | `cn_prophet_v2` | 367 | 44.07 | False | buy blocked by filter: counter-trend, no 200-reclaim/hold |
| 2026-08-06 | `cn_prophet_v3` | 931 | 41.23 | False | buy blocked by filter: counter-trend, no 200-reclaim/hold |
| 2026-08-07 | `cn_prophet_v3` | 1557 | 25.73 | False | buy blocked by filter: counter-trend, held but no 200-reclaim |
| 2026-08-10 | `cn_prophet_v3` | 1615 | 21.55 | False | buy blocked by filter: counter-trend, held but no 200-reclaim |
| 2026-08-11 | `cn_prophet_v3` | 1650 | 16.26 | False | buy blocked by filter: counter-trend, held but no 200-reclaim |

## 6. Verification

**9 of 9 checks passed; 9 of 9 mutation probes detected their mutation.**

_A check that cannot fail is a defect. Every check above is paired with a mutation that it MUST detect; `detected: false` anywhere means the check is vacuous and the run is not evidence._

| check | result | mutation probe | mutation applied |
|---|---|---|---|
| `quarantined_columns` | pass | detected | inject fwd_mfe_5 into the board frame's column list |
| `keep_first_key` | pass | detected | duplicate one board row on its full effective key |
| `pit_footprint_availability` | pass | detected | declare a pick on a full-history name as having no footprint (must classify UNEXPLAINED) |
| `detector_vs_zt_pool` | pass | detected | switch off 5% of the detector's board flags |
| `definition_stream_disjointness` | pass | detected | add a pooled 'ALL_STREAMS' key to an output table |
| `window_extension` | pass | detected | move the edge across a real limit-width rule change (2019) |
| `stop_ship_reference_scan` | pass | detected | introduce a withdrawn-artifact reference into a scanned surface |
| `pin_line_numbers_resolve` | pass | detected | shift a pinned line number by +5 (simulates a W-P0 edit above it) |
| `window_trim_is_output_only` | pass | detected | probe a date with no panel row (no footprint can be proven finite) |

**Detector cross-check.** On the 38 sessions where `china_zt_pool` and the footprint plane both have coverage, 949 pool rows fall inside the footprint universe and the tolerant detector agrees on 947 of them — recall **99.79%**. The 2 misses: `000811.SZ @ 2026-06-25`, `001289.SZ @ 2026-06-26`. One-directional by construction. `china_zt_pool` is a PARTIAL vendor pool (its `asof` postdates its `date`), so this measures the detector's RECALL on the pool's own rows and is NOT a precision test — a detector board absent from the pool is not evidence of a false positive.

**Footprint availability exceptions.** 2 of 1485 board rows have no W-P0 footprint, and every one classifies into a W-P0 gate (0 unexplained): `603194.SS @ 2026-08-04 [cn_prophet_v2] :: below_w1_min_history_400_bars(n=395)`, `688411.SS @ 2026-06-30 [legacy] :: below_w1_min_history_400_bars(n=372)`. That is the pinned definition declining to measure a name with too little history, not a data gap — and the check fails if any exception cannot be classified, so 'few missing' is not what earns the pass.

**Effective keep-first key.** `board.parquet` is keyed on `date + ticker + board_definition` and `candidates.parquet` on `stamp_date + ticker + board_definition` — zero duplicates on either. `(date, ticker)` alone is **not** the key: 1 same-day cross-definition collision(s) exist — `002755.SZ @ 2026-08-11 :: cn_prophet_v2_shadow + cn_prophet_v3`. (date, ticker) is NOT the key — the same ticker legitimately appears on one session under two definitions, each carrying its own rank. P-A1 never de-duplicates across definitions: a collision row is counted once inside EACH of its own streams and never pooled.

## 7. What this does NOT establish

- NO selection skill. That the panel's names carry a footprint, or that some later printed a board, says nothing about whether the panel SELECTED them well. This artifact contains no comparison against any non-panel baseline — not the market, not a matched cohort, not a random draw of names with the same footprints. Without a comparison arm, an incidence count is a description of the panel and nothing more.
- NO lift, no significance, no interval, no effect size. None is computed, and none may be inferred by dividing two numbers in this file. The panel is 27 sessions of a single era, entirely in-sample of the current regime; the genesis stream is frozen at 5 sessions. Those honest-Ns cannot support inference and the charter forbids attempting it until the P-A2 accrual gate opens (>=120 sessions AND >=2 regime segments on a SINGLE stream).
- NO cross-stream comparison. The five definitions are five instruments. That one stream shows more of something than another is a statement about two different measuring devices observed over different, short, non-overlapping windows.
- NOTHING about the withdrawn W1-W3 constructions. This artifact cites no number and no artifact from them (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT; grep-verified in verify.stop_ship_reference_scan).
- NO price or return claim for any named episode, including the worked example. Board incidence here is an EVENT count from the tolerant detector; the case study's price/return claims remain withdrawn under their own stamp.
- NO resolution of the two ledgers' disagreement. Where the board surfaced a name the gate blocked, both readings are printed and neither is corrected. The write path owns that defect.
- NO extrapolation beyond the survivor slice. The footprint plane is W-P0's curated large-cap survivors; delisted names are absent from it, so every count here is measured on names that lived.
- NO claim that a footprint CAUSES a board, in either direction, and no claim that the engine's stamp or the W-P0 footprint is the correct one where they diverge. Divergence is reported as data.

## 8. Amendments — every deviation declared

Deviations from a bare W-P0 invocation. All mechanical; none touches the oracle math, which is imported rather than re-derived.

**A1 — Forward evaluation edge extended from W-P0's 2026-08-07 audit edge to 2026-08-11.**

- why: P-A1 must read picks made on 2026-08-10 and 2026-08-11, which lie beyond W-P0's edge. The store reaches 2026-08-11.
- controlled by: verify.window_extension — proves no limit-width rule differs between the two edges and that the store actually reaches the new one. No footprint definition is touched.

**A2 — Panel OUTPUT rows trimmed to sessions on/after 2026-05-01.**

- why: P-A1 needs the full market cross-section only on and around the 27 panel sessions; carrying 15 years of rows would cost memory and change nothing.
- controlled by: verify.window_trim_is_output_only — W-P0 computes every rolling footprint on each name's FULL series before applying this filter, so the trim cannot move a value; a finite 250-session drawdown inside the trimmed frame proves it.

**A3 — Chips (S5b winner/trajectory) join skipped — attach_conditioners is called with chips=None.**

- why: The charter's footprint list is washout / confluence / sector. S5b is neither and is not read anywhere in this artifact.
- controlled by: W-P0's own None branch sets the S5b bands to 'na'; no S5b column appears in any table here.

**A4 — Board incidence is reported as a three-way censoring status alongside W-P0's own fb_H flag, rather than as fb_H alone.**

- why: fb_H requires win_ok_H, so a board that DID occur inside an incomplete window reads as False. On the worked example that would have turned an observed board into a null.
- controlled by: The trichotomy reads only W-P0's own `lu` flags (an index scan over an already-computed detector output, not a second detector), and W-P0's fb_H / win_ok_H counts are printed beside it in every table.

## 9. Provenance

| stamp | value |
|---|---|
| `base_sha` | `09765e8cbc90b9868ff786ab7cf25fbdefe9b281` |
| `build_head_sha` | `09765e8cbc90b9868ff786ab7cf25fbdefe9b281` |
| `board_store_commit` | `ef11a6472da6734cd7f49b3d241bf766cca58d1b` |
| `candidates_store_commit` | `ef11a6472da6734cd7f49b3d241bf766cca58d1b` |
| `raw_store_commit` | `ba925156a174130613de33acdb3cf6814494f068` |
| `zt_pool_commit` | `ef11a6472da6734cd7f49b3d241bf766cca58d1b` |
| `w1_pin_commit` | `b50cf9461be794f3190b0bc985a35f6dfb3078d1` |
| `w1_sha256` | `11ac61de71f0f595e618f6f152dcea2334370d34cb736df919fb7127f1325cbf` |

Every store stamp is verified to be an ancestor of the build head before this file is written (the A4 provenance guard); a checkout that moved mid-run refuses to write rather than emit polluted provenance. Consecutive runs of this instrument are byte-identical — no wall-clock value enters either receipt.

Pinned definitions: `washout_onset_w1.py` @ sha256 `11ac61de71f0f595…`, imported. Inherited limits travel with the pin: the footprint plane is a curated large-cap **survivor** slice (delisted names absent), and `china_stocks_raw` is **back-adjusted**, which is the measured source of the detector's residual misses above.

