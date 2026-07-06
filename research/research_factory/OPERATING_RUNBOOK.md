# Research Factory — Operating Runbook

How to run a factory batch end-to-end, exactly as Batch A was run (2026-07-06, #1623 + #1629). For any fresh session operating the factory. Charter: `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` — the law; this file is just the commands.

## Standing facts

- State is resolved from `data/research_factory/transitions.jsonl` (last transition per candidate_id wins). The `status` field on `candidates.jsonl` rows is the ingest-time snapshot — do NOT read it as current state.
- All ledgers are git-tracked; batch runs happen on a fresh branch off `origin/main`, finish commit → push → PR → same-day squash-merge. `data/experiments/registry_seed.json` and `data/neuralweb/governance.jsonl` are append-race-prone with concurrent PRs — resolve rebase conflicts by UNION (keep both sides' entries).
- Human-gate transitions (`paper`/`deferred`/`rejected`/`scoped_build`, and respin registration) require actor `fable`/`operator` with `--actor-ref` — `engine/research_factory/state.py` raises otherwise. The challenger is ADVISORY; its recommendation never picks a branch.
- The nightly monitor (`scripts/research_factory_monitor.py --write`, daily.yml engine job) is the ONLY writer of `paper_monitor.jsonl`/nightly `health.jsonl` rows. Manual monitor runs stay `--dry-run`.
- LLM invocation is operator/Fable-only (RF-16). No script in the repo calls an LLM.

## Batch procedure

1. **Ingest** (pick sources):
   - External report: `python scripts/research_factory_report_pack.py --report <path>` → run the extraction prompt with an LLM out-of-band → proposals JSON → `python scripts/research_factory_ingest.py --manual <path> --write`
   - Oracle brainstorm: `oracle_ingest_brainstorm` scratch output → `--oracle-scratch <dir> --oracle-inbox <dir> --write`
   - Adopt existing domain compounds (RF-2 pointers): `--adopt-oracle <id> ...` or `--adopt-promotion-queue --write`
   - Neural Web queue: `--research-queue [--nominate <id>] --write`
   - Respins: `--respin-of <candidate_id> --actor fable --actor-ref <ref>` (human-gated; generation cap 2)
   Dedup drops persist keep-first with reasons — check stderr and the transition log.
2. **Run adapters:** `python scripts/research_factory_run.py --execute` (dry-run first if unsure; NEVER pass `--count` unless you intend a counted oracle 63d screen — that spends trial-ledger search width).
3. **Challenge** (top N by a declared simple criterion, e.g. n): per candidate `python scripts/research_factory_challenge_pack.py --candidate <id>` → spawn an Opus reviewer agent (agentType='reviewer' — the routing guard blocks bare model spawns) with: "Read research/research_factory/CHALLENGER_PROMPT.md IN FULL, read <packet path>, write the response JSON to /tmp/rf_batch/<id>.response.json; read-only otherwise." Then `--ingest-response /tmp/rf_batch/<id>.response.json` (validates; malformed = no transition).
4. **Queue:** `python scripts/build_research_factory_review_queue.py --write` → read `data/research_factory/review/queue.md`.
5. **Decide** (the human gate — read the packets first, genuinely): `python scripts/research_factory_decide.py --candidate <id> --actor fable --actor-ref <session-ref> --decision ...`
   - `paper`: `--expected-half-life-d <d>` (default prior 250, recorded as defaulted) — writes seed entry + track skeleton. Consider enriching the track file with challenger-derived `paper_tripwires` (Batch A precedent: A15).
   - `rejected`: `--kill-class <duplicate|falsified|underpowered_accruing|regime_change_suspect|decayed|budget_withdrawn> --n-at-kill <n>` (underpowered/regime-suspect also write a requeue pointer; re-arm is a human decision).
   - `deferred`: `--come-back-on YYYY-MM-DD`. `scoped_build`: `--program-doc research/<NAME>_BY_FABLE.md`.
6. **Close:** rebuild queue (`--write`, should drain), update charter §0 status log, commit/PR/merge. The nightly monitor takes over paper candidates from there.

## Current work-list (as of 2026-07-06, post-Batch A)

- **A17_WASHOUT_SAME_OUT_NEG_VEL, A24_SAME_IN_LOW_VOL_ROUTE, A46_SAME_IN_CHOP_FILTER** sit at `screened` — the natural Batch A2 (challenge → review → decide). Note A17 is itself gauntleted domain-side; the A9/C6 kill rationales lean on it — read their challenge files first.
- **A15** in `paper`: seed clock 2027-03-13; tripwires in `data/research_factory/track/rf-20260706-adopt-a15_washout_opp_out_2node.json` (beta-attribution vs size-matched null; cluster-adjusted SE required before any promote_eligible). The monitor grades nightly once live outcomes mature (~21d).
- **Optional respins recorded in kill steelmen:** A9 under a labeled modern-regime track; TERM_PREMIUM_02 only with an entry-set redundancy audit + registered trial family. Both require human-gated respin registration (RF-15).
- **Deferred separate programs** (each has a seed doc): `research/RF_CODEGEN_LANE_FOR_FABLE.md`, `research/RF_AUTO_SCHEDULING_FOR_FABLE.md`, `research/RF_CORTEX_BATCH_FOR_FABLE.md`, `research/RF_SURFACING_FOR_FABLE.md`.
