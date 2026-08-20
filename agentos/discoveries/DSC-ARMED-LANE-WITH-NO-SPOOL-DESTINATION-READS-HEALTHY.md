---
key: ARMED-LANE-WITH-NO-SPOOL-DESTINATION-READS-HEALTHY
claim: >
  A fail-closed producer armed WITHOUT a configured output destination is
  indistinguishable from a healthy quiet lane on every instrument we own: Entry
  Radar W4 was armed 2026-08-18 and ran 215 passes (160 in-window) with ZERO
  envelopes ever written, because the writer unit's EnvironmentFile
  (/etc/macro-live.env) carried neither R2 credentials nor a spool dir while
  the READER (macro-api, /etc/macro-api.env) was fully configured for the R2
  prefix the writer never wrote — a same-host split-brain between two systemd
  units' env files. spool_then_commit withholds transitions fail-closed
  (correct), so no error, no alert, and no evidence accrue anywhere; "armed" was
  read as "producing" for two days. Separately observed same class: the pack
  lane refused 446 nomination events (08-19) for the same missing destination.
falsifier: >
  Any envelope appearing under the reader's prefix (R2
  mastermindx/live_flow/entry_radar_events) without the writer-env repair would
  disprove the destination gap; a monitoring surface that distinguishes
  "armed-and-writing" from "armed-and-withholding" (e.g. a spool-receipt
  counter exported per pass) would retire the blindness half.
so_what: >
  When a producer-consumer pair shares one host and the consumer sees nothing,
  check EnvironmentFile PARITY between the two systemd units FIRST — before any
  code theory. Arming is not producing: a commissioning is complete only when
  the first artifact lands under the READER's resolved source. Repair idiom
  that avoids credential handling entirely: a systemd drop-in giving the writer
  unit the reader's EnvironmentFile (same-source by construction; verify env
  NAME collisions first — here 0 collisions, only the four R2_* names
  referenced by engine/entry_radar/spool.py).
kind: constraint
confidence: verified
verified_at: 2026-08-20
verified_by: "engine/entry_radar/spool.py:129-160 (writer resolves env-only, no default) + engine/entry_radar/live_ledger.py:1134-1160 (spool_then_commit withholds on missing receipt); VPS receipt cat /var/lib/macro-live/state/prophet_lab/commissioning_receipt_2026-08-20.json (sha256 96badf18..., journal histogram 215 passes/160 in-window 'no_pack'; R2 events prefix 0 keys vs nominations 195)"
scope:
  - "macro"
related:
  - "WS:LIVE-ENTRY-RADAR"
  - "WS:PROPHET-US-V4-RECOVERY"
---

Found during the Sol Day-3 Prophet Operator Lab commissioning (Gate B). The
primary 08-19 blocker (pack builder exit 5 on an unadvanced daily store) was an
honest refusal that self-resolved; the destination gap beneath it had been
invisible since arming because every layer failed closed exactly as designed —
the design is right, the observability gap is the discovery. The staged repair
(drop-in + two path appends + API restart) is recorded in the commissioning
receipt and in WS:LIVE-ENTRY-RADAR's W4.1 day-3 comment; application is an
operator act because the session harness denies remote production config
mutation from any lane.
