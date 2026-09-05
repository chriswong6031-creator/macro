---
key: SLACK-INBOUND-WATERMARK-EXCLUDES-OWN-POSTS
claim: >
  A Slack-thread reader that derives its next `oldest` boundary from its own most recent outgoing
  post can omit an already delivered inbound relay from later incremental reads. In A1, the
  `oldest` value taken from the worker's own latest post kept Secretary relay
  `1788593042.348469` invisible across two `NO_NEW_EDGES` checks. Worker receipt
  `1788593776.233029` is the successful corrective consumption/admission of that relay, not the
  earlier failed-read boundary. Separately, the F1 release decision `1788592894.675119` was
  missed because the worker had not opened its original F1 root `1787975946.019219` and had
  substituted an exhaustive Git census plus a stale #6868 description for carrier authority;
  it was later directly read.
falsifier: >
  Re-read the original A1 carrier `C0BSBM78V1N/1788590913.182019`, its F1 root
  `1787975946.019219`, and the exact worker receipt `1788593776.233029`. This discovery is
  falsified if that carrier does not establish that the reader used its own latest outgoing post
  as `oldest`, or if it proves that the A1 relay `1788593042.348469` was consumed by this target
  during either earlier `NO_NEW_EDGES` check without the corrective read. The F1 authority half
  is falsified if the carrier proves the F1 root was opened and its release decision was consumed
  before the later direct read.
so_what: >
  When an existing authorized carrier-read surface retains inbound-consumption or read evidence,
  anchor incremental overlap to that inbound evidence rather than an outbound-post timestamp.
  Otherwise, use the existing carrier's bounded reconciliation path. If evidence shows an edge
  was skipped, report the earlier target read as incomplete; do not retrospectively claim timely
  consumption of that edge. This finding does
  not authorize a new watcher, cursor store, control plane, queue, scheduler, policy, or Slack
  lifecycle state.
kind: landmine
verified_at: 2026-09-05
verified_by: >
  Root's `slack_read_thread(limit=100)` read of all 11 replies with pagination exhausted for A1
  carrier `C0BSBM78V1N/1788590913.182019`. Its successful corrective worker receipt
  `1788593776.233029` records two prior `NO_NEW_EDGES` reads using the worker's own latest post
  as `oldest`, identifies Secretary relay `1788593042.348469`, and attests the worker's later
  direct read of original F1 root `1787975946.019219` and release decision `1788592894.675119`.
  Root verified that attestation in the full A1 carrier; it did not independently read F1's root
  for this discovery.
scope:
  - WS:CHAIRMAN-CONTROL-ROOM
  - C0BSBM78V1N
  - Slack thread reads
  - active-session dialogue
confidence: verified
---

## Causal boundary

The failure is not that Slack transport became canonical, nor that a browser session was proven
awake. It is narrower: an outbound timestamp was used as an inbound low watermark. In the
observed A1 sequence, the relay had been delivered but remained unconsumed by this target across
two `NO_NEW_EDGES` reads because it was older than the synthetic boundary. Receipt
`1788593776.233029` records successful later corrective consumption/admission. It cannot make
the earlier reads timely consumption of that relay.

The missed F1 release has a separate cause. The worker did not open the original F1 root and
substituted an exhaustive Git census and stale #6868 description for carrier authority. The later
direct read of the F1 root corrected that authority gap. This discovery does not assert that the
outbound-boundary defect hid the F1 release, that both messages arrived after one verified prior
read, or that Slack failed to deliver the relay. It also does not negate any separate worker ACK;
it concerns this target's skipped-edge consumption evidence.

## Boundary for future readers

Keep the transport and authority distinctions already established by
`DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`: a complete thread read is not runtime
visibility, and a transport correction is not a new execution authority. When the existing read
surface retains inbound-consumption or read evidence, use that evidence as the incremental overlap
anchor. Outbound messages may be evidence that a session spoke, but they cannot advance the
inbound-consumption boundary. Carrier authority must be read from the exact original root, not
substituted by a Git census or stale PR description.

If existing inbound evidence is unavailable, an incremental read cannot establish that earlier
edges were consumed; use the existing carrier's bounded reconciliation path. A completed full
carrier reconciliation does not require a new persistent watermark. Do not backfill timely consumption of the
skipped edge, infer the original-root decision was seen, replace the original task/carrier, or
add a persistent cursor, watcher, queue, scheduler, policy, or control plane to compensate.

## Duplicate boundary

This finding is distinct from `DEC:SLACK-IS-EVENT-TRANSPORT-NOT-RUNTIME-DELIVERY`, which assigns
Slack's transport-only role, and from
`DSC:SHARED-GITHUB-REST-BUDGET-MAKES-PER-SESSION-WATCHERS-A-FLEET-OUTAGE`, which prohibits
per-session watcher amplification. `DSC:DELETE-BEFORE-ACK-NEEDS-AN-IN-FLIGHT-ASSERTION` is an
ordering-test lesson for a durable outbox, not an A1 inbound-watermark fact. None describes an
outgoing Slack post excluding an already delivered inbound relay from a later target read, paired
with a distinct failure to open the original authority root.
