---
workstream: "WS:MARKET-OS"
session: "claude/marketontology-f04-x1-wti-live-trace-20260905 (worktree f04-x1-wti-live-trace)"
model: opus
ended_because: complete
mission: >
  F04-X1 Stage A. A researcher opens /ontology.html and receives one truthful
  current WTI Live Trace — the owner-observed path, which conditions hold, the
  first blocking leg, what changed, why it is dormant, evidence and clocks per
  leg, and one next research action — without manufacturing causality,
  confidence or a scenario forecast.
state_before: >
  main carried the nine-record F04 constitution but no /ontology.html and no
  /api/ontology/explorer/v1. SPEC_ONLY / X1_NOT_BUILT.
changed:
  - path: "engine/ontology_explorer.py"
    what: >
      New. Pure request-time composer of ontology_explorer_snapshot.v1 over
      knowledge/transmission/<chain>.yaml and data/transmission/chain_state.json
      (plus chain_episodes.jsonl when present). Never calls
      transmission_chains.run() — it defaults write=True and appends the episode
      ledger, so a GET would mutate an owner artifact. Deliberately does not call
      validate_chain() either: that is the nightly's gate and it RAISES, while a
      request-time surface must degrade with a legible typed state and must not
      change product semantics when the nightly's strictness moves.
  - path: "app/ontology_explorer.py"
    what: >
      New. GET /api/ontology/explorer/v1 behind require_user ->
      enforce_site_full(always=True). Private headers applied via a route class,
      because the outcomes most likely to leak (401/403 from a dependency, 422
      from validation) never reach the handler. Typed 503, no fallback.
  - path: "templates/ontology.html.j2, templates/ontology.{css,js}, site/*"
    what: >
      New. Public shell with zero current values plus the paired plain-copy
      assets. Signature is a severed rail in pure CSS — no canvas, no SVG, no
      graph library — which is what lets it turn vertical on a phone and satisfy
      "mobile path without graph-canvas JS" by construction.
  - path: "scripts/build_ontology_explorer.py"
    what: >
      New, feature-owned. Avoids contending for scripts/build_site.py, which an
      open sibling carrier owns.
  - path: "app/main.py"
    what: "One include_router hunk. No other change to any shared file."
verified:
  - claim: "69 tests pass; they were RED before the implementation existed."
    command: "python3 -m pytest tests/test_ontology_explorer_*.py -q"
    note: "RED checkpoint is commit be5555bb, titled 'no implementation yet'."
  - claim: "Paired plain-copy assets are byte-identical."
    command: "python3 -m scripts.check_template_site_sync"
  - claim: >
      Real router returns 200/401/403/503 with private,no-store +
      Vary:Authorization + nosniff + noindex,noarchive on EVERY outcome.
    command: "captured via fastapi TestClient against app/ontology_explorer.py"
  - claim: >
      Live chain composes to DORMANT with first blocking leg oil_shock by path
      order and contradiction downstream_true_without_upstream on
      duration_derate; what_changed is comparison_unavailable.
    command: "python3 -c 'from engine.ontology_explorer import compose_snapshot; compose_snapshot(Path(\".\"))'"
  - claim: >
      Rendered in a real browser at 1440/768/390, dark+light, EN+ZH: zero
      horizontal overflow, 44px touch targets, zero WCAG-AA text failures, zero
      refutation vocabulary and zero raw slugs on the live chain.
    command: "Browser pane against a local harness (removed before commit)"
