# Capital Structure W2C incremental document-term qualification — 2026-08-25

Status: **qualified implementation, held for Sol before merge**.

This packet attributes the W2 runtime falsifier and qualifies one repair on the
existing Capital Structure job. It does not change the W2B `500/20/20 = 540`
collector envelope, deterministic spill, SEC pacing, daily carrier, 76.5-minute
warning, 90-minute hard cap, queue, store, parser semantics, projection law, or
authority. `prophet_authority=false` remains frozen.

## Exact inputs

- protected Sol Skillpack: Mastermind `master`
  `51f9942733b86e550bb9169d2a43462bd28e774f`, schema
  `mastermind.sol_skillpack.v1`, version `1.0.0`;
- W2B qualification baseline:
  `research/CAPITAL_STRUCTURE_W2B_CAPACITY_QUALIFICATION_2026-08-23.md`;
- first natural W2B run `32671784885`, collect job `97273624140`,
  Capital Structure job `97292842139`, generation `8a3628f1c2bb`;
- debt-closure run `32786919396`, collect job `97620633216`,
  Capital Structure job `97654020902`, generation
  `a6ff3b6b47db58ec549ff4508399312311f549a1`;
- implementation pickup: freshly fetched Macro `origin/main`
  `afdb8e9e95140ae52129aa268a973a98ad18290c`.

No Capital Structure source-law, compiler, collector, workflow, or test collision
landed between the accepted debt generation and pickup. The only named material-
path drift was `.github/ci/legacy-jobs.yml` CI bookkeeping.

## Three-run timing attribution

| Evidence | Capital Structure wall | Direct document terms | Eligible roots | Dirty roots | Output observations |
| --- | ---: | ---: | ---: | ---: | ---: |
| W2B qualification baseline | 65.0m | 63m27s | 550 existing | 57 new | not separately receipted |
| Natural W2B run `32671784885` | 65m32s | 64m11s | 607 | 57 | 3,190 |
| Debt closure `32786919396` | 80m43s | 78m32s | 670 | 63 | 3,505 |

For job `97654020902`, the direct-document step consumed 4,712 of 4,843
seconds, or 97.3 percent. All checkout, environment, dependency, artifact,
event-spine, health, projection, commit, push, timing, and cleanup work together
used 131 seconds. Runner/setup overhead is therefore not the dominant cause.

The debt generation carried forward 607 roots and 3,190 observations unchanged.
Those unchanged roots were 90.6 percent of the 670-root retained-source read set;
the unchanged rows were 91.0 percent of output observations. The production
path materialized only 63 dirty roots, but its post-compile source-authority pass
then read all 670 retained roots and re-derived all 3,505 observations. The disk
wrapper repeated the row-level source re-derivation from its memoized bytes.

The deterministic R2 path therefore performed 670 unique backend object reads,
covering 4,341,004,140 bytes (4.043 GiB):

| Cohort | Roots | Bytes | GiB |
| --- | ---: | ---: | ---: |
| unchanged carried-forward | 607 | 3,821,247,008 | 3.559 |
| new dirty | 63 | 519,757,132 | 0.484 |
| total | 670 | 4,341,004,140 | 4.043 |

All 63 newly eligible roots joined to `HISTORICAL_BACKFILL`: 58 registration
and five Regulation A. The run selected 337 LIVE, zero RECOVERY, and 203
HISTORICAL after 183 unused LIVE/RECOVERY slots spilled to history. Thus the
incremental W2B-to-closure growth has a class-B contributor, but the absolute
80.3-minute wall is class A: full historical-estate source revalidation. W2C
does not change the accepted spill law.

## Qualified repair

The existing canonical `document_term_observations.parquet` ledger is the only
reuse surface. Every existing row still passes its closed schema, immutable
observation ID, correction-chain, released-parser registry, canonical manifest
ledger, and exact manifest dependency checks. `manifest_id` binds the retained
evidence occurrence and source bytes; the row additionally pins the same
manifest ID, source/content SHA-256, source ID, filing fields, canonical URL,
and source-available clock.

The incremental compiler may avoid a retained-source read only when all of that
identity is unchanged and the current row already uses the active released
parser. A new manifest/evidence identity, content correction, detached field,
missing manifest, or parser-version change prevents reuse. Dirty roots still
pass retained-byte digest and SEC-envelope validation, parsing, closed-contract
validation, and exact byte/span/source-semantic re-derivation before append.

`--rebuild` preserves the expensive whole-output retained-byte authority pass.
It is the deliberate audit/correction path and remains byte- and semantic-parity
authority for incremental output. No historical observation is rewritten to
establish this optimization, and no cache, truth store, queue, or carrier is
added.

## Production-ledger replay and headroom

The exact committed production estate at generation `a6ff3b6b47db` was replayed
through the changed compiler with a source reader that raises on any call:

```text
source manifests                   8,757
existing observations              3,505
eligible complete submissions        670
processed complete submissions          0
reused complete submissions           670
source reads                            0
dependency-validated observations   3,505
source-validated observations           0
parser invalidations                    0
output semantically identical        true
wall                               9.071s
```

The replay proves that nightly no-op cost scales with the dependency ledger,
not the 4.043-GiB retained-source estate. Hostile fixtures separately prove
that new evidence and parser invalidations each read exactly the dirty root,
detached evidence fails before reuse, and incremental/full rebuild Parquet is
byte-identical without rewriting history.

For the observed 63-root dirty cohort, scaling the 4,712-second direct step by
dirty bytes rather than the smaller root ratio gives 9.40 minutes of dirty
source work. Add the measured 9.071-second dependency replay and 131 seconds of
all other job work: 11.73 minutes. Applying a conservative 2x factor to the
dirty-source band projects 21.13 minutes total, leaving 55.37 minutes below the
unchanged 76.5-minute warning. This is qualification headroom, not natural
production proof; the first natural chain containing accepted W2C and W2D must
still prove the actual job wall.

## Gates and falsifiers

The repair is acceptable only if:

- exact incremental/full semantic and Parquet-byte parity stays green;
- parser-version, new-evidence, correction, detached-dependency, and stale-reuse
  tests fail closed;
- the released parser closure remains byte-identical and the intentionally
  changed authority closure is control-first resealed;
- W1 identity, closed bundles, no-new-legacy, append-only fence, #5792, W2A,
  and W2B suites remain green;
- hosted CI, fences, and current CI authority bind to the exact PR head.

Return to Sol if new HISTORICAL work rather than unchanged estate remains the
dominant post-repair runtime, any dependency can be stale-reused, parity differs,
or the natural job still crosses 76.5 minutes. None of those outcomes authorizes
a timeout/warning/cap/spill/carrier change.
