# Grey Deer Risk Intelligence & Capital Protection — canonical index

**Program key:** `WS:GREY-DEER-RISK-INTELLIGENCE` · registry key `grey-deer-risk-intelligence`
(`config/mastermind_programs.yml`) · **Status:** architecture frozen 2026-08-19; no runtime
behavior exists yet. This README is an index only — it duplicates no architecture.

## Canonical files (this directory)

| File | Role |
|---|---|
| `GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md` | Sol's product/system/authority freeze. The architecture law. |
| `GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md` | Fable COO execution packet: wave packets GD-0..GD-11, laws, routing, acceptance, stop conditions. |
| `GREY_DEER_WAVE_GRAPH_AND_PR_ACCEPTANCE_MATRIX_2026-08-19.md` | Mechanical index: wave DAG, PR cards, path fences, collision fences, authority checkpoints. |
| `GD1_GROK_SCIENTIFIC_REPLAY_HANDOFF_2026-08-19.md` | GD-1A/GD-1B research protocol for the Grok operator (prereg-first PIT replay). Outputs land under `research/grey_deer/gd1/`. |

AgentOS records: `agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md`, eight
`agentos/decisions/DEC-RISK-*.md` / `DEC-PROPHET-RANK-*` / `DEC-REPAIR-*` / `DEC-PORTFOLIO-*` /
`DEC-SCOPED-*` / `DEC-AUTO-EXIT-*` records, and `agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-19.md`.

## Document precedence (on conflict)

1. Chairman instructions for this program.
2. `GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md` (the freeze).
3. `GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md` (execution hardening; may not change the freeze).
4. `research/DO_NOT_REBUILD.md` and durable AgentOS decisions.
5. Prophet V4 architecture freeze and regional Prophet decisions.
6. Live Entry Radar frozen research contract and its AgentOS workstream.
7. Canonical semantic/system registries (`config/mastermind_programs.yml`, `config/synapse.yml`, `docs/SIGNAL_BUS.md`, `config/lobe_charters.yml`, `config/reflexes.yml`, Chronicle, QLedger/Evaluation contracts).
8. Current merged source code and production evidence.
9. Older risk masterplans (`research/RISK_LAYER_DESIGN.md`, contagion/portfolio-risk-desk/market-risk-bridge docs) — substrate/evidence only.

The wave matrix is a mechanical index under 3. The GD-1 packet governs GD-1 research conduct under 2–3.

## Current next action (updated 2026-08-27, GD-3 acceptance handoff)

- **GD-1 closed:** GD-1A DONE; GD-1B ACCEPTED_NO_PROMOTION — zero GD-5 promotions
  (`DEC:GD1-ACCEPTED-NO-PROMOTION`). Dossier: `gd1/`. **GD-1C closed** DONE /
  BLOCKED_NO_PROMOTION (#6038): PIT membership unreconstructable; GD-5A/B/C stay CLOSED.
- **GD-2 DONE** (Gate 8 passed 2026-08-20). **GD-4A DONE** (real settled proof +
  idempotence, 2026-08-20). **GD-4A.1 DONE** (#6140 merged `e4f18b53e9d0`,
  live-verified run 32435846087; ledger freshness now graded by the liveness lane).
- **GD-3 built/merged/deployed/repaired** (#6144 `55d7ea02ce3e`; GD-3R1 clock-truth
  repair #6210 `e667ec39d176`; commission §0b carries Sol's seven clarifications) —
  wave OPEN on **WAITING_FOR_PRODUCTION_EVENT**. Verified 2026-08-27: the box runs
  the repaired bytes, the module executes on every fast-lane fire, and the
  closed-market clock laws hold in served production bytes. The only remaining step
  is the Gate-8-equivalent four-clock receipt, which requires an AUTHENTICATED
  browser during a US cash session (payload and consumer script are tier-gated by
  design). **Executable acceptance packet:**
  `agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-27.md` (lists what is already
  proven, so it is not re-proven). Never simulate the event; never modify the
  implementation unless the real witness falsifies it.
- **Gates:** GD-5A/B/C remain closed (GD-1C did not clear the promotion gate). GD-8/9
  gated on GD-3 production acceptance (Sol 2026-08-21). GD-6/7, Portfolio cutover: not
  authorized.

## Do not start (explicit)

No Grey Deer policy authority; no live Prophet sidecar behavior; no Portfolio cutover; no new
model training; no automatic exits; no re-weighting of legacy `engine/risk_state.py`. Authority
activations require the named checkpoints (Sol / Chairman) in the wave matrix §6.

## Naming note

"Grey Deer" elsewhere in this repo (`app/deploy/Caddyfile` — greydeercapital.com) is the brand
site, not this program. This directory is the only program home.
