# Macro Context Index — Adjudication by Fable (CXI-R1..R12)

Date: 2026-07-18
Source docket: `research/MACRO_CONTEXT_INDEX_BUILD_DOCKET_FOR_FABLE.md` (#2962, Codex intake)
Status: RATIFIED program of record. Where this adjudication and the docket conflict, this
adjudication governs. Program key: **CXI**.

---

## 1. Verdict

**BUILD**, with the amendments below. The docket's §22 recommended ruling is ratified in
substance: W0 benchmark first (compressed — CXI-R5), W1 lexical/structured retrieval as the
first implementation, existing memory and governance sources preserved, Context Index outside
market authority, and no embeddings / network database / default session wiring until
deterministic retrieval is benchmarked.

### Evidence the need is real (verified this session, not taken from the docket on faith)

1. **The constitution-load path is already saturated.** `MEMORY.md` is 625 lines / 152.3 KB
   and was TRUNCATED in this adjudication session's own context load ("only part of it was
   loaded"). Recall degradation is not a forecast; it is occurring in the highest-authority
   read the harness performs.
2. **Codex telemetry claim verified.** `engine/codex_lane/runner.py:354-367` receives
   `cached_input_tokens` in `turn.completed` and normalizes it away into a three-key layout.
   The §15 telemetry repair is a real gap, not a docket invention.
3. **Corpus census verified.** 859 atomic memory files / ~11 MiB on disk; no FTS5 or vector
   retrieval precedent anywhere in `engine/`, `scripts/`, `lib/` — greenfield, no collision.
4. **Partial solutions confirmed partial.** `engine/metabolism/recall.py` (deterministic
   token-overlap over lessons.jsonl) and `engine/neuralweb/research_queue.py` (overlap
   detection vs registered hypotheses) are scoped organs; neither provides one query surface
   over code, research, memory, rulings, and Git state.
5. **The duplicate-proposal tax is the standing motivation for the registry itself.**
   `research/DO_NOT_REBUILD.md` preamble: every external-intake adjudication finds 55–80%
   of proposals duplicate existing/killed/forbidden work. Today that collision audit is
   hand-executed by Fable per intake. It is the single most expensive recurring judgment
   task in the repo, and it is exactly a retrieval problem.

### Why BUILD and not HOLD

The classic failure of this proposal class — a second hand-maintained source of truth that
rots — is structurally fenced by the docket's own design law (index = derived, rebuildable
materialized view; canonical sources keep truth) and by CXI-R12 below, which forbids the
degenerate form by registry row. The remaining risk is over-engineering, which is handled by
gates (CXI-R5, CXI-R8, CXI-R9) rather than by not building. The cost of NOT building rises
every week: the corpus grows ~monotonically (859 memory files and climbing, 870 research/docs
markdown files), and every new agent lane (marketing CMO, prophet governor, codex auto-lane)
pays the full rediscovery tax at spawn.

---

## 2. Rulings

