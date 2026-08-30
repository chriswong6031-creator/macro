---
key: SEAL-ABSTENTION-DISCARDS-ITS-OWN-TRANSCRIPT
claim: >
  The SPY REST source seal computes a full per-observation transcript
  (transport_error / no_bar / malformed / valid_bar) and then throws it away on the
  not_eligible path, logging nothing and persisting nothing, so the CAUSE of every
  Market Memory v2 abstention is unauditable forever. Scope note: this destroys the
  cause of an abstention only; it never renders a terminal gate classification
  unresolvable.
falsifier: >
  Read scripts/ingest_market_memory_sources_spy.py:474-482 - if the not_eligible
  branch persists or logs seal_state.transcript, this is refuted. Or run
  `find /var/lib/macro-market-memory/state/sources-spy-rest-v1 -type f | wc -l` on
  146.190.142.17 after a not_eligible run and get a non-zero count, or
  `journalctl -u macro-market-memory-source-spy-rest.service | grep -icE
  "transport|no_bar|malformed|observ"` and get a non-zero count.
so_what: >
  Do not open a source-plane investigation into WHY the v2 chain never admits by
  reading production receipts - the receipts do not exist and cannot be made to
  exist retroactively. Persisting the transcript must be fixed FIRST; only then does
  the next abstention answer the question from its own bytes. Equally, never read a
  Market Memory v2 abstention as evidence that the vendor had no bar - a run in which
  every poll was a transport error is byte-identical to one in which the vendor
  lawfully had nothing.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  scripts/ingest_market_memory_sources_spy.py:474-482 and _collect_seal_observations;
  production host 146.190.142.17 journal 2026-08-23..2026-08-27 (0 observation lines,
  0 transport/error matches) and empty sources-spy-rest-v1 store; MM-G0 wave under
  operation market-memory-full-capability-20260827-sol-001
scope:
  - macro
  - market-memory
  - scripts/ingest_market_memory_sources_spy.py
  - engine/neuralweb/market_memory_sources_spy.py
confidence: verified
---

# The seal's abstention receipt is the one thing it never writes

`evaluate_seal_predicate` (`engine/neuralweb/market_memory_sources_spy.py:216-260`) builds a
`transcript` listing every observation in `[seal_open, seal_close)` with its `observed_at`,
`status` and `digest`, and attaches it to the returned `SealState` — including on the failure
branches.

The caller then discards it. `scripts/ingest_market_memory_sources_spy.py:474-482`:

```python
if not seal_state.opportunity_eligible:
    return {
        "schema": "market_memory.spy_rest_source_intake_run.v1",
        "status": "not_eligible",
        ...
        "reason": seal_state.reason,
        "generation_id": None,
        "created": False,
    }
```

No `transcript` key. No store write. And `_collect_seal_observations` — which is the only place
that knows whether a poll was a `transport_error`, a `no_bar` or a `malformed` response — contains
no logging statement at all. The whole causal record dies with the process.

Measured consequence on production (2026-08-23 → 2026-08-27, five daily runs, three of them real
XNYS sessions): `sources-spy-rest-v1/` holds **0 files**, and the unit's entire retained journal
matches `transport|error|timeout|http|401|403|429|500|exception|retry` **0 times**. The only
surviving line is the summary `reason=no valid bar observation in seal window`, which is emitted
identically whether the vendor had nothing, the network failed, or the payload was malformed.

**Keep two layers apart.** This is *not* what made the 2026-08-25 W2C M0D gate
`RECEIPT_UNRESOLVED`. That state existed because the authentic host/store receipts had not been
recovered; once they were, the terminal gate classified cleanly as `ABSTAINED` from the
experience-v2 store bytes, and this landmine did not obstruct that at all.

What this landmine destroys is strictly one layer down: the question anyone actually wants answered
— *why* did it abstain — was gone at 04:05:00Z on the day it happened. A terminal disposition stays
recoverable from the store; a cause does not.

Full evidence bundle: `research/MARKET_MEMORY_MM_G0_AUG25_GATE_RECEIPTS_2026-08-27.md` §4.
