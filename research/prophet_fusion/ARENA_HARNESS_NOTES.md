# Arena harness — usage notes (PR-1a skeleton)

`WS:PROPHET-CONDITIONAL-FUSION`. Binding spec:
`research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md` §5.1 (family registry),
§7 (frozen outcomes), §8.3 (metrics), §8.5 (frames), §9 (validation protocol).

**Zero authority.** Research tier. Read-only over committed stores, no `data/` or
`site/` writes, no ranker import. There is no model in PR-1a — the challenger slot
holds a deliberate no-op, and every number it produces is stamped
`dummy: true, non_promotion_bearing: true` at the point of production. Nothing here
may be quoted, promoted, or cited as a result.

## Files

| Path | What it owns |
|---|---|
| `scripts/prophet_fusion_labels.py` | the frozen §7 outcome frame + era hygiene + the pooling law |
| `scripts/prophet_fusion_arena.py` | registry reader, PIT gate, folds, normalizer, coverage, dummy run, CLI |
| `research/prophet_fusion/families.yml` | the §5.1 registry — **the law** (sibling deliverable) |
| `tests/test_prophet_fusion_labels.py` | 27 tests — every label refusal, the frozen thresholds |
| `tests/test_prophet_fusion_arena.py` | 55 tests — every §9 rule, with mutation receipts |

## Commands

```bash
python3 -m scripts.prophet_fusion_arena --selftest          # end-to-end proof, exit 0/1
python3 -m scripts.prophet_fusion_arena --survey            # honest depth on the real frame
python3 -m scripts.prophet_fusion_arena --check-registry    # families.yml is lawful
python3 -m scripts.prophet_fusion_labels --frame board_ledger --json
python3 -m pytest tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py -q
```

`--out` defaults to the system scratch dir and **refuses** any path inside `data/` or
`site/`. Artifacts written: `arena_receipt.json`, `coverage.csv`.

## What the harness refuses, and why each refusal exists

Every one is a typed error carrying the offending name — never a warning, never a
silently narrowed frame.

| Refusal | Fires when | Spec |
|---|---|---|
| `StoreEmptyRefusal` | a store is absent or has zero rows | §4.0 — the keystone `us_prophet_rank/grades` store is empty TODAY; an empty frame still produces quotable numbers |
| `LabelUnitsRefusal` | `excess_spy` looks percent-scaled (\|p99\| > 3.0) | every §7 threshold is a fraction (`0.10 == +10pp`); a 100× unit error looks plausible and makes every tail read meaningless |
| `PriceBasisPoolRefusal` | >1 `price_basis` era is treated as one population | §9.4 — raised at the point of POOLING, not at build; the frame always carries the stratum |
| `UnregisteredFeatureRefusal` | a feature column is in no family | §5.1 — this is what makes the registry the law instead of documentation |
| `ForbiddenCompositeRefusal` | a blended composite is requested as a feature | §5.2 — names the decomposition the caller must use instead |
| `PITRefusal` | a `snapshot_not_pit` / `forward_only` member enters a **backtest** frame | §9.1, §4.2 — a snapshot join writes today's knowledge onto a historical row |
| `FoldRefusal` | a fold retains <60 train dates or <10 test dates after purge+embargo | §9.2 — the harness never silently shrinks a fold |
| `RegistryRefusal` | `families.yml` absent, mis-schema'd, or homes a column twice | §5.1 uniqueness is enforced by the reader, not by prose |
| `NormalizerRefusal` | transform-before-fit, re-fit, unknown method | §9.1b — a re-fit is how a full-sample statistic reaches a feature |
| `OutputPathRefusal` | `--out` resolves inside `data/` or `site/` | house law: research tooling never writes a tracked store |

## The §9.2 refusal is the acceptance behaviour, not a bug

The graded frame is **24 distinct dates** and the longest graded horizon is 21, so the
embargo is 21 and every fold refuses:

```
$ python3 -m scripts.prophet_fusion_arena --survey
survey frame=board_ledger rows=4075 dates=24 horizons=[5, 10, 21] folds_usable=0
  folds_refused=3 (embargo=21, min_train=60)
  REFUSED fold 0 refused (§9.2 minimum-usable-fold): 0 train dates after purge+embargo
  (minimum 60) and 4 test dates (minimum 10), at horizon=21 embargo=21 over 24 distinct
  dates. The harness refuses the fold; it never silently shrinks one.
```

