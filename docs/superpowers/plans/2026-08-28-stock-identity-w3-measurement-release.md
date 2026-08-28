# Stock Identity W3 Measurement Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first post-W2 Stock Identity measurement release: an executable expert-independent localization ruler, honest estimability/dependence census, and a terminated-instrument survivorship control status, with zero confirmatory fit/routing authority.

**Architecture:** Extend the existing `engine/stock_identity/` package rather than creating a second research framework. W3A creates deterministic ruler primitives over W1 episodes + W2 events; W3B computes support/estimability from those same canonical objects; W3S reuses current data owners to supply a bounded terminated-instrument control cohort or returns a typed hard blocker. No task opens Q1 outcomes, changes Prophet, writes Radar, or modifies sealed W1 partitions.

**Tech Stack:** Python 3, pandas/numpy/scipy where already present, parquet/json artifacts, existing `engine/trial_ledger.py`, existing Agent OS/CI patterns, pytest.

**Spec:** `research/stock_identity/STOCK_IDENTITY_COMPLETE_MASTERPLAN_2026-08-28.md` and `research/stock_identity/W3_FINAL_ARCHITECTURE_FREEZE_2026-08-27.md` on operation carrier Macro PR #6529.

## Global Constraints

- `DNR:KILL-OUTCOME-AUDITION` remains total; no per-name best expert/rank output exists in W3.
- Only existing W1 episodes/fingerprints/partitions and W2 historical expert events/attribution may feed W3A/W3B.
- W3A must remain expert-independent on the episode-definition side; `engine/stock_identity/episodes.py` may not import expert producers/replay modules.
- Frozen graded composite family is exactly `C-LOC-R` and `C-LOC-D`; any other composite is exploratory and must not enter W5 inputs.
- Honest N is distinct episodes plus distinct calendar clusters/blocks; raw fires/rows are never the headline N.
- Every output uses all-false Stock Identity authority from `engine/stock_identity/authority.py`.
- W3S must reuse current canonical adjusted-history owners first; it may not create a general second market-data plane.
- `data/massive_stock_day` remains prohibited for behavioral math.
- Sealed W1 calibration/blind manifests and W1-A1 GOLD/Barrick receipts remain byte/logically unchanged.
- No `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`, `engine/prophet_*.py`, `engine/stock_personality.py`, `engine/oracle/personality_context.py`, `scripts/build_stock_library.py`, or `engine/entry_radar/**` modification in W3.
- Channel A carries the original §2.3 capacity budget: effective parameter count `p_eff` is declared before any fit and must satisfy `p_eff <= N_names/10`; the functional form is additive/monotone in a declared feature subset unless a richer form is separately preregistered. W3 freezes this model constitution (Task 3B); no W3 task fits the map or opens Q1.
- The PR-3 ruler-composite constant family (`lambda_fs`, recall floor, declared composite constants) is NOT already frozen. It is set exactly once in Task 1B from `SI-SEALED-CAL-P1` under rule-before-value discipline (selection rule declared in code/doc BEFORE any value is computed from partition data), with exemplars and the untouched blind arm contributing nothing, declared ±20% diagnostic grids registered in the TrialLedger before execution, and the later fit-read look budget logged.
- W3 completion is a measurement release, not Q1, SIF, Prophet integration, or production trading authority.

---

### Task 1: Freeze the W3 ruler wire contract and failing fixtures

**Files:**
- Create: `engine/stock_identity/ruler.py`
- Create: `tests/test_stock_identity_ruler.py`
- Create: `data/stock_identity/ruler/ruler_spec_v1.json`
- Create: `research/stock_identity/W3_RULER_REGISTRATION.md`

