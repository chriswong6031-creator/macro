# GD-4A.1 Commission — CN/HK risk-forward-ledger freshness in the existing liveness lane

**Commissioned by:** Sol next-wave authorization 2026-08-20 (parallel to GD-3), via Fable
COO. **Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-4A.1 · **One PR** (may share the GD-3
PR only if the diff stays trivially separable; default is its own PR).
**Authority: watchdog/receipt only.** No policy authority, no ledger writes, no
auto-remediation, no new monitoring plane.

## Why

GD-4A proved the settled Asia-close lane advances `data/risk_radar_intl/cn_forward_log.jsonl`
and `hk_forward_log.jsonl` exactly once per settled session — but the July→August outage
showed a silent stall is invisible until a human looks: a killed/starved/mis-gated lane
leaves the same trace as a lane that never fired (the 2026-08-20 gate-classifier bug held
the ledgers stalled for hours with every conclusion SUCCESS). The handoff's `unresolved`
already names this: "No ledger-stall heartbeat exists on the CN/HK forward logs."

## §0 Acceptance gates (not done unless)

1. **Extends the EXISTING independent GitHub-hosted liveness system**
   (`.github/workflows/nightly-liveness.yml` family — GitHub-hosted runner, off the
   self-hosted render pools). No new workflow *plane*: the check joins the existing
   lane's schedule/receipt mechanism. A new job inside that existing workflow is
   acceptable; a new workflow file is not, unless the census proves the existing lane
   structurally cannot host it — in which case STOP and return to Fable.
2. **One capability only:** detect a silent CN/HK forward-ledger stall within the next
   expected market session. Freshness law: after a settled Asia session's expected
   advance window closes, each ledger's newest `asof` must equal that session's date;
   otherwise the check FAILS with a receipt naming the ledger, its newest `asof`, and
   the expected session date.
3. **Session-calendar honest:** weekends and non-session days never false-alarm.
   Holiday behavior is declared in the check's receipt copy (a holiday may false-alarm
   only if the repo has no calendar source the lane can already reach; if so, the
   receipt must say "holiday not modeled" — no silent suppression, no new calendar
   dependency invented for this).
4. **Reads committed state only** (the checkout / git — the same trust boundary the
   liveness lane already uses). No VPS probing, no new secrets, no API surface beyond
   what the lane already holds.
5. **Alarm = the lane's existing receipt mechanism** (same issue/failure idiom the
   liveness system already uses). No email/webhook/Slack additions.
6. **Idempotent and quiet:** a healthy day produces no noise beyond the lane's existing
   summary; a stall alarms once per lane fire, not once per check evaluation.
7. **Zero coupling to GD-3:** no imports from the live-envelope builder; the check reads
   the ledgers and the calendar only.

## Non-goals

No new monitoring plane, no auto-redispatch (prophet_rescue.py owns redispatch law), no
ledger backfill, no edits to asia-close.yml, no CN/HK engine edits, no alert product
surface (GD-8A remains gated on GD-3 production acceptance).
