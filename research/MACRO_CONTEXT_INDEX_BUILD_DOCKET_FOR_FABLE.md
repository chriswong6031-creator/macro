# Macro Context Index

## AI-Only Knowledge Retrieval Plane — Build Docket for Fable

Date: 2026-07-18

Status: proposed program of record for Fable adjudication and build-out

Authority ceiling: agent context and research infrastructure only; never signal, rank, size, gate, or trading authority

Canonical deliverable: `research/MACRO_CONTEXT_INDEX_BUILD_DOCKET_FOR_FABLE.md`

---

## 1. Executive ruling

Build this now, but do not build a second hand-maintained knowledge base.

The Macro Dashboard already has a large knowledge corpus:

- source code, tests, configs, and contracts;
- `CLAUDE.md` and the atomic Claude memory store;
- research reports and masterplans;
- `research/DO_NOT_REBUILD.md` and the ruling graph;
- `docs/ACTIVE_BUILD_MAP.md` and Git history;
- `config/synapse.yml` and `docs/SIGNAL_BUS.md`;
- Metabolism lessons, priors, journals, and other typed artifacts.

The missing capability is a bounded retrieval plane that can locate, rank, and cite the right evidence without forcing every AI session to rediscover the repository through broad reads and repeated searches.

The correct product is therefore a **Macro Context Index**:

> A rebuildable, AI-only index over existing canonical sources that compiles a small, cited context packet for each task.

It must meet information where it already lives. It must not become a new source of truth. It must not require every session to copy edits or conclusions into another database.

### Immediate recommendation

1. Build a benchmark and lexical/structured retrieval core first.
2. Keep exact `ripgrep` and structured-registry lookup as first-class retrievers.
3. Add semantic embeddings only where the benchmark proves lexical retrieval misses paraphrases.
4. Use a local SQLite/FTS5 index for v1; do not begin with a Postgres service.
5. Expose narrow MCP/CLI retrieval tools, not a public UI or a monolithic answer endpoint.
6. Make merge-time incremental indexing automatic.
7. Require agents to query the index before nontrivial work, but do not require them to write a memory after every edit.
8. Preserve the current memory system until the new index wins a measured A/B test.

---

## 2. Why this is now justified

Repo and memory census taken against `origin/main` and the local Claude project memory on 2026-07-18:

| Corpus | Current scale |
|---|---:|
| Tracked repository files | 38,557 |
| Curated source/config/test/doc files after broad generated-data exclusions | 4,439 files / 87.83 MiB |
| `docs/` + `research/` Markdown | 870 files / 18.28 MiB |
| Atomic Claude memory files | 859 Markdown files / approximately 11 MiB |
| Entries in the main memory index | 591 |
| Entries in the secondary memory catalog | 200 |
| Raw size of the main `MEMORY.md` index | 157,973 bytes |

The existing Codex research lane also contains evidence of high context consumption. Across 15 versioned `usage_state.json` snapshots, median recorded input was 156,890 tokens and the maximum was 1,245,643 tokens.

That is not a clean billable-cost series:

- snapshots can repeat the most recent run;
- the runner currently normalizes total input but does not retain `cached_input_tokens` as a separate field;
- token totals include work beyond memory lookup.

It is nevertheless sufficient evidence that context acquisition is no longer a small concern. The system must begin measuring and reducing it deliberately.

### Present partial solutions are not a general context plane

Several useful systems already exist:

- Claude atomic memory provides durable fact records and description-driven recall.
- `ObsidianBrain/` provides a human view over memory and research.
- Metabolism `recall.py` performs relevance-ranked recall over `data/metabolism/lessons.jsonl` using deterministic token overlap and a prior-failure floor.
- Metabolism agenda/proposal paths already consume selected case law, active-build state, and lessons.
- `engine/neuralweb/research_queue.py` performs deterministic overlap detection against registered hypotheses and species.
- the ruling graph, kill registry, Signal Bus, active build map, and lobe registries already provide structured truth.

These are valuable source systems. None provides one query surface over code, research, memory, rulings, recent Git state, and live context.

---

## 3. Already covered and explicitly excluded

Fable must treat this section as a collision and scope fence.

### 3.1 Reuse; do not replace

| Existing system | Keep as | Context Index role |
|---|---|---|
| `CLAUDE.md` | Always-read constitution | Index it for discovery, but continue loading it directly |
| Atomic Claude memory | Durable operator/project facts | Private overlay source |
| `MEMORY.md` and `CATALOG.md` | Compatibility indexes during migration | Ingest descriptions; do not delete or shrink before A/B proof |
| `ObsidianBrain/` | Human browse/view layer | No edits; it is not the machine index |
| `research/DO_NOT_REBUILD.md` | Canonical standing kill registry | Structured, high-authority retriever |
| `config/ruling_graph.yml` | Canonical case-law registry | Structured, high-authority retriever |
| `docs/ACTIVE_BUILD_MAP.md` | Temporal PR/collision map | Freshness-sensitive retriever |
| Git commits and PRs | Change history and current delivery state | Recent-change retriever |
| `config/synapse.yml` / Signal Bus | Producer-consumer contract truth | Structured dependency retriever |
| Metabolism lessons and priors | Loop-specific steering memory | Optional scoped source; do not merge into operator memory |
| Research Factory / research queue | Candidate and trial lifecycle | Queryable source, not replaced |
| Source code and tests | Final implementation truth | Exact/symbol retrieval and source opening |

