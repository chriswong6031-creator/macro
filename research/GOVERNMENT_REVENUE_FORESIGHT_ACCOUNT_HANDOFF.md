# Government Revenue Foresight — account handoff

Use `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` as the canonical product/architecture specification. This file is only the compact implementation checkpoint for resuming from another account.

## Current checkpoint

- Waves 1–4 are on `origin/main`: bounded USAspending award/action collection, first-seen SAM rail, bitemporal and receipt-bound ledgers, procurement workspace, premium three-pane UI, Award Tape, and display-only Neural Web/Prophet context.
- Wave 5 adds a separate content-addressed `government_revenue_dossiers.v1` artifact, byte-identical canonical/public twins, stable generated-award identity, bounded company/award/action APIs with generation-bound cursors, and a progressive premium award-book/action-tape UI.
- Wave 5 also adds the strict exact-recipient graph and independent absolute-dollar coverage contracts plus fail-closed resolver helpers. It deliberately ships without fabricated mappings; no discovery ticker or fuzzy company name becomes issuer proof.
- The live and generic render workflows now carry and verify `dossiers.json`; the projection fence rejects stale, malformed, non-canonical, or mixed dossier generations.
- Focused local checkpoint: 133 Government Revenue API/build/contract/UI/projection/recipient-graph/DAG/Synapse tests pass; the repository claims fence and a real local API/browser award-book/action-tape smoke test also pass.

## Truth and authority fences

- This is an original clean-room implementation over official/public data, not copied competitor code or proprietary data.
- Government Revenue remains `display/context` only. It cannot rank, size, gate, add a candidate, originate a signal, or escalate one in Prophet/Neural Web.
- Collection-scope tickers are discovery queries only. Exact reviewed UEI/CAGE/USAspending identifiers plus point-in-time ownership evidence are required for issuer attribution.
- Obligations, current award value, potential ceiling, GAAP backlog, and revenue are separate semantics.
- The user-supplied competitor login must never be used or preserved.

## Resume sequence

1. Start a fresh `codex/` worktree from newly fetched `origin/main`; do not touch the shared dirty main checkout.
2. Read this file, the masterplan, repo `CLAUDE.md`, and `AGENTS.md` before editing.
3. Verify `https://mastermind-x.com/api/health`, `/government_revenue.html`, `/api/government-revenue/latest`, and one dossier API route.
4. Resume with **Exact Recipient Graph Activation**: add a reviewed empty-first graph/evidence artifact, wire resolver annotations and independent coverage into the receipt-bound award-event projection, preserve source events when the graph is absent/invalid, and expose only reviewed listed-company impacts.
5. Then activate the **SAM observed-lifecycle and exact notice→award lane** after installing a server-side `SAM_API_KEY` and completing a baseline. Never label a POP expiry estimate as an official recompete or infer follow-on lineage from text/date similarity.
6. Next parity lanes: saved searches/typed alerts/export, DoD budget→program→award transmission, IDIQ/vehicle seats, subawards, OTA/SBIR progression, and calibrated bidder/value/revenue-timing models with forward validation.

Every tracked change must complete the repo ship loop: focused tests, broad relevant tests, commit, PR, concluded checks, squash merge, `origin/main` evidence, deploy completion, production health, and changed-surface verification.
