---
key: MASSIVE-TICKER-CASE-IS-IDENTITY
claim: >
  Massive (Polygon) ticker symbols are CASE-SENSITIVE — a lowercase letter marks a
  DIFFERENT security on the same root, not a formatting variant — so upper-casing a
  vendor ticker before joining it to a universe silently mis-identifies the price.
  Measured 2026-08-15 on grouped daily for session 2026-08-13 (12,500 rows, 389 of
  them mixed-case): `TPC` = Tutor Perini common, c=94.67, beside `TpC`, c=16.98; and
  `BCPC` = Balchem common, c=177.14, beside `BCpC` = "Brunswick Corporation 6.375%
  Notes due 2049" (reference type SP), c=23.9999. Exactly 2 of the 389 collided with
  this repo's 1,763-name universe on both 2026-08-13 and 2026-08-14. Because a naive
  upper-casing join is last-row-wins, TPC came back at 16.98 (a 5.6x mis-price) while
  Balchem survived on PAYLOAD ORDER alone — the same code was wrong for one name and
  right for the other in a single response.
falsifier: >
  GET /v2/aggs/grouped/locale/us/market/stocks/{session}?adjusted=false and count rows
  where T != T.upper(); resolve any such T via /v3/reference/tickers/{T} and compare
  `name`/`type` against the upper-cased sibling. If every mixed-case row resolves to
  the SAME issuer and security type as its upper-cased form, case is formatting and
  this record is false. Re-runnable: scripts/measure_massive_close_parity.py --session
  <date> surfaces the mis-price as a parity disagreement against the store's own bar.
so_what: >
  Any join between a Massive/Polygon ticker and a repo universe must compare
  case-EXACTLY, folding only the vendor's dot-to-hyphen class-share convention
  (BRK.B -> BRK-B). Normalising case on EITHER side is the same defect from two
  directions. The one deliberate exception is a fail-CLOSED guard: engine/close_pass/
  massive_close.corp_action_tickers also carries the upper-cased spelling, because
  over-darking costs one name's coverage for one night while under-darking splices a
  split-day price onto a pre-split history (measured: zero corp-action rows were
  mixed-case and upper-cased into the universe on 2026-08-13 or 2026-08-14, so the
  extra spelling currently costs nothing). Ordering-dependent correctness is the
  hazard to look for, not the mis-price itself: it passes review and passes a
  spot-check.
kind: data
verified_at: 2026-08-15
verified_by: "live grouped-daily + /v3/reference/tickers probes for 2026-08-13 and 2026-08-14; caught by the parity battery in scripts/measure_massive_close_parity.py (1741/1741 agree within $0.005 after the fix, 1740/1741 before)"
scope: ["macro", "breathing-platform", "engine/close_pass/", "collectors/massive_*", "scripts/build_polygon_universe.py"]
confidence: verified
---

Related: [[DSC-MASSIVE-SNAPSHOT-DAY-IS-RTH-CLOSE]] covers the other half of the
same-day close contract (which RUNG to read); this one covers WHICH SECURITY the row
belongs to. Both are needed before a vendor close may be spliced onto a store series.

Not audited here, and worth a look: other joins in this estate that upper-case a
vendor ticker before matching. The pattern to grep for is `.upper()` applied to a
Polygon/Massive `T`/`ticker` field — `collectors/massive_stock_day.py`,
`scripts/build_polygon_universe.py` and the per-ticker parquet store all key on the
vendor's symbol, and a mixed-case symbol upper-cased into a filename is the same
collision with a durable artifact behind it rather than one night's board.
