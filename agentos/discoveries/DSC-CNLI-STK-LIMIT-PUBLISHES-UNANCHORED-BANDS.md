---
key: CNLI-STK-LIMIT-PUBLISHES-UNANCHORED-BANDS
claim: >
  TuShare `stk_limit` routinely publishes a complete legal upper/lower limit
  band for an instrument whose prior close it does NOT republish, spelling the
  absent anchor as `0`. The collector treated that combination as a
  contradiction and raised, which destroyed the entire unit: measured on canary
  run 33037449419 (2018-01-02), `stk_limit` returned 3,466 source rows and
  landed 0, with `reason: daily_contract_failed` and
  `SpineError: stk_limit published upper/lower limits without an anchoring
  pre_close`. This is the THIRD instance of the vendor's zero-as-null spelling
  after `bak_basic.list_date` and `stk_limit.pre_close` itself, and the second
  time one descriptive field destroyed a whole unit's source accounting.
falsifier: >
  Re-run one bounded canary window covering a session and read the landed
  partition:
  `python3 -c "import pandas as pd,pathlib; S=pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine'; d=pd.read_parquet(S/'stk_limit/year=2018/month=01/part.parquet'); print(len(d), d['pre_close_cents'].isna().sum(), d['up_limit_cents'].notna().sum())"`.
  Falsified if zero landed rows carry a null `pre_close_cents` alongside a
  non-null `up_limit_cents` (meaning the shape does not actually occur and the
  original raise was correct), or if any ticker with a null
  `stk_limit.pre_close` also carries a positive-volume `daily` row for the same
  session — that would mean the shape is NOT confined to non-trading
  instruments and the repair is unsafe.
so_what: >
  The repair relaxes a FAIL-CLOSED check, so it needs its justification recorded
  rather than assumed. Two things make it safe, and they must never be
  separated.

  First, what remains checkable is still checked. The band's own ordering
  (`up_limit > down_limit`) is enforced even with no anchor, so dropping the
  anchor requirement does not leave the row structurally unexamined; the full
  three-way invariant `up_limit > pre_close >= down_limit` still runs whenever
  the anchor IS present.

  Second, and decisively, the case that actually matters stays fail-closed
  somewhere else. `build_canonical_event_substrate` raises when ANY
  positive-volume `daily` row lacks a non-null `stk_limit.pre_close`
  (`DSC:CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL` S3). So a security that really
  traded can never acquire a null anchor silently — the guard fires. Landing
  here is therefore safe BECAUSE that guard exists; anyone weakening or removing
  it must restore a check in this branch at the same time.

  A row that lands with a null anchor is not thereby event-eligible:
  `event_eligible = positive_volume AND source_limits_present`, and a
  non-trading instrument has no positive-volume daily row.

  The general lesson is about the direction of the error. The original raise was
  written from a MODEL of what a vendor "should" publish — the code comment
  literally asserted "this is NOT the non-trading case" — and the model was
  simply wrong. A fail-closed check derived from an assumed source contract is
  not conservative; it is a guess that fails loudly on first contact and can
  block an entire program. Fail-closed is the right default for an UNKNOWN
  disposition, not for a disposition you have merely never observed.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-27
verified_by: >
  Canary run 33037449419 (mode=canary, max_requests=12, 2018-01-02, ref
  claude/cn-limit-namechange-source-authority, which carries the #6494
  sentinel — confirmed by 4 occurrences of _stk_limit_price_or_sentinel_absent
  in that ref). Run log: `SpineError: stk_limit published upper/lower limits
  without an anchoring pre_close`. Unit record stk_limit/20180102 status failed,
  attempts 2, source_row_count 3466, landed_a_row_count 0,
  quarantined_unknown_row_count 3466. The same window landed namechange 5/5,
  suspend_d 239/239 and stock_st 73/73 terminal — the first live execution of
  either of those two endpoints.
---

# A fail-closed check derived from an assumed contract is still a guess

Found driving the acceptance canary after `DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY`
merged. The 10B ruling worked exactly as ordered — namechange reached 5 of 5
attempted year-units terminal with every accounting equation balanced — and the
window still failed, on an unrelated check written in the PREVIOUS repair.

The shape is worth remembering because it is self-inflicted and repeats. The
`stk_limit` sentinel repair (`DSC:CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL`)
correctly identified that the vendor spells an absent prior close as `0`, and
then added a NEW hard failure for the combination it had not yet observed —
absent anchor plus published band — reasoning from what a limit band "means"
rather than from data. One session later the vendor produced that exact
combination as its dominant shape and cost a whole unit.

Sibling instances of the same vendor idiom:
`DSC:CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL` and the `bak_basic.list_date`
sentinel folded into `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`. Before an
endpoint's first live run, audit every field the shared coercers touch — and
audit every raise you added for a combination you have never actually seen.
