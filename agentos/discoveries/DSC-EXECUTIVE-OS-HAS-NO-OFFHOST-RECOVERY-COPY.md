---
key: EXECUTIVE-OS-HAS-NO-OFFHOST-RECOVERY-COPY
kind: landmine
verified_at: 2026-09-01
verified_by: >
  DR-A0 audit 2026-09-01: `tmutil listbackups` / `tmutil destinationinfo`, `which rclone
  litestream`, `crontab -l`, `grep -l -i backup /Library/LaunchDaemons/*.plist`, `git grep`
  transport sweep at Mastermind 524b6dc8, and grep of the world-readable deployed release
  a6fde004 — full command set in agentos/handoffs/WS-EXECUTIVE-OS-DISASTER-RECOVERY-2026-09-01.md
scope: [mastermind, executive-os]
confidence: verified
claim: >
  As audited 2026-09-01 (Mastermind master 524b6dc8071d6ea0b484819630e9de846e1df93e,
  deployed release a6fde00413979ede525033053bc09a495d6e5fbd), NO off-host,
  failure-independent copy of the Executive OS lifecycle database exists, and no
  mechanism that could create one is present anywhere reachable. The single copy lives at
  /var/db/mastermind-executive/control/db/data/control_plane/executive.sqlite3 (WAL, mode-700
  under _mastermind_exec) on the control Mac's boot volume. Absences verified independently:
  (1) repo — `git grep` at the pinned SHA for rclone/litestream/restic/borg/s3/b2/wasabi/
  sftp/rsync/off-host finds no Executive OS transport (all rsync hits are the trading-app
  VPS lane); (2) host binaries — rclone and litestream are not installed and ~/.config/rclone
  is absent; (3) scheduling — no launchd job in /Library/LaunchDaemons or ~/Library/LaunchAgents
  mentions backup, `crontab -l` is empty, the repo has zero StartCalendarInterval/StartInterval,
  and executive_service.py/executive_runtime.py contain zero backup references in the serve
  path — the `backup` control-socket command is on-demand only; (4) Time Machine — `tmutil
  destinationinfo` lists only a local pseudo-destination that fails to mount and `tmutil
  listbackups` reports "No machine directory found for host"; (5) mounted volumes —
  "WD 5TB" is personal media (92% full), "Mastermind"/"Worktrees" are working checkouts, and
  all are attached to the same host anyway. The existing backup primitive
  (control_plane/executive_backup.py: create_online_backup at :905 uses the SQLite Backup
  API with atomic tmp+rename, fsync, 0600, sha256 manifest mastermind.executive_backup_manifest/v1,
  immediate re-verify) writes only to backup_root=/var/db/mastermind-executive/control/backups —
  the same disk, same host, same service user. Whether even ONE local artifact exists there
  is unverifiable from a fleet shell (mode-700 + password sudo + no TTY).
falsifier: >
  A privileged `sudo ls -la /var/db/mastermind-executive/control/backups` (administrator
  ceremony) producing receipts of verified artifacts WITH off-host transport receipts;
  `grep -l -i backup /Library/LaunchDaemons/*.plist` or `crontab -l` turning up a
  backup-shipping job on the control host; `tmutil listbackups` returning real snapshots
  that include /var/db/mastermind-executive; or DR-O1/DR-D1 of
  WS:EXECUTIVE-OS-DISASTER-RECOVERY merging with a clean-host drill receipt (which retires
  this record rather than falsifying the audit).
so_what: >
  Treat the control Mac as a single point of TOTAL loss for Job/Attempt/Worker/Event
  history until WS:EXECUTIVE-OS-DISASTER-RECOVERY ships DR-O1: do not cite Time Machine,
  external volumes, release directories (code only), or the local backup_root as recovery
  layers. Never hand-copy the live DB file (WAL is part of persistent state; a filesystem
  copy can lose committed transactions) — the only lawful backup creator is the existing
  `backup` socket command. And when a future session needs host truth about Executive
  state, route it as a bounded administrator ceremony or an Executive-native read-only
  Job up front — fleet shells structurally cannot sudo, so plans that assume direct
  inspection of /var/db/mastermind-executive will stall exactly where this audit did.
---

Full command-level evidence: `agentos/handoffs/WS-EXECUTIVE-OS-DISASTER-RECOVERY-2026-09-01.md`.
Operation: mastermind-executive-os-offhost-disaster-recovery-20260830-sol-pro-001.
