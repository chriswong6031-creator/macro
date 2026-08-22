---
key: W2C-M0D0-0400Z-SOURCE-SEAL-GO
question: >
  After the 2026-08-20 natural-session M0D-0 probe, is single-ticker REST a
  lawful W2C v2 source, what is the production readiness boundary, and may M0D
  proceed to a bounded runtime vertical slice?
answer: >
  M0D-0 PASS. Sol GO_M0D. Freeze production readiness on a D+1 source-seal
  window [04:00:00Z, 04:05:00Z), not on first REST availability. The endpoint
  is a live forming daily aggregate from the XNYS open; existence at 09:30 ET
  does not make it opportunity-eligible. Persist one sealed source capture per
  session when the registration stability predicate holds. Later vendor
  revisions append correction lineage and never rewrite the already-sealed
  opportunity bytes. Authorize the bounded M0D v2 runtime after this records
  closeout merges. Do not backdate activation_session.
rationale: >
  The 2026-08-20 probe (841 polls, 13:09:02Z through 04:44:49Z D+1) proved the
  chosen object is not another class-A source-clock race: first non-empty bar
  at 13:30:41Z, last price revision at 20:10:56Z, last activity revision at
  03:01:52Z D+1, then 19/19 identical canonical results[] digests in
  04:00–04:05Z and 155/155 identical through 04:44:49Z. Grouped daily matched
  final OHLCV/n but disagreed on bar.t and remains non-authoritative. The 546
  unique digests are the forming-bar trajectory, not a storage model: copying
  that research instrumentation into production would waste capacity and treat
  every poll as a generation. First availability therefore cannot be the
  readiness sentence. The source seal is. Experience stays in the frozen
  04:30–04:45Z window with v2 staggered to 04:32Z. v1 remains the untouched
  control arm.
alternatives:
  - option: Treat first non-empty REST observation as opportunity-ready
    why_not: >
      On 2026-08-20 the bar existed at the 09:30 ET open and then changed 545
      more times. First availability proves the endpoint is live, not that the
      daily aggregate is sealed.
  - option: Persist every distinct forming-bar revision as a source generation
    why_not: >
      546 unique digests on one session. One stable seal equals one normal
      source capture. Distinct later corrections may append under the
      registered reserve.
  - option: Keep M0C's first-availability fail-closed probe as the standing readiness test
    why_not: >
      That probe was the M0D-0 gate and has now passed. Standing readiness is
      the 04:00–04:05Z seal predicate, not a recap of when the bar first
      appeared.
  - option: Seal from grouped daily because final OHLCV/n agreed
    why_not: >
      Grouped disagreed on t, lagged once during RTH, and remains the
      unbounded whole-market object M0C rejected. Cross-check only.
  - option: Move the experience clock to 04:00Z because the source now seals then
    why_not: >
      Destroys v1 comparability. Source seal at 04:00Z; technicals around
      04:07Z; experience-v2 at 04:32Z inside the registered 04:30–04:45Z
      window.
  - option: Hold M0D for more natural sessions before any runtime
    why_not: >
      Sol authorized GO_M0D on this completed trajectory. Further sessions
      accrue as prospective v2 opportunities, not as another research freeze.
evidence:
  - "research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv"
  - "sha256 69402b2e9d519b48181d9bf64b1608514c2bd6c495c4faab50e17bf4b8ec5755"
  - "DSC:W2C-M0D0-SPY-REST-FORMING-BAR-SEAL-STABLE"
  - "DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY"
  - "DEC:W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE"
  - "DEC:W2C-M0C-SOL-RATIFIED-REST-SUCCESSOR"
  - >
    Probe coverage: 841 polls of
    GET /v2/aggs/ticker/SPY/range/1/day/2026-08-20/2026-08-20?adjusted=false;
    546 sequential distinct canonical results[] digests; 0 reappearances.
  - >
    First non-empty 2026-08-20T13:30:41Z HTTP 200 resultsCount=1 digest
    499b14721c22b54c35672a546c31786eab72198575fec9d0f2c2e3dcaa36590d
    O/H/L/C/V/n 765.96/766.14/765.94/766.12/1104104.391941/17761.
  - >
    Final digest 56152e7292db903dee1fee2af4ae6e4319c55bceb140ea911f4acae48b9184d0
    first seen 2026-08-21T03:01:52Z; O/H/L/C 765.96/768.15/762.04/762.60;
    V/n 45520302.607881/600817.
  - "Seal 04:00:00Z–04:04:58Z: 19/19 same digest. Post-seal to 04:44:49Z: 155/155 same digest."