**Interfaces:**
- Produces:
  - `RulerSpec.from_json(path: Path) -> RulerSpec`
  - `RulerSpec.spec_hash() -> str`
  - `validate_ruler_inputs(events: pd.DataFrame, attribution: pd.DataFrame, episodes: pd.DataFrame) -> None`
  - closed per-fire/per-cell metric column names (owned by `compute_fire_metrics` and its aggregations): `lead_lag`, `price_dist`, `atr_dist`, `mae_after`, `capture`, `false_start` (per-fire flag), `false_start_rate` (aggregate consumed by the composites), `flooding`, `recall_at_tier`, `zone_precision`, `relative_order`, `consistency`
  - closed unconditional-block column names (owned by `compute_unconditional_block`): `fires_per_name_year`, `episode_attribution_rate`
  - closed composite names: `c_loc_r`, `c_loc_d`

- [ ] **Step 1: Write the failing contract tests**

```python
from pathlib import Path
from engine.stock_identity.ruler import RulerSpec


def test_ruler_spec_has_only_two_graded_composites():
    spec = RulerSpec.from_json(Path("data/stock_identity/ruler/ruler_spec_v1.json"))
    assert spec.graded_composites == ("c_loc_r", "c_loc_d")


def test_ruler_spec_hash_is_stable():
    spec = RulerSpec.from_json(Path("data/stock_identity/ruler/ruler_spec_v1.json"))
    assert len(spec.spec_hash()) == 64
    assert spec.spec_hash() == RulerSpec.from_json(Path("data/stock_identity/ruler/ruler_spec_v1.json")).spec_hash()
```

- [ ] **Step 2: Run the tests and prove red**

Run:

```bash
python3 -m pytest tests/test_stock_identity_ruler.py::test_ruler_spec_has_only_two_graded_composites tests/test_stock_identity_ruler.py::test_ruler_spec_hash_is_stable -q
```

Expected: import/file failure because `ruler.py` / `ruler_spec_v1.json` do not exist.

- [ ] **Step 3: Add the minimal typed ruler spec**

Implement `RulerSpec` as an immutable dataclass containing only receipted constants: the previously frozen W1 geometry constants (attribution pre-window, useful-zone session/ATR bounds, false-start ATR threshold, ATR basis, grain labels, episode-type anchor mapping) plus the PR-3 ruler-composite family (`recall floor`, `lambda_fs`, any declared composite constants), which does not exist yet and is written exactly once by Task 1B. Until Task 1B runs, the PR-3 fields carry the explicit sentinel `{"status": "pending_sealed_calibration"}` — never a guessed number.

Canonical hash implementation:

