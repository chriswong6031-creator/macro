# BioCatalyst — two decisions only the operator can make

Written 2026-08-07 by the overnight autonomous session. Everything buildable is built. What
remains at the front of the critical path is not engineering — it is two acts of judgment that a
model is not permitted to perform for you.

---

## Decision 1 — Enable ClinicalTrials.gov **Record History** ingest

**This is the single highest-value action available to this program.** Everything downstream —
forward accrual, calibration, any clinical signal at any horizon — is gated behind it, and every
day it waits is a day of forward evidence that is never recorded and can never be recovered.

### The situation, measured

- Of the **8** registered BioCatalyst sources, exactly **1** is `production_ingest_allowed: true`.
- `clinicaltrials_gov_record_history` is `production_ingest_allowed: false`, with
  `rights_state: operator_review_required_before_enable`.
- **Every** outcome family's entry gate names it. `timing_slip` and `enrollment_site_change`
  require *only* that source; `trial_progression_termination` and `endpoint_readout` require it
  alongside `clinicaltrials_gov_v2`.
- Therefore **no outcome family clock can open**, and none was opened.

### Why nothing was opened anyway

Opening a clock over a source that cannot be ingested would accrue nothing while later reading
as *"accruing since 2026-08-07"*. That is exactly the fabrication this program exists to prevent,
so the machinery was built inert. The **activation receipt is the authority, not the config
file** — no edit to a YAML can claim an open clock.

### What your decision buys, precisely

Flipping `production_ingest_allowed: true` on `clinicaltrials_gov_record_history` **after a
rights review** opens three families on the next evaluation, **with no code change**:

- `trial_progression_termination`
- `timing_slip`
- `enrollment_site_change`

This is not a hope. It is pinned by
`tests/test_biocatalyst_m0a_clock_activation.py::test_the_trial_families_would_open_once_their_source_is_eligible`,
which runs the real evaluator against a widened registry and asserts `clock_state == opened`
with zero blockers.

`endpoint_readout` stays closed even then, on a second declared blocker
(`endpoint_alignment_review_queue_not_drained`). That queue is a separate, later piece of work.

### What it does NOT buy

It does not create a signal, a score, or any authority. It starts a **clock**. Forward accrual
needs roughly 12–24 months before a pre-registered test is possible — which is precisely why
starting it is urgent and why testing on the existing retrospective store is not an option
(that store is look-ahead-selected pre-2019 and cannot be cleaned).

### What the decision actually requires of you

A **rights review** of Record History: retention, redistribution, training and publication
disposition. The registry's own default is `unknown_rights_behavior: block_ingest_and_export`,
which is why it is off. This is a rights judgment, not a technical one, and it is yours.

---

## Decision 2 — Admit sponsor→ticker rows (or don't)

**Status:** `config/biocatalyst_sponsor_ticker_map.yml` ships **50 rows — 30
`candidate_unreviewed`, 20 `ambiguous_queued`, and zero admitted.**

A model may not admit an identity link. Under the house rule an LLM-suggested link is a
**candidate** until a human reviews it, so the map was built to make self-promotion impossible:

- `test_committed_map_carries_no_admitted_row_so_a_model_cannot_self_promote` fails if any
  committed row is `reviewed_admitted`.
- `test_reader_refuses_every_committed_row_and_never_returns_a_ticker` proves the reader returns
  unavailable-with-reason rather than a guess.

Where a sponsor was genuinely ambiguous — a subsidiary, a joint venture, a renamed entity — the
lane wrote `ambiguous_queued` with the competing candidates recorded rather than picking one.
**Twenty of fifty is a feature, not a shortfall:** a map with 30 honest candidates and 20 queued
ambiguities is worth more than 50 confident guesses.

### What admission buys

`BC-P1` post-selection context: after Prophet selects a name, BioCatalyst can explain that name's
trial and regulatory state. Until rows are admitted, that surface stays dark.

### What it does NOT buy, and must never

The map is **post-selection only**. It may not originate, rank, reorder, size, or gate a
candidate, and it is wired to nothing — not Prophet, not Neural Web, not any scoring path.
Effective intervals are mandatory so a later ticker reuse or rename cannot rewrite history.

---

## What needs no decision from you

Already merged and live: the whole Wave 0 substrate, the premium trial product (Trial Screen,
facets, Peer Matrix, replay-verified Change Tape, Decision Sentence, Temporal Braid), the v2
acceptance contract with a real trusted browser verifier, the operating packet producer and
Neural Web reader, and the bounded fixed-cohort transport (dark). Main is green for BioCatalyst
at **1061 passed**.

And the honest headline that no decision changes: **a contextual layer already exists and is
already live** — `engine/theme_clinical.py` aggregates trials to a theme, joins that theme to
baskets, and feeds Mastermind, reaching price with no per-company identity at all. It is
correctly fenced as display-tier and never scored. You have context today; you do not have an
authorized signal, and you will not have one before 2027 even in the best case.