affects:
  - "WS:MARKET-MEMORY-W2C"
  - research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv
  - config/market_memory_spy_experience_registration.v1.json
  - engine/neuralweb/market_memory_sources.py
  - engine/close_pass/massive_close.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-21
review_by: 2026-08-25
---

# M0D-0 PASS — 04:00Z source seal is the readiness boundary

Sol classified the completed 2026-08-20 natural-session probe **GO_M0D**.
This decision freezes the production source-seal contract. It does not
implement runtime.

## Forming bar, not a late daily file

`GET /v2/aggs/ticker/SPY/range/1/day/{D}/{D}?adjusted=false` is a live
forming daily aggregate from the opening bell. On 2026-08-20 it printed a
non-empty bar at 13:30:41Z and then produced 545 further distinct canonical
`results[]` digests. That is why M0D-0 was worth doing: first availability
does not prove readiness. The endpoint can exist at 09:30 ET and still be
unusable for W2C until the fixed next-day seal.

## Production source-seal contract

The research probe's 841 polls are not the production architecture. Do not
persist hundreds of forming-bar revisions.

For each prospective session D:

- Source-seal window: `[04:00:00Z, 04:05:00Z)` on D+1.
- The source owner performs bounded repeated observations during that
  interval only.
- Freeze this stability predicate in the v2 registration:
  - HTTP 200
  - exactly one result
  - ticker SPY
  - request session D
  - `adjusted=false`
  - valid finite required fields
  - at least 3 successful observations spanning ≥240 seconds
  - at least one valid observation in the opening 60 seconds
  - at least one valid observation after 04:04:00Z
  - every valid bar-bearing observation in the seal interval has the
    identical canonical `results[]` digest
- A transient transport failure does not itself manufacture a different bar,
  but the minimum-coverage requirements must still be met.
- Any differing valid digest inside the seal interval ⇒ unstable at seal /
  no opportunity-eligible source capture.
- No valid bar by the seal deadline ⇒ source absent.
- Persist **one** opportunity-eligible sealed source capture per session, not
  one capture per network poll.
- The seal receipt may contain the bounded observation transcript
  `{observed_at, status, digest}` so the stability claim is auditable.
- Later vendor revisions append correction lineage. They never change the
  source bytes selected for the already-sealed opportunity.
- A correction after 04:05Z is not retroactive evidence that the original
  opportunity was invalid; it is a later-known correction.

Source identity is canonical `results[]`, never `request_id`. Session identity
is request date D. `bar.t` is a consistency witness only.

## Capacity

One stable seal = one normal source capture. Distinct later corrections may
append revisions under the registered reserve. The 546-row research
trajectory is evidence for this contract, not the storage model.

## What M0D may now build

After this records closeout is on `origin/main`, implement one vertical
slice: credentialed REST source owner, generalized source-store kernel with
new family root `/var/lib/macro-market-memory/state/sources-spy-rest-v1`,
keyless technicals-v2, content-addressed registration v2, experience-v2 at
04:32Z. Pin v1 registration
`e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3`.
`activation_session` is the first XNYS session whose regular open occurs
strictly after registration is on `origin/main` **and** the complete v2
runtime is verified installed. Monday 2026-08-24 is the earliest possible
candidate, not a deadline.

v1 stays untouched. No trusted-v1 repair, no R2 coherence, no UI, no
Cortex/Prophet, no ranking/gating/sizing.