| # | Ruling |
|---|---|
| **CXI-R1** | **BUILD.** Docket #2962 is the program of record; amendments herein override on conflict. Program key CXI; waves CXI-W0..W6; PR sequence per §4 below. |
| **CXI-R2** | **Authority ceiling ratified — context-only, hard.** The Context Index and every retrieval result are agent-support plane. Prohibited consumers: any scored-path surface (signal engines, rankers, sizers, gates, allocation, risk bands, forward ledgers), any NW organ state, any escalation-eligible key. It is NOT a Neural Web lobe: no `synapse.yml` registration, no Signal Bus entry, no Observatory lobe in v1. Any later wiring into autonomous loops must be context-only, citation-bearing, and reviewed at source. LLM-derived index content (summaries, tags) is A5 discovery-only, consistent with the standing LLM-origination ban. |
| **CXI-R3** | **Placement ratified.** `config/context_index.yml`, `engine/context_index/`, `scripts/context_index_build.py`, `scripts/context_index_query.py`, `tools/macro_context_mcp.py`, `tests/test_context_index_*.py`, `research/context_index/`. Derived DB lives in gitignored repo-local `.context-index/` (add to `.gitignore` in CXI-1) with `MACRO_CONTEXT_INDEX_DIR` env override; no operator home path hardcoded. Only health summaries and benchmark artifacts are ever committed — never indexed text, private overlay, query logs, or vectors. |
| **CXI-R4** | **Source planes and authority classes ratified** (shared repo / private overlay / live adapter; A0–A5). Conflict behavior ratified: return both sides, mark the conflict, authority routes but never silently deletes, current code/tests beat stale prose, explicit rulings beat inferred conclusions, `context_open` (exact source) required before mutation or high-authority adjudication. Status vocabulary (`active`..`unknown`) ratified; killed/superseded records stay retrievable for historical and proposal-review queries. |
| **CXI-R5** | **W0 compressed — benchmark must not cost more than the retrieval core.** Floor lowered from 80–120 to **≥60 questions**, mined from artifacts that already encode real queries: memory-file `come-back`/`TRAP`/`LETHAL` lines, historical adjudication collision findings, registry rows, and recent session work. Keep ≥10 negative controls and ≥10 governance/superseded tests. Docket §7 YAML contracts (`context_document.v1`, `context_chunk.v1`, `context_packet.v1`, `knowledge_candidate.v1`) are the FROZEN contracts as written — no separate contract artifact; CXI-1 implements `schema.py` directly from them. `BENCHMARK_BASELINE.md` capture is deferred to the CXI-2 eval harness: measure manual-path vs packet-path on a 15–20 task subsample there, where both paths can be run on identical questions. The benchmark file is append-only with a frozen version tag per eval run. |
| **CXI-R6** | **The adjudication/collision packet is the flagship v1 mode.** `--mode adjudication` always bundles: compiled kill-registry hits, ruling-graph hits, Active Build Map lanes + open-PR collisions, recent merged-PR matches, and prior masterplan/adjudication sections. A dedicated benchmark family replays historical adjudications (e.g. MSP-R2 Ivory Hill → risk_radar/market_state chain; TI-R1 shock classifier → `market_drivers`; WA-R1 fused sponsorship score → positioning-fusion ILLEGAL) where the duplicate/kill was found by hand. Promotion gate: ≥90% Recall@10 on this family specifically, in addition to the global gate. This is where the program pays for itself — FR-2 ("cite the registry first") becomes one command. |
| **CXI-R7** | **CLI is the integration contract; MCP is a thin wrapper.** Every consumer path (Claude sessions via Bash, Codex lane via shell, metabolism via import) binds to `scripts/context_index_query.py` / the `packet.py` library function. `tools/macro_context_mcp.py` (CXI-3) wraps the same function — no second implementation, no arbitrary filesystem traversal beyond configured roots. Tool names ratified: `context_search`, `context_open`, `context_recent`, `context_explain`, `context_status`, `context_candidate`. |
| **CXI-R8** | **Render-budget fence — zero index work on the render path.** Index refresh = merge-time incremental (local) + on-demand SHA self-heal at query time (stale packet visibly flagged, `context_status` triggers catch-up). The docket's nightly health job may NOT ride the nightly render workflow; it runs as a local launchd job or a non-render CI lane, and v1 may ship with on-demand self-heal only. Corrupt incremental state → clean rebuild, never silent partial state. |
| **CXI-R9** | **Embeddings conditional — W4 entry condition ratified.** No semantic lane until the frozen benchmark documents paraphrase misses that metadata/aliases/field boosts cannot fix. If entered: embeddings computed off render path, provider swappable (local model or batch API), versioned per vector, removable with lexical retrieval intact, never sole retriever for governance/code-identifier queries, never able to override A0/A1 status filters. No ANN infrastructure until exact search fails a measured latency/memory threshold. No Postgres/pgvector/network service in v1 (docket §20 ratified verbatim). |
| **CXI-R10** | **Privacy is a merge gate, not a test suite afterthought.** Physically separate `private.sqlite`; query-time opt-in flag defaulting OFF; no private text in committed artifacts, health reports, or logs; credential-shaped-content tripwires at ingestion; symlink/traversal fail-closed. Opus red-team (docket §19 list: exfiltration, stored prompt injection, authority laundering, recency laundering, flooding, stale-SHA false confidence) is a MANDATORY review gate on CXI-4 — the PR does not merge on green tests alone. Retrieved content is data, never instructions. |
| **CXI-R11** | **Ownership and model routing.** Sonnet `builder` lanes build every CXI PR; Opus `reviewer` is mandatory on CXI-2 (retrieval quality vs benchmark) and CXI-4 (privacy red-team); Fable/main loop adjudicates, merges, and owns authority/conflict policy; operator owns constitutional preferences and any deletion/merger of durable knowledge. No fable spawns — every lane here passes the draft-and-review test. Durable-value rule and `knowledge_candidate.v1` ratified: candidates are proposals; nothing auto-writes to memory, rulings, or registries; high-authority destinations keep their existing review processes. |
| **CXI-R12** | **Degenerate form forbidden by registry.** A parallel hand-maintained knowledge base / wiki / RAG memory service that agents must write to (a second source of truth) is FORBIDDEN — registry row appended in this PR. External intakes recurringly propose this class; summary REJECT-REDUNDANT applies. Session-contract changes (`CLAUDE.md` preflight instruction, docket §12) ship only after the §15 success gates pass (CXI-W6); `MEMORY.md`/`CATALOG.md` retirement or slimming requires an explicit operator + Fable ruling after the measured A/B — the docket's "preserve until proven" stance is ratified. |