```python
def spec_hash(self) -> str:
    payload = json.dumps(self.to_canonical_dict(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Encode the frozen JSON spec and registration receipt**

`ruler_spec_v1.json` must contain explicit numeric constants sourced only from the Task 1B one-time sealed-calibration receipt or previously frozen W1 constants (with the pending sentinel for PR-3 fields before Task 1B), plus `authority` all false and `graded_composites: ["c_loc_r", "c_loc_d"]`. `W3_RULER_REGISTRATION.md` records the source/hash of every constant and states that the blind arm was not opened.

- [ ] **Step 5: Run the contract tests**

Run:

```bash
python3 -m pytest tests/test_stock_identity_ruler.py -q
```

Expected: contract tests pass; later metric tests may still be absent.

- [ ] **Step 6: Commit Task 1**

```bash
git add engine/stock_identity/ruler.py tests/test_stock_identity_ruler.py data/stock_identity/ruler/ruler_spec_v1.json research/stock_identity/W3_RULER_REGISTRATION.md
git commit -m "stock-identity W3A: freeze localization ruler contract"
```

---

### Task 1B: One-time sealed-calibration constant-setting for the PR-3 ruler family

**Files:**
- Create: `scripts/stock_identity_calibrate_w3.py`
- Create: `tests/test_stock_identity_w3_calibration.py`
- Modify: `data/stock_identity/ruler/ruler_spec_v1.json`
- Modify: `research/stock_identity/W3_RULER_REGISTRATION.md`

**Interfaces:**
- Produces the one-time PR-3 constant receipt: `recall_floor`, `lambda_fs`, and any declared composite constants, each with its written selection rule, rule hash, input partition hash, and computed value.

- [ ] **Step 1: Declare every per-constant selection rule before any value exists**

Following the W1 `scripts/stock_identity_calibrate.py` rule-before-value law: each PR-3 constant gets an explicit written selection rule in `scripts/stock_identity_calibrate_w3.py` and `W3_RULER_REGISTRATION.md`, and the sha256 of the rule text is recorded in the registration BEFORE the script is ever run against partition data. A test asserts the registration carries the rule hash and that the JSON spec still holds the pending sentinel at this step.

- [ ] **Step 2: Register the declared diagnostic grids and the fit-read look budget**

Register the exact declared ±20% diagnostic sensitivity grids in the TrialLedger via `engine/trial_ledger.py` BEFORE execution, and log the W5 fit-read look budget in the same registration. Diagnostic grids are never used to re-pick a constant.

- [ ] **Step 3: Run the calibration once on lawful material only**

Input material is exactly the `SI-SEALED-CAL-P1` partition object per the W1 registration (drawn-name history; the recent-history guard honored). Pilot/exemplar and blind names contribute nothing. Tests assert the input name set is disjoint from the pilot cohort and the blind-arm manifest.

- [ ] **Step 4: Write constants exactly once with receipts**

The script replaces the pending sentinels in `ruler_spec_v1.json` with computed values, records value + rule hash + partition hash + timestamp in `W3_RULER_REGISTRATION.md`, and re-pins the final `spec_hash`. A second invocation must refuse (one-time law) — tested. No constant may thereafter change without voiding the affected preregistrations.

- [ ] **Step 5: Run the calibration test suite**

```bash
python3 -m pytest tests/test_stock_identity_w3_calibration.py -q
```

Expected: rule-hash-before-value receipts asserted; no pending sentinel remains; blind/pilot exclusion proven; re-run refusal proven.

- [ ] **Step 6: Commit Task 1B**

```bash
git add scripts/stock_identity_calibrate_w3.py tests/test_stock_identity_w3_calibration.py data/stock_identity/ruler/ruler_spec_v1.json research/stock_identity/W3_RULER_REGISTRATION.md
git commit -m "stock-identity W3A: one-time sealed-calibration ruler constants"
```

---

### Task 2: Implement deterministic per-fire/per-episode metrics and unconditional block

**Files:**
- Modify: `engine/stock_identity/ruler.py`
- Modify: `tests/test_stock_identity_ruler.py`
- Create: `scripts/stock_identity_build_ruler.py`

**Interfaces:**
- Consumes: W1 episode rows, W2 event rows, W2 attribution rows, accepted daily adjusted bars.
- Produces:

```python
def compute_fire_metrics(
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    episodes: pd.DataFrame,
    bars_by_symbol: Mapping[str, pd.DataFrame],
    spec: RulerSpec,
) -> pd.DataFrame: ...


def compute_unconditional_block(
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    episode_rows: pd.DataFrame,
) -> pd.DataFrame: ...
```

- [ ] **Step 1: Add failing synthetic metric tests**

Create a three-episode fixture covering reset, reclaim and censored/unresolved cases plus events before/inside/outside attribution windows. Assert exact sign convention (`lead_lag < 0` anticipates), censored episodes have no anchor metrics, and out-of-episode fires remain in `fires_per_name_year` / attribution-rate denominators.

Example:

```python
def test_censored_episode_has_no_anchor_metrics_but_counts_unconditional():
    out = compute_fire_metrics(events, attribution, episodes, bars, spec)
    row = out.loc[out["episode_id"] == "E_CENSORED"].iloc[0]
    assert pd.isna(row["lead_lag"])
    assert pd.isna(row["atr_dist"])
    unconditional = compute_unconditional_block(events, attribution, episodes)
    assert unconditional.loc[unconditional["ticker"] == "AAA", "fires_per_name_year"].iloc[0] > 0
