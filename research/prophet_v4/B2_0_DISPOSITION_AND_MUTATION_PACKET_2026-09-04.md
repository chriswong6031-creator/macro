# B2-0 — the B-15..B-19 disposition & mutation packet (frozen 2026-09-04)

Operation `prophet-entry-truth-b2-0-disposition-mutation-20260903-sol-001` · wave `b2`
of `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md` (B2/B3/B4 execute jointly under
WS:PROPHET-US-ENTRY-TIMING per the wave-graph rulings).

**What this packet is.** A records/research + discriminating-tests surface: the exact
disposition matrix for launch-review findings B-15..B-19 with deterministic
classification, correction/supersession lineage, point-in-time replay, and fail-closed
mutation controls. **No authority changes hands**: nothing calls the new module from
`select_candidates` / `originate_plans` / `union_admission` / the reconciler or any
product surface, and a tree-scan test pins that boundary
(`tests/test_prophet_b2_disposition.py::test_no_engine_scripts_app_or_lib_module_imports_the_disposition_matrix`).

Code of record: `engine/prophet_b2_disposition.py` (pure stdlib, no file writes, no
imports of `prophet_bridge`/`us_early_turn`, mirroring the discipline of
`engine/us_candidate_episode.py:1-6`). Suite: `tests/test_prophet_b2_disposition.py`
(16 tests). CI: a new additive step in the `prophet-anticipation-intake` job
(`.github/ci/legacy-jobs.yml`), beside the union-admission step whose pins the matrix
cites.

## The two-pin citation law

Every matrix row carries **both** citations:

