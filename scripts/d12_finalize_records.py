"""ONE-SHOT D12 records/CI finalizer. Deleted by its workflow after use."""
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    s = p.read_text()
    assert s.count(old) == 1, (path, s.count(old), old[:100])
    p.write_text(s.replace(old, new, 1))


# Permanent P0 wiring: add the D12 suite to the one canonical Prophet P0 pytest command.
p = Path('.github/ci/legacy-jobs.yml')
s = p.read_text()
needle = "          tests/test_prophet_live_pack.py\n"
assert s.count(needle) == 1, s.count(needle)
s = s.replace(needle, needle + "          tests/test_prophet_live_pack_d12.py\n", 1)
p.write_text(s)

handoff = 'agentos/handoffs/WS-PROPHET-US-AVAILABILITY-2026-08-26-live-force-majeure.md'
replace_once(
    handoff,
    '  - "The pack builder\'s as_of is the tip of the loaded close series (build_prophet_live_pack.py:167). It is VISIBLE now (pack_ok) but NOT repaired — it will recur."\n',
    '  - "D12 is BUILT_NOT_PROVEN on operation prophet-us-d12-pack-tip-hardening-20260827-sol-001: the US pack owner quarantines non-session, not-yet-completed, and malformed last bars before BOTH pack-tip selection and gate submission. Shared armed_pack/CN semantics are unchanged. Do not call this PROVEN_LIVE until the first natural post-merge US pack + evaluator/dead-man proof."\n',
)
replace_once(
    handoff,
    '''next_actions: >
  1) PRIMARY NEXT: assign D12 to one bounded owner and repair the armed-pack `as_of`
     tip law so a non-session/same-day contaminated close cannot darken a whole future
     session. Return to Sol with exact mutation proof and live-path evidence; do not
     couple that repair to the recovered forward ledger.
  2) INDEPENDENT OPERATOR AUDIT: attribute the 2026-08-26T07:43:28Z R2 credential
     seeding and record the carrier/operator provenance without rotating or rewriting
     working credentials merely to make the record tidy.
  3) HELD INVESTIGATION: classify the partial 2026-07-30 tail after 17:20:56Z. Its
     existence is not replay/backfill authority; any recovery requires the same
     point-in-time evidence law and explicit authority that governed the seven Class-R
     sessions.
''',
    '''next_actions: >
  1) PRIMARY NEXT: after the D12 carrier merges and reaches the natural production
     pack path, hold the first US pack + live-evaluator proof. Require completed_through
     = the canonical last completed NYSE session; pack as_of must be a real completed
     session at or before that bound; any invalid_series_tip names must be explicit
     non-verdicts; the evaluator must consume the pack without global stale_pack
     darkness; and the external dead-man must report pack_ok=True. Do NOT manufacture a
     contaminated production store merely to force the negative case, and do NOT
     manually dispatch prophet-live.yml while the VPS timer is primary.
  2) INDEPENDENT OPERATOR AUDIT: attribute the 2026-08-26T07:43:28Z R2 credential
     seeding and record the carrier/operator provenance without rotating or rewriting
     working credentials merely to make the record tidy.
  3) HELD INVESTIGATION: classify the partial 2026-07-30 tail after 17:20:56Z. Its
     existence is not replay/backfill authority; any recovery requires the same
     point-in-time evidence law and explicit authority that governed the seven Class-R
     sessions.
''',
)
replace_once(
    handoff,
    '  - "D12 remains unreproduced: the 2026-08-26 pack was clean (0 names ahead of as_of), so the mis-stamp mechanism is proven from code + journal but its upstream trigger is not identified."\n',
    '  - "The historical D12 contamination SOURCE remains unreproduced/unattributed: the 2026-08-26 pack was clean. The repair itself is discriminator-proven against Saturday, future-session, and NaT hostile inputs; no contaminated production store was manufactured for proof."\n',
)
replace_once(
    handoff,
    '  - "D12 ownership: the armed pack\'s as_of inherits the close-series tip (build_prophet_live_pack.py:167). Visible now via pack_ok; unrepaired and will recur."\n',
    '  - "D12 production acceptance: ownership and implementation are resolved on operation prophet-us-d12-pack-tip-hardening-20260827-sol-001, but capability state remains BUILT_NOT_PROVEN until the first natural post-merge pack/evaluator/dead-man proof described in next_actions."\n',
)

research = 'research/PROPHET_US_LIVE_FORCE_MAJEURE_2026_08_26_EVIDENCE.md'
replace_once(
    research,
    '''**Proposed repair (NOT built — needs an owner and a ruling).** `as_of_date`
should refuse a tip that is not a completed NYSE session rather than propagate one
series' MAX, using the calendar already imported by
`live_states.last_completed_session`. This preserves the docstring's intent (a
stale store still reports honestly stale) while making an impossible date
unrepresentable. It is pinnable without a live reproduction:

> feed `as_of_date` a series set in which one series' last bar is a Saturday and
> assert the returned tip is the last **session**, not the Saturday.

Deliberately not done in this program: it edits the nightly pack path, this
session could not reproduce the trigger, and PR #6464 has already told Sol the
defect needs an owner. PR #6464 makes it *visible* (`pack_ok` on `/api/status`,
graded by the dead-man) so the next occurrence pages instead of silently darkening
a session.
''',
    '''**D12 repair implemented — BUILT_NOT_PROVEN (2026-08-27).** Operation
`prophet-us-d12-pack-tip-hardening-20260827-sol-001` confirmed the proposed direction
but found one important correction: capping only `as_of_date` is insufficient.
`armed_pack.session_lag()` intentionally returns zero when a name's last bar is at or
ahead of the selected tip, so a contaminated name could still enter the signal gate
even if the published stamp were repaired. The US pack owner now obtains the canonical
`last_completed_session(now)` bound, quarantines any series whose FINAL index is a
non-NYSE session, later than that bound, or malformed/NaT, and only then selects the
raw pack tip and submits valid names to the gate. It never trims and reuses a bad
series. Rejected names publish `skip=invalid_series_tip` as an explicit stale/non-
verdict. Shared `engine/prophet_live/armed_pack.py` is unchanged, preserving CN calendar
semantics and honest stale-store behavior.

TDD/proof receipts:

- binding owner-bound RED `33068839608`: **5 failed / 2 passed** before the US
  admission helpers existed; the two passes pinned the existing completion clock and
  shared calendar-neutral `as_of_date` behavior;
- committed-head GREEN `33069264975`: **8/8**;
- mutation run `33069337428`: deleting only `not is_session(day)` made the
  Saturday-before-bound case select `2026-08-01` instead of `2026-07-31`; mutation
  killed;
- cross-market run `33069685528`: **81/81** existing US + CN armed-pack tests;
- hostile NaT RED `33069928015`: **1 failed / 8 passed** with a real
  `TypeError: Cannot compare NaT with datetime.date object`;
- one-line fail-closed repair committed as
  `e2d612e4bd3b2dbddff4b25103c09aac3dc7434d`; apply run `33069998807` held **9/9**
  before commit.

This is not yet production acceptance. After merge/deploy, the first **natural** US
pack/evaluator cycle must prove the canonical completion bound and pack stamp, explicit
invalid-tip degradation if any exists, no global `stale_pack` darkness, and external
`pack_ok=True`. Do not seed a bad production row merely to exercise the negative case,
and do not manually dispatch `prophet-live.yml` while the VPS timer is primary.
''',
)
