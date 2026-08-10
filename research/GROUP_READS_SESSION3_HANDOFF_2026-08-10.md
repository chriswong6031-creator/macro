# Group Reads — session-3 handoff (2026-08-10, ~07:00Z)

**From:** the continuation session that landed the armed board and live-verified the program.
**Supersedes:** `research/GROUP_READS_SESSION2_HANDOFF_2026-08-09.md` (its resume sequence is fully executed).
**Masterplan:** `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` (#4991, merged) — §0 gates still bind every future wave.

## 1. Final board — EVERYTHING MERGED AND LIVE

| PR | Wave | Merge |
|---|---|---|
| #4991 | Masterplan | merged (session 2) |
| #5008 | GR3 linked-outsiders plane | merged (session 2) |
| #4995 | GR0 pulse plane + episode ledger (keystone) | `904301046d5`, 08-09 13:20Z |
| #4996 | GR2 earnings pulse + sympathy | `49327a9`, 08-09 17:24Z |
| #5011 | GR1 READ surfaces | `57c1413`, 08-09 17:28Z |
| #5020 | GR3b counterparty unlock | `8cd281f`, 08-09 17:31Z |

**Live verification (all green, 08-10 ~06:50Z):**
- `site/basketdata/{pulse,episodes,earnings_pulse,linked_outsiders}.json` committed + serving (subscriber-walled; verified via committed bytes + rendered pages). pulse.json: 49 baskets, `group_pulse.v1`, as_of 08-07.
- Ledgers under `data/group_pulse/` advanced ONLY by the nightly engine run (03:36Z "engine: regime update 2026-08-10"): episodes 2,004 rows (latest session 08-07), sympathy 6,202 rows, **linked_outsider_edges 1,902 rows — GR3b's unlock is feeding real edges** (was 0 for months).
- READ band live on `basket/<id>.html` (34 `gpr-` nodes on ai_semiconductors, `gpr-stance` present, zh in band); board chips live on `sector_central.html` (4 `gpr-` nodes; baseline pre-bake was 0). Baked by `render: site re-render 2026-08-10 (scope=all)` after the freeze below cleared.

## 2. What this session had to clear to land it (fleet context, keep for pattern-recall)

1. **Interlocked fleet reds** (partial-heal deadlock #4850 geometry): main red on (a) `test_every_first_party_import_resolves` — merged #5008 imports `engine.group_pulse`, which only #4995 provides — and (b) the govrev candidate family ×35 — #4951 made `recipient_query_terms` required in the workspace coverage-manifest schema without regenerating the committed twins. A standalone heal for either stays red on the other; **the govrev twin heal rode inside #4995** (derivation-true backfill via the real `recipient_query_terms()` + `_workspace_bundle_id()` rebind; byte-true compact serialization; commit `90fda71fc51` in #4995's chain).
2. **`gh run rerun --failed` re-tests the ORIGINAL pinned merge SHA** — useless for picking up base heals; move the head instead.
3. **PR runs are changed-file scoped; main dispatches run the full suite** — PRs merge green past latent full-suite reds; scoped heal PRs don't deadlock; a red main dispatch needs per-family attribution before believing anything about your own merge.
4. **#5124's hosted-pool return UNMASKED @needs_node suites** (node absent on the old pc-render boxes = silent skips reading as passes). The regime-sizing parity red was latent since #4512 (16:42Z) removed the ⚠ from one renderer fork; my #5187 (revive glyph) was correctly closed — **#4512's later intent was iconless-both**, completed in the #5188 window. Lesson recorded: `git log -S` with a RENDERED string misses per-file source-syntax changes; search each file's own source shape before choosing a parity direction.
5. **Render freeze 18:00Z→~04:00Z**: `check_government_revenue_projection` fail-closed on `coverage.award_events.rejected=9, reason=None` — a state post-#5086 engine code cannot produce. The Mac SAM lane ran a checkout predating #5086 (old contract still rejecting the 9 issuer-impact events #5086 admits). Self-healed when the lane refreshed (rejected=0 at `5fc18d5aac8`); renders then went green without intervention. Chip `task_20c5a989` remains for the govrev/ops lane iff the lane's checkout pins stale again (see also #5029, lru_cache-pinned schema).
6. Signal-lab salvage from session-2's step 4 was already covered by #5079 (deepcopy at `engine/signal_lab.py:1883`); branch `claude/main-heal-spvector-factor` is redundant. #5034 is another session's live |t|-rank test improvement — untouched.

## 3. Worktree tidy (report-only, per WORKTREE_GC_POLICY)

All Group Reads worktrees now hold MERGED work and are GC-eligible on the normal lane (do not force): `gr0-group-pulse`, `gr2-group-earnings`, `gr1-basket-read`, `gr3b-counterparty-unlock`, `gr3-linked-outsiders`, `group-reads-masterplan`, `main-verify-0808` (redundant salvage), `gr-heal2-signal-lab` (session-2 handoff branch — the doc is superseded by this file). Remote branch `claude/heal-regime-sizing-parity` deleted (closed #5187).

## 4. Program continues — next session picks up here

- **GR4**: fold basket state-change events into Turn Desk artifacts (DNR:KILL-ROTATION-SCHEDULE — no parallel surface), `docs/site_semantics/` glossary rows for every new stat (CXI law — the READ band stats have NO glossary rows yet), regional twins (CN/HK) after US proves (US is now proven live).
- **GR0.1**: contract v1.1 `members[]` per-member activity array → GR1.1 member-table column (full Jodie member-table parity). Additive, version-bumped.
- **GR3 phase-2**: commercial-relationship mix via EDGAR FTS phrase dictionary (8-K 7.01/8.01) — v1 edges are financing-heavy; counterparty alias map (Con Edison self-name miss); GOOGL/GOOG `ambiguous_tie` policy.
- **`contract_dollar_z` quality pass** — amounts now flow (0→1,793); the largest-$ heuristic can grab aggregates (KKR $195B example). Flagged, unactioned.
- **Operator's standing ask:** full production-quality + competitive audit vs Jodie/Struct/Quartr/EarningsCall.ai/EquityDesk per masterplan §7 — the build-out it was waiting on is DONE; this is the natural next session's opening move.
- Session-2 §5 flags still unactioned: HK weekly regime timeline disagreement, `_BTC_VECTOR_FROZEN` stale stamp, spvector `check()` failures in `dashboard/china/hk.html.j2`, guidance collector thinness (18 rows).

## 5. First-week watchlist for the new surfaces

- Episode ledger closure math meets real nightly cadence for the first time this week — watch `data/group_pulse/episodes.parquet` row growth and closure counts for sanity (490 closed at seed → should grow slowly, not explode).
- Sympathy ratios re-baseline as earnings season rolls — regional_banks 1.23× / mag7 0.93× were the first live reads; the floors (`MIN_REPORTED`/`MIN_COVERED`/`MIN_DRIFT_N`) should keep thin baskets null.
- Arc ladder is near-degenerate post-washout (age ~90d) — GR1 leads with participation/direction by design; arc gains contrast as the cycle ages.