### 3.2 Do not build

- No public knowledge-base page.
- No general employee-facing wiki replacement.
- No Slack ingestion program unless Slack later becomes a real canonical source.
- No second copy of every file's content in Git.
- No requirement that every session manually write a knowledge record.
- No automatic extraction of verdicts from arbitrary research prose. `DO_NOT_REBUILD.md` explicitly records that verdict formats are inconsistent and that a generated extractor must not be built.
- No generic LLM that rewrites constitutional, ruling, kill, or operator-preference sources.
- No embedding of `site/`, large `data/` trees, raw parquet, caches, generated HTML, package artifacts, secrets, credentials, or private position data.
- No semantic retrieval result may become a Neural Web signal, score, escalation, rank, position size, gate, or trade decision.
- No autonomous memory deletion based only on age or low retrieval frequency.
- No Postgres, pgvector, HNSW, or separate network service in v1 unless the measured corpus or concurrency requires it.
- No LLM reranker in the hot path until deterministic hybrid retrieval has a benchmarked failure that justifies it.

### 3.3 Architectural placement

The Context Index is an **agent support/control-plane service**, not a Neural Web lobe.

It may help:

- Claude and Codex understand the repository;
- Fable adjudicate proposals against current house law and prior work;
- Metabolism avoid duplicate or prohibited constructions;
- research agents find relevant evidence and contracts;
- build agents locate implementation owners and tests.

It may not provide market authority. Any use inside autonomous loops must be marked context-only and citation-bearing.

---

## 4. Target operating model

The corpus is divided into three planes.

### 4.1 Shared repo plane

Rebuildable from the checked-out commit:

- `CLAUDE.md`;
- selected `docs/`, `research/`, `config/`, `engine/`, `scripts/`, `collectors/`, `lib/`, `app/`, `admin/`, `tests/`, and workflow files;
- local Git commit history;
- GitHub PR metadata when credentials/network are available.

This plane may be rebuilt on every host and may be distributed as a sanitized snapshot if needed.

### 4.2 Private operator overlay

Local-only sources:

- `~/.claude/projects/<project>/memory/`;
- private research not committed to the repo;
- operator preferences and local operational notes;
- optional Codex memory summaries when explicitly authorized.

This overlay must never be uploaded into a public artifact, static site, PR, or shared R2 bucket.

### 4.3 Live adapter plane

Queried at task time rather than treated as durable semantic memory:

- open PRs and merge state;
- current branch/worktree state;
- deployment/live host state;
- current engine artifacts and freshness;
- current market data;
- rate limits and token budgets.

Live results must carry `as_of`, source, and freshness status. They should not be embedded into long-lived memory merely because an agent queried them.

---

## 5. Source authority and conflict rules

Retrieval relevance is not authority. A semantically close summary may not override a current contract or test.

### 5.1 Authority classes

| Class | Examples | Default behavior |
|---|---|---|
| A0 — constitutional | `CLAUDE.md`, immutable operator policy, explicit operator ruling | Always surface when applicable; cannot be overridden by lower classes |
| A1 — canonical structured truth | configs, tests, ruling graph, kill registry, Signal Bus, schemas | Prefer over prose summaries |
| A2 — implementation truth | current code, workflows, builders | Open and verify before mutation |
| A3 — durable interpretation | atomic memory, adjudicated masterplans, research conclusions | Rank by status, recency, and source references |
| A4 — temporal state | Active Build Map, PRs, recent commits, live artifacts | Strong freshness decay; always print `as_of` |
| A5 — derived retrieval aid | LLM summary, embedding, subsystem index, inferred tags | Discovery only; never treated as truth without source opening |

### 5.2 Conflict behavior

When two sources disagree:

1. Return both sources.
2. Mark the conflict in the context packet.
3. Prefer higher authority only for routing, not silent deletion.
4. Prefer current-commit code/tests over stale prose for implementation behavior.
5. Prefer explicit rulings over inferred conclusions.
6. Require source opening before an agent changes code or makes an irreversible ruling.

The system must support `active`, `historical`, `superseded`, `killed`, `forbidden`, `deferred`, and `unknown` statuses. Historical and killed records remain retrievable when the query asks what was tried or why something must not be rebuilt.

---

## 6. Proposed v1 repository boundary

Fable may adjust names, but ownership must remain clear.

```text
config/context_index.yml
engine/context_index/
  __init__.py
  schema.py
  sources.py
  chunking.py
  ingest.py
  lexical.py
  structured.py
  fusion.py
  packet.py
  health.py
scripts/context_index_build.py
scripts/context_index_query.py
tools/macro_context_mcp.py
tests/test_context_index_schema.py
tests/test_context_index_ingest.py
tests/test_context_index_retrieval.py
tests/test_context_index_packet.py
tests/test_context_index_privacy.py
tests/test_context_index_incremental.py
research/context_index/
  BENCHMARK_QUESTIONS.jsonl
  BENCHMARK_BASELINE.md
  BENCHMARK_RESULTS.md
```

