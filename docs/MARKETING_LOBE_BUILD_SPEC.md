# Marketing Lobe — Build Specification (frozen contract)

Internal build spec for the Marketing lobe (Growth OS substrate + admin surface + NW registration).
This is the **frozen contract**: the engine produces exactly the `marketing_state.json` shape defined
in §3, and the admin renders exactly that shape. Do not invent alternate field names.

Companion docs:
- `research/NEURAL_WEB_AUTONOMOUS_MARKETING_LOBE_GRANDMASTER_PLAN_FOR_FABLE.md` (architecture docket)
- `research/MARKETING_LOBE_GUERRILLA_GROWTH_AND_OPERATIONS_BY_FABLE.md` (strategy/operations doctrine)

## 0. Invariants (house law)

- **Deterministic v1.** The engine makes NO LLM calls at build time. Opus/Sonnet/Haiku "directors/workers"
  are roles described in config/state, not invoked here. Agent actuation is a later wave. This keeps the
  lobe cheap, render-safe, and fully testable.
- **Display tier, off the scored path.** `tier: display`, `horizon_role: context`. The lobe never
  originates a market signal/score/escalation and never writes to any Article-2 scored surface.
- **Never-raise.** Governor + every builder is fail-soft: log a warning, write best-effort, never abort nightly.
- **Envelope-stamped.** Every written JSON artifact carries the 5 sibling envelope keys via
  `engine.neuralweb.envelope.stamp(payload, artifact_id=...)`.
- **Admin reads, never writes.** Panels are `panel(root=None) -> dict`, fail-soft, read committed artifacts only.
- **Self-improvement ≠ self-concealment.** Ledgers are append-only; losing experiments/corrections are retained.

## 1. File layout

### Engine domain package — `engine/marketing/`
- `__init__.py` — exports `build_state`.
- `charter.py` — CMO mandate constants (category/promise/proof/icp/first_paid_job) + lobe charter text.
- `authority.py` — `GrowthAuthority` (G0..G7) enum with `.level`, `.name`, `.desc`; `LADDER` list; helpers
  `can_earn(record)->bool`, `should_narrow(signals)->bool` (pure predicates over dicts).
- `departments.py` — `Department` dataclass + `DEPARTMENT_CHARTERS` (the 10 depts as data, seeded/overridable
  from `config/marketing.yml`) + `Scorecard` dataclass + `registry(cfg)->list[Department]`.
- `opportunity_bus.py` — `Opportunity` dataclass + `score(opp)->float` (expected_value × originality ×
  freshness/half-life decay) + `half_life_class(source_type)->str`.
- `campaign_compiler.py` — `compile(opportunity, accounts)->Campaign` producing per-channel/per-account
  variant plan; `distinctness(variants)->{max_similarity,flags}` (token-Jaccard over variant text; flags any
  pair above 0.7). Pure functions.
- `provenance.py` — `MODES = ("neural_web","marketing_original","hybrid")`; `SourcePacket` dataclass; validator.
- `claims.py` — `ClaimPassport` dataclass + proof-graph link helpers + `summarize(claims)->{total,open,resolved}`.
- `publication.py` — `DeskAccount` dataclass; `desk_network(cfg)->dict`; `PublicationReceipt` dataclass;
  `CorrectionBus` (given a changed claim id, return derivative asset ids).
- `economics.py` — `retained_contribution(cohort)->float` implementing the docket formula; `BudgetAllocator`
  (allocate an envelope across departments by scorecard); `cohort_summary(cohorts)->dict`.
- `experiments.py` — `Experiment` dataclass (hypothesis/unit/holdout/primary_metric/guardrails/start_stop/result);
  `TRIAL_VARIANTS = ["7_trading_days","14_calendar_days","value_moment_limited"]`.
