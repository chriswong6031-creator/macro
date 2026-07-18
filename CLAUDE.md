# Macro Dashboard — agent instructions

Signal-engine + static-site repo (engines in `engine/`, builders in `scripts/`, rendered site in `site/`, programs/masterplans in `research/`). Nightly pipeline runs on a self-hosted Mac Studio via GitHub Actions; render budget is law (~67 min, 4-core-bound) — heavy compute goes off the render path, artifacts to R2.

## Model routing (STANDING — token economy)

The main session may run a frontier model (Fable/Opus). **Never let fan-outs inherit it.** Workflow `agent()` calls and Agent-tool spawns inherit the session model unless you pass `model:` explicitly — under ultracode that silently burns frontier tokens on mechanical work. Route every spawn:

| Tier | Use for | Never for |
|---|---|---|
| **fable** (main loop + gated spawns/stages) | planning, adjudication, rulings, merges, final synthesis; spawns ONLY via `orchestrator` + FABLE-WHY; workflow stages ONLY with a script-level FABLE-WHY (see below) | bulk ×N mechanical fan-outs, ungated workflow stages, anything passing the draft-and-review test |
| **opus** | reviews, judge/red-team critics, stats/math review, hard debugging | bulk census, mechanical edits |
| **sonnet** | building code/PRs, census/exploration lanes, refactors, tests, doc drafts | final adjudication |
| **haiku** | trivial extraction/format sweeps | anything needing judgment |

Also set `effort: 'low'` on mechanical workflow stages; reserve high effort for verify/judge stages. Rule of thumb: **Sonnet builds, Opus reviews, Fable (main loop) plans/adjudicates/merges.**

**Fable spawn exception (gated):** a single `Agent` spawn may run fable ONLY as the triple `subagent_type: 'orchestrator'` + explicit `model: 'fable'` + a `FABLE-WHY: <orchestration|brainstorm|creative>: <specific reason>` line in the prompt (hook-enforced). Legit = fails the **draft-and-review test** — Sonnet-draft + Opus/main-loop-review would NOT recover the quality: open-ended judgment steering major downstream work, long-horizon orchestration with irreversible mid-task decisions, or taste-as-deliverable creative work. Topic importance alone does NOT qualify (important-but-mechanical → sonnet; critique of an existing artifact → opus). Never fable ×N mechanical fan-outs. **Workflow stages may route to fable (operator re-enable 2026-07-18, "fable ultracode") ONLY when the script carries the same `FABLE-WHY: <category>: <specific reason>` line** — reserve fable stages for judge/synthesis work where the draft-and-review test fails; default synthesis home remains the main loop after the workflow returns. FABLE-WHY lines are the audit trail: grep them periodically for drift.

Enforcement: a PreToolUse hook (`.claude/hooks/model_routing_guard.py`, wired in `.claude/settings.json`) denies Agent/Task spawns without an explicit model, `fable` spawns outside the orchestrator+FABLE-WHY gate, fable-pinned agent frontmatter outside that gate, and Workflow scripts whose `agent()` calls carry no `model:`/`agentType` routing (or route to fable without a script-level FABLE-WHY line). Model-pinned agent types are available: `builder` (sonnet) for build stages, `reviewer` (opus) for review stages — spawns using them pass the guard without a `model:` param; `orchestrator` (opus floor; fable only via the gate above, always with explicit `model:`).

## House laws (short list; details in research/ masterplans)

- **Git:** branch off **fresh `origin/main`** (never reuse a squash-merged branch); finish via commit → push → PR → same-day squash-merge. Stash stack is repo-global — never bare `git stash`/`pop`. Main checkout is often occupied by other agents; work in worktrees, never touch main checkout's git state.
- **Before proposing/adjudicating new work:** read `docs/ACTIVE_BUILD_MAP.md` (open-PR lanes/collisions; regen `python scripts/build_active_build_map.py`) and `research/DO_NOT_REBUILD.md` (standing kills/forbidden designs). Don't re-propose in-flight or killed topics; adjudications that kill a topic append a row to the registry (inside sections 1–4 — rows elsewhere are invisible to the compiler and hard-fail CI) AND commit the regenerated compiled blocklists in the same PR — a PostToolUse hook auto-regens them on registry edits; manual heal: `python3 scripts/check_blocklist_drift.py --fix`.
- **Epistemics (gauntlet = PROMOTION gate, NOT a build gate):** context/data/detection/tagging infrastructure ships display-tier **freely** — a null NEVER blocks building or accrual; the gauntlet applies only when promoting to authority (rank/size/gate). A factor that is null as a *standalone* signal is **retained as a confluence input** (it may confirm other signals when they align) — non-standalone ≠ worthless. A kill closes the *specific construction tested*, not the search space: "not found yet" ≠ "does not exist" — keep searching for the ranker. AT PROMOTION only: display-only until gauntleted; pre-registered gates; nulls printed, not hidden. The word "validated" in user-facing text is CI-enforced (`scripts/check_validated_claims.py`). LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations. (Memory: `context-accrual-fundamental-goal`.)
- **Design (user-first law):** read `docs/DESIGN_DOCTRINE.md` before ANY user-facing surface work. Glance tier = state + plain-word stance under hard word budgets (banned vocab: internal state/study names, untranslated stats, raw slugs); technicals demoted to hover/popover/detail pages; every signal panel answers "so what do I do", even when the honest answer is "watch — don't chase". Plain-word null disclosure + Tier-2 receipt is the compliant "nulls printed" form.
- **Ledgers:** nightly is the sole advancer of forward ledgers; intraday lanes discard `data/` writes.
- **Ops:** known-spurious CI: "Workers Builds: macro" red X is ignorable. Bilingual (EN/ZH) UI; no translated text in `title=` attributes (CI-guarded). Plain-copy page assets are PAIRED: editing `templates/<name>` (non-.j2 that also ships as `site/<name>`) requires the byte-matching site copy in the same PR — run `python -m scripts.check_template_site_sync --fix` (CI-guarded; render lanes self-heal post-rebase).

## Memory frontmatter contract

Memory files (account-local, `~/.claude/projects/<project>/memory/`) are one fact per file with frontmatter: `name` (kebab slug), `description` (one line, drives recall), `metadata.type` ∈ user | feedback | project | reference. Link related memories with `[[name]]`. Index each file as one line in `MEMORY.md`. Update/delete rather than duplicate.

## Obsidian brain vault

`Macro Dashboard/ObsidianBrain/` is a live symlink view over memory + research (Dataview MOCs). It is a *view* — edit sources (memory files, research docs), never the vault copies.

<!-- Reconstructed 2026-07-05: PR #1215 shipped this file as 0 bytes (commit message described vault pointer + memory contract; content was lost — the #1052 zero-byte failure mode). Rebuilt from the memory index + program docs, with the model-routing standing rule added. -->
