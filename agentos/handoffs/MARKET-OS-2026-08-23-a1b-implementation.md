---
workstream: "WS:MARKET-OS"
session: codex/market-os-a1b-implementation-20260823
model: codex
ended_because: complete
mission: >
  Implement exactly the commissioned A1B Portfolio Fast Start Import vertical in
  Macro: paste the frozen line grammar, review every valid row exactly, save once to
  canonical portfolio_positions with stable UUID identity and fail-closed mutation
  semantics, authoritatively reread the Portfolio, preserve Terminal as an unchanged
  independent consumer, and stop at one draft review PR before merge, deployment, or
  production mutation.
state_before: >
  A1A was PROVEN_LIVE / DONE and A1B was separately commissioned. Macro had truthful
  Portfolio population/state authority and authenticated cloud failure behavior, but
  no canonical holdings paste flow. The existing paste path owned Watchlist/ENTERED
  state and could not be relabeled as Portfolio import. Terminal already read the same
  portfolio_positions rows and required no A1B code change.
changed:
  - path: "templates/portfolio_import.js"
    what: >
      Adds the DOM/network/persistence-free frozen grammar, exact editable draft,
      stable RFC4122 UUID identity, strict finite numeric/date validation, coverage
      annotation, duplicate warnings without deduplication, and semantic fingerprint.
  - path: "templates/portfolio_import_ui.js"
    what: >
      Adds the EN/ZH paste and exact review workflow, editable nullable fields,
      per-row removal, one explicit save action, privacy-safe lifecycle events, and
      hard retry lockout for ambiguous/effect-unknown/auth/reread failures.
  - path: "templates/portfolio_import.css"
    what: >
      Adds token-native desktop/narrow modal layout, including a narrow two-column
      review and collision avoidance with the existing floating Brain launcher.
  - path: "templates/watchstore.js"
    what: >
      Adds one-batch local/cloud persistence, exact owner/ID/semantic receipt proof,
      stable-ID lost-response reconciliation, one same-ID retry only after proven zero,
      auth-generation fencing, authoritative cloud reread, UUID-preserving local fold,
      and safest-existing legacy loc-* fold behavior.
  - path: "templates/portfolio.js"
    what: >
      Connects successful import completion to the existing authoritative Portfolio
      reread and write-honesty state without claiming saved state early.
  - path: "templates/watchlist.html.j2"
    what: >
      Adds the primary Import holdings action, exact review modal, and ordered A1B
      assets while preserving Add position and Watchlist separation.
  - path: "site/portfolio_import.css"
    what: "Shipping pair of templates/portfolio_import.css."
  - path: "site/portfolio_import.js"
    what: "Shipping pair of templates/portfolio_import.js."
  - path: "site/portfolio_import_ui.js"
    what: "Shipping pair of templates/portfolio_import_ui.js."
  - path: "site/watchstore.js"
    what: "Shipping pair of templates/watchstore.js."
  - path: "site/portfolio.js"
    what: "Shipping pair of templates/portfolio.js."
  - path: "site/watchlist.html"
    what: "Generated shipping Watchlist/Portfolio shell with the bounded A1B UI."
  - path: "scripts/build_site.py"
    what: "Adds the three A1B assets to the canonical site build copy list."
  - path: "config/site_access.yml"
    what: >
      Declares the three visitor-owned import UI assets in the existing public static
      asset boundary; they carry no Portfolio rows or gated intelligence payload.
  - path: "app/deploy/Caddyfile"
    what: >
      Adds those exact three assets to the existing Portfolio shell/static cache
      matchers without adding a new route, API, or data boundary.
  - path: "tests/test_portfolio_import_a1b_js.py"
    what: >
      Adds the frozen parser, mutation honesty, atomicity, idempotency, stable-ID,
      duplicate, auth-generation, fold, source-wiring, and responsive regression suite.
  - path: ".github/ci/legacy-jobs.yml"
    what: "Wires the A1B suite into the existing Portfolio CI owner job."
  - path: "tests/test_unsubscribe_page.py"
    what: "Updates the exact reviewed public-static asset fence for the three A1B files."
  - path: "tests/test_caddy_hub_boundary.py"
    what: >
      Advances the pinned final safe-proxy line number by one after A1B expands the
      reviewed Caddy cache-law comment; the proxy classification remains unchanged.
  - path: "agentos/workstreams/WS-MARKET-OS.md"
    what: >
      Advances A1B from eligible/todo to implementation-in-review while preserving
      Sol as the next gate and keeping merge, deployment, production proof, and A2+
      explicitly unstarted.