- `events.py` — `GROWTH_EVENTS` (the full instrumented event-name taxonomy from docket §12.1.A); `spine()->dict`.
- `cmo.py` — the self-improving CMO: `portfolio(departments)->dict` (allocation + ranking by scorecard),
  `department_formation_gate(queue)->dict`, `improvement_loop_state(...)->dict`,
  `self_deception_checks()->list[{name,status,note}]`, `org_simulator(scenario)->dict` (deterministic what-if).
- `ledgers.py` — tiny append-only JSONL helpers: `read_jsonl(path)->list`, `append_jsonl(path,obj)`,
  `tail(path,n)->list`. Used for the seed ledgers.
- `state.py` — `build_state(root=None, cfg=None)->dict`: assembles the FULL frozen `marketing_state` snapshot
  (§3) deterministically from config + ledgers. This is the single source of truth for the shape.

### NW governor — `engine/neuralweb/marketing_governor.py`
- `build_and_write(root=None)->dict`: calls `engine.marketing.state.build_state`, stamps envelope, writes:
  - `data/neuralweb/marketing_state.json` (schema `marketing.state/v1`, tier display)
  - `site/neuralwebdata/marketing_lobe.json` (schema `marketing.lobe/v1`, public-safe subset — §4)
  Never-raise. Runnable as `python -m engine.neuralweb.marketing_governor`.

### Orchestrator script — `scripts/build_marketing.py`
- Thin: `python -m scripts.build_marketing` → calls `marketing_governor.build_and_write()`; prints a one-line
  summary. (Mirrors the prophet builder shape; no R2 needed v1.)

### Contracts — `contracts/` (JSON Schema draft-07, 10 files)
`marketing_opportunity.schema.json`, `marketing_source_packet.schema.json`, `marketing_claim_passport.schema.json`,
`marketing_campaign.schema.json`, `marketing_content_asset.schema.json`, `marketing_publication_receipt.schema.json`,
`marketing_growth_event.schema.json`, `marketing_experiment.schema.json`, `marketing_department_change.schema.json`,
`marketing_correction.schema.json`. Fields per docket §10.2/§10.1 contracts. Each has `$schema`, `$id`, `title`,
`type:"object"`, `properties`, `required` (the identifying + provenance fields).

### Config — `config/marketing.yml`
Drives the governor. Shape in §5.

### Seed data — `data/marketing/`
Append-only JSONL ledgers, each seeded with 1–3 synthetic **shadow-mode** rows so the pipeline demonstrably
runs end to end (Wave-1 acceptance): `opportunities.jsonl`, `campaigns.jsonl`, `publications.jsonl`,
`growth_events.jsonl`, `experiments.jsonl`, `department_changes.jsonl`, `corrections.jsonl`, `claims.jsonl`.
Seed rows must be clearly synthetic (`"mode":"shadow"`, ids prefixed `seed-`).

### Seed artifacts (committed so admin renders day 0)
`data/neuralweb/marketing_state.json` and `site/neuralwebdata/marketing_lobe.json` — produced by running the
governor once and committing its output.

### Admin — `admin/marketing.py`
Panel module (fail-soft, read-only). Functions returning dicts (all reading `data/neuralweb/marketing_state.json`):
- `overview(root=None)->dict` — the CMO office view.
- `departments(root=None)->dict` — `{ok, departments:[...], authority_ladder:[...]}`.
- `channels(root=None)->dict` — `{ok, desk_network, publications, corrections}`.
- `campaigns(root=None)->dict` — `{ok, opportunities, campaigns, pipeline}`.
- `experiments(root=None)->dict` — `{ok, experiments, trial_variants, north_star}`.
- `lobes(root=None)->dict` — `{ok, engines_by_department, provenance, growth_events}`.
- `settings(root=None)->dict` — echo of `config/marketing.yml` top-level knobs.
All read the single state file + config; none read secrets. Every function returns `{"ok":True, ...}` or
`{"ok":False,"error":...}`.

