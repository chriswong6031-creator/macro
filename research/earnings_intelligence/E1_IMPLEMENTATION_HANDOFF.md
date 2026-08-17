# E1 Implementation Handoff — Canonical truth convergence

**Not done unless** one real event (AAPL FY2026 Q3, call 2026-07-30) is bound from issuer identity + 8-K/Exhibit 99.1 + transcript through exact per-claim receipts into `event_workspace.v1` on the frozen §4.1 path, `engine.neuralweb.company_intelligence_reader.read_event_workspace` observes both the initial generation and a source-SHA correction, and the change is merged and live-checked.

A golden JSON fixture may pin bytes. It is **not** the consumer. Terminal Brief + dossier glance is **E1+E2 arc success**, not E1.

**Do not begin E2 in the same session.** Do not build UI.

Read first, in order: repo `AGENTS.md`/`CLAUDE.md`; `research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md` (§4.1 is the publication/read contract); `DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT`; `research/earnings_intelligence/E0_LINEAGE_AND_RUNTIME_MAP.md`; `research/EARNINGS_WAVE1_CONTRACT_FREEZE_2026-08-06.md`; this file.

---

## Flagship event

| Field | Value |
|---|---|
| Issuer | Apple Inc · real CIK `0000320193` · `company_id` `cik:0000320193` |
| Event | `evt_cik0000320193_2026q3_results` |
| Live alias today | `cie_98e318c37ec1a2a1f83c45e1` from `GET https://www.mastermind-x.com/api/company-intelligence/AAPL` (2026-08-16) |
| Call date | 2026-07-30 |
| Fiscal | FY2026 Q3 (June quarter) |
| Wire | `aapl-2026q3-call-record.html` was **404** on 2026-08-16 — admission is part of the job, not a skip |

Control grammar (do not make this the flagship): IEX Q2 FY2026 live Wire already has byte-exact quotes.

---

## Acceptance — not done unless

1. A test fails on current main and passes on the branch: minting AAPL Q3 under `AAPL` yields `evt_cik0000320193_2026q3_results`, and the existing `cie_98e318c37ec1a2a1f83c45e1` aliases to it (do not rewrite the `cie_` bytes).
2. The 8-K Item 2.02 for this print is bound by `(cik, accession)`, not `(cik, filing_date)`.
3. Every glance fact in `E0_GOLDEN_UNIVERSE_AND_ACCEPTANCE_CASES.md` §4 is either a `byte_replayed` span (release table or transcript) or a **typed absence**. Overlay prose must not remain the payload summary.
4. `claim_citations_pending` on the **v2** payload is derived. v1 CI contexts still validate only with `true`.
5. No beat/miss is emitted unless `basis_match` is true. Consensus may be `unlicensed_absent`.
6. Mutating the source SHA on a fixture amendment keeps the same `event_id`, sets lifecycle `corrected`, and changes `generation_id`. `read_event_workspace` returns the corrected generation. A golden JSON fixture used *as* that observer does not count.
7. Compact payload carries `authority=context_only` and Prophet flags all false.
8. Files touched ⊆ the E1 allow-list in the contract freeze. No Terminal UI. No Stage. No Prophet rank path. Do not mutate closed v1 `validate_context` / `validate_manifest`.
9. `python3 scripts/agentos.py validate` exits 0 if records change. Relevant tests green. PR, squash-merge, live check that `event_workspace.v1` for this event exists at `company_intelligence/event_workspaces/` and is readable by `read_event_workspace`.

---

## Implementation order

1. Identity: resolve `AAPL` as of 2026-07-30 to `cik:0000320193` via `IssuerRegistry` with a **real** CIK (not corpus synthetic).
2. Mint canonical event + alias index (`event_id_adapter`).
3. Bind 8-K + Exhibit 99.1; extract deterministic table facts (same-table revenue+EPS rule from `EARNINGS_WIRE_PROGRAM.md` L4).
4. Bind the Terminal transcript revision; attach exact claims already in the evidence grammar.
5. Emit `event_workspace.v1` via `write_workspace_generation` onto `company_intelligence/event_workspaces/`.
6. Prove `read_event_workspace` sees the payload, then replay a source-SHA correction through that same reader.
7. Stop. Do not open Terminal Brief or the dossier.

---

## Forbidden

Search, slides, Topics ML, relationships, Command Center, dossier JS rewrite, Qwen production calls, Prophet authority, using synthetic corpus CIKs, declaring done because CI still shows the overlay summary.

---

## Next sentence after merge

> Implement E2 exactly as frozen; render AAPL Q3 FY2026 from `event_workspace.v1` in the existing Terminal workspace and dossier glance.
