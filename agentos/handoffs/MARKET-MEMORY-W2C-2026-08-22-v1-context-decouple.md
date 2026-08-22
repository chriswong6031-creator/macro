---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/w2c-v1-context-audit-decouple
model: local
ended_because: ci_handoff
prs: []
decisions:
  - "DEC:W2C-V1-CONTEXT-OWNER-DECOUPLED-FROM-OPTIONS-AUDIT"
discoveries:
  - "DSC:OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL"
mission: >
  Restore W2C v1 owner replay and experience-timer arming by decoupling trusted
  Market Memory context publication from the Options Context Audit, without
  implementing Options Audit preregistration v2.
state_before: >
  v1 experience.timer was enabled but inactive/dead since 2026-08-21 04:03:05Z.
  Every macro-update tick died on macro-market-memory-context.service
  TimeoutStartSec=180 because project_market_memory_context.main() ran
  publish_live_audit after trusted projection. W2C registration does not consume
  the Options audit. M0D v2 remains installed and isolated.
changed:
  - path: scripts/project_market_memory_context.py
    what: Production main() publishes trusted context only; run_projection_cycle removed.
  - path: app/deploy/macro-market-memory-context.service
    what: InaccessiblePaths on options-context-receipts so the trusted unit cannot write the audit store.
  - path: app/deploy/macro-market-memory-options-context-audit.service
    what: Independent Options Context Audit oneshot using the existing CLI; same 180s/50% envelope; After=context without Requires.
  - path: app/deploy/macro-market-memory-options-context-audit.timer
    what: Hourly :20 UTC retry after trusted context :17; no Wants/Requires/PartOf.
  - path: app/deploy/update.sh
    what: Install/enable the audit unit; stop+rearm include it; ready loop and w2c_start_owner_chain do not.
verified:
  - claim: W2C v1 registration names the trusted macro-regime profile and does not name the Options audit.
    command: python3 -c "from pathlib import Path; p=Path('config/market_memory_spy_experience_registration.v1.json'); t=p.read_text(); assert 'market_memory.trusted.macro_regime_canary.v1' in t and 'options_context' not in t"
    result: assertion passed
  - claim: Production context writer no longer calls publish_live_audit.
    command: python3 -c "from pathlib import Path; t=Path('scripts/project_market_memory_context.py').read_text(); assert 'publish_live_audit' not in t and 'project_current_context' in t"
    result: assertion passed
unverified:
  - claim: After merge, canonical macro-update re-arms macro-market-memory-experience.timer to enabled/active/waiting with a future 04:30 UTC NextElapse.
    what_would_verify: >
      Deploy via normal updater. Do not systemctl start experience.service.
      Journal source success → trusted-context success → technicals success →
      w2c_reconcile_timer(); systemctl show the v1 timer.
  - claim: The independent Options audit remains not-healthy until preregistration v2.
    what_would_verify: >
      Audit unit Result/status and receipt HEAD; stale 1214-ref HEAD or rc 2 /
      timeout is honest. Do not mark it healthy to finish W2C recovery.
unresolved:
  - Production proof that v1 timer is actually waiting after deploy.
  - Options Context Audit preregistration v2 (WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2).
next_actions:
  - Merge this split and let canonical macro-update perform owner replay.
  - Confirm v1 experience.timer NextElapse is a real future 04:30 UTC.
  - Leave Options Audit v2 to WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2.
  - Tuesday 2026-08-25 grade M0D v2 independently if v1 is still unrestored.
do_not_redo:
  - Do not raise TimeoutStartSec or CPUQuota.
  - Do not widen _MAX_REFERENCES or window/evict owners.
  - Do not start v1 or v2 experience oneshots by hand.
  - Do not backfill missed v1 windows.
  - Do not recouple publish_live_audit into project_market_memory_context.main().
danger_areas:
  - reciprocal_market_memory_units_ready must stay v1-only; adding the new audit unit deadlocks first deploy.
  - w2c_reconcile_timer owns v1 experience.timer; do not add bare experience to the rearm loop.
  - M0D v2 units/contracts/04:00/04:07/04:32 must stay byte-unchanged.
---

Trusted context is the W2C owner. The Options audit is a different overdue owner.
