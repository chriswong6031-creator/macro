---
key: NIGHTLY-SECMASTER-REFRESH-WEDGES-SILENTLY-ON-PRUNE-CONFLICT
claim: >
  The nightly security-master refresh (build_security_master --nightly,
  run_nightly_refresh) answers a VendorAliasPruneConflict by restoring last-good
  artifacts and returning 0 — by design (AMENDMENT ruling 11/§3) — which means a
  standing conflict WEDGES the committed data/reference artifact set indefinitely
  while every seed keeps moving. Measured 2026-08-20 -> 2026-08-28: the fresh
  (store, VMRK) alias row conflicting with the committed open (store, EQR) row froze
  the artifacts for 8 days; the visible symptoms were NOT the nightly's ::warning
  (nobody read it) but a spreading set of red artifact-pinned tests on main
  (committed-artifact staleness, AEP issuer-evidence drift, EA refusal-class drift,
  CN count 984-vs-1002) that sessions kept classifying as unrelated base reds. Exact
  population-count pins against a frozen artifact all go red TOGETHER once the wedge
  lifts, because every deferred lawful admission lands at once.
falsifier: >
  run_nightly_refresh (scripts/build_security_master.py:3476-3492) escalating a
  REPEATED prune conflict into a red run or a tracked issue instead of
  warn-and-return-0, or the AMENDMENT §2 same-id-refinement carve-out landing in
  _prune_stale_aliases (scripts/build_security_master.py:2590) so dated renames stop
  conflicting at all — either removes the silent-wedge mode.
so_what: >
  When several dataos artifact-pinned tests go red on main together with no code
  change, check the nightly security-master log for security-master-nightly-prune-
  conflict FIRST — the artifact is probably frozen, and the fix is curing the named
  conflict (a dated RenameEvent family + one-time hand-migration of the committed
  open row, per D2B1-R1 AMENDMENT §2 option 2 — executed for store/EQR->VMRK
  2026-08-28), then regenerating artifacts + appending a sidecar epoch in one PR.
  After unwedging, expect exact-count pins on live populations to rot within days;
  floor pins keep the downward regression bite without re-rotting (conversion done
  2026-08-28 for the US/CN/coverage pins).
kind: landmine
scope: [macro]
confidence: verified
verified_at: 2026-08-28
verified_by: >
  scripts/build_security_master.py:3476-3492 (dedicated VendorAliasPruneConflict
  handler: restore last-good, ::warning, return 0) and :2590 (the raise);
  committed data/reference/vendor_aliases.parquet ingested_at stamps frozen at
  2026-08-13/2026-08-20 while CN seeds had advanced 984->1002; pristine-base pytest
  runs 2026-08-28 showing the same 4 artifact-pinned reds on df7404226504 as on the
  migration branch pre-fix, all green after the cure + regen (353 passed).
---

Found while the EQR->VMRK key migration tripped the same conflict in tests. Related:
[[BREADTH-TICKER-FIXUPS-PIN-THE-FETCH-SYMBOL-TOO]].
