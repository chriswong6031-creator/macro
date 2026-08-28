---
key: OFFICIAL-SOURCE-403-TO-A-BARE-PROBE-CARRIES-NO-SIGNAL
claim: >
  A 403 returned to an unauthenticated curl with a browser user-agent tells you nothing about
  whether an official .mil/.gov source is collectable by this repository, because dsca.mil and
  sec.gov — both provably collected in production — return exactly the same 403 to that probe.
falsifier: >
  `curl -s -o /dev/null -w '%{http_code}' -A '<browser UA>' https://www.dsca.mil/press-media/major-arms-sales`
  returning 200. If the sources this repo demonstrably collects answer a bare probe, then a 403
  from another official source would again be informative and this claim is refuted.
so_what: >
  Never grade a candidate source's feasibility with a bare HTTP probe, and never record a rail
  as infeasible or REJECTED_BY_DESIGN on that evidence — the conclusion is void and will kill a
  buildable rail. Grade feasibility by reproducing the request with the acquisition discipline
  collectors/fms_notifications_live.py already uses, and run it from the runner rather than a
  developer host. Conversely, budget for that discipline up front when a rail targets a
  WAF-protected official source.
kind: landmine
verified_at: 2026-08-27
verified_by: >
  Read-only probes from the developer host, one browser UA, single request each —
  403: gao.gov/bid-protest-docket/search, gao.gov/legal/bid-protests, gao.gov/api/products,
  dote.osd.mil, dodig.mil/Reports, api.www.sbir.gov/public/api/awards, www.dsca.mil, www.sec.gov;
  200: gao.gov/rss/reports.xml, api.usaspending.gov, federalregister.gov/api/v1, example.com.
  DSCA is collected by the Sol-accepted PROVEN_LIVE D6-B rail
  (collectors/fms_notifications_live.py:255,312,334).
scope:
  - macro
  - government-revenue-foresight
  - collectors/
confidence: verified
---

The probe was run to grade source feasibility for the remaining D6 rails and produced a clean,
plausible, and wrong story: GAO, DOT&E, DoDIG and SBIR all refused, so all four looked
infeasible. Running the same probe against sources the repository already collects refuted it —
`dsca.mil` and `sec.gov` refuse identically, while `api.usaspending.gov`,
`federalregister.gov/api` and `example.com` answer 200. Egress is healthy; the probe simply has
no power against the WAF-protected class.

What survives is a narrower and genuinely useful fact: **`.mil`/WAF-class official sources
refuse naive server-side acquisition**, so a rail targeting them must budget for real
acquisition discipline rather than a plain GET. That discipline already exists in this
repository and is the reusable asset — `collectors/fms_notifications_live.py` carries a
`requests.Session()` with full browser headers for `state.gov` (`:503-507`) and a bounded
browser-transport archival replay for DSCA recorded as
`transport="browser_in_page_fetch_staged"` (`:255`, `:312`, `:334`), staging the fetched objects
under `data/government_revenue/fms_staged_objects/`.

Note the accompanying law, which the 200/403 split makes concrete: the Federal Register API is
open and machine-readable and serves as the **population authority**, while the WAF-protected
web surface is observational enrichment only. A rail with no open population authority is
blocked by that law regardless of how good its acquisition discipline is.

Related: [[DSC-GOVREV-SBIR-RAIL-IS-A-SHIPPED-COLLECTOR-ONLY-WAVE]].