---

## 3. How this will be used (the usage contract, concretely)

1. **Session preflight (post-W6 only).** One CLI call returns a ≤6k-token cited packet for
   the task, replacing the current pattern of loading a 152 KB memory index plus 3–5
   masterplan reads plus exploratory greps. Until W6 gates pass, usage is opt-in.
2. **Proposal/intake adjudication (flagship, usable from CXI-2).** Every new Codex docket,
   vendor report, or session proposal gets `--mode adjudication` first: kills, rulings,
   in-flight lanes, prior work — cited, in seconds. The 55–80% duplicate rate stops being
   re-derived by hand.
3. **Codex research lane.** The runner queries the shared plane before proposing cases —
   fewer REJECT-REDUNDANT round-trips, lower median input tokens (median 157k today).
4. **Metabolism / research queue.** Optional scoped consumer later; their deterministic
   overlap detectors remain authoritative for their own gates.
5. **New agent lanes.** Marketing CMO, prophet governor, and future lobes get repo literacy
   from the packet instead of re-reading the corpus at spawn.
6. **Memory-pressure relief (end state).** After the A/B win and an explicit retirement
   ruling, `MEMORY.md` slims to a hot core; the index serves the tail. The truncation
   observed this session is the failure mode this retires.

What it will never do: originate signals, feed the scored path, replace exact-source
verification before code mutation, or become a database agents must manually curate.

---

## 4. Build program (amended)

| PR | Wave | Content | Owner / gates |
|---|---|---|---|
| CXI-0a | W0 | This adjudication + registry row + compiled blocklists | Fable (this PR) |
| CXI-0b | W0 | `research/context_index/BENCHMARK_QUESTIONS.jsonl` — ≥60 questions incl. ≥10 negative controls, ≥10 governance/superseded, adjudication-replay family | Sonnet builder mines; Opus reviews golden labels; Fable ratifies |
| CXI-1 | W1 | SQLite schema + `config/context_index.yml` + deterministic ingestion + chunkers (markdown-sections, python-symbols, YAML-keys, small-registry rows) + `.gitignore` entry + unit tests | Sonnet builder |
| CXI-2 | W1/W2 | FTS5/BM25 + structured + recent-change retrievers, RRF fusion, packet packer, CLI query/status, eval report vs frozen benchmark (incl. manual-vs-packet baseline subsample) | Sonnet builder; **Opus retrieval-quality review mandatory** |
| CXI-3 | W2 | MCP wrapper over the CLI/packet function + conflict/stale-SHA behavior | Sonnet builder |
| CXI-4 | W3 | Private overlay (separate DB, memory-frontmatter chunker, opt-in) + privacy/leak suite | Sonnet builder; **Opus red-team mandatory merge gate** |
| CXI-5 | W4 | Semantic lane — ONLY if CXI-2 eval documents qualifying paraphrase misses | Entry-gated (CXI-R9) |
| CXI-6 | W5/W6 | Merge-time refresh automation, health, curator report, codex `cached_input_tokens` telemetry repair, A/B, preflight instruction, migration recommendation | Entry-gated on §15 success gates |

