---
key: EDGAR-ATOM-TRANSIENT-IS-A-TIMEOUT
claim: >
  The browse-edgar Atom surface fails ~1.6% of valid requests transiently, and
  transport-level READ TIMEOUTS dominate that population — NOT the HTML
  "SEC.gov | File Unavailable" body the failure is usually reported as. Measured
  read-only on 2026-08-17 over 500 requests spread across the production page
  offsets (start=0..700): 8 failures (1.6%), all requests.exceptions.ReadTimeout,
  zero HTML bodies in that window. All 5 failures that were retried recovered on
  the FIRST retry. Successful-request latency was p50 1.6s, p95 11.7s, max 25.7s
  against the probe's 30s read timeout — the failures are the tail of a
  heavy-tailed latency distribution, not an unavailable surface. BOTH MODES ARE
  REAL: the same day, an independent ~25-request probe (the #5854 session) caught
  the HTML mode twice — start=0&count=30 and count=39 each returned
  `<!DOCTYPE html>` and each succeeded on retry seconds later with an identical
  URL. The two windows disagree because the HTML mode CLUSTERS, not because
  either mismeasured. The durable point is therefore not "the transient is a
  timeout" but "timeouts dominate, and a body-only check cannot see them".
falsifier: >
  Re-run the paced read-only probe and observe either a transient rate
  materially above ~2%, HTML error bodies outnumbering timeouts, or retried
  failures that do not recover on the first retry:
  `for i in $(seq 1 100); do curl -sS -o /dev/null -w "%{http_code} %{time_total}\n"
  -A "$SEC_USER_AGENT" --max-time 30
  "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F&start=$((
  (i % 8) * 100 ))&count=100&output=atom"; sleep 0.2; done`
  — non-200s and curl exit 28 (timeout) are the transient population. The
  encoded constant is engine/institutional_census/sec_sources.py:77
  (ATOM_FETCH_ATTEMPTS).
so_what: >
  A retry policy that only inspects the RESPONSE BODY (the HTML-error-page
  check) cannot fire for the dominant failure mode, because a read timeout
  raises out of the fetch callable and never reaches the parser. Any transient
  handling for this surface must be declared at the layer that owns the HTTP
  client — `sec_sources` deliberately does not import requests — and the
  parser-side HTML check is the secondary path, not the primary one. Because
  failures are a latency tail rather than an outage, an immediate retry through
  the existing pacing is sufficient and no extra backoff is needed. Note the
  probe used a 30s read timeout while production allows 180s, so 1.6% is an
  upper bound for the production lane. DO NOT PRUNE the HTML-body branch
  (`_is_html_error_body`) on the grounds that a probe window saw no HTML: that
  mode is bursty and was observed twice in ~25 requests on the same day it was
  absent from 500. A zero count in one window is not evidence the branch is dead
  code, and removing it re-opens the failure this record exists to close.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  Two read-only probes against
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F&output=atom
  at 5 req/s (production caps at 8, SEC allows 10), cycling start=0,100,...,700
  with production page sizes. Probe 1: 200 requests, 3 ReadTimeout, 0 HTML.
  Probe 2: 300 requests, 5 ReadTimeout, 0 HTML, each retried twice — 5/5
  recovered on the first retry. The HTML-mode sighting is the #5854 session's
  independent ~25-request probe the same day (start=0&count=30 and count=39).
  Live-feed happy-path anchor at 04:07Z post-merge, entry_limit=750: the ladder
  (0,100)(100,100)(200,100)(300,100)(400,100)(500,100)(600,100)(700,40)(740,10)
  = 9 pages / 750 entries / complete=False / stop_reason=ephemeral_limit, pinned
  by test_atom_scanner_matches_the_live_production_page_ladder. Encoded as
  ATOM_FETCH_ATTEMPTS and
  SecSourceUnavailableError in engine/institutional_census/sec_sources.py, with
  the transport translation in scripts/run_institutional_13f_rolling.py, by
  PR #5858.
scope:
  - macro
  - engine/institutional_census/sec_sources.py
  - scripts/run_institutional_13f_rolling.py
confidence: verified
---

Found while closing the robustness gap that PR #5854 deliberately left open: a
transient page killed the whole atom scan. The reported symptom was an HTML
error page, and a body-only retry would have looked correct in review while
firing for none of the failures actually observed on the live surface.

This is why the fix has two entry points rather than one. `SecSourceError` gains
a `SecSourceUnavailableError` subclass; the parser raises it for an HTML body,
and `_RequestsSecFetch` raises it for timeouts, connection errors, and the
transient HTTP statuses (429/500/502/503/504) — a 403/404 stays a refusal and is
never retried. See [[EDGAR-BROWSE-COUNT-IS-ROUNDED-DOWN]] for the paging model
these pages are walked with.