### Admin server — `admin/server.py`
- Add `marketing` to the `from . import (...)` block.
- GET routes (in `do_GET`, near the prophet route ~line 377):
  `/api/marketing/overview`, `/api/marketing/departments`, `/api/marketing/channels`,
  `/api/marketing/campaigns`, `/api/marketing/experiments`, `/api/marketing/lobes`.
  Each → `self._json(marketing.<fn>())`.
- POST route `/api/marketing/settings` (in `do_POST`, near prophet ~line 569) with a `_MARKETING_SETTINGS_SPEC`
  + `validate_marketing_setting(key,value)` mirroring `validate_prophet_setting`. Settings knobs:
  `trial_variant` (enum of TRIAL_VARIANTS), `desk_network_stage` (enum "A"/"B"/"C"),
  `paid_enabled` (bool, default false), `auditor_strict` (bool, default true). (Writes go through config_store
  like prophet — but if config_store can't map `config/marketing.yml`, store under a `marketing:` block in the
  same config the store already manages; if not feasible, make settings **read-only echo** and skip POST. Prefer
  read-only echo if config_store integration is non-trivial — do not break the store.)

### Admin UI — `admin/static/app.js`
- Add 6 `ICONS` entries: `marketing_overview, marketing_departments, marketing_channels, marketing_campaigns,
  marketing_experiments, marketing_lobes` (distinct SVG glyphs; megaphone / org-tree / broadcast / rocket /
  flask / brain-grid).
- Add a NAV group after "Neural Web": `{ label: "Marketing", items: [["marketing_overview","CMO Office"],
  ["marketing_departments","Departments"],["marketing_campaigns","Campaigns"],["marketing_channels","Channels & Desks"],
  ["marketing_experiments","Experiments"],["marketing_lobes","Engines"]] }`.
- Add `RENDER.marketing_overview/…/marketing_lobes` async functions using the existing design primitives:
  `card()`, `meter()`, `.section`, `.grid`, `.kv`, `.statpill s-ok|s-warn|s-bad|s-mut`, `.note muted`, `.sub`,
  `.mono`, tables, `nwEmpty()`. Beautiful, information-dense, honest "accruing/chartered/shadow" states when
  values are null. Match the Observatory aesthetic (dark, indigo→cyan accent).

### Registration
- `config/synapse.yml` — 2 artifact entries (§6).
- `docs/SIGNAL_BUS.md` — regenerate: `python -m scripts.gen_signal_bus_doc`.
- `tests/test_signal_bus_doc.py` — bump the `len(artifact_ids) ==` pin by +2 and append a history note line.
- `config/lobe_charters.yml` — 2 charter entries, `tier: display`, **string-form** `fitness_sensors:
  [liveness, freshness_sla]` (string-form ⇒ NO metabolism roster slot ⇒ no `metabolism_budget.yml` edit,
  no operator cap-raise needed), `owner_program: marketing`.
- `admin/nw_lobe_descriptions.py` — add a one-line description for each of the 2 lobe ids.
- `config/dag.yml` — declare the governor step under the daily engine job.
- `.github/workflows/daily.yml` — add a `continue-on-error` step running the governor AFTER build_site, with
  explicit `git add data/neuralweb/marketing_state.json site/neuralwebdata/marketing_lobe.json`.

### Tests
- `tests/test_marketing_engine.py` — asserts: state builds without error; 10 departments chartered with required
  charter fields; authority ladder has G0..G7; opportunity scoring monotonic in expected_value; campaign
  distinctness flags identical variants and passes distinct ones; economics formula subtracts all cost terms;
  self-deception checks all present; growth-event taxonomy non-empty; governor `build_and_write` writes both
  artifacts with envelope keys; seed ledgers round-trip.
- `tests/test_admin_marketing.py` — each panel returns `ok:True` with the seeded artifact; fail-soft returns
  `ok:False`/empty on a missing-artifact fixture root (never raises).

