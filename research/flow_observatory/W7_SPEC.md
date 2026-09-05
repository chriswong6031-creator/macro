# W7 frozen spec — product-learning instrumentation

`child: macro-flow-observatory-v2-w7-product-learning-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §11, packet W7`
`design authority: this spec. Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. Flow Observatory interactions are measurable through the EXISTING first-party
   `/api/collect` beacon only (templates/theme.js's envelope) — no second transport, no
   Umami custom events, no new analytics plane.
2. Events are typed, documented, deduplicated, and privacy-clean (no holdings, no
   research text, no PII; group ids and lens names only).
3. Telemetry never changes flow state or authority; the page renders identically with
   the beacon blocked (test JS-off / beacon-failure indifference).
4. A live canary receipt exists post-merge (one real event observed end-to-end).
5. Targeted suites green; contract-delta 0 introduced (the wiring meta-test already
   guards the flow lane — any new suite must satisfy it); canonical rebuild committed;
   PR DRAFT/unlabeled; tree clean.

## 1. Event schema (frozen)

All events ride the existing collect envelope with `t: "flowobs"` (or the envelope's
nearest existing type-field convention — read theme.js's actual envelope FIRST and
reuse its field names exactly). Payload fields: `ev` (enum below), `lens`
(theme|sector|aggregate|null), `id` (group/entity id or null), `sess` (the page's
market_session string), plus whatever session/page fields the envelope already carries
automatically. NOTHING else.

| ev | fired when |
|---|---|
| `trust_open` | a trust-strip chip's LENS tip opened via hover/focus/tap (amended post-#6815 review: not click — the LENS controller never opens on click, and a mobile tap's click event can be retargeted away from the chip by the sheet scrim) |
| `changed_expand` | the what-changed section's overflow details is opened |
| `quadrant_select` | a quadrant-cell chip is clicked |
| `group_drill` | a group row is expanded (either lens) |
| `history_open` | a history drawer is opened |
| `compare_run` | a same-lens compare renders |
| `episode_view` | an episodes panel becomes visible (first per group per pageview) |
| `terminal_out` | a member Terminal link is clicked |
| `watch_note_view` | the watch-limitation note becomes visible (first per pageview) (amended post-#6815 review: the note is a static always-visible paragraph with no LENS tip to open — this is an impression event, like `episode_view`, not a click) |

Dedup: per (ev, id) per pageview (a Set in page JS). Fire-and-forget (sendBeacon or
the envelope's existing transport; never block interaction; no retries).

## 2. Implementation

- One small JS block in templates/flow_velocity.html.j2 (page-scoped, event-delegation
  on the existing DOM hooks — add data-ev attributes where a stable hook is missing).
  No new files, no runtime CSS, no framework.
- Success-metric definitions (documented in the PR body + a short
  docs/site_semantics/china.md addendum, NOT new UI): time-to-first-drill proxy
  (pageview→first group_drill), evidence-inspection share (trust_open or history_open
  per pageview), terminal handoff rate, degraded-day engagement (events per pageview on
  publication_state != HEALTHY days — computable server-side later from the sess field
  + the ledger; no new storage now).
- Server side: NOTHING (the /api/collect endpoint and analytics_events store already
  exist and accept arbitrary typed events — VERIFY this by reading the endpoint's
  handler; if the handler whitelists event types, add `flowobs` to the whitelist in the
  same PR and note it — that file becomes an OWNED file in that case).

## 3. Tests (extend tests/test_flow_observatory_workflow.py or a new small suite —
if new, the meta-test forces the wiring)

1. every data-ev hook renders in the page for each event type (rendered-HTML asserts);
2. the JS block contains a dedup structure and uses the existing envelope call (source
   asserts — no second transport URL);
3. no payload field beyond the frozen schema (source assert on the payload builder);
4. page renders + interacts with the beacon stubbed to throw (indifference test via
   the existing render harness);
5. no banned vocabulary introduced; EN/ZH untouched (this wave adds no visible copy
   except nothing — assert the visible-text diff is empty);
6. mutation M1: add a forbidden field (e.g. a member ticker list) to the payload
   builder → test 3 fails (paste output).

## 4. Live canary (post-merge, principal-owned)

After merge + VPS pull: open the live page, trigger one `group_drill`, and verify the
event landed (via the analytics store's existing read path or server logs — whatever
access exists; if no read access exists from this seat, the canary receipt is the
beacon's 2xx response observed in the browser network log, recorded with a screenshot).