### Storage

The derived database must live outside tracked source:

```text
${MACRO_CONTEXT_INDEX_DIR}/shared.sqlite
${MACRO_CONTEXT_INDEX_DIR}/private.sqlite
${MACRO_CONTEXT_INDEX_DIR}/vectors/
```

If the environment variable is absent, use a repo-local ignored `.context-index/` directory. Do not hardcode an operator home path into production code.

Only health summaries and benchmark results may be committed. The indexed source text, private overlay, query logs, and vectors must not be committed.

---

## 7. Core data contracts

### 7.1 Source document record

```yaml
schema: context_document.v1
document_id: sha256-stable-id
project_ids: [macro-dashboard, neural-web]
source_type: code | test | config | research | memory | ruling | git | pr | live
source_uri: repo://research/DO_NOT_REBUILD.md
path: research/DO_NOT_REBUILD.md
title: DO NOT REBUILD
authority_class: A1
visibility: shared | private
status: active | historical | superseded | killed | forbidden | deferred | unknown
content_hash: sha256
git_sha: optional-commit-sha
valid_from: optional-iso8601
valid_to: optional-iso8601
source_as_of: iso8601
expires_at: optional-iso8601
supersedes: [optional-document-id]
tags: [governance, kills]
summary: optional-derived-discovery-summary
summary_model: optional-model-version
ingested_at: iso8601
```

### 7.2 Chunk record

```yaml
schema: context_chunk.v1
chunk_id: stable-document-plus-anchor-hash
document_id: parent-id
ordinal: 12
locator: research/DO_NOT_REBUILD.md#1-forbidden-by-ruling
heading_path: [DO NOT REBUILD, Forbidden by ruling]
symbol: optional-python-symbol-or-yaml-key
text: exact-source-text
token_count: integer
content_hash: sha256
neighbor_before: optional-chunk-id
neighbor_after: optional-chunk-id
```

### 7.3 Context packet returned to agents

```yaml
schema: context_packet.v1
query: user-or-agent-query
project_scope: [macro-dashboard]
mode: code | architecture | research | operations | live
generated_at: iso8601
repo_sha: current-commit
index_sha: indexed-commit
index_stale: false
token_budget: 6000
retrievers_used: [structured, rg, fts5]
results:
  - result_id: stable-id
    source_uri: repo://research/DO_NOT_REBUILD.md
    locator: research/DO_NOT_REBUILD.md#1-forbidden-by-ruling
    authority_class: A1
    status: active
    source_as_of: iso8601
    git_sha: commit
    excerpt: bounded-exact-source-text
    score_components:
      exact_rank: 2
      lexical_rank: 1
      semantic_rank: null
      fused_score: 0.0325
    why_retrieved: exact topic and active prohibition
conflicts: []
omitted_due_to_budget: 4
no_answer_reason: null
```

Every result must be traceable to a source. Derived summaries may help discovery but must link to the exact chunk they summarize.

### 7.4 Knowledge candidate emitted at session close

```yaml
schema: knowledge_candidate.v1
candidate_id: stable-id
task_id: optional-session-id
kind: operator_preference | durable_gotcha | architecture_contract | ruling_candidate
claim: concise proposed fact
why_durable: future failure prevented
source_refs:
  - repo://engine/example.py#symbol
confidence: evidence_complete | evidence_partial
proposed_owner: memory | ruling_graph | do_not_rebuild | canonical_doc
automatic_write_allowed: false
```

This is a proposal, not a memory write. High-authority destinations always require their existing review process.

---

## 8. Source configuration and projects

`config/context_index.yml` should declare projects, source roots, denies, authority, visibility, and freshness.

Illustrative shape:

```yaml
schema: macro_context_index.config.v1

projects:
  macro-dashboard:
    description: whole-repo default
  neural-web:
    includes_tags: [neural-web, signal-bus, metabolism]
  china-hk:
    includes_tags: [china, hk, asia]
  research-governance:
    includes_tags: [research, rulings, trials, kills]

sources:
  - id: repo-constitution
    roots: [CLAUDE.md]
    authority_class: A0
    visibility: shared
    chunker: whole_file
  - id: repo-rulings
    roots: [research/DO_NOT_REBUILD.md, config/ruling_graph.yml]
    authority_class: A1
    visibility: shared
    chunker: structured
  - id: repo-research
    roots: [research/**/*.md, docs/**/*.md]
    authority_class: A3
    visibility: shared
    chunker: markdown_sections
  - id: repo-code
    roots: [engine/**/*.py, scripts/**/*.py, collectors/**/*.py, lib/**/*.py]
    authority_class: A2
    visibility: shared
    chunker: python_symbols
  - id: claude-memory
    roots_from_env: CLAUDE_PROJECT_MEMORY_DIR
    authority_class: A3
    visibility: private
    chunker: memory_frontmatter

deny:
  - "**/.env*"
  - "**/*credential*"
  - "**/*secret*"
  - "**/auth.json"
  - "site/**"
  - "data/**"
  - "**/__pycache__/**"
  - "**/node_modules/**"
  - "research/artifacts/**"
  - "ObsidianBrain/**"
```