```

- [ ] **Step 2: Run red**

```bash
python3 -m pytest tests/test_stock_identity_ruler.py -k "lead_lag or censored or unconditional" -q
```

Expected: missing functions/columns.

- [ ] **Step 3: Implement metrics with no ranking step**

`compute_fire_metrics` returns one measurement row per valid event↔episode attribution, never one best-expert row. Episode anchor selection is a pure mapping from episode type. All bars are prior-close ATR-based as already frozen; no future data enters event `known_ts`.

- [ ] **Step 4: Implement unconditional false-positive accounting**

Every expert/ticker row must include total fires, attributed fires, `fires_per_name_year`, and `episode_attribution_rate = attributed_fires / total_fires`, preserving zero-total as explicit no-coverage rather than division to zero.

- [ ] **Step 5: Add no-ranking/no-authority mutation guards**

Tests scan W3 output schema and `engine/stock_identity/ruler.py` for prohibited output columns such as `best_expert`, `expert_rank`, `winner`, `route`, `prophet_score`, and verify all serialized authority axes remain false.

- [ ] **Step 6: Run targeted tests**

```bash
python3 -m pytest tests/test_stock_identity_ruler.py -q
```

Expected: pass.

- [ ] **Step 7: Run real pilot smoke without blind output**

```bash
python3 scripts/stock_identity_build_ruler.py --pilot --output-dir /tmp/si-w3a-ruler-smoke
```

Expected: metric/unconditional artifacts for the design-touched pilot only, explicit censored counts, no blind-name table, no `best`/`rank` output. The script additionally emits `support_coverage_v1.parquet` — the outcome-independent support/coverage frame for W3B (identifiers, clocks/blocks, family/grain, attribution presence, feature/price coverage, censored/availability state; NO realized metric or composite columns) — which is the ONLY ruler-side artifact Task 4 may consume.

- [ ] **Step 8: Commit Task 2**

```bash
git add engine/stock_identity/ruler.py tests/test_stock_identity_ruler.py scripts/stock_identity_build_ruler.py
git commit -m "stock-identity W3A: implement episode localization metrics"
```

---

### Task 3: Implement the two composites, grain controls, and mandatory null generators

**Files:**
- Modify: `engine/stock_identity/ruler.py`
- Modify: `tests/test_stock_identity_ruler.py`
- Create: `engine/stock_identity/ruler_nulls.py`
- Create: `tests/test_stock_identity_ruler_nulls.py`

**Interfaces:**

```python
def compute_composites(metrics: pd.DataFrame, spec: RulerSpec) -> pd.DataFrame: ...

def random_fire_null(events: pd.DataFrame, episodes: pd.DataFrame, seed: int, spec: RulerSpec) -> pd.DataFrame: ...

def grain_cadence_null(events: pd.DataFrame, episodes: pd.DataFrame, spec: RulerSpec) -> pd.DataFrame: ...

def equal_proximity_control(metrics: pd.DataFrame, tolerance_atr: float) -> pd.DataFrame: ...
```

- [ ] **Step 1: Add failing composite identity tests**

```python
def test_c_loc_r_exact_formula():
    row = pd.DataFrame([{"recall_at_tier": 0.5, "zone_precision": 0.8, "false_start_rate": 0.1}])
    out = compute_composites(row, spec)
    assert out.loc[0, "c_loc_r"] == pytest.approx(0.5 * 0.8 - spec.lambda_fs * 0.1)
