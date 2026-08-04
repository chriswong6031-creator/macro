# Context Vector — cross-market schema contract (US side)

**Status: JOINT-PENDING-CN-ADJUDICATION.** This note fixes the **US** side of the
contract only. The CN lane owns CN files; this lane owns US files; the contract
itself is joint and is not settled until the CN program adjudicates §3 below.
**No CN file was edited to produce this note** (roadmap §8 fence).

Origin: `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §7 requires CN
and US context vectors to stay "one schema family with market-specific axes". A
census on 2026-08-04 (grep for `context_vector`, `schema family`, `co-adjudicated`,
`contract note` across `research/` and repo-wide) found **no existing joint contract
note** — §7 is prescriptive, not a record of an agreed document. Its cited sibling,
`PROPHET_CN_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md`, is not in this checkout either.
So this is the first draft of the US half, written to be conformed to, not imposed.

---

## §1 What each market ships today

| | CN | US |
|---|---|---|
| Store | `data/china_prophet_rank/candidates.parquet` | `data/us_prophet_rank/candidates/YYYY-MM.parquet` |
| Producer | `engine/china_prophet_shadow.py` | `engine/us_context_vector.py` |
| Since | 2026-07-30 | 2026-08-04 (this PR) |
| Shape | 5,881 x 88 (4 nights) | 1,540 x 150 (1 night) |
| Layout | one accreting file | monthly parts, read via `load_candidates()` |
| Stamp column | **`stamp_date`** | **`stamp_date`** |
| Keep-first key | `(stamp_date, ticker, board_definition)` | `(stamp_date, ticker, board_definition)` |
| Lane gate | `lane == "asia"` argument | `ledger_lane.nightly_advance_enabled()` |
| Board definition | `china_prophet_v2` | `us_prophet_v1` |

## §2 Agreed family invariants (both markets already satisfy these)

These are not proposals — both stores implement them today, and they are what makes
the two one family:

1. **Full universe, including ineligible names.** The store's value is that a name
   that did *not* make the board is present with its reason.
2. **Keep-first on `(<stamp>, ticker, board_definition)`.** A rerun never rewrites a
   night a user could already have seen.
3. **Schema-union append.** A column added later is null for prior nights and
   self-heals forward only; a retired column is preserved for the nights that had it.
4. **Itemized score legs, never a blend.** Both stores carry
   `prophet_<leg>` + `prophet_<leg>_points` per leg, read off the market's own
   ranker. Neither store recomputes or invents a leg.
5. **One lane advances.** CN gates on the asia collection lane, US on
   `COLLECT_LANE=nightly`. Different sentinels, same law.
6. **Zero authority at birth.** Neither store is read for scoring; both register with
   empty `consumers` in `config/synapse.yml`.
7. **Null means unmeasured, never false** (#4485).
8. **Fail-soft.** A broken context input returns 0 and never breaks the build.

## §3 Open divergences — for joint adjudication

These are the actual decisions. On the still-open items the US side states a
preference and will conform to whatever is adjudicated; **it does not act unilaterally
on any of them.** §3.1 is settled and recorded below with its date.

### 3.1 — ADJUDICATED 2026-08-04: `stamp_date` wins

The stamp column is `stamp_date` for the schema family. It is self-documenting where
`date` is ambiguous next to the event dates it sits beside in a joined frame (both
stores already carry several `*_asof` columns). **US ships as-is and does not change.**
The CN-side rename of `date` -> `stamp_date` is filed as its own task for the CN lane,
to be done while that store is still young — it is not a rider on this PR, and no CN
file was touched here.

Rationale for settling it now rather than later: this is the JOIN KEY. Every night both
stores accrue makes the rename more expensive, and until it lands a cross-market study
must special-case per market or alias on read — exactly the shape contamination §7
exists to prevent.

**LANDED 2026-08-04 (CN lane, PR TBD).** The CN rename shipped as its own CN-lane PR,
as filed above — no US file was touched by it. It was a column rename with receipts and
no strategy, scoring, or lane-logic change: producer `engine/china_prophet_shadow.py`
(record key, `_OBJECT_COLUMNS`, the keep-first dedup subset, docstring), the candidates
read path in `engine/cn_prophet_audit.py::miss_funnel`, and a one-time in-place rewrite
of the committed store. The rewrite mirrored the writer's own whole-file
`to_parquet(index=False)` so the parquet's pandas schema-metadata was rebuilt rather
than left naming the old column, and was verified by re-reading from disk: 5,881 rows
and 88 columns before and after, `stamp_date` value-identical to the old `date` column,
`assert_frame_equal` clean on every other column, dtypes unchanged, and per-night counts
identical across all four nights (2026-07-30 1,472 / 07-31 1,469 / 08-03 1,471 / 08-04
1,469). Three neighbouring `date` schemas were deliberately NOT renamed, because they
are separate artifact contracts with their own readers: the audit's forward log
(`data/cn_prophet_audit/forward_log.parquet`, keep-first per `(date, board_definition)`),
the `china_standout_track` board store, and the `by_date[].date` key in the audit's
published `data/cn_prophet_audit/latest.json`. Regression pin:
`tests/test_cn_prophet_candidates_schema.py` (committed-store schema + writer output),
running in the `unrun-picks-boards` CI pack.

### 3.2-3.5 — still open

| # | Divergence | US preference | Cost of the split |
|---|---|---|---|
| 3.2 | **Leg names**: CN `(signal, entry, runway, bottom_quality, reversal_member)` vs US `(signal, entry, edge, runway, quality)` | Keep divergent — these are genuinely market-specific axes, which §7 explicitly permits. `signal`/`entry`/`runway` already agree | Low. A joiner reads `prophet_*_points` as a per-market block |
| 3.3 | **Context block**: US carries 82 `neuralweb.context_api` columns (`<dim>__<field>`); CN carries none | CN adopt `context_frame` if/when its cost is acceptable on the asia lane. US measures 0.0675 s/name after the insider-panel memo (2026-08-04) | Medium — the US store answers questions the CN one cannot |
| 3.4 | **Lane-gate mechanism**: CN passes `lane=` as an argument; US reads the env sentinel via `ledger_lane` | Converge on `engine/ledger_lane.py` — it already defines BOTH markets' gates (`nightly_advance_enabled` / `asia_advance_enabled`) and is a leaf module | Low, but the CN form lets a caller pass the wrong lane; the env form cannot be spoofed by a caller |
| 3.5 | **Coverage disclosure**: US stamps `context_dims` per row; CN has no equivalent | Adopt per-row disclosure wherever a block can be thinned | Low |
| 3.6 | **Storage layout**: US writes monthly parts (`candidates/YYYY-MM.parquet`), CN one accreting file | **Not a schema question — explicitly out of scope for this contract.** Layout is a per-market storage idiom; the COLUMNS are identical either way, so the family is intact. US partitioned because a git-tracked whole-file rewrite costs `S x N(N+1)/2` of history (3.2-14.7 GB in year one) against `12 x S x 231` for parts (0.27-1.28 GB). CN carries the same exposure and the same remedy is available to it, but that is the CN lane's call | None to the schema; the reader helper hides it |

## §4 US field contract v1

Namespace convention: block-prefixed snake_case (`theme_`, `relay_`, `regime_`,
`turnover_`), except the Context Snapshot columns, which keep the canonical
`<dimension>__<field>` names `context_api` itself emits — a column's name should say
which producer owns it.

- **identity/board** — `stamp_date`, `ticker`, `name`, `sector`, `board_definition`,
  `lane`, `eligible`, `buyable`, `tier_cascade`, `tier_sub`, `ticks`,
  `bars_to_cross`, `fresh_bars`, `gate_weight`, `gate_state`, `gate_reason`,
  `gate_provisional`, `htf_s1`, `htf_s2`, `near_miss_reason`, `signal_asof`,
  `stage`, `alpha`, `alpha_percentile`, `prophet_score`, `score_rank`,
  `display_rank`, `featured`
- **legs** — `prophet_{signal,entry,edge,runway,quality}` and `..._points`
- **theme** — `theme_membership_count`, `theme_membership_ids`, `theme_primary_id`,
  `theme_primary_name`, `theme_heat_rank`, `theme_label`, `theme_reco`,
  `theme_score`, `theme_bull_days`, `theme_clean_entry`, `relay_count_3d`,
  `relay_position`, `relay_members_covered`, `relay_basket_id`, `foresight_stage`
- **event** — `days_to_report`, `reports_within_7`, `post_earnings_move_pct`,
  `post_earnings_sessions_since`, `earnings_stale`, `in_blackout`,
  `eightk_recent_days`
- **flow** — `turnover_pctile_20d`, `turnover_window_20d`, `turnover_pctile_60d`
- **regime** (one value per night) — `regime_dispersion_state`, `regime_gate_go`,
  `regime_market_quad`, `regime_quad_name`, `regime_vol_regime`
- **risk** — `ext_z`, `antichase_shadow_blocked`
- **quality** — 82 `<dim>__<field>` columns over the 11 Context Snapshot dimensions,
  plus `context_dims`

Storage layout (monthly parts on the US side) is NOT part of this contract — see
§3.6. The field list above is what one schema family means; where the bytes sit is
each market's own call.

Per-column provenance, measured coverage and the three named debts live in
`data/us_prophet_rank/README.md`. The schema is pinned by
`tests/test_us_context_vector.py::TestSchemaContract`.

## §5 What this note does NOT do

No CN edits. No score, blend, or gate change in either market. No claim that either
store has authority — both are display/shadow tier until an axis clears the §3
bounded-authority ladder with its own preregistration. §3.1 was adjudicated 2026-08-04
(`stamp_date` wins) and is now DONE on both sides — the CN rename landed the same day in
its own CN-lane PR (§3.1). §3.2-3.6 remain open.
