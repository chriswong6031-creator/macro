---
workstream: WS:EVAL-OS-OUTPUT-HEALTH
session: claude/eval-os-t4-output-health (COO Fable lane; commissioned by Sol handoff + CEO admin amendment mid-session)
model: fable
ended_because: complete

mission: >
  Build T4: the per-output health contract over the T1 engine registry — four states plus a
  separate could_not_look assessment, reader-side evidence sovereign over producer-side,
  dependency-bound honesty, lawful time bases, nothing committed — and (CEO amendment) the
  read-only admin Intelligence OS surface exposing the derived T1+T4 estate. Own to merge +
  live verification.

state_before: >
  T1 live and trustworthy (378 engines, derived on demand); W3 output_class 107/109 merged
  22bd3fae4cff (2 deliberate nulls: cortex two-species, options_structure unbuilt). No
  output-level health layer existed: producer green / mtime fresh / workflow green were the
  only observable proxies, and every stale-content incident (Jul-31→Aug-6 re-bake freeze,
  Prophet candidates freeze) had to be discovered by a human or a purpose-built sentinel.

changed:
  - path: engine/output_health.py
    what: "NEW pure resolver, schema mastermind.output_health.v1: unit (engine_id, artifact_id); state healthy/degraded/stale/unavailable/null + assessment_status complete/partial/could_not_look + decided_by plane; precedence blindness-first then missing>required-missing>stale>required-stale>semantic-degraded>required-degraded>optional-negative>healthy(complete-only); reader content-clock evidence outranks producer/transport both directions; staleness_from honored; promised-asof-field-absent refuses silent fallback; date-only watermarks resolve fresh only under the conservative end-of-date reading else date_only_calendar_unknown; dependency_bound exact only for single-output producers; self-loops excluded; dependency cycles reported not recursed."
  - path: scripts/build_output_health.py
    what: "NEW CLI adapter: storage-aware presence ladder (filesystem -> git show HEAD:, reusing T1 read_tracked; batched ls-tree fast path), watermark read from the declared field only, evidence adapters (NW health per-lobe, Foresight cascade legs, provider_health diagnostics-only, sentinel staleness.json + R2 audit reader evidence), trust-mtime off by default (checkout mtimes are false-fresh), JSON to stdout, writes nothing."
  - path: engine/neuralweb/synapse.py
    what: "health_optional_upstreams validate-when-present rule (2n): entries must be existing artifact ids, inside the mechanically inferred direct upstream set, with notes; ZERO live entries shipped. Placeholder regex widened <[A-Z_]+> -> <[A-Za-z_]+> in step with the resolver (lowercase placeholder families are could_not_look, not unavailable)."
  - path: admin/intelligence_os.py
    what: "NEW read-only derived panel (CEO amendment, DEC:EVAL-OS-T4-ADMIN-SURFACE): panel() census + engines table, engine_detail() per-output records; in-memory mtime-keyed cache only; trust_mtime iff ADMIN_DEPLOYED=1; output_class only from the T1 overlay (null renders null, never guessed)."
  - path: admin/server.py
    what: "GET /api/intelligence_os + /api/intelligence_os/engine?id= dispatch entries."
  - path: admin/static/app.js
    what: "Intelligence OS page (census chips, chip-filtered engines table, #/engine/<id> drill-down with per-output state/assessment/decided_by/age-vs-SLA/reasons; lobe cross-links) + one Observatory header cross-link. index.html/styles.css as needed."
  - path: tests/test_output_health.py
    what: "53 tests: all 22 commissioned acceptance gates incl. three hand-verified mutation receipts (precedence rule removal, mtime-over-content inversion, could_not_look conversion — each fails a named test), plus property/edge suites; fixture-root only."
  - path: tests/test_admin_intelligence_os.py
    what: "CEO reflectivity gate (fixture add/remove appears/disappears with zero admin code edits), output_class-never-guessed, no-persisted-state, worst_state ordering, cache semantics."
  - path: .github/ci/legacy-jobs.yml
    what: "T4 + admin test steps APPENDED to the isolated intelligence-registry job (never ahead of the T1 guard); curated exclusive scope widened to the measured import closure (incl. lib/dataos/*, scripts/freshness_sentinel.py, app/mailer.py)."
  - path: agentos/workstreams/WS-EVAL-OS-OUTPUT-HEALTH.md
    what: "Workstream record (owns_paths, do_not_redo naming the five reused monitors, landmines)."
  - path: agentos/decisions/DEC-EVAL-OS-T4-ADMIN-SURFACE.md
    what: "The CEO amendment ruling: existing admin console, view-not-store, alternatives rejected."
  - path: research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md
    what: "T4 as-built amendment: unavailable vs could_not_look split; categorical display confidence; admin surface."