```

Also assert `c_loc_d` refuses rows below the frozen recall floor.

- [ ] **Step 2: Add failing null invariance tests**

Assert random null preserves per-expert fire count and declared dwell structure; grain null preserves each expert's cadence/stamp lag; equal-proximity control never pairs observations outside the ATR tolerance.

- [ ] **Step 3: Run red**

```bash
python3 -m pytest tests/test_stock_identity_ruler.py tests/test_stock_identity_ruler_nulls.py -q
```

- [ ] **Step 4: Implement composites and null generators**

No function may inspect per-name outcome rank to select a parameter, expert or neighborhood. Seeds are deterministic and recorded into the W3 registration artifact.

- [ ] **Step 5: Add TrialLedger discipline**

Any diagnostic sensitivity grid invoked by the W3 script must register the exact grid before execution via the existing `engine/trial_ledger.py` contract. The shipped-parameter primary path itself is not a grid search.

- [ ] **Step 6: Run all W3A tests and real pilot smoke**

```bash
python3 -m pytest tests/test_stock_identity_ruler.py tests/test_stock_identity_ruler_nulls.py -q
python3 scripts/stock_identity_build_ruler.py --pilot --include-nulls --output-dir /tmp/si-w3a-ruler-smoke
```

Expected: pass; both graded composites present; all nulls present; no blind/fit/rank output.

- [ ] **Step 7: Commit Task 3**

```bash
git add engine/stock_identity/ruler.py engine/stock_identity/ruler_nulls.py tests/test_stock_identity_ruler.py tests/test_stock_identity_ruler_nulls.py scripts/stock_identity_build_ruler.py
git commit -m "stock-identity W3A: add composites and localization nulls"
```

---

### Task 3B: Freeze the Channel-A model constitution (prereg only — no fitting)

**Files:**
- Create: `research/stock_identity/W3_CHANNEL_A_MODEL_CONSTITUTION.md`
- Create: `data/stock_identity/ruler/channel_a_constitution_v1.json`
- Create: `engine/stock_identity/model_constitution.py`
- Create: `tests/test_stock_identity_model_constitution.py`

**Interfaces:**

```python
def load_constitution(path: Path) -> "ChannelAConstitution": ...
def count_p_eff(constitution: "ChannelAConstitution") -> int: ...
def assert_capacity(p_eff: int, n_names: int) -> None:  # raises CapacityViolation when p_eff > n_names // 10
    ...
```

- [ ] **Step 1: Write the failing constitution tests**

Assert: the JSON declares an explicit feature subset that is a subset of the actual W1 fingerprint columns; the functional form is `additive_monotone` (a richer form is admissible only via a `separately_preregistered_form_ref` field pointing at a real registration document — absent here); `count_p_eff` implements the exact declared counting rule deterministically; `assert_capacity` raises on `p_eff > n_names // 10` and passes at the boundary; the module imports no fitting/estimation library and no fit entry point exists.

- [ ] **Step 2: Run red**

```bash
python3 -m pytest tests/test_stock_identity_model_constitution.py -q
```

- [ ] **Step 3: Author the constitution artifact**

`W3_CHANNEL_A_MODEL_CONSTITUTION.md` freezes, per original masterplan §2.3 control (i): the declared fingerprint feature subset (named columns), the allowed additive/monotone functional form, the exact `p_eff` counting rule (formula stated, including per-feature shape terms), `p_eff <= N_names/10` with `N_names` defined as the post-exclusion training-fold name count, and the enforcement contract: W5Q evaluates `assert_capacity` on every training fold BEFORE any fit and a violation aborts the read. The JSON mirror is spec-hashed; authority all false. W3 fits nothing.

- [ ] **Step 4: Run green and commit Task 3B**

```bash
python3 -m pytest tests/test_stock_identity_model_constitution.py -q
git add research/stock_identity/W3_CHANNEL_A_MODEL_CONSTITUTION.md data/stock_identity/ruler/channel_a_constitution_v1.json engine/stock_identity/model_constitution.py tests/test_stock_identity_model_constitution.py
git commit -m "stock-identity W3A: freeze Channel-A model constitution (capacity budget)"
```

---

### Task 4: Build the W3B estimability/dependence census

**Files:**
- Create: `engine/stock_identity/estimability.py`
- Create: `scripts/stock_identity_build_estimability.py`
- Create: `tests/test_stock_identity_estimability.py`
- Create: `data/stock_identity/census/fit_estimability_v1.schema.json`
- Create: `research/stock_identity/W3_ESTIMABILITY_REGISTRATION.md`

