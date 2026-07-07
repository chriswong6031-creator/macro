# Active Build Ownership — Fable adjudication of the Codex collision-map handoff

Adjudicated: 2026-07-07 by Fable (main loop). Census: 1 Sonnet lane (ownership/CI infra),
1 Haiku lane (verdict-marker sweep, 492 research docs), live `gh` PR state.
Intake: `~/.codex/.../research/fable_exit/04_ACTIVE_BUILD_COLLISION_AND_OWNERSHIP_MAP_HANDOFF.md`
(Codex, 2026-07-07, freeze-spec only).

## Problem statement (accepted)

Codex is right about the gap: `config/synapse.yml` owns artifacts, `config/dag.yml` owns
workflow lanes, GitHub owns branches — nothing answers the *temporal* multi-agent question
("which open PR owns this surface; what should a new session stop recommending?"). Every
external-intake adjudication to date rebuilt that collision map from scratch, inline, in
prose (`NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` line 6 is the exemplar), and each
docket ran 55–80% dup/in-flight/killed.

## Evidence that shaped the verdict

- **Velocity:** 31 PRs merged in the ~26h before adjudication; 20 open. Codex's own doc
  went stale mid-writing (its "17 open PRs" snapshot, #1777 "current" → merged).
- **Existing rails already guard the dangerous surfaces:** synapse single-producer +
  undeclared-reader scans, dag conformance, Article-2 authority guards, 23 `check_*.py`
  total. No PR-collision check exists — but none of the observed incidents would have been
  prevented by one; they were prevented/caught by the rails above.
- **Verdict formats are not machine-parseable:** Haiku sweep found 3 dominant patterns +
  ~15% freeform across 492 docs; auto-extraction = high false-positive.
- **No CODEOWNERS exists**; `RF_CODEGEN_LANE_FOR_FABLE.md:18-19` already claims that
  decision as a precondition of the (NOT STARTED) codegen lane.

## Disposition of the Codex proposals

| Codex item | Verdict |
|---|---|
| Manual `config/active_builds.yml` (per-PR ownership declarations) | **REJECT** — stale-by-construction at ~30 merges/day; becomes noise or friction (ABM-R1) |
| `check_active_build_collisions.py` + `check_build_ownership_registry.py` as CI | **REJECT** as blocking CI; collision analytics salvaged into the generated map (ABM-R2) |
| `check_codeowners_required.py` / CODEOWNERS mandate | **DEFER** to RF codegen lane; enforcing reviews would break same-day babysitter merges today (ABM-R3) |
| S0–S5 severity ladder + owner-ack + merge-order rule engine | **REJECT** enforcement; collapsed to informational ⚠ flags (ABM-R7) |
| Generated `ACTIVE_BUILD_COLLISION_MAP` + `active_builds.json` | **BUILD, reshaped** — fully derived from `gh`, zero curation (ABM-R4) |
| "Do not recommend in-flight topics" | **BUILD, split** — temporal half in the map; permanent half is the new curated kill registry Codex missed (ABM-R5) |

## Rulings

- **ABM-R1** — No manually curated build-ownership registry. Anything a session must
  remember to update per-PR is presumed stale; ownership state must be *derived*.
- **ABM-R2** — No blocking CI on collisions or ownership declarations. PR-API-in-CI is
  brittle (Codex concedes this) and a false-positive tax on a 20-PR queue. The map is
  advisory; the existing authority/producer/dag guards remain the only hard gates.
- **ABM-R3** — CODEOWNERS/branch-protection deferred to the RF codegen lane's charter.
  Registered in `DO_NOT_REBUILD.md` §4 so it isn't re-proposed piecemeal.
- **ABM-R4** — BUILD `scripts/build_active_build_map.py` → `docs/ACTIVE_BUILD_MAP.md` +
  `data/governance/active_builds.json` (schema `active_builds.v1`). Sources: open PRs
  (+changed files, +mergeStateStatus), merges last 14d. Derived analytics: pairwise
  file collisions, protected-path touches (informational), DIRTY→"CONFLICTING — CI
  suppressed" flag (known repo failure mode). Nightly light job (off render path,
  fail-open, narrow commit) + on-demand. Artifact registered in synapse
  (tier: infrastructure).
- **ABM-R5** — BUILD `research/DO_NOT_REBUILD.md`: curated, append-per-adjudication
  registry of standing kills / forbidden designs / estimator laws / holds, seeded with
  ~40 entries; authority mirrors FR-2 (cite first; entry = grounds for summary
  REJECT-REDUNDANT). Auto-generation explicitly rejected on the sweep evidence.
- **ABM-R6** — Session protocol line added to CLAUDE.md: read the map + the registry
  before proposing or adjudicating new work.
- **ABM-R7** — Severity taxonomy collapsed to informational flags. No merge-order
  engine, no owner-ack ceremony, no override hierarchy. Merge races on generated
  registries stay owned by the existing drift-fix recipe.

## Non-goals (inherited from Codex intake, ratified)

No auto-merge, no auto-close, no branch manipulation, no replacement of Signal Bus/DAG,
no authority changes. Additionally ruled out here: no extractor over research verdicts,
no per-PR declaration ceremony.

## Success test (Codex's V1 test, answered by the built system)

A new session proposes "build macro context intake and memory rail into world_state and
the Mastermind bridge." `docs/ACTIVE_BUILD_MAP.md` shows #1635 open on
`feat/nw-macro-context` touching `engine/neuralweb/*` + `config/synapse.yml` +
`config/dag.yml` with ⚠ protected flags; the CLAUDE.md protocol line made the session
read it. Answer in one lookup: do not duplicate — review #1635 or write a narrow adjunct.
The permanent complement: a session proposing "signed-charm intensity signal" hits
`DO_NOT_REBUILD.md` §2 and self-rejects without burning a Fable census.

## Come-back clock

2026-07-21: check whether the nightly map job has been green for 2 weeks and whether any
adjudication since has appended to `DO_NOT_REBUILD.md`. If the registry has zero appends
despite new kill rulings, the append convention needs a CI nudge (revisit ABM-R2 scope).