verified:
  - claim: "T4 + admin suites green on the branch tree."
    command: "python3 -m pytest tests/test_output_health.py tests/test_admin_intelligence_os.py -q"
    result: "79 passed (53 core + 3 perf/placeholder + 23 admin)."
  - claim: "T1 suites, synapse contract, admin smoke/server/ESLint all green; the one red in the wider battery (test_admin_neural_web::test_bus_graph_shape) is a sparse-worktree artifact — materializing data/neuralweb/confluence_graph.json from HEAD makes it pass; CI runs a full checkout."
    command: "python3 -m pytest tests/test_output_health.py tests/test_admin_intelligence_os.py tests/test_intelligence_registry.py tests/test_check_intelligence_registry.py tests/test_synapse_registry.py tests/test_admin_neural_web.py tests/test_admin_modules_smoke.py -q"
    result: "452 passed / 1 sparse-artifact fail, attributed with a reproduction."
  - claim: "All CI wiring validators green with the T4 steps appended after the T1 guard."
    command: "run_ci_pack --validate-only packs 0-11; check_ci_trigger_closure; check_workflow_yaml; check_house_law_registry; audit_unrun_tests; check_admin_js"
    result: "12/12 valid; closure OK (0 gaps); 86 workflows parse; 83 laws OK; unrun-tests clean; ESLint no-undef clean."
  - claim: "The three commissioned mutation gates bite (performed by hand, restored byte-identical)."
    command: "edit engine/output_health.py per gate; pytest; cmp/shasum restore"
    result: "precedence-rule removal, mtime-over-content inversion, could_not_look conversion — each fails its named test; independent reviewer re-performed gate 19 with shasum receipts."
  - claim: "CLI runtime on this sparse worktree cut 691.96s -> 78.39s (git subprocesses ~1144 -> 133) with byte-identical summary output."
    command: "time python3 scripts/build_output_health.py --summary --now 2026-08-14T00:00:00+00:00 (before/after batched ls-tree + cat-file --batch)"
    result: "8.8x; batched-vs-per-path verdict identity pinned by test_batched_head_reads_are_verdict_identical_to_the_per_path_ladder."
  - claim: "Placeholder-regex widening blast radius measured before commit: 2 artifact paths flip to placeholder handling, 0 producer existence-check changes."
    command: "static + dynamic diff over live synapse.yml (builder receipt in the PR thread)"
    result: "placeholder_path 26->28; no producer flips — the stop condition never triggered."
  - claim: "Adversarial review (opus): 3 BLOCKERs + 4 MAJORs, every one reproduced before fixing; fix wave + reader-negative/r2-primary carve-out landed with named pinning tests; 11 hand-performed mutations all bite; final suites green."
    command: "python3 -m pytest tests/test_output_health.py tests/test_admin_intelligence_os.py -q (post-fix tree)"
    result: "122 passed (98 core + 24 admin); 321 with the T1 suites; live distribution shifted only by removing false negatives (unavailable 134->92, nothing new entered healthy)."
  - claim: "Admin Intelligence OS page verified end-to-end on a local authed server: census chips, provenance line (nothing stored / write-time refused), blind badges (F5), chip filters, drill-down records, unknown-id refusal; /api/intelligence_os payload matches the CLI census; cache hit <1ms on second call."
    command: "python -m admin --port 8791; curl /api/intelligence_os + /api/intelligence_os/engine?id=...; browser screenshots + DOM row count"
    result: "60 rows page 1; first row = the (no engine cell) bucket showing 8 T1-excluded artifacts with a live '2 blind' badge; zero console errors; ESLint clean."
  - claim: "Real-tree acceptance census (sparse worktree, --now 2026-08-15T00:30Z): healthy 147 / degraded 4 / stale 39 / unavailable 92 / null 360; complete 207 / partial 202 / could_not_look 233; exact 230 / upper 412; reader-observed 0 on a checkout (deployed-plane evidence; carve-outs proven reachable via synthetic audit fixture)."
    command: "python3 scripts/build_output_health.py --now 2026-08-15T00:30:00+00:00"
    result: "Full distribution + reason histogram in the PR body; runtime ~80s after the batched-read fix (was 692s)."