## 2. Department roster (the 10, chartered now; see docket §7 and strategy §8)
`office_cmo` (Fable), `growth_os` (COO), `intelligence` (Intelligence Dir), `products` (Product Growth Dir),
`studio` (Creative Dir), `distribution` (Distribution Dir), `lifecycle` (Revenue Dir), `ecosystem` (Ecosystem Dir),
`growth_science` (Growth Science Dir), `trust_office` (Independent Auditor). Each with: id, name, director_model
(`fable` for office_cmo, `opus` for the rest), primary_outcome, non_goals[], engines[], authority_level (seed G1–G2),
lifecycle_state (`chartered` seed; `growth_os` seeded `building`), budget{envelope_usd:0,spent_usd:0}, model_mix,
clock{cadence,last_review:null,next_review}, retirement_test, scorecard{primary_metric, leading[], trust_health:
"clean", experiment_velocity:0, learning_quality:"seeding", authority_level}, wave.

## 3. FROZEN `data/neuralweb/marketing_state.json` shape (`marketing.state/v1`)
```jsonc
{
  "schema_version": 1, "produced_by": "...", "produced_at": "...", "inputs_hash": "sha256:...", "tier": "display",
  "schema": "marketing.state/v1", "as_of": "YYYY-MM-DD",
  "lobe": { "id":"marketing","name":"Marketing","lifecycle_state":"chartered","authority_level":"G2",
            "mandate": {"category","promise","proof","icp","first_paid_job"} },
  "north_star": {"metric":"...","value":null,"state":"accruing","note":"..."},
  "cmo": {"director":"Fable","portfolio":{"allocations":[{"department":id,"weight":0.0,"rank":n}],"total_envelope_usd":0},
          "opportunity_queue_depth":n,
          "self_improvement":{"loop_state":"observing","open_hypotheses":[{id,text,status}],"last_review":null,"next_review":"..."},
          "guardrails":{"self_deception_checks":[{name,status,note}]}},
  "departments": [ /* §2 department objects */ ],
  "authority_ladder": [ {"level":"G0","name":"Observe","desc":"..."}, ... G7 ],
  "desk_network": {"stage":"A","actuation":{"path":"human_in_loop","api_eligible":false,"control_loop":"drafted"},
    "distinctness":{"max_similarity":0.0,"flags":0},
    "accounts":[ {"id","handle":null,"kind":"branded|generic","beat","voice","corpus","stage":"A","status":"warming",
                  "authority":"G1","health":{"warnings":0,"followers":null,"engagement":null}} ] },
  "pipeline": {
    "opportunities":{"open":n,"scored":n,"newest":[{id,problem_or_desire,expected_value,score,half_life_class,status}]},
    "campaigns":{"active":n,"shadow":n,"newest":[{id,objective,audience,promise,channels,authority_level,status}]},
    "publications":{"total":n,"receipts":n,"corrections":n,"newest":[{id,channel,account,status,published_at}]},
    "experiments":{"running":n,"newest":[{id,hypothesis,primary_metric,status}]},
    "growth_events":{"instrumented":[...names...],"observed":n} },
  "provenance": {"modes":["neural_web","marketing_original","hybrid"],
                 "claims":{"total":n,"open":n,"resolved":n}},
  "economics": {"formula":"retained contribution = recognized revenue - fees - refunds - payouts - paid media - inference - data/delivery - support",
                "cohorts":[], "budget_allocator":{"method":"scorecard-weighted","total_envelope_usd":0,"allocations":[]}},
  "channels_priority": {"tier1":[...],"tier2":[...],"tier3":[...],"tier4":[...]},
  "waves": [ {"id":"wave0","title":"Root charter & inventory","status":"active","goal":"..."}, ... wave7 ],
  "notes": ["deterministic v1 substrate; agent actuation staged", ...]
}
```
All counts derive from the seed ledgers so numbers are honest. Null/accruing where no data exists.