**Interfaces:**

```python
def validate_support_frame(support: pd.DataFrame) -> None:  # raises OutcomeLeakage on any forbidden column
    ...

def build_estimability_census(
    episodes: pd.DataFrame,
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    support: pd.DataFrame,
    feature_coverage: pd.DataFrame,
    floors: "EstimabilityFloors",
) -> pd.DataFrame: ...
```

`support` is the typed outcome-independent support/coverage frame emitted by the Task 2 ruler build (`support_coverage_v1.parquet`). Its closed column contract is exactly: `episode_id`, `event_id`, `ticker`, `known_ts`, `calendar_block`, `family`, `grain`, `attributed` (bool presence, not quality), `price_coverage`, `feature_coverage`, `price_plane_id`, `availability_state` (censored/not-yet-available/structural-absence/etc.). `validate_support_frame` (called first inside `build_estimability_census`) raises `OutcomeLeakage` if the frame carries ANY realized-fit column — `c_loc_r`, `c_loc_d`, `lead_lag`, `price_dist`, `atr_dist`, `mae_after`, `capture`, `recall_at_tier`, `zone_precision`, `false_start`, `false_start_rate`, `relative_order`, `consistency`, or any column not in the closed contract. Cell inclusion/estimability may never depend on how well any expert scored.

Required outputs per candidate cell include `episode_n`, `calendar_cluster_n`, `largest3_cluster_share`, `fire_n`, `fires_per_name_year`, `episode_attribution_rate`, `grain_coverage`, `feature_coverage`, `price_plane_id`, `estimability_state`, and `unestimable_reason`.

- [ ] **Step 1: Add failing dependence tests**

Create a fixture with 100 episode rows concentrated in two calendar clusters. Assert `episode_n == 100` while `calendar_cluster_n == 2`, and that the cell is `UNESTIMABLE` when the registered cluster floor is >2.

- [ ] **Step 2: Add failing missingness taxonomy tests**

Assert structural expert absence, no fires despite coverage, missing feature plane, censored episode, and insufficient clusters map to distinct reason codes rather than one generic null.

- [ ] **Step 2B: Add the failing outcome-leakage regression**

Assert `build_estimability_census` raises `OutcomeLeakage` when the support frame carries any realized-fit column (parameterized over the full forbidden list above), and that census output on a lawful support frame is byte-identical when the fixture's underlying expert quality is permuted — inclusion/estimability provably cannot respond to realized localization quality.

- [ ] **Step 3: Run red**

```bash
python3 -m pytest tests/test_stock_identity_estimability.py -q
```

- [ ] **Step 4: Implement calendar-block assignment**

Use the frozen W3 ruler episode-duration distribution to set block length at least the P90 episode duration; assign episodes to calendar blocks by the registered anchor/start sensitivity rule. Do not use the W1 degenerate universe cluster component as inferential N.

- [ ] **Step 5: Implement explicit estimability state**

Closed states: `ESTIMABLE`, `UNESTIMABLE`, `NO_COVERAGE`, `STRUCTURAL_ABSENCE`, `CENSORED_ONLY`. A cell may never be represented as a numerical zero merely because it is unestimable.

- [ ] **Step 6: Run real pilot census**

```bash
python3 scripts/stock_identity_build_estimability.py --pilot --support-path /tmp/si-w3a-ruler-smoke/support_coverage_v1.parquet --output-dir /tmp/si-w3b-census
```

Expected: every candidate cell has honest episode/calendar-cluster N and a closed estimability state; no fit/composite ranking table is emitted. The script consumes ONLY the outcome-independent support artifact — never the metric/composite/null files that share the ruler output directory.

- [ ] **Step 7: Commit Task 4**

```bash
git add engine/stock_identity/estimability.py scripts/stock_identity_build_estimability.py tests/test_stock_identity_estimability.py data/stock_identity/census/fit_estimability_v1.schema.json research/stock_identity/W3_ESTIMABILITY_REGISTRATION.md
git commit -m "stock-identity W3B: add estimability and dependence census"
```

