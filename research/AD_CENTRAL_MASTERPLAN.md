# Ad Central — masterplan

**Owner department:** `growth_science` (arena + statistics) × `studio` (creative) × `growth_os` (budget)
**Status:** Phase 1 landed — spine built, shadow mode, no spend.
**Created:** 2026-07-26

---

## §0 ACCEPTANCE GATES (read first; a phase is not done unless every gate is green)

Every phase below carries these. A masterplan pointer is context, not enforcement — these
gates are the contract, and they belong inline in any spawn prompt that continues this work.

**G-A — Money never moves without three independent arms.** No adapter may spend unless
ALL of: `settings.paid_enabled: true` in `config/marketing.yml`, a non-zero
`ad_central.envelope.daily_usd`, AND an operator arm action (the `arm_publisher` idiom).
Any one of the three off ⇒ dry-run. A test asserts the triple-gate; deleting the test is
deleting the gate.

**G-B — Denominators are assignment-time.** Every rate in every verdict divides by units
**assigned**, never by units that survived to the outcome. Outcome-conditioned denominators
delete losers and manufacture lift. A test feeds an arena where the losing arm bleeds units
before conversion and asserts the verdict does NOT flip.

**G-C — The null is the control, and it is printed.** No arena declares a winner against
0.5, against a fixed prior, or against nothing. Every verdict names the control arm's
posterior and prints the null result when there is one. "No arm separated" is a first-class,
displayed outcome — not an empty panel.

**G-D — N-floor before any verdict.** Below `ad_central.n_floor` (default 100 assignments
per arm) the verdict is `seeding` and NO arm is declared, promoted, killed, or scaled.
Matches the existing `telemetry.py` `_N_FLOOR` law.

**G-E — The primary metric is frozen at arena creation.** Secondary metrics are labeled
`exploratory` and can never trigger a stop, a kill, or a budget shift. A test asserts a
stop rule reading a secondary metric raises.

**G-F — Every claim in every ad carries a passport.** An ad creative whose claim has no
`claim_passport_id` is refused at build time, not at review time. The word "validated"
stays CI-forbidden in ad copy (`scripts/check_validated_claims.py`).

**G-G — Determinism.** No RNG anywhere in the spine. Same arena + same ledger ⇒ byte-identical
allocation and verdict. (Thompson allocation is computed in expectation — probability
matching by quadrature — precisely so no seed is needed.)

**G-H — Budget conservation.** Allocations sum to ≤ the envelope, every arm ≤ its per-arm
cap, every live arm ≥ the exploration floor until it clears the n-floor. Asserted as an
invariant over randomized posteriors, not a spot check.

**G-I — Nightly is the sole advancer.** Arena ledgers are forward-only and advanced by the
nightly lane. Intraday callers may read; writes from an intraday lane are discarded.

**Phase-specific visual gate (Phases 2+):** any operator- or user-facing surface ships with
per-state crops (light + dark, EN + ZH where applicable) posted in the PR body.

---

## §1 What was missing

The marketing lobe can *say* things and cannot *test* them. 48 modules / 27k lines run
opportunity → campaign → copy → sentinel gate → outbox → publish → telemetry. But the three
objects that would close the loop are seed-state placeholders:

| Object | State before Ad Central |
|---|---|
| `Experiment` (`experiments.py`, 55 lines) | bare dataclass — no runner, no assignment, no statistics. 0 running. |
| `Campaign` (`campaign_compiler.py`) | dataclass + a Jaccard distinctness check. 1 shadow campaign, `budget_envelope: {total_usd: 0}`. |
| `BudgetAllocator` (`economics.py`) | equal weights across 11 departments; every envelope `$0`. |

`economics.retained_contribution` already subtracts a `paid_media_cost` term — the P&L was
written for a paid lane that was never built. Ad Central is that lane, plus the free lanes
that should be exhausted first.

## §2 The shape — one spine, three planes

The spine is plane-independent. A creative that wins on a free plane is promoted to a paid
plane with the same id, the same passport, and the same arena machinery.

```
opportunity ──► ad_creative ──► ad_matrix ──► ad_arena ──► ad_stats ──► ad_allocator
               (typed ad)      (fan-out)     (split test)  (verdict)    (budget)
                                                  │
                        ┌─────────────────────────┼─────────────────────────┐
                     Plane O                   Plane G                   Plane P
                owned inventory           organic pre-screen          paid inventory
             (site copy; $0 spend)      (X desks; $0 spend)        (adapters; armed off)
```

**Plane O — owned inventory.** Landing hero, headline, CTA, pricing and regwall copy.
Assignment by deterministic hash of the visitor cookie; conversions measured in the existing
first-party analytics (`analytics_events` in Supabase, read by `admin/analytics_first_party.py`).
Zero external spend, zero credentials, no ad account. **Highest ROI in the whole plan** — it
raises conversion on traffic already paid for. Ships before anything paid.

