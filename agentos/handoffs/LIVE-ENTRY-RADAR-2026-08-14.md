---
workstream: WS:LIVE-ENTRY-RADAR
session: claude/radar-w1-probe-bus
model: fable
ended_because: ci_handoff

mission: >
  W1 / PR-1 (operator CONTINUE directive 2026-08-14): build the Probe Universe funnel
  layers A-D and the frozen mastermind.entry_probe_nomination.v1 enlistment bus so Radar
  continuously maintains a broad Probe Set; prove a lobe nomination for a small cap
  outside the hot universe enters with provenance/freshness/eligibility intact and zero
  score authority. W1 only — no detectors, no Prophet edits, no rolling into W2.

state_before: >
  PR-0 merged as #5578 (merge 14fa4339a67); zero drift between the session-authored
  contract head and origin/main; no entry_radar paths existed; no PR/worktree/ABM
  collisions (release-radar codex worktrees are macro-release-intel, unrelated).

changed:
  - path: engine/entry_radar/ (contracts, universe, nomination_bus, spool, producers/{base,boards,baskets,live_flow,ipo,constituents})
    what: "The W1 package: frozen v1 nomination contract (13 §6.1 fields, PIT-enforced, bidirectional membership-expansion lock), funnel layers A-D (A = eligibility lens only; membership = B∪C∪D), bus with widened dedup identity, prospective spool (spool-before-consume), 7 producer adapters + Supabase watchlist interface + hot_tape tap."
  - path: scripts/entry_radar_universe.py
    what: "Nightly assembly entrypoint: live-dir ladder artifact (atomic rename, authority all-false), NYSE-session stamped, nightly gate exercised (durable-writes set empty by design until PR-5), non-zero exit when nothing publishes."
  - path: config/entry_radar.yml
    what: "Budget knobs (every key binds something — tested); Layer C thresholds; staleness windows."
  - path: tests/test_entry_radar_w1.py + tests/test_entry_radar_producers.py
    what: "93 tests incl. the named ACCEPTANCE tests, no-flattening bus tests, Layer-A outage retention, narrowing, spool/artifact agreement, laundering guards, missing≠negative, PIT, no-data/-writes, Prophet clean-diff guard."
  - path: research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md
    what: "§18 A3 (append-only): Track C census errata (us_standouts/setups writer + field names) + three ratified W1 deviations + known-inert-by-design notes."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W0 done (#5578); W1 in_progress with PR number."

prs: [5625]

verified:
  - claim: "Full W1 suites green under orchestrator re-run, not just builder claim."
    command: "python3 -m pytest tests/test_entry_radar_w1.py tests/test_entry_radar_producers.py -q"
    result: "93 passed"
  - claim: "The acceptance requirement holds end-to-end: an out-of-hot-universe small-cap lobe nomination enters the Probe Set with family/producer/observed_at/source_asof/provenance/freshness/eligibility intact and no score field."
    command: "python3 -m pytest tests/test_entry_radar_w1.py -k ACCEPTANCE -q"
    result: "2 passed (test_ACCEPTANCE_lobe_nominated_small_cap_enters_probe_set + layer-A-unknown variant)"
  - claim: "Prophet non-interference is mechanical and clean."
    command: "git diff --name-only origin/main...HEAD | grep -cE 'entry_signal|signal_gate|confluence_tiers|signal_quality|prophet_|washout_turn|mtf_upturn|stock_identity'"
    result: "0"
  - claim: "Adversarial review ran (opus) — 3 blockers found (bus flattening, Layer-A-as-door, retention key mismatch), each reproduced before fixing, all fixed + 8 improvements; 36 guard mutations, 0 survivors."
    command: "review transcript + git show 70c1bcfc07f0"
    result: "fix commit on branch; new tests named per finding"

unverified:
  - claim: "Production artifact shapes match adapters on tonight's real tape (adapters were verified against origin/main writer code, not live artifacts — sparse worktree)."
    what_would_verify: "First real assembly run on the VPS after merge; PR-4 wires the timer."

unresolved:
  - "layer_c.gap_abs_pct has no producer (entry_primitives gap detection stays DORMANT); honest empty lane."
  - "Supabase watchlist adapter is injected-client only; VPS wiring is PR-4."
  - "hot_tape live tap wiring (one line in the marketing lane) deliberately not done here; the tap function + outbox tailer exist."
  - "Episode continuity when a name exits and re-enters the Probe Set (a name whose only door closes now leaves, correctly) is PR-4/PR-5 territory."
  - "DURABLE_WRITES is empty by design; PR-5 populates it and the nightly gate then binds writes."

next_actions:
  - "W2 (PR-2): detector framework + G0 artifact consumption + fixtures F1-F6 (G0-VIS closed; A1 adapter obligations: verbatim family/subtype preservation, expert-family keys from emitter receipts, entry_event.v1 store)."
  - "At W2 start: re-check Terminal artifact freshness (feed_end hard gate, contract §3.2) and the production probe-set artifact's first real assembly."

do_not_redo:
  - "Do not re-run the W1 review cycle — findings and fixes are in commits 4c890ad0e688/26b115ffbd02/70c1bcfc07f0 with tests pinning each."
  - "Do not 'fix' the nomination dedup identity back to the (source_id, ticker, source_asof) triple — the widened identity is deliberate (no-flattening law outranks the PR-0 dedup wording; documented in contracts.Nomination.identity)."
  - "Do not make Layer A a membership door again — it is the eligibility lens; membership is B∪C∪D (test_layer_a_admits_nobody_on_its_own pins it)."

danger_areas:
  - "Sparse worktree: data/, site/ absent — all tests are synthetic-fixture; never add a test needing materialized data/."
  - "Protected paths unchanged (see verified clean-diff); engine/marketing/hot_tape.py deliberately untouched."
  - "The probe artifact is live-dir only; any data/ write before PR-5's reconciler violates the single-writer law."
---