The actual deny policy must use path and content tripwires. Filename denial alone is insufficient.

The same source may belong to several projects without duplication. Project scopes are query-time filters, not separate copies.

---

## 9. Ingestion and chunking

### 9.1 Deterministic discovery first

The indexer must:

1. resolve the repository root explicitly;
2. read configured sources only;
3. apply deny rules before reading content;
4. compute a content hash;
5. skip unchanged documents;
6. replace changed chunks transactionally;
7. tombstone or remove records when sources are deleted;
8. stamp repo SHA, source `as_of`, and ingestion time;
9. fail closed on private/shared visibility ambiguity;
10. emit a health report without exposing indexed private text.

### 9.2 Chunking policy

| Source | Chunking rule |
|---|---|
| `CLAUDE.md` and small constitutional files | Whole file plus heading anchors |
| Markdown research/docs | Heading sections; preserve parent heading path; split oversized sections by paragraphs |
| Atomic memory | Frontmatter description as discovery chunk plus exact body chunks |
| Python | Module header, classes, functions, and neighboring docstrings; never split a signature from its body header |
| YAML | Top-level and second-level keys with full key path |
| JSON/JSONL | Only explicitly allowlisted small registries; typed row chunks |
| Tests | Test class/function plus target module tags |
| Git commits/PRs | Title, body, files, dates, state, and links; no giant patch body in the index |

Default target chunk size should be roughly 300–900 tokens. Do not force every source into one fixed byte size. Neighbor links must allow the retrieval layer to expand a matched section after ranking.

### 9.3 Code summaries

Do not begin by LLM-summarizing every source file.

V1 code discovery should use:

- exact identifier search;
- paths and imports;
- symbols and docstrings;
- test-to-module links;
- Signal Bus producer/consumer metadata;
- recent Git history.

Per-file or per-subsystem LLM summaries may be added later for high-use, poorly documented areas. Every summary must carry source hashes and be invalidated when any summarized source changes.

### 9.4 Incremental updates

Shared index:

- build from the current commit for local use;
- on merge to `main`, process `git diff --name-status <indexed_sha>..<new_sha>`;
- reindex only added/modified/renamed paths;
- delete/tombstone removed paths;
- publish a sanitized index snapshot only if cross-host distribution is required.

Private overlay:

- update from file hashes or a local scheduled job;
- never upload or include in CI artifacts;
- rebuild locally if the schema or embedding model changes.

Git hooks are not authoritative because they can be bypassed and do not cover every host. Merge/push automation plus local on-demand self-healing is the durable path.

---

## 10. Retrieval pipeline

### 10.1 V1 retrievers

Each retriever returns independently ranked evidence rows.

1. **Structured retriever**
   - ruling IDs, kill topics, Signal Bus artifacts, owners, consumers, active PRs, schemas, memory names, and status fields;
   - highest priority for explicit identifiers and governance questions.

2. **Exact code retriever**
   - `ripgrep` over scoped source roots;
   - exact filenames, symbols, error strings, flags, schema keys, and paths;
   - remains a direct tool rather than being hidden behind embeddings.

3. **Lexical retriever**
   - SQLite FTS5 with BM25 ranking;
   - field boosts for title, path, description, headings, symbols, and exact status terms;
   - freshness and authority applied as transparent modifiers after lexical rank.

4. **Recent-change retriever**
   - local Git and optional GitHub metadata;
   - recent commits/PRs involving matched paths or topics;
   - recency decay appropriate to temporal state.

### 10.2 Conditional V2 retriever

5. **Semantic retriever**
   - initially limited to memory descriptions, research sections, and subsystem summaries;
   - exact cosine search is sufficient at the expected v1 corpus size;
   - embedding model/version stored per vector;
   - never the sole retriever for governance or code identifiers.

Do not add approximate nearest-neighbor infrastructure until exact search latency or memory usage fails a measured threshold.

### 10.3 Fusion

Use reciprocal rank fusion or another deterministic rank-based fusion rather than attempting to normalize incomparable raw BM25, exact, vector, and recency scores.

Required post-fusion steps:

1. merge duplicate chunks and versions;
2. cap results per file/source;
3. apply project, visibility, status, and freshness filters;
4. ensure A0/A1 matches cannot be crowded out by many lower-authority chunks;
5. retain relevant killed/superseded records when the task is historical or proposal review;
6. expand neighboring chunks only after final ranking;
7. pack results to a hard token budget;
8. emit conflicts and omitted counts.

### 10.4 No silent answer synthesis

The retrieval service should return evidence, not pretend to be the final reasoner.

Claude, Codex, Fable, or another client owns synthesis. This keeps the retrieval layer cheap, testable, model-independent, and reusable.

An optional small reranker may be tested later, but the raw fused order and score components must remain observable for evaluation.

---

## 11. AI tool surface

Expose narrow, stable tools:

### `context_search`

Inputs:

- query;
- project scope;
- mode;
- source types;
- status filter;
- maximum results;
- token budget;
- include private overlay boolean.

Output: `context_packet.v1`.

### `context_open`