**Plane G — organic pre-screen.** Arena arms ride the existing outbox → sentinel → publisher
path as distinct posts on the desk network; `telemetry.py` supplies impressions/engagement.
This is what "fan out to many ads on small budgets" looks like when the budget is **zero** —
angle screening at no cost, so paid dollars only ever buy confirmation, never discovery.

**Plane P — paid inventory.** Reddit / X / Meta / Google adapters behind the dry-run ladder.
Many arms at $5–20/day, allocated by probability matching, killed by CI-based rules. Built
in Phase 4, armed in Phase 5 behind G-A and an operator ruling.

## §3 The five modules

### `ad_creative.py` — what an ad *is*
A creative is `angle × hook × proof × cta × format × destination × claim_passport`. `format`
carries the placement's hard limits (char caps per field, media aspect, whether links are
permitted); assembly refuses rather than truncates a claim. Destination is a canonical
UTM-tagged link where `utm_content = creative_id`, reusing `links.py` — so the existing
attribution join (`attribution.py`, keyed on `utm_content`) already knows how to score it.

### `ad_matrix.py` — fan-out
Cross the dimension levels, drop pairs above the Jaccard ceiling (reuse `campaign_compiler`),
cap the matrix, and return a stable ordering. Fan-out without distinctness is buying the same
ad N times.

### `ad_arena.py` — the split test
Pre-registered primary metric, unit, arms, exploration floor, stop rule, guardrails.
Assignment is `hash(arena_id, unit_key) → arm`: stateless, reproducible, and workable on a
static site with no session store. Exposures and outcomes append to a forward-only ledger.
**Denominator is assignment-time** (G-B) — intention-to-treat, always.

### `ad_stats.py` — honest measurement
Beta-Binomial posterior per arm on a binary primary metric. Reports posterior mean, credible
interval, P(best), and lift-vs-control with an interval. Pure-Python regularized incomplete
beta (continued fraction) + bisection quantile — **no scipy**, because CI packs install
minimal deps and a `importorskip` "fix" would disarm the gate. Below the n-floor: `seeding`,
no verdict. When nothing separates: `null`, printed.

### `ad_allocator.py` — small budgets, many arms
Deterministic probability matching: allocate each arm the posterior probability that it is
best, computed by quadrature rather than sampled. This is Thompson sampling *in expectation*
with no RNG (G-G). Subject to exploration floor, per-arm daily cap, total envelope, and a
kill rule (arm retired when its CI upper bound sits below the control's posterior mean at
n ≥ floor). Budget conservation is an invariant (G-H).

## §4 Phase ladder

| Phase | Delivers | Spend | Gate to advance |
|---|---|---|---|
| **1** ✅ | spine + contracts + tests + admin read surface, shadow mode | $0 | G-B…G-H green |
| 2 | Plane O live — site variant assignment + first-party conversion join, nightly-advanced | $0 | one arena reaching n-floor with a printed verdict (winner *or* null) |
| 3 | Plane G live — arena arms through the outbox | $0 | ≥3 arenas concluded; angle-level priors accrued |
| 4 | Plane P adapters, dry-run only | $0 | dry-run parity: adapter plan == what would ship |
| 5 | Plane P armed | capped | operator ruling + G-A triple gate |

## §5 Standing laws this plan inherits

- **Epistemics.** Ad Central is display/accrual tier. It may build, fan out, and accrue
  freely; a null never blocks building. The gauntlet applies only when a *finding* is
  promoted to authority (e.g. "this angle converts" becoming a permanent copy law).
- **Nightly is the sole advancer** of the arena ledgers (G-I).
- **Sentinel still gates.** Every arm on Planes G/P passes the existing policy gate. Ad
  Central adds arms; it does not add a bypass.
- **No `validated` in ad copy** (CI-enforced). Bilingual EN/ZH where the surface is bilingual.
- **Design.** Operator console follows the existing marketing-panel idiom; any user-facing
  surface (Plane O copy) goes through `docs/DESIGN_DOCTRINE.md` + the frontend-design skill.

## §6 Deliberately not built

- **Ad account creation, credential entry, or payment setup.** Out of scope by policy — the
  operator does this in each platform's own UI; Ad Central reads keys from the environment.
- **Creative image generation.** `share_cards.py` + `chart_render.py` already produce the
  house visual; ad formats reuse them rather than growing a second renderer.
- **Cross-platform identity resolution.** First-touch UTM only, opaque `user_ref`, no PII —
  the privacy law in `attribution.py` stands.