Trust boundaries stay isolated per docket §18: never combine `CLAUDE.md`, workflow
automation, private overlay, and retrieval core in one PR. Before every CXI PR: regenerate
the Active Build Map and re-check `DO_NOT_REBUILD.md`.

### Stop/go gates (docket §15 ratified, with two amendments)

- Ratified: ≥90% Recall@10 overall; ≥95% precision on A0/A1 governance answers; zero
  private leakage under adversarial tests; no correctness degradation; ≥30% median input
  reduction on repo-grounded sessions (or equivalent tool-call reduction); ≥50% fewer broad
  exploratory reads; packet ≤6k default / 8k hard; p50 <2s lexical/structured; stale SHA
  fail-visible.
- Amended (CXI-R6): ≥90% Recall@10 on the adjudication-replay family specifically.
- Amended (build-cost gate, guards docket Failure 5): if the CXI-1..3 core outgrows three
  focused builder lanes, STOP and re-adjudicate scope before continuing.

If token use does not improve at A/B, do not broaden the corpus — diagnose routing,
authority, chunking, and packing first (docket §15 closing law, ratified).

---

## 5. Collision audit record (per house law, taken 2026-07-18)

- **Open PRs:** #2957 (winner-autopsy case) only — no collision; no context-index lane in
  flight anywhere.
- **Name-adjacent research programs** — all market-context/NW domain, different meaning of
  "context", no scope overlap: `NW_CONTEXT_INTELLIGENCE_MASTERPLAN`,
  `NW_MACRO_CONTEXT_RAIL_MASTERPLAN`, `MACRO_SIGNALS_FX_CONTEXT_MASTERPLAN`,
  `NEURAL_WEB_MACRO_CONTEXT_INTEGRATION`. Closest neighbor
  `METABOLISM_V3_MEMORY_CONTEXT_BY_FABLE` governs metabolism's own lesson memory — the
  docket fences it as a reused scoped source (§3.1), not replaced.
- **DO_NOT_REBUILD:** no standing kill touches AI knowledge retrieval. The one adjacent law
  — verdict formats are inconsistent, do not build an auto-extractor — is honored verbatim
  by docket §3.2 ("no automatic extraction of verdicts from research prose").
- **Registry row appended by this PR** (CXI-R12): forbids the degenerate
  second-source-of-truth knowledge base class going forward.

---

## 6. Come-back

- Next action: dispatch CXI-0b benchmark builder, then CXI-1.
- Come-back checks: CXI-2 eval report (first Recall@10 by family, nulls printed); CXI-4
  red-team verdict; §15 A/B before any session-contract change.

---

## Amendment 1 (2026-07-18, operator order) — cross-repo corpus: Terminal + Mastermind

Operator directive: include the Terminal charting app and the Mastermind portfolio bot in
the Context Index. Censuses taken 2026-07-18 (sonnet lanes, both repos read-only):

- **Terminal** = `~/Documents/Cluade/charting-app` (395 tracked files, ~5.8 MiB text;
  TS/TSX-heavy Next.js app + Python ingest/signal_layer + JS quote-hub + SQL migration +
  versioned JSON contracts `mastermind.indicator/v1`, `backtest_result/v1`). LIVE SECRETS
  ON DISK: `/.env` (Supabase PAT + service-role key, Polygon key), `terminal/.env.local`
  (+DeepSeek key), replicated across ~12 `.claude/worktrees/*` copies. Heavy generated
  trees: `terminal/public/data` (~653 MiB), `node_modules`, `.next`.