---

### Task 5: Close or truthfully block the W3S terminated-instrument control

**Files:**
- Create: `engine/stock_identity/dead_control.py`
- Create: `scripts/stock_identity_build_dead_control.py`
- Create: `tests/test_stock_identity_dead_control.py`
- Create: `data/stock_identity/control/dead_instrument_manifest_v1.json`
- Create: `research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md`

**Interfaces:**

```python
def load_delisted_sampling_frame(repo_root: Path) -> pd.DataFrame: ...
def inventory_existing_adjusted_history_owners(repo_root: Path) -> list["HistoryOwnerCandidate"]: ...
def validate_terminated_instrument(candidate: "HistoryOwnerCandidate") -> "DeadInstrumentReceipt": ...
def build_dead_control_manifest(receipts: Sequence["DeadInstrumentReceipt"]) -> dict: ...
```

The sampling frame starts from `config/delisted_symbols.yml` with `terminated_reason` recorded, per the original masterplan's dead-names clause: `load_delisted_sampling_frame` reads that file and is the sole source of candidate terminated identities; the owner inventory then determines which canonical adjusted-history plane can supply each tape. Consequence law is fixed and no new statistical kill threshold is invented: fewer than 5 lawful instruments => `BLOCKED_NO_LAWFUL_DATA` and W5P/Q1 stay blocked; >=5 => the cohort MUST enter the W5 survivorship control/report, and its performance does not independently pass or fail Q1 unless a future separately preregistered criterion says so.

- [ ] **Step 1: Write the source-owner inventory test**

The inventory function must enumerate current canonical/registered adjusted-history owners before any network/source adapter code is allowed. The test fails if an implementation imports a new collector/provider module without a recorded owner verdict in the registration document. A companion test asserts the candidate identity set comes exactly from `load_delisted_sampling_frame` over `config/delisted_symbols.yml` (with `terminated_reason` present per row) and that no candidate is minted from any other list.

- [ ] **Step 2: Write terminated-identity/hygiene tests**

A valid receipt requires: instrument identity, terminal reason, terminal date, price source, adjustment mode, first/last date, OHLCV coverage, source/rights note, correction semantics, and reused-ticker hygiene result. A live ticker relabeled as dead must fail.

- [ ] **Step 3: Write fingerprint/episode compatibility test**

Each accepted control tape must pass through existing `engine.stock_identity.fingerprint` and `engine.stock_identity.episodes` entry points with the same adjustment/identity semantics as the study cohort.

- [ ] **Step 4: Run red**

```bash
python3 -m pytest tests/test_stock_identity_dead_control.py -q
```

- [ ] **Step 5: Implement owner-first inventory and validation**

No general market-data platform is created. If an existing canonical owner satisfies the contract, the manifest references it. If fewer than five lawful terminated instruments can be produced, the script exits nonzero with typed status `BLOCKED_NO_LAWFUL_DATA` and writes only a non-authoritative diagnostic receipt; W5 remains blocked.

- [ ] **Step 6: Run the real control build**

```bash
python3 scripts/stock_identity_build_dead_control.py --min-instruments 5 --output data/stock_identity/control/dead_instrument_manifest_v1.json
```

Expected either:

- success with >=5 validated terminated instruments and immutable hashes; or
- fail-closed `BLOCKED_NO_LAWFUL_DATA`, with no fake survivor substitute.

- [ ] **Step 7: Commit Task 5**

```bash
git add engine/stock_identity/dead_control.py scripts/stock_identity_build_dead_control.py tests/test_stock_identity_dead_control.py data/stock_identity/control/dead_instrument_manifest_v1.json research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md
git commit -m "stock-identity W3S: establish terminated-instrument control"
```

If the real run returns `BLOCKED_NO_LAWFUL_DATA`, commit the registration/typed blocker and tests but do not fabricate a successful manifest.

