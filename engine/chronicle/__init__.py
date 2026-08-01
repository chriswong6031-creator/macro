"""engine.chronicle — market context timeline engine (Chronicle W0).

Deterministic event spine + short/medium rollups + context_pack over 7
committed sources (research-vault catalog, Prophet ledger closes, macro-release
reactions, earnings surprises, evidence-addressed earnings-call reads,
risk-band flips, regime flips). No LLM calls
anywhere in this package — W0 is 100% deterministic (house epistemics law: LLMs
may only de-escalate calibrated keys, never originate signals/scores).

See research/agentic_media/CHRONICLE_CONTEXT_TIMELINE_MASTERPLAN_BY_FABLE.md
for the full spec. Modules:

  schema.py        chronicle.event.v1 field allowlist + validation + id helper
  adapters.py       5 source adapters (research_vault, prophet_ledger,
                    macro_release, earnings, risk_band — the last reads the
                    real committed data/risk_radar/forward_log.jsonl history
                    directly, B6)
  earnings_calls.py nightly-only healthy-score projection + committed ledger
                    adapter (rebuild reads it but never rewrites it)
  state_log.py      forward-capture ledger + regime_flip derivation (adapter
                    6 — world_state.json has no committed dated history of
                    its own, unlike risk_band's source)
  spine.py          orchestration + events.jsonl read/write (deterministic,
                    idempotent, append-only via union-merge — see spine.py
                    module docstring)
  rollups.py         daily/weekly "streaming consciousness" tiers
  context_pack.py   pack() — the one symbol every consumer binds
  manifest.py        manifest.json payload assembly (stamped by governor.py)
  governor.py         build_and_write(root=None, rebuild=False) entry point
"""
from __future__ import annotations
