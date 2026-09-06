---
key: EXECUTIVE-OS-DISASTER-RECOVERY
title: Executive OS off-host disaster recovery and point-in-time restore
objective: >
  Loss of the control Mac or its disk no longer destroys the only recoverable copy of
  Executive lifecycle history: verified immutable backups flow through the existing
  Executive backup primitive to an encrypted off-host store in an independent failure
  domain, restore is explicit/offline and proven by a clean-host drill, and RPO/RTO/RCO
  are measured from real drills — with no second runtime and no automatic failover.
status: active
program: executive-os
p0: EXECUTIVE_OS
repos: [mastermind, macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - id: DR-A0
    title: Current recovery audit
    status: done
    next_action: >
      COMPLETED 2026-09-01, DO_NOT_REPEAT. Answer to the audit question: NO off-host,
      failure-independent copy of Executive lifecycle state exists. Evidence in
      agentos/handoffs/WS-EXECUTIVE-OS-DISASTER-RECOVERY-2026-09-01.md and
      DSC:EXECUTIVE-OS-HAS-NO-OFFHOST-RECOVERY-COPY. One residual unknown remains for a
      privileged follow-up inside DR-C0: whether ANY local backup artifact exists in the
      mode-700 backup_root (fleet sessions cannot read it; no scheduler exists, so the
      expected state is manual-only or empty).
  - id: DR-C0
    title: Recovery architecture and contracts (RPO/RTO/RCO, manifest identity, off-host trust model, key custody, retention, restore stages, no-auto-failover law)
    status: done
    depends_on: [DR-A0]
    next_action: >
      COMPLETED 2026-09-01, DO_NOT_REPEAT. Frozen at Mastermind
      research/MASTERMIND_EXECUTIVE_DR_V1_ARCHITECTURE_2026-09-01.md (merged 9ed1a2020246,
      PR #358). See DEC:EXECUTIVE-DR-V1-ARCHITECTURE. The privileged backup_root/DB-size
      census folded into the single Chairman ceremony (DR-PROMOTE) — production is inert,
      so the census stopped gating architecture.
  - id: DR-B1
    title: Immutable export vertical (one real backup + manifest + local verification + create-only artifact)
    status: done
    depends_on: [DR-C0]
    next_action: >
      COMPLETED_DO_NOT_REPEAT. control_plane/executive_dr.py + scripts/executive_dr_cli.py
      merged in Mastermind 9ed1a2020246 (PR #358); envelope mastermind.executive_dr_export/v1;
      cross-implementation openssl portability test-pinned.
  - id: DR-O1
    title: Off-host transport (least-privilege credentials, checksum-after-upload, immutable/versioned destination, no delete from routine writer)
    status: done
    depends_on: [DR-B1]
    next_action: >
      COMPLETED_DO_NOT_REPEAT for T-GH (GitHub release assets, create-only,
      checksum-after-upload on both assets, drill lane = draft releases via ephemeral
      GITHUB_TOKEN). T-R2 (S3/R2 immutable bucket) remains the preferred production
      target and is ceremony-gated (DR-PROMOTE); do not implement it as a second lane
      without the scoped credential existing first.
  - id: DR-R1
    title: Download and restore verifier (restore to new path; cryptographic + SQLite + Executive restore-verify + Event-tail checks; never overwrites live DB)
    status: done
    depends_on: [DR-O1]
    next_action: >
      COMPLETED_DO_NOT_REPEAT. fetch/decrypt (MAC-before-decrypt) + existing
      verify_restore_drill chain, merged in Mastermind 9ed1a2020246.
  - id: DR-L0
    title: Litestream compatibility falsifier (optional, separately gated; no production install without PASS and value over simpler backups)
    status: todo
    depends_on: [DR-C0]
  - id: DR-D1
    title: Clean-host disaster drill (simulated total loss, independent retrieval, exact release install, restore, health, external-effect reconciliation; measures RPO/RTO/RCO)
    status: done
    depends_on: [DR-R1]
    next_action: >
      AUTOMATED LANE COMPLETED_AND_SELF-SUSTAINING: .github/workflows/dr-drill.yml
      (weekly + dispatch, hosted runner, ephemeral key). First live run 33594694384
      SUCCESS 2026-09-02: ok=true, offline=false, logical_state_equal=true,
      fetch_to_verified_ms=1438, exactly one Draft release and zero git tags after.
      The FULL-CEREMONY drill (host provisioning + runbook stages, the real RTO
      measurement, and the live production DB's own export) is DR-PROMOTE ceremony work.
  - id: DR-OBS1
    title: Recovery health projection through existing OBS-F0/Steward seams (no new monitor store)
    status: todo
    depends_on: [DR-O1]
  - id: DR-PROMOTE
    title: Independent security/operability review, accepted runbook, scheduled cadence under existing host owner, durable records, real RPO/RTO/RCO receipts
    status: in_progress
    depends_on: [DR-D1, DR-OBS1]
    next_action: >
      Software side DONE: independent adversarial security review (opus; 3 blockers + 10
      majors found and fixed pre-merge), accepted runbook ops/executive_os/DR_RUNBOOK.md,
      weekly drill self-sustaining, durable records this file + DEC/DSC. REMAINING = ONE
      Chairman ceremony sitting (DR_RUNBOOK.md §ceremony): standing master key custody
      (password manager + 0400 host file; NEVER a GitHub secret), fine-grained PAT for
      executive-dr-vault, optional R2 scoped-token enrollment (T-R2), backup daemon
      arming (with, not before, the H0/P0 Executive arming), the live production DB's
      first shipped export + privileged backup_root/DB-size census, and the full-ceremony
      RTO measurement. Until then key-custody and bounded-credential ruler items are
      PARTIAL by design, and the drill lane is the only PROVEN_LIVE path.
discoveries:
  - DSC:EXECUTIVE-OS-HAS-NO-OFFHOST-RECOVERY-COPY
  - DSC:OPENSSL-ENC-SALTED-HEADER-DIVERGES-ACROSS-IMPLEMENTATIONS
decisions:
  - DEC:EXECUTIVE-DR-V1-ARCHITECTURE
landmines:
  - "The control Mac is a concentrated failure domain: it is simultaneously the Executive OS host, the production CI runner (mac-builder-3), the fleet session host, and the mount point for every external volume found. Nothing currently mounted counts as off-host."
  - "Time Machine on the control Mac is ABSENT, not merely stale: `tmutil destinationinfo` lists only a local pseudo-destination that fails to mount and `tmutil listbackups` reports no machine directory (verified 2026-09-01). Never cite TM as a recovery layer here."
  - "All live Executive state is mode-700 under service users (`_mastermind_exec`, `_mastermind_codex_*`); fleet shells have no TTY so `sudo` ceremonies are structurally unexecutable. Host-truth questions (backup_root contents, DB size) need a Chairman ceremony or an Executive-native bounded Job — do not report them as bare facts without such a receipt."
  - "SQLite WAL is part of persistent state: a filesystem copy of the live DB without the Backup API can lose committed transactions or corrupt recovery. The only lawful backup creator is the existing `create_online_backup` path (control socket command `backup`)."
  - "`backup` is an on-demand control-socket command with NO scheduler anywhere (no StartCalendarInterval/StartInterval in repo, no cron, no in-service timer, zero `backup` references in executive_service.py/executive_runtime.py serve path). A green backup capability is not a backup cadence."
  - "Litestream's MCP exposes restore/reset functions; never put them on a general model-facing tool surface. Recovery stays a bounded admin operation."
do_not_redo:
  - "Do not create a hot standby, automatic failover, second Executive runtime, replacement Event stream, or a second active database — REJECTED_BY_DESIGN for V1 by the operation packet."
  - "Do not make backup transport own lifecycle, retry decisions, provider-effect reconciliation, or restore-while-live."
  - "Do not create a second database as the recovery catalog; remote artifact+manifest is the identity source, any local catalog is a cache."
  - "Do not let a model prune backups; deletion is a privileged maintenance action with receipts."
  - "Do not install Litestream in production before the DR-L0 falsifier passes AND its value exceeds simply shipping verified backups more often."
next_action: >
  Execute the DR-PROMOTE Chairman ceremony sitting per ops/executive_os/DR_RUNBOOK.md
  §ceremony (standing key custody, vault PAT, optional R2, daemon arming with H0/P0, live
  DB first export + privileged census, full-ceremony RTO measurement). The weekly drill
  (dr-drill.yml) is self-sustaining; a red weekly drill is the program's regression
  signal. Operation carrier:
  mastermind-executive-os-offhost-disaster-recovery-20260830-sol-pro-001 (Chairman
  direct-delivery to the Fable COO session of 2026-09-01; Chairman full-completion
  override same date).
---

## Why this workstream exists

Executive OS is the single canonical lifecycle authority (Jobs, Attempts, Workers,
Events) for autonomous company work, stored in one SQLite database on the control Mac at
`/var/db/mastermind-executive/control/db/data/control_plane/executive.sqlite3` (WAL mode).
The DR-A0 audit (2026-09-01) established that every byte of that history has exactly one
copy, on one disk, on one host, readable by one service user — and that the well-built
backup/restore primitive that already exists (`control_plane/executive_backup.py`,
`scripts/executive_os_phase1c.py`: `backup`, `verify-backup`, `restore-verify`,
`restore-backup`) writes only to a same-disk `backup_root` and runs only when invoked by
hand. The program's job is to turn that primitive into failure-independent, verifiable,
explicitly-restorable recovery without creating a second runtime.

## Capability ledger (DR-A0, 2026-09-01)

| Capability | State | Evidence anchor |
|---|---|---|
| Executive SQLite lifecycle authority | PROVEN_LIVE (daemon KeepAlive on control host) | `/Library/LaunchDaemons/com.mastermind.executive.control.plist` |
| Online backup command (`backup`) | BUILT_NOT_PROVEN (code verified in deployed release a6fde004; no production execution receipt accessible) | `control_plane/executive_backup.py:905` |
| Backup verification (`verify-backup`) | BUILT_NOT_PROVEN | `control_plane/executive_backup.py:1079` |
| Offline restore verification (`restore-verify`) | BUILT_NOT_PROVEN | `control_plane/executive_backup.py:1109` |
| Offline restore (`restore-backup`, refuses while service marker/lock live) | BUILT_NOT_PROVEN | `control_plane/executive_backup.py:1278` |
| Local backup artifacts in backup_root | UNKNOWN (mode-700; no scheduler ⇒ expected manual-only or empty) | privileged census folded into the DR-PROMOTE ceremony |
| Scheduled backup cadence | BUILT_NOT_PROVEN on-host (nightly daemon ships DISABLED, armed at ceremony) + PROVEN_LIVE weekly CI drill | Mastermind 9ed1a2020246; run 33594694384 |
| Off-host copy (drill lane, full pipeline) | PROVEN_LIVE 2026-09-02 (backup→encrypt→ship→discard→fetch→decrypt→restore-verify→state-equality in a clean hosted environment) | run 33594694384 receipt |
| Off-host copy (live production DB) | NOT_BUILT until the ceremony's first shipped export (Executive OS itself is production-inert) | DR-PROMOTE next_action |
| Host-level backup (Time Machine) | BROKEN/ABSENT | `tmutil listbackups` → "No machine directory found for host" |
| Point-in-time recovery | PARTIAL (per-export point selection via content-addressed envelopes; no WAL-continuous PITR — DR-L0 still gated) | envelope contract §3 of the architecture doc |
| Clean replacement-host drill | PROVEN_LIVE for the automated clean-environment lane; full-ceremony host drill pending | run 33594694384 |
| Hot standby / automatic failover | REJECTED_BY_DESIGN (V1) | operation packet |
| Backup observability | PARTIAL (OBS-F0 records-only; its architecture doc has zero backup/recovery signals) | Mastermind PR #277 |

RPO today is unbounded (possibly no durable copy at all beyond the live file); RTO and
RCO are undefined (no runbook, no drill). DR-C0 freezes the targets.
