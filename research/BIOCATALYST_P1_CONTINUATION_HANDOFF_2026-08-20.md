# BioCatalyst P1 Continuation Handoff — the exact first implementation PR (P1-1)

- **Date:** 2026-08-20. Written by the P1-0 recharter session (`claude/biocatalyst-p1-recharter`).
- **Authority state:** P1-1 is **NOT yet commissioned.** Two gates precede any implementation session: (1) Sol ratifies the first-vertical revision and the named catalyst-calendar boundary evolution (`DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR`; architecture doc §11.1), and (2) Sol names the P1 workstream home (§11.2 — deliberately not minted by P1-0). Until both, this file is a frozen spec, not a start order.
- **Architecture source of truth:** `research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md` (esp. §0 gates, §6 spine, §9 experience, §10 slice). On any conflict, that document wins.

## The one PR

**P1-1: Catalyst Radar — Trial Milestones.** Source/read-adapter → temporal catalyst event → identity → bounded API → one useful Radar surface → evidence drill-down → entitled browser proof. Independently useful on its own; no calendars+dossiers+options+alerts mega-build.

**Naming law (from the red-teamed adjudication):** the source supplies registry primary/overall **completion dates** — sponsor-submitted, often `ESTIMATED` — which are NOT topline-readout announcement dates. The surface, rows, and API say "trial milestones"; the word "readout" may not appear front-facing except accompanied, in the same glance-tier line, by the registry-estimated nature of the date.

### MISSION
Ship the Catalyst Radar — Trial Milestones vertical over the existing BioCatalyst evidence plane: project the admitted CT.gov trial snapshots + record-history + change-tape into deterministic catalyst-event rows (§6 spine) and serve them through one entitled endpoint and the upgraded Milestones tab (§9), with evidence drill-down to stored source receipts. Event kinds: `{primary_completion, completion}`. Default horizon ≥365 days — measured on the live cohort 2026-08-20: `next_90d` = 0 rows (the P0 lawful-empty), `next_180d` = 1 row, `next_365d` = 3 rows (§9 falsification table); mind the milestones endpoint's whole-interval containment filter and generation-date anchor (`app/biocatalyst.py:2647`, `:2249`) when defining the radar's own horizon semantics.

