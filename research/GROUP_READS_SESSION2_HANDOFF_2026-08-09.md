# Group Reads — session-2 handoff (2026-08-09)

**From:** the Fable orchestrator session that ratified and built the Group Reads program (2026-08-08 → 09).
**Program:** match and exceed Jodie.ai's theme/basket engine and integrate it with the earnings intelligence data plane (operator directive 2026-08-08). Masterplan: `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` (merged, #4991) — §0 acceptance gates bind every wave; §4 contracts are FROZEN. Memory pointer: `group-reads-basket-participation-program` (+ traps: `edgar-index-type-field-is-the-icon-name`, `weekly-artifact-refresh-reds-three-suites-untested`, `hermetic-fixture-with-hardcoded-dates-is-a-time-bomb`).

## 0. Verified board at handoff time (~05:30Z 08-09 — RE-VERIFY FIRST, the fleet moves fast)

| PR | Wave | State at handoff |
|---|---|---|
| #4991 | Masterplan | **MERGED** |
| #5008 | GR3 linked-outsiders plane | **MERGED** (ships inert until #5020's data lands; runtime falls back gracefully without group_pulse) |
| #5065 | (other session) earnings-seasons date bombs | **MERGED** |
| #4995 | GR0 pulse plane + episode ledger | **OPEN, armed** — the keystone: #4996/#5011 consume its artifacts; merged-#5008's `from engine import group_pulse` resolves only when this lands |
| #4996 | GR2 earnings pulse + sympathy | OPEN, armed |
| #5011 | GR1 READ surfaces | OPEN, armed, **orchestrator-reviewed** (crops verified; review comment on the PR) |
| #5020 | GR3b counterparty unlock (0→1,916 names) | OPEN, armed |
| #5033 | my five-family fleet-heal omnibus | **CLOSED unmerged** — fleet healed via other sessions' PRs while this session was dark |
| #5034 | (other session) partial heal | OPEN — likely now redundant; its govrev rewrite was adopted into #5033 (now closed); check before touching |