Open an exact source/result with bounded neighboring context. This is required before code mutation or high-authority adjudication.

### `context_recent`

Return recent commits, PRs, and active-build entries for a topic/path.

### `context_explain`

Return why a result ranked, its score components, source hash, and staleness.

### `context_status`

Return indexed SHA, current repo SHA, source counts, private/shared status, stale documents, last successful refresh, and benchmark version.

### `context_candidate`

Write a local `knowledge_candidate.v1` proposal. This must never directly modify constitutional or ruling sources.

The MCP server must not expose raw filesystem traversal beyond configured source roots.

---

## 12. Session operating contract

Add the following compact behavior to agent instructions only after the retrieval benchmark passes:

1. Before nontrivial repo work, query the Context Index with the task and project scope.
2. For proposals, always include governance, active-build, and prior-work retrieval.
3. For code changes, use retrieval to locate candidates, then open and verify current source/tests.
4. Never cite a summary when the exact source can be opened.
5. Do not inject the full memory index or broad research directories into the prompt.
6. Keep the context packet under its configured token budget.
7. At task close, emit a knowledge candidate only when the durable-value rule is satisfied.

### Durable-value rule

Promote a fact only if a future agent could otherwise make a materially:

- wrong;
- redundant;
- unsafe;
- authority-violating;
- or expensive decision.

Qualifying examples:

- operator preference;
- architecture ownership or contract;
- repeated operational gotcha;
- invalid estimator or falsified construction;
- permanent kill/prohibition;
- non-obvious source-of-truth location.

Non-qualifying examples:

- normal code change already represented by Git;
- branch or PR status;
- temporary debug output;
- one-off file locations discoverable by direct search;
- live market observations without a durable research conclusion;
- generic session summary.

---

## 13. Cleanup and stewardship

The index is a materialized view. Mechanical hygiene should be automatic; semantic governance remains source-owned.

### On every successful merge

- update changed shared-source chunks;
- delete/tombstone removed files;
- invalidate changed summaries and embeddings;
- update the indexed commit SHA;
- run retrieval smoke tests.

### Nightly

- compare indexed SHA to `origin/main`;
- detect missing, unreadable, or orphaned sources;
- detect expired live/temporal records;
- verify no denied paths entered the index;
- print source counts and index size;
- rebuild if incremental state is corrupt.

### Weekly AI curator

Produce proposals for:

- near-duplicate memory files;
- contradictory active facts;
- giant memory records that should be split;
- weak or missing descriptions;
- broken source links;
- frequently searched topics with no useful result;
- high-use stale summaries;
- records that appear superseded but lack an explicit link.

The curator may automatically repair only derived index state. It may not automatically merge, delete, or rewrite canonical memory, rulings, or research.

### Monthly or release-boundary review

- rerun the full benchmark;
- compare token use and tool calls with baseline;
- review false-positive and missed-source queries;
- review corpus growth and source caps;
- evaluate whether semantic retrieval remains justified;
- review private/shared boundary tests.

### Ownership

- **Fable/main loop:** architecture, authority, conflicts, and final adjudication.
- **Sonnet builder lanes:** deterministic ingestion, search, contracts, tests, and tooling.
- **Opus reviewer:** retrieval quality, privacy, contradiction behavior, and adversarial benchmark review.
- **Operator:** constitutional preferences, policy changes, and deletion/merger of important durable knowledge.
- **Context Index machinery:** hashes, refreshes, tombstones, stale flags, duplicates, and health reports.

No permanent human librarian is required. The operator should see only exceptions that require judgment.

---

## 14. Privacy, security, and provenance

### Hard requirements

- Shared and private indexes are physically separate SQLite files.
- Every query explicitly declares whether private overlay use is permitted.
- No private source text appears in committed health reports or logs.
- Query logs store hashes/metrics by default, not full sensitive queries.
- Ingestion scans for credential-shaped material before writing chunks.
- Symlinks must resolve inside configured roots; external symlinks fail closed.
- Source paths are normalized and traversal attempts rejected.
- MCP clients cannot request arbitrary paths.
- Every context result includes source URI, locator, authority, content hash, and `as_of`.
- Index schema and embedding version changes trigger explicit migrations or rebuilds.

### Freshness

Suggested default SLAs:

| Source | Freshness expectation |
|---|---|
| Current repo code/config/tests | Indexed SHA must match current task SHA or packet is stale |
| Active Build Map / open PRs | Less than 15 minutes for proposal/merge tasks |
| Atomic memory | Less than 24 hours, with on-demand refresh |
| Adjudicated research/rulings | Hash-based; no age decay while active |
| Live artifacts | Source-specific SLA; stale results visibly marked |
| Derived summaries | Invalid immediately when any source hash changes |

---

## 15. Token and efficiency telemetry

The build is not complete without a cost ledger.

### Repair current Codex telemetry

`engine/codex_lane/runner.py` already receives `cached_input_tokens` in the current event protocol but normalizes usage into input/output/total fields. Preserve at least:

```yaml
input_tokens: integer
cached_input_tokens: integer
noncached_input_tokens: integer
output_tokens: integer
reasoning_output_tokens: integer
total_tokens: integer
```

