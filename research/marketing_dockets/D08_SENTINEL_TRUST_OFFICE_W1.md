# MKT-D08 — Sentinel W1: Pre-Publication Policy Gate + Ban-Risk Rails

> **Status: W1 SHIPPED 2026-07-19 (PR #3057).** `engine/marketing/sentinel.py` plan-level gate (near-dup/caps/lexicon/disclosure/cherry-pick/stale-receipts + exception queue), kill-switch hierarchy (`MARKETING_PUBLISH_ENABLED` default-off, per-account `disabled:`, fail-closed crash path), red-team appendix `D08_APPENDIX_X_POLICY_REDTEAM.md` sets the caps (config ships at the weeks_1_2 new-account tier), admin `/api/marketing/sentinel`, 63 tests. Come-back: first nightly bakes `data/marketing/sentinel_report.json`. **W2/D02 contract:** the actuator reads caps + ramp from `config/marketing.yml sentinel:` (no own constants), checks `publish_enabled()` + `sentinel_ok` per item, and refuses when report `plan_status != "pass"`. **Red-team R0 (operator go/no-go):** UI-automation posting itself is the pattern X's automation rules prohibit — read appendix §2 R0 + §6 kill criteria before D02 goes live. Cherry-pick detector is partial (fires only on zero losers shown).

**Department:** Sentinel (trust_office) · **Priority: P0 — build BEFORE first live post** · **Status: ready now, no operator input needed**
**Charter:** `engine/marketing/departments.py` id=`trust_office` ("Autonomous Trust, Policy & Red-Team Office", wave 0, 12 chartered engines — all stubs today).

## Why

Six AI-run accounts posting finance content is the highest-ban-risk configuration X knows. The operator's own words on the old copy: "will get us banned." `validate_copy` already kills invented numbers and banned vocab **per post**, but nothing today looks **across** posts, accounts, or time — and nothing owns platform-policy posture, financial-advice phrasing, or the quarantine path. Sentinel is the difference between a growth machine and six suspended handles.

## What already exists (do not rebuild)

- Per-post gate: `validate_copy` in `engine/marketing/copywriter.py` (numbers whitelist, banned vocab, dup-headline within a batch, cashtag rules, invalidation disclosure).
- Live-signal gates: `is_postable_signal`, `verify_signal_live` in `content_studio.py` (#2961 #2994).
- `settings.auditor_strict` knob in `config/marketing.yml`.

## Deliverables — W1

1. `engine/marketing/sentinel.py` — a **plan-level gate** run after `content_plan` and inside the D01 fastlane, over the full day's item set:
   - **Cross-account near-dup:** token-shingle similarity across all queued items; two accounts must never post near-identical text or the same media the same day (X coordinated-inauthentic-behavior vector). Action: rewrite-or-drop the later item.
   - **Cadence caps:** per-account posts/day, min spacing, cashtag frequency (same $TICKER ≤2/account/day), reply-lane caps. Config block `config/marketing.yml sentinel:` with conservative defaults.
   - **Financial-advice phrasing lexicon:** beyond validate_copy's banned vocab — "you should buy", "can't lose", "guaranteed", "get in now", price *targets* stated as promises. Educational/observational framing only.
   - **Disclosure law:** signal posts carry the standing disclosure line; receipts must include losers when the window had them (cherry-pick detector: receipts shown vs. graded ledger for the same window).
   - **Quarantine path:** violations → item status `quarantined` + reason, surfaced on the admin Outbox page (D02), never silently dropped. Human-exception queue file for the operator.
2. **Kill-switch hierarchy:** `MARKETING_PUBLISH_ENABLED` (global, D02 checks per item) + per-account `disabled: true` in desk_network config; Sentinel refuses the whole plan if the graded-receipts ledger is stale >7 days (we must not post "receipts" we can't back).
3. **Platform-policy red-team memo:** `research/marketing_dockets/D08_APPENDIX_X_POLICY_REDTEAM.md` — an opus `reviewer` pass over X automation/financial-content policies as of build date: what our loop does, where the risk concentrates (new accounts + links + cashtags + media volume), and the ramp schedule (weeks 1–2: low volume, no links; ramp links + volume only as accounts age). Cite sources; this memo sets the initial cap numbers.
4. Tests: near-dup caught across accounts, caps enforced, lexicon hits quarantined with reasons, stale-receipts refusal, kill-switch.

## Acceptance

- Running the nightly content plan through Sentinel yields a gate report artifact (`data/marketing/sentinel_report.json`: pass/quarantine counts + reasons) and the admin Outbox shows quarantined items with reasons.
- A seeded near-dup pair across two accounts is caught; a seeded "guaranteed winner" is quarantined; with `MARKETING_PUBLISH_ENABLED` unset the actuator posts nothing.

## Traps

- Sentinel **de-escalates only** — it can drop/quarantine/downgrade items, never originate or upgrade content (house LLM law applies to any LLM-assisted check here; the W1 gate above is fully deterministic).
- Don't fold Sentinel into `validate_copy` — per-post vs. plan-level are different layers; keep the seam.
- The ramp schedule is law once written: the actuator (D02) reads its caps from Sentinel config, not its own constants — remove the hardcoded defaults in D02 when this lands.
