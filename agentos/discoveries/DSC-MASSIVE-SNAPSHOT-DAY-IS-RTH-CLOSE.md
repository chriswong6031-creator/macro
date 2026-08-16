---
key: MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE
claim: >
  Massive (Polygon) full-market snapshot `day.c` is RTH-close basis, equal to the
  grouped-daily unadjusted close to the cent, and the day aggregate freezes AT the
  16:00 ET close rather than absorbing after-hours prints — measured 2026-08-15 for
  session 2026-08-14: AAPL snapshot day.c=305.93 == grouped c=305.93, snapshot
  `updated`=1786752000000000000 ns = exactly 2026-08-14T20:00:00.000Z despite heavy
  AAPL after-hours trading. On non-session days the snapshot `day` continues to hold
  the LAST COMPLETED session, so a session-identity check on `updated`'s ET date is
  mandatory before trusting a snapshot day-bar.
falsifier: >
  On a live session shortly after 16:00 ET, poll
  GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL and compare day.c at
  16:01/16:05/16:20 against the next morning's grouped daily
  (/v2/aggs/grouped/.../{session}?adjusted=false): if day.c moves after ~16:05 or
  diverges from grouped by more than a cent, the freeze-at-close claim is false.
  scripts/measure_massive_close_parity.py --session <date> automates the grouped half.
so_what: >
  A same-day close reader may use snapshot day.c as a provisional RTH close in the
  first minutes after the bell (never lastTrade), must verify the row's session via
  the updated-stamp ET date (a Friday bar survives into Monday-16:01 reads), and
  should prefer grouped daily as the finalized basis once it returns rows.
kind: data
verified_at: 2026-08-15
verified_by: "live curl probes, session 2026-08-14: grouped 12,424 tickers; AAPL/BRK.B/TSLA cross-checked; recorded in DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK evidence"
scope: ["macro", "breathing-platform", "engine/close_pass/", "collectors/massive_*"]
confidence: verified
---

One nuance carried with the claim: the equality was measured on a WEEKEND read of a
COMPLETED session. The first minutes after a live close (does day.c include the
closing auction immediately? how long until grouped returns rows?) are exactly what
Monday's live measurement must pin — the adapter treats snapshot reads as
finalized=False and grouped reads as finalized=True for this reason.
