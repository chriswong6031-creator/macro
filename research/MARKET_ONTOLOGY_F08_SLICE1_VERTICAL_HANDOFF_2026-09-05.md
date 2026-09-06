# F08 Slice 1 — bounded vertical handoff (commissioning-ready; execution gated on Sol ratification)

**Operation:** `marketontology-f08-portfolio-alerts-20260826-fable-001` · carrier `C0BSBM78V1N/1788510682.177519` · macro#6819 · MAS-149
**Contract:** `research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md` (binding, §§0–13) · census merged `10619b0e`
**Authority:** records only until Sol ratifies the §1–§2 gates on the carrier. This packet grants no build/Ready/merge/deploy/trade authority; it makes the first build wave commissionable the moment ratification lands.

## §0 Acceptance gates (inline — the slice is NOT DONE UNLESS)

1. **End-to-end on real state, zero manual workarounds:** one real canonical holding (A1A `portfolio_positions` row) + one owner-native material event → deterministic event-to-position mapping → truthful evaluation with `last_attempt`/`last_success` displayed separately → visible in-product alert in the Terminal shell → one real delivery via `app/mailer.py` **or** a typed delivery failure on the alert row → drillback from the alert to the holding and the event evidence. A health-only backend PR without the real consumer does not complete the slice (Sol ruling, verbatim).
2. **Calm law:** with the evaluator stopped or failing, the monitoring surface renders "monitoring degraded — last successful check <t>" — proven RED-first before the happy path.
3. **Two-user production proof:** user B never sees user A's positions, alerts, fire events, outbox rows, or deliveries — both directions, in production, plus one degraded-case proof with real data.
4. **Privacy boundary:** no user-scoped field in `site/`, `data/`, R2, or any triage feed; CI grep proof in the PR body.
5. **Replay/idempotency:** re-running the evaluator over the same vintage fires nothing and re-sends nothing (`active=eq.true` guard + outbox `fire_event_id` + `email_log.idem_key`); crash-between-disarm-and-enqueue leaves the alert `pending`, never lost, never "delivered".
6. **Evidence matrix:** exact-head CI green; opus reviewer sign-off (privacy/risk) BEFORE the delivery channel is enabled; browser evidence dark/light × EN/ZH × 1440/390 with both art directions named per §0 G6 of the freeze; per-step visual crops against `mockups/refs/f08/` posted in the PR body; production receipt (delivery ledger row + live surface screenshot) in the closing comment.
7. **No new organisms:** the diff creates no second portfolio book, watchlist store, alert registry, scheduler abstraction, delivery service, or identity plane (freeze G1).

## §1 Entry gates (blockers to clear before or at wave start)

- **EG1 — Supabase migration namespace:** ONE Supabase project currently carries TWO hand-applied migration ledgers with colliding numbers (Terminal 0001-0010 vs Macro 0004-0008; two PRs each claiming "0011"), no runner. The slice's `alert_runs`/outbox DDL may not be written until the namespace is settled by its owner or an explicit numbering ruling is recorded. Escalate on the carrier if unresolved at wave start.
- **EG2 — C2 (suite evaluator):** V1 must locate/verify the implied Node suite-lane evaluator or record that `suite_event`/`suite_sequence` are admitted-but-dead; the slice itself does not touch suite types but the receipt substrate it builds must not paper over an evaluator that never runs.
- **EG3 — C12 (identity):** add the read-side normalization assertion (engine `cond.get("root")` vs route-canonicalized identity) or a one-shot audit proving no divergent legacy rows.

## §2 Slice scope and repository/path ceilings

**Terminal (charting-app) — evaluation, receipts, outbox, surface:**
- `ingest/alerts_engine.py` — add: two-phase run receipt (started/terminal rows), implicit held-position material-change evaluation over the A1A book (NO per-position `alerts` rows; never contends with the 50-row cap), fire-event minting, outbox write before/atomic-with disarm. The `active=eq.true` guard and one-shot semantics are frozen — extend, never replace.
- `supabase/migrations/<settled-number>_alert_runs_outbox.sql` — `alert_runs` receipt table + `alert_outbox` (both RLS'd, owner-scoped where user-bound) — gated on EG1.
- `terminal/app/api/alerts/**` — read additions only for receipts/outbox state; no new write semantics beyond the frozen re-arm.
- `terminal/components/**` + shell wiring — the in-product alert surface and drillback, composed per `mockups/refs/f08/` (design is fixed there; builder implements, does not redesign).
- **Ceiling:** no writes to `portfolio_positions` (F08 issues no holdings writes), no watchlist changes, no `mm.wls` reads.

**Macro — prefs, mailer wiring, off-render delivery drain:**
- `app/account_prefs.py` — alert prefs minimal set: email binding, one category opt-in, user timezone (IANA, explicit default), quiet hours.
- `app/mailer.py` — wire the alert-delivery message type; `idem_key` derived deterministically from `fire_event_id`; statuses stay `mailer.STATUSES` — no parallel enum, no new ledger.
- New drain entry point (script + cron/dag node OFF the render path) — drains the outbox, writes delivery receipts, send-time entitlement re-check fail-closed, quiet-hours defer in user tz.
- **Ceiling:** no `site/` writes from any user-plane module; user sends never touch `push_sent*.jsonl`; render budget untouched.

**Event source (owner-native):** one existing macro event owner (per census: event/K5/scenario owners; slice picks ONE concrete stream at commissioning, e.g. a ticker_alerts state-change on a held symbol) — read-only composition; direct-holding mapping only in slice 1 (deterministic; second-order/transmission mapping is V3, statistical factors are V2 — both OUT of slice).

## §3 Deterministic vs statistical

Slice 1 is 100% deterministic: existing owner-minted event → exact-ticker match against §5-folded positions → threshold-free material-change surface. No statistical scenario/factor/uncertainty content ships in this slice; any statistical output belongs to V2/V3 under their own ceilings and native-uncertainty law.

## §4 Routing (per ROUTE registry + root routing)

Contracts/adapters/evaluation + receipts + drain → Codex lane (or `builder`/sonnet where commissioned in-fleet); in-product surface implementation from the fixed compositions → Cursor lane or `builder`; privacy/risk adversarial pass → `reviewer` (opus) — mandatory before channel enable; no `designer` needed (design frozen in `mockups/refs/f08/`); separate reviewer from builder on every PR. First-pass child PRs return to the commissioning principal for review — no child self-merge of flagship UI.

## §5 Hostile-test subset owned by the slice (RED-first)

calm-empty vs outage vs no-coverage; evaluator-down degradation; fallback-to-persisted (`partial` + `source_asof` re-stamp); crash between disarm and enqueue (outbox drains, alert renders `pending`); replay run (no re-fire, no re-send); duplicate holdings rows folded in the touched-position readout; notification failure typed and retried; quiet-hours defer in user tz; lapsed entitlement send-time fail-closed; two-user isolation both directions; privacy-boundary grep on published artifacts.

## §6 Deliverable shape

Bounded PRs per repository (Terminal evaluation/receipts/outbox/surface; macro prefs/mailer/drain), each citing this packet + the freeze; acceptance is END-TO-END across them — the slice closes only when the §0 chain is proven in production with the delivery ledger row and the drillback screenshot in evidence. MO-PAID-027 and 085 move to their acceptance tests on this slice; 028/036 remain open for V2/V3.