* **audit pin `edaf501ae7e4e1547e6124d50dd1b59e3cb17954`** — the readiness review's own
  line refs (PR #5370 head at review time). These line numbers are **stale by design**:
  `research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md:212-217` records that
  B-15..B-19 "remain the independent audit findings against `edaf501a…`; they are not
  current-main status assertions". They are never rewritten into HEAD coordinates.
* **HEAD pin `fdaf40910809de8da38e91c4696abfa22d2199e0`** — every HEAD-side citation
  below was re-read at this exact commit by this packet's author before baking, and
  every `PROVEN_CLOSED` cites a discriminating run actually executed at this commit on
  a clean tree (transcripts in §Verification below). Code reading alone never grants
  `PROVEN_CLOSED`.

## The rule table

| Rule | Value |
|---|---|
| Classes (issue #6805, verbatim) | `PROVEN_CLOSED`, `BUILT_NOT_PROVEN`, `STILL_LIVE`, `SUPERSEDED_BY_ACCEPTED_OWNER`, `REJECTED_BY_DESIGN`, `UNKNOWN_EVIDENCE_REQUIRED` |
| Rule lineage | `DISPOSITION_RULE_VERSION = "b2-disposition-v1-2026-09-04"` (modeled on `UNION_ADMISSION_ERA` / `DEFAULT_DEFINITION_ERA`); stamped on **every** outcome, including the synthesized pre-evidence one |
| Totality | `disposition()` is total over `("B-15","B-16","B-17","B-18","B-19")`; any other id ⇒ `DISPOSITION_UNTOTAL` error, never a default |
| FUTURE_KNOWLEDGE | replay at `as_of` sees only records with `known_at <= as_of`; a record learned later can never leak backward; no knowable record ⇒ `UNKNOWN_EVIDENCE_REQUIRED` (never silently closed) |
| Append-only | `supersede()` returns a new matrix; prior records are read-only (mappingproxy) and stay retrievable at their own `as_of` after any supersession |
| Chain law | per finding: seq 1 root, gapless `seq = head+1`, `supersedes = head`, `known_at` never backdated — any violation ⇒ `CORRECTION_CHAIN_BROKEN` |
| Fail-closed guards | missing/None owner ⇒ `OWNER_UNKNOWN`; missing `known_at` ⇒ `SOURCE_UNKNOWN`; foreign `rule_version` ⇒ `RULE_VERSION_UNKNOWN`; lineage gap/fork/backdate ⇒ `CORRECTION_CHAIN_BROKEN`; each seeded and proven by a discriminating test |

## The frozen v1 matrix

All five records: `owner = WS:PROPHET-US-V4-RECOVERY.b2`, `known_at = recorded_at =
2026-09-04`, `seq = 1`, `supersedes = null`, rule version as above.

| Finding | Disposition | Audit-pin citation (`edaf501a…`, line refs stale by design) | HEAD citation + discriminating run (`fdaf4091…`) |
|---|---|---|---|
| **B-15** open-bucket union repaint | **PROVEN_CLOSED** | readiness doc `:184` — PR #5370 admits on the still-open 3D bucket; STLD 8→4 live fires, NEM 20→7; audit refs `engine/us_early_turn.py:651-653, :835, :1102-1103` | heal: `engine/us_early_turn.py:662-696` `_completed_bucket_mask` applied `:721-722`. **Run:** `test_a_live_fire_never_disappears_or_re_dates_itself[STLD]` + `[NEM]` PASSED (150-session walk-forward; `7 passed in 19.21s`; full file `80 passed in 27.13s`) |
| **B-16** schema/manifest consistency | **PROVEN_CLOSED** | readiness doc `:185` — conditional `early_signal_dates` registered ALWAYS-PRESENT, `schema_version` unbumped, manifest stale; audit refs `engine/signal_quality.py:937-949`, `scripts/export_signal_contracts.py:170-180, :223`, `.github/ci/legacy-jobs.yml:2172` | heal: `scripts/export_signal_contracts.py:231-245` (v1.3.0 + `optional_fields=[early_signal_dates]`), pairing validator `scripts/validate_signals.py:153-197`. **Runs:** gate command green + regeneration byte-diff identical (§Verification legs 1-2); live census 245/246 carry the stamp, `SATS.json` lawfully omits it |
| **B-17** deck ≠ measured object | **STILL_LIVE** | readiness doc `:186` — shipped deck is union ∩ `select_candidates` while the 60.6% / 12-session numbers are naked-union; audit refs `engine/prophet_bridge.py:4018, :4318-4319, :1127-1132`, `engine/us_early_turn.py:1096-1099` | **measurement leg OPEN**: readiness `:211-217` ("does not close J-16/B-17") + `:841-847` (§8.1 claim 1 SUSPENDED); no re-measurement artifact exists at HEAD. **disclosure leg CLOSED**: `engine/us_early_turn.py:1196-1203` pinned by test `:598-609`, PASSED — strings only, cannot close the measurement |
| **B-18** deck ⊉ plan + null era | **PROVEN_CLOSED** | readiness doc `:187` — 114 STLD sessions `fired=True, deck_admitted=False`, `admission_era: None`; audit refs `engine/us_early_turn.py:1047-1058, :1102-1103`, `engine/prophet_bridge.py:4181-4182` | heal: `engine/us_early_turn.py:1186-1218` — absence-not-nulls confirmed lane, unconditional `admission_era: UNION_ADMISSION_ERA` at `:1211`, `deck_admitted: True` `:1218`. **Run:** tests `:526-539`, `:542-567` (120-session non-vacuous sweep), `:570-577` all PASSED |
| **B-19** dead-fire chase verdict | **PROVEN_CLOSED** | readiness doc `:188` — chase verdict fires off a dead union fire on every plan incl. confirmed-lane `buy_now`; audit refs `engine/us_early_turn.py:948`, `engine/prophet_bridge.py:300-302, :4536-4569` | heal: `engine/us_early_turn.py:1024-1039` — chase leg gated at `:1031` on `fired` AND `fire_date`. **Run:** test `:580-595` `test_a_dead_fire_never_emits_a_chase_chip` PASSED |

### Promote/demote conditions

* **B-17 → PROVEN_CLOSED** (the only promote owed): a frozen re-measurement of the
  shipped `union ∩ select_candidates` roster's coverage/lead on the bake-off panel,
  appended as a superseding record (`seq 2, supersedes 1`). Until then §8.1 claim 1
  stays SUSPENDED and no product copy may quote the naked-union numbers as the deck's.
* **B-15/B-18/B-19 demotion path**: these closures are proven on the committed
  STLD/NEM fixtures in a local run (py3.14.7, macOS, pytest 9.1.1). If the CI
  re-proof (the union-admission step this packet's new step sits beside) ever goes red
  at a descendant of `fdaf4091`, the correct move is a superseding record demoting the
  row — never an edit of this one.
* **B-16 gate-sensitivity note** (recorded, not a leg): `check_contract_drift.py`
  samples only the FIRST wildcard file, and `site/signals/AAPL.json` now carries
  `early_signal_dates` — so a planted pre-heal manifest (field REQUIRED) no longer
  re-reds the gate on today's tape (verified: planted run exits 0). The finding's own
  three legs (optional registration, version bump, manifest regeneration) are closed
  and proven; deepening the gate's sampling is future-wave work, not B2-0's.

## The five red-conditions and their discriminators

Each is a test that goes red if someone swaps in a naive "current-state as history"
reader (the naive answer is computed inside the test and asserted to differ), or
weakens a fail-closed guard. All in `tests/test_prophet_b2_disposition.py`:

1. **Correction after the cut** — `test_red_condition_corrected_after_cut_does_not_alter_replay_at_the_cut`
   (a `CORRECTED` event with `known_at` after a decision cut leaves replay at that cut
   byte-identical; the current-only projection provably differs).
2. **Retracted trigger** — `test_red_condition_a_retracted_trigger_does_not_remain_active`
   (a `RETRACTED` trigger vanishes from the projection; a reader that drops RETRACTED
   events provably resurrects an ACTIVE row).
3. **Identity supersession** — `test_red_condition_identity_supersession_fails_closed_for_stale_identity_reads`
   (`superseded_by` never leaks before its `known_at`; a ratified — non-provisional —
   identity refuses supersession outright with `EpisodeContractError`).
4. **Backward leak** — `test_replay_reproduces_the_earlier_answer_after_a_supersession`
   (after a t2 supersession is appended, `as_of=t1` still reproduces the t1 answer, and
   `as_of < t1` sees nothing — FUTURE_KNOWLEDGE).
5. **Silent default to closed** — `test_no_record_knowable_at_as_of_is_never_read_as_closed`
   (no knowable record ⇒ `UNKNOWN_EVIDENCE_REQUIRED` with empty evidence, stamped with
   the rule version).

Red-conditions 1-3 run against the B1 core (`engine.us_candidate_episode`, imported
read-only) on tiny fixed-stamp in-memory fixtures — no clocks, no files.

## DO_NOT_REBUILD confrontation

B2-0 is a **records** packet: it computes no signal, admits no name, sizes nothing,
and renders nowhere. The three adjacent kill rows are confronted by name:

* **`DNR:KILL-WASHOUT-TURN`** (`research/DO_NOT_REBUILD.md:85` — the 2W washout×turn
  operator seed died in test; entry-stack Amendment-3, #1747). Not engaged: B2-0 builds
  no washout/turn detector and grants no promotion of any Radar/entry detector; it only
  RECORDS the disposition of findings about the already-shipped union admission.
* **`DNR:KILL-FRESH-TICKS-WINDOW`** (`:126` — FRESH_TICKS widening killed on a frozen
  third-look replay; `FRESH_TICKS=2` stands). Not engaged: B2-0 touches no admission
  window, no tick count, and none of the mirrors (`us_board_rank.py:84`,
  `check_board_contradictions.py:49`, `build_stock_library.py:4513`).
* **`DNR:KILL-PROPHET-POP-MERGE`** (`:55` — no data-lane merge of Top-setups into the
  graded board; presentation-tier merge is the ratified form). Not engaged: B2-0 writes
  no board artifact, alters no graded population, and introduces no blended ranking —
  the module is import-dead to every producer by tested law.

## Freeze-premise recheck (recorded honestly)

The freeze premise said the latest natural B1 run reported `MISSING_SOURCE_FILE` for
Radar. Re-checked at `fdaf4091`: **every `engine/entry_radar/*.py` cited path
resolves** (19 modules present, `__init__.py` through `vendor_minutes.py`). The absent
paths are the V4-B7 UI templates — `templates/entry_radar.html.j2` and
`site/entry_radar.html` do not exist at HEAD — which are Radar-owned future work, not
missing evidence. B2-0 fabricates nothing on that basis.

## Verification transcripts (2026-09-04, clean tree at `fdaf4091`)

**B-16 leg 1 — the gate command itself** (`python3 scripts/check_contract_drift.py`,
the same command as `.github/workflows/ci-main-heartbeat.yml:96-97` hard-fail and the
pack-lane twin `.github/ci/legacy-jobs.yml:4310-4336`):

```
contract drift: 0 drift(s), 10 clean, 1 skipped (no live sample)  [11 entries total]
exit 0
```

**B-16 leg 2 — regeneration state** (`export_signal_contracts.build_manifest()` vs
committed `site/factordata/contracts/artifact_manifest.json`):

```
committed entries=11 regen entries=11
artifacts arrays byte-identical (canonical json): True
non-as_of top-level keys identical: True
committed per_stock_signal: schema_version=1.3.0 optional_fields=['early_signal_dates']
```

**B-16 leg 3 — planted pre-heal probe** (registration flipped back to REQUIRED in a
scratch copy, gate re-run on the live tree): exits **0**, because the first-sampled
`site/signals/AAPL.json` now carries `early_signal_dates` — the 2026-08-11 audit's
"none of 241 carry the field" is no longer true (census: 245/246 carry it; `SATS.json`
omits it, which is exactly why OPTIONAL is the lawful registration). Recorded as the
gate-sensitivity note above.

**B-15/B-18/B-19/B-17-disclosure pin tests, node level:**

```
tests/test_us_early_turn_union_admission.py::test_a_live_fire_never_disappears_or_re_dates_itself[STLD] PASSED
tests/test_us_early_turn_union_admission.py::test_a_live_fire_never_disappears_or_re_dates_itself[NEM] PASSED
tests/test_us_early_turn_union_admission.py::test_a_confirmed_lane_row_carries_no_early_lane_block_at_all PASSED
tests/test_us_early_turn_union_admission.py::test_every_union_fire_is_a_deck_row_and_every_plan_is_a_deck_row PASSED
tests/test_us_early_turn_union_admission.py::test_the_era_stamp_is_present_exactly_on_the_early_lane PASSED
tests/test_us_early_turn_union_admission.py::test_a_dead_fire_never_emits_a_chase_chip PASSED
tests/test_us_early_turn_union_admission.py::test_the_shipped_deck_is_not_claimed_to_be_the_naked_universe PASSED
7 passed, 151 warnings in 19.21s
```

**Neighbor suites (no-regression + promote-condition evidence):**
`python3 -m pytest tests/test_us_candidate_episode.py
tests/test_us_early_turn_union_admission.py -q` → `80 passed, 198 warnings in 27.13s`,
exit 0.

**This packet's own suite** — RED first (module absent):
`ModuleNotFoundError: No module named 'engine.prophet_b2_disposition'` (exit 2); then
GREEN: `16 passed, 198 warnings in 2.48s`, exit 0.

## Spec-divergence note (evidence-true over spec-true)

The commissioning spec's provisional classes for B-15/B-18/B-19 were
`BUILT_NOT_PROVEN` "with a reason naming what would promote it to PROVEN_CLOSED (a
green run of the walk-forward ghost test at exact HEAD)". Those promote-conditions were
**met during this packet's own verification** — the named discriminators were RUN at
exact HEAD on a clean tree and passed (transcripts above) — so freezing
`BUILT_NOT_PROVEN` would have baked an already-satisfied promote-condition, which is
evidence-false. Per the spec's own override ("encode what YOU verified — the matrix
must be evidence-true, not spec-true"), the rows are `PROVEN_CLOSED` with the runs
cited and a demotion path recorded. B-17 stays `STILL_LIVE` exactly as specified: its
measurement leg was not run, and nothing here claims otherwise.
