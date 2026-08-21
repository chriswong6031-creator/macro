---
key: RADAR-SPOOL-PUBLIC-R2
claim: >
  The Entry Radar Lab's canonical evidence spool is anonymously readable on
  the public R2 dev host: an unauthenticated GET of
  live_flow/entry_radar_events/2026-08-20/115834-entry_radar_live.json (the
  Day-4 commissioning envelope) answered HTTP 200 on
  pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev (2026-08-21). Spool keys are
  dated and pattern-guessable (live_flow/entry_radar_events/<YYYY-MM-DD>/
  <HHMMSS>-entry_radar_live.json), so the whole observation stream — quote
  coverage, lifecycle transitions, radar events, basis audits — is
  effectively public even though the bucket does not allow anonymous listing.
  The writer and the Lab reader both use authenticated boto3, but the bucket
  (mastermindx) is the same one exposed by the public dev URL, so every
  non-curated key written to it is world-readable.
falsifier: >
  An anonymous GET of a known spool key returning 403/404 (public dev URL
  disabled for the prefix/bucket, or the spool moved to a private bucket)
  retires this. A ruling that radar envelopes are deliberately public-tier
  would retire the concern half but must square with the Lab's
  evidence-plane privacy assumptions.
so_what: >
  Escalation for the WS:LIVE-ENTRY-RADAR owner and the R2 delivery-plane
  migration program — NOT fixed in the B1 wave (Sol scoped B1 to the Prophet
  index). Any future private artifact written to the mastermindx bucket
  inherits this exposure; the structural fix is a private bucket or a
  scoped public-access configuration, which belongs to the delivery-plane
  migration (config/r2_delivery_plane_classification.v1.json) rather than a
  per-key patch.
kind: constraint
confidence: verified
verified_at: 2026-08-21
verified_by: "anonymous curl -H 'User-Agent: mastermind-audit/1.0' https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/live_flow/entry_radar_events/2026-08-20/115834-entry_radar_live.json → HTTP 200"
scope:
  - "macro"
related:
  - "WS:LIVE-ENTRY-RADAR"
  - "DSC:PROPHET-INDEX-PUBLIC-R2-TWIN"
---

Found incidentally during the Day-5 B1 census while proving which planes the
public dev URL exposes. Recorded so the Radar owner and the delivery-plane
program inherit it explicitly; the B1 wave changes nothing about this spool.