## 4. FROZEN `site/neuralwebdata/marketing_lobe.json` (`marketing.lobe/v1`) — PUBLIC-SAFE subset
Envelope keys + `schema:"marketing.lobe/v1"`, `as_of`, `lobe`(id/name/lifecycle_state/mandate),
`north_star`(state only, no dollar value), `departments`:[{id,name,lifecycle_state,wave}] (names + lifecycle only,
NO budgets), `waves`(id/title/status), `channels_priority`. NO credentials, NO budgets, NO internal scorecards,
NO desk-account handles.

## 5. `config/marketing.yml` shape
```yaml
positioning:
  category: "Accountable AI market intelligence"
  promise: "Know what changed, why it matters, and what to watch next."
  proof: "Every important conclusion carries evidence, invalidation, timestamp, and outcome history."
  icp: "Self-directed, research-intensive swing/position investors following 10–100 names."
  first_paid_job: "Continuously monitor what matters to my holdings/watchlist and tell me when the causal picture changes."
settings:
  trial_variant: "7_trading_days"      # or 14_calendar_days | value_moment_limited
  desk_network_stage: "A"               # A warm | B assisted | C autonomous
  paid_enabled: false
  auditor_strict: true
  north_star_window_days: 90
departments:                            # overrides/extends the coded DEPARTMENT_CHARTERS defaults
  growth_os: { lifecycle_state: building, authority_level: G2, budget_envelope_usd: 0 }
  # ... optional per-dept overrides ...
desk_network:
  stage: A
  accounts:
    - { id: flagship, kind: branded, beat: "What changed and why it matters", voice: "authoritative desk", corpus: full }
    - { id: receipts, kind: branded, beat: "Visual evidence + public report card", voice: "dry, receipts-forward", corpus: charts_claims }
    - { id: theme_desk, kind: branded, beat: "Rotating high-attention vertical", voice: "specialist", corpus: theme }
    - { id: research_a, kind: generic, beat: "Macro/rates/liquidity explainers", voice: "educational", corpus: macro }
    - { id: research_b, kind: generic, beat: "Single-stock why-is-it-moving fast desk", voice: "fast, reactive", corpus: why_moving }
    - { id: research_c, kind: generic, beat: "Charts + historical analogues", voice: "pattern/history", corpus: analogues }
```

## 6. `config/synapse.yml` entries (2)
```yaml
  marketing-state:
    path: data/neuralweb/marketing_state.json
    format: json
    producer: engine/neuralweb/marketing_governor.py
    known_extra_writers: []
    owner_program: marketing
    cadence: daily-engine
    storage: git
    asof_field: as_of
    freshness_sla_hours: 48
    schema: marketing.state/v1
    tier: display
    horizon_role: context
    weights: none
    scored_path_surfaces: []
    consumers: [admin/marketing.py]
    external_consumers: []
    notes: >
      Marketing lobe (sovereign business-growth lobe, off the scored path). Deterministic Growth-OS state
      snapshot: CMO portfolio, 10 department scorecards, growth-authority ladder, desk network, campaign/
      opportunity/publication/experiment pipeline, provenance & claims, economics, wave status. Display-only;
      originates no market signal. Consumed by the admin Marketing pages.
  marketing-lobe:
    path: site/neuralwebdata/marketing_lobe.json
    format: json
    producer: engine/neuralweb/marketing_governor.py
    known_extra_writers: []
    owner_program: marketing
    cadence: daily-engine
    storage: git
    asof_field: as_of
    freshness_sla_hours: 48
    schema: marketing.lobe/v1
    tier: display
    horizon_role: context
    weights: none
    scored_path_surfaces: []
    consumers: [site/committee.html]
    external_consumers: []
    notes: >
      Public-safe summary of the Marketing lobe for the Neural Web organization graph (no budgets, no
      credentials, no desk handles). Names, lifecycle states, wave status, positioning, channel priority only.
```
Then bump `tests/test_signal_bus_doc.py` pin +2 and regenerate `docs/SIGNAL_BUS.md`.
