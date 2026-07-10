# METABOLISM REASONING RECEIPT (R-V3-5a)

> **IMMUTABLE (R-V3-5): loop PRs may not edit this schema; registered in
> `check_self_mod_fence.py` by W3.**

## Purpose

The Reasoning Receipt is a **structured artifact** the autonomous Metabolism
loop fills on every pass, turning the fable-mode pre-send gate from prose into
a machine-checkable record.  Each field maps to a specific epistemic principle.
All `claims[].source` values are validated by `grounding.validate_grounding`
(see `engine/metabolism/grounding.py`).

---

## Schema (JSON)

```json
{
  "fork": "string — the single question whose answer most changes the next action",
  "prediction": "string — stated expectation before the next probe runs",
  "cheapest_falsifier": "string — cheapest observation that could kill the current hypothesis",
  "falsifier_result": "string — what the falsifier actually returned",
  "positive_control": "string — what was run to confirm the instrument would have caught a failure",
  "lobe": "string — (optional) structured lobe reference, checked against config/synapse.yml",
  "refs": {
    "lobes": ["string — structured lobe ids, each checked against config/synapse.yml"],
    "rulings": ["string — ruling ids, each checked against config/ruling_graph.yml"]
  },
  "claims": [
    {
      "claim": "string — a behavioral assertion made in this pass",
      "source": "string — the specific observation grounding it (file:line, command, data path)",
      "lobe": "string — (optional) the lobe this claim pertains to, checked against registry",
      "refs": {
        "lobes": ["string — lobe ids referenced by this claim"],
        "rulings": ["string — ruling ids referenced by this claim"]
      }
    }
  ]
}
```

---

## Field-to-principle mapping

| Field | Fable-mode principle operationalized |
|-------|--------------------------------------|
| `fork` | §2.1 — *Find the fork before spending effort*: name the question whose answer most changes the next three actions. |
| `prediction` | §3.3 — *Predict the output before running the probe*: write the expected result before executing; mismatch = fork-resolving signal. |
| `cheapest_falsifier` | C2 — *Hypotheses, not beliefs*: every conclusion travels with its cheapest falsifier. |
| `falsifier_result` | C2 — records whether the falsifier was run and what it returned; absent or "not run" is a red flag for the reviewer. |
| `positive_control` | §3.4 — *Positive-control the instrument*: when a null result supports a conclusion, confirm the instrument would have fired on a known-positive case. |
| `claims[].claim` | C1 — *Evidence over plausibility*: every behavioral claim must cite an observation, not a story. |
| `claims[].source` | C1 — the specific observation (file:line, command, data path); validated against known registries by `grounding.validate_grounding`. |

---

## Filled example

```json
{
  "fork": "Does organism_state.json already exist, or is this a first-run cold start?",
  "prediction": "If nightly has run at least once, the file exists at data/metabolism/organism_state.json and has at least one lobe entry.",
  "cheapest_falsifier": "stat data/metabolism/organism_state.json",
  "falsifier_result": "File exists, mtime=2026-07-09T23:18:42Z, size=4.2KB — hypothesis confirmed.",
  "positive_control": "Renamed file to .bak, re-ran build_organism_state() — returned empty lobes with gap logged. Renamed back.",
  "lobe": "til",
  "refs": {
    "lobes": ["til"],
    "rulings": ["RUL-CL-1"]
  },
  "claims": [
    {
      "claim": "The TIL lobe trajectory is accruing — fewer than 3 fitness_delta observations.",
      "source": "data/metabolism/trajectory.jsonl — last 10 rows, lobe=til, all have fitness_delta=null (gate_reason: no delta)",
      "lobe": "til",
      "refs": {
        "lobes": ["til"],
        "rulings": []
      }
    },
    {
      "claim": "grounding check returned ok=True, ungrounded=[] for RUL-CL-1.",
      "source": "engine/metabolism/grounding.py:validate_grounding({'lobe_id': 'til', 'ruling_id': 'RUL-CL-1'}, root=repo)",
      "refs": {
        "lobes": ["til"],
        "rulings": ["RUL-CL-1"]
      }
    }
  ]
}
```

---

## Validation

`grounding.validate_grounding(receipt, root=...)` checks id references in the
receipt.  The exact scope of what IS and IS NOT grounded is stated here:

**Lobes** — grounded from **structured fields only**: `lobe`, `lobe_id`, `lobes`
keys at the top level and inside `claims[]` and `refs`.  A lobe id found in a
structured field is checked against `config/synapse.yml` artifacts.
Free-text mentions of lobe names (e.g. "the til lobe is compounding") are **not**
extracted or checked — prose is too ambiguous and display-only.

**Ruling ids** — grounded from **both** structured fields (`ruling_id`, `ruling`,
`rulings`) and **free text**.  Free-text detection uses a prefix-anchored pattern
derived at load time from the actual ruling ids in `config/ruling_graph.yml`;
only tokens whose prefix matches a known ruling prefix are candidates, and each
is then membership-checked against the full id set.  A known-prefix token that
is NOT a real id (e.g. a hallucinated `RUL-CL-9999`) is flagged as `ungrounded`.
Tokens with no known ruling prefix (tickers, macro variables, etc.) are silently
ignored — they never enter the ruling candidate set.

**Sensors** — grounded from structured fields only (`sensor`, `sensor_id`,
`sensors`).  Requires fitness cards in `data/metabolism/fitness/`; if absent,
`sensors_loaded=False` in `registry_status` (not counted in top-level
`unverified` flag — sensor grounding is best-effort only).

A receipt with `unverified=True` in the grounding result must be surfaced as
**"grounding unverified"**, not "grounding clean", in any downstream digest.
Unrecognised ids appear in the `ungrounded` list; `ok=False` signals at least
one ungrounded id from a successfully loaded registry.

---

## Immutability note

This schema is registered in the self-modification fence
(`scripts/check_self_mod_fence.py`, W3 integration).  Loop PRs (branch prefix
`metabolism/` or `claude/loop-`) that edit this file are blocked by CI.
Human / operator PRs may amend the schema, but must increment the version
comment above and update `check_self_mod_fence.py` accordingly.
