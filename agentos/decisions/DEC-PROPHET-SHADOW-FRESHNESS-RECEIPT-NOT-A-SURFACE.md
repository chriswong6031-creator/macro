---
key: PROPHET-SHADOW-FRESHNESS-RECEIPT-NOT-A-SURFACE
question: >
  How does an append-only, zero-authority shadow discovery store satisfy the
  contract's deferred surface-freshness wiring ("absent vs stale" must be
  distinguishable) when a lawful zero-candidate session writes no rows — and
  does that wiring belong on the first-class surface artifact list that pages
  operators?
answer: >
  A per-market JSON receipt, not store bytes, and NOT a first-class surface.
  write_shadow writes data/prophet_shadow/<market>_discovery_receipt.json on
  every POST-GATE pass for a market with >=1 registration ({market, as_of,
  registry_state, written, definitions, challenger_failures, stamped_at});
  pre-gate refusals and zero-registration markets write nothing. The SOLE
  reader is scripts/check_surface_freshness.check_hk_discovery_freshness():
  warn-only (exit 0 always), on the HK session clock (lib.hk_calendar),
  emitting DISTINCT line-start annotations for absent / stale (HK-session
  gap) / substrate error / challenger failures, and staying SILENT on a
  fresh zero-written receipt. The receipt is deliberately excluded from
  _ARTIFACTS: it must never enter the generic SURFACE STALE loop or the
  push_ops_alert escalation spine.
rationale: >
  Lane B is append-only keep-first: a healthy session with zero candidates
  leaves the parquet byte-identical to a stale one, so any freshness read off
  store bytes is structurally blind to the state Sol's ladder most needs
  (registered-and-healthy-but-empty vs broken writer). The receipt advances
  on every lawful pass regardless of row count, making the five states
  (absent/not-wired, lawful zero, populated fresh, stale, producer failure)
  observable. Excluding it from _ARTIFACTS follows from zero authority: that
  list is the ops paging spine (a MISSING entry escalates severity=major via
  push_ops_alert), and a research store the contract forbids from touching
  any user-visible surface may not page an operator — the adversarial review
  (finding F1) showed the naive registration would have paged every US
  nightly between merge and the first HK-lane run. The HK clock matters for
  the same honesty reason: the generic loop measures gaps on the NYSE
  calendar, which mis-states HK staleness across divergent holidays
  (probed: 2 real HK sessions reported as 5 across the 2026 LNY closure).
alternatives:
  - option: Register the receipt in _ARTIFACTS like other freshness-checked
      artifacts
    why_not: Escalates a zero-authority research store onto the ops paging
      spine; double-annotates; measures staleness on the wrong (NYSE)
      calendar; fires a false severity=major page on every US nightly until
      the first post-merge HK session (review finding F1).
  - option: Freshness from hk_discovery.parquet max(session_date)
    why_not: Append-only + lawful zero rows means max(session_date) does not
      advance on a healthy empty session — stale and healthy-zero are
      indistinguishable by construction.
  - option: A new standalone health checker/plane for shadow stores
    why_not: >
      The Sol commission forbids creating another health/control plane; the
      existing sentinel module already owns surface freshness and has the
      specialized-check precedent (check_darkpool_population).
evidence:
  - "engine/board_shadow.py — _write_discovery_receipt; receipt only when
    _registrations_for(market) is non-empty, post-gate, fail-soft"
  - "scripts/check_surface_freshness.py — check_hk_discovery_freshness();
    hk_calendar clock; receipt absent from _ARTIFACTS"
  - "tests/test_check_surface_freshness.py — K-D8 four-state ladder tests +
    executed error/zero-collapse mutation arm; R11 calendar-divergence
    fixture (2026-04-07: HK expected 2026-04-02 vs NYSE 2026-04-06)"
  - "Opus adversarial review 2026-08-22, findings F1/F10 (escalation +
    NYSE-gap defects in the first build), repaired as R1"
  - "asia-close.yml commit step `git add data/ site/` — the receipt's path is
    tracked and reaches the sentinel's checkout; daily.yml neither writes nor
    cache-restores data/prophet_shadow/ (no W0b clobber vector today)"
affects:
  - WS:PROPHET-HK-CA-REVAMP
confidence: high
reversibility: easy
reversibility_detail: >
  Additive and consumer-free: nothing in production reads the receipt except
  the warn-only sentinel check. Moving the receipt onto the surface list (or
  retiring it) is a two-file edit with no schema migration; the store itself
  is untouched by any such change.
decided_by: fable-program-owner (WS:PROPHET-HK-CA-REVAMP autonomous grant 2026-08-20; wave commissioned by CEO Sol 2026-08-22)
decided_at: 2026-08-22
---

The receipt is liveness vocabulary, not authority: visible only to the
warn-only sentinel and operators reading job summaries. If a future wave
promotes shadow stores to user-visible surfaces, that promotion — not this
record — must re-adjudicate paging.