Do not infer billable cost unless model-specific pricing and caching rules are explicitly available. The first goal is comparative workload measurement.

### Per-task retrieval telemetry

Record locally:

- task category;
- project scope;
- retrieval modes used;
- query count;
- result count;
- retrieved token count;
- source-open count;
- broad `rg`/file-read count after retrieval;
- end-to-end task input/output/cached tokens where available;
- retrieval latency;
- whether the canonical source was found;
- whether the agent later discovered a missed source;
- whether the answer/edit required correction.

### Success gates

After a representative A/B period, promotion to default preflight requires:

- at least 90% canonical-source Recall@10 on the frozen benchmark;
- at least 95% precision for A0/A1 governance answers;
- no private-source leakage in adversarial tests;
- no correctness degradation versus baseline;
- at least 30% lower median input tokens on repo-grounded architecture/research sessions, or an equivalent reduction in tool/file-read burden if caching masks token savings;
- at least 50% fewer broad exploratory file reads on benchmark tasks;
- default packet no larger than 6,000 tokens and hard maximum no larger than 8,000 tokens;
- lexical/structured local p50 latency below 2 seconds;
- index SHA mismatch visibly fail-stale, never silently pass-current.

If token use does not improve, do not broaden the corpus. Diagnose routing, source authority, chunking, and packet packing first.

---

## 16. Frozen benchmark design

### 16.1 Question families

Create 80–120 real questions from prior sessions and recent repo work:

| Family | Examples |
|---|---|
| Location | Where is the producer for artifact X? Which builder renders page Y? |
| Ownership | Does Oracle, Neural Web, Cycle, or Mastermind own this capability? |
| Contract | What schema and consumers govern artifact X? |
| Governance | Was construction X killed, deferred, or forbidden? |
| Current state | Is work on topic X already open or recently merged? |
| Gotcha | What previously broke this path and how was it repaired? |
| Architecture | What already exists, and what is genuinely missing? |
| Research | Which reports tested this idea and what was the verdict? |
| Code | Which symbols/tests implement behavior X? |
| Freshness | Is the retrieved statement current enough for this task? |

### 16.2 Golden labels

Every benchmark row must contain:

```json
{
  "id": "CTX-001",
  "query": "Where is the canonical producer-consumer registry?",
  "project": "macro-dashboard",
  "mode": "architecture",
  "required_sources": ["config/synapse.yml", "docs/SIGNAL_BUS.md"],
  "acceptable_sources": ["CLAUDE.md"],
  "forbidden_as_authority": ["derived subsystem summary"],
  "required_status": "active",
  "notes": "Signal Bus config is canonical; generated doc is readable projection"
}
```

Questions must include lexical mismatch, exact error strings, renamed systems, superseded reports, and negative-control queries with no answer.

### 16.3 Baseline

For each benchmark task, record the existing workflow:

- commands/tool calls;
- files opened;
- bytes/tokens introduced;
- elapsed time;
- final sources used;
- correctness and correction burden.

Do not claim savings without this baseline.

---

## 17. Build program

### CXI-W0 — Census, contracts, and benchmark

**Goal:** freeze the problem and avoid building retrieval theater.

Deliver:

- `research/context_index/BENCHMARK_QUESTIONS.jsonl`;
- `BENCHMARK_BASELINE.md`;
- corpus/source census with deny analysis;
- `context_document.v1`, `context_chunk.v1`, `context_packet.v1`, and `knowledge_candidate.v1` schemas;
- source authority and freshness policy;
- privacy threat model;
- v1 file/path ownership ruling.

Acceptance:

- at least 80 benchmark questions;
- golden required sources reviewed by Opus;
- at least 10 no-answer/negative controls;
- at least 10 governance conflicts or superseded-source tests;
- private/shared boundary reviewed before implementation.

### CXI-W1 — Shared lexical and structured core

**Goal:** useful retrieval without embeddings or an LLM hot path.

Deliver:

- SQLite schema and migrations;
- configured shared-source discovery and denies;
- Markdown, memory-description, Python-symbol, YAML, and small-registry chunkers;
- content-hash incremental ingestion;
- FTS5/BM25 retrieval;
- structured lookup for rulings, kills, Signal Bus, active builds, and Git metadata;
- CLI build/query/status commands;
- provenance-bearing context packets.

Acceptance:

- deterministic rebuild produces the same logical record hashes;
- changed-file run touches only changed documents;
- deletion removes or tombstones records;
- no denied source reaches the DB;
- benchmark Recall@10 reported by family, with nulls printed.

### CXI-W2 — Tool surface and session packet

**Goal:** make retrieval usable by Claude, Codex, Fable, and future agents.

Deliver:

- MCP tools `context_search`, `context_open`, `context_recent`, `context_explain`, and `context_status`;
- deterministic rank fusion;
- authority/status/freshness filtering;
- neighbor expansion after ranking;
- per-file and per-source diversity caps;
- hard token-budget packer;
- conflict and stale-index reporting.

Acceptance:

- no arbitrary filesystem reads through MCP;
- packet never exceeds hard token budget;
- exact source locators open successfully;
- stale repo SHA is visible in every packet;
- A0/A1 results survive lower-authority result floods.

