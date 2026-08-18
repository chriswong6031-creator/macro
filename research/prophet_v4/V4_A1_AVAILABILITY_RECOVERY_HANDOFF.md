# V4-A1 — AUG-14 AND CURRENT-SESSION SETTLEMENT RECOVERY (ACCEPTANCE CONTRACT)

> **SUPERSEDED AS A SPAWN COMMAND (V4-0B, 2026-08-18): DO NOT LAUNCH A V4-A1 SESSION.**
> Active Availability/outage sessions own the implementation (incident receipt #5742).
> This document is now the ACCEPTANCE CONTRACT Sol reviews the sibling return against —
> its gates (§0) define "settled"; its spawn/sequencing language below is retained as
> historical contract detail only. See `WAVE_GRAPH_AND_MERGE_ORDER.md` §4.11 and the
> WS `a1` row.

**Program:** `WS:PROPHET-US-V4-RECOVERY` wave `a1` · **Written:** 2026-08-17 by V4-0A (Fable) at pin `fc0557bb0873`
**Session model routing:** sonnet `builder` executes; opus `reviewer` red-teams the recovery claim before merge; the commissioning main loop (or the session's own loop) adjudicates. Every spawn carries explicit routing per repo law.
**RE-PIN FIRST:** fresh `origin/main` at session start; every receipt below is as-of 2026-08-17T11:44Z and the estate moves fast — re-verify §2 before acting.

## §0 Acceptance gates — "not done unless" (inline by law)

1. **Root cause named with receipts** for run `31977372592`'s `engine` job failure (and the queued-~13h downstream jobs), from that run's logs — not pattern-matched from prior incidents. If logs are gone, say so explicitly and diagnose from the next live run.
2. **Every owed NYSE session settles or is honestly declared unrecoverable, on the production reader.** Owed at write time: **2026-08-14** (Friday; never captured) and the **current session at execution**. Settled = the served `site/prophet/index.json` shows the owed `source_asof` + a plan cohort for it on git main, R2, AND the VPS (`showcase.json` public check; index via authenticated path or operator screenshot). Unrecoverable = an explicit missing-session receipt visible to the reader (not a silent gap), constructed per masterplan §18.5.
3. **No future knowledge:** Aug-14 reconstruction only from data lawfully knowable for Aug-14 (PIT stores, that day's collected artifacts). If exact reconstruction is impossible, publish the unrecoverable receipt — do NOT synthesize from Aug-17 knowledge. (`WS-PROPHET-US-AVAILABILITY.md` landmine: 2026-08-11 precedent — backfill refused absent operator override.)
4. **The FULL checkpoint manifest advances, not just the board:** a recovered nightly must land the closed allowlist (`daily.yml:2717-2732`) — index/showcase/board_read_sparks, ledger+quarantine, arena scoreboard, origination receipts, legacy_shadow parts — AND the candidate store `data/us_prophet_rank/candidates/` (stalled since 08-14) and `site/turn_watch/turn_watch.json` (stale at 08-13) must advance with their next wired nightly. If any lane stays frozen after your recovery, name it and why.
5. **Issue #5742 updated/closed only when the reader-visible truth supports it** — closing comment must cite the served `source_asof` and cohort, not a green run.
6. **Rescue discipline intact:** read the open `prophet-outage` issue receipts BEFORE any dispatch; NEVER dispatch while a `daily.yml` run is queued/in-progress; stay inside `prophet_rescue.py`'s 2/night budget semantics (budget counts attempts incl. runless POSTs); never cancel a production lane (`gh_quota_guard.py` shape 6 blocks it; a cancel is invisible to every staleness instrument).
7. **Ship loop:** commit → push → PR → CI → same-day squash-merge → live verification (the served artifact, not the workflow conclusion). Arm `merge-on-green`, stay to merged.
8. **Durable records in the same PR:** update `research/prophet_v4/CAPABILITY_LEDGER.md` rows 1/5/28 (+13 if TURN WATCH advanced), the `WS:PROPHET-US-V4-RECOVERY` wave `a1` row, and write `agentos/handoffs/PROPHET-US-V4-RECOVERY-<date>.md`. If your findings prove `WS-PROPHET-US-AVAILABILITY.md` stale (its W0/`next_action` predate the live rescue lane), correct that record from merged evidence in the same PR.

## §1 Mission and why it matters

Close the actual stale-data incident — the Chairman has been served Aug-13 picks since Friday. PR #5723 fixed a scheduler mechanism; nobody has yet recovered the missed session or proven a post-fix nightly. This wave makes the production reader honest again and is the gate for every later V4 wave (A2/A3 build on a settled baseline).

**User journey that must work:** Chairman opens Prophet (VPS, authenticated) and sees an honest owed-session status — fresh picks for the latest session, or an explicit "session missing" receipt. No silent staleness.

## §2 Verified starting state (2026-08-17T11:44Z — re-verify at spawn)

- All serving surfaces byte-identical at `source_asof=2026-08-13`; 206 plans; newest cohort 08-13 (27 plans); no 08-14+ cohort anywhere. Last checkpoint commit `012fbedc64` 2026-08-14T04:25:52Z.
- Run `31977372592` (Sat 22:48:50Z): collect/capital_structure/factor_series/factor_panel/cortex green; `engine` **failure**; ~8 downstream jobs queued ~13h; `publish` (Pages) success under `if: always()`.
- `prophet-rescue.yml` red (alert semantics) on wakes 06:03→11:00Z; `nightly-liveness.yml` green 08:45Z (coarser cadence — disagreement is expected behavior, not a contradiction).
- Issue #5742 OPEN, zero comments; last known dispatch-budget reading 1/2 (from the 08-15 issue body — re-read the issue, do not trust this).
- Publication mechanism + the unexplained 08-16 Pages-newer-than-git violation: `research/prophet_v4/CURRENT_STATE_2026-08-17.md` §2. Diagnosing THAT violation is A3's job, not yours — but your engine-failure diagnosis may overlap (both involve push contention); record anything you learn as evidence for A3.
- Key landmines: index top-level `asof` is wall-clock (`DSC:PROPHET-ASOF-IS-WALL-CLOCK`) — verify freshness by `source_asof` + cohorts only; run conclusions decouple from Prophet delivery in both directions (`DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET`); the "two memories of the board" differ (candidates store vs snapshots.jsonl) — don't conflate when checking what shipped.

## §3 Scope and owned paths

- **In scope:** diagnosing and fixing the specific breakage that is preventing the nightly checkpoint from landing (whatever run `31977372592`'s logs name — could be daily.yml steps, push retry, disk, a build script); executing/awaiting the recovery nightly; the Aug-14 decide-and-receipt; reader verification; the record updates of §0.8.
- **Owned paths while active (Lane A holds the publication plane alone):** `daily.yml` Prophet-relevant steps and `scripts/build_prophet.py`/checkpoint plumbing as needed. `scripts/prophet_rescue.py` and `scripts/check_nightly_liveness.py` are **`WS:PROPHET-US-AVAILABILITY` property** (wave-graph §4.2): touch them only if the root cause lives there, and then this session executes as that workstream's continuation — update its record in the same PR; no unilateral freeze of a sibling's files.
- **Existing instruments to USE, not re-derive:** `scripts/freshness_sentinel.py` (`client_visible_session()` reads the production reader's served bytes; `sentinel.first_fresh/v1` append-only settlement receipts — your gate-2 reader proof should cite its reading); `engine/prophet_integrity.py` (`outage_backfill` origination prefix + `is_reconstructed()` — the existing reconstruction-provenance law your gate-3 Aug-14 decision must stamp through).
- **Explicit non-goals:** no settlement manifest (A2), no bundle-ID fence (A3), no episode/lifecycle/availability contracts (B-lane), no Radar arming (B6), no Fusion PR-3B files (`WS-PROPHET-CONDITIONAL-FUSION.md` owns_paths — 8 paths, forbidden), no score/rank changes, no UI work, no fire drills (A4). One wave, one capability: **sessions settle**.

## §4 Ordered implementation sequence

1. Re-pin main; re-run the §2 checks (surfaces, run states, issue, budget).
2. Pull run `31977372592`'s engine job logs; name the failing step with the log lines. Check whether the queued downstream jobs ever concluded or were orphaned (queued >40 min with pool moving = orphan escape per repo law).
3. If a code/workflow defect: fix minimally on a `claude/v4-a1-*` branch; PR; merge per ship loop. If purely operational (e.g., the next scheduled nightly will self-heal): justify with receipts, then supervise that nightly.
4. Recovery execution: prefer the ordinary scheduled nightly landing tonight's session; dispatch manually ONLY under the rescue etiquette of §0.6 (clear field, budget available, issue receipts read).
5. Aug-14 decide: attempt exact PIT reconstruction only if the inputs for 08-14 exist in stores; else publish the unrecoverable receipt (masterplan §18.5 shape) to the reader.
6. Verify the reader (git/R2/VPS `source_asof` + cohort), update #5742 truthfully, land §0.8 records.
7. STOP. Return: root cause, sessions settled/receipted, PR number(s), what A2 should read first. No auto-roll into A2.

## §5 Failure states to defend against

- A green `daily.yml` that gate-skipped (7s success pattern) read as recovery — verify by served bytes, never by run conclusion.
- Dispatching over a queued run (supersede/livelock class — measured, not hypothetical).
- A recovery that lands the board but leaves the candidate store / legacy-shadow / TURN WATCH lanes frozen (partial manifest = gate 4 fails).
- Synthesizing Aug-14 from later knowledge (gate 3).
- Closing #5742 on a workflow conclusion (gate 5).
- Weakening the fail-closed checkpoint fence to "make it land" (Fusion WS do_not_redo binds: do not weaken it to look green).

## §6 Stop condition and continuation

Stop at: owed sessions settled-or-receipted on the reader + records landed + PR(s) merged + #5742 truthful. Continuation handoff owed to A2 (settlement manifest): include the exact clocks you observed (`source_asof`, `computed_at`, publish times, reader check time) — A2 turns your manual verification into the machine-verifiable `prophet.settlement_manifest/v1`.
