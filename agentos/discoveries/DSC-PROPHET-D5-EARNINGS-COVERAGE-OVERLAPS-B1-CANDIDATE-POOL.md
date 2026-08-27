---
key: PROPHET-D5-EARNINGS-COVERAGE-OVERLAPS-B1-CANDIDATE-POOL
claim: >
  The D5 Earnings first vertical is provable on real production data, not only on
  fixtures. The Earnings owner's registered issuer coverage is five CIKs — AAPL
  0000320193 plus the four IMCE homebuilders DHI 0000882184, PHM 0000822416,
  KBH 0000795266 and TOL 0000794170 (engine/company_intelligence/issuer_profiles.py:68-71).
  Three of those — PHM, KBH and TOL — are present in B1's real TURN WATCH candidate
  input for data_session 2026-08-25, which carries 1790 rows and whose every row
  passes B1's intake predicate. AAPL and DHI are absent from that pool. So a real
  canonical B1 episode with a real published event_workspace.v1 behind it is
  reachable, while the overwhelming majority of episodes (about 1787 of 1790
  tickers) are genuinely NOT_COVERED.
falsifier: >
  A B1 natural generation in which no episode opens for any of PHM, KBH or TOL and
  no other covered issuer's security appears, sustained across consecutive sessions;
  or evidence that issuer_profiles.py is not the coverage boundary and additional
  issuers publish event_workspace.v1 objects. A different ticker being present in
  some other Prophet store does not falsify this: the claim is about the TURN WATCH
  episode-input pool specifically.
so_what: >
  Sets the honest acceptance shape for the first D5 vertical and prevents two wrong
  readings. First, an empty or NOT_COVERED Earnings family on most episodes is the
  TRUTH, not an adapter bug and not a producer outage — do not "fix" it, and do not
  widen coverage to make the demo look better. Second, the golden path does not have
  to wait on coverage expansion: PHM/KBH/TOL give a real episode-to-real-workspace
  instance. The correction / then-versus-now law (amendment A7) is separately
  provable today against AAPL, whose event is recorded as having taken a source-SHA
  correction into a new generation with lifecycle corrected
  (research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md:159) even though AAPL
  is outside the candidate pool. CORRECTED 2026-08-26 by direct production read:
  that doc line states the INTENDED E1 success criterion, not a currently published
  chain. read_event_source_revisions('evt_cik0000320193_2026q3_results') against live
  R2 returns exactly ONE revision, lifecycle_state 'complete', source_available_at
  2026-07-30T20:30:28Z - so no live correction exists to test against, and the
  correction path is UNEXERCISED in production. Plan the vertical accordingly: golden
  path on a homebuilder, NOT_COVERED at scale, and the two-generation correction test
  against a CONSTRUCTED chain driven through the real reader, with the live
  single-revision case proven separately.
kind: architecture
verified_at: 2026-08-26
verified_by: >
  Registered issuer CIKs read from engine/company_intelligence/issuer_profiles.py:68-71.
  Candidate pool read from the committed B1 input
  data/us_prophet_rank/episode_inputs/turn_watch/2026-08-25.json at origin/main
  (schema prophet.candidate_episode_input.turn_watch/v1, content_sha256 verified to
  recompute exactly via engine.us_candidate_episode.canonical_json), 1790 rows,
  membership tested per ticker. B1's intake predicate
  (engine/us_candidate_episode_intake.py:174-268) was replayed against those bytes:
  all 1790 rows satisfy the trigger/evaluated/clock/reset-anchor gates, so
  suppression is expected only from Data OS identity resolution, which was not
  simulated here. The correction-chain claim was checked against production rather
  than inferred: read_event_source_revisions on the AAPL event returned one revision
  with keys form, generation_id, lifecycle_state, observed_at, source_available_at,
  source_sha256, workspace. DEFAULT_MAX_CHAIN_HOPS is 500 so the walk was not bounded
  early, and _dedupe_carry_forward_hops collapses only CONSECUTIVE byte-identical
  source_sha256 values, so a genuine correction would not have been hidden.
scope:
  - macro
  - engine/company_intelligence/issuer_profiles.py
  - data/us_prophet_rank/episode_inputs/turn_watch/
  - future prophet.intelligence_vector/v1
confidence: verified
---

Coverage is the boundary that decides what the first vertical can prove, and it is
narrow by design rather than broken. Treat the covered set as an input to the
acceptance plan, never as something the D5 wave may widen: expanding issuer coverage
is the Earnings owner's operation, and doing it to improve a D5 demo would be a
cross-owner authority hop.