- **Mastermind** = `~/Documents/Cluade/Mastermind` (606 tracked files; Python brain/
  portfolio/loop/control_plane + constitution stack CLAUDE.md/AGENTS.md/DOCTRINE.md/
  MAINTENANCE.md + research masterplans). LIVE SECRETS ON DISK: `.env` + `.env.bak-*`
  (7 OAuth tokens, Polygon/Tushare, auth tokens); actual position/NAV/fill/decision data
  throughout `data/` (7 paper books incl. a self-directed sleeve that may mirror real
  operator holdings); `vendor/` holds a 5.6 GiB macro-repo clone.

### Rulings

| # | Ruling |
|---|---|
| **CXI-R13** | **Multi-project corpus ratified.** Projects: `macro-dashboard`, `terminal`, `mastermind` — each with its own repo root (config-declared, env-overridable, host-portable). **One physical SQLite per project** (`shared.sqlite` for macro-dashboard, `terminal.sqlite`, `mastermind.sqlite`); a project's DB is opened only when that project is in query scope. An absent repo root degrades gracefully: the project is skipped with a health-report note, never a build failure (other hosts/CI won't have these checkouts). Cross-project ranking happens in CXI-2 fusion (per-DB ranked lists merged by RRF), not by cross-attached SQL. |
| **CXI-R14** | **External repos are private-visibility, fail-closed.** `terminal` and `mastermind` documents carry `visibility: private`; the default query scope is `macro-dashboard` only, and external projects join results only by explicit project opt-in (CXI-R10 double-gate discipline). Deny rules (on top of the standing set): both repos' `.env*` anywhere; `**/.claude/**`; Terminal `terminal/public/data/**`, `node_modules/**`, `.next/**`, `data/cache/**`, `web/**` mockups optional-in; Mastermind **`data/**` wholesale** (code/docs/config/sql ONLY — no selective allows in v1 even for "safe-looking" runtime JSON; positions, marks, chat history, key ledger, cost ledgers, backups all live there), `vendor/**` (it is the macro repo — already its own project; indexing it twice is the duplication failure), `catboost_info/**`, `*.parquet`, `*.db`, `*.sqlite`, `prototype/**`. Content tripwires (credential-shaped scan) apply to every external file exactly as to macro sources. Committed artifacts (benchmark rows/results) may reference external-repo PATHS, never external-repo content excerpts. |
| **CXI-R15** | **Authority is project-scoped; one new chunker.** Within its own project scope, each external repo's constitution stack (Terminal: README/HANDOFF/TERMINAL-ASSESSMENT; Mastermind: CLAUDE.md/AGENTS.md/DOCTRINE.md/MAINTENANCE.md) maps to A0-equivalent; contracts/config/SQL → A1; code → A2; docs/research → A3. Macro's CLAUDE.md remains the only A0 in `macro-dashboard` scope — no cross-project authority bleed. New `code_blocks` chunker for `.ts/.tsx/.js/.mjs/.sql/.sh/.toml`: deterministic heuristic boundaries (top-level export/function/class/CREATE-TABLE markers, size-capped windows with stable `#block-<n>` locators) — NO new parser dependencies; A2 discovery tier only, exact-source opening still mandatory before use. |
| **CXI-R16** | **Benchmark v1.2 extension rides with CXI-1b:** ≥15 cross-repo questions appended (CTX-082+), same golden-label bar (sonnet mines, Opus reviews, Fable ratifies). Priority families: cross-repo placement/adjudication-replay (the PRD-R1/UWP "which repo owns this" class — now answerable by retrieval), contract (`mastermind.indicator/v1`, `model_slice`, rotation handoff docs), location, gotcha (from their incident docs), ≥3 negative controls. Terminal/Mastermind rows are answerable only with their projects in scope — the eval must run those rows with opt-in enabled and report them as a separate family block. |
| **CXI-R17** | **Grading semantics fix pass (2026-07-18, benchmark README v1.4; one adjudicated regold).** (a) `required_status` binds ONLY to verdict-carrying registry sources among `required_sources` (`research/DO_NOT_REBUILD.md`, `config/ruling_graph.yml`, `config/compiled_kill_registry.yml`); all other required sources grade on top-10 presence alone. The v1.2 "for each required source" wording was unsatisfiable by construction for the 23 kill-class rows pairing an ACTIVE masterplan/engine file with the registry verdict row — same disease class as the v1.3 mode regold (unpassable-by-construction), and the registry row is the authority by the rows' own notes. (b) DO_NOT_REBUILD registry-row chunks take their status from the SECTION (§1→forbidden, §2→killed, §3→unknown, §4→deferred) — implements the CXI-R4/finding-11 gate the ingest docstring and tests already claimed; verdict-cell keyword matching had mislabeled §2 rows that quote §1 vocabulary (WA-R1 "STRUCK — positioning-fusion illegal" → `forbidden`, failing CTX-013 with the correct chunk at top rank). (c) `required_status: superseded` rows grade presence-only: one-status-per-chunk cannot honestly label a still-live ruling row whose sub-clause was struck (the PRD-R1 amendment lives inside the still-`forbidden` PRD-R2 row); supersession evidence = amended row text + superseding masterplan, both required in top-10. (d) One regold rides with the pass: CTX-054 `killed`→`forbidden` — its TI-R5 target row is FILED in §1 (design-level prohibition; the verdict cell's KILLED wording is vocabulary drift), and the section-authority sweep found no other section-vs-gold mismatch across the 25 kill-class rows. Genuine retrieval misses keep failing — the recall gates stay honest; no gate thresholds change. BENCHMARK_RESULTS.md becomes append-only (one section per eval run). |

