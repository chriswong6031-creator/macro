---
workstream: "WS:EARNINGS-INTELLIGENCE-OS"
session: claude/earnings-e2-d
model: local
ended_because: complete
mission: >
  E2-D Canonical Macro Dossier Glance: from origin/main, make the public
  Company Intelligence module render live event_workspace.v1 as the current
  earnings glance for AAPL, matching Terminal Brief identity and source-backed
  hierarchy. Stop at a DRAFT hold/do-not-merge PR for Sol review. Do not merge,
  deploy, reopen E2-T1, or start E3+.
state_before: >
  E1P production nest live on generation f709a0a6ec514282d5769e7d,
  event_id evt_cik0000320193_2026q3_results. Terminal E2-T1 landed at
  abf87195c7ea. Public dossier still fetched GET /api/company-intelligence/{ticker}
  and rendered v1 teaser (summary, Strength/Pressure, score_overlay lineage,
  questions_count 14). No public v2 glance route existed.
changed:
  - path: engine/company_intelligence/event_workspace.py
    what: Added select_current_event_from_aliases (T/YYYYQn, canonical evt_cik ids only, fail closed on ambiguity, greatest fiscal period).
  - path: engine/neuralweb/company_intelligence_reader.py
    what: Added read_current_event_workspace({ticker}) reusing workspace snapshot/object loaders; never consults v1.
  - path: app/company_intelligence.py
    what: Added GET /api/event-workspace/{ticker} returning event_workspace_public_glance.v1; v1 teaser route unchanged.
  - path: site/assets/js/company-intelligence-dossier.js
    what: v2-first fetch law (200 render v2, 404 then v1, else unavailable never v1); REPORTED/GUIDANCE/WATCH/COVERAGE; analysis intelligence CTA.
  - path: templates/ticker.html.j2
    what: v2 host + CSS hierarchy; hide v1 history/lenses in v2; unavailable hides v1 marketing title.
  - path: tests/test_company_intelligence_event_workspace.py
    what: Q2+Q3 latest, ambiguous owners, correction, leak denylist, coverage honesty.
  - path: tests/test_company_intelligence_api.py
    what: v2 HTTP 200/404/503/422/429; v1 reader not called; leak denylist.
  - path: tests/test_company_intelligence_dossier_js.py
    what: Browser cutover discriminators against poisoned v1 overlay.
  - path: tests/test_ticker_pages.py
    what: v2-first fetch order and #ci-v2-host in the dossier template.
  - path: agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md
    what: E2-D marked in_progress; workstream awaiting Sol review of the draft PR.
verified:
  - claim: Selector admits Q2+Q3 aliases and returns Q3 (evt_cik0000320193_2026q3_results); same-period distinct owners fail closed; non-canonical ids are skipped.
    command: python3 -m pytest tests/test_company_intelligence_event_workspace.py -q --tb=line
    result: file green including test_select_picks_q3_when_q2_and_q3_both_published, test_select_raises_ambiguous_for_duplicate_period_canonical_ids, test_select_ignores_non_canonical_event_ids
  - claim: Public glance projection formats Revenue $109.4B · +16% and Q4 9–11% from the AAPL workspace fixture, keeps consensus unlicensed / reaction not_joined, omits R2 URLs and hashes, and updates value on same-event correction without minting a new event_id.
    command: python3 -m pytest tests/test_company_intelligence_event_workspace.py tests/test_company_intelligence_api.py -q --tb=line
    result: both files green (58 passed with dossier JS file in the same invocation)
  - claim: Browser cutover — v2 200 never requests v1; v2 404 renders legacy v1; v2 503/429/network/invalid schema render unavailable and never request v1; primary CTA is /analysis?symbol=AAPL&page=intelligence.
    command: python3 -m pytest tests/test_company_intelligence_dossier_js.py tests/test_ticker_pages.py -k company_intelligence -q --tb=short
    result: discriminators passed; node --check on company-intelligence-dossier.js included
  - claim: Local Playwright visual of the Company Intelligence block — 1440×900 EN v2, 820×1180 EN v2, 390×844 ZH v2, 1440 EN unavailable, 1440 EN v1 404 fallback — zero module overflow; v2 shows canonical event and source-backed hierarchy; 503 does not call v1.
    command: /opt/homebrew/Caskroom/miniconda/base/bin/python /tmp/e2d-visual/prove_e2d.py
    result: >
      1440en/820en/390zh mode=v2 event_id=evt_cik0000320193_2026q3_results overflow=false v1_called=false;
      glance Revenue $109.4B · +16%, Q4 9–11%, Unlicensed, Not joined;
      ZH 营收/第四季度营收增长/未授权/未接入;
      unavailable mode=unavailable v1_called=false Retry present;
      v1_fallback mode=v1 v1_called=true. Screenshots /tmp/e2d-visual/*.png
unverified:
  - claim: Production public AAPL dossier at mastermind-x.com/stocks/AAPL.html serves this v2 glance after merge/deploy.
    what_would_verify: After Sol review and squash-merge, wait for VPS pull and confirm GET /api/event-workspace/AAPL plus the live dossier data-ci-event-id.
unresolved:
  - "Draft PR is hold + do-not-merge for Sol. Do not merge or deploy from this session."
  - "Watch claim text is English source-backed excerpt even in ZH; labels are bilingual."
  - "AAPL public Wire slug remains absent; generic earnings/ archive CTA stays."
  - "questions_count remains unstructured; consensus unlicensed; reaction not_joined."
next_actions:
  - "Sol reviews the draft E2-D PR against the frozen architecture rulings."
  - "After approval, squash-merge, then live-verify public AAPL dossier against generation f709a0a6ec514282d5769e7d."
  - "Do not start E3+."
do_not_redo:
  - "Do not mutate GET /api/company-intelligence/{ticker} or stuff event_workspace.v1 into company_intelligence_context.v1."
  - "Do not reopen Terminal E2-T1 / PR #418 product, Results taxonomy, or receipt copy."
  - "Do not fall back to v1 on v2 503/429/invalid/network — that would show a stale quarter."
  - "Do not send full workspace, R2 URLs, hashes, or byte locators to anonymous browsers."
  - "Do not start E3+, slides, Q&A ML, Wire publisher, or canonical multi-event history (E4/E5)."
danger_areas:
  - "coverage_states is an array of {id,label,state}, not a dict. A dict renderer prints [object Object]."
  - "Ticker→event selection must use verified workspace aliases only. Consulting v1 CI or Wire would pick the wrong current event."
  - "Public Watch items require byte_replayed plus rp_public_primary_v1/public_primary; omit otherwise."
  - "templates/ticker.html.j2 cache-busts the dossier JS (?v=). Bump it when the JS changes."
---

E2-D implements the public Macro dossier glance as a bounded projection of
`event_workspace.v1`. Authority for a covered ticker is
`GET /api/event-workspace/{ticker}` (`event_workspace_public_glance.v1`).
The closed v1 teaser remains the 404 fallback only.

Stop condition for this session is the draft PR for Sol, not a merge.