This is §8.7 power honesty made mechanical: today's frame *cannot* be folded at the
chartered horizons, and the harness says so rather than bending a parameter. The
end-to-end proof therefore runs on a **synthetic 150-date fixture** — `--selftest` —
which exists solely because the real frame is too shallow to exercise the machinery.

## Design decisions where the masterplan was silent

1. **The session grid is the frame's own sorted distinct dates.** The graded dates are
   a subset of trading sessions, so moving *k* positions in the frame spans ≥ *k*
   sessions — a purge measured in frame positions removes at least as much history as
   one measured in sessions, never less. Conservative in the safe direction, and
   `build_folds(dates=…)` accepts a fuller grid when a caller has one.
2. **Embargo defaults to the longest horizon graded *in the frame*, not the scoring
   horizon.** §9.2 says "≥ the longest horizon graded in the fold". Scoring at the
   chartered H=10 while the frame carries H=21 rows still embargoes 21, because the
   H=21 labels are the ones that straddle.
3. **`test_size` defaults to the largest block that still leaves 60 train dates.** A
   frame that can be folded is folded generously; a frame that cannot is refused with
   the honest counts rather than shaved to fit.
4. **Pooling is checked at consumption, not at build.** The label frame always carries
   `price_basis`; `assert_poolable()` is what refuses. The era violation is "a
   statistic was computed across two eras", not "the frame contains two eras".
5. **Refusal order at the gate: forbidden composite → unregistered → PIT status.**
   Registering a forbidden composite must not launder it, and an unregistered column
   has no `pit_status` to judge. Pinned by
   `test_registering_a_forbidden_composite_does_not_launder_it`.
6. **A registered column absent from the frame is 0.0 coverage, counted separately as
   `n_columns_absent`.** Excluding it would let a family score full coverage on the one
   column that happens to be present.
7. **The PIT gate is frame-kind aware.** `snapshot_not_pit` is refused in a `backtest`
   frame and admitted in a `live` one — a live read has no future to leak. The default
   is `backtest`.
8. **`board_definition` joins when both sides carry it.** The board ledger has no such
   column (measured); the receipt discloses it as absent rather than filling it.
9. **Label key excludes `lane`.** A name in two lanes on one night is one outcome, not
   two (measured: 2 such pairs in `retro_grades` on 2026-07-29). Keep-first mirrors the
   candidates store's own dedupe law; the count is in the receipt.
10. **O3 tails are computed at every horizon but flagged `tail_registered_read` only at
    H=21/63.** §7 registers the read there; the rest is exploratory and says so.
11. **The selftest uses a synthetic registry.** `families.yml` is a sibling deliverable
    in the same PR, so binding the proof to its contents would make this harness's
    verdict depend on that file's timing. The real registry's status is reported in the
    selftest receipt regardless, and `test_the_shipped_registry_loads_and_is_lawful`
    asserts it — no skip.

## Deferred heads — reported, never proxied

* **O4 Entry quality** — owned by Live Entry Radar (#5578 §10). This program defines no
  rival entry outcome. The `fwd_mdd`-before-`fwd_mfe` stand-in an earlier draft carried
  was itself a rival outcome and is withdrawn.
* **O6 Confidence calibration** — no printed-confidence band accrues yet, so the head
  has no ruler and may not move rank.

Both appear in `receipt["deferred_heads"]`, and
`test_deferred_heads_are_reported_and_never_proxied` asserts no entry- or
confidence-shaped column exists in the label frame at all.

## Metrics are diagnostics, by construction

§8.3 requires the primaries on the **deployed composition** — the challenger's score
substituted into the same stage-bucketing, vetoes and `(stage_rank, −score, ticker)`
sort the champion uses, because a majority of cross-bucket raw-score comparisons
contradict the published order (§6.7.1). PR-1a has **no composition stage**, so what
`score_by_date()` emits is the pure-score-order diagnostic §8.3 explicitly demotes. The
output carries `composition: "raw_score_order"`, `deployed_composition: false`, and a
note saying so. Wiring the deployed composition is PR-1b+ work.

Scaffolded: P@1/3/5/10, top-K mean and median excess, large-loser rate (top-10 below
−10pp), all date-grouped. **Not yet built:** lead time, turnover/Jaccard, calibration
and Brier, MFE/MDD medians on the top-10, capacity budget `p_eff`, name-permutation
null, beta/size/vol-neutralized variants. Those arrive with the rung that needs them
(§9.5 binds them from C3 upward).
