---
key: TERMINAL-QUOTE-DEMAND-IS-PLANNED-NOT-CAPPED
question: >
  Terminal's live-quote demand set can exceed `/api/quote`'s 200-symbol request cap
  (watchlists permit 500 symbols and composite rows expand into several quote symbols
  each). Should the cap be raised to cover the largest supported list, or should the
  client plan its demand to fit under the existing cap?
answer: >
  Plan the demand; keep the cap. terminal/lib/quoteDemand.ts splits the demand set into
  a PRIORITY group (the charted symbol and its composite legs, plus the movers strip)
  that rides EVERY poll, and a ROTATING remainder that walks the leftover capacity
  behind a carried cursor. One request per tick of at most the cap — identical to
  before — while every symbol is refreshed within ceil(rotating / capacity) polls
  instead of never. A demand set that already fits reports `complete`, does not drift
  its cursor, and behaves byte-for-byte as it did. The route keeps enforcing the cap but
  must now report `truncated: {requested, served, omitted[]}` rather than slicing in
  silence; a correct client never sees that field.
rationale: >
  Raising 200 -> 500 only moves the boundary: it is still a fixed number against an
  unbounded demand set (composites expand, and nothing prevents a larger list bound
  later), so the same defect returns at the new edge. It also triples one poll's
  upstream fan-out — the quote hub chunks at 100 and Tencent at 30, so 500 symbols is
  ~5 + ~17 provider requests every 6 seconds — and pushes a GET query string toward URL
  limits. Rotation gets FULL coverage at the SAME request volume, which is the property
  actually wanted: the invariant is "no symbol is permanently excluded because of its
  position", not "every symbol is fresh every tick". Freshness is already tiered in this
  product (the visible-chart fast lane polls at 1s, the wide batch at 6s), so a bounded
  staleness for off-priority rows is consistent with the existing model rather than new.
  Demand is grouped by ROW rather than flattened because a composite is only correct when
  ALL its legs are priced; groups are admitted whole so rotation can never split one and
  leave a row summing a fresh leg against a stale one.
alternatives:
  - option: Raise MAX_BATCH to 500 to cover the largest supported watchlist
    why_not: moves the boundary instead of removing it, triples per-poll provider fan-out (hub chunks 100, Tencent 30), and grows the GET toward URL limits; composites make the true symbol count unbounded above the row count anyway
  - option: Client-side chunking — send ceil(n/200) parallel requests per poll
    why_not: full coverage but request volume scales with list size, which is exactly the upstream load the cap exists to bound; a 500-name list would issue 3 batches every 6s against providers that already chunk internally
  - option: Viewport-visible prioritisation (poll on-screen rows fast, off-screen slowly)
    why_not: better UX and explicitly allowed by the handoff, but requires IntersectionObserver plumbing on watchlist rows that collides with concurrent Handoff-A work there; rotation alone satisfies the required invariant with zero added request volume. Deferred, not rejected.
  - option: Body-based batch transport (POST) to escape URL-length limits
    why_not: solves only the URL bound, not the fan-out bound, and changes a cached GET surface for no coverage gain
affects:
  - terminal
  - "DSC:TERMINAL-QUOTE-DEMAND-SILENT-SLICE"
evidence:
  - "mastermind-terminal PR #429 (terminal/lib/quoteDemand.ts, app/api/quote/route.ts, components/TerminalShell.tsx, components/PortfolioView.tsx)"
  - "terminal/lib/__tests__/quoteDemand.test.ts — 16 tests incl. the asserted before/after measurement (117 of 317 symbols never requested -> 0)"
  - "terminal/lib/__tests__/quoteRouteTruncation.test.ts — 5 tests pinning the truncation contract"
  - "terminal/e2e/quote-demand-coverage.spec.ts — real browser, real 300-symbol watchlist; both specs fail with the flat silent slice restored"
scope: [terminal]
status: accepted
confidence: high
reversibility: easy
decided_by: claude-opus-5-session-d
decided_at: 2026-08-19
---

## Detail

The decision worth remembering is not "we added rotation" but **where the fix belongs**. The
instinct on meeting "the cap is too small" is to enlarge the cap. That is almost always wrong when
the demand set has no upper bound of its own: it converts a permanent defect into a deferred one,
and it pays for the deferral in load.

Two degenerate cases are handled explicitly in the planner, because each would otherwise starve a
symbol forever — reintroducing the exact bug in a rarer shape:

- a **priority set larger than the whole budget** is admitted in order, so the charted symbol (first)
  survives rather than being cut arbitrarily;
- a **single group larger than the whole budget** is served partially and stepped past, rather than
  parking the cursor on it so every group behind it starves. A composite has a handful of legs, so
  this is theoretical today — but a cursor that can park is a permanent silent stall, and the cost of
  preventing it is four lines.

The truncation report on the route is deliberately kept even though the in-product caller now plans
under the cap and should never trigger it. It is defence in depth for a future consumer, and more
importantly it converts the failure mode from "invisible" to "loud" — which is the property whose
absence made the original defect survive.