### Build-plan impact

CXI-1 (in flight) is unchanged — its single-repo core is repo-root-parameterized by design.
**CXI-1b** (new, immediately after CXI-1): config `projects:` section + per-project DB
routing + `code_blocks` chunker + external-repo deny sets + graceful-absence health +
benchmark v1.2 + this amendment text. CXI-2 fusion gains per-project DB merge (design
already assumed multi-list RRF). Consumer wiring for Mastermind brain seats / Terminal
build sessions (both already run Claude on this host) is a CXI-6-class step behind the
same §15 gates.

---

## Amendment 2 (2026-07-20, operator order) — comprehension layer + discovery

Operator evidence: a fresh session was asked what the `china.html` track-record strip
("Beating CSI300 so far: 67% CI 63–70%, median excess +3.8%, n=660") means, and burned
~108k tokens on repo exploration, collision checks, and task setup for what is a lookup.
Root causes, both structural: (a) no session is told the Context Index exists — the CLI
shipped in CXI-2 but discovery is zero; (b) the corpus has no layer answering "what does
this user-facing stat MEAN" — the answer lives split across a template
(`china.html.j2:3287`) and an engine grader (`china_standout_track.py:_wilson_ci`/
`hit_vs_csi300`) with no curated entry for either humans or retrieval to hit.

### Rulings

