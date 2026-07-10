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
  "claims": [
    {
      "claim": "string — a behavioral assertion made in this pass",
      "source": "string — the specific observation grounding it (file:line, command, data path)"
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
  "claims": [
    {
      "claim": "The TIL lobe trajectory is accruing — fewer than 3 fitness_delta observations.",
      "source": "data/metabolism/trajectory.jsonl — last 10 rows, lobe=til, all have fitness_delta=null (gate_reason: no delta)"
    },
    {
      "claim": "grounding check returned ok=True, ungrounded=[].",
      "source": "engine/metabolism/grounding.py:validate_grounding({'lobe': 'til', 'ruling_id': 'RUL-CL-1'}, root=repo)"
    }
  ]
}
```

---

## Validation

- `grounding.validate_grounding(receipt, root=...)` checks every `claims[].source`
  string for references to lobes (`config/synapse.yml`), ruling_ids
  (`config/ruling_graph.yml`), and sensors (fitness cards).  Unrecognised ids
  appear in the `ungrounded` list.
- A receipt with `unverified=True` in the grounding result must be surfaced as
  **"grounding unverified"**, not "grounding clean", in any downstream digest.

---

## Immutability note

This schema is registered in the self-modification fence
(`scripts/check_self_mod_fence.py`, W3 integration).  Loop PRs (branch prefix
`metabolism/` or `claude/loop-`) that edit this file are blocked by CI.
Human / operator PRs may amend the schema, but must increment the version
comment above and update `check_self_mod_fence.py` accordingly.