unverified: []

next_actions:
  - "FILLED AT SHIP: merge + live verification receipts; T7 readiness recommendation."

unresolved:
  - "Registry curation debt SURFACED, deliberately not healed here: 30 artifacts promise an asof_field their content does not carry (site-foresight-cascade declares as_of, file has asof; NW health's _AS_OF_KEYS fallback masked all 30); ~80 storage:git artifacts absent from both worktree and HEAD (nightly-estate-only outputs declared git); 86 watermark_unreadable_format (parquet without envelope sidecars). Each is a per-record honest could_not_look/unavailable with a reason code until curated."
  - "Reader-plane observability is nearly nonexistent estate-wide: sentinel covers the Prophet index store; R2 audit anchors cover 6/21 R2-registered artifacts; 640/642 outputs have no independent reader-plane source. T4 makes the gap visible per record; closing it is future sentinel/audit scope — the sentinel must never import T4."
  - "Calendar semantics: 58 date-only asof fields resolve fresh only under the conservative reading; beyond-SLA date-only watermarks are date_only_calendar_unknown. If coverage matters, a validated freshness_calendar synapse field bound to existing calendar implementations is the follow-up — do not infer calendars from names."
  - "T7 consumes these records next (separately commissioned): scorecard rendering of display_confidence_state; the desk hit-rate metric-binding warning from the T1/W3 handoff still stands."

do_not_redo:
  - "Do not add a committed health artifact, a --check equality mode, or a second monitor — T4 is a derived view; the five existing health systems are evidence providers (WS record carries the full list)."
  - "Do not flatten unavailable and could_not_look — separate fields by design; every blind path must name a reason code."
  - "Do not generalize NW's weekend shortcut or _AS_OF_KEYS fallback estate-wide; do not silently substitute watermark fields."
  - "Do not treat provider-health rung failures as output failures — diagnostics only, contract-bound."
  - "Do not give the admin surface authority or persistence — view-not-store (DEC:EVAL-OS-T4-ADMIN-SURFACE); enforcement belongs to T12."

danger_areas:
  - "The intelligence-registry job's scope is exclusive: any new import in the T4/admin closure must be added to its paths or the manifest fails to load."
  - "trust_mtime: checkout mtimes are checkout-time (false-fresh); only the live estate (ADMIN_DEPLOYED=1 / --trust-mtime) may treat write time as evidence, and only under a write-time contract (asof_field null + SLA non-null)."
  - "The T1 AST meta-test freezes live-invoking call shapes — new tests touching the T1 builder must use fixture roots."

prs: []
decisions:
  - "DEC:EVAL-OS-T4-ADMIN-SURFACE"
---

## Cold-start orientation

Read the WS record first, then the PR body (census + receipts), then
`engine/output_health.py`'s docstring — the precedence and the time-basis law live there as
code-adjacent truth. The single most important structural fact: T4 is a DERIVED ON-DEMAND
VIEW joining T1 + synapse + the existing health evidence; nothing generated is committed, so
no nightly append or sibling synapse PR can red it, and no self-monitoring fixed point can
form. `could_not_look` is a first-class answer, never an embarrassment to hide: most of what
this wave produces is an honest map of what the estate cannot currently see.