do_not_redo:
  - >
    Do not render owner falsifier notes verbatim on a user surface. The live WTI
    chain's second note carries the word "falsified", the raw node id
    yield_rise, and no Chinese — three front-facing violations in one string.
    engine._screen_note withholds it and shows the structured condition instead.
  - >
    Do not use --ok / --act / --warn as TEXT colours. On the light canvas they
    measure 4.32:1 and 3.60:1. theme.css already ships --ink-* for text; the
    house form is var(--ink-act, var(--act)).
  - >
    Do not treat an unparseable build stamp as age zero. `built` is
    "YYYY-MM-DD HH:MM UTC", not ISO; the silent fallback rendered as "built just
    now".
  - >
    Do not re-litigate K1. Sol ruled at 1788593425.474829; the decisive fact is
    that txi.chain_state is an excluded_derived_head in
    contracts/evidence_foundation/vocabulary.v1.json and a dormant chain has no
    eligible txi.episode_transition. The broader claim that K1 requires
    fabrication or has no possible producers was WRONG and is withdrawn.
  - >
    The carrier's nav collision claim is false. Neither #6828 nor #6834 touches
    templates/_navlinks.html.j2. The real four-way contention is
    .github/ci/legacy-jobs.yml.
danger_areas:
  - >
    transmission_chains.run() defaults write=True and appends
    data/transmission/chain_episodes.jsonl. Any request-time consumer must read
    the artifacts directly. A test monkeypatches run() to fail loudly.
  - >
    The mid-read digest re-verification cannot catch a source rewritten just
    BEFORE its own read (that read returns the newer generation and digests stay
    stable). The revision coherence check is what closes that window; neither
    check is redundant.
  - >
    site/ontology.html is generated. Editing it directly drifts it from the
    template; rebuild with python3 -m scripts.build_ontology_explorer.
unverified:
  - claim: "The route serves a real entitled user in production."
    what_would_verify: >
      A real Supabase session holding site_full against the deployed app,
      reading /api/ontology/explorer/v1 and rendering the trace. The local
      harness OVERRODE the entitlement dependency, so authentication itself is
      the one leg of the journey this session did not exercise. Status codes,
      headers and bodies were captured from the real router.
  - claim: "The public shell behaves correctly once cached by the CDN."
    what_would_verify: >
      A deployed read of /ontology.html plus its paired assets, confirming the
      shell is cacheable while every API outcome stays private,no-store.
  - claim: "The page is discoverable."
    what_would_verify: >
      Stage B: build registration, a nav entry, and a page-registry row. Today
      /ontology.html is reachable by direct URL only.
unresolved:
  - >
    Whether the nav entry belongs to the authenticated family (_site_nav) or the
    anonymous family (_public_nav). The page is public but its payload is paid,
    so it sits across the two families the doctrine separates. Deliberately not
    decided here: both nav templates are held by open sibling carriers
    (#6828 owns _public_nav.html.j2) and this branch touches neither.
  - >
    Whether other transmission chains should get the same surface. The composer
    is chain-generic and the route takes a `chain` parameter, but only the
    default chain has been read end to end.
next_actions:
  - >
    Sol acceptance of this Draft PR. It is PARTIAL / BUILT_NOT_PROVEN by
    construction: not Ready, not merged, not deployed.
  - >
    Return the Stage B integration-hunk packet to F00: register
    scripts/build_ontology_explorer.py in the site build, add the page-registry
    row, add the four test files to CI selection, and add the nav entry once
    #6828/#6834 reconcile.
  - >
    Prove production: a real authenticated read with a real site_full
    entitlement, then observe a correction/failure transition on the deployed
    surface.
---

## Narrative

The part worth carrying forward is not the feature; it is that four defects
survived a careful reading of my own code and were caught only by running it.

A build stamp that would not parse became an age of ZERO — which renders as
"built just now", the most reassuring possible reading of a value the code had
failed to understand. A falsifier note copied straight out of an owner file put
banned refutation vocabulary, a raw node id, and untranslated English onto a
bilingual page in one string. Two status colours that are correct as fills
failed as text on the light canvas at 4.32:1 and 3.60:1. And the terminal
station of the rail claimed a confirmed outbound link that does not exist,
invisibly, because CSS hides that connector.

Each one produced a page that looked right. What caught them was measuring:
parsing the real stamp, scanning the real knowledge file, computing contrast
against the actually-painted ancestor, and reading the DOM rather than the
screenshot. Every one is now pinned by a test, and the vocabulary screen runs
against the live chain rather than a fixture — because a fixture I wrote would
have been clean.
