# MKT-D02 — X Actuation: Outbox Contract + Computer-Control Posting Loop

**Department:** Broadcast (distribution) · **Priority: P0** · **Status: W0 SHIPPED #3056 (2026-07-19) — outbox contract (`engine/marketing/outbox.py`) + governor wiring behind `MARKETING_OUTBOX_ENABLED` + admin Outbox review page + `--dry-run` actuator + 54 tests; W1 blocked on operator accounts/host**
**Strategy doc (read it):** `research/MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md` (multi-account doctrine, computer-control posture) and `research/MARKETING_ZERO_FOLLOWER_TRACTION_PLAYBOOK_BY_FABLE.md` (what to post from zero followers).

## Why

Everything upstream (Content Studio → personas → charts → movers reach engine) currently ends at `data/marketing/content_plan.json` — a plan nobody executes. This docket is the hands: the outbox contract every producer writes into, and the actuator that logs into the six X accounts and posts, via Opus-driven computer control on warmed browser environments on the operator's M1.

## The six accounts (config truth: `config/marketing.yml desk_network`)

`flagship`, `receipts`, `theme_desk` (branded) + `research_a/b/c` (generic research). Each has a 9-type content **tilt** (signal/chart/education/macro/receipt/watchlist/event/mover/theme_list) — mixed content per account, not topic silos (operator law). Handles are unset until the operator creates the accounts.

## What already exists (do not rebuild)

- Content plan with per-account assignment + round-robin mover/theme-list injection (`engine/marketing/content_studio.py`, #2950 #3020).
- All rendering + copy validation (`chart_render.py`, `copywriter.py`).
- Computer-use + Chrome MCP tooling in the agent environment (tiered access; browsers are click-blocked under raw computer-use — use the Chrome MCP for browser actuation).

## Deliverables

### W0 — outbox + dry-run actuator (buildable today, no accounts)
1. `engine/marketing/outbox.py` — the **posting-queue contract** shared by nightly Content Studio and the D01 fastlane: item schema `{id, account, kind, text, media[], scheduled_at|immediate, priority, provenance, status}` with a status ledger (`queued → approved → posted|failed|quarantined`) as jsonl. Producers write items; only the actuator transitions status.
2. Wire Content Studio: after `content_plan`, emit outbox items for the day's plan (behind `MARKETING_OUTBOX_ENABLED`).
3. Admin **Outbox page** (route through the `designer` agent — user-facing surface): review queue grouped by account, media preview, approve/hold buttons writing a decisions file, posted-history with receipts. This is the operator's pre-launch review window.
4. `scripts/marketing_actuator.py --dry-run` — consumes approved items, renders exactly what WOULD be posted (text + media paths) into a run report; no network.
5. Tests: schema round-trip, status transitions are append-only, dedupe by id, per-account daily caps enforced (caps come from D08 Sentinel; hardcode conservative defaults `max_posts_per_account_per_day: 8` until Sentinel lands).

### W1 — live actuator (needs operator: 6 warmed X accounts, browser profiles, M1 host grant)
6. Per-account browser profile map (local config file OUTSIDE the repo, e.g. `~/.mastermind/x_accounts.yml` — handles, profile dirs; **credentials live only in the browser profiles**, never in files we read).
7. Actuator loop: for each approved item → select browser profile → Chrome-MCP navigate/compose/attach media/post → capture screenshot receipt → mark `posted` with the tweet URL. Failures → `failed` + quarantine after 2 attempts, never retry-spam.
8. Cadence + jitter: post-time jitter ±20 min, per-account spacing ≥45 min, respect D08 caps. Kill-switch `MARKETING_PUBLISH_ENABLED` checked every item.
9. launchd deployment on the M1 (traps in memory `mm-bot-launchd-reboot-survival`).

### W2 — engagement lane (gated by D08)
10. Reply-guy lane from the guerrilla doc: reply to large-account posts with a relevant chart receipt. Strict caps (≤3/day/account), Sentinel-gated, distinct from the posting loop.

## Acceptance

- W0: nightly run produces approved-queue items visible in the admin Outbox with media previews; dry-run report matches the plan 1:1; caps enforced in tests.
- W1: one real post per account end-to-end with screenshot receipt + URL in the ledger; kill-switch halts mid-queue; no credential material anywhere in the repo or logs.

## Traps

- **NO GIT for builders**; audit after every lane (two rogue-merge incidents in this program).
- X duplicate-content enforcement across our own 6 accounts is a real ban vector — do not post identical text on two accounts; the plan already tilts content, and D08 adds a cross-account near-dup gate. Coordinate, don't duplicate.
- Posting is **outward-facing and irreversible** — W1 first-live must run with the operator present (small approved batch), not autonomously.
- Browser automation: prefer Chrome MCP (DOM-aware) over pixel clicking; screenshots for receipts only.
