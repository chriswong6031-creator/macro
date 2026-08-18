---
key: EDGAR-BROWSE-COUNT-IS-ROUNDED-DOWN
claim: >
  browse-edgar serves only the page sizes 10, 20, 40, 80, 100. Any other
  `count` is rounded DOWN to the largest of those that fits, so an unhonored
  request returns a page shorter than asked for while the feed still has more
  to give. Measured against action=getcurrent&type=13F on 2026-08-17:
  count=50 served 40, count=30 served 20, count=15 served 10, count=39 served
  20, count=101 and count=200 each served 100. Separately, `type` is a PREFIX
  match, not an exact one: getcurrent&type=13F-H returns both 13F-HR and
  13F-HR/A, and type=13F therefore admits 13F-family forms such as 13FCONP
  (CIK 1067983 has filed four, all under the 9999999997 accession prefix).
falsifier: >
  GET https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F&company=&dateb=&owner=include&start=0&count=50&output=atom
  returns 50 `<entry>` elements, or count=30 returns 30. Or
  getcurrent&type=13F-H returns only one distinct `<category term=...>` value.
so_what: >
  Never treat "EDGAR returned fewer entries than I requested" as "the feed ran
  out" unless the request used an honored page size — a pager that infers
  end-of-feed from a short page will silently truncate and report itself
  complete. Ask only for 10/20/40/80/100, and advance the cursor by the
  entries actually served, not the count requested. A `type=` filter is also
  not a guarantee of exact form: client-side form filtering must never feed a
  paging or completeness decision.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  Read-only curl probes of action=getcurrent&type=13F at start=0 across
  count=10,15,20,30,39,40,41,50,79,80,81,100,101,200 and at start=700 count=50
  (served 40) and start=900 count=30 (served 20); prefix behaviour from
  getcurrent&type=13F-H (83 x 13F-HR + 17 x 13F-HR/A) and 13FCONP from
  getcompany&CIK=0001067983&type=13F. Encoded as ATOM_HONORED_PAGE_SIZES in
  engine/institutional_census/sec_sources.py by PR #5854.
scope:
  - macro
  - engine/institutional_census/sec_sources.py
  - engine/institutional_census/rolling.py
confidence: verified
---

Found while confirming a chipped latent bug in `scan_latest_filings_atom`. The
chip named the form filter as the cause — real, but rare. The dominant trigger
was this rounding: production runs `--max-accessions 750`, so the tail page
asked for 50, received 40, and returned `complete=True` on a truncated scan.
Both triggers produced the same silent green receipt, which is why the lane
never reported the gap.
