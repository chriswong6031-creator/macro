# Golden set — the press scoring brain's ground truth (XG-W5 / IS-W2)

`labels.jsonl` (this directory) is the **committed, hand-authored** label store the
precision@20 harness grades against. It does not exist until the first labeling
session lands rows in it.

**It is not a forward ledger.** No engine path writes it, the press daemon never
touches it, and the nightly does not advance it — the nightly-sole-advancer law
governs ledgers the engine accrues, and this is ground truth a human produced.
It is maintained the way `config/reply_targets.yml` is: edited in a session,
reviewed as a diff, committed by hand.

## Row schema (`golden.v1`)

```json
{"schema": "golden.v1", "item_id": "…", "label": "post_worthy",
 "labeler": "fable", "labeled_at": "2026-07-28T12:00:00+00:00",
 "batch_id": "gb-…", "headline": "…", "source": "…", "notes": ""}
```

`label` is exactly one of:

| label | means |
|---|---|
| `garbage` | should never have entered the pipeline |
| `useful` | real information, not worth a post on its own |
| `post_worthy` | worth an X post |
| `viral_grade` | worth a prime slot |

`post_worthy` + `viral_grade` are the positive class for precision@20.

## Producing labels

The ingested corpus is runtime-only and lives on the press host. Full procedure —
export command, labeling flow, import, and the arming rule it gates — is in
[`docs/scoring_brain.md`](../../../docs/scoring_brain.md) §2.

```bash
python3 scripts/marketing_golden_set.py export --n 200 --out batch.jsonl   # on the host
python3 scripts/marketing_golden_set.py import batch.jsonl --labeler fable
python3 scripts/marketing_golden_set.py eval --k 20
```

Until rows exist, `eval` reports `state: no-labels` and a **null** precision. That
is the honest answer, not a failure — and not a pass.