### CXI-W3 — Private overlay and project scoping

**Goal:** retrieve operator/project memory without leaking it.

Deliver:

- separate private SQLite database;
- memory frontmatter ingestion;
- project membership without source duplication;
- query-time private-overlay opt-in;
- local-only refresh and health;
- redaction/leak tests.

Acceptance:

- private chunks never appear when opt-in is false;
- no private content in committed artifacts or logs;
- private index can be deleted and rebuilt without affecting shared index;
- project scoping improves benchmark precision without reducing required recall.

### CXI-W4 — Conditional semantic retrieval

**Entry condition:** lexical/structured benchmark has documented paraphrase misses that cannot be fixed with metadata, aliases, or field boosts.

Deliver:

- embedding provider abstraction;
- versioned embeddings for memory descriptions, research sections, and selected subsystem summaries only;
- exact vector search;
- RRF integration;
- embedding invalidation on source/model change;
- cost and latency report.

Acceptance:

- semantic lane improves frozen-query Recall@10 by a predeclared margin;
- exact/error-string/code-symbol queries do not regress;
- semantic results cannot override A0/A1 status filters;
- the index remains within local size/latency budget;
- embeddings can be removed with lexical retrieval still functional.

### CXI-W5 — Automation, health, and curator

**Goal:** keep the index current without asking sessions to maintain it manually.

Deliver:

- merge/push incremental refresh;
- on-demand SHA self-heal;
- nightly health job;
- weekly curator report;
- missing-query and contradiction queue;
- optional sanitized shared-index snapshot if multi-host need is proven.

Acceptance:

- main-merge changes become searchable within the declared SLA;
- corrupt/incomplete incremental state triggers a clean rebuild;
- curator only proposes canonical edits;
- shared snapshot contains no private source paths or text.

### CXI-W6 — Agent default and measured migration

**Entry condition:** W1–W3 pass correctness/privacy gates; W4 is optional.

Deliver:

- compact `CLAUDE.md` preflight instruction;
- Codex/Claude context-packet integration;
- token telemetry repair, including cached-input fields;
- A/B benchmark results;
- migration recommendation for `MEMORY.md` and `CATALOG.md`.

Acceptance:

- success gates in §15 pass;
- agents still verify exact code before mutation;
- no constitutional or ruling source is silently summarized away;
- old memory indexes remain available until explicit operator/Fable retirement ruling.

---

## 18. Suggested first PR sequence

Keep hot files and authority surfaces isolated.

1. **PR CXI-0:** this docket plus frozen benchmark/contracts only.
2. **PR CXI-1:** SQLite schema, source config, deterministic ingestion, and unit tests.
3. **PR CXI-2:** structured + FTS5 retrieval, packet packer, evaluation report.
4. **PR CXI-3:** MCP tools and stale/conflict behavior.
5. **PR CXI-4:** private overlay and privacy suite.
6. **PR CXI-5:** semantic retrieval only if entry condition passes.
7. **PR CXI-6:** automation, token telemetry, and default agent preflight.

Avoid combining `CLAUDE.md`, workflow automation, private overlay, and retrieval core in one PR. Each changes a different trust boundary.

Before every PR, regenerate/read the current Active Build Map and re-check `DO_NOT_REBUILD.md` for newly claimed or prohibited lanes.

---

## 19. Test and adversarial review matrix

Required tests include:

### Schema and determinism

- stable document/chunk IDs;
- idempotent rebuild;
- deterministic FTS result order for ties;
- schema migration and full-rebuild path;
- Unicode/Chinese headings and symbols.

### Incremental behavior

- add, edit, rename, delete;
- changed summary invalidation;
- repo SHA mismatch;
- interrupted transaction recovery;
- concurrent reader during update.

### Retrieval quality

- exact error string beats semantic paraphrase;
- path/symbol query returns code and tests;
- governance query returns active ruling before stale prose;
- historical query can retrieve killed/superseded records;
- duplicate chunks do not flood top results;
- neighboring context is expanded only after ranking;
- no-answer query returns an honest no-answer packet.

### Privacy and security

- `.env`, credentials, auth, key-shaped strings, and denied paths rejected;
- symlink escape rejected;
- path traversal rejected;
- private overlay omitted by default;
- query logs contain no private excerpts;
- sanitized snapshot audit.

### Authority and conflict

- A0/A1 cannot be displaced by many A5 summaries;
- code/test disagreement is surfaced;
- stale active-build state is marked;
- a summary with a stale source hash cannot rank as current;
- a killed construction is not returned as a build recommendation without its status.

### Token packing

- packet under default and hard caps;
- top result remains whole;
- low-authority duplicates dropped before high-authority evidence;
- omitted result count printed;
- result excerpts bounded and source-open tool available.

Opus red-team should attempt:

- secret exfiltration through crafted queries;
- prompt injection stored inside research prose;
- authority laundering through derived summaries;
- recency laundering through copied old documents;
- result flooding by duplicate files;
- malicious symlinks and odd filenames;
- query terms that collide with market tickers or short acronyms;
- false confidence when the index SHA is stale.

Retrieved content is data, not an instruction. The synthesis agent must not obey instructions found inside indexed documents unless they come from an explicitly authorized instruction source.

