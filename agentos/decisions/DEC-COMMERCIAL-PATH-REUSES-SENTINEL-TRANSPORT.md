---
key: COMMERCIAL-PATH-REUSES-SENTINEL-TRANSPORT
question: >
  Where should GATE-4 commercial-path alarms go, given the launch brief
  forbids a new observability vendor and the freshness sentinel already
  pages Telegram / Discord / email?
answer: >
  Reuse scripts/freshness_sentinel.py's send_telegram / send_discord /
  send_email and ride app/deploy/macro-sentinel.service (same
  EnvironmentFiles, same 30-minute timer). Emit fail-soft JSONL events
  from the API process into MACRO_API_STATE_DIR/commercial_path/; the
  sentinel pass evaluates them. Do not add a vendor, a second timer, or
  a third notify implementation.
rationale: >
  GATE-4's pass condition is "an alert reaches a channel a human watches",
  not "a new dashboard exists". The 2026-08-06 outage taught that alarms
  living inside GitHub are silent when GitHub is the thing that died; the
  freshness sentinel already lives on the VPS for that reason. Putting
  money-path pages on the same unit means one env file, one credential
  slot, and one dead-man box. A new vendor would violate the remediation
  plan Part XXX warning and create a second place credentials can be
  missing. A second timer would drift. Inlining a third requests.post
  would recreate the 12-sender census the neural-web scout already
  flagged.
alternatives:
  - option: Add Datadog / Sentry / PagerDuty
    why_not: Explicitly forbidden by GATE-4 and the remediation plan. Another credential, another vendor outage mode.
  - option: A new macro-commercial-sentinel.timer
    why_not: Splits the dead-man box. The launch gate asked to reuse the sentinel transport, not mint a sibling cadence that can be forgotten.
  - option: Page from inside the FastAPI process on each emit
    why_not: A webhook handler that talks to Telegram on the request path couples Stripe retries to a third-party POST. The ledger + 30-minute pass keeps emit fail-soft and the page off the money path.
  - option: Fold commercial checks into freshness_sentinel.py itself
    why_not: That file is stdlib-only on purpose (observer of last resort). Commercial events live under MACRO_API_STATE_DIR and are a different concern. A second ExecStart on the same unit reuses transport without mixing import closures.
evidence:
  - "research/MASTERMIND_LAUNCH_GATES.md GATE-4 — reuse the sentinel's existing Telegram/Discord/email transport"
  - "research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md WS-4 — Files/systems: app/deploy/macro-sentinel.service transport (reuse)"
  - "app/deploy/macro-sentinel.service EnvironmentFile=-/etc/macro-sentinel.env"
  - "scripts/freshness_sentinel.py notify_operator / send_telegram / send_discord / send_email"
affects:
  - WS:COMMERCIAL-PATH-ALERTING
  - shared-auth-entitlements
  - app/deploy/macro-sentinel.service
  - scripts/commercial_path_sentinel.py
confidence: high
reversibility: easy
decided_by: cursor-cloud-ws4
decided_at: 2026-08-15
---

Webhook silence is gated on a live money path (a checkout.ok or a prior
webhook.ok). A brand-new box with zero customers is not an incident.
The actionable silence is "Checkout created, no webhook followed".
