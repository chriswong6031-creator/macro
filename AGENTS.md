# Macro Dashboard — shared agent operating rules

This repository is operated by multiple Claude accounts and Codex sessions. Repository files are the durable, shared source of instructions; promises or “memory” recorded only inside one chat do not carry to another session.

## Required context at the start of every task

1. Read `CLAUDE.md` in full and follow it as the authoritative project guide.
2. Search the Claude project memory index at
   `~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/memory/MEMORY.md`
   and open the entries relevant to the task. For delivery work, always include
   `session-finish-full-git-chain`, `auto-finish-commit-push-pr`, and
   `go-live-deploy-mechanics` — read all three under §Definition of done, which
   outranks them: one session owns the whole delivery chain through the merge and
   the live check.
3. Treat `/Users/chriswong/Documents/Cluade/charting-app` as the connected Terminal
   repository. Authentication, subscriptions, data contracts, APIs, and deployment
   changes may require checking both repositories.
4. **Company strategic state lives in the Mastermind repo**
   (`/Users/chriswong/Documents/Cluade/Mastermind`), not here:
   `config/strategic_state.yml` — current phase, north star, P0 objectives, resource
   policy, standing constraints — read via
   `control_plane.strategic_state.load_strategic_state()`. The worker contract
   (hierarchy Chairman Chris → AI CEO GPT-5.6 Sol → COO Fable → workers; the
   six-layer source-of-truth order; the completion rule) is Mastermind
   `AGENTS.md` § "Executive contract". Macro fleet law below is unchanged and still
   governs sessions here. **Never create a second strategic state, control plane, or
   authority map in this repository** — `duplicate_control_planes` is a standing
   prohibition. See `research/EXECUTIVE_OS_PHASE0_CENSUS.md` (PR #5356) and
   `Mastermind/research/EXECUTIVE_OS_STRATEGIC_STATE_BOOTSTRAP.md`.
5. **The Mastermind Agent OS knowledge plane lives in this repository at `agentos/`**
   — workstreams, decisions, discoveries, and handoffs, canonical for all three
   repos. When a task belongs to an existing workstream, read its `WS-*` record and
   latest handoff before starting. See § "Agent OS knowledge plane" below and
   `agentos/README.md`.

## Navigation source-of-truth

There are exactly two global navigation families:

- Authenticated/product pages use `templates/_site_nav.html.j2`. Its inventory
  lives in `templates/_navlinks.html.j2`; shared geometry, responsive behavior,
  mega menus, ticker search and motion live in
  `templates/navigation-refresh.css`, `templates/nav_market.js`, and
  `templates/theme.js`.
- Anonymous/corporate pages use `templates/_public_nav.html.j2` with
  `templates/_public_chrome_css.html.j2` and
  `templates/_public_chrome_js.html.j2`. The hand-authored landing page mirrors
  that family in `templates/index.html`/`templates/landing.css`, guarded by
  `tests/test_public_chrome.py`.

Do not hand-copy or restyle a third header inside a page template. A page may
provide a relative `nav_prefix`, but page CSS must not change the global
header's width, typography, menu dimensions, search behavior, breakpoints or
motion. Change the appropriate shared family and its parity tests instead.

## Design system (any user-facing surface)

`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` is the binding visual/composition
law: archetype per route, canonical components (registry = the specimen at
`mockups/design_system/specimen.html`), tokens only (extend `templates/theme.css`,
never a parallel token root), density budgets, dark+light as two art directions,
EN/ZH parity. Content law stays with `docs/DESIGN_DOCTRINE.md` (wins on conflict).
Migration work follows `research/DESIGN_MIGRATION_FACTORY_V1.md`: builders execute
a committed migration packet exactly and never invent design language — a builder
that believes the packet is wrong stops and escalates.

## Workspace and git

- The canonical tree is GitHub `origin/main`
  (`mastermindx-market-intelligence/macro`), never a local folder. The only local
  project root is `/Users/chriswong/Documents/Cluade/macro-main` (operator
  2026-08-15). Never open `/Users/chriswong/Documents/Cluade/Macro Dashboard` as a
  workspace — not as a session working directory, not as an editor root.
- At session start: `git fetch origin && git merge --ff-only origin/main`. If the
  fast-forward fails, stop and tell the operator; do not rebase, reset, or force
  past it.
- `macro-main` is a linked worktree, not a second clone (verified 2026-08-15):
  `macro-main/.git` is a gitfile pointing at
  `Macro Dashboard/.git/worktrees/macro-main`, which still owns every object, ref,
  config, remote, reflog, and the worktree registry — which is why `git worktree
  list` run from `macro-main` prints `Macro Dashboard` first. Never delete, move,
  rename, or iCloud-relocate `Macro Dashboard`, and never run repo-wide destructive
  git operations from inside it: that would destroy `macro-main` and every sibling
  worktree at once. The clone is also blobless (`blob:none`, promisor), so history
  operations that need file contents fetch over the network.
- Never create project work in `~/.codex/worktrees`, `/private/tmp`, or another
  Codex-only location. Never use a `codex/` branch for these repositories.
- The primary checkout is shared and commonly dirty or detached. Do not change its
  files or git state. Fetch the remote default branch, then create a fresh worktree
  under this repository's `.claude/worktrees/<task>/` and use a `claude/<task>`
  branch.
- A merged PR does not update any folder until that folder fast-forwards. Merging
  is a GitHub-side event; every local checkout, worktree, runner workspace, and VPS
  clone keeps its old bytes until it pulls. Verify state against `origin/main`,
  never against the folder you are standing in.
- Macro branches start from fresh `origin/main`; Terminal branches start from fresh
  `origin/master`. Never reuse a squash-merged branch.
- Do not use the repo-global stash stack.
- Session worktrees are garbage-collected by `scripts/worktree_gc.py` per
  `research/WORKTREE_GC_POLICY.md` (report-first; deletion only while
  `config/worktree_gc.json` is `armed:true` — an operator ratification act). The
  sweeper honors `git worktree lock`, live process cwds, uncommitted/unpushed
  work, open PRs, and <7-day activity. To park a checkout long-term, lock it:
  `git worktree lock --reason "<why>" <path>`.
- **Session worktrees are SPARSE by default** (`research/WORKTREE_GC_POLICY.md`
  §0 R8). Claude's `.claude/hooks/worktree_create_sparse.py` mints a worktree
  off fresh `origin/main` sparsely before file checkout. Codex uses the checked-in
  `.codex/environments/environment.toml` setup plus the `.codex/hooks.json`
  `SessionStart` fallback; Cursor IDE uses `.cursor/hooks.json`
  `sessionStart` and `workspaceOpen`; Cursor CLI / Agents Window uses
  `.cursor/worktrees.json` `setup-worktree-unix`; Grok uses
  `.grok/hooks/sparse-worktree.json` `SessionStart`. Those call
  `python3 scripts/worktree_sparse.py auto`,
  which acts only on a linked worktree sitting under a session root
  (`.claude/worktrees/` and siblings — never the occupied primary, and never the
  operator's designated local root, which is itself a linked worktree), and preserves
  an existing sparse selection. Those harnesses expose setup/`SessionStart` only
  after Git creates the worktree, so they reach the same standing size but may
  incur one transient full-checkout write during creation. Project-local Codex
  and Grok hooks require one-time review/trust when their exact definition
  changes. Grok and Cursor default a new worktree to the current HEAD — pass
  `--ref origin/main` / `--worktree-base origin/main`. All of these harnesses use
  each tracked top-level directory EXCEPT the heavy
  generated ones listed in `config/sparse_worktree.json` — `data/`, `site/`,
  `mockups/`, `verify_shots/` — because those are 87 % of a 3.8 GiB checkout
  (measured 2026-08-13: data 2.3 + site 0.73 + mockups 0.23 + verify_shots 0.05
  GiB) and a typical session never reads them. A tree costs ~0.35-0.57 GiB
  instead of 3.8. This is the other half of the 2026-08-13 disk-pressure
  incident: the Studio sat at 1.7 Ti / 1.8 Ti (~100 GiB free) after two
  receipted runner ENOSPC crashes, and arming the GC (#5502) only drains
  FINISHED trees — at ~40 new worktrees/day the ~330 GiB active window is
  structurally out of the sweeper's reach, so only a thinner per-tree footprint
  shrinks it. **Opt in whenever you need those trees** — any render, `site/`,
  paired plain-copy asset, or `data/` task — with `python3
  scripts/worktree_sparse.py full` (worktree-scoped; siblings are untouched), or
  take one tree with `python3 scripts/worktree_sparse.py add site`. `python3
  scripts/worktree_sparse.py status` says what is missing. Nothing is hidden by
  this: omitted paths stay tracked, `git status` stays clean, and a write into
  an omitted path is still reported — so `ship_loop_guard.py`'s dirty snapshot
  keeps working. **A write into an omitted tree TRUNCATES the committed
  artifact**, because the real content was never on disk for the writer to
  extend: measured 2026-08-13, a test run with the `MM_DATA_GUARD` tripwire
  disabled left `data/hk_southbound/holdings.parquet` at 45,157 bytes against
  7,295,941 committed, and `data/trial_ledger.jsonl` short by 1,411 lines. Never
  `git add -A` a diff you did not expect under `data/` or `site/`; run `python3
  scripts/worktree_sparse.py clean` (report-first; `--force` deletes) to put the
  omitted trees back. Nothing is silently greened either:
  `scripts/check_template_site_sync.py` REFUSES on a sparse tree rather than
  reporting "sync OK (0 pairs checked)", and pytest prints the omitted trees and
  the opt-in command, skipping only tests explicitly marked
  `needs_full_checkout`. **Do not run the full test suite in a sparse worktree** —
  measured 2026-08-13 it produces 1,281 failures and 419 errors across 247 files
  (against 68,776 passes) purely as artifacts of the missing trees. Opt into a
  full checkout first; marking all 247 files was considered and rejected because
  it would permanently mask real regressions in a tenth of the suite. Do not detect sparseness with `Path.is_dir()` — `data/`
  survives `git reset --hard` as a 0-byte husk; ask
  `scripts/worktree_sparse.missing_dirs()`.

## Signal-state interpretation (operator 2026-08-09)

An engine state machine's terminal verdict is an INSTRUMENT verdict, never a market verdict:
a transmission chain or cycle tripwire printing "failed" means its declared windows failed,
not that the thesis is false. Report the scope ("no 22d rolldown yet", never "no peak");
relay a falsifier's prose note only as far as its receipt supports; and when a display-tier
state disagrees with the terminal asset's tape or a scored organ (Prophet, Sector
Intelligence), lead with the dual-read. Receipts and the design seed:
`research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md`.

## Adjudication coverage gate (operator 2026-08-10)

Statistical rigor (prereg, held-out eras, clustered CIs) does NOT substitute for an adversarial
pass on the CONCLUSION. Before presenting any discovered rule or promotion-bearing adjudication:
(1) **coverage** — run the rule against the live exemplars that motivated the question AND the
current regime, and lead with that answer (a rule that refuses all of them is not the answer,
however clean its CIs — the SPY-altitude miss, blocked-entry study round 1); (2) **episode
honest-N** — for state-conditioned cells report distinct EPISODES, not fires or dates, and state
whether today's tape is in-sample of the winning cell; (3) **panel integrity** — name who is
missing (survivorship/delistings/coverage floors) before trusting a cohort mean; deep-drawdown
cohorts concentrate the dead; (4) **red-team** — make-or-break calls get an opus `reviewer` pass
briefed to break the conclusion against the operator's actual use-case BEFORE the main loop
presents it. The operator often cannot audit these calls and will not be the safety net.

## Kill-registry citations (DO_NOT_REBUILD.md)

Rows in `research/DO_NOT_REBUILD.md` carry a stable `Key` column (`KILL-…` §1–2,
`LAW-…` §3, `HOLD-…` §4). Cite rows as `DNR:<KEY>` — for example
`DNR:KILL-PROPHET-POP-MERGE` — never by row or line number: numbers shift on
every append/reflow, and row-number citations have already mis-resolved in the
wild (2026-08-05). An adjudication that kills, forbids, or defers a topic
appends its row inside sections 1–4 only, mints a new unique Key, and commits
the regenerated `config/compiled_kill_registry.yml` and
`config/signal_foundry_blocklist.yml` in the same PR (manual heal:
`python3 scripts/check_blocklist_drift.py --fix`).

## Agent OS knowledge plane

`agentos/` in this repository is the canonical organizational memory shared across
sessions, models, and accounts — Claude and Codex alike: workstream records
(`agentos/workstreams/WS-<KEY>.md`), decision records (`agentos/decisions/DEC-<KEY>.md`),
discovery records (`agentos/discoveries/DSC-<KEY>.md`), and session handoffs
(`agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`). Read `agentos/README.md` before writing
any record; the machine schemas live in `agentos/schema/` and the handoff protocol in
`research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md`.

It is a knowledge plane, never a control plane. Nothing under `agentos/` decides
whether work may run: no gate, no dispatch, no scheduler, no lease with teeth. Execution
authority stays where it already lives — this repository's hook layer for
sessions, Mastermind `control_plane/` for worker processes.
A workstream `claim:` is an advisory author's note in git; never present one as evidence
that an agent is currently alive or working (`DEC:AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY`;
live occupancy evidence is `git worktree list`). Do not create a second Agent OS store,
or a local Decision/Discovery mirror, in any other repository —
`DEC:AGENTOS-HOME-IS-MACRO`; if cross-repo write friction proves real, the route is to
supersede that decision with evidence, never to mirror silently.

When to read: at task start, if the task belongs to an existing workstream, read its
`WS-*` record, its most recent handoff, and the decisions/discoveries they cite before
writing code. `do_not_redo` entries are binding unless refuted with new evidence. The
records are context, not permission — the Charter, strategic state, authority map,
`DO_NOT_REBUILD.md`, and the fleet law in this file still govern.

When to write, and only then — this layer must stay low-friction, and a one-file fix
that merges clean with nothing learned needs no records:

- a **Discovery** (`DSC-*`) when the session verified a durable, non-obvious fact that
  future sessions materially benefit from and no canonical document already records.
  Both admission gates are required — a `falsifier` (what would disprove it) and a
  `so_what` (what a future session does differently). Account-local memory is not
  company memory; cross-session facts graduate here.
- a **Decision** (`DEC-*`) when an actual choice with durable consequences was taken:
  the question, the answer, the rationale, the alternatives rejected, the evidence, and
  what would cause reconsideration. Decisions are superseded, never deleted.
- a **Handoff** when the session claimed a workstream, minted records, or leaves work in
  a state another session must resume. Contract: a competent stranger continues from the
  text alone; every `verified:` claim names the command that backs it. The natural
  moment is immediately before the session stops, in the same PR.
- a **workstream update** when durable state materially changes — status and
  `next_action` at wave boundaries, not per commit.

Hygiene: `python3 scripts/agentos.py validate` must exit 0 on any PR touching records
(schema is fail-closed; cross-store joins fail open). Cite records as `WS:<KEY>`,
`DEC:<KEY>`, `DSC:<KEY>` — the colon form, never row or line numbers. Never hand-edit
the generated views `docs/AGENT_OS_STATE.md` and `data/governance/agent_os_state.json`
— the nightly is their only regenerator — and never author `created`/`updated` fields;
the generator derives both from git history.

## Model routing

Every Agent/Task spawn and every Workflow `agent()` call must carry an explicit
model — a PreToolUse hook (`.claude/hooks/model_routing_guard.py`, wired in
`.claude/settings.json`) denies spawns that would silently inherit the session
model, `fable` spawns outside the `orchestrator` + FABLE-WHY gate, fable-pinned
agent frontmatter outside that gate, and Workflow scripts whose `agent()`
calls carry no `model:`/`agentType` routing.

Current tiers: Sonnet builds shipping code — writing code, PRs, refactors,
tests — via the `builder` agent type (model-pinned `sonnet`; spawns using it
pass the guard without a `model:` param), alongside its existing role in
census/exploration/mechanical non-code fan-out. Opus reviews (`reviewer`),
handles hard debugging, judge/red-team critics, and stats/math review, and
owns user-facing design (`designer`) — design is judgment work and is never
routed to a sonnet builder, a separate 2026-07-18 ruling that this build-lane
change does not touch. Fable (the main loop) plans, adjudicates, and merges,
and may be spawned only as the triple `subagent_type: 'orchestrator'` +
explicit `model: 'fable'` + a `FABLE-WHY: <orchestration|brainstorm|creative>:
<specific reason>` line — reserved for work that fails the draft-and-review
test, never bulk ×N mechanical fan-outs. Haiku handles trivial
extraction/format sweeps.

The build-lane tier was reversed 2026-08-17 (operator instruction) from the
2026-07-21 "no more sonnet building code" order, and the `builder` agent type
is re-pinned `sonnet` accordingly. The autonomous metabolism build loop
(`scripts/metabolism_build.py`, R-V4-2) is a separate system and stays
Opus-pinned unless amended on its own terms. See Macro `CLAUDE.md` §Model
routing for the full tier table, and
`agentos/decisions/DEC-SONNET-BUILDS-AGAIN.md` (supersedes
`DEC-OPUS-BUILDS-SONNET-EXPLORES-FABLE-GATED`) for the decision record.

**Direct-spawn routing (hook-enforced amendment, 2026-08-17 — semantic ROUTE contract):** every direct Agent/Task spawn declares a semantic `ROUTE: <class>` line; `.claude/agent-routing.json` (execution-policy registry, NOT a strategic control plane) maps each route to its ONE canonical custom agent and model — `extract`→`extractor`(haiku), `census`→`scout`(sonnet), `research`→`researcher`(sonnet), `draft`→`drafter`(sonnet), `analysis`→`analyst`(opus), `debug`→`debugger`(opus), `build`→`builder`(sonnet), `review`→`reviewer`(opus), `design`→`designer`(opus), `judgment`→main loop ONLY (never spawned), `orchestration`→`orchestrator`. The orchestrator seat runs either explicit `model: 'fable'` + FABLE-WHY (unchanged gate, work failing the draft-and-review test) or — for easier orchestration that does not need frontier judgment — explicit `model: 'opus'` with a prompt directive to load the `fable-mode` skill (`.claude/skills/fable-mode`), at roughly half Fable's price and with no FABLE-WHY because no fable is spent; the same skill lets an Opus MAIN session hold the orchestrator role. `model_routing_guard.py` denies missing/unknown routes, route↔agent/model mismatches, under-specified commissions (each route's required `SECTION:` labels live in the registry), and bypass via `general-purpose`/`Explore`/`Plan`/`fork`; a `SubagentStop` hook (`.claude/hooks/agent_return_guard.py`) blocks a routed worker ONCE if its final message misses the STATUS/RESULT/EVIDENCE/GAPS/DEVIATIONS packet, then lets the second stop through (no loops). Treat a guard rejection as feedback — fix the route or commission, never evade the registry to obtain a different model. Frontmatter pins are the runtime truth; `tests/test_agent_routing_control.py` keeps registry↔frontmatter from drifting.


## Context economy (frontier burn is CONTEXT × TURNS)

Measured 2026-08-06 across 3,043 local transcripts (week of 07-30→08-06): of all
Fable burn, **62% was cache reads, 21% cache writes, only 17% output**. Cache
reads are the discount (0.1× fresh input), not the waste — never try to avoid
caching. The cost driver is `context size × turn count`, and the per-turn floor
is `0.1 × context`: ~15k units/turn at 150k context, ~80k at 800k.

The worst measured session ran 3,539 turns at a median 419k context (max 879k)
over 43h and 16 branches, costing 11.6% of the week's Fable burn on its own
(Fable was 26% of all model burn that week; Opus 62%). Its turns at ≥400k context were 52% of turns but 67% of its burn. Riding
context up to auto-compaction is the most expensive possible pattern: compaction
fires near the ceiling, so every turn on the approach bills at the ceiling rate.
There is no configurable compaction threshold and a session cannot compact
itself on demand.

- **Delegate execution; the orchestrator adjudicates.** 76% of Fable's
  main-loop tool calls that week were `Bash`/`Edit`/`Read`/`Write`, and
  delegation was 2.6%. A subagent's context is discarded on return — only its report lands — so
  delegating keeps tool output out of the orchestrator permanently.
- **Budget what enters context.** A tool result of size S landing at turn N is
  re-read on every remaining turn. Prefer targeted `grep`/line-ranged reads over
  whole files, cap command output (`head`, `--limit`, `--jq`), and keep browser
  screenshots and full page dumps inside a subagent.
- **One session = one task boundary.** A long program needs durable state on
  disk, not a long session. Run it as a chain of short sessions over a
  `research/*_CONTINUATION_HANDOFF_<date>.md`, one wave per session. Keep an
  orchestrator under ~200k; past ~250k, checkpoint to a handoff and let the
  operator clear rather than grinding to the ceiling.

Do NOT save tokens by reducing reasoning effort — output is only 17% of burn, so
cutting thinking degrades quality for at most a sixth of the cost. The savings
are in where work happens and how large the context is.

## Definition of done

DONE for a substantive, verified change is the full delivery chain, which is
never abandoned partway and never handed back to the operator to finish:

1. commit;
2. push;
3. open a pull request;
4. check CI and resolve genuine failures;
5. same-day squash-merge and delete the remote branch;
6. deploy or wait for the repository's normal deploy lane, then verify the change
   on the real live URL.

**One session owns all six.** There is no earlier "worker done" state — the rule
that let a session terminate on an armed pull request was REMOVED by the project
owner on 2026-08-12 ("ur the owner of this project so u keep it until its
finished, no need for handoff"). It had turned an unfinished job into a
reported-complete one: a session declared itself done while its pull request sat
`merge-blocked` on a red check, and the owner had to reopen the work by hand.
Stopping at a local commit, at an open pull request, or at an armed-but-unmerged
one is abandoned work, not delivered work.

`merge-on-green` remains available and is still the recommended way to get the
merge PERFORMED — arming it means you do not have to run the merge yourself. It
is not a reason to stop: keep the session alive until the pull request is merged
and the change is verified live. The only holds are an explicit operator request
to hold, a genuine non-spurious failing check, or a real deployment blocker.
For Macro, the `Workers Builds: macro` red X is known-spurious. Template/source
changes must include their paired `site/` artifact when required, and “merged” is
not “live” until the VPS/render path and live marker are verified.

**Healing a red pack: claim the lane FIRST, and heal the WHOLE pack (2026-08-07,
#4850 closed unmerged).** A fleet-wide red is being worked by the whole fleet, so
before writing a line: identify every red job **by name** and confirm its pack
(`python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml
--pack-index N --pack-count 12 --validate-only`) — never trust the pack index in a
failure report, `run_ci_pack.py` rebalances whenever any job's weight moves — then
check `gh pr list --search "<filename>"` and `docs/ACTIVE_BUILD_MAP.md` for an open
lane on the files you are about to touch. The "before proposing new work" rule is
scoped to NEW work and does not cover heals, which is exactly how this was missed.

**A pack is ONE check, so two partial heals DEADLOCK.** With two independent reds
in `ci-pack-3`, the ITR-only PR stayed red from the stale report and the
report-only PR stayed red from ITR: neither could ever go green, so neither could
merge. One PR must carry every fix the pack needs. Cherry-pick a sibling with `-x`
(authorship preserved) rather than rewriting it, and read its diff first — the
sibling's version is often the better one.

Sessions SHOULD heal. The “don’t propose in-flight work” line is for new
features; heals are the exception (this bullet exists because #4850 was missed
that way). One PR per pack stays — different packs still get separate heal PRs.

**Missing hole (2026-08-14, #5715/#5717 deadlock then #5689 absorbed both):**
if TWO (or more) packs are red on main AND required `ci-gate` needs every pack
green AND `gh pr merge --admin` is refused by the repository ruleset, two
whole-pack PRs still cannot land. Then ONE PR labelled `main-red-repair` must
carry every pack heal that `ci-gate` is blocking. Do not wait. Do not open a
second `main-red-repair`. That is not a repeal of one-PR-per-pack; it is the
mutual-block exception.

**Re-fetch `origin/main` and re-run the job line before pushing OR merging.** On a
red main the tree moves in hours (five heal PRs landed mid-session here), and a
`merge-blocked` "real content conflict" on a heal PR usually means the heal already
landed rather than that you must resolve anything. Diff against fresh main
(`git diff --stat origin/main HEAD -- <files>`; empty = already there) and **close
rather than force through** — a superseded regeneration silently reverts the better
fix that landed behind you (#4850's live-cache report would have reverted #4842's
frozen-slice render).

**Merge on CONCLUDED checks, never mid-flight (operator 2026-07-28).** A pending
check is not a pass: an `--admin` squash-merge while the PR's packs are still
running used to fire a `pull_request: closed` event into the live concurrency
group and cancel the PR's own proof run — the merged head then carried
`cancelled` packs forever (PR #3867), unproven merges stacked up red on main, and
every ship-loop session pinned on the next full-CI dispatch (measured 2026-07-28:
100 ci.yml runs in 8h, 6 successes). ci.yml now fences merged-close events into
their own concurrency group so a fast merge no longer destroys its own evidence,
but the discipline stands: wait for the packs to conclude (green, or spurious-only
red) before squash-merging. Do NOT arm `gh pr merge --auto --squash` as the wait:
main carries no branch protection, so auto-merge has no required checks to gate on
and merges IMMEDIATELY (verified PR #3889, 2026-07-28 — merged ~1 min after arming
with packs still pending). That "no protection" is the NORMAL state, not a law of
nature: a repository ruleset can appear at any time and reject even the nightly's
bot pushes with GH013 — `ci-recovery-bootstrap-freeze-2026-08-15` did exactly
that 08-15→08-17 (bypass = org admin only, minted with no DEC record), froze
every Prophet board for three days, and no instrument saw it because the engine
kept BUILDING green and only the push died. When pushes to main mysteriously
fail, `gh api repos/{owner}/{repo}/rulesets` is the FIRST diagnostic, and any
deliberate freeze must ship a DEC record plus an expiry plan
(research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md).

**ARM `merge-on-green`, THEN STAY.** After opening the pull request, run
`gh pr edit <n> --add-label merge-on-green`.
`.github/workflows/merge-on-green.yml` (GitHub-hosted `ubuntu-latest`, every 10 minutes,
deliberately off every self-hosted render pool) squash-merges the
pull request once every check has CONCLUDED clean, with the known-spurious
`Workers Builds: macro` X excluded. A genuine red or a merge conflict gets the
`merge-blocked` label plus ONE explanatory comment instead of a merge; the
`merge-on-green` label stays armed, so a rerun that greens the head merges on the
next sweep.

Arming it is a BACKSTOP that saves you the merge command — it is not an exit. The
sweeper cannot fix a red, cannot resolve a conflict, and cannot verify the change
live; those are yours, and you will not learn they are needed if you have already
stopped. `ship_loop_guard.py` blocks a session whose pull request is armed but not
merged, and NAMES the reds the sweeper would refuse, so the answer to "am I done"
is always "is it merged". Merging by hand on concluded-green stays fully valid and
is often faster than waiting a sweep. After any accidental fast merge, the
surviving PR proof run is the merge's evidence — watch it to conclusion. `--admin`
remains only for the spurious Workers X, docs-only pull requests that trigger no
pack checks, and genuine wedges — never to outrun CI.

**DISARMING IS NEVER SILENT (PR #5291, 2026-08-11).** The sweeper never removes
`merge-on-green`; `scripts/merge_on_green.py` has no code path that does. Every
removal is a session's deliberate act, so treat it as one: taking a pull request
manual — your own or a sibling's — requires, IN THE SAME ACT, a visible marker
(`merge-blocked`, or a PR comment naming your session and what you intend) and
ownership of that pull request through to merged-or-handed-back. A bare
`gh pr edit <n> --remove-label merge-on-green` with no marker is not a hand-off, it
is a disappearance: the sweeper only ever lists LABELED pull requests, so a disarmed
PR leaves its world entirely and no later sweep can label, comment on, or merge it.
PR #5291 was stripped twice in one evening (02:13:34Z, 02:21:36Z) with no marker
either time, sat red and unattributed, and needed a manual `--admin` merge at
02:32:52Z to escape. The sweeper now marks a fresh red within seconds of the failed
run (failure wake-ups run a bounded mark-only pass), but that only shrinks the
window — it cannot make a silent disarm visible.

**A `merge-blocked` backlog means main is UNPROVEN, not that the pull requests are
bad (#5037, 2026-08-08).** The sweeper's base-inherited-red refresh — the mechanism
that drains an armed backlog once main is healed — can only tell an inherited red
from a real one against a RECENT proof of main. `ci.yml` has no `push` trigger, so
main is proven ONLY by a `workflow_dispatch`, while the nightly/wire lanes push ~24
`[skip ci]` commits per 2 hours — so any commit-window heuristic ages out in ~100
minutes. Measured 2026-08-08: main's newest proof sat **117 commits / 12 HOURS**
back, the refresh resolved zero pack names, and 61 pull requests sat armed with 60
of them red on `ci-pack-2`/`ci-pack-3` that main's own last run had proven green.
Three properties now hold and must not be regressed: the proof is resolved from the
newest completed `ci.yml`/`fences.yml` **RUN on main** (velocity-independent, and
cheaper than the walk it replaced); a refresh additionally requires that proof to
**POSTDATE** the pull request's failing checks (correctness — a green that predates
your red does not excuse it — and the loop guard, because `update-branch`'s
422-on-current-head does NOT prevent loops when main moves every few minutes); and
the sweeper **dispatches its own main baseline** when its proof is too stale to
answer the reds it just saw. **Diagnose a fresh backlog from the sweep log first:** a
summary reading `0 main commit(s) classified`, or a proof set carrying no
`ci-pack-*`, means the refresh path is closed no matter how green main is. Operator
lever unchanged: `gh workflow run ci.yml --ref main`.

**But NEVER dispatch over a live baseline (livelock, measured 2026-08-09).**
Main-ref ci.yml dispatches share ONE concurrency group with
`cancel-in-progress: true`, so every re-dispatch KILLS the in-flight proof: the
11:00Z baseline died 44 min in — likely minutes from concluding — to a sibling
session's re-dispatch, whose own run died 4 min later to the next session's. With
several pinned sessions each firing the lever, no proof ever concludes, the
sweeper keeps reading `0 main commit(s) classified`, and the entire fleet stays
pinned — the escape hatch IS the lock. (fences.yml's main-push runs were dying
the same way under main's ~1/min push cadence, closing the other proof source;
structural fix = event-conditional cancel-in-progress, in flight 2026-08-09.)
Preflight before the lever:
`gh run list --workflow ci.yml --branch main --json databaseId,status,createdAt --jq '[.[]|select(.status!="completed")]'`
— anything `queued`/`in_progress` → WATCH it (`gh run watch <id> --interval 60`)
instead of dispatching. Dispatch only over a clear field, or over a run stuck
`queued` >40 min with the pool otherwise moving (orphaned-run escape — your
dispatch is then the mercy kill, not a murder).

### Waiting on CI without jamming every other session

Every session now waits out its own merge, so this is the ONLY thing restraining
fleet-wide polling. Treat it as a hard rule, not as advice.

`gh` authenticates as ONE account token, so GitHub REST's 5,000/hr `core` pool is a
single bucket shared by every parallel session, the babysitter lane, and the hooks.
Exhausting it 403s all of them for up to an hour — including `ship_loop_guard.py`,
which spends up to four REST calls per Stop evaluation and **fails closed** when
rate-limited, so over-polling blocks the very Stop the polling was meant to reach.
A ci.yml run here takes 30–34 minutes. Pace the wait to THAT, not to impatience:
one status read per minute is already generous, and a run that has been going four
minutes cannot be finished.

`.claude/hooks/gh_quota_guard.py` (PreToolUse on Bash) denies the shapes that
emptied the pool on 2026-07-26 and 2026-08-09:

- `gh run watch` at its **default `--interval 3`** — nothing on the command line
  says "3 seconds", which is exactly why it passed review. Use `--interval 60`+.
- a `gh` call inside a loop sleeping under 90s (two watchers on one endpoint at 45s
  went 4,488 → 0 in under an hour);
- `--paginate` over check-runs/jobs — ~130 checks per PR, where one page already
  answers "is it still running";
- re-dispatching a main proof workflow (`ci.yml` / `fences.yml` /
  `integration-baseline.yml`) over one already in flight on main.

The guard governs HOW you watch, never WHETHER you may: reading your own pull
request's check state is part of owning it through to the merge, and no state
outside the command line makes that read illegal. What is on you: preflight
`gh api rate_limit --jq '.resources.core.remaining'` before arming any long watch,
run exactly ONE watcher per endpoint (a second watcher on the same run buys no
information and doubles the burn), and never read an empty or 403 response as a
settled/green result. REST and GraphQL are separate 5,000/hr pools, so `gh pr view`
continuing to work does not mean `gh api` will.

When an operating standard changes, update the repository's `AGENTS.md` and
`CLAUDE.md` together so both Codex and every Claude account inherit it.

### GitHub annotations must start the line (CI-guarded)

Emit `::warning` / `::error` / `::notice` with a bare
`print("::warning title=<slug>::<msg>", flush=True)` — never through a logger.
GitHub only parses a workflow command when `::` is the first thing on the line,
and every builder here logs with a prefixing format, so
`log.warning("::warning ...")` emits `WARNING ::warning ...` and the annotation
is silently dropped. The call reviews as an alarm, runs without error, and
produces nothing in the Actions summary — the worst failure mode for a
fail-soft, which ships degraded output with its only signal gone.

This shipped dead five separate times (#3487, #3515, #3562, #3563, #3570) before
#3587 swept 69 sites across 21 modules and added the guard at
`tests/test_gh_annotation_line_start.py`. Notes:

- `flush=True` is load-bearing: stdout is block-buffered when piped in CI, and
  these sit on paths that may precede a crash.
- Modules that never execute inside an Actions step (FastAPI request paths —
  `brain_gateway`, `download_quota`, `view_ratelimit`) are EXEMPT and listed in
  that test; check `app/` / `admin/` imports before converting an `engine/`
  module, because adding a `print` to a request path is wrong.
- Converting breaks any test that asserts the annotation via `caplog`. Switch it
  to `capsys` AND assert `line.startswith("::")`, so the test pins the property
  that was actually broken rather than the message wording.
- To prove an annotation is live, use GitHub's annotations API — it returns only
  lines it actually parsed:
  `gh api "repos/<o>/<r>/actions/runs/<id>/jobs" --jq '.jobs[].id'` then
  `gh api "repos/<o>/<r>/check-runs/<job_id>/annotations"`.

### Shared render-lane safety

`render.yml` is one shared, coalescing deploy lane. A successful push render at
a merge SHA or any later main descendant covers the earlier merge because the
workflow unions every dirty scope since its last covering watermark. Monitor
that shared covering run; do not demand a dedicated successful run for every
merge SHA.

A **paired plain-copy asset PR needs no render at all.** A non-`.j2` file under
`templates/` that also ships as `site/<name>` — the pairs
`scripts/check_template_site_sync.py` enumerates (a growing set; read the count
from the script): `theme.js`, `mm_brain.js`,
`onboard.js`, `index.html`, the `*.css` — has its `site/` copy committed straight
to main, and the VPS `macro-update` cron pulls main every 3 minutes, so it is live
within minutes whether render ever completes or not. render.yml produces only two
things: re-baked `.j2` pages and the `?v=` content-hash re-stamp. Do not wait on a
perpetually superseded render for such a PR, and do not report it as a blocker.
The one thing you forfeit is that re-stamp: the Caddyfile pins `?v=`-carrying
requests to `immutable, max-age=1y` for an enumerated list (`theme.js`, `live.js`,
`theme.css`, `product-nav-icons.css`, `onboard.*`, `landing.css`, `account.js`,
`nav_market.js`, `supabase.js`, `data_base.js`, `chat*.css`,
`assets/{css,landing}/*`), so for those a warm-cache visitor keeps the old body
until a later render re-hashes the pages that reference them. New visitors always
get fresh bytes. `.j2` pages, `scripts/build_*.py`, and the page-rewriting sweeps
(`optimize_assets.py`, `externalize_css.py`, `inject_data_base.py`, `lib/pages.py`)
still require the render before they are live.

Never cancel or manually re-run an in-progress `render`, `engine-render`, or
`daily` solely to unblock a session. A long job inside its declared timeout is
not wedged evidence. Re-run only after the job has concluded unsuccessfully,
the cause has been identified or corrected, and one session owns the recovery.
Parallel sessions must reuse that recovery instead of launching retries of
their own.

**Hook-enforced as of 2026-08-13.** `.claude/hooks/gh_quota_guard.py` shape 6
denies `gh run cancel`, `POST …/actions/runs/<id>/cancel` and `…/force-cancel`
when the run belongs to `daily.yml`, `closing-bell.yml`, `asia-close.yml`,
`render.yml`, `engine-render.yml` or `weekly.yml`; it fails OPEN when the run
cannot be resolved. The paragraph above already said all of this on 2026-08-12
and did not bind: a live fleet session force-cancelled the US nightly's recovery
dispatches six times (receipt: `POST /actions/runs/31583415065/force-cancel`),
and stacked on the #5362 workflow-size strand the night before it served Prophet
US's 2026-08-10 picks for two full sessions before the operator noticed by
looking at the site. **A cancel is invisible to every staleness instrument in
this repo** — a killed bake and a bake that never fired leave the same trace,
which is nothing. The hook binds Claude-fleet sessions; sessions on other agent
accounts are bound by this paragraph alone, so treat killing a production run as
an OPERATOR call and hand it over rather than taking it.

**Recovery etiquette (2026-08-14).** `scripts/prophet_rescue.py`
(`.github/workflows/prophet-rescue.yml`, hourly at :40 from 23:40Z to 13:40Z) is
now the ONLY auto-redispatcher of `daily.yml`, bounded to two attempts per night
counted across all actors. A session that believes the nightly needs a manual
dispatch must first read the open `prophet-outage` issue — the rescue lane's
receipts live there, including attempts whose POST created no run — and must
never dispatch while a `daily.yml` run is queued or in progress. The two watchdog
lanes, `prophet-rescue.yml` and `nightly-liveness.yml`, are themselves in the
hook's protected set: killing a watchdog is worse than killing a bake, because it
removes the only thing that would have noticed.

The contract is actively enforced for Claude by the tracked `SessionStart` and
`Stop` hook in `.claude/hooks/ship_loop_guard.py`. It snapshots pre-existing dirty
files, then refuses a normal stop while session-created work is uncommitted,
unpushed, unmerged, awaiting a render, or absent from production. `unmerged` is
satisfied by an actually-MERGED pull request and by nothing else: an armed
`merge-on-green` pull request blocks like any other unmerged one, and the block
names the reds the sweeper would refuse so the session is told what to fix rather
than merely that it may not leave. A red that is genuinely this head's files
`ci_failed_unmerged`, which is deliberately an INTERNAL code (10 consecutive / 15
total, not the external 2/3): the state this rule exists to prevent — alive
session, armed pull request, red the sweeper will never merge, head still
pushable — must not also be the cheapest state in the guard to leave.
The dirty snapshot judges only this checkout's own work. Untracked entries under
another fleet's worktree roots (`.claude/worktrees/`, `.claire/worktrees/`,
`.codex/worktrees/`, `.codex-worktrees/`) are excluded — a blocked session can neither commit another
session's checkout nor delete it without destroying live work — and a path that
LEAVES `git status`, whether committed or newly ignored, stops counting as
outstanding. Both stay fail-closed: tracked content under those roots gates
normally, and a tracked file the session deleted is still reported by git as
` D`, so it still blocks.
Codex must follow the same chain directly from this file. A genuine repeated
external blocker must be reported as `SHIP LOOP BLOCKED:` with concrete evidence;
ordinary local cleanup, authentication setup, and waiting are not blockers.
The CI gate is base-side-aware: a red on the merged head that provably pre-existed
on main (same check failing on ≥2 independent concurrent PR heads pre-merge, or a
green ci.yml run on a main descendant) is excluded by name rather than pinning the
session forever; the operator lever for a healed base is
`gh workflow run ci.yml --ref main` — one green dispatched run clears every pinned
merge at once, but preflight for an in-flight baseline first (see the livelock
note above: a re-dispatch cancels the very proof every pinned session is waiting
on). Unknown or lone-sibling evidence stays `ci_failed` (fail-closed).

The PRE-merge path is base-side-aware too, and has to be: now that every session
stays through its own merge, that path runs on EVERY Stop of EVERY armed session,
which is exactly the population that inherits a red main. Before an armed head's
red is called this session's defect, the guard asks whether main's own newest
concluded `ci.yml`/`fences.yml` run is red on the same job NAME, and failing that
whether the same name is red on ≥2 independent concurrent sibling heads. If either
answers, the block is filed as `unmerged` naming MAIN as the cause and
`gh workflow run ci.yml --ref main` (with the in-flight preflight) as the lever —
never "fix the cause and re-run", which is how several sessions end up healing one
pack in parallel, and two partial heals of one pack can never both go green.
Fail-closed in the safe direction throughout: a stale proof, a lone sibling, an
undated red, or any probe that raises excuses nothing and the red stays this
session's, with the gap NAMED in the block. Nothing here releases anybody — both
outcomes still block, only the advice changes.

An IN-FLIGHT covering render DEFERS rather than blocks (operator ruling
2026-07-27): a queued or running render whose head covers this merge satisfies the
render gate and the session proceeds to the live check, because the VPS pulls main
every 3 minutes so the merge is live regardless, the shared lane owns the re-bake,
house law forbids a waiting session from cancelling or re-running it, and the
nightly `scope=all` re-render is the backstop. A render lane that NEVER started
(the dead-wire trap) or that concluded FAILED with no in-flight successor still
blocks. Every blocker also carries an escape ladder so an unsatisfiable gate can no
longer trap a session indefinitely: an EXTERNAL blocker escapes at 2 consecutive OR
3 cumulative external blocks; ANY code (including the internal ones —
unmerged/ci_failed_unmerged/unpushed/uncommitted/unsafe_branch/guard_error)
escapes at 10 consecutive OR 15 total blocks. Every escape still requires an explicit `SHIP LOOP BLOCKED:`
evidence report with `stop_hook_active` set, so a session cannot bail on the first
attempt.