### FROZEN SPEC (do not redesign)
1. **`engine/biocatalyst/catalyst_events.py`** (new, pure projection; no network, no new storage plane; reads the admitted generation artifacts exactly as existing `_read_bundle()` consumers do — request-local per the #6052 pattern, no process-lifetime cache). Emits per event: source-native id `nct:{NCT_ID}:{milestone_kind}`; scheduled date + native precision (month vs day, first-class field); `known_at` from the evidence-store watermark/generation chain; revision lineage (record-history versions + change-tape classification, predecessor pointers kept; first poll in an epoch = baseline, no change emitted); cancellation-class states from status transitions (terminated/withdrawn/suspended); issuer resolution via `engine/biocatalyst/sponsor_identity.py` **only for `review_state: reviewed_admitted` rows**, typed `unresolved_sponsor` otherwise, never fuzzy; intervention name as lexical label only (no asset id minted). Deterministic source facts only — **no probability, materiality, score, or rank anywhere** (also `DNR:KILL-PHASE3-START-WEIGHT`).
2. **`app/biocatalyst.py`**: one new entitled endpoint `GET /api/biocatalyst/v1/catalyst-radar` (site_full via `require_site_full_user`, same generation-read seam as `trials:screen`; params: horizon, pagination; typed states incl. `source_outage`, locked, valid-empty-with-reason; `Cache-Control: private, no-store` like siblings).
3. **`templates/biocatalyst.html.j2` / `templates/biocatalyst.js` / `templates/biocatalyst.css`**: Milestones tab graduates into "Catalyst Radar — Trial Milestones" per §9 — glance tier (trial short title · phase chip · issuer chip or unresolved · plain-word event kind · scheduled window with honest precision · days-to-event · date-moved chip when lineage exists · condition), expand tier (full revision lineage, known_at, sponsor line, dossier link, evidence drill-down to generation + record-history receipts). All §9 states reachable. EN/ZH; no translated text in `title=` attributes; no internal state names or raw slugs front-facing; falsifier/refutation language never front-facing.
4. **Tests**: projection determinism, precision handling, revision lineage + predecessor pointers, unresolved-issuer, cancelled-class, valid-empty reason, API contract + entitlement, plus the acceptance journey.

### OWNED FILES
`engine/biocatalyst/catalyst_events.py` (new), `app/biocatalyst.py`, `templates/biocatalyst.html.j2`, `templates/biocatalyst.js`, `templates/biocatalyst.css`, new test file(s), and — because `templates/biocatalyst.js`/`.css` are plain-copy paired assets — the byte-matching `site/biocatalyst.js`/`site/biocatalyst.css` in the same PR (`python -m scripts.check_template_site_sync --fix`). Nothing else. **Zero mutation of the frozen soak surface:** `config/biocatalyst_sources.yml`, `config/biocatalyst_launch_slo_manifest.yml`, cohort/allowlists, collector cadence, `engine/sector_intelligence/launch_slo_verifier.py`.

### NOT DONE UNLESS (the §0 gates of the architecture doc, restated — on any divergence §0 wins)
- Real entitled browser journey on the deployed production process shows Radar rows from the live public generation (served process/commit identity, route timings, no 524/5xx, unsigned 401 intact) — the #6090 receipt standard. A local or pre-deploy result is not acceptance. Verify `app/deploy/update.sh`'s restart regex actually covers every changed runtime file before calling the deploy done.
- **No score, probability, materiality, rank, or composite anywhere in payload or UI** — deterministic source facts only, `authority: facts_and_context_only`. This is the single most load-bearing BioCatalyst prohibition and is an acceptance gate, not a style note.
- Every §9 state typed and reachable; no generic unavailable state without a reason code.
- Evidence drill-down resolves to real stored receipts.
- New test suite actually RUNS in CI: check `config/unrun_test_baseline.json` (893 suites are grandfathered-dark; adding tests to an existing dark file does nothing); a new `engine/biocatalyst/` module must be declared in every curated `scope: exclusive` CI job whose closure reaches it or `contract-delta` reds the PR (see `biocatalyst-serving` job in `.github/ci/legacy-jobs.yml`).
- PR body: before/after screenshots of the entitled journey + row count + generation digest.
- Ship loop completed by the implementing session: commit → push → PR → merge-on-green armed → CI concluded → same-day squash-merge → live verification. One session owns all of it.

### Builder traps (from house memory — read before starting)
- Sparse worktrees omit `site/` from disk: opt in with `python3 scripts/worktree_sparse.py add site` BEFORE running the template-site sync, or the paired-copy check refuses.
- The BioCatalyst product truth plane is the VPS public generation (`BIOCATALYST_PUBLIC_ROOT`), NOT `data/clinicaltrials/trials.parquet` (ticker-keyed altdata, no milestone dates, look-ahead-selected pre-2019). Do not join the parquet into the radar.
- Entitled route latency is 4.5–7.9 s today (proven lawful). The radar endpoint must not worsen the per-request validation budget — reuse the #6052 request-local retention seam; do not reopen ContractRegistry/bootstrap (do_not_redo in the recovery closeout).
- `/live/*.json` cache-control and versioned-asset verification rules apply if any versioned asset is touched — verify the versioned URL, not just the bare one.

### RETURN (implementing session reports back)
STATUS / RESULT (PR number, merge SHA, live-proof receipt path) / EVIDENCE (the §0 gate artifacts) / GAPS / DEVIATIONS.

## Explicitly OUT of P1-1 (post-soak or Sol-gated; do not smuggle)
Cohort expansion beyond 4 NCTs; `biopharmcatalyst_jv_snapshot` runtime registration; Drugs@FDA/openFDA activation (rights review b4 owed); PDUFA tenant (needs Sol's §11.3 plane ruling); alerts; Neural Web synapse registration (one-line `tier: display` follow-up once the artifact stabilizes); Prophet anything; company dossier; cash/runway (needs Sol's §11.4 ownership ruling); any composite BioCatalyst score. Post-soak gate = soak close 2026-08-26T02:00:00Z **plus** the successor-registry/successor-launch-manifest transition per `research/BIOCATALYST_HANDOFF_TO_CODEX_2026-08-15.md` §Priority-0 — no bypass.
