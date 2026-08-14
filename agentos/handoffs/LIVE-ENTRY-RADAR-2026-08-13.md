---
workstream: WS:LIVE-ENTRY-RADAR
session: worktree-live-entry-radar-95b9ce
model: fable
ended_because: ci_handoff

mission: >
  Execute PR-0 of the operator-commissioned Live Entry Radar program: parallel archaeology
  (Tracks A-E), synthesis of the frozen research contract covering all eleven commissioned
  deliverables, adversarial review (Track F), Agent OS workstream/decision/discovery records,
  and the standard armed-PR handoff. No production behavior.

state_before: >
  Nothing existed for this program: no workstream, no research docs, no entry_radar namespace
  (verified: git ls-files, open-PR sweep, worktree list, agentos owns_paths grep, 2026-08-13).
  Adjacent prior art existed and was censused rather than rebuilt: DNR:KILL-WASHOUT-TURN
  (entry-stack Amendment-3 #1747), the PSS F1-F4 timing-family kills under the §7 ruler,
  engine/washout_turn.py and engine/mtf_upturn.py display organs, the prophet-live VPS lane,
  and the Terminal grey-dot implementation (charting-app signal_layer/confluence_v2.py).

changed:
  - path: research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md
    what: "The frozen contract: separation doctrine, kill compliance + NC-2 kill-arm, G0 locked spec + parity decision, C1-C5 arena + indicator-core law, PIT/leakage matrix, universe funnel + nomination bus, ratified live architecture, scoring doctrine, frozen §10 prereg numbers, comparison design, cohorts, episode contract, UI directive, PR-0..PR-9 sequence with §0 gates."
  - path: research/live_entry_radar/ (TRACK_A..TRACK_E)
    what: "Five census appendices with file:line receipts: Grey Dot forensics + fired dates (A), Macro indicator/entry-lane census (B), lobe producer + universe census (C), live plane + entitlements (D), eval-OS/replay conventions + DRL boundary (E)."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "Workstream with waves W0-W9 mapping to PR-0..PR-9, landmines, owns_paths claims."
  - path: agentos/decisions/ (DEC-LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE, DEC-LER-PROPHET-BOARD-IS-DESIGN-REFERENCE, DEC-LER-LIVE-LANE-VPS-5MIN-REST)
    what: "Founding decisions: separation from Prophet (operator commission); Prophet Board as direct design reference (operator directive, sister product, IA-only changes); VPS 5-min REST live lane with no WebSocket."
  - path: agentos/discoveries/DSC-TERMINAL-GREY-DOT-IDENTITY.md
    what: "Verified identification of the operator's grey dot with runnable falsifier and fired-date receipts."
  - path: agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-13.md
    what: "This handoff."

prs: [5578]

verified:
  - claim: "The grey dot is Terminal's early anticipation dot; fired dates computed for NVDA/NFLX/TSLA."
    command: "git show origin/master:signal_layer/confluence_v2.py (staged with confluence.py); early_dots(compute_signals(close), close) over data/stocks/<SYM>.parquet"
    result: "NVDA n=135 / NFLX n=132 / TSLA n=80 all-history; ≥2025 tables in TRACK_A §2.6; emitter comment 'old gray side-channel dot' verbatim at confluence_v2.py@origin/master:1174-1176"
  - claim: "The killed construction is decoded and distinguished, not hand-waved."
    command: "grep -n 'esx_washout_x_turn' research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md"
    result: "2W-D-min<25 × {A1,A2} layered on gate fires, killed by NC-2 proximity de-confound (:259); contract §2 carries the TS-R3 four-part distinction + kill-arm inheritance"
  - claim: "Prophet non-interference is mechanical and this PR adds no engine code."
    command: "git diff origin/main...HEAD --stat"
    result: "research/ + agentos/ files only; zero engine/, scripts/, templates/, site/ changes"
  - claim: "Record store is schema-valid."
    command: "python3 scripts/agentos.py validate"
    result: "exit 0, 0 errors (phantom-owns-path warnings expected for future build paths)"
  - claim: "Branch merges clean against fresh origin/main."
    command: "git merge-tree $(git merge-base HEAD origin/main) HEAD origin/main | grep -c '<<<<<<<'"
    result: "0 conflict markers"

unverified:
  - claim: "The 5-week-stale shared deep store (last bar 2026-07-08 at census) is a checkout artifact, not a production staleness."
    what_would_verify: "Read the production store's max bar date on the primary checkout or VPS; PR-2 hard-gates on feed_end regardless."
  - claim: "prophet-live's forward ledger accrues (data/prophet_live/forward.parquet has zero rows ever committed to main)."
    what_would_verify: "Confirm expected early-accrual vs stalled pipeline before PR-5 treats the reconciler as a proven precedent (Track D flag)."

unresolved:
  - "Probe-set hotness thresholds (Layer C) are PR-1 budget knobs, deliberately not frozen in PR-0."
  - "STARTER/RE-ENTRY family enumeration with emitter receipts is PR-2 archaeology (contract §18 A1.3 — family keys minted from receipts, never invented)."

next_actions:
  - "W1 (PR-1): probe universe + enlistment bus per contract §6 + TRACK_C. Named build items: wrapper classifier, hot_tape nomination tap, Supabase watchlist server-side adapter, day-one nomination spool."
  - "W2 (PR-2): detector framework + G0 artifact consumption + fixtures F1-F6. G0-VIS CLOSED by operator 2026-08-13 (contract §18 A1) — parity freeze unblocked; PR-2 also owns the A1 adapter obligation (verbatim family/subtype/stage preservation + expert-family keys from emitter receipts)."
  - "Every build session: fresh worktree off origin/main, read the contract + relevant track appendix, spawn Opus builder per §Model routing, arm merge-on-green, ci_handoff."

do_not_redo:
  - "Do not re-census producers/indicators/live-plane/eval conventions — Tracks A-E are the record; extend, don't re-derive."
  - "Do not re-litigate contract-frozen decisions (parity strategy, live architecture, scoring doctrine, §10 numbers) outside §18 amendments."
  - "Do not read charting-app's working checkout for G0 spec (month-stale, pre-#392 leaking 2D map) — spec reads pin origin/master; never seed a reimplementation from Macro research/signal_engine/confluence.py (verified silent fork, zero known_ts)."

danger_areas:
  - "engine/entry_signal.py, signal_gate.py, confluence_tiers.py, signal_quality.py, prophet_*.py: never touched by this program (contract §16; sibling WS:PROPHET-US-ENTRY-TIMING owns prophet paths)."
  - "Massive stocks WebSocket slot: unclaimed estate-wide; overflow EVICTS the oldest connection silently — Radar never opens it (DEC:LER-LIVE-LANE-VPS-5MIN-REST)."
  - "Session worktrees are SPARSE (DSC:SESSION-WORKTREES-ARE-SPARSE): data/, site/, mockups/ absent — existence checks via git ls-files / git show, never bare ls."
  - "Event ts vs known_ts: G0's emitted ts is the 3D bar OPEN date, up to 2 sessions before knowability — any consumer treating ts as decision date backdates every signal."
---