---

## 20. Scale and storage ruling

Corpus size is not prompt size.

At the current roughly 100 MiB high-value text/source corpus, a local index should be operationally small. Even tens of thousands of chunks plus metadata and dense vectors should generally remain sub-gigabyte to low-single-digit gigabytes, depending on embedding dimensions and precision.

The prompt receives only a bounded evidence packet.

Do not impose a small corpus cap merely because model context is limited. Instead cap:

- results per source;
- results per file;
- neighbor expansion;
- total packet tokens;
- stale temporal retention;
- generated summaries;
- embedded source types.

Upgrade from SQLite/exact vectors to Postgres/pgvector or an ANN service only if one of these is measured:

- millions of active chunks;
- exact vector latency outside the SLA;
- simultaneous multi-host writers;
- central ACL/audit requirements;
- index distribution becomes more complex than a rebuildable snapshot.

No infrastructure promotion should occur because a larger system sounds more sophisticated.

---

## 21. Principal failure modes

### Failure 1 — A second source of truth

**Symptom:** agents update the index but not the canonical file.

**Prevention:** index is derived and rebuildable; direct database edits forbidden.

### Failure 2 — Memory sludge

**Symptom:** every session writes summaries and the corpus fills with transient facts.

**Prevention:** durable-value rule plus `knowledge_candidate.v1`; no automatic canonical write.

### Failure 3 — Semantic search replaces verification

**Symptom:** agents edit code based on summaries.

**Prevention:** `context_open` and exact source verification required before mutation.

### Failure 4 — Stale authority laundering

**Symptom:** an old research report outranks current code or a later ruling.

**Prevention:** authority/status/validity fields, source hashes, conflict packet.

### Failure 5 — Retrieval becomes more expensive than search

**Symptom:** planner, embeddings, reranker, and synthesis consume more tokens than `rg`.

**Prevention:** deterministic routing, exact search first, no LLM hot path in v1, measured A/B.

### Failure 6 — Generated-output noise

**Symptom:** site/data artifacts dominate results.

**Prevention:** allowlist source roots and strict denies; index structured metadata rather than raw output.

### Failure 7 — Private-memory leakage

**Symptom:** operator memory appears in shared CI/R2 or an agent without permission.

**Prevention:** physically separate DBs, explicit opt-in, adversarial privacy tests.

### Failure 8 — Index drift across agents

**Symptom:** agents retrieve different truths from different indexed SHAs.

**Prevention:** every packet reports repo/index SHA; stale mismatch is visible and self-heals.

### Failure 9 — Ruling extractor resurrects dead work

**Symptom:** freeform research prose is auto-parsed into an incorrect active verdict.

**Prevention:** structured rulings/kill registry only; no general verdict extractor.

### Failure 10 — Context Index becomes a market brain

**Symptom:** retrieved prose affects score/rank/size/gate.

**Prevention:** context-only authority ceiling, no scored-path consumer, CI/source review if later wired into autonomous loops.

---

## 22. Requested Fable adjudication

Fable should respond with a concrete ruling, not a general brainstorm.

Required response:

1. **Verdict:** BUILD / MODIFY / HOLD.
2. **Placement:** ratify or replace the proposed repository boundary.
3. **Authority:** confirm the context-only ceiling and identify prohibited consumers.
4. **Source policy:** ratify shared/private/live planes and authority classes.
5. **V1 scope:** identify exactly which W0–W3 files and sources ship first.
6. **Embedding ruling:** confirm that W4 is conditional on benchmarked lexical misses.
7. **Ownership:** name build, review, merge, and operator-exception owners.
8. **Collision audit:** cite any newly opened PR or existing program that supersedes a lane.
9. **Build sequence:** dispatch the first PR without combining hot trust-boundary files.
10. **Stop/go gates:** ratify or amend the benchmark, privacy, token, latency, and correctness thresholds.

### Recommended Fable ruling

> BUILD, with W0 benchmark first and W1 lexical/structured retrieval as the first implementation. Preserve existing memory and governance sources. Keep the Context Index outside market authority. Do not approve embeddings, a network database, or default session wiring until deterministic retrieval is benchmarked.

---

## 23. External methodology references

- Cerebras, “How we built our knowledge base” — hybrid lexical/vector retrieval, source-local ingestion, project scoping, reranking, and MCP primitives: <https://www.cerebras.ai/blog/how-we-built-our-knowledge-base>
- SQLite FTS5 — full-text indexing and BM25 ranking: <https://www.sqlite.org/fts5.html>
- pgvector — later-stage exact/approximate vector search and hybrid retrieval option, not required for v1: <https://github.com/pgvector/pgvector>
- GitHub webhook push event — optional merge/push-triggered incremental refresh: <https://docs.github.com/en/webhooks/webhook-events-and-payloads#push>

---

## 24. Final build instruction

The core design law is:

> Canonical sources remain where they are. The Context Index compiles evidence; it does not own truth.

Build the smallest system that proves it can find the correct source faster, with fewer tokens, while preserving authority, freshness, privacy, and exact verification. Expand only when the frozen benchmark identifies a measured retrieval gap.
