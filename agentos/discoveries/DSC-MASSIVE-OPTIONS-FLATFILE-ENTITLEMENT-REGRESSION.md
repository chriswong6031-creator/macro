---
key: MASSIVE-OPTIONS-FLATFILE-ENTITLEMENT-REGRESSION
claim: >
  On 2026-08-20 the production Massive S3 credential can list the exact OPRA minute
  aggregate objects for 2026-08-14, 2026-08-17, 2026-08-18, and 2026-08-19, but a
  ranged GET of every object returns HTTP 403. The same endpoint, bucket, access key,
  signing configuration, and request path can list and ranged-GET the 2026-08-19 US
  stocks SIP day aggregate (HTTP 206 with gzip bytes). The Options day aggregate for
  that session also lists but returns 403. This is therefore a dataset-specific Options
  flat-file authorization or entitlement regression, not missing configuration, an
  invalid key, endpoint/transport failure, unpublished objects, a discovery/parser bug,
  or the separate REST Options Snapshot entitlement failure.
falsifier: >
  Run collectors.massive_flatfiles.probe_available("minute", end_date=date(2026,8,19))
  with the production closing-bell credential and receive reason=available with a
  non-null date; then ranged-GET that exact OPRA object and observe HTTP 200/206 with
  gzip bytes. That proves the dataset grant was restored or the credential changed and
  this discovery's operational block no longer applies.
so_what: >
  Do not change the provider, object path, parser, signing version, calendar, or flow
  arithmetic to work around this 403. The owner/vendor must restore or bind the Options
  flat-file aggregate grant to the production S3 key and confirm commercial rights.
  After restoration, rerun the same secret-safe differential probe, then let the normal
  Options Flow producer publish the next lawful session; do not reconstruct the missing
  sessions. PR #6074 already makes the publication lane fail nonzero and retain the last
  useful artifact while this source is unavailable.
kind: constraint
verified_at: 2026-08-20
verified_by: >
  Production-venv probe using the closing-bell .env through
  scripts.close_pass_host_runner.load_env_file (values never printed), calling the exact
  collectors.massive_flatfiles key/client/probe_available path. All four OPRA minute
  objects listed with nonzero sizes and ranged GET returned HTTP 403; probe_available
  returned authorization_or_entitlement_failure and latest_available returned None.
  A same-credential 2026-08-19 differential returned Options minute 403, Options day
  403, and stocks day HTTP 206 with gzip magic 1f8b. M1 copies of the two production
  flow envs independently returned the same Options-403/stocks-200 differential.
scope:
  - macro
  - options-intelligence
  - collectors/massive_flatfiles.py
confidence: verified
workstream: "WS:ADVANCED-DATA-OPTIONS"
evidence:
  - "2026-08-14 OPRA minute: listed size 25,741,176; range GET HTTP 403"
  - "2026-08-17 OPRA minute: listed size 25,693,894; range GET HTTP 403"
  - "2026-08-18 OPRA minute: listed size 24,225,530; range GET HTTP 403"
  - "2026-08-19 OPRA minute: listed size 26,319,507; range GET HTTP 403"
  - "2026-08-19 differential: Options day listed size 4,146,965 / GET 403; stocks day listed size 323,206 / GET HTTP 206 / gzip 1f8b"
  - "PR #6074 merge 9fca6705597f7ff958960e1078b36736da36c5db: source failures are publication failures and stale artifacts retain no current authority"
---

This credential lane is distinct from DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION.
The flat-file S3 key and the REST API key can fail independently; a restoration claim
for one is not evidence for the other.
