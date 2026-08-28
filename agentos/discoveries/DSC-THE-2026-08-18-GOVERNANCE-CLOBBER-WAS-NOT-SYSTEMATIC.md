---
key: THE-2026-08-18-GOVERNANCE-CLOBBER-WAS-NOT-SYSTEMATIC
claim: >
  Commit `f66a44bde106` ("engine: regime update 2026-08-18", dashboard-bot) is the ONLY
  commit in the entire git history of `data/neuralweb/governance.jsonl` that removes a
  line. It replaced the cortex evaluator's article3_review for Q1 (event_id
  `4f984c71679385bd`, ts 2026-08-18T11:26:15Z) with an `altdata_brain.article3_actionable_verdict`
  event stamped 11:20:17Z — i.e. a lane whose working copy was read BEFORE the evaluator
  appended wrote that copy back afterwards. The event is permanently lost; today's ledger
  carries 5 evaluator events (H1/H2/H3 on 08-04, H4/H5 on 08-10) and no Q1 event.
  Sweeping every contract-append-only neuralweb ledger for line removals returns four
  commits total, and the other three are benign: they are `machine_registry.jsonl` status
  flips written by the old in-place `_update_row_status` (79f45462b2a4 +3/-3 on 08-03,
  6870d97010e9 +2/-2 on 08-09, e687aabe8ccd +1/-1 on 08-18), each changing only the
  `status` field of the row it rewrote. `engine/neuralweb/governance.py::append_event`
  itself opens with mode `"a"`, so the append path has no read-modify-write window — the
  race was at the git/workflow layer, between two lanes in one nightly, not in the code.
falsifier: >
  Any second line-removing commit on `data/neuralweb/governance.jsonl` found by
  `git log --numstat --format="C|%H|%ad|%s" --date=short -- data/neuralweb/governance.jsonl`
  whose deletion count is non-zero, or an `append_event` implementation that stops using
  `open("a")`.
so_what: >
  Do NOT build a general anti-clobber guard for governance.jsonl on the strength of this
  one event — the mechanism is not recurring, and the file's own writer is already
  append-correct. DO treat "a nightly lane committed a whole-file rewrite of an
  append-only ledger" as the actual hazard class: it is invisible to any instrument that
  inspects the file's content, because the surviving file is perfectly well-formed. The
  only detector is git numstat over the file's history, which is cheap; run that sweep
  before accepting any claim that an append-only ledger is intact. Note also that a
  registry whose status transitions REWRITE rows makes this sweep noisy — after the
  W7b-PR3 repair `machine_registry.jsonl` appends superseding rows instead, so future
  removals on that file are unambiguously clobbers.
kind: constraint
verified_at: 2026-08-26
verified_by: >
  `git log --numstat` sweep over data/neuralweb/{governance,machine_registry,hypothesis_inbox}.jsonl
  (4 removing commits total); `git show f66a44bde106 -- data/neuralweb/governance.jsonl`
  (the -/+ pair, 11:26:15Z removed / 11:20:17Z added); per-commit JSON diff of the three
  machine_registry commits confirming status-only field changes; read of
  engine/neuralweb/governance.py append_event (`with p.open("a")`)
scope:
  - mastermindx-market-intelligence/macro
  - data/neuralweb/governance.jsonl
  - engine/neuralweb/governance.py
confidence: verified
---

The audit recorded this as "one confirmed instance; systematicity unaudited", and the
answer is that it is a singleton. That is worth writing down precisely because the
instinct on finding a lost append is to harden the append path — and here the append path
was never the problem. `append_event` has always used `O_APPEND`; two concurrent appenders
would both have survived. What did not survive was a git commit whose tree contained a
stale copy of the file.

The detection asymmetry is the durable part. A clobbered append-only ledger looks exactly
like an intact one: valid JSONL, monotonic-ish timestamps, no gap that any schema check
could name. The Q1 event's absence is only visible if you already know it should be there
— which, in this case, we do only because the evaluator's own registry row recorded
`insufficient-n` on 08-18 while the ledger carried no matching review. That cross-artifact
disagreement, not the ledger itself, is what makes the loss detectable, and it is worth
preferring that shape of check (two artifacts that must agree) over any single-file
integrity guard.
