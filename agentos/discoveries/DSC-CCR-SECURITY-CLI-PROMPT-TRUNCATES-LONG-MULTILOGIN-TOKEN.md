---
key: CCR-SECURITY-CLI-PROMPT-TRUNCATES-LONG-MULTILOGIN-TOKEN
claim: >
  On the Chairman host, repeated interactive uses of macOS `security
  add-generic-password ... -w` stored exactly 128 bytes of the current
  735-byte, three-segment Multilogin JWT, leaving only two segments. Keychain
  Access could store the full value, so the truncation occurred at the CLI
  prompt boundary rather than in Keychain storage.
falsifier: >
  In a human-controlled Terminal on the same current macOS build, run
  `/usr/bin/security add-generic-password` against a disposable service with a
  final bare `-w`, enter a synthetic ASCII JWT longer than 128 bytes, then use
  `python3` for a narrow shape-only readback. The claim is falsified if stored
  byte length and segment count match the full input across repeated trials
  without putting the value in argv or output.
so_what: >
  MAS-115 must not use the `security ... -w` prompt for long vendor tokens.
  Use the reviewed fixed-coordinate secret-owning Security.framework helper,
  keep the raw token outside argv/environment/shell/temp/log/model output, and
  validate the long JWT shape before storage. Do not create a generic secret
  service from this narrow helper.
kind: landmine
verified_at: 2026-08-24
verified_by: "repeated native CLI attempts with shape-only Keychain reads; Mastermind PR #139 long-token hostile tests and exact-head review"
scope:
  - mastermind
  - scripts/mas115_setup.py
  - scripts/mas115_keychain_store.py
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-115
confidence: verified
---

No credential value is recorded here. The observed byte length and segment
count are shape evidence only; the short-lived live credential remains an
action-time human-controlled input.
