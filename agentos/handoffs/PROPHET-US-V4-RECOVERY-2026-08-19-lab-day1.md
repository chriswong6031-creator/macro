---
workstream: WS:PROPHET-US-V4-RECOVERY
session: prophet-lab-r4-migration-day1
model: fable
ended_because: blocked

mission: >
  Chairman commission 2026-08-18: Prophet Operator Lab (LIVE|LAB operator mode)
  + R4/MP-1 production migration program. Day 1 = LAB-0 recut merged, Radar W4.1
  transport + P-LAB-API built and twice-reviewed and armed, R5/R5.1/R5.2 RIG
  design cycle through the revision, plus the fleet main-red heals the merges
  depended on. Session ends blocked on an external gate: every remaining merge
  waits on the next nightly roster snapshot self-healing house-law-registry (VMRK).

state_before: >
  LAB-0 unwritten; V4-B5 conflated the operator lab with the authoritative desk;
  Radar confirmed-lane transport structurally broken (probe_set nightly_lanes read
  never populated; W5 rejected every W4 envelope wholesale); no Lab API; R4
  reference committed but never RIG-approved; MP-1 unexecuted.
changed:
  - {path: "research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md", what: "MERGED #5924 — LAB-0 recut: B5A/B5B split, wave-graph ruling 14, DEC:PROPHET-LAB-B5A-RECUT, Radar W4.1 wave charter"}
  - {path: "tests/test_prophet_postmortem.py", what: "MERGED #5939 — ASTS ladder-rung re-pin + agentos/discoveries/DSC-BREADTH-CLOSES-CACHE-UNION-UNIVERSE.md (main-red-repair)"}
  - {path: "engine/entry_radar/live_pack.py", what: "BUILT+REVIEWED+ARMED #5929 — W4.1 transport: v2 pack confirmed_lanes in pack hash, W5 envelope consumption + keep-first dedup (scripts/reconcile_entry_radar.py), e2e contract test, plus the #5938 suite wiring heal in .github/ci/legacy-jobs.yml"}
  - {path: "app/prophet_lab.py", what: "BUILT+REVIEWED+ARMED #5928 — P-LAB-API: engine/prophet_lab/ projection package, six frozen boards, observation-class honesty fail-closed, generation/health blocks, 99+ fixture tests"}
  - {path: "research/reference_integrity/prophet-board-lab-r5/verdict.yml", what: "ARMED #5931 — R5 RIG cycle record: authority verdict REVISE + both critic receipts committed verbatim"}
  - {path: "mockups/refs/prophet_lab/", what: "BUILT #5940 — R5.1+R5.2 revision at frozen SHA f40ae70ac989; two-pass critic cycle + verdict OWED (C12)"}
verified:
  - {claim: "#5924 merged and live on origin/main", command: "git show origin/main:research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md | head -3"}
  - {claim: "#5939 merged", command: "gh pr view 5939 --json state --jq .state"}
  - {claim: "delta re-reviews returned MERGE-SAFE at heads 8bbb372d6dee (#5928) / e69edc55df9d (#5929); post-rebase heads carry the identical reviewed diffs", command: "gh pr view 5928 --json comments (round-1 dispositions + rebase evidence); gh pr view 5929 --json comments"}
  - {claim: "R5.2 harness 125/125 verify, 26/26 mutations caught at f40ae70ac989", command: "see PR #5940 body 'R5.2 fix round' section for the pasted tails; reproduce via mockups/refs/prophet_lab/tools/{verify,mutation_test}.py on a playwright host"}
unresolved:
  - "Armed PRs #5928/#5929/#5931 unmerged — gated on the house-law-registry VMRK self-heal at the next nightly (~05:00Z) + a green main proof postdating their reds"
  - "#5940 two-pass critic cycle + authority verdict + (if PASS) approval.yml against f40ae70ac989"
  - "baseline.yml:70,:117-118 stale lines in the R5.1 packet (flagged, outside the R5.2 round's owned files)"
  - "Radar live-commissioning gates (§1.4 of the body: timestamp-compare fix, baseline ordering, R2 transport wiring)"
  - "P-MP1-SHELL gates (C8 R4-composition critique or override; DNR:KILL-PROPHET-POP-MERGE recheck; DA-002 routed to a DS-PR)"
unverified:
  - "The house-law-registry self-heal thesis (rests on #5936's collector fix; falsifier: still red after a fresh roster snapshot)"
  - "The VPS terminal-slice directory (/opt/terminal/terminal/public/data) — must be checked live before deployment config"
