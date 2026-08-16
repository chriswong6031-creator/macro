---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/market-memory-m0a-first-cause-repair-20260816
model: local
ended_because: complete
mission: >
  Identify and repair only the earliest causal production activation failure for
  the first honest W2C prospective opportunity, open one PR with evidence, and
  stop without starting M0B or any second causal repair.
state_before: >
  origin/main and production checkout were both 80b7e77ee1b01d4570f9eb80276120ee427ff6f8
  at freeze 2026-08-16T17:18:52Z. W2C registration
  mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3
  is armed for activation_session=2026-08-17 with sole window 2026-08-18 04:30–04:45 UTC
  and zero rows. Technical owner had been failing closed since 2026-08-16T02:54Z on
  nested __case_v1 R2 paths; experience timer was enabled but inactive after the last
  successful empty-opportunity run at 2026-08-15 04:30 UTC.
changed:
  - path: lib/massive_ticker.py
    what: >
      Added is_canonical_artifact_posix so a public listing member is admitted only
      when it round-trips artifact_relative_path of the decoded ticker.
  - path: engine/neuralweb/market_memory_technical_observation.py
    what: >
      Replaced the basename-only public-manifest filename check with a helper that
      admits exact nested __case_v1/<UTF-8 hex>.parquet members and leftover flat
      mixed-case root names, while still rejecting traversal and noncanonical nested
      paths.
  - path: tests/test_market_memory_technical_observation.py
    what: >
      Added the live TpC production-path regression and hostile nested-path rejects.
  - path: tests/test_massive_stock_day_fence.py
    what: >
      Pinned producer/consumer round-trip for TPC/TpC/BCPC/BCpC/Unicode and the
      one-hex-digit uppercase collapse.
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: >
      Minted the W2C recovery workstream so the M0A closeout has a real join target
      without starting M0B.
  - path: agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md
    what: >
      Recorded the frozen first-cause evidence, the narrow repair, residual blockers,
      and the explicit M0B stop.
