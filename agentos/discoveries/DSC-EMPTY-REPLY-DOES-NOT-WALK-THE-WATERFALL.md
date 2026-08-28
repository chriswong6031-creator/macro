---
key: EMPTY-REPLY-DOES-NOT-WALK-THE-WATERFALL
kind: landmine
confidence: verified
verified_at: 2026-08-27
verified_by: >
  Three-rung probe against the real engine/llm_auth.make_call with a stub rung 1
  returning stop_reason='end_turn' and content=[] — rungs called ['codex'], text
  None, served_by 'codex'. Then the same shape through master_brain._call_model
  after the local fix — rungs called ['codex','codex','oauth'], brief written.
  Pinned by tests/test_master_brain_ladder.py::test_call_model_empty_reply_falls_through_to_the_next_rung
  (10 passed).
claim: >
  engine/llm_auth.make_call advances the provider waterfall ONLY on an exception.
  A call_fn that RETURNS (None, "empty_reply") — a 200 carrying no text blocks —
  is taken as that rung having served: make_call returns immediately with that
  rung's name, never calls mark_dead, and never tries rungs 2..N. Measured with
  three healthy rungs where rung 1 returns an empty completion: rungs actually
  called = ['codex'], returned text = None, served_by = 'codex'. Every
  caller-level retry therefore re-enters the ladder at rung 1 and draws the SAME
  rung again, so a provider stuck returning empty text blanks the artifact with
  healthy providers sitting behind it. This is invisible to the ladder's own
  evidence: the ai_costs ledger and provider_health both record the rung as
  having been asked, and nothing anywhere says the other rungs were skipped.
falsifier: >
  Change the success branch of llm_auth.make_call (the `return text, reason, name`
  after call_fn succeeds) to treat a None text with a retryable reason as a rung
  failure and continue the loop; or wire the existing, currently-unused
  llm_auth.providers_after / empty_text_retry_plan helpers into the callers. Either
  makes rungs 2..N reachable on an empty reply and falsifies the claim as stated.
  Re-run the three-rung probe: rungs called becomes ['codex','oauth'].
so_what: >
  Any lane that leads its ladder with a provider whose empty-reply mode is a
  RETURN rather than a raise inherits a single point of failure that the ladder
  was supposed to remove. Codex is partly protected by accident —
  codex_provider raises CodexProviderError("Codex provider returned an empty
  response"), which converts empty into an exception and does fall through — but
  the oauth/anthropic rungs are not: llm_auth itself documents a thinking-only
  response class that yields no text blocks. The seed-nudge retry does not help a
  Codex-shaped rung either, because its adapter takes **kwargs and silently
  ignores unknown ones, so the nudge cannot change its output. master_brain works
  around this locally: it retries the same rung ONCE (the nudge is what recovered
  the China lens on 2026-07-20) and then calls mark_dead on the serving rung so
  the remaining attempts fall through — measured ['codex','codex','oauth'] with
  the brief written. That workaround lives in master_brain._call_model only; every
  other make_call caller in the repo still has the original behaviour.
evidence: >
  Probe against the real llm_auth.make_call with three stub providers (rung 1
  returning stop_reason='end_turn' and content=[], rungs 2-3 healthy):
  "rungs actually called : ['codex'] / returned text : None / reason : empty_reply
  / served by : codex". After the master_brain-side fix, the same shape through
  _call_model yields ['codex','codex','oauth'] and a written brief; pinned by
  tests/test_master_brain_ladder.py::test_call_model_empty_reply_falls_through_to_the_next_rung.
scope:
  - macro
  - engine/llm_auth.py
  - engine/master_brain.py
discovered_at: 2026-08-27
discovered_by: claude/aibrief-provider-ladder
---

## Why this is not visible in the usual places

A rung that raises leaves a `provider_health` row with an `error_class` and a
`mark_dead` entry; the waterfall moves on and the ledger names whoever finally
served. A rung that *returns* an empty reply leaves a row that is indistinguishable
from a normal attempt, and the artifact simply degrades. So the two questions an
operator would ask — "did the ladder fall through?" and "was the ladder even
built?" — both answer misleadingly: the ladder WAS built with every rung present,
and it did NOT fall through, and neither fact is wrong.

Related: [[DEC-BRIEF-LANES-PIN-THE-MANDATED-RUNG-ORDER]].
