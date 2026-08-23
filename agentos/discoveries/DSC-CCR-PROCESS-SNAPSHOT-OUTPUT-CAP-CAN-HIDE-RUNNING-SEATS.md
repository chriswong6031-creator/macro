---
key: CCR-PROCESS-SNAPSHOT-OUTPUT-CAP-CAN-HIDE-RUNNING-SEATS
claim: >
  A bounded subprocess result can create a false negative when the producer's
  stdout legitimately exceeds the default capture cap: on the Chairman's M3
  Ultra, the prior 64 KiB runner cap truncated the process-table snapshot and
  hid every managed-browser process, making running seats read as stopped.
falsifier: >
  Re-run the dedicated max_bytes/process-snapshot regressions recorded in
  Mastermind PR #110 on a process table larger than 64 KiB with the old
  default cap and with the reviewed explicit larger cap. The claim is
  falsified if both return the same complete set of running managed-browser
  identities without truncation.
so_what: >
  Future high-volume observational probes must declare and test an explicit
  output bound sized for the real producer. A truncated bounded read may not be
  interpreted as authoritative absence or healthy emptiness, and raw process
  argv must still be reduced to non-secret booleans/known ids before leaving
  the adapter because it can carry live proxy credentials.
kind: landmine
verified_at: 2026-08-22
verified_by: "Mastermind PR #110 head 98c8834; live Wave-D smoke + dedicated max_bytes regressions"
scope:
  - mastermind
  - integrations/chairman_surfaces/runner.py
  - integrations/chairman_surfaces/chatgpt.py
  - WS:CHAIRMAN-CONTROL-ROOM
confidence: verified
---

This is not permission to make subprocess reads unbounded. The law is explicit,
reviewed bounds plus a discriminating truncation test for producers whose normal
output can exceed the package default.