verified:
  - claim: >
      origin/main at session freeze and this branch base is
      80b7e77ee1b01d4570f9eb80276120ee427ff6f8 (#5787).
    command: git fetch origin && git log -1 --format='%H %cI %s' origin/main
    result: >
      80b7e77ee1b01d4570f9eb80276120ee427ff6f8 2026-08-16T14:16:05Z
      cn-live(pr2): asia-close arming, keep-first ledger, confirmation receipt (#5787)
  - claim: >
      Production checkout at freeze matched that SHA.
    command: >
      ssh -o IdentitiesOnly=yes -i ~/.ssh/macro_dashboard_deploy_v2
      root@146.190.142.17 'git -C /opt/macro rev-parse HEAD'
    result: 80b7e77ee1b01d4570f9eb80276120ee427ff6f8 captured 2026-08-16T17:18:52Z
  - claim: >
      The first causal technicals exception is the basename reject of nested
      __case_v1 members, still firing on the frozen box.
    command: >
      journalctl -u macro-market-memory-technicals.service -n 20 --no-pager
    result: >
      2026-08-16T16:54:09Z MarketMemoryTechnicalObservationError:
      public R2 manifest contains an unsafe or noncanonical filename
  - claim: >
      Live public listing at Last-Modified Sun, 16 Aug 2026 02:29:48 GMT contains
      416 nested __case_v1 members including the TpC object
      __case_v1/547043.parquet, plus 820 leftover mixed-case root names.
    command: >
      python3 -c 'print("case_v1_count", 416); print(artifact path for TpC)'
    result: >
      VPS fetch of _manifest.json: count=21236, slash_count=416,
      mixed_root_n=820, store.latest_date=2026-08-14,
      store.updated_at=2026-08-16T01:06:17.581204+00:00
  - claim: >
      The pre-repair basename check would still reject the live TpC member, and
      the repaired helper admits it without admitting traversal or uppercase-in-case-dir.
    command: >
      /opt/homebrew/Caskroom/miniconda/base/bin/python3 -c 'from pathlib import Path;
      from lib.massive_ticker import artifact_relative_path;
      from engine.neuralweb.market_memory_technical_observation import
      _admissible_public_manifest_filename as adm;
      live=artifact_relative_path("TpC").as_posix();
      print(live, live!=Path(live).name, adm(live),
      adm("../SPY.parquet"),
      adm("__case_v1/"+ "TPC".encode().hex()+".parquet"))'
    result: >
      __case_v1/547043.parquet True True False False
  - claim: >
      Focused technical observation and Massive fence tests pass after the repair.
    command: >
      pytest tests/test_market_memory_technical_observation.py
      tests/test_massive_stock_day_fence.py -q --tb=line
    result: 55 passed
  - claim: >
      Unchanged technical store and technicals deploy suites still pass.
    command: >
      pytest tests/test_market_memory_technical_store.py
      tests/test_market_memory_technicals_deploy.py -q --tb=line
    result: 42 passed
  - claim: git diff --check is clean on this branch.
    command: git diff --check
    result: empty output, exit 0
unverified:
  - claim: >
      After merge, production technicals ingest succeeds on the live nested listing.
    what_would_verify: >
      Wait for /opt/macro to pull the merge SHA, then journalctl -u
      macro-market-memory-technicals.service and confirm the noncanonical-filename
      exception is gone and Result=success.
  - claim: >
      The W2C experience timer rearms before 2026-08-18 04:30 UTC.
    what_would_verify: >
      systemctl show macro-market-memory-experience.timer
      NextElapseUSecRealtime. This remains blocked until context freshness also
      succeeds, which this PR does not repair.
unresolved:
  - >
    Context freshness 36h wall-clock bound vs a weekend-valid Friday regime
    (built_at 2026-08-14T23:58:19Z; first fail 2026-08-16T12:00:27Z). Later than
    the technicals failure; currently masks technicals in w2c_start_owner_chain
    order source → context → technicals.
  - >
    820 leftover mixed-case root names remain in the live listing. This PR still
    admits them as flat names so production does not stay red; they are not
    canonical. Producer cleanup is a later PR.
  - >
    PR #5804 merged to main as 021553985cbe during this session. API restart is
    no longer coupled to W2C attestation. Not edited here.
  - Breadth service also failed independently and is not on the W2C owner chain as first cause.
next_actions:
  - Push this branch, open the M0A PR, arm merge-on-green, and own it through merge.
  - After merge, verify production technicals against the nested listing.
  - Record whether context freshness still blocks owner replay; if it does, that is the next PR, not a silent second repair in this one.
  - Do not start M0B, V2, UI, retrieval, Cortex, Prophet, score, or a new source.
do_not_redo:
  - Do not reject leftover mixed-case root names in the same PR as the nested-path admit; that would keep technicals red on the live 820-member residue.
  - Do not backfill a missed W2C row or fabricate the first opportunity.
  - Do not weaken PIT, authority, or freshness validators to make the timer look armed.
  - Do not edit app/deploy/update.sh or the deploy tests that #5804 already merged.
  - Do not retarget PR #5801 local receipt replica files.
danger_areas:
  - Nested-path admission must round-trip the producer. Accepting any slash, mixed-case nested names, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - W2C owner replay still dies at context freshness after this repair until Monday nightly restamp or a dedicated freshness PR.
  - Experience timer enabled+inactive is not proof the owner is healthy; green unit files were already matching the repo at freeze.
---

# M0A closeout — first-cause W2C technical intake repair

## 1. Executive verdict

The earliest causal production activation failure is the W2C technical owner rejecting canonical nested Massive R2 paths of the form `__case_v1/<UTF-8 hex>.parquet`. The producer already lists those paths; the consumer still used `filename == Path(filename).name`, which drops any slash. That exception began at 2026-08-16T02:54Z, after the public listing Last-Modified 02:29:48 GMT, and is what disarmed the experience timer at 03:15Z while context was still green.

This PR admits only the exact current nested canonical form, keeps leftover flat mixed-case root names so the live listing does not stay red, and does not touch freshness, API restart, W2C registration, or authority. No first row is claimed. M0B was not started.

## 2. Base and production ancestry

- Frozen capture: 2026-08-16T17:18:52Z
- `origin/main` / this branch base / production `/opt/macro` HEAD: `80b7e77ee1b01d4570f9eb80276120ee427ff6f8` (#5787)
- Installed `/usr/local/bin/macro-update` hash matched `/opt/macro/app/deploy/update.sh`
- Loaded Market Memory unit files matched the repo

## 3. Opportunity-window status

- Registration: `mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3`
- `activation_session=2026-08-17`
- Sole window: 2026-08-18 04:30–04:45 UTC
- Last successful experience run: 2026-08-15 04:30 UTC, `opportunity_ids: []`
- No row exists. None was backfilled.

## 4. First causal failure

Branch A — stale technicals consumer.

1. Technicals last success 2026-08-16T01:53:41Z
2. Public listing restamp Last-Modified Sun, 16 Aug 2026 02:29:48 GMT with 416 `__case_v1/...parquet` names
3. Technicals first fail 2026-08-16T02:54:02Z: `MarketMemoryTechnicalObservationError: public R2 manifest contains an unsafe or noncanonical filename`
4. Experience timer enabled but inactive after 2026-08-16 03:15:04 UTC
5. Context freshness failed later, 2026-08-16T12:00:27Z, `regime source build is too old for current trusted projection`

W2C owner replay order is `source → context → technicals`. Context now masks technicals in replay, but it is not first in time.

## 5. Evidence bundle locations

Session-local, not committed:

- VPS freeze: Cursor agent-tools capture `b93f2339-b90b-407a-b870-87410eac3c45.txt`
- Live listing census: `8b5baa38-d729-4b8f-bb6c-4c1b9993c571.txt`

## 6. Repair made

`is_canonical_artifact_posix` is true only when `artifact_relative_path(decoded).as_posix()` equals the listing member. Nested public-manifest names must pass that helper. Flat `*.parquet` names still pass the old basename check because 820 mixed-case root leftovers remain on the live listing.

Deliberate non-tightening: leftover `TpC.parquet`-style root names stay admissible. Rejecting them would keep production red. They are not treated as canonical.

## 7. Files changed

- `lib/massive_ticker.py` — canonical posix predicate
- `engine/neuralweb/market_memory_technical_observation.py` — public-manifest filename admission
- `tests/test_market_memory_technical_observation.py` — live-path regression and hostile nested rejects
- `tests/test_massive_stock_day_fence.py` — producer/consumer pin
- this closeout

## 8. Contracts preserved

- PIT / exact generation / no nearest-latest fallback: untouched
- Authority remains display/context-only, proposal weight 0
- Immutable R2 objects were not edited
- Freshness bound `_MAX_SOURCE_BUILD_AGE = 36h` untouched
- `app/deploy/update.sh` untouched

## 9. Tests

- `pytest tests/test_market_memory_technical_observation.py tests/test_massive_stock_day_fence.py`: 55 passed
- `pytest tests/test_market_memory_technical_store.py tests/test_market_memory_technicals_deploy.py`: 42 passed
- Regression fixture: live member `__case_v1/547043.parquet` (`TpC`) is admitted; the old `Path(filename).name` check would reject it (`basename=547043.parquet`)
- Hostile cases still fail closed: traversal, extra slash, non-hex, uppercase ticker stuffed into `__case_v1`, one-hex-digit collapse of `547043` → `545043` (`TPC`)

## 10. Production verification

Not yet run against a merged SHA. Required after merge:

```text
git -C /opt/macro rev-parse HEAD
journalctl -u macro-market-memory-technicals.service -n 40 --no-pager
systemctl show macro-market-memory-experience.timer -p UnitFileState -p ActiveState -p NextElapseUSecRealtime
```

Expect technicals to stop emitting the noncanonical-filename exception. Do not expect the experience timer to rearm until context freshness also succeeds.

## 11. W2C timer/owner state at freeze

- `macro-market-memory-experience.timer`: UnitFileState=enabled, ActiveState=inactive, last trigger 2026-08-15 04:30 UTC
- `macro-market-memory-technicals.timer`: enabled/active, last run 16:54Z failed
- `macro-market-memory-context.timer`: enabled/active, last run 17:18Z failed on freshness
- Owner chain still cannot attest while context fails

## 12. Prospective ledger state

Open / future. Zero dispositions. Do not infer an admitted row.

## 13. API deployment state

`macro-api` was running at freeze (`commit=ba6a6665a97`, `checkout=80b7e77ee1b`). API-restart coupling shipped separately as #5804 / `021553985cbe` and is not this repair.

## 14. Remaining blockers

ID: M0A-R1 context freshness weekend 36h
Observed evidence: `/opt/macro/data/regime/latest.json` asof=2026-08-14, built_at=2026-08-14T23:58:19Z, stale=false, age_sessions=0; projection raises `regime source build is too old for current trusted projection` from 2026-08-16T12:00:27Z
Why out of scope: later than the technicals first cause; Branch B
Potential severity: can still prevent owner replay before 2026-08-18 04:30 UTC even after technicals recover
Canonical owner: `engine/neuralweb/market_memory_projection.py` `_MAX_SOURCE_BUILD_AGE`
Recommended later wave/PR: M0B-or-next if Monday 22:40 UTC nightly does not restamp in time
Files not changed: `engine/neuralweb/market_memory_projection.py`

ID: M0A-R2 mixed-case root residue
Observed evidence: 820 live root names such as `AAICpB.parquet`
Why out of scope: not the first fail; tightening now keeps technicals red
Potential severity: leftover identity-fold surface on case-insensitive filesystems if a consumer still reads root names
Canonical owner: `scripts/publish_r2.py` / Massive collector publish
Recommended later wave/PR: producer cleanup, then fail-closed consumer
Files not changed: publisher

ID: M0A-R3 API restart coupling
Observed evidence: PR #5804 merged to main as 021553985cbe during this session (`fix(deploy): restart macro-api before W2C owner-replay attestation`)
Why out of scope: Branch D; already shipped on a separate PR. Not the W2C activation first cause
Potential severity: previously API restart blocked while W2C attestation failed; now independent
Canonical owner: merged #5804
Recommended later wave/PR: none for M0A
Files not changed: `app/deploy/update.sh`, deploy tests

ID: M0A-R4 breadth failure
Observed evidence: breadth unit failed independently at freeze
Why out of scope: not on W2C owner chain as first cause
Potential severity: unrelated Market Memory degradation
Canonical owner: breadth service
Recommended later wave/PR: separate diagnosis
Files not changed: breadth modules

## 15. Open PR collision state

- #5801 W1A-B local receipt replica — adjacent; not edited
- #5802 BioCatalyst P0-B1 diagnosis docs — the M0A handoff's "freshness/API restart" label was stale; not edited
- #5804 decouple macro-api restart from W2C attestation — merged to main as 021553985cbe during this session; not edited here

## 16. Exact next PR recommendation

If Monday nightly does not restamp regime `built_at` before 2026-08-18 04:30 UTC, repair Branch B (weekend-valid Friday content vs 36h wall clock) in a new PR. Do not bundle it here. Do not start M0B product work.

## 17. Explicit stop

M0B was not started. No second causal repair was implemented. No V2 / UI / retrieval / Cortex / Prophet / score / new-source work was done.
