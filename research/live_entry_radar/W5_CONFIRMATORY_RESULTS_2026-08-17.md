# W5 confirmatory Panel-A/B results (first non-empty §7 control arm)

**Status:** production runs completed 2026-08-16/17. **Scope:** results only — the
matching fix is already on main (#5780, `f8201036c139`). Git copies of the panel
JSON omit the per-row refusal lists (1.29M / 67k rows); counts below are from
those production files.

The 81 smoke looks of 2026-08-15T09:19–09:33Z stay in `data/trial_ledger.jsonl`
and remain void for interpretation.

## 1. Refusal census first

Broken-instrument signature (2026-08-15 smoke): `n_refusals=543` vs
`n_episodes=502`, essentially all `control_match_unavailable`.

| panel | n_refusals | n_episodes | refusals ≥ episodes? | `control_match_unavailable` |
|---|---:|---:|---|---:|
| A (this worktree, cache-only) | 1,292,516 | 7,546 | yes, but **not the defect** | **0** |
| B (post-fix sibling, same cache) | 67,534 | 212,593 | **no** (31.8%) | **0** |

Panel A’s 1.29M rows are gather coverage (`minute_refusal` wrapping
`minute_window_refused` / `c3_refusal` / `suppressed_by_rearm`), not the matching
blackout. Attach+match completed **7,546/7,546 in 42s**.

Panel B’s 67,534 rows are `g6_out_of_era` (67,496) + `no_staged_table` (38). The
pre-attach gather print was already 67,534 — attach added **zero** matching
refusals.

Verified: `rg -c control_match_unavailable` on both production JSON files = 0;
ledger `refusal_census` rows named above.

## 2. Recovered control-pool sizes

Per-episode `n_cell` / k were **not serialized** by `_write_results` (schema
gap). Observable proxy: `uninformative_no_control` is the `n_cell=0` (or no
admissible k-NN) share after a successful `controls.match` call — the pre-fix
path never reached `match` (it raised into `control_match_unavailable` and
stored `n_cell=0` via `matches.append(None)`).

| cell | n_episodes | uninformative_no_control_n | empty-cell share | implied matched share |
|---|---:|---:|---:|---:|
| A FIT C1 | 1,099 | 515 | 46.9% | 53.1% |
| A FIT C2A | 6,440 | 3,001 | 46.6% | 53.4% |
| B TEST G0 | 69,382 | 23,343 | 33.6% | 66.4% |
| B TEST C5 | 13,618 | 1,812 | 13.3% | 86.7% |
| B FIT G0 | 73,569 | 29,057 | 39.5% | 60.5% |
| B FIT C5 | 10,546 | 2,169 | 20.6% | 79.4% |

k is at most `prereg.CONTROL_K=5` on the matched subset. A k histogram was never
written.

**§9 proximity-overlap (`nc2_overlap`):** NaN on every confirmatory question.
Q1 never reached the NC-2 pair (M14 fail-closed). Q2 never reached it (§12
floors). Q5 does not emit an NC-2 pair. The unmatched `same_band_support` mean
has therefore still never been published as a number.

## 3. §7 / §10 reads

### Panel A (`info_cutoff` 2026-08-16T01:23:09Z)

- **Q2** `ACCRUING` — “§12 floors not met on an arm; look unspent.” TEST primary
  tables are n=1 (C1) and n=6 (C2A), all uninformative.
- **Q3** not executed — no common-eligibility C3/C2a rows.
- FIT tables **did** produce matched excess (first ever): C1 mean −1.78 pp
  (CI −3.65/−0.27, p=0.008, `eff_names`=11.87, `floors_met=true`); C2A mean
  −1.65 pp (CI −3.27/−0.34, p=0.010, `eff_names`=11.91, `floors_met=true`).
  These are FIT-era exploratory tables, not the confirmatory Q2 TEST contrast.

### Panel B (`info_cutoff` 2026-08-17T01:56:44Z)

- **Q1** `UNINFORMATIVE` — M14: row-16 G0 date agreement **69.86%** vs floor
  **90%**. Primary not computed. Expected fail-closed; `row16_agreement.json`
  already measured 0.6986 before this run.
- **Q4** `ACCRUING` — live-forward only; W4 spool not a historical reconstruction.
- **Q5** `PASS_SHAPED` (BH survives): G0 vs nearest incumbent signed gap mean
  **+13.43 sessions** (CI 12.25–14.22), n=54,538, n_names=2,673,
  `eff_names`=2,118, p=0.002. Guardrail `EQUAL_OR_BETTER` (false-start
  difference −5.4 pp, CI −7.9/−3.1).
- TEST G0/C5 primary tables: floors met, `eff_names` 2,311 / 1,537 (M3 floor
  is 8). Excess vs matched controls is negative at H=10 (G0 −0.91, C5 −0.68)
  with false-start rates ~41%.

## 4. M14 and M3 against real pools

- **M14** (`ROW16_AGREEMENT_FLOOR=0.90`): measured **0.6986** (12,846 matched /
  239 names, era 2011-01-03–2026-02-13). Q1/Q5 identity: Q1 refuse-closed as
  designed; Q5 is an incumbent-gap question and still graded.
- **M3** (`FLOOR_EFF_NAMES=8`): Panel-B TEST G0/C5 and FIT G0/C5 all
  `floors_met=true` with `eff_names` ≫ 8. Panel-A TEST primary fails (n_names=1).
  Panel-A FIT C1/C2A pass (`eff_names` ≈ 11.9).

## 5. Provenance

- Panel A: worktree `claude/w5-confirmatory-replay`, runner PID 16290,
  `--panel both` then died mid-B attach; A results written 2026-08-16T09:45Z
  local. Cache-only (`POLYGON_API_KEY`/`MASSIVE_API_KEY` emptied).
- Panel B: post-fix sibling PID 44804 in
  `live-entry-radar-w5-396a76` (`#5780` is an ancestor), `--p0-minute skip`
  (G0/C5 staged tables; P0 minute is a C1 path), 10-chunk attach, results
  written 2026-08-17T02:00 PDT. Looks appended to this tree’s ledger by hash
  (dedup against smoke + this tree’s A spend).
- Gates G-1..G-5 green on both runs.
- Full per-row A census retained off-git at `/tmp/w5_results_panel_A.full.json`
  on the build host (not a repo path).