---

### Task 6: W3 release integration, fences, and return packet

**Files:**
- Modify: CI registry/job file only through the current house pattern selected by current main at implementation time; no new standalone workflow.
- Modify: `agentos/workstreams/WS-STOCK-IDENTITY.md`
- Create: `agentos/handoffs/STOCK-IDENTITY-<current-date>-W3-measurement-release.md` on the implementation carrier with the exact calendar date of the actual return.
- Modify: `research/stock_identity/W3_RULER_REGISTRATION.md`
- Modify: `research/stock_identity/W3_ESTIMABILITY_REGISTRATION.md`
- Modify: `research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md`

**Interfaces:**
- Produces a W3 milestone packet containing exact PR/head, ruler spec hash, artifact hashes, test/CI receipts, real pilot smoke, survivorship status, all unverified claims, and the exact W4 gate.

- [ ] **Step 1: Add the current-house CI job for only the new W3 tests**

Use the current Macro CI registry semantics at pickup; do not add a duplicate GitHub Actions workflow. The job must run the ruler, null, estimability, dead-control unit suites plus existing W1/W2 Stock Identity guards.

- [ ] **Step 2: Run the complete local Stock Identity suite**

```bash
python3 -m pytest tests/test_stock_identity_ruler.py tests/test_stock_identity_w3_calibration.py tests/test_stock_identity_ruler_nulls.py tests/test_stock_identity_model_constitution.py tests/test_stock_identity_estimability.py tests/test_stock_identity_dead_control.py -q
```

Then run every pre-existing Stock Identity W1/W2 test file selected by current CI planning.

- [ ] **Step 3: Run protected-path diff fences**

```bash
git diff --stat origin/main...HEAD -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/stock_personality.py engine/oracle/personality_context.py scripts/build_stock_library.py engine/entry_radar
```

Expected: empty.

- [ ] **Step 4: Run Agent OS validation**

```bash
python3 scripts/agentos.py validate
```

Expected: 0 errors attributable to W3 changes.

- [ ] **Step 5: Update `WS:STOCK-IDENTITY` truthfully**

Mark W3 sub-capabilities individually. A successful W3A/W3B with W3S blocked must not mark the full W3 Measurement Release done. W4 stays held until Sol adjudicates the milestone packet.

- [ ] **Step 6: Push and obtain exact-head hosted CI**

Return exact head SHA and hosted `fences`/`ci` run IDs. Do not call a local pass acceptance.

- [ ] **Step 7: Post `RESULT SI-W3-MEASUREMENT-RELEASE` in the shared Slack thread**

The message includes exact PR/head, capability deltas, whether W3S is successful or blocked, and the immutable Agent OS handoff ref. Then enter the approved exact-thread wait/watch path. Do not self-start W4.

- [ ] **Step 8: Stop at Sol review**

Sol applies `REVIEW_RETURN.md` against exact head. Only a Sol `CONTINUE` after accepted W3 Measurement Release permits a new W4 operation/carrier.

---

## Plan self-review

- Spec coverage: W3A deterministic ruler, one-time sealed-calibration constant-setting with rule-before-value and look budget (Task 1B), frozen composites, unconditional block, grain/null controls, the Channel-A model constitution / capacity budget (Task 3B), W3B honest-N/estimability on an outcome-independent support frame, W3S survivorship from the `config/delisted_symbols.yml` frame, protected paths, real smoke, hosted CI and milestone return are all assigned explicit tasks.
- The W3B census provably cannot read realized localization/composite quality; the W5 population is outcome-independent.
- The W3S consequence matrix is unchanged: the control can block or enter the W5 report, never independently kill Q1.
- No Q1 outcome opening occurs in this plan.
- No W4 epoch implementation is smuggled into W3.
- No downstream consumer path is preclaimed.
- No duplicate event/replay/data/control plane is introduced.
- Failure to obtain terminated-instrument data remains a typed blocker rather than an invented substitute.
