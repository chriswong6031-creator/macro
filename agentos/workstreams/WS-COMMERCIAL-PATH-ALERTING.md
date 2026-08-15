---
key: COMMERCIAL-PATH-ALERTING
title: Commercial-path alerting (GATE-4)
objective: >
  A human-watched channel is paged for Stripe webhook silence or errors,
  checkout create failures, require_user 502 spikes, LLM daily spend above
  threshold, and brain_gateway quota fail-open — using the existing sentinel
  Telegram/Discord/email transport, with every condition proven by synthetic
  injection. Done when those detectors ship, the unit is armed on the
  freshness timer, and DETECT+MESSAGE are green; live DELIVER is PASS or an
  honest SKIP if credentials are absent.
status: active
program: shared-auth-entitlements
repos: [macro]
owner: ops
class: build
blast_radius: reversible
ambiguity: specified
owns_paths:
  - lib/commercial_path.py
  - scripts/commercial_path_sentinel.py
  - tests/test_commercial_path_alerts.py
  - app/deploy/macro-sentinel.service
waves:
  - id: W1
    title: Detectors + emit points + sentinel reuse + synthetic proof
    status: in_progress
next_action: >
  Merge the isolated GATE-4 PR and confirm /etc/macro-sentinel.env has a
  human-watched channel if DELIVER was SKIP in the prove receipt.
decisions:
  - DEC:COMMERCIAL-PATH-REUSES-SENTINEL-TRANSPORT
do_not_redo:
  - "Do not add Datadog/Sentry/PagerDuty or any new observability vendor — GATE-4 forbids it and the sentinel transport already exists."
  - "Do not give commercial-path its own systemd timer; it rides macro-sentinel.service so a freshness outage and a money-path outage share one dead-man box."
  - "Do not page on an empty ledger (a quiet new box is not webhook silence)."
landmines:
  - "Type=oneshot stops later ExecStart on the first non-zero. Commercial-path is ExecStart=- and FIRST so neither pass can skip the other; freshness still owns unit status."
  - "admin/alerts.py and admin/key_alerts.py are the market-signal rail, not the ops page. Do not dump commercial alarms into the alerts tab."
---

Launch-gate home: `research/MASTERMIND_LAUNCH_GATES.md` GATE-4 and
`research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md` WS-4. Isolated from the
other Wave-1 lanes.
