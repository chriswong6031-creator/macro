---
workstream: WS:COMMERCIAL-PATH-ALERTING
session: cursor/ws4-commercial-path-alerting-fddd
model: opus
ended_because: complete
mission: >
  Isolated GATE-4 / WS-4 commercial-path alerting PR. Reuse the existing
  sentinel Telegram/Discord/email transport. Page a human for Stripe webhook
  silence or errors, checkout create failures, require_user 502 spikes, LLM
  daily spend above threshold, and brain_gateway quota fail-open. Prove every
  alert by synthetic injection. If human-channel credentials are absent,
  prove transport construction locally and report the remaining delivery
  check honestly.
state_before: >
  origin/main at 6685df10 had no commercial-path ledger, no GATE-4 detectors,
  and no ExecStart besides scripts.freshness_sentinel on macro-sentinel.service.
  Money-path failures were log lines only.
changed:
  - path: lib/commercial_path.py
    what: Fail-soft JSONL emit + pure evaluate/inject/decide_alerts for the six GATE-4 kinds.
  - path: scripts/commercial_path_sentinel.py
    what: 30-minute pass that reuses freshness_sentinel transports; --inject and --prove-all.
  - path: app/deploy/macro-sentinel.service
    what: Leading ExecStart=- commercial pass so neither oneshot can skip the other.
  - path: app/billing.py
    what: Emit checkout.ok/fail and webhook.ok/error (payload, signature, handler).
  - path: app/main.py
    what: Emit auth.502 on the require_user upstream-failure path only.
  - path: engine/neuralweb/brain_gateway.py
    what: "Emit quota.fail_open next to the existing brain_gateway fail-open log lines; emit llm.spend from token usage."
  - path: tests/test_commercial_path_alerts.py
    what: Synthetic injection, local Discord webhook delivery, honest SKIP without credentials.
  - path: .github/ci/legacy-jobs.yml
    what: Wired the new suite as its own step on unrun-builders-stores, before the 40-file sweep.
prs: []
decisions:
  - DEC:COMMERCIAL-PATH-REUSES-SENTINEL-TRANSPORT
verified:
  - claim: "All six GATE-4 kinds DETECT and MESSAGE on synthetic injection."
    command: "python3 -m scripts.commercial_path_sentinel --prove-all --state-dir /tmp/commercial_path_prove"
    result: "DETECT=PASS MESSAGE=PASS for webhook_silence, webhook_errors, checkout_fail, auth_502, llm_spend, quota_fail_open."
  - claim: "DELIVER is SKIP when no human-channel credentials are present — not papered over as PASS."
    command: "python3 -m scripts.commercial_path_sentinel --prove-all --state-dir /tmp/commercial_path_prove"
    result: "DELIVER=SKIP (no human-channel credentials) on all six; REMAINING names /etc/macro-sentinel.env."
  - claim: "Each injected kind delivers a COMMERCIAL PATH message to a real local HTTP webhook."
    command: "python3 -m pytest tests/test_commercial_path_alerts.py -q"
    result: "Suite green, including parametrized local-receiver delivery and prove-all SKIP/PASS cases."
  - claim: "Emit sites fire on checkout fail, bad webhook signature, good webhook, require_user 502, and quota-dir fail-open."
    command: "python3 -m pytest tests/test_billing_webhook.py tests/test_collect_identity.py tests/test_brain_gateway.py::test_quota_dir_unavailable_emits_fail_open -q"
    result: "Green. checkout.fail / webhook.ok / webhook.error / auth.502 / quota.fail_open rows land in the tmp ledger."
  - claim: "agentos records validate."
    command: "python3 scripts/agentos.py validate"
    result: "0 error(s). New WS and DEC accepted."
unverified:
  - claim: "A credentialed Telegram/Discord/email send from the live VPS."
    what_would_verify: >
      On the live-plane box, with TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID or
      DISCORD_WEBHOOK_URL in /etc/macro-sentinel.env, run
      python3 -m scripts.commercial_path_sentinel --prove-all --send
      and confirm DELIVER=PASS plus a message in the watched channel.
unresolved:
  - "This cloud environment has no sentinel channel credentials. Local transport construction is proven; live delivery is the remaining operator check."
next_actions:
  - "Arm merge-on-green on the isolated PR and stay through merge."
  - "After deploy, confirm /etc/macro-sentinel.env has a human-watched channel and run --prove-all --send once on the VPS."
do_not_redo:
  - "Do not add an observability vendor."
  - "Do not give commercial-path its own systemd timer."
  - "Do not page on an empty ledger."
  - "Do not fold these alarms into admin/alerts.py (market-signal rail)."
danger_areas:
  - "Type=oneshot + a non-zero freshness exit used to skip a later ExecStart. Keep commercial FIRST with a leading '-'."
  - "WS-3 will touch require_user; the auth.502 emit is one fail-soft try-block on the 502 path — rebase, do not drop it."
  - "WS-2 will touch brain_gateway quota functions; keep the emit next to the existing fail-open log.error lines."
  - "WS-8 will touch the webhook handler; keep webhook.ok after success and webhook.error on the three failure paths."
---

Cold-stranger resume: the ledger is `lib/commercial_path.py`, the page is
`scripts/commercial_path_sentinel.py`, the unit is `macro-sentinel.service`.
Thresholds are env-overridable (`COMMERCIAL_*`). Prove command is in
`verified:` above.
