# Prophet V4 D5 Earnings entrance hold — 2026-08-30

## Executive verdict

```text
D5 IMPLEMENTATION: HOLD
REASON: NO_LAWFUL_REAL_VERTICAL
CAPABILITY STATE: SPEC_ONLY / NOT_BUILT
```

The D5 contract is architecturally ready to govern an Earnings evidence adapter,
but the first implementation vertical is not presently lawful. The canonical B1
episode owner and the Earnings workspace owner have no accepted real issuer/security
overlap in any of the first three natural B1 generations. Independently, the
canonical Data OS identity reader does not expose the issuer CIK required by D5
amendment A13.

Building now would require at least one forbidden substitution:

1. call a fixture-only demonstration real production proof;
2. join by ticker/date instead of canonical economic identity;
3. read the identity parquet directly and bypass the Data OS owner; or
4. widen Earnings coverage to make a demo possible.

All four are rejected. D5 remains unbuilt until every reopen gate in this ruling is
satisfied on current canonical sources.

## What the landed architecture makes true

Macro merge `418def12139f8a9d1ddc7a3abc82e57442095c96` froze one canonical
Prophet platform with multiple governed strategy sleeves. It did not implement D5.
The controlling D5 sources remain:

- `research/prophet_v4/D1_D5_READINESS_RULING.md`;
- `research/prophet_v4/flagship_cells/CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md`;
- `research/prophet_v4/flagship_cells/CELL_F_D5_ADVERSARIAL_REVIEW_AMENDMENTS_2026-08-22.md`;
- `research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md`;
- `DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY`.

Those sources preserve the epistemic contract:

- one `prophet.intelligence_vector/v1` is pinned to one canonical B1 episode,
  decision cut, adapter set and B1 generation;
- Context Vector remains unchanged and read/reference only;
- evidence-family values are distinct from authority;
- missing/unbuilt is never converted into zero or neutral;
- Earnings decision-time reads use source-revision history, never current-workspace
  convenience readers;
- admission requires both `source_available_at <= decision_cut` and
  `observed_at <= decision_cut`;
- `tradable_at=NOT_ASSERTED` remains binding until B4;
- `fusion_bindings=[]` and all authority flags remain false at D5 birth.

The contract is therefore **SPEC_ONLY** and ready to constrain future code. It is not
proof that a real vertical currently exists.

## Three different populations must not be blurred

### 1. TURN WATCH source-input membership

A row in `data/us_prophet_rank/episode_inputs/turn_watch/<date>.json` is an upstream
candidate observation. It may still fail canonical identity, as-of, basis, universe,
reset-anchor or mechanical-overlap law. Source-input presence is useful intake
archaeology; it is not a D5 episode identity.

The historical discovery
`DSC:PROPHET-D5-EARNINGS-COVERAGE-OVERLAPS-B1-CANDIDATE-POOL` observed PHM, KBH and
TOL in the pre-generation `2026-08-25.json` input and correctly disclosed that Data
OS identity resolution was not simulated. That was a plausible readiness hypothesis,
not a canonical episode proof.

### 2. Accepted B1 episode membership

D5 may join only from the owner-issued `prophet.candidate_episode/v1` plane, pinned by
`episode_ref` and the exact B1 generation. An upstream candidate that never becomes an
accepted episode is not a null D5 vector; it is outside the legal join population.

The first three committed natural generations are:

| B1 generation | Recorded at | Episodes | Covered listed-security overlap |
|---|---:|---:|---:|
| `peg:c025bb50c45f319f989a4848249b8a85b65354143e3262f2ad09d07841311b08` | `2026-08-28T14:28:48Z` | 467 | 0 / 5 |
| `peg:9afeb4f89ecc434c119f563424990d7b10b58bc75a30a0f275c74cf73465cfcc` | `2026-08-29T15:41:20Z` | 467 | 0 / 5 |
| `peg:881d604cc56968cfe921188f59e992c1652329416fa2bb2b4e9059a46616acc2` | `2026-08-30T07:20:29Z` | 467 | 0 / 5 |

Exact searches of each `all_candidates.json` found no AAPL, DHI, PHM, KBH or TOL
`ticker_at_observation`. The current `HEAD.json` selects the third generation.

All three receipts bind the same 1,903-row TURN WATCH source dated 2026-08-26. The
older 1,790-row 2026-08-25 input is not the source of any accepted natural generation
above. The old discovery's own falsifier—continued natural absence—has therefore
fired.

The stage at which the covered names disappeared is not yet attributed. They may be
absent from the later source or may have been suppressed during canonical intake.
That distinction is scientifically useful but not release-relevant: accepted episode
overlap is zero either way.

### 3. Earnings event-workspace coverage

The Earnings owner registers five issuer profiles in
`engine/company_intelligence/issuer_profiles.py`:

| Security | CIK |
|---|---:|
| AAPL | `0000320193` |
| DHI | `0000882184` |
| PHM | `0000822416` |
| KBH | `0000795266` |
| TOL | `0000794170` |

The four homebuilders bind one primary NYSE common listing apiece. This is narrow
owner coverage by design, not an adapter defect. A future D5 vector for an accepted
episode outside this set should be `NOT_COVERED`, not a fabricated zero and not a
producer outage.

Coverage presence alone also does not create a join. D5 needs an accepted B1 episode
for the same economic issuer and a canonical identity path that resolves the episode's
security to the Earnings CIK.

## Independent identity-owner blocker

D5 amendment A13 requires:

```text
B1 security_id (ISS)
  -> Data OS economic issuer
  -> owner-native issuer CIK
  -> Earnings company_id_for_cik
```

