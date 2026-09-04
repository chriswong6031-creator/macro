---
workstream: "WS:BIOCATALYST-CORE-PRODUCT"
session: claude/biocatalyst-p1-avail-1
model: fable
ended_because: blocked
mission: >
  BIOCATALYST-P1-AVAIL-1-20260827 / MAS-172 (Fable COO dispatch, Slack
  C0BSBM78V1N thread 1787879112.101029): the Chairman reported the proven
  P1-1 interface "currently down"; reproduce read-only on the real
  production path, isolate root cause across edge/static/updater/auth/API/
  data/browser, repair only a proven root cause, and return exact evidence.
state_before: >
  P1-1 done at PROVEN_LIVE_COHORT_LIMITED (P1-1R receipt 2026-08-23);
  workstream parked; only open BioCatalyst PR is #6389 under a Sol
  freshness-only HOLD (untouchable in this operation). Chairman availability
  report received 2026-08-28 01:05Z with no symptom detail beyond "down".
changed:
  - path: research/BIOCATALYST_P1_AVAIL_1_AVAILABILITY_AUDIT_2026-08-28.md
    what: >
      Added the full read-only availability audit: every origin-measurable
      plane healthy and byte-identical to origin/main; the one real incident
      (transient Supabase-upstream /api/me 502 window 22:56-22:59Z Aug 27,
      self-healed); the zero-origin-traffic finding placing the Chairman's
      failure in front of the origin; the named entitled-browser boundary;
      the out-of-scope /api/dossier-quote 503 observation flagged for Sol.
  - path: agentos/workstreams/WS-BIOCATALYST-CORE-PRODUCT.md
    what: >
      Opened bounded wave P1-AVAIL-1 (status in_review), set workstream
      active for this wave only, linked the audit artifact. No new product
      authority; P1-2 still separately gated.
  - path: agentos/handoffs/BIOCATALYST-CORE-PRODUCT-2026-08-28-P1-AVAIL-1.md
    what: Added this cold-stranger continuation handoff.
prs: []
verified:
  - claim: >
      Production static delivery serves exactly the accepted bytes: page 200
      with the P1-1R stamp set; all 10 referenced assets 200; served
      biocatalyst.css/js, theme.js, live.js SHA-256 equal to origin/main
      blobs; identical from both EdgeOne A records.
    command: >-
      curl page + assets with response SHA-256; git cat-file blob
      origin/main:site/<asset> | shasum -a 256; curl --resolve against
      43.159.98.106 and 43.159.99.101
    result: >
      css 712a3a77307efbe9… == origin/main; js c35dac39a3718d8d… ==
      origin/main; theme.js 0956049c81c4d071…, live.js cfb8c072fff903da…
      both equal; page 200/70171B on both POPs.
  - claim: >
      The Radar API contracts hold from the public vantage: unsigned 401
      "missing bearer token", garbage bearer 401 "invalid token" reaching
      origin, private no-store + Vary Authorization on each.
    command: curl -sSi with and without Authorization header
    result: Both 401 variants exact; eo-cache-status MISS; headers exact.
  - claim: >
      The data plane is fresh and gapless: pointer generation
      ctgov_run_20260828T050054568203Z_e679bb3d2518, state fresh, 4/4
      cohort, hourly generations with zero gaps Aug 27 00:00Z -> Aug 28
      05:00Z.
    command: >-
      read-only SSH (deploy identity): cat current.json/health.json; ls
      generations/ bucketed by hour
    result: As stated; last_error_code null; source dataset 2026-08-27T09:00:05.
  - claim: >
      The real production handler serves the exact P1-1 contract: executed
      app.biocatalyst.catalyst_radar() in-process with the production
      interpreter on the production checkout (auth dependency injected,
      read-only): 200 shape, 4 rows, 3+1+0+4=8 arithmetic, 2 has_revisions
      (3+3=6 lineage entries) + 2 history_not_collected, authority block
      frozen, zero forbidden keys, and horizon="bogus" raises typed 400
      "invalid horizon" with private no-store headers.
    command: >-
      sudo -u macro-biocatalyst /opt/macro-api/.venv/bin/python with
      sys.path /opt/macro; recursive forbidden-key walk
    result: All values exact as recorded in the audit doc.
  - claim: >
      The unauthenticated browser runtime is clean on real production bytes:
      locked state renders, radar fetch fires and reaches the origin
      journal, only console error is the expected 401, zero horizontal
      overflow at 2055x1270 / 1280x900 / 390x844 in EN and ZH.
    command: >-
      Chromium (Browser pane) on https://www.mastermind-x.com/
      biocatalyst.html; resize_window cuts; scrollWidth/clientWidth
      measurements; read_console_messages; data-lang zh via the page's own
      langchange mechanism
    result: hOverflow false at all six cuts; workspaceState "locked".
  - claim: >
      The only authenticated-path failure in 7 days of complete journal is
      the transient /api/me 502 "auth check upstream failure (outage)"
      window 2026-08-27 22:56:17-22:59:08Z (6 requests; plus 4 on Aug 24
      03:38-03:39Z), and ZERO BioCatalyst API requests from any real user
      exist between 2026-08-23 07:13Z and this audit.
    command: >-
      journalctl -u macro-api (floor Jul 09) grep catalyst-radar /
      biocatalyst / 502 / "auth check upstream failure" over 7 days
    result: Counts and windows exact as recorded; journal continuous.