Main tip at handoff: `48d13f4347e` (#5124 — packs moved to the hosted pool; runner starvation may be over).

## 1. What this session shipped (all orchestrator-reviewed)

- **Teardown + verdict**: Jodie decomposed (participation / agreement / flow / outside-confirmation / episodes / heat). Our measurement layer already exceeded them; product gaps were assembly + episodes + outside confirmation + earnings. Two moats Jodie lacks: **arc state** and **earnings integration**.
- **GR0** (#4995): `engine/group_pulse.py` — activity+trend participation, sign-agreement (landed in `group_flow`), arc ladder off `coiled.washout_ctx_detail()` (pure extraction, pinned), append-only episode ledger + `site/basketdata/{pulse,episodes}.json`. 124 tests. 26s runtime. Arc is near-degenerate after a broad washout+bounce (age 90d) — GR1 correctly leads with participation/direction.
- **GR2** (#4996): `engine/group_earnings.py` — season clock, beat rollup with floors, `guidance_gap` imported-not-forked, revisions, drift, **sympathy ratio** (first live read: regional_banks 1.23× baseline n=102; mag7 0.93× — the operator's "do earnings move together" question, answered with floors).
- **GR1** (#5011): READ band on `basket_detail.html.j2` (stance line, four tiles, arc rail signature, "what we're watching", episode history, earnings section), board chips on `sector_central.html.j2` `#btable` (the REAL US board — `baskets.html` is a stub), native zh, 红涨绿跌 via var() routing, non-directional `--gr` token, `gpr-` namespace (`.gr-*` is govrev's). 4,200-combination stance-matrix sweep.
- **GR3** (#5008, merged): `engine/group_linked_outsiders.py` + edge ledger + masterplan §4.4. Honest relationship subtypes (never Customer/Supplier labels). Strict unique near-verbatim resolver. Proven end-to-end with a loaded run (1,169 edges, 48/49 baskets) — inert on real data until #5020.
- **GR3b** (#5020): `collectors/edgar_8k.py` was parsing the EDGAR submission-header page for months (`index.json` `type` = the ICON name), unstripped, with names gated behind dollars — three stacked defects. Fixed + exhibit fetch + backfill: **0 → 1,916 counterparties** (financing-heavy, as Item 1.01/2.03 is), amounts 0 → 1,793 (activates the dormant `contract_dollar_z` panel — quality unassessed, flagged). Nightly cost unchanged (~3 filings/night).
- **Fleet forensics** (mostly superseded by other sessions' merges, but the analysis holds): weekly deep-dive `901282ec209` single-handedly redded spvector (null-tail timeline), factor-exposure (ETHA rank knife-edge), signal-lab (frozen-stamp divergence × REGISTRY mutation); plus fixture date bombs (#5065) and govrev truth-pins detonated by our own Wave 9C activation. Five sessions built overlapping heals that cross-blocked (#5023/#5031/#5033/#5034/#5065).

## 2. RESUME SEQUENCE (in order)

1. **Re-verify the board** (states above age in minutes): `gh pr view` each of #4995/#4996/#5011/#5020. Check main health: latest `ci.yml` run on main; if none since tip, a sibling PR's packs probe it for free.
2. **Land #4995 first.** If its checks are stale-red, rerun the failed packs (`gh run rerun <id> --failed`) — its remaining reds were base-side families that other sessions' merges likely healed. The sweeper merges on concluded green (label armed). Its old run id: 31269873216.
3. **Then #4996, #5011, #5020** — same rerun-if-stale-red treatment. Expect trivial tail conflicts in `scripts/build_baskets.py` + `.github/ci/legacy-jobs.yml` against merged-#5008: resolve by keeping ALL hooks in order **flow → pulse → earnings → linked_outsiders** and ALL CI jobs (worktrees below; `rerere` OFF in each — a sibling's replayed resolution is a recorded trap).
4. **Signal-lab root cause may still be unlanded.** #5033 closed unmerged; if the fleet healed signal-lab via a re-stamp only, the REGISTRY-mutation bug (build_scorecard mutates module state; `engine/signal_lab.py:1871` era) will re-fire at the next weekly artifact refresh. Check current main: does `build_scorecard()` resolve over a copy? If not, re-ship the fix — it sits ready as commit `d33af7d8bdf` (+ regression test) on branch `claude/main-heal-spvector-factor` (worktree `main-verify-0808`). Small PR, big future save.
5. **Live verification after the first post-merge nightly** (ship-loop law: not done until live): `site/basketdata/{pulse,episodes,earnings_pulse,linked_outsiders}.json` present on the live site; basket detail pages render the READ band (light+dark+zh); board chips on sector_central; ledgers under `data/group_pulse/` advancing nightly-only.
6. **Tidy**: comment/close #5034 if redundant post-verification; delete merged-work worktrees ONLY per WORKTREE_GC_POLICY (report-first).

## 3. Then the program continues

- **GR4**: fold basket state-change events into Turn Desk artifacts (DNR:KILL-ROTATION-SCHEDULE — no parallel surface), `docs/site_semantics/` glossary rows for every new stat (CXI law), regional twins (CN/HK) after US proves live.
- **GR0.1**: contract v1.1 `members[]` per-member activity array → GR1.1 member-table column (full Jodie member-table parity). Small, additive, version-bumped.
- **GR3 phase-2**: commercial-relationship mix via EDGAR FTS phrase dictionary (8-K 7.01/8.01, collaboration/supply announcements) — v1 edges are financing-heavy. Also: counterparty alias map (Con Edison self-name miss), GOOGL/GOOG dual-class `ambiguous_tie` policy.
- **Operator's standing ask**: after build-out, the full production-quality + competitive audit vs Jodie/Struct/Quartr/EarningsCall.ai/EquityDesk (masterplan §7 rubric). The teardown facts are in the masterplan §1 and the program memory.

## 4. Worktree inventory (do NOT delete armed-PR homes)

| Worktree (`.claude/worktrees/`) | Branch | Holds |
|---|---|---|
| `gr0-group-pulse` | claude/gr0-group-pulse | #4995 |
| `gr2-group-earnings` | claude/gr2-group-earnings | #4996 |
| `gr1-basket-read` | claude/gr1-basket-read | #5011 |
| `gr3-linked-outsiders` | claude/gr3-linked-outsiders | #5008 MERGED (removable after live-verify) |
| `gr3b-counterparty-unlock` | claude/gr3b-counterparty-unlock | #5020 |
| `main-verify-0808` | claude/main-heal-spvector-factor | closed #5033's commits — the signal-lab fix to salvage (step 4) |
| `gr-heal2-signal-lab` | claude/group-reads-handoff | this handoff |
| `group-reads-masterplan` | merged #4991 | removable |

## 5. Flagged, unactioned (candidates for chips/waves)

- Weekly lane publishes an HK regime timeline that DISAGREES with the parquet it commits (data-correctness bug, raised as a chip by the heal builder).
- `_BTC_VECTOR_FROZEN` is a stale stamp vs a weekly-moving artifact (re-stamp = promotion-stat decision, operator-adjacent).
- `contract_dollar_z` largest-$ heuristic can grab aggregates (KKR $195B example) — quality pass needed now that amounts exist.
- `tests/test_spvector_page.py` carries 4 pre-existing `check()` failures pytest cannot see (stale template markers in `dashboard/china/hk.html.j2`).
- Guidance rollup near-dark repo-wide: `data/edgar/guidance_hits.parquet` has 18 rows — upstream collector thinness; honest nulls everywhere until a collector wave feeds it.

## 6. Laws that bit this session (obey them)

GitHub quota is ONE shared bucket (≥90s poll floors, one watcher per endpoint, preflight `rate_limit`). A push can schedule ZERO Actions runs — compare run `headSha` to your head; the cure ladder is empty-commit nudge → fresh branch. Pack jobs share ONE workspace (earlier jobs pollute later ones). `--limit` listings fake merges — check PRs by number. Never bare `git stash` (repo-global stack). Worktree `add` outlives the 2-min timeout — background it and verify the `.git` file + `worktree list` row before spawning into it. Census any tree against `origin/main` before believing "X doesn't exist."
