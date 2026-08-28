# GD-4A.1 Commission — CN/HK risk-forward-ledger freshness in the existing liveness lane

**Commissioned by:** Sol next-wave authorization 2026-08-20 (parallel to GD-3), via Fable
COO. **Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-4A.1 · **One PR** (shipped as PR
#6140, merged `e4f18b53e9d0`).
**Authority: watchdog/receipt only.** No policy authority, no ledger writes, no
auto-remediation, no new monitoring plane.

## Why

GD-4A proved the settled Asia-close lane advances `data/risk_radar_intl/cn_forward_log.jsonl`
and `hk_forward_log.jsonl` exactly once per settled session — but the July→August outage
showed a silent stall is invisible until a human looks: a killed/starved/mis-gated lane
leaves the same trace as a lane that never fired (the 2026-08-20 gate-classifier bug held
the ledgers stalled for hours with every conclusion SUCCESS). The GD-4A closeout
handoff's `unresolved` already named this: "No ledger-stall heartbeat exists on the CN/HK
forward logs."

## §0 Acceptance gates (not done unless)

1. **Extends the EXISTING independent GitHub-hosted liveness system**
   (`.github/workflows/nightly-liveness.yml` family — GitHub-hosted runner, off the
   self-hosted render pools). No new workflow *plane*: the check joins the existing
   lane's schedule/receipt mechanism. A new job inside that existing workflow is
   acceptable; a new workflow file is not, unless the census proves the existing lane
   structurally cannot host it — in which case STOP and return to Fable.
2. **One capability only:** detect a silent CN/HK forward-ledger stall within the next
   expected market session. Freshness law as adjudicated post-review (supersedes the
   draft's same-session-20Z alarm): each ledger's newest `asof` is graded against the
   calendar's expected session with `max_sessions_behind: 1` — a SUSTAINED stall on
   session D alarms at D+1's 20:00Z look; a single-session hiccup that self-heals stays
   quiet BY DESIGN (mirrors the boards' phantom-session budgets; `lib/cn_calendar`
   deliberately leaves extra State-Council closures un-encoded, so budget 0
   deterministically false-pages on weekend-anchored holidays — the adversarial review
   traced five dated false pages through 2029, plus the lane's late-fire tail and the
   ledger's own measured healthy-era misses).
3. **Session-calendar honest:** weekends and non-session days never false-alarm.
   Holiday behavior is declared in the check's receipt copy — no silent suppression, no
   new calendar dependency invented for this.
4. **Reads committed state only** (the checkout / git — the same trust boundary the
   liveness lane already uses). No VPS probing, no new secrets, no API surface beyond
   what the lane already holds.
5. **Alarm = the lane's existing receipt mechanism** (same annotation/notify idiom the
   liveness system already uses). No email/webhook/Slack additions.
6. **Idempotent and quiet:** a healthy day produces no noise beyond the lane's existing
   summary; a stall alarms once per lane fire, not once per check evaluation.
7. **Zero coupling to GD-3:** no imports from the live-envelope builder; the check reads
   the ledgers and the calendar only.
8. **Failure modes fail LOUD, not green, and never take the watchdog down:** missing
   file, empty ledger, unparsable tail → the existing INDETERMINATE semantics; a
   non-UTF-8 byte must degrade the one check, never crash the lane (review finding,
   fixed: `except (OSError, ValueError)`); "newest row" is `max(asof)` over the tail
   scan, never "last line" (the writer appends any absent asof to the end).

## Non-goals

No new monitoring plane, no auto-redispatch (prophet_rescue.py owns redispatch law), no
ledger backfill, no edits to asia-close.yml, no CN/HK engine edits, no alert product
surface (GD-8A remains gated on GD-3 production acceptance).

## Outcome (2026-08-21)

Shipped as PR #6140 (2 commits: build + adversarial-review repairs), merged
`e4f18b53e9d0` on concluded green. Live-verified the same hour: production
`nightly-liveness.yml` run 32435846087 on main concluded SUCCESS with
`cn_ledger=2026-08-20(0) hk_ledger=2026-08-20(0)` in the market-boards summary — the new
checks grading the real ledgers, healthy, no alarm.
