---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-1p-universe-cap
model: local
ended_because: blocked
mission: >
  FF-1P production commissioning: prove merged FF-1 through canonical universe,
  real SEC, real private Research R2, bounded July recovery, then one incremental.
  Stop on the first genuine production defect. Do not start FF-2. Do not merge.
state_before: >
  PR #5820 squash-merged at cd064848298063faac82059f71daf24bdd4112a2. Final tested
  head 83a8218d2ba7865bf56d1be7b1a137d2fd986e01 is byte-identical for
  broad_sec_store.py on current main. AgentOS still said awaiting_review / awaiting_ci.
  No production R2 proof existed. Local two-issuer SEC canary had passed against
  LocalStore only.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: "Raise MAX_UNIVERSE_ISSUERS 2500 -> 4000 so the live 2837-issuer parquet can bind. No other kernel, clock, recovery, or store changes."
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: "Regression: 2837 synthetic issuers bind; cap+1 still fail-closes; live parquet bind gated on full checkout."
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: "Record #5820 merged, production blocked on universe_invalid, FF-2 still todo."
  - path: agentos/discoveries/DSC-FF-1-LIVE-UNIVERSE-EXCEEDS-2500.md
    what: "Live parquet 2837 > merged cap 2500; scheduled run 32097495749."
  - path: agentos/decisions/DEC-FF-1-UNIVERSE-BIND-CAP-4000.md
    what: "Cap raise to 4000; parquet untouched; continuation limits untouched."
verified:
  - claim: "Current main contains merge SHA cd064848298063faac82059f71daf24bdd4112a2."
    command: "git merge-base --is-ancestor cd064848298063faac82059f71daf24bdd4112a2 HEAD"
    result: "exit 0 on both macro-main and this worktree"
  - claim: "broad_sec_store.py blob on current main matches final PR head 83a8218d."
    command: "git rev-parse HEAD:engine/fundamental_forensics/broad_sec_store.py && git rev-parse 83a8218d2ba7865bf56d1be7b1a137d2fd986e01:engine/fundamental_forensics/broad_sec_store.py"
    result: "both f35f3cf8b08391078beac2e5332da4bfd9100f7a before this repair"
  - claim: "Live parquet is 2837 unique tickers, 2837 unique CIKs, SHA-256 84bc9a713314b20f5803a65f353bcf89b1ad82f45683757b0f5e6b1fe4394190, 0 duplicates/malformed, >2500."
    command: "python3 -c load_universe/pandas unique counts on data/edgar/fundamentals.parquet from a full checkout"
    result: "rows=2837 unique_ticker=2837 unique_cik=2837 AAPL=0000320193 MSFT=0000789019; load_universe raised universe_invalid at 2500"
  - claim: "The only filing-forensics-broad-sec.yml run since merge is scheduled incremental 32097495749, conclusion failure, universe_invalid, 2s, MODE=incremental."
    command: "gh run list --workflow filing-forensics-broad-sec.yml && gh run view 32097495749 --log-failed"
    result: "one run; event=schedule; headSha=0823b0daced1ec2a713de75531f00533b1ffb0ef; detail universe has 2837 issuers; hard max is 2500; expected_issuers=0"
  - claim: "universe_invalid returns before any store put, so latest-complete cannot have advanced from this run."
    command: "sed -n '815,835p' engine/fundamental_forensics/broad_sec_store.py"
    result: "except BroadSecError: build empty receipt; return PollResult(exit_code=1) with no store call"
  - claim: "Schedule stayed incremental-only; shared concurrency group filing-forensics-sec; cancel-in-progress false; Wave-2 32095231301 finished 03:23:55Z before FF-1 03:59:58Z."
    command: "gh run list --workflow filing-forensics-sec.yml --limit 1 plus workflow YAML and the failed-run log MODE block"
    result: "Wave-2 success 03:22:21Z-03:23:55Z; FF-1 schedule if event_name != workflow_dispatch keeps MODE=incremental; no overlap"
unverified:
  - claim: "Private Research R2 prefix fundamental_forensics/broad-sec/v1/ has no latest-complete / latest-observation / continuation objects."
    what_would_verify: "GET those keys with R2_RESEARCH_* (or readonly) credentials. This session had no local R2_RESEARCH_* env and did not print GitHub secrets. Inference is the kernel return-before-put path plus the failed receipt showing observation_sha256=null."
  - claim: "After this cap raise lands on main, July recovery from 2026-07-12T11:23:15Z will converge."
    what_would_verify: "Re-run FF-1P commissioning: explicit recovery until pending_count=0, then one incremental."
unresolved:
  - "Production commissioning STOPPED at STATE E. July recovery was not dispatched."
  - "FF-1 is merged code, not PROVEN_LIVE."
  - "Sol must review this cap-raise PR. Do not merge from the worker session."
  - "FF-2 remains forbidden."
  - "Local R2 GET was not executed (no local research credentials)."
next_actions:
  - "Sol reviews the MAX_UNIVERSE_ISSUERS=4000 repair PR. Merge only if the cap choice is accepted."
  - "After merge, resume FF-1P: explicit recovery from 2026-07-12T11:23:15Z, one run at a time, then one incremental."
  - "Do not start FF-2."
  - "Do not shrink data/edgar/fundamentals.parquet."
do_not_redo:
  - "Do not treat PR #5820 merge as production proof."
  - "Do not dispatch recovery while the live parquet exceeds the bind cap on main."
  - "Do not alter the canonical parquet to fit 2500."
  - "Do not raise MAX_AFFECTED_ISSUERS or Company Facts byte budget to finish recovery in one run."
  - "Do not start FF-2, detectors, Prophet, or Neural Web."
  - "Do not mutate production R2 objects by hand."
danger_areas:
  - "A write into sparse-omitted data/ truncates the committed parquet."
  - "universe_invalid receipts print storage keys that were never written."
  - "4000 is still a fence; a parquet that grows past 4000 will fail the same way. The live bind test is the tripwire."
  - "Shared concurrency group filing-forensics-sec serializes with Wave-2."
decisions:
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
discoveries:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
---

FF-1P commissioning classified production as STATE E (unexpected failure),
not empty and not recovery-in-progress. The scheduled incremental could not
bind the canonical universe. Repair is the bind cap only.