unverified:
  - >
    The real entitled browser journey (real /api/me 200, entitled Radar 200,
    populated-page geometry, evidence drill-down) — claude-in-chrome was
    disconnected and agent credential sign-in is prohibited; this is the
    named boundary, not an oversight.
  - >
    In-China EdgeOne POP reachability for the Chairman's vantage — untestable
    from the fleet host; DNS via China resolvers was consistent but that does
    not prove in-country POP delivery.
unresolved:
  - >
    Which layer actually failed for the Chairman: their attempts left no
    origin trace, so the candidates are the Chairman-side access path
    (client/network/in-China edge) or the 22:56-22:59Z Aug 27 auth-upstream
    window (self-healed). Needs Chairman-side vantage data or an entitled
    acceptance run to close.
next_actions:
  - >
    Sol ruling needed on the evidence-bounded state: (a) obtain
    Chairman-side vantage data (exact URL, what rendered, timestamp,
    whether other authenticated pages worked), and/or (b) run the standing
    entitled acceptance via a claude-in-chrome-connected session (operator's
    authenticated Chrome), and/or (c) accept the audit as the wave verdict.
  - >
    If Chairman-side repro shows in-China EdgeOne unreachability, that is an
    edge/platform plane (EdgeOne console), not a repo patch — route as an
    operator/platform action.
do_not_redo:
  - >
    Do not re-diagnose the origin planes for this report window: static,
    assets, updater convergence, regwall, API contracts, auth upstream,
    generation cadence, handler payload, and unsigned browser runtime were
    all proven healthy 2026-08-28 04:50-05:45Z with receipts in the audit
    doc. New evidence from the Chairman's vantage is the only useful input.
  - >
    Do not treat /biocatalyst (extensionless) 401 JSON as the defect: no
    shipped surface links it; the nav links biocatalyst.html which serves
    200 publicly by design (Caddyfile @reg_html exclusion).
  - >
    Do not touch, rebase, merge, publish, or deploy #6389 (Sol
    freshness-only HOLD) under this operation.
danger_areas:
  - >
    The stock-dossier plane (/api/dossier-quote, #6572) is 503ing to an
    external 60s poller since 2026-08-28 04:09Z — real, ongoing, OUT of
    BioCatalyst scope; owned by the dossier/Terminal-quote workstream.
    Flagged to Sol; do not fold into this wave.
  - >
    Credential sign-in by an agent is prohibited; the entitled journey must
    come from the operator's own authenticated browser session.
---

Cold-stranger summary: the Chairman reported BioCatalyst down; every layer
the fleet can measure is provably healthy and byte-exact, the Chairman's
failing requests never reached the origin, and the only genuine incident was
a 3-minute Supabase-upstream 502 window on Aug 27 that self-healed. The wave
is parked on a Sol ruling because the one unproven hop — the real entitled
browser journey — is exactly the hop this session cannot lawfully exercise
while claude-in-chrome is disconnected. Read the audit doc first; do not
re-plow the proven planes.
