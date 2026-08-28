---
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: m1-w4-read-only-census
model: codex
ended_because: ci_handoff
mission: >
  Determine whether the recovered M1 can safely admit exactly one
  capability-specific production lane without harming ThetaData, options,
  research or other live host work. Make no host, workflow or GitHub mutation.
state_before: >
  The accepted W2 soak existed, and storage recovery had raised internal free
  space above 200 GiB, but durable W2 state was stale. No current census bound
  listener state, production services, workflow consumers, guard bytes or the
  collect_tail runtime tail into one W4 admission decision.
changed:
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Reconcile W2 to done from the accepted soak/storage receipt and record W4
      as a measured but unarmed single-capability lane with explicit disk,
      listener, runtime and trust gates.
  - path: agentos/handoffs/RUNNER-FLEET-RESILIENCE-2026-08-26-w4-m1-census.md
    what: >
      Preserve the read-only host/workflow census, safe stop condition and exact
      one-root continuation without claiming that any listener or route changed.
verified:
  - claim: M1 storage and Theta capability are live after W2 recovery.
    command: read-only host filesystem, process, port, launchd and Git-root census
    result: >
      M1 Max arm64, 10 cores and 32 GiB RAM. Internal data volume had about
      201.3 GiB available at 52 percent used; /Volumes/STORAGE had about 377.5
      GiB available at 60 percent used. The canonical 61 GiB Theta store remained
      at /Volumes/STORAGE/macro-data/thetadata_eod with eod/greeks/oi roots.
      ThetaTerminal retained ports 25503 and 25520, and all eight relocated Git
      paths still resolved through the expected STORAGE symlinks.
  - claim: Existing production load materially constrains a new M1 lane.
    command: read-only process/resource and launchd schedule census
    result: >
      OptionsHub consumed 9-14 GiB RSS and about one CPU core; host load was near
      5.7 and swap use was 4.45 of 6 GiB while memory_pressure still reported 85
      percent free. ThetaTerminal, macro-live, state-sync, bot and extquotes were
      live, with additional five/fifteen-minute and scheduled Theta/options/GEX/
      Prophet/research contenders. W4 cannot assume an otherwise idle M1.
  - claim: No current M1 listener is production-admissible.
    command: read-only runner root/process/LaunchAgent/admission census
    result: >
      All four listener processes were absent and all four LaunchAgent plists were
      unloaded. Repository runner m1-nightly-repo-1 was offline in Default and is
      ineligible because it lacks the selected-workflow group boundary. Installed
      admission SHA b3fd7bee0918fa5469da8859f81f0033c1da2e6e99803eed48b3c9609fdd1607
      was stale versus main e4ff74a96e9949a0ce4707e3fdb58cfffc251057d5e8c69a7309fe2871e11202,
      and correctly refused schedule/daily.yml@main/collect_tail with exit 77.
  - claim: Generic macstudio remains rejected by design.
    command: current-main workflow label census
    result: >
      49 literal macstudio jobs plus one dynamic key-pool probe and 20 separate
      macstudio-light jobs exist, while zero jobs use theta-m1 or m1-nightly.
      Adding macstudio would expose roughly fifty unrelated jobs rather than one
      measured capability lane.
  - claim: collect_tail is the only evidence-supported W4 candidate, but not safe to arm yet.
    command: workflow contract plus last six M2 and three historical M1 run census
    result: >
      collect_tail requires ThetaTerminal/store, CENSUS_API_KEY and contents:write;
      it mutates data/site and pushes main. Last six M2 runs took 95.18-177.90
      minutes, with qledger at about 86-164 minutes. Three historical real M1
      theta-m1 successes took 97.77-102.80 minutes and executed store-dependent
      work that M2 now skips. Current qledger tail plus real M1 Theta work can
      exceed the 170-minute acceptance tripwire and approach the 200-minute cap.
unverified:
  - claim: A cold collect_tail checkout can preserve the 200 GiB hard floor.
    what_would_verify: >
      Recover at least 225 GiB start free space or capture an exact lower checkout/
      temporary-growth peak without starting production admission.
  - claim: One natural collect_tail run coexists safely with the current M1 estate.
    what_would_verify: >
      After the storage, listener, admission and selected-workflow gates pass, run
      exactly one natural main job on m1-nightly-2/theta-m1 and preserve full
      resource, Theta identity, timing, push and concurrent M2 sibling receipts.
unresolved:
  - >
    Organization runner identities/group membership need the existing admin browser
    or API permission before mutation. Repository Default-group runner remains
    ineligible and offline.
  - >
    A full-work production profile does not exist. The current launcher hardcodes
    m1-canary and only performs the lightweight listener-start disk check.
  - >
    Current 201.3 GiB free space passes W2 but leaves insufficient mechanically
    safe margin for a 25 GiB capped cold runner workspace.
next_actions:
  - Recover a 225 GiB start floor or prove an exact lower cold-checkout peak.
  - Revalidate the three diagnostic listeners with the existing no-secret canary, then stop two.
  - Build one bounded admission/policy/workflow carrier for only m1-nightly-2/theta-m1 collect_tail.
  - Drain scheduled heavyweight writers, prove one natural run below 170 minutes, and keep M2 rollback for seven nights.
do_not_redo:
  - Do not add generic macstudio, macstudio-light, render-heavy or codex to M1.
  - Do not use m1-nightly-repo-1 or the Default runner group for W4.
  - Do not kill Theta/options/research production to manufacture a passing capacity receipt.
  - Do not add automatic fallback, another scheduler, queue or retry plane.
danger_areas:
  - >
    collect_tail commits, rebases and pushes main. Its production admission must
    bind exact repository, main ref, daily.yml@main and job identity, and must use
    the existing selected-workflow runner group plus a root-owned full resource guard.
  - >
    A first proof that crosses 170 minutes, breaches disk/memory/swap gates or loses
    Theta identity is a preserved failed receipt and rollback trigger, not authority
    to add another M1 listener or M4 capacity.
---
