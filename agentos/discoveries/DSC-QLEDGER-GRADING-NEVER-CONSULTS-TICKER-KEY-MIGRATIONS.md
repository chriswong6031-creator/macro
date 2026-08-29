---
key: QLEDGER-GRADING-NEVER-CONSULTS-TICKER-KEY-MIGRATIONS
claim: >
  qledger claim grading resolves scope.key to a price series LITERALLY, never through
  quality.ticker_key_migrations: engine/qledger.py grade path reads scope["key"] and
  prices it via engine/ai_desk._close_series, whose ladder is data/yahoo/<key>.parquet
  first, then the S&P-1500 breadth close-cache COLUMN named <key>, then China stores,
  with exactly ONE last-resort retry through lib.ticker_aliases.fetch_symbol when every
  direct read misses. Neither engine/qledger.py nor engine/ai_desk.py imports
  engine/ledger_identity, so a ticker_key_migrations row (SATS->ECHO shape) has ZERO
  effect on whether an open claim stays gradeable — that map serves only the
  track-record ingest guard, near-miss re-keying, and audit disclosure. Corollary
  measured 2026-08-28 during the EQR->VMRK migration: a PRESENT-but-frozen store or
  cache column SHADOWS every later rung of the ladder (a data/yahoo file frozen at
  08-13 or a ghost-bar breadth column wins over the live alias fallback), so open
  claims on a renamed key silently stop maturing rather than failing loudly.
falsifier: >
  engine/qledger.py or engine/ai_desk.py importing ledger_identity/load_migrations and
  mapping scope.key through it before pricing, or _close_series gaining
  staleness-awareness that skips a frozen direct hit and falls through to the alias
  retry. Either change makes a migrations row sufficient and open-claim re-keying
  unnecessary.
so_what: >
  A ticker rename with open qledger claims is NOT finished by adding the migrations
  row: either re-key the OPEN claims' scope.key to the new symbol (what the EQR->VMRK
  migration did — 12 open claims, claim_ids untouched, closed claims left as history)
  or keep an alias-reachable LIVE store under the old key forever. And when retiring an
  old key's stores, retire ALL of them plus any breadth cache column — leaving one
  frozen artifact strands every open claim on it invisibly (the frozen hit shadows the
  alias fallback; nothing warns).
kind: constraint
scope: [macro]
confidence: verified
verified_at: 2026-08-28
verified_by: >
  grep -rln ledger_identity engine/*.py (only track_record.py + the module itself);
  engine/qledger.py:2660 (grade_claim) -> :2701 (scope key read) -> :2459 (_fwd_ret) ->
  engine/ai_desk.py:189-208 (_close_series outer alias retry) -> :213-260
  (_close_series_direct ladder: yahoo store, breadth close-cache column, China);
  live probe 2026-08-28: data/yahoo/EQR.parquet frozen at 08-13 while
  data/yahoo/VMRK.parquet ran to 08-25, breadth _closes_cache EQR column carried
  0-volume 63.66 ghost bars 08-19..21.
---

Found while executing the EQR->VMRK key migration (the audit's delisted_printing
lane): the claims-continuity design question "does adding the migrations row keep the
open EQR claims gradeable" turned out to be a category error — the grading path has
never read that map. Related: [[BREADTH-TICKER-FIXUPS-PIN-THE-FETCH-SYMBOL-TOO]].
