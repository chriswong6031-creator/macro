# CN limit data heals — safe salvage disposition

Status: **partial salvage; adjusted-price limit tape STOP-SHIP**

Authority: `context_only_display_audit`

## Governing boundary

This reconciliation preserves
`research/CN_LIMIT_ALPHA_SOL_ADJUSTED_PRICE_STOP_SHIP_2026-08-09.md`.
Yahoo A-share history remains split-adjusted even when requested with
`auto_adjust=False`; it therefore cannot establish historical nominal CNY closes
or exact exchange limit bands. The proposed `limit_events` / `limit_tape`
backfill, its newcomer scanner, its coverage claims and its regression suite are
withdrawn and are not part of this change.

An exact legal-band verdict may be produced only from authorized, unadjusted
TuShare `daily` joined on the same ticker and trade date to vendor `stk_limit`,
with upper/lower prices compared by integer-cent equality and exchange-compatible
half-up validation. Until that plane is complete, no Yahoo-derived value may
rank, gate, size, alert, trade or establish numerical strategy authority.

## Salvaged heal: `china_zt_pool` trade-date semantics

The Eastmoney `stock_zt_pool_em` endpoint can clamp a request for a non-session
date to the most recently published session. The old collector stamped the date
it asked for, which could relabel Friday's vendor pool as Saturday or Sunday.
This is a provenance/date defect independent of any reconstructed legal band.

The retained collector changes:

- select request dates from a deterministic session calendar derived from the
  dates present in the local CN price store; price values are not consulted;
- keep `date` as the market session and `asof` as the UTC scrape day;
- reject a payload fingerprint already stored under a different session, which
  detects a clamped response without treating it as a new legal-band event;
- re-collect the newest session and replace that complete date slice wholesale,
  while leaving all other dates unchanged; and
- fill bounded recent session gaps without widening the vendor-call budget.

`collectors._drip.append_snapshot(..., replace_dates=True)` is opt-in. Its
default keep-last merge remains unchanged for per-name stores such as margin and
LHB, where a partial write must accumulate rather than replace the day's slice.

`scripts/heal_cn_zt_pool_dates.py` is the bounded repair/check tool. It refuses
ambiguous relabels rather than guessing. The committed `pool.parquet` is vendor
context only: inclusion in a vendor pool is not accepted as exact exchange-limit
evidence and cannot override the TuShare `daily` + `stk_limit` gate above.

## Retained proof

```text
pytest tests/test_china_zt_pool_dates.py tests/test_drip_append_only.py
python scripts/heal_cn_zt_pool_dates.py --check
```

The tests pin calendar resolution, clamp rejection, whole-slice replacement,
idempotence and the unchanged default behavior for other drip stores. CI routes
only those two retained suites. No engine, Prophet, Neural Web, candidate,
ranking or trading path is added.

## Explicitly withdrawn from the original branch

- `data/china_microstructure/limit_events.parquet` and `limit_tape.parquet`
  rewrites;
- the Yahoo-derived newcomer history scan in
  `scripts/build_china_microstructure.py`;
- `tests/test_china_limit_events_coverage.py`; and
- every event-count, breadth, precision, recall or continuation claim derived
  from that adjusted-price plane.

Those ideas remain research context only and must be rerun from the authorized
TuShare substrate before any quantitative verdict is restored.