next_actions:
  - "Execute §1 of the body in order: verify overnight settlements → #5940 cycle → P-MP1-SHELL → Radar live commissioning → P-LAB-UI → live verification + operator guide"
do_not_redo:
  - "§2 of the body: reviewed PR semantics, frozen boards, production bounds, the VMRK alias (regression proven), data receipts, stale R5.1 critic receipts"
danger_areas:
  - "§3 of the body: harness stops eat subagent context (checkpoint notes + resume); the armed-backlog refresh needs a proof postdating the reds; REST quota left low"
---

# Handoff — Prophet Operator Lab (V4-B5A) day 1 · 2026-08-19

**Workstream:** WS:PROPHET-US-V4-RECOVERY (wave b5a) · joint with WS:LIVE-ENTRY-RADAR (W4.1)
**Program contract:** `research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` (merged, #5924)
**Author:** the LAB-0 commissioning Fable session (Chairman commission 2026-08-18). Cold-stranger
oriented: every claim names its receipt; nothing here requires this session's memory.

## §0 State of the program (verified at authoring)

| Item | State | Receipt |
|---|---|---|
| LAB-0 records (B5A/B5B recut, ruling 14, DEC:PROPHET-LAB-B5A-RECUT, Radar W4.1 wave) | **MERGED** | #5924, squash 71c2af497568; on origin/main |
| Radar W4.1 transport (v2 pack `confirmed_lanes` in pack hash, W5 consumes `entry_radar.events/v1` envelopes, keep-first dedup, earliest-`pass_ts` observation, e2e contract test) | **BUILT + 2-round opus review MERGE-SAFE + ARMED** (`merge-on-green`+`main-red-repair`) | PR #5929, head rebased on healed main; review receipts in PR comments/session records; also carries the #5938 `test_ci_gate_reliability_report.py` wiring heal |
| P-LAB-API `GET /api/prophet/lab/v1` (six boards, all-false authority block, observation classes fail-closed, generation block, per-board availability, 99+ tests) | **BUILT + 2-round opus review MERGE-SAFE + ARMED** | PR #5928, head rebased on healed main; review round-1 dispositions in PR body |
| D-LAB-R5 reference + RIG cycle (verdict REVISE, both critic receipts committed) | **ARMED** (cycle record merges as-is, r3 precedent) | PR #5931 + `research/reference_integrity/prophet-board-lab-r5/{verdict.yml,reviews/}` |
| D-LAB-R5.1 + R5.2 revision (all R5 majors + both critics' R5.1 majors closed; frozen SHA `f40ae70ac989`, packet head `e9b6f125afdf`) | **BUILT — verdict OWED** (see §2) | PR #5940 (stacked on #5931's branch; narrows when #5931 merges) |
| Main-red heals this session contributed | **MERGED** | #5939 (ASTS re-pin + DSC:BREADTH-CLOSES-CACHE-UNION-UNIVERSE); plus absorbed-then-superseded work landed via #5937/#5941 |

**Why the armed PRs have not merged yet:** main's residual red is `house-law-registry`
(`scripts/check_symbol_rename_drift.py`: VMRK absent from the frozen roster snapshot). #5936
fixed the collector that froze the snapshot since 2026-08-11; the **next nightly collection
(~05:00Z) writes the first unfrozen snapshot including VMRK and the check should self-heal**. Do
NOT ship a `lib/ticker_aliases.py` VMRK entry as a shortcut — it was built, proven to regress 5
dataos security-master tests (`VendorAliasTable._assert_unambiguous` IdentityError), and
deliberately reverted (receipts in #5939's body). #5928/#5929 are **authority-changing**
(`.github/ci/legacy-jobs.yml`), so their lawful merge condition is their OWN run concluding fully
clean — which becomes possible exactly when house-law-registry heals. The sweeper then merges
both; nobody needs to babysit the night.

## §1 Next session — execution order

1. **Verify the overnight settlements:** #5928, #5929, #5931 merged (if a red persists past the
   nightly, attribute before touching anything — `house-law-registry` still red after a fresh
   snapshot means the self-heal thesis was wrong; the fallback fix is a dated `RenameEvent` in
   `scripts/build_security_master.py` + nightly-side regeneration, an authority-changing PR that
   must land on otherwise-green main). W4.1's merge closes Radar wave W4.1 — update its row.
2. **Finish the #5940 RIG cycle (C12):** run BOTH critics against frozen SHA `f40ae70ac989` —
   quarantined first passes (the R5.1 receipts in the session record are stale against this SHA
   by construction), then reveal rationale for genuine second passes, then mint the authority
   verdict + `reviews/*.yml` + (if PASS) `approval.yml`. Known open items for that cycle:
   `baseline.yml:70,:117-118` carry two stale lines (flagged, deliberately not edited out of
   OWNED FILES); the R5.2 vocabulary move ("Seen live"→"Seen first-hand"/第一手观测) is a
   second-round change a reviewer may push back on; verify the landing behaviour against LAB-0
   §6.5 (the R5.2 worktree predated LAB-0 on its branch and could not re-check).
3. **P-MP1-SHELL** (after the R5-family cycle passes): gates recorded in the R5 verdict —
   **C8** (R4's composition has never had its own dual-critic pass: commission it, or record an
   explicit named override), MP-1's population re-source vs `DNR:KILL-PROPHET-POP-MERGE`,
   DA-002 (`--pv-buy`≡`--up` in production theme.css — any fix is a separate DS-PR, outside
   MP-1's own scope), MP-1 §7/§9 laws (stocks-mode-only, candidates separate, non-US byte
   parity, server-side withholding, no theme.css change).
4. **Radar live commissioning** (operator arm; LAB-0 §6 step 3) — hard gates recorded this
   session: (a) fix the lexicographic timestamp compares in `engine/prophet_lab/observation.py:43,46`
   + `sources.py:183` (operator-minted baseline with a non-Z offset can relabel a seed
   live-forward — R1); (b) baseline marker minted STRICTLY AFTER the first spooled pass
   (N-a — else the Lab is permanently all-seed); (c) production spool transport wiring (the API
   reads local dirs; production is R2-first — S2's deferred half); (d) consider the collapsed-
   duplicate counter (N-c, #5929 review nit). Full-RTH/H10/H21 maturation is NOT a gate (LAB-0).
5. **P-LAB-UI** per LAB-0 §6 step 5 (ProphetBoardController; W-L1 receipts are in the session's
   product census — `templates/dashboard.html.j2:17792-18990`), then deployment verification
   (VPS terminal-slice dir check — likely `/opt/terminal/terminal/public/data`, UNVERIFIED),
   `PROPHET_LAB_DISABLED` provisioning, live URL + operator guide to the Chairman.

## §2 do_not_redo

- Do not reopen the reviewed semantics of #5928/#5929 (two full adversarial rounds each; the
  dispositions tables in their PR bodies are the record).
- Do not re-litigate the six frozen Lab boards, the observation classes, or LAB-0 §1-§5.
- Do not widen `_MIN_PRICED_COVERAGE`/the ≤1.0 bound, any price-ladder tolerance, or a detector
  spec to silence a test (this session's heals establish the pattern: pin fixtures, re-pin
  receipts, never bend production invariants).
- Do not add the VMRK alias to `lib/ticker_aliases.py` (regression proven — #5939 body).
- Do not edit `data/` receipts from a PR (nightly is sole advancer) — the breadth latent defect
  is recorded as DSC:BREADTH-CLOSES-CACHE-UNION-UNIVERSE with the lawful fix direction.
- Do not treat R5.1's critic receipts as current — they bind SHA `f889d5eb35f3`, superseded by
  `f40ae70ac989`.
- #5925 (sibling, probe-population fix in `live_pack.py`) is complementary to W4.1, not
  competing — whichever lands second rebases knowingly (coordination comment on #5925).

## §3 danger_areas

- **Harness stops eat subagent context**: background workers stop mid-task repeatedly and their
  transcripts are sometimes reaped (two agents lost entirely this session). Mitigation that
  worked: interim checkpoint notes every ~8 units of work + resume-by-name; treat every final
  packet as at-risk until received.
- **The armed backlog logic**: a green main proof must POSTDATE the PRs' reds for the sweeper's
  refresh to drain them; preflight for in-flight baselines before dispatching (`cancel-in-progress`
  livelock). This session never dispatched a baseline — others' dispatches sufficed.
- **REST quota**: this session left the pool low (~500). Preflight `gh api rate_limit`.

## verified

- `#5924 merged`: `git log --oneline -1 origin/main` at authoring ancestor check + `git show origin/main:research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md`.
- `#5939 merged`: `gh pr view 5939 --json state` → MERGED.
- Review verdicts: session records (delta re-reviews returned MERGE-SAFE for #5928 at head 8bbb372d6dee and #5929 at head e69edc55df9d; both heads since rebased content-identically — post-rebase heads carry the same reviewed diffs plus the wiring heal noted in #5929's comments).
- R5/R5.1/R5.2 receipts: `research/reference_integrity/prophet-board-lab-r5/` (merged with #5931 when it lands) and PR #5940's body + packet commits.
