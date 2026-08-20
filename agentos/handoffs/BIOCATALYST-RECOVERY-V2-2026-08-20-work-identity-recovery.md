---
workstream: WS:BIOCATALYST-RECOVERY-V2
session: sol/biocatalyst-recovery-v2-work-identity-recovery
model: local
ended_because: complete
prs: [5788, 5793, 5804, 5810, 5906, 5927, 5934, 6052]
decisions:
  - DEC:BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI
discoveries: []
mission: >
  Recover durable Agent OS work identity for the already-existing BioCatalyst
  Recovery + Alpha Engine V2 program without creating a new semantic program,
  widening runtime authority, or mis-assigning core P0 recovery to the separate
  BPC JV snapshot or draft BCI programs.
state_before: >
  The canonical Recovery V2 masterplan had been on main since #5788 and a coherent
  P0 execution chain had progressed through merged #5793/#5804/#5810/#5906/#5927/
  #5934 to #6052, but Agent OS had no matching workstream. Linear therefore initially
  mapped #6052 to WS:BPC-JV-RECON by title/domain similarity, even though that workstream
  owns finite licensed-snapshot archaeology/onboarding rather than core product hydration.
  During this records PR's review window, a separate Chairman/Sol-commissioned COO lane
  adjudicated #6052 PASS, released its author hold, and #6052 merged after green CI.
changed:
  - path: agentos/workstreams/WS-BIOCATALYST-RECOVERY-V2.md
    what: >
      Restores the missing workstream identity, exact P0 chronology, records #6052 as
      separately accepted/merged, makes entitled production acceptance the live gate,
      preserves source/soak fences and keeps post-P0 expansion unauthorized.
  - path: agentos/decisions/DEC-BIOCATALYST-RECOVERY-V2-CORE-NOT-JV-OR-BCI.md
    what: >
      Rules that core Recovery V2 is its own Agent OS workstream under the existing
      biocatalyst semantic parent, separate from BPC JV and draft BCI, while recognizing
      the later independently valid #6052 implementation acceptance.
verified:
  - claim: >
      research/biocatalyst_recovery_v2 is the canonical repository form of the
      Recovery V2 program and freezes P0 hydration as the immediate PR-by-PR job.
    command: >
      Read research/biocatalyst_recovery_v2/README.md and Part 01 on current main.
    result: >
      README names the directory canonical and explicitly says P0 production
      hydration diagnosis/recovery comes first; later parity/alpha work waits.
  - claim: >
      The encoded execution chain is real and not inferred from titles alone.
    command: >
      Read exact GitHub state/bodies for #5788, #5793, #5804, #5810, #5906,
      #5927, #5934 and #6052.
    result: >
      All eight are now merged in the stated chain. #6052 merged as
      427d676de1a3ba086e4b63480018ecd733dd666e after a separate commissioned
      COO adversarial review released its author hold and returned PASS.
  - claim: >
      The current #6052 authority is production acceptance, not another speculative repair.
    command: >
      Read PR #6052 body and issue comment 5355409048 after merge.
    result: >
      Review PASS says normal macro-update deploy, then immediate entitled P0-C2
      production acceptance; do not start P1 or a ContractRegistry/bootstrap PR first.
  - claim: >
      WS:BPC-JV-RECON is a different program slice and cannot own core recovery.
    command: Read agentos/workstreams/WS-BPC-JV-RECON.md on current main.
    result: >
      It owns finite JV snapshot reconstruction/onboarding, preserves source-soak
      boundaries, and does not describe the core P0 hydration chain.
  - claim: >
      Draft Biopharma Cycle Intelligence cannot silently supersede this recovery.
    command: Read current PR #5821 body/state.
    result: >
      #5821 is draft/unmerged and its own federation keeps BioCatalyst clinical/
      regulatory truth, workbench and independent production recovery in BioCatalyst.
unverified:
  - claim: >
      This new Agent OS workstream/decision/handoff trio passes the repository's
      final exact-head hosted Agent OS/schema/CI checks after reconciliation with #6052.
    what_would_verify: >
      Refresh this records branch onto current main, run hosted checks on that final
      exact head, and inspect all required contexts before merge.
  - claim: BioCatalyst P0 production hydration is fixed.
    what_would_verify: >
      Normal macro-update deploy of merged #6052 followed by a real entitled production
      browser/API journey with serving identity, timings, typed states and no hidden
      contract/console/network failure.
unresolved:
  - "Which exact deployed process/generation serves the first post-#6052 P0-C2 acceptance run."
  - "Whether the accepted #6052 path passes the real Edge/served-route latency and product journey once deployed."
  - "Post-P0 parity/alpha/asymmetry/Prophet sequencing remains outside this identity repair and must follow accepted architecture only after P0 production acceptance."
next_actions:
  - "Refresh MAS-49/#6079 onto current main and require exact-head Agent OS/schema/CI green with exactly WS + DEC + handoff changed."
  - "Merge MAS-49 only if those checks are green and the current-main ownership review remains clean."
  - "Then create the Linear project WS:BIOCATALYST-RECOVERY-V2; represent MAS-12/#6052 as the completed R2 implementation, and create/keep a separate production-acceptance gate open."
  - "Deploy merged #6052 through normal macro-update and immediately run the real entitled P0-C2 acceptance."
  - "If production fails, stop on the first causal edge. Do not start P1 or a speculative ContractRegistry/bootstrap PR first."
do_not_redo:
  - "Do not remap #6052 to WS:BPC-JV-RECON."
  - "Do not assign core P0 recovery to draft/unmerged BCI #5821."
  - "Do not mint another semantic biocatalyst program; the missing object is Agent OS work identity."
  - "Do not mutate collectors/source roster/cadence/fixed cohort/launch-SLO law to make serving recovery pass."
  - "Do not re-run the P0-A auth-vs-caller-binding diagnosis, P0-C2 entitlement discriminator, or R0 deep-validation profile."
  - "Do not resurrect #6052's author hold after the separate commissioned PASS/release/merge."
  - "Do not call local/off-process performance proof or #6052 merge itself production acceptance."
  - "Do not authorize post-P0 alpha/Prophet expansion from this work-identity record."
danger_areas:
  - "The shared deploy repair in #5804 is historical evidence, not a path this workstream owns; do not absorb app/deploy/update.sh into BioCatalyst ownership."
  - "Existing authorized browser sessions can prove entitlement without exposing tokens. Never print or persist JWT/cookie material in a handoff or Slack/Linear."
  - "The latest #6052 review explicitly says no ContractRegistry/bootstrap PR first; production proof of the accepted bounded repair is now the shortest lawful path."
  - "A new Agent OS row can make dashboards look complete without improving the product. P0 remains open until real entitled production proof closes it."
---

# Return point

Read the new workstream and decision, the Recovery V2 README/Part 01, and merged PR #6052
including comment 5355409048. The work-identity gap is repaired on this branch; the implementation
repair has separately merged. The next capability owed is **not another architecture layer** — it is
normal deployment followed by real entitled P0-C2 production acceptance.