The current `lib/dataos/identity.py::IssuerMaster` public reader exposes:

- `issuer_of_security(security_id)`;
- `securities_of_issuer(issuer_id)`;
- security state and supersession behavior.

It does not expose an issuer-CIK accessor. D5 may not compensate by:

- joining on `ticker_at_observation`;
- parsing `issuer_id` as if it were a CIK;
- opening identity parquet directly;
- importing a second CIK registry into Prophet; or
- copying Earnings issuer-profile logic into the adapter.

An owner-native CIK reader is a separate bounded Data OS capability. Its eventual
existence does not by itself reopen D5; a natural accepted overlap is still required.
Conversely, a future overlapping episode does not authorize a ticker join while the
CIK bridge is absent.

## Decision-time and correction law remain binding

The live AAPL event currently exposes one complete source revision. No live correction
chain exists. This does not weaken the contract, but it changes acceptance evidence:

- the real single-revision case can prove decision-cut admission and current no-change
  behavior;
- a constructed two-generation chain must prove then-versus-now correction behavior;
- the constructed chain must be consumed through the real
  `read_event_source_revisions` / `read_all_event_source_revisions` reader, not by
  calling internal translation functions directly;
- the constructed proof is correction-contract evidence, not a claim that production
  already contains a corrected event;
- unknown or null admission clocks remain `UNKNOWN`;
- a revision available before the cut but observed after it is
  `NOT_CAPTURED_AT_DECISION`, never silently admitted.

## Capability ledger

| Capability | State | Evidence / boundary |
|---|---|---|
| D5 architecture and epistemic law | `SPEC_ONLY` | Cell F contracts + A7-A13 amendments |
| Canonical B1 episode plane | `PROVEN_LIVE` | three natural committed generations; B1 acceptance |
| Earnings workspace owner | `PROVEN_LIVE` for its registered events | narrow five-issuer profile boundary; not broad coverage |
| Real B1 × Earnings episode overlap | `NOT_BUILT` as a usable vertical / currently absent | 0/5 across three natural generations |
| Data OS issuer-to-CIK read seam | `NOT_BUILT` for D5 consumption | no owner-native accessor in `IssuerMaster` |
| D5 Earnings adapter | `NOT_BUILT` | no lawful real input pair; no code authorized |
| D5 correction proof | `PARTIAL` | contract frozen; live chain absent; constructed reader-path proof owed |
| D5 rank/trade authority | `REJECTED_BY_DESIGN` at this stage | B4 and later evaluation/promotion owners retain authority |

## Failure states

A future implementation must preserve these states separately:

- `NOT_COVERED`: accepted episode resolves lawfully, but the Earnings owner has no
  workspace coverage for the issuer;
- `IDENTITY_UNRESOLVED`: B1 security cannot resolve to one canonical economic issuer;
- `CIK_UNAVAILABLE`: issuer resolves, but the owner-native CIK bridge is unavailable;
- `NO_EVENT_AT_CUT`: issuer is covered but no event revision is admissible at the
  episode decision cut;
- `NOT_CAPTURED_AT_DECISION`: source was available but the owner observed it only
  after the decision cut;
- `UNKNOWN_CLOCK`: required clock is null, malformed or unknown;
- `CONFLICTED`: admissible evidence ties under the owner's deterministic selection
  law;
- `CORRECTION_NOT_CAPTURED_LIVE`: no real multi-generation revision chain exists;
- `UNBUILT`: adapter code does not exist and therefore emits no evidence-family
  envelope.

None of these states may be averaged, filled with zero, translated into a weak score,
or used to widen coverage.

## Conjunctive reopen gates

D5 implementation may be reconsidered only when **all** of the following are true on
fresh canonical evidence:

### Gate 1 — natural accepted overlap

A current naturally published B1 generation contains at least one accepted episode
for an Earnings-covered listed security. Fixture-only or upstream-source membership
does not count.

### Gate 2 — canonical economic identity

The episode security resolves through the accepted Data OS identity spine to exactly
one economic issuer, with epoch/supersession behavior honored.

### Gate 3 — owner-native issuer CIK

The Data OS owner exposes a reviewed issuer-to-CIK read seam. Prophet does not read
parquet, copy a registry or join on ticker.

### Gate 4 — evidence-shape proof

The bounded vertical can demonstrate:

1. one real positive covered case;
2. one real `NOT_COVERED` case;
3. null/unknown clock behavior;
4. a constructed two-generation correction chain through the real revision reader;
5. all authority false, `fusion_bindings=[]`, and `tradable_at=NOT_ASSERTED`.

A new natural B1 generation or a merged CIK reader is only a reason to **re-census**.
Neither event independently authorizes implementation.

## Exact next action

Keep wave D5 `todo` under an intentional natural-evidence wait. Recheck after
2026-09-01 only if either:

- a new natural B1 generation lands; or
- an accepted owner-native issuer-CIK reader lands.

At that time, rerun both gates. If the conjunction still fails, update the wait rather
than building. If every gate passes, Sol may commission one bounded Earnings vertical
under the frozen Cell F amendments.

## Non-goals

This ruling authorizes none of the following:

- D5 adapter implementation;
- `prophet.intelligence_vector/v1` schema or publication code;
- changes to Context Vector;
- Data OS identity code;
- new Earnings issuer coverage;
- direct identity-parquet reads;
- ticker/date surrogate joins;
- correction publication;
- B4 Availability, ranking, sizing, leverage, trade or portfolio action;
- D6 or another downstream wave.

The correct result today is a durable, explicit hold—not an impressive but unlawful
demo.
