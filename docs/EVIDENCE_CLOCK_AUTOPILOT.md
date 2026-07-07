# Evidence Clock Autopilot — Operator Guide

## What it is

The Global Evidence Clock is a nightly deterministic aggregator that reads every
review-clock source in the repo and writes a single display-only artifact:

    data/neuralweb/evidence_clock.json

It answers one morning question: **what is due, stale, underpowered, or blocked today?**

It routes attention.  It cannot promote, retire, or mutate any source system.
No LLM is in the loop.  Runtime is a few seconds.

---

## The morning question

Open `data/neuralweb/evidence_clock.json` and read `summary.morning_line`:

```
3 due/overdue, 12 accruing, 2 stale, 5 blocked. Top due: experiments:radar-ic.
```

That is the full signal.  Drill into `rows` filtered by `state == "due"` or
`state == "overdue"` for the detail.  Rows include `packet` stubs on due/overdue
entries with the reason-due and any missing evidence.

---

## State vocabulary

| State | Meaning | Action |
|---|---|---|
| `overdue` | Clock date passed and grace window expired | Inspect; source system needs attention |
| `due` | Clock date arrived (within grace window) | Inspect; decide in the source system |
| `human_review` | Candidate queue waiting for a human decision | Review via the source system's review tool |
| `missing` | Expected artifact is absent on disk | Run `regenerate_cmd` shown in the row |
| `stale` | Artifact exists but freshness SLA breached | Run `regenerate_cmd` shown in the row |
| `blocked` | A higher-precedence signal prevents action | See `readiness.blocking_reason` |
| `not_ready` | Date-due but evidence floors unmet | See `readiness.blocking_reason`; gather missing evidence |
| `promotion_eligible` | Evidence floors met; awaiting authority sign-off | Operator decision required in the source system |
| `accruing` | Clock is running; date not yet arrived | No action |

The `date_state` field records the pre-demotion state for audit purposes, so you
can see whether a `blocked` row would have been `due` before the precedence check.

---

## Precedence rules (EC-R3)

When multiple clocks compete for the same subject, higher-precedence signals demote
lower-precedence ones.  The order (highest first):

1. Governance ruling (lapses_at)
2. Research-factory transition state (awaiting_data, blocked)
3. qledger maturity (check_by past due)
4. Trial budget exhaustion
5. Freshness SLA breach (adds a note; does not change state alone)
6. Experiments registry
7. Display (declared) clocks

A `blocked` row carries `readiness.blocking_reason` explaining the demotion.

---

## How to acknowledge a review

When you have inspected a `due` or `overdue` row and want to snooze it for 7 days,
append one line to `data/neuralweb/evidence_clock_reviews.jsonl`:

```json
{"clock_id": "experiments:radar-ic", "reviewed_on": "2026-07-06", "note": "reviewed; will re-check on come_back_on date", "outcome": "deferred"}
```

Fields:
- `clock_id` — exact `clock_id` from the row
- `reviewed_on` — ISO date string (today)
- `note` — free text
- `outcome` — `deferred`, `rejected`, `escalated`, `closed`, or `paper`

The builder reads this file on the next nightly run.  Within `snooze_days` (7d),
the row is marked `acknowledged: true` and excluded from `top_due` and the
`morning_line` due count.  The row still appears in `rows` for audit.

**Never** write to any source ledger directly (governance.jsonl, claims.jsonl, etc.).
Real state changes must flow through the source system's own write path.

---

## How to add a source

Two ways:

**Option A — preferred (RF-9):** Register a `come_back_on` field in
`data/experiments/registry_seed.json`.  The experiments adapter picks it up
automatically on the next nightly run.

**Option B — stopgap:** Add an entry to `declared_clocks` in
`config/evidence_clock.yml`.  This is a temporary home for masterplan come-backs
that have no ledger home yet.  Migrate to Option A as soon as possible.

To add a new source adapter, implement `_adapt_<source>` in
`engine/neuralweb/evidence_clock.py` following the existing adapter pattern, add
it to the `sources:` block in `config/evidence_clock.yml`, and call it in `build()`.

---

## Caution: "validated" strings from the experiments adapter

`readiness.maturation` and `readiness.status` values in clock rows are copied
verbatim from the experiments registry (`data/experiments/registry_seed.json`).
That registry may contain the word "validated" as a descriptive string (e.g.
`maturation: "partially validated"`).

**EC-R5 (no site/ copy) is the load-bearing guard.** The artifact is only ever
served through the authed admin console, so `scripts/check_validated_claims.py`
(which scans `site/` for the word "validated") does not fire on it.

Any future v2 that renders clock rows to `site/` **must** strip or rephrase
`maturation`/`readiness.status` fields before writing to site — otherwise
`check_validated_claims.py` will hard-fail CI.

---

## Explicit non-goals

The evidence clock:

- Does **not** promote any experiment, candidate, or claim
- Does **not** retire or change the status of any source record
- Does **not** originate any signal, score, or rank
- Does **not** replace or duplicate any source system
- Does **not** run any LLM
- Does **not** write to any source ledger (`governance.jsonl`, `claims.jsonl`, `registry_seed.json`, etc.)
- Does **not** ship a `site/` copy — this artifact is behind the authed admin console only

---

## Wiring

| Component | Location |
|---|---|
| Config | `config/evidence_clock.yml` |
| Core logic | `engine/neuralweb/evidence_clock.py` |
| CLI builder | `scripts/build_evidence_clock.py` |
| CI checker | `scripts/check_evidence_clock.py` |
| Reviews ledger | `data/neuralweb/evidence_clock_reviews.jsonl` (operator-maintained) |
| Nightly step | `.github/workflows/daily.yml` — engine job, after `research_factory_monitor` |
| Synapse registration | `config/synapse.yml` — `evidence-clock` + `evidence-clock-reviews` |

Run the builder manually:

```bash
python -m scripts.build_evidence_clock
```

Run the CI check:

```bash
python -m scripts.check_evidence_clock
python -m scripts.check_evidence_clock --selftest
```
