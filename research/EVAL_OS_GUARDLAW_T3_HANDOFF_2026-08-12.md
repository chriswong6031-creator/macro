# Eval OS — append-only law + T3 gate promotion — continuation handoff

**Date** 2026-08-12 · **Branch** `claude/eval-os-guardlaw-t3` (pushed, **no PR**) ·
**Status** NOT SHIPPABLE. 3/3 adversarial lenses refuted. Two genuinely good ideas inside,
and one instructive failure.

---

## 0. The instructive failure — state it before anything else

**Job C promoted `scripts/check_qledger_metric_validity.py --strict` to severity `hard`, wired
into `pr_ci`, while that gate asserts on the CONTENT of `data/qledger/claims.jsonl` — an
append-only store that grows every night. That is exactly what the append-only law (Job B)
shipped in the SAME COMMIT forbids. And the law is structurally blind to it.**

Two failures in one commit:
- the law cannot enforce its own subject (`check_append_only_assertions.py:499-519` matches only
  `ast.Assert` nodes containing an `ast.Compare`, so a guard whose *exit code* is a function of
  store content is invisible to it);
- the thing it failed to catch is a **hard, fleet-wide gate**.

**Worse, the gate it promoted is vacuous.** A PR that fully reintroduces the pre-T3 emitter
defect passes `--strict` with exit 0, because `derive_reported_metrics` reads metric keys back
out of the committed `site/qledger/track_record.json` rather than out of the emitter. The gate
is a receipt written from the same variable it checks — it cannot fail on the defect it exists
to gate. It also counts a metric as "published" by **key presence, ignoring a null value**, so 13
zero-claim families with null `challenger_excess_mean_5d` register as publishing it.

Do not resurrect the promotion without fixing both: the gate must read what the **emitter would
produce**, and it must not be gated on append-only content.

---

## 1. Two ideas worth keeping

**(a) The monotonicity rule.** The right test for an illegal assertion is not "does it compare
against a committed artifact" but:

> **illegal iff APPENDING A ROW can falsify it.**

`len(rows) == 28` and `ledger_ids <= graded_ids` are fragile. `>= floor`, `x in store`,
`set(keys) == FIELDS`, and two reads of the same store within one run are all safe. That
formulation is correct and should survive into any future version.

**(b) The cadence trap, measured.** **Neither motivating store's synapse cadence says
"nightly"** — `data/qledger/claims.jsonl` and `data/prophet/ledger.jsonl` are both
`daily-engine`. A rule grepping for "nightly" would have classified **zero of the four known
defects**. 108 stores classify correctly under the derived rule (jsonl under `data/` + `storage:
git` + a nightly-lane cadence, OR the entry's own prose declaring append-only). Anyone rebuilding
this must not regress to the naive keyword.

---

## 2. Confirmed live defect the census found (this part is real and unfixed)

`engine/qledger.py::_aggregate()` (lines 850-905) is the single chokepoint feeding both
`compute_track_record()` → `site/qledger/track_record.json` and
`scripts/grade_qledger.py::compute_promotion_readiness()`. It computes a **pooled signed
`excess_mean`** for every family with no legality gate.

**On the live corpus this reaches a human surface:** `radar` (directions {−1,0,1}) and
`whitehouse` ({−1,1}) carry non-null pooled `excess_mean` (radar@5d = −0.0031, whitehouse@5d =
−0.0026), flowing through `engine/experiments_registry.py::_refresh_qledger_promotion()` into the
**admin Experiments tab**, rendered literally as `hit=…% · excess=…%`. `policy` and `intel_hub`
are also mixed-direction but are not in `config/qual_ladder.yml`, so their pooled excess sits
unread in raw JSON — latent, not yet human-facing.

**Fixing `_aggregate` alone fixes both downstream paths.** The in-repo template for the correct
behaviour already exists: `_placebo_magnitude()` (908-982) reports `mean_abs_excess`, never a
signed pooled mean. Two emitters already do the right thing and are worth copying:
`engine/china_special_situations.py::_track_summary()` refuses to surface hit_rate/excess for a
salience-only family, and `engine/neuralweb/mastermind_context.py::_summarize_claim_reliability()`
omits null values entirely rather than rendering an ambiguous dash.

**A refinement to my own catalog:** `hit_rate` is structurally safe for salience families today —
`grade_claim()` always stores `hit=None` for `direction==0`, so `hit_rate` resolves to `None`
everywhere it is read. No downstream emitter has ever shown a fabricated hit rate for a salience
family. The V2 finding in `engine/qledger_validity.py` is therefore about **schema exposure and
ambiguity**, not a currently-wrong number. `scripts/build_measurement.py::build_qledger_reliability()`
renders `—` for salience families with no label distinguishing "categorically undefined" from
"ACCRUING, not enough n yet", which is the real (and milder) harm.

---

## 3. Remaining defects in Job B's law

- Only recognises a repo root bound as `Path(__file__)….parents[N]`; the commoner
  `Path(__file__).resolve().parent.parent` shape is invisible.
- **False positive contradicting its own stated guarantee**: a `tmp_path` sandbox assertion IS
  reported, although the docstring promises those can never fire.
- **Dead code drives a false message**: `_reads_a_store` and `_READ_CALLS` are defined and never
  called.
- `_append_fragile` returns True unconditionally for `NotIn`, so `x not in <anything>` always
  fires even when the right-hand set was derived in the same run.
- The registry's false-negative note is mis-attributed and its prescribed remedy would not work.

---

## 4. Recommended sequence when this resumes

1. **Fix `_aggregate` only** (§2) — a small, high-value, self-contained PR that removes a live
   illegal number from a human surface. It needs no new guard and no gate promotion.
2. Rebuild the law around the monotonicity rule (§1a), keeping the cadence finding (§1b), and
   make it able to see a guard whose **exit code** depends on store content.
3. Only then revisit promoting the metric-validity gate — and only if the gate reads the
   **emitter**, not the published artifact.

## 5. Exact next command

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/eval-os-guardlaw-t3"
git log --oneline -3
python3 scripts/check_append_only_assertions.py --selftest
python3 scripts/check_append_only_assertions.py --root ../eval-os-t2-prophet-benchmark   # proves it catches the motivating defect
python3 scripts/check_qledger_metric_validity.py --strict > /tmp/o 2>&1; echo $?          # do NOT trust green here — see §0
```