verified:
  - claim: "The frozen A1B parser and batch persistence/failure laws are executable"
    command: >
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
      tests/test_portfolio_import_a1b_js.py -q
    result: >
      PASS — 25 tests cover strict grammar/null preservation, UUID stability,
      duplicates, local one-write atomicity, exact N-row cloud receipt, lost-response
      all/zero/some/conflict/unavailable branches, auth changes, authoritative reread,
      and UUID-preserving plus legacy local folds. Synthetic fixtures only; no live
      account or production mutation.
  - claim: "Accepted A1A Portfolio/auth/Watchlist behavior is unchanged"
    command: >
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
      tests/test_watchlist_books_js.py tests/test_portfolio_truth_a1a_js.py
      tests/test_portfolio_auth_transition_js.py tests/test_watchlist_workspace_js.py -q
    result: "PASS — 189 tests."
  - claim: "The existing registration/static boundary remains exact"
    command: >
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
      tests/test_site_access_boundary.py tests/test_unsubscribe_page.py -q
    result: "PASS — 78 tests."
  - claim: "Generated shipping pairs and serving syntax are valid"
    command: >
      python3 scripts/check_template_site_sync.py &&
      caddy validate --config app/deploy/Caddyfile
    result: "PASS — 94 pairs checked; Caddy reports Valid configuration."
  - claim: "A1B preserves the pinned Caddy backend-proxy safety map"
    command: >
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
      tests/test_caddy_hub_boundary.py -q
    result: >
      PASS — 18 tests. The first exact-head CI attempt correctly caught that A1B's
      expanded cache-law comment moved the final SAFE_FIXED_REWRITE proxy from line
      769 to 770; the expectation now pins the unchanged safe classification at its
      actual shipped line.
  - claim: "The complete review interaction works in both art directions and viewport classes"
    command: "In-app browser against an isolated local site/ server; no Save action invoked"
    result: >
      PASS — EN/light desktop and ZH/dark narrow review flows render exact rows,
      preserve duplicate lots, retain uncovered valid rows, show invalid-line errors,
      disable Save on errors, re-enable Review after Back, keep Save reachable on a
      390x844 viewport, and leave the synthetic Portfolio population at zero. Browser
      warning/error logs were empty. No authenticated session or production write was
      used.
  - claim: "Terminal remains an unchanged independent canonical consumer"
    command: >
      Protected Terminal master census at
      935a13d4a66d749ee6356b5f5ed0feff8af4a2dd plus schema/service inspection
    result: >
      PASS — no Terminal file is changed; its existing owner-scoped
      portfolio_positions reader remains the independent conformance path. Production
      Macro-Terminal proof remains a separately authorized post-review operation.
unverified:
  - claim: "The exact A1B review head is accepted by Sol"
    what_would_verify: >
      Sol review of the final draft PR exact head after all binding CI/fence checks
      conclude. A draft PR or green CI does not itself authorize merge/deploy.
  - claim: "A real authenticated import journey is accepted in production"
    what_would_verify: >
      Fresh Sol action-time authority followed by the bounded production proof in the
      A1B commission: baseline seals, controlled batch, exact write/reconciliation
      receipts, Macro and Terminal rereads, privacy inspection, exact cleanup, and
      immediate/delayed baseline restoration.
unresolved:
  - "A1B is implemented for review but is not merged, deployed, production-proven, or accepted."
  - "No authenticated offline outbox was added; a failed signed-in write remains a typed failure, never local fallback."
  - "Production lost-response exercise and anonymous-to-authenticated fold proof require separate bounded disposable authority."
danger_areas:
  - >
    Never change stable draft IDs on retry. After a lost response, only exact intended
    IDs under the authenticated owner can establish success or proven zero; some,
    conflict, or unavailable reconciliation is a hard stop.
  - >
    Never dedupe by ticker. Duplicate tickers and duplicate lots are legal canonical
    positions and retain distinct UUIDs.
  - >
    Never treat Review as a write, authenticated cloud failure as local fallback, an
    unknown effect as retryable, a partial receipt as success, or a failed
    authoritative reread as Saved.
  - >
    Terminal, A2-A6, Watchlist mutation semantics, schema/RLS, new persistence planes,
    CSV/broker import, broad My Market redesign, merge, deploy, and production mutation
    are outside this carrier.
next_actions:
  - >
    Return the exact draft PR head, changed-file inventory, CI/fence run IDs, browser
    receipt, collision census, and this handoff to Sol for code review. Keep the PR
    draft with no merge-on-green label and native auto-merge disabled.
  - >
    On Sol approval only, follow the next explicit authority. Do not infer permission
    to merge, deploy, run production acceptance, or begin A2.
do_not_redo:
  - "Do not repeat A1A or Scene 9."
  - "Do not replace canonical portfolio_positions with the Watchlist/ENTERED paste path."
  - "Do not add a second Portfolio, identity, retry/outbox, or local/cloud persistence plane."
  - "Do not edit Terminal merely to create implementation symmetry; it is the unchanged independent consumer for A1B."
  - "Do not call A1B complete because local tests, browser QA, or CI are green."
prs:
  - 6335
decisions:
  - DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE
  - DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT
  - DEC:MARKET-OS-A1A-ACCEPTED-IN-PRODUCTION
---

# A1B Portfolio Fast Start Import — Implementation Review Handoff

## Review state

`A1B_IMPLEMENTATION_READY_FOR_SOL_REVIEW` is the intended return state only after the
exact draft PR head has concluded its binding checks. It is not an acceptance, merge,
deployment, or production-proof claim.

## Capability delta

Before, users could add one canonical Portfolio position at a time, while the existing
paste path belonged to Watchlist/ENTERED state. The review carrier adds one bounded
Portfolio-native workflow: paste the frozen grammar, inspect and edit every valid row,
then make one stable-identity batch save whose outcome is proven by exact receipt and
authoritative reread.

## Exact stop

Stop at Sol review. Preserve the draft/HOLD state. No production row was read or
mutated by this implementation session, no Terminal file changed, and no later Market
OS wave started.