| # | Ruling |
|---|---|
| **CXI-R18** | **Comprehension is a first-class question family; the site-semantics glossary layer is chartered.** `docs/site_semantics/<page>.md` — one curated entry per user-facing stat/panel: plain-word meaning, computed-by (file + symbol references, never line numbers), universe/window, threshold or CI method, and the design-doctrine "so what" line. Authority A3 (derived interpretation); every entry MUST cite its computing source; a drift test asserts referenced files and symbols exist (full hash-pinning deferred to the curator wave). This is documentation of the product, NOT a second source of truth (CXI-R12 untouched): when glossary and code disagree, code wins and the entry is a bug. The benchmark gains a `comprehension` family seeded with real operator questions — the CSI300 question verbatim is row 1 — and future operator questions are mined into it continuously (the benchmark was designed to grow from real sessions). Bilingual bodies optional in v1; entry titles EN. |
| **CXI-R19** | **Advisory discovery pointer permitted now; mandatory preflight stays gated.** A ≤4-line advisory in `CLAUDE.md` telling sessions the index exists and to TRY it for lookup/comprehension/collision questions before broad exploration is authorized immediately — the tool cannot earn usage evidence if no session knows it exists, and the pointer's worst case is one ~1s CLI call returning a cited packet. The docket §12 session operating contract (mandatory preflight, packet discipline, knowledge-candidate emission) remains gated on the §15 A/B success gates, unchanged. The pointer must be marked advisory and must not claim reliability the eval numbers don't support. |
| **CXI-R20** | **"Ask the site" direction noted for a later wave.** The Brain gateway chat (dashboard/Terminal, W6a) may eventually wire `context_search` as a context-only, citation-bearing tool so operator comprehension questions are answered by the Fast tier + retrieval instead of a full Claude Code session. Compliant with CXI-R2 (retrieval output is data, never authority). Requires CXI-3 tool surface; not built in this pass. |
| **CXI-R21** | **Comprehension rows grade on the glossary entry.** As authored, CTX-097..104 required the glossary page AND the computing engine file jointly in top-10 — the CXI-R17 defect class again: the glossary entry alone answers a comprehension question (its Computed-by citation is the pointer; `context_open` follows it). Engine files demoted to acceptable. Post-regold run v5: comprehension 8/8. Standing rule for future comprehension rows: required = the curated entry; acceptable = its cited sources. |
| **CXI-R22** | **No-answer floor verdict — honest null, next mechanism named.** A fused-score floor cannot separate negative controls from real queries at this corpus state (score ranges overlap; a distinctive-term rule false-nulled real code queries and was reverted). The floor ships at 0.010 (degenerate-empties only). Negative controls stay 0/10 and the gate stays red until either an IDF-rarity term rule (deterministic, preferred first) or the CXI-R9-gated semantic lane addresses it — this documented miss class is admissible entry evidence for CXI-W4. Threshold-tuning re-attempts without a new mechanism are rejected. |
| **CXI-R23** | **Audience fence (operator ruling 2026-07-20).** The operator, informed that the public repo exposes `engine/` source, `research/`, and the site-semantics glossary (the github.io mirror and keyless raw.githubusercontent live-quotes depend on repo visibility), ruled **keep public — accepted cost**, extending the MNZ "mirror stays (accepted leak)" posture to source. The standing fence that survives this acceptance: **no PUBLIC-FACING surface may ever serve repo-internals retrieval** — the public/subscriber Brain chat (and any future public endpoint) must NOT be wired to `context_search`, the glossary, engine code, or research docs. Public-audience explanations come only from what the site itself ships (Tier-2 receipts, on-page help, site copy) or a separately curated public FAQ authored under DESIGN_DOCTRINE vocabulary rules. The CXI-R20 wiring is therefore OPERATOR/ADMIN-audience only unless a future explicit operator ruling says otherwise. Registry row appended (§1) making violations summary-rejectable. |
| **CXI-R23a** | **Operator carve-out (operator order 2026-07-20).** The CXI-R23 fence gains ONE exception: the Brain gateway may serve repo-internals retrieval (`context_search`/`context_open`, shared plane only) to sessions whose **server-verified** account email (Supabase `/auth/v1/user` — never a client-supplied field, header, or proxy hint) matches the operator allowlist. The allowlist lives ONLY in the `BRAIN_INTERNALS_ALLOWLIST` env var on the serving host — never committed anywhere in this public repo (the list itself is an attack map). Default empty = fence holds for everyone. For allowlisted sessions only, the system prompt's proprietary-methodology refusal clause is swapped for an operator-internals clause; retrieved content remains data-not-instructions. Private planes (terminal/mastermind DBs, memory overlay) stay unreachable from the gateway regardless of allowlist. RISK FLAGGED: `demo@mastermind.test` is on the operator's requested list — if demo credentials are ever shared with prospects, whoever holds them gets internals; removal is one env edit. |

### Build-plan impact

**CXI-2x** (this pass, one PR): (a) retrieval-quality iteration — no-answer score floor
(negative controls are 0/10, the dominant gate drag; floor calibrated on the frozen set,
overfit risk accepted for v1 and printed), residual replay/governance miss diagnosis from
the v1.4 run-v2 failure list, eval production-parity for adjudication rows; (b) glossary
seed for the four highest-traffic pages (macro, us_stocks, china, china_stocks) including
the CSI300 strip entry; (c) benchmark v1.5 `comprehension` family; (d) re-eval appended as
run v3. **CLAUDE-pointer micro-PR** separately (hot file, cut fresh at merge time).
