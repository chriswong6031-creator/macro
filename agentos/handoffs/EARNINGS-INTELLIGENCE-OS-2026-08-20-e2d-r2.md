---
workstream: "WS:EARNINGS-INTELLIGENCE-OS"
session: claude/earnings-e2-d
model: local
ended_because: complete
mission: >
  E2-D Round 2: keep PR #6021, reconcile onto current origin/main, and close
  only the five Sol findings in review 4980594142. Do not merge, deploy, or
  start E3+.
state_before: >
  Draft PR #6021 (hold + do-not-merge) implemented the public dossier glance
  from event_workspace.v1. Sol accepted the architecture and blocked merge
  for alias uniqueness, genuine 404 proof, public projection bounds, cache
  policy, and hosted CI wiring. Branch base was 169 commits behind main.
changed:
  - path: engine/company_intelligence/event_workspace.py
    what: Private _register_alias helper; same alias/same event idempotent; collision raises before marker advance.
  - path: engine/neuralweb/company_intelligence_reader.py
    what: Post-load ticker/period/alias/issuer cross-check maps to verification failure, never 404.
  - path: app/company_intelligence.py
    what: Exact-public-evidence predicate, bounded glance, machine-coded not-covered 404, short public cache.
  - path: site/assets/js/company-intelligence-dossier.js
    what: v1 fallback only on 404 + event_workspace_not_covered + ticker match.
  - path: .github/ci/legacy-jobs.yml
    what: prelaunch-hardening now names and executes tests/test_company_intelligence_dossier_js.py with node --version.
prs: [6021]
verified:
  - claim: Writer alias collision refuses before event_workspaces/manifest.json advances.
    command: python3 -m pytest tests/test_company_intelligence_event_workspace.py::test_write_workspace_generation_refuses_alias_collision_before_marker -q
    result: passed
  - claim: Generic JSON/HTML/missing-code/mismatched-ticker 404s never call v1; canonical not-covered 404 still does.
    command: python3 -m pytest tests/test_company_intelligence_dossier_js.py -q
    result: Node suite passed including the four 404 states
  - claim: Public projection is exact-evidence gated and size-bounded.
    command: python3 -m pytest tests/test_company_intelligence_event_workspace.py -q -k "public_glance"
    result: typed-absent lede omits +16%; address-only/non-public guidance omitted; watch text <=500; watch list cap 3; no claim_text
  - claim: 200 and canonical 404 are public max-age=60 SWR=240; 422/429/503 remain private no-store.
    command: python3 -m pytest tests/test_company_intelligence_api.py -q -k event_workspace_glance
    result: passed
  - claim: contract-delta introduced zero findings against origin/main.
    command: python3 scripts/check_contract_delta.py --base origin/main
    result: "0 introduced, 7 inherited (base 7afb9489731d)"
  - claim: Local visual AAPL glance remains correct at 1440 EN, 820 EN, 390 ZH with no overflow.
    command: /opt/homebrew/Caskroom/miniconda/base/bin/python /tmp/e2d-visual/prove_e2d.py
    result: "FAILURES none; shots in /tmp/e2d-visual/{1440en,820en,390zh,1440en-unavail,1440en-v1}.png"
unverified: []
unresolved:
  - "Hosted CI classification of this Round-2 head is not yet in this file; post after push."
  - "slides remain typed absent; consensus unlicensed; questions unstructured; reaction not_joined."
next_actions:
  - "Sol Round-2 re-review of draft PR #6021. Keep hold + do-not-merge. Do not arm merge-on-green."
  - "After Sol GO: arm → merge → API/static deploy → real AAPL production proof, then mark E2 complete."
do_not_redo:
  - "Do not mutate GET /api/company-intelligence/{ticker}."
  - "Do not fall back to v1 on generic/Caddy/HTML 404."
  - "Do not reopen Terminal E2-T1, E3+, publisher, Qwen, slides, peers, Prophet, or corpus backfill."
  - "Do not let dictionary assignment own workspace aliases."
danger_areas:
  - "A v2 404 without code=event_workspace_not_covered is a partial-deploy failure, not coverage absence."
  - "Registering _aliases.tickers as publication aliases would collide across fiscal periods."
  - "Editing .github/workflows/ci.yml and .github/ci/legacy-jobs.yml is an authority-changing path."
---

## §0 State — what is true right now

E2-D Round 2 is on the same draft PR #6021. The accepted architecture is unchanged. The five Sol findings are closed in tests: writer alias collisions fail before marker advance; generic 404 never calls v1; the public glance is exact-evidence and rights-gated; 200 and canonical 404 are short-public-cacheable; the dossier JS suite is named by prelaunch-hardening and requires Node on PATH.

## §1 What is LEFT — in order

1. Sol re-review of #6021. Keep DRAFT + hold + do-not-merge.
2. After GO: merge, deploy, and prove live AAPL public dossier against generation f709a0a6ec514282d5769e7d.
3. Then mark the E2 arc complete. Do not start E3 in that same motion unless separately commissioned.

## §2 What will bite you

A FastAPI `{"detail":"Not Found"}` or Caddy HTML 404 during partial deploy used to paint AAPL as an older v1 quarter. That path now renders unavailable. Do not "simplify" JS back to `status === 404`.

`_aliases.tickers` is a list and must not go through `_register_alias`. Bare ticker `AAPL` would collide across quarters.

## §3 What was decided and found

No new DEC/DSC. Architecture remains DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT.

## §4 Not in scope — do not adopt

No merge, no deploy, no E3+, no Terminal work, no publisher changes, no Qwen, no slides, no Prophet.
