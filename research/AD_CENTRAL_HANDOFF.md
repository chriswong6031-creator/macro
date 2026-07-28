# Ad Central — handoff

**Written 2026-07-27** for whoever picks this up next (different account/session).
Plan: `research/AD_CENTRAL_MASTERPLAN.md`. Program state: everything below is merged
and live unless marked otherwise.

---

## §0 ACCEPTANCE GATES — read before you touch anything

These are inline on purpose. A masterplan pointer is context; these are the contract.

**H-1 — No ad runs without the operator's approval.** `ad_arena.create(mode="live")` and
`ad_arena.arm()` RAISE unless every arm has an approval on record
(`engine/marketing/ad_review.py`). There is no bypass flag and you must not add one.
`pause()` never needs permission. A standing test asserts nothing in the shipped ledger is
live un-reviewed. **This law exists because it was broken:** a landing-hero test went live
on un-reviewed copy and served it to real visitors.

**H-2 — A rejection carries a reason.** `record(..., "rejected")` raises without one. The
reason is the only training signal the system gets about taste. `ad_review.taste_notes()`
is that corpus — **read it before generating anything new.** A system that re-proposes what
was already rejected has not learned; it has been outvoted twice.

**H-3 — The browser and the engine must agree on assignment.** `templates/adtest.js::hashUnit`
and `engine/marketing/ad_arena.py::_unit_hash` are one algorithm in two languages. If they
drift, visitors are counted in one arm and shown another, and **nothing goes red** — every
number stays plausible while measuring noise. Change both or neither.
`tests/test_marketing_ad_plane_o.py` pins it three ways. Changing the hash invalidates every
arena that has already assigned a visitor.

**H-4 — Only the words change.** Both arms of a copy test must use identical markup. A test
that changes two things measures neither. Enforced by a test.

**H-5 — Denominators are assignment-time.** `Arm` has `assigned`/`converted` and deliberately
no "survivors" field. An outcome from a never-assigned unit is an anomaly, not a conversion.

**H-6 — Money needs three independent switches** (`paid_enabled` × envelope × operator arm).
Any one off ⇒ dry run. Nothing has ever spent a cent.

---

## Where it stands

| Piece | State |
|---|---|
| Spine: creative → matrix → arena → stats → allocator | merged, live, **armed off** |
| Browser assignment (`adtest.js`), parity-pinned | merged, live |
| Nightly ingest `analytics_events` → arena ledgers | merged, deployed |
| Admin panel → Marketing → Ad Central | merged, live |
| Landing hero arena `hero-promise-vs-receipt` | **PAUSED** (`planned`/`shadow`) |
| Round-1 ads (6) | **ALL REJECTED** by the operator |
| Approved ads | **none** |

The hero arena is paused, not concluded. Its two creatives
(`adc-a929e26ce95c` control = the copy that ships, `adc-67661666832f` receipt variant) have
no approval, so it cannot be re-armed without one.

---

## What the operator asked for

Two core marketing points, both verified as real shipping surfaces:

1. **Call signals** — quality picks backed by context: trending and bottoming sectors,
   insider/congress flow, institutional positioning, and **precise entry points**.
2. **Breadth** — insider & congress trades, institutional 13F smart money, theme tracking
   and theme *rotation* tracking, event trades, the call signals, the free professional
   Terminal charting suite, and the Mastermind AI chat.

Also: **ads must be shown to the operator as designed visuals**, not copy lines — "beautiful
illustration and design", reusing elements from the site / `start.html`.

**One claim could NOT be substantiated:** "hundreds of core contextual data points." I found
34 distinct context keys, not hundreds. Do not put a number in an ad you cannot defend if
someone asks where it comes from — name the concrete desks instead. If the operator supplies
a real source for a count, use it.

---

## Round 1: rejected — what to learn from it

Committed reference (the actual ads as reviewed, open it in a browser):
**`mockups/refs/ad_central/round1_rejected.html`**

Six ads across two concepts (call-signal quality; desk breadth), rendered at real placement
sizes in the product's own tokens and typeface. Operator verdict:

> rejected as a set — *"not robust enough to even be considered for live split testing"*

**The per-ad reasons are still owed.** The operator flagged that each has its own reason but
did not enumerate them before handing off. A generic "missed the bar" tells you the bar was
missed, not *where*, so it is a weak entry in the taste corpus. **Ask for the specifics
before generating round 2** — otherwise round 2 is a guess wearing the costume of a revision.

What I would ask about first, based on what these ads did:
- the illustration used an **invented** signal (AVGO, entry 184.20 / invalidates 176.80).
  Should ad visuals use *real* recent calls from the track record instead? That is a
  materially different — and more defensible — ad.
- "Eight terminals' work" is an unbacked comparison. Which competitors, and can we say so?
- the breadth concept lists features; the operator may want the *outcome* of breadth, not
  the inventory.

---

## The measurement chain, end to end

```
adtest.js  picks an arm from a local id, rewrites [data-adtest-slot], beacons /api/collect
   ↓        (server stamps visitor_id from the httpOnly mm_aid cookie — the client
   ↓         chooses the arm, never its own identity)
analytics_events (Supabase)
   ↓        scripts/ad_ingest_run.py, nightly step in daily.yml
data/marketing/ad_central/{assignments,outcomes}.jsonl   ← forward-only, nightly is sole advancer
   ↓
ad_arena.tally → ad_stats.analyze → verdict (separated | equivalent | null | seeding)
```

Traps that already bit, all silent:
- the landing does **not** load `theme.js`, so `window.mmTrack` does not exist there — the
  shim beacons directly. Do not "simplify" it back to mmTrack.
- the landing's language switcher caches the English in `el.__en` on first run; the shim
  clears it, or one zh→en toggle restores the control copy under a variant assignment.
- the render lane rewrites the loader to `adtest.js?v=<hash> defer`. Do not assert the exact
  unstamped tag — and do not read "absent" off a grep that misses the stamped form.

---

## If you are generating round 2

1. Read `ad_review.taste_notes(root=".")` first. All six current entries are the same
   generic verdict — get specifics from the operator before you spend effort.
2. Build creatives with `ad_creative.build(...)`; it refuses over-limit copy rather than
   truncating, and refuses factual/directional/causal claims with no passport.
3. Render them as designed visuals and **show the operator** — the product's own tokens live
   in `site/landing.css` (`--blue:#285fff`, `--violet:#7862e0`, `--ink:#1c2430`), typeface is
   self-hosted Inter in `site/fonts/`. Committed example of the render:
   `mockups/refs/ad_central/round1_rejected.html`.
4. Record the operator's decision with `ad_review.record(...)`. Only then can an arena be armed.
5. Never set `arena.status`/`arena.mode` by hand — use `ad_arena.arm()`, which is the
   transition with the gate attached.

## Open, unowned

- **Per-ad rejection reasons for round 1** — blocks a well-aimed round 2.
- Whether ad visuals should use real graded calls instead of invented ones.
- `test_world_state.py::test_determinism` is intermittently red in `ci-pack-1` and blocks
  unrelated PRs; a separate session was started on it 2026-07-27.
- The render lane adds `defer` to the shim loader, which delays the swap past first paint.
  Revisit before the next live arena.
