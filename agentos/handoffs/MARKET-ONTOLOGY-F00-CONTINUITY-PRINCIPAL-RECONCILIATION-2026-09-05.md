---
workstream: WS:MARKET-OS
session: claude/marketontology-f00-principal-20260905
model: fable
ended_because: ci_handoff
mission: >
  Record, for a cold successor of the F00 full-site-restart integrator
  (operation marketontology-f00-full-site-restart-integrator-20260904-sol-001,
  Slack root C0BSBM78V1N/1788510607.305039, git carrier macro#6819), the seam map
  of where a user's research context is lost across the current Macro/Terminal
  estate, the Sol-corrected facts that supersede the first integration return,
  the two ruled shared-hunk outcomes (Help live path, F01 three-asset boundary),
  the open DECISION_REQUEST, and the exact next actions. Additive only; the
  earlier Sol handoff MARKET-ONTOLOGY-F00-META-CEO-CONTINUITY-PRODUCT-RESET-2026-09-05
  remains the program baseline.
state_before: >
  The F00 principal is Code session 5b29ad85-0490-42c8-b5e4-1e32b1922014
  (app-realm local_a43a5e87-f178-472b-bde0-c6f4bda22a1b, Slack seat Claude8),
  bound 2026-09-05 after the quarantined 1727abca principal. Help #6828 merged as
  8431aeafcc3929a0d25cacaebd83c0815adb79a4 and records #6864 as
  ab28de989ae1e63f2f96601eb8f6579fa1acb388, both under explicit one-PR Sol
  delegation. The five-part seam return (Slack 1788599499.371569 through
  1788599647.845789) was consumed by Sol 1788599922.022699 with corrections that
  this record adopts; the stale claims it replaces (F05 unbound, Terminal user
  state unverified, V-A frozen, V-B read-only, F02 pre-START, CI list as a queue)
  must not be re-asserted. The served public site was stale at main ≈ f8371aa4
  while GitHub main was ≥ 8431aeaf; a host-native read-only diagnostic child was
  requested by Sol (root C0BSBM78V1N/1788600409.396209) and had no receiver yet.
changed:
  - path: agentos/handoffs/MARKET-ONTOLOGY-F00-CONTINUITY-PRINCIPAL-RECONCILIATION-2026-09-05.md
    what: >
      New additive F00 principal handoff: six-seam context-loss map with evidence
      classes, corrected S3/S4/V-A/V-B facts, Help live-path before-state and
      acceptance readback, F01 three-asset boundary ruling, CI hunk disjointness,
      DECISION_REQUEST on MO-PAID-020 renderer/CIK-leg ownership, MO-DELTA-010
      reconciliation through #6792, ordered next actions and do-not-redo list.
  - path: agentos/discoveries/DSC-MARKET-ONTOLOGY-K1-VOCABULARY-EXCLUDES-TXI-CHAIN-STATE.md
    what: >
      New discovery: K1 vocabulary.v1 admits txi.episode_transition and excludes
      txi.chain_state, so current chain heads carry a typed K1 limitation; X1
      current-head exception is narrow.
  - path: agentos/discoveries/DSC-MARKET-ONTOLOGY-USER-STATE-STORE-IS-TERMINAL-WATCHLISTS.md
    what: >
      New discovery: user-scoped watchlists already live in Terminal
      lib/watchlists.ts + Supabase RLS tables, bound by Macro watchstore.js; S4 is
      owned, not empty.
  - path: agentos/discoveries/DSC-MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM.md
    what: >
      New discovery (Boundary 2, corrected under Sol ruling 1788654063.022769):
      on 2026-09-05 the VPS Caddy served only mastermind-x.com/www and dated
      readbacks gave .com 200 / .ai 525; the .ai result is a separate mapping on
      that evidence, uptime and .ai→.com binding not established.
prs: [6792, 6819, 6828, 6864, 6872, 6873, 6876, 6890]
verified:
  - claim: >
      RCTX-1 (same-document span → Ask → return) is BUILT in source on both
      canonical heads and therefore BUILT_NOT_PROVEN, not absent.
    command: >
      In charting-app: git fetch origin master; git cat-file -e
      e89ebda4:terminal/lib/companySourceContext.ts; git grep -l companySourceContext
      e89ebda4. In macro at 8431aeaf: grep -n company_source_span app/main.py
      engine/neuralweb/brain_gateway.py templates/mm_brain.js.
    result: >
      Terminal writer present at e89ebda4 with non-test importers
      terminal/components/fin/TranscriptSearchWorkspace.tsx and
      terminal/lib/mastermindBrain.ts; Macro BrainChatRequest.company_source_span
      (app/main.py:1164) → brain_gateway._resolve_company_source_attachment (:3493)
      → earnings_transcript_intake.resolve_company_source_span (:3518) at call sites
      :8569 and :9071; mm_brain.js hook :23/:36, wire site :2792;
      tests/test_company_source_span.py exists. Live reachability, real
      authenticated journey and telemetry remain unverified.
  - claim: >
      The three F01 presentation assets are paired plain-copy, byte-equal and
      presentation-only at #6873 head ba9e37db, and no open PR touches the access
      boundary files.
    command: >
      git fetch origin refs/pull/6873/head; for f in macro_suite.css
      macro_suite_boot.js macro_suite.js; do cmp <(git show ba9e37db:templates/$f)
      <(git show ba9e37db:site/$f); git show ba9e37db:templates/$f | grep -c -E
      'fetch\(|XMLHttpRequest|premiumdata|stockdata|\.json|http://'; done;
      gh pr list --state open --json number,files | jq for app/deploy/Caddyfile
      and config/site_access.yml.
    result: >
      Pairs byte-equal (32739 / 903 / 7484 bytes), 0 payload references each; no
      open PR carries Caddyfile or site_access.yml hunks (Help's are merged at
      8431aeaf). Ruling posted on Slack root C0BSBM78V1N/1788583938.803689 at
      1788601186.334209.
  - claim: >
      #6873's .github/ci/legacy-jobs.yml hunk is disjoint from every other open
      contender's hunk in that file.
    command: >
      git diff origin/main...ba9e37db -- .github/ci/legacy-jobs.yml (hunk header
      @@ -13797,+13808 +9) compared against the same diff for the heads of #6834,
      #6842, #6514, #6840, #6832, #6831, #6830, #6803, #6793, #6706.
    result: >
      #6873 adds one job block at base lines 13797–13808; the other ten edit
      3656–3690, 5016/9716, 726, 10104, 2264–2430, eight single lines 1139–12585,
      9550, 919, seven single lines 1586–12250 and 11703 respectively. No
      intersection, so no ordering constraint beyond re-fetching main before push
      and requiring the integrated YAML to parse.
  - claim: >
      The served public site lagged accepted main before the host diagnostic was
      requested, with Help absent on the live path.
    command: >
      curl -s https://www.<site>/index.html | git hash-object --stdin (and
      support.html, plans.html); git rev-parse "<commit>:site/<page>" for main
      commits 8431aeaf, 1454f06f, f8371aa4; curl -sI /help.html and /help.
    result: >
      At 09:20Z live index.html blob 14b8426477c7 = main 1454f06f; support.html
      edcd6a936b0a and plans.html fecd2b303576 = main f8371aa4; /help.html 404 from
      origin Caddy; /help 401; committed help.html blob at 8431aeaf is f7c67b2d0090.
      This proves a stale SERVED copy, not the failing host stage; Sol
      1788600354.288809 records the exact /opt/macro HEAD, updater version and lock
      state as UNKNOWN pending the host-native child.
  - claim: >
      User-scoped watchlist state is implemented in Terminal and bound by Macro
      watchstore.js (S4 correction).
    command: >
      See DSC:MARKET-ONTOLOGY-USER-STATE-STORE-IS-TERMINAL-WATCHLISTS falsifier
      (git cat-file -e e89ebda4:terminal/lib/watchlists.ts; git show
      e89ebda4:supabase/migrations/0001_init.sql | grep watchlists).
    result: >
      Files present; tables public.watchlists / public.watchlist_symbols with RLS
      enabled (0001_init.sql:97-99); owner scoping via .eq("user_id", userId)
      (watchlists.ts:106-109).
  - claim: >
      K1 vocabulary.v1 excludes txi.chain_state and admits txi.episode_transition.
    command: >
      python3 -c "import json;v=json.load(open('contracts/evidence_foundation/vocabulary.v1.json'));print('txi.chain_state' in v['excluded_derived_heads'],'txi.episode_transition' in v['owner_stores'])"
    result: >
      True True at origin/main a232b1743e54.
  - claim: >
      The production origin serves mastermind-x.com / www.mastermind-x.com and the
      Help publication blocker is host storage plus a stale checkout, not the
      updater's flock and not a site outage (Boundary 2 correction of the
      unverified cron claim recorded at Boundary 1).
    command: >
      HOST_DIAGNOSIS_RESULT 1788635437 on Slack root C0BSBM78V1N/1788600409.396209
      (accepted/closed by Sol 1788636103.500379); curl -sI on www.mastermind-x.com
      /, /help.html and on mastermindx.ai /.
    result: >
      Loaded Caddy hosts = .com/www only; /opt/macro available_bytes=0; updater
      failures are no-space; checkout HEAD 761a4df8 (108 behind); Help absent from
      /opt/macro/site and the served root; macro-update.service/.timer
      LoadState=not-found, no cron.d match; installed update.sh and Caddyfile
      byte-equal to the checkout. www 200 (TencentEdgeOne), /help.html 404,
      mastermindx.ai 525 (cloudflare) = separate unqualified mapping.
      DSC:MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM. Storage recovery is Sol's lane
      and was NOT_STARTED at record time.
  - claim: >
      F04 #6872 B-1/B-3 at head ba62f5a598ea: the app/deploy/update.sh
      restart-trigger hunk is admitted as path 25, the B-1 build_site.py anchor
      (after _tmark("biocatalyst") :7682) is accepted but the returned body would
      have silently skipped, B-3 is accepted, and #6872 × #6873 collide on the
      same four Caddyfile lines with no ordering dependency.
    command: >
      git fetch origin refs/pull/6872/head refs/pull/6873/head; git diff
      --name-only $(git merge-base ba62f5a5 origin/main) ba62f5a5 (35 paths);
      grep -n "def build_shell" scripts/build_ontology_explorer.py; git
      merge-tree --write-tree --name-only --messages ba62f5a5 b7d237f0.
    result: >
      build_shell(env: Environment, site: Path) -> None, so the proposed caller
      _render_ontology(config.ROOT) raises TypeError inside the additive
      try/except and the page is skipped without failing the build; corrected
      hunk (build_shell(env, site) + _tmark("ontology_explorer")) and a RED-first
      nightly-hook test were ruled owed at 1788633496.506309 on root
      1788584226.926809. B-3 = macro:ontology archetype instrument_analyzer after
      page_registry_overrides.yml :176 (archetype validator-known, 119 uses).
      merge-tree conflicts on app/deploy/Caddyfile (:344/:470/:514/:549, different
      insertion points) plus 13 site/macro_*.html (F01 render vs nightly);
      config/site_access.yml merges clean. Ruling: keep both, second to land
      re-applies its tokens; no serialization.
  - claim: >
      F01 #6873 Slot-2 hunks at head b7d237f067f2 are accepted: hub admission is
      the HubPage registration, the page registry is derived, the build_site hook
      and render dirty-scope entry pre-exist on main, and telemetry is none.
    command: >
      git diff --name-only $(git merge-base b7d237f0 origin/main) b7d237f0 (49
      paths: 15 source / 16 site / 18 evidence / 0 data); grep -n "HUB_PAGE =
      HubPage(" scripts/build_macro_suite_pages.py; git diff origin/main b7d237f0
      -- scripts/build_site.py; grep -n "site/\*.html" scripts/build_product_page_registry.py.
    result: >
      HubPage at scripts/build_macro_suite_pages.py:251; build_site.py identical
      to main (macro-suite hook :7700 and render.yml:152 pre-exist); registry
      derives from git ls-files site/*.html (build_product_page_registry.py:612);
      Caddy/site_access/boundary-test hunks identical to 8e08c27c (three exact
      asset paths after /markets.css). Ruling posted on root 1788583938.803689
      after 1788639616.516889; CI 33988162571 success; 0 reviews.
unverified:
  - claim: >
      The effective scheduler/activation path for /opt/macro. Dated evidence
      (2026-09-05 host diagnosis): /opt/macro available_bytes=0; checkout
      761a4df8, 108 commits behind then-current main; macro-update.service and
      macro-update.timer answered LoadState=not-found; no match in the bounded
      cron.d search. That narrows the search; it does not establish what last
      updated the checkout, so the "3-minute VPS pull" this repo's law assumes is
      unverified on this host.
    what_would_verify: >
      The storage-recovery lane's host report naming the unit, cron or manual
      procedure that last updated /opt/macro, with its last-run timestamp; until
      then a merged Caddy/site_access change has no proven activation path.
  - claim: >
      A canonical join ticker ↔ issuer_cik ↔ isin/cusip6 does not exist anywhere in
      the repository.
    what_would_verify: >
      A census of engine/capital_structure/* consumers and engine/options_hub.py
      identity inputs, plus grep for a shared resolver; S3 inspected neither the
      options key nor its consumer.
  - claim: >
      Correction identities (correction_version / correction_of from
      scripts/compile_capital_structure_events.py) propagate to any consumer view.
    what_would_verify: >
      Open the consumers of data written by that script and the ten replay/revision
      tests named by grep; assert typed correction states.
  - claim: >
      An in-flight nav→Help→destination/filter journey works once the host serves
      8431aeaf or later.
    what_would_verify: >
      After the host child result: same three body hashes moved to ≥8431aeaf blobs
      (help.html → f7c67b2d0090), /help → 301 → /help.html → 200 anonymous, then the
      12-shot browser matrix in the F00 help_ev manifest (EN/ZH × dark/light).
unresolved:
  - "DECISION_REQUEST (no build attached): who owns the ListingAlias→ListingKey renderer and the CIK-leg access named in MO-PAID-020. Until ruled, event→security continuation (F05+F06) is not a bounded vertical; it is not an F00 build."
  - "MO-DELTA-010 ('no rendered indicator library') is stale against source: config/market_reference.yml, scripts/build_market_reference.py, templates/reference.html.j2 exist and #6792 (DRAFT @7853ffea, MOR-1) owns that surface; the ledger row is reconciled through #6792's owner, never a second catalogue; presence is neither coverage nor PROVEN_LIVE."
  - "V-A (security → options continuation) is NOT frozen: F03 and F06 must first return the exact existing source→destination consumer, native identity tuple (possibly multi-field), parser/resolver and supported instance; the one-key-per-hop convention proposed in the seam return is withdrawn."
  - "V-B (RCTX-1 production proof) is proof-first but a real Ask turn is not read-only (chat/telemetry rows, model quota): the existing proof carrier, approved test identity, entitlement, isolated browser, persistence/cost and mutation gate must be recovered before any live turn; invalid-reference injection runs on the hermetic path unless a live test is explicitly authorized."
  - "F04 #6872 (head ba62f5a598ea at Boundary 2, DRAFT/HOLD, 35 paths) owes the corrected B-1 body, the RED-first nightly-hook test and a RESULT / HOLD-FOR-SOL; Stage B (site_access :107 two literals, Caddy :344/:470/:514/:549, legacy-jobs additive job after transmission-chains with if:false + gate:code like all 209 jobs, pack 6 validated) was verified by diff and ruled at 1788608265.003859; the earlier repair subset (K1 false-available, typed legs, rev/cutoff identity, exposure_screens, method version) landed at ebca50bf per observer 1788607834.596239."
  - "F01 #6873 is at RESULT / HOLD-FOR-SOL (head b7d237f0, Draft, no labels, auto-merge null, 0 reviews); Slot-2 hunks accepted by F00; independent review cannot come from the shared Claude8 identity, Sol places it via Capacity; global admission stays HELD; the NaN/True finite-number obligation (lib/macro_suite_view.py _finite) stays in #6873 and is explicitly NOT fixed by the repair child."
  - "Pack-5 main red (tests/test_macro_suite_pages.py :269 neutral-hollow unknown token, :424-429 hard-coded C/cy/cx) is settled by chain, not by F00: F00 option 1788637042.194119 → Sol amendment 1788645638.002919 on root 1788583938.803689 (sole exception to the 1788615927.409309 no-new-PR ruling; canonical macro#6819 issuecomment-5555062885, 6,692 bytes, SHA256 2901b934…4957) → repair root C0BSBM78V1N/1788645583.769389 → F01 owner dd51ef8f ACK 1788646076 / START 1788646503 → macro#6890 (Draft, labels none, auto-merge null, head 7eb8f7305a24, 2 paths, 52 passed locally, contract-delta 0/0, CI 33995832426 in flight, reviews REQUESTED from mastermindx-2/-3 but not submitted). Sol has not accepted or released #6890; #6873 and #6426 are not released."
  - "Terminal OAuth continuity break (Sol support c5551301450): terminal/components/onboarding/oauth.ts builds `next` from location.pathname + '?onboard=resume' and drops search/hash, so the requested company/analysis subpage is lost across the Google round-trip (six cases reproduced hermetically at blob 8027b6f7); Terminal #508 (094d061c, 34 paths) does not touch oauth.ts/StepAccount/OnboardingProvider/auth callback and is not that fix; #445 owns OnboardingSheet — any repair reconciles that hunk. Adjacent bounded follow-up, not an F00 build; no second session/navigation store."
  - "F03 specimen v4 (per c5551301450): whole-collar risk withheld without stock basis, debit vs hypothetical stock-basis separated, model-mark/EOD qualifications visible, keyed mobile legend; disposition belongs to the F03 action-authoritative Sol (five decisions: C0 release stays with C0 #6604, 16-row corrections with the ledger owner, Express in the existing workspace/parser, server-save ownership distinct from local drafting, one producer→contract→risk→return vertical when gates clear)."
  - "F00E archive subset is VERIFIED-USABLE (manifest 7488cf17…eaeda737 unchanged; 14 sampled event captures carry the unpublished-transmission message and no /equities/ anchors; 68 news URLs ⊂ event sitemap; corrected union 5,282 URLs) while route-universe categorization, the 337/5,009 vs 335/4,947 split rule, crosswalk method and paid-behaviour completeness stay OPEN; F00 consumes only REPAIRED F00E/F00G candidates."
  - "Research Vault #6862 (root C0BSBM78V1N/1788581036.874359) has an older START/effect-unknown on the same VPS; it is not adopted, bypassed or touched from the Help path."
  - "Per-route access tier for /transmission, /stocks and capital pages is not mapped route-by-route in config/site_access.yml; delivery/receipt states for alerts were not found in the two alert modules read (repo-wide absence unknown)."
next_actions:
  - "Host child is CLOSED (Sol 1788636103.500379); the storage-recovery lane is Sol's and was NOT_STARTED at Boundary 2. When it reports, re-verify Help live on www.mastermind-x.com by body hash (help.html → f7c67b2d0090, /help → 301 → 200 anonymous) and then run the 12-shot readback. Nothing on the host is F00's to run."
  - "Consume the F01 repair child's RESULT on root 1788645583.769389 and Sol's disposition of macro#6890; when #6890 merges, re-verify main's pack-5 by the newest main ci.yml run, then the pinned contenders (#6873, #6872, #6876) can be re-proven against a green base. F00 never arms, readies or merges any of them."
  - "Rule F04's corrected B-1 body + RED-first nightly-hook test when the worker returns the new head (compare against the hunk at 1788633496.506309; re-run merge-tree against the then-current #6873 head and fresh main); consume its RESULT / HOLD-FOR-SOL."
  - "Route the MO-PAID-020 DECISION_REQUEST to Sol once; do not build a renderer or an identity plane while it is open."
  - "Have F03/F06 return the V-A seam facts (consumer, identity tuple, resolver, instance) and F06/F11 recover the V-B proof carrier before any V-A/V-B source commission."
  - "Reconcile MO-DELTA-010 through #6792's owner; fold F09's ledger correction (MO-PAID-066 / MO-DELTA-025 'CONFIRMED-ABSENT' is false for ETF-disclosed bonds) into the next ledger write."
do_not_redo:
  - "Do not re-run the seven-scout seam census or a whole-fleet placement census; the seam map and corrections here are the baseline. Read carriers for state, not source absence."
  - "Do not resume quarantined F00 UUID 1727abca-4b22-4106-a498-6b83ad223a73; do not re-ACK or re-START any bound lane (F01 dd51ef8f, F04 d6317c9b, F05 cc2d9d31, F06 03200f5b, F09 641ca8f7, F10 9c9ac628, F11 d937f8bd, F12 local_abf9f882, F03 local_cc5baa49)."
  - "Do not commission a replacement user-state store, an indicator catalogue, a second evidence library, a research_context database, a page registry, an auto-publicizer or any deploy/scheduler control plane."
  - "Do not treat 'no K1 producer' as the gap; the gap is the excluded derived head (DSC:MARKET-ONTOLOGY-K1-VOCABULARY-EXCLUDES-TXI-CHAIN-STATE)."
  - "Do not propose reset --hard, live-plane rollback, wedged-process termination or 'run the updater once' as Help recovery; update.sh also arms Market Memory runtime fences."
  - "Do not widen public access beyond the three exact asset paths, and never with a prefix, wildcard or JSON/payload path."
  - "Do not order the shared CI contender list by PR number or age; only intersecting hunks serialize."
  - "Do not serialize #6872 and #6873 over their shared Caddyfile lines; keep-both was ruled, the second to land re-applies its tokens."
  - "Do not re-ACK, re-START, review from the Claude8 identity, arm, Ready or merge macro#6890 (F01 repair child, exact receiver dd51ef8f); do not open a second main-red-repair for pack 5; do not fold lib/macro_suite_view.py into that child."
  - "Do not relay a mastermindx.ai 525 on its own as a .com outage or widen a child's scope on it; positive new .ai-to-same-deployment evidence is reconciled under this operation's authority, not assumed (DSC:MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM)."
  - "Do not commission a Terminal OAuth rewrite or a second navigation/session store; the auth-return boundary is an adjacent follow-up reconciled with #445/#508 owners."
danger_areas:
  - "Sparse worktrees omit site/, data/ and mockups/; a write into an omitted tree truncates the committed artifact. Materialize with scripts/worktree_sparse.py before comparing site/ blobs."
  - "The clone is blobless: `git show <old>:<file>` on an old commit fetches over the network and can exceed 100 s; compare live bodies with `git hash-object --stdin` against `git rev-parse \"<commit>:<path>\"` (zsh requires the quoted ${c}:path form)."
  - "Slack send tool parameter is `message`; a `text` parameter fails with `no_text` while reads keep working, which reads as a dead carrier."
  - "Routed scout subagents die at roughly fourteen turns with findings only in tool results; cap them at ten calls and write once at the end."
  - "A merged PR is not live: the VPS pulls on its own cadence and the served copy can lag main by hours; verify by body hash on the real route, never by GitHub state."
  - "Shared fleet identity: every worktree commits and posts as the same account; a same-account post is not proof of which session acted."
  - "zsh parses `$r:app/deploy/Caddyfile` as the `:a` modifier ('ambiguous argument'); write `\"${r}:app/deploy/Caddyfile\"`. `git merge-tree --write-tree` takes exactly two branches; `origin/main A B` is a usage error."
  - "A held-PR push is an ACT: re-read the Slack carrier immediately before every push to #6876, and re-arm exactly one check watcher afterwards because a new head re-opens the checks."
decisions:
  - DEC:RESEARCH-CONTEXT-IS-PORTABLE-REFERENCE-NOT-MEMORY
  - DEC:SOL-HOLD-IS-A-MERGE-BARRIER
discoveries:
  - DSC:MARKET-ONTOLOGY-K1-VOCABULARY-EXCLUDES-TXI-CHAIN-STATE
  - DSC:MARKET-ONTOLOGY-USER-STATE-STORE-IS-TERMINAL-WATCHLISTS
  - DSC:MARKET-ONTOLOGY-PUBLIC-P1-CORPUS-RETAINED-OUTSIDE-GITHUB
  - DSC:MACRO-SERVED-ORIGIN-IS-MASTERMIND-X-COM
---

# Seam map — where a user's context is lost today

Evidence classes: CENSUS = cited file:line at Macro main 8431aeaf / Terminal
e89ebda4; F00-STATE = adjudication state read from carriers; UNKNOWN = not
established read-only, never "broken".

**S1 source event → macro/transmission trace.** Producer
engine/transmission_chains.py run()/build_chain_state → data/transmission/
chain_state.json + chain_episodes.jsonl (append-only); display projection
engine/transmission_publish.py → site/transmission_chains.json; consumer
templates/transmission.html.j2. Identity: chain id, rev, asof, substrate_asof,
hop.asof, confirmed, state, tier. K1: current head excluded, transitions admitted.
No code path carries an F02/F05 event object into a chain condition in the files
read (indirect path UNKNOWN). F04 X1 adds authenticated /api/ontology/explorer/v1.

**S2 macro/trace → resolved security.** engine/chronicle/spine.py (build_events,
union_events, apply_authoritative_retractions) and engine/security_state.py
compile_security_state via scripts/build_stock_library.py → /stockdata/<T>.json +
/stocks/<T>.html. Identity rule R8 issuer_cik == workspace_native_cik
(security_state.py:302, :463-473); URL key is the ticker; the
ListingAlias→ListingKey renderer is absent (MO-PAID-020 blockers
NO_GENERAL_NAMESPACE_RENDERER + CIK_LEG_UNOWNED_ACCESS); key present on 2 of 3014
stockdata files; PROVEN_LIVE for AAPL only. Consumer of an event→security link:
none confirmed (F05 MO-DELTA-001, MO-PAID-017/018/033).

**S3 resolved security → valuation / options / capital.** Options
engine/options_hub.py → templates/options.html.j2 (MO-PAID-071 PROVEN_LIVE;
stateless, no correction ledger); whether it keys on ticker was NOT inspected.
Valuation: no producer (consensus unwired at stock_fundamentals.py:1815).
Capital engine/capital_structure/* identity = cusip6/isin/name, prefix-then-name,
first registry match (:763-782); population = ETF-held par, not issuer
outstanding; dominant failure BLOCKED_RIGHTS. Biggest gap: two verified keys
(cik; isin/cusip6) plus an uninspected third leg with no verified join.

**S4 analysis → thesis / holdings / watchlist.** House thesis
engine/macro_thesis.py (append-only JSONL, keep-first thesis_id) and house
portfolio engine/portfolio.py are house-level by design. User-scoped watchlists
are OWNED by Terminal (DSC above) and bound by Macro templates/watchstore.js.
Access: require_user → require_site_full_user → paywall.enforce_site_full is
confirmed on ask_brain/ask_brain_stream (app/main.py:948, :978-981, :1086, :1116;
paywall.py:392). Open gap = authenticated live proof and tenant-scoping evidence.

**S5 holdings/thesis → monitoring/alerts → delivery.** engine/alerts.py
evaluate() (L71-570) → log_and_dedup (L602) → data/alerts/alerts_log.parquet →
alert_view/alert_views (L1082/1097) + engine/alert_triage.py → Alert Command
Center. Alert dataclass (L27-31) carries no user id, condition id, evaluation id
or delivery id; portfolio_digest send path deliberately unwired (MO-PAID-085).
Delivery/receipt states not found in the two modules read.

**S6 correction → affected views → follow-up.** Only
scripts/compile_capital_structure_events.py carries a typed correction identity
(correction_version int, correction_of; contiguity :420-438; max version = current
:548-552, :776-777, :987-990); consumer propagation UNKNOWN. 61/130 ledger rows
define correction_behavior; no effective_date/reason field found in the lines
inspected.

**Research context (RC).** RCTX-1 is BUILT_NOT_PROVEN on both heads (verified
above). Permitted shape per DEC:RESEARCH-CONTEXT-IS-PORTABLE-REFERENCE-NOT-MEMORY:
an ephemeral reference bundle (canonical refs, pinned receipts, cutoff, lens refs)
re-resolved at the destination; forbidden: source bodies, a research_context
store, Brain-owned navigation, whole-UI serialization. Extending a span beyond
same-document Ask → return is outside RCTX-1 and is not adopted.

Cross-seam reading: the resets users feel are identity-reference gaps (event id
never reaches a security page; ticker vs cik vs isin never joined; span only
inside one document), not memory gaps.

# Direction accepted by Sol (1788599922.022699)

"Context-preserving composition over existing owners" is accepted as DIRECTION,
not a cross-route implementation grant. Keep every page and owner; destinations
re-resolve through existing chains and refuse on mismatch; first-viewport grammar
State / What changed / Why it matters / Next action on hub and workspace pages;
rights/auth unchanged and re-checked at destination; no _navlinks, Caddy or
registry edits inside feature work. The one-key-per-hop link convention is
withdrawn until the V-A seam is proven (some native identities need several
fields).

# Shared wiring order (F00-STATE)

- .github/ci/legacy-jobs.yml: additive job blocks; only intersecting hunks
  serialize (none today between #6873 and the ten other contenders).
- scripts/build_site.py: Help guarded call merged; F01 hook on main; F04 X1 adds
  one guarded call, additive.
- config/site_access.yml / Caddyfile: Help entries merged at 8431aeaf; F01's three
  exact asset entries authorized inside #6873 (ruling 1788601186.334209); F04 Stage
  B ruled when it lands. Product-admission order Help → F01 → F04 is an admission
  order, not a file-serialization claim.
- Host activation of any merged access change rides the operator deployment
  packet, never a builder SSH/reload.

# Proof graph per journey

immutable source ref → owner generation/receipt → composed page (browser matrix,
typed states, both art directions) → RED-first journey test → merge =
BUILT_NOT_PROVEN → live readback on the real route → telemetry receipt =
PROVEN_LIVE. Help today: SOURCE_RELEASED at 8431aeaf, public-render succeeded,
served copy stale; host stage UNKNOWN until the host child returns.

# Boundary 2 addendum (2026-09-05 ~22:40Z, F00 principal 5b29ad85)

Recorded at the boundary Sol named in amendment 1788645638.002919 ("F00 records
the bounded amendment at its next existing record boundary"). Additive; nothing
above is withdrawn except where a row says so.

**Production correction.** F00's relay 1788633512.480849 ("origin unreachable,
525 on every path") was wrong at the altitude it claimed. The host child's dated
loaded configuration listed only the `.com` hosts, and the dated readbacks gave
`.com` 200 (via TencentEdgeOne) while `.ai` gave 525; on that evidence `.ai` is a
separate unqualified edge mapping, with uninterrupted uptime and any `.ai`→same-
deployment binding not established. F00 corrected itself at 1788637058.742439
and both posts stay as dated history. The real
publication blocker, as dated 2026-09-05 evidence, is `/opt/macro
available_bytes=0`, checkout `761a4df8` 108 commits behind then-current main,
`macro-update.service`/`.timer` at `LoadState=not-found`, and no match in the
bounded cron.d search; the effective scheduler/activation path remains
unverified. Storage recovery is Sol's lane.

**F04 ruling (1788633496.506309).** Path 25 admitted; B-1 body corrected (the
returned caller would have TypeError'd inside the additive guard and skipped the
page silently — the exact failure the guard pattern hides); B-3 accepted; RED-first
nightly-hook test owed; keep-both on the four shared Caddyfile lines with #6873.

**F01 Slot-2 acceptance.** Ruled at head b7d237f0 after RESULT 1788639616.516889.
Corrections issued: the worker's outage claim was stale; "no separate CI-fix PR"
was a worker position, not a ruling; no independent review can come from the
shared identity. Sol-ruled ledger facts from the F01 root: a shared test that
pins a live snapshot is data-as-fixture (1788615927.409309), and a candidate-owned
pack-4 design-governance red needs mockups/evidence EVIDENCE.yml + p0_evidence.v2
manifest + 8-cell PNGs (1788616061.860239).

**Pack-5 settlement chain.** F00 returned one bounded option and commissioned
nothing; Sol amended its own no-new-PR ruling for exactly that shape; the same F01
owner executed it as #6890. F00 consumes the child's returns as parent control and
records them; it does not review, arm, ready or merge. The NaN/True finite-number
dependency is deliberately outside the child and stays owed by #6873.

**Records routing.** The F03 v4 specimen disposition, the F00E verified subset,
the Terminal OAuth auth-return boundary and the #508/#445 collision identities are
carried in `unresolved:` above from Sol support c5551301450; F00 folds them, it
does not adjudicate them. The risk_envelope_live admission item remains with its
own owner and is not an F00 hunk.

