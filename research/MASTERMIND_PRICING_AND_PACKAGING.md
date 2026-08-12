# Mastermind-X — Pricing & Packaging (V1)

**Status:** RECOMMENDATION, 2026-08-12. Companion to `MASTERMIND_COMMERCIAL_ARCHITECTURE.md`.
**Current catalog traced from `config/plans.yml`; nothing below is inferred from marketing copy.**
**Optimizing for** conversion × retention × perceived value × long-term revenue — explicitly
**not** short-term ARPU.

---

## 1. Where pricing stands today

| Product | Monthly | Annual | Annual $/mo-equiv | Discount vs monthly | Trial |
|---|---|---|---|---|---|
| Essential | $99 | $900 | $75 | 24% | 0 days |
| Pro | $149 | $1,308 | $109 | 27% | 7 days, card required |
| Founding Pro | — | $900 | $75 | 31% off Pro annual | inherits Pro |

Founding Pro: `max_redemptions: 2000`, `duration: forever`, `public_count_threshold: 25`,
and an `allotment_pacing` block that withdraws 2 seats per day from a baseline of 244
unavailable as of 2026-07-27.

**Two structural facts about this table.**

**(a) Essential annual is dominated.** $900 buys either Essential-annual or Founding-Pro-annual,
and Founding Pro is a strict superset. This is intentional — the plans page says so
(`templates/plans.html.j2:490`, "every Pro feature at the Essential annual price") — but the
consequence is that **Essential's only live product is the $99 monthly**, while its annual row
still sits on the page with a working Subscribe button.

**(b) The founder discount is deep and permanent.** `duration: forever` at 31% off, across up to
2,000 seats, is a decision to cap long-run ARPU on a potentially large fraction of the eventual
base. That can be an excellent investment. At 2,000 seats it is an unexamined one.

---

## 2. PART XIX — Pricing verdicts

### 2.1 Is $149/month too high for first-purchase friction? — **No, and do not cut it.**

$99–149/month sits at the top of the retail intelligence band (Benzinga Pro $99–197, Koyfin
$39–99, Unusual Whales ~$48, TradingView Premium ~$60, Seeking Alpha Premium ~$25/mo annual).
It is defensible **only** if the product demonstrably compresses hours of work — which is
precisely the claim `…ARCHITECTURE.md` §5.4 says we should be making, and precisely the claim
the current packaging fails to make.

The friction at first purchase is **not the price level — it is belief**. A trader who believes
will pay $149 to find out; one who does not will not pay $49. The correct instruments for that
friction are the 7-day trial and the Day Pass (§4), not a discount.

**Do not add a discounted first month.** It would (a) teach the market the price is soft, (b)
attract exactly the freebie-hunters the handoff worries about, and (c) collide with the founder
story, which is our one legitimate discount.

### 2.2 Does $900 annual create sufficiently strong commitment economics? — **Yes, but the ladder is wrong.**

A 24–27% annual discount is at the low end of what pulls annual mix. More importantly, at
$1,308 the Pro annual reads as **$109/month**, which is above the psychological $99 line and
sits awkwardly close to the $149 monthly.

**Recommendation: a three-line reprice that removes the dominance instead of removing a product.**

| | Now | Recommended | Why |
|---|---|---|---|
| Pro annual | $1,308 ($109/mo) | **$1,188 ($99/mo, save 34%)** | $99/mo-equivalent is a threshold number; 34% is a badge worth showing |
| Essential annual | $900 ($75/mo) | **$828 ($69/mo, save 22%)** | **This is the fix for Finding A.** At $69 it is no longer priced identically to Founding Pro, so nothing is dominated and nothing has to be withdrawn |
| Essential monthly | $99 | **$89** (secondary) | Keeps the ladder monotone once Pro annual reads $99/mo: $89 < $99 < $149 |

The first draft of this document recommended *withdrawing* Essential annual instead. That was
worse on two counts. It is not a config edit — deleting `products.essential.prices.annual` makes
both builders default the missing `unit_amount` to `0` and the page renders "$0 /mo billed
annually", "Billed $0 a year", "SAVE 100% VS MONTHLY" with a live Subscribe button that then
400s. And it solved a pricing problem by deleting a product, when moving one number solves it
without touching the catalog's shape.

**The resulting ladder has no dominated cell and one obvious pull:**

```
Free  $0
Essential   $89/mo   ·  $828/yr  ($69/mo)
Pro        $149/mo   ·  $1,188/yr ($99/mo, save 34%)
Founding Pro          ·  $900/yr  ($75/mo, forever)
```

Founding Pro sits **$72/year above Essential annual** and gives the whole system, permanently.
That is the strongest honest nudge in the table, and it exists only because Essential annual
came down rather than going away.

**Cost:** ~9% lower Pro annual ARPU and ~8% lower Essential annual ARPU. **Expected return:**
annual mix — annual subscribers pay cash up front and churn at a fraction of monthly rates.
*Confidence: moderate. This is the recommendation I would most want revisited with 90 days of
mix data.*

**Cost:** ~9% lower annual ARPU. **Expected return:** annual mix. Annual subscribers pay cash up
front and churn at a fraction of monthly rates; a 10-point shift in annual mix is worth
substantially more than 9% of annual price. *Confidence: moderate. This is the recommendation in
this document I would most want to see revisited with 90 days of mix data.*

### 2.3 Should there be a low-friction first month? — **No.** See §2.1. The trial is that instrument.

### 2.4 Does a trial attract serious users or freebie hunters? — **Card-required trials attract serious users.** Keep MNZ-R9. See §4.

### 2.5 Should Free → paid depend on usage rather than a fixed trial? — **Both.** See §4.3.

### 2.6 Renewal expectations and grandfathering

- **Renewal is at the rate you bought at**, for as long as you stay subscribed, for founders
  (`duration: forever` — this is the entire promise, and breaking it once destroys the
  mechanism permanently).
- **Non-founder subscribers are not grandfathered by default**, but any price increase must give
  90 days' notice and must not apply mid-term. State this on the plans page *before* launch, not
  in a later email; a grandfathering policy discovered at renewal is a churn event.
- **Essential subscribers keep `terminal_live_options`** if that capability moves to Pro-only
  (`MASTERMIND_ENTITLEMENT_MATRIX.md` §6). Grandfathered by a feature key, never by a code branch.

### 2.7 Psychological positioning

The three-price shape should read as **one obvious choice with two flanks**:

```
   Essential $89/mo          Pro $149/mo  ·  $99/mo billed annually        Founding $75/mo
   the research desk         the whole system                              annually, forever
   ─ the flank ─             ─ THE CHOICE ─                                ─ the reward ─
```

Read left to right the per-month numbers are $89 → $99 → $149, and the only way below $89 is a
twelve-month commitment to the *bigger* product. Every step buys something; no step is a worse
deal than the one beside it. An earlier draft set Essential monthly at $99 so it would match
Pro-annual's headline — a nice line that put two $99/month products side by side, one of them a
strict superset. Cleverness that invites "why would I ever pick the smaller one" is not
positioning; it is Finding A again, one cell over.

---

## 3. PART XX — Free trial vs freemium: the definitive recommendation

**Recommendation: freemium as the primary motion, with a card-required 7-day Pro trial and a
usage-triggered 72-hour Pro Day Pass. Not a longer trial.**

### Why freemium is primary for *this* product
Mastermind's value is a **loop**, not a moment: the engines run every night and the product tells
you what changed. A loop cannot be demonstrated inside a bounded window that also has to teach
the user what the product is. A Free tier that produces a genuine weekly habit converts on
*accumulated* evidence — which is the only kind of evidence this product can actually offer.

### Why 7 days and not 14 or 30
Seven calendar days ≈ **five market days**, which is enough to see the retention loop fire twice
and at least one Prophet entry/exit cycle — the minimum viable demonstration. Fourteen is
defensible; thirty is not. A 30-day trial on a subscription product with a strong Free tier is
just a slower Free tier with a card attached: urgency evaporates, revenue is delayed a month,
and the trial→paid decision gets made by a calendar reminder rather than by the product.

### Why card-required
It converts substantially better, it filters intent, and the generous Free tier already serves
the no-card audience. This restates MNZ-R9, which stands.

### The addition: the usage-triggered Pro Day Pass
**Once per account, no card, 72 hours of full Pro**, granted automatically the **third** time a
Free user encounters the same paid ceiling within 14 days.

Why it is better than a longer trial:
- It fires at **demonstrated intent** — we know exactly what they want, so the pass can open
  *with that thing already rendered*.
- 72 hours is short enough to be used immediately and long enough to include two overnight cycles.
- It costs nothing when nobody wants anything, which is the property a calendar trial lacks.
- It gives the contextual upgrade system (see `MASTERMIND_PAYWALL_SYSTEM_SPEC.md` §5) something
  generous to offer at the exact moment the user is most receptive.

Implementation is a `comp`-source entitlement row with a 72-hour `current_period_end` — a shape
`app/billing.py` already supports (`source` ∈ `stripe | substack | comp`). **Post-launch, Wave 2.**

### The complete ladder

```
anonymous → Free (no card, indefinite)
              ├─ 3rd ceiling hit within 14d → 72h Pro Day Pass (once, no card)
              └─ any time                   → 7-day Pro trial (card required) → Pro
                                            → Essential monthly (no trial, bought outright)
```

Essential has `trial_days: 0` today and that is correct — Essential is the *considered* purchase
for someone who already knows they want research rather than execution. The trial exists to sell
Pro.

---

## 4. PART XXI — The founder launch

### 4.1 What is right about the current design
The scarcity is **enforced, not cosmetic** — `app/billing.py:314-425` subtracts reserved seats
from `remaining`, `active` follows `remaining`, and every checkout path gates on those numbers.
The payload discloses `claimed` (real redemptions) and `reserved` (operator-withdrawn) as
separate fields. The counter only becomes public above `public_count_threshold: 25`, so we never
publish an embarrassing "3 sold". This is careful, honest work.

### 4.2 What is wrong: the rationale, not the mechanism

**Problem 1 — 2,000 seats is not scarcity.** A cap we have no realistic path to approaching is a
number, not a limit. Scarcity that cannot be tested is not believed.

**Problem 2 — the daily withdrawal has no answerable rationale.** The code comment is honest:
"the operator retires founding memberships from public sale on a daily schedule." If a customer
asks *why* two seats disappeared yesterday, there is no answer that respects them. The handoff's
instruction is explicit: *avoid fake scarcity; if founder membership is limited, there should be
an actual rationale.* A schedule is not a rationale.

**Problem 3 — `duration: forever` × 2,000 × 31% off is an unexamined permanent ARPU cap.**

### 4.3 Recommended founder offer

| Element | Recommendation |
|---|---|
| **Name** | Founding Member (not "Founding Pro" — the tier is an implementation detail; membership is the thing) |
| **Price** | **$900/year, locked forever** — unchanged. Against a repriced Pro annual of $1,188 that is a 24% permanent discount and a clean $288/yr saving |
| **Cap** | **500** (from 2,000) |
| **Close** | **A date**, published: the offer closes at 500 members *or* on a stated date, whichever comes first |
| **Pacing** | **Remove `allotment_pacing`.** `remaining = cap − claimed`, honestly. Urgency comes from the date and the real count |
| **Grandfather** | `duration: forever`, unchanged and inviolable |
| **Eligibility** | Anyone, annual only, while seats remain |
| **Migration** | On close, the promotion code retires; existing members are untouched forever |

### 4.4 The rationale that makes 500 real

The cap must exist for a reason a customer can respect. It does, if we give founders something
that genuinely does not scale:

1. **Price locked forever** — the economic promise.
2. **A direct line** — a private founders' channel and a monthly call with the operator, where
   they see what is being built and what it found. *This is the reason for the cap:* a feedback
   channel with 2,000 people in it is a broadcast; with 500 it is a conversation, and with the
   first 100 it is a design partnership.
3. **First access** to new desks before general release.
4. **Credit in the product** for those who want it.

That is a founder programme rather than a discount code, and the number 500 becomes explicable
in one sentence: *"We can only run a real feedback loop with a few hundred people."*

**Economics:** 500 × $900 = $450k of annual cash at full subscription, against a permanent ARPU
concession of $288/member/year. That is a bounded, deliberate investment in the cohort that will
tell us what to build. 2,000 × $288 = $576k/yr of permanent concession is not.

*If the operator prefers to keep 2,000:* then remove the pacing anyway and let the counter be
honest. Of the three problems, the unexplainable daily withdrawal is the one that costs trust
with exactly the audience the founder offer is trying to recruit.

---

## 5. PART VII — Packaging: the recommendation restated as a catalog

Architecture 2 ("Research vs Execution"), from `…ARCHITECTURE.md` §5.2. Expressed as the
`config/plans.yml` change it implies:

| | **Free** | **Essential** — the research desk | **Pro** — the whole system |
|---|---|---|---|
| Who | Anyone building a habit | The Allocator (P3) | The Operator (P2) + Builder (P4) |
| One sentence | "The market, read every night." | "Everything the engines compute, in full, with your holdings watched." | "Everything, plus live and in time to act." |
| Price | $0 | **$89/mo** · **$828/yr** ($69/mo-equiv, save 22%) | **$149/mo** · **$1,188/yr** ($99/mo-equiv, save 34%) |
| Trial | — | none (bought outright) | 7 days, card required |
| Features | — | `site_full`, `board_full`, `history_full`, `watch_pro` | + `alerts_realtime`, `chat_deep`, `terminal_live_options`, `export_api` |
| Ceiling | 1 list / 15 symbols / 3 rows / 20 chat a week / 7d history | 10 lists / 250 symbols / EOD alerts / 300 fast + 10 deep chat | unlimited / intraday / uncapped fast + 150 deep |

**Why `terminal_live_options` moves to Pro:** it is the clearest timeliness capability in the
product, and moving it is what converts Essential↔Pro from a size split into a segment split.

**But it must not be the first move, and it is not a config edit.** Adversarial review found
both halves of the mechanism missing: `app/billing.py:799` prefers Stripe's ActiveEntitlements
over the catalog and `stripe_bootstrap._attach_features` never detaches, so deleting the key
from `config/plans.yml` changes nothing for real subscribers; and the promised grandfather has
no carrier, because `terminal/lib/entitlement.ts::hasLiveOptions` tests a hardcoded
`"terminal_live_options"` literal in another repository. `MASTERMIND_ENTITLEMENT_MATRIX.md` §6
now specifies the two mechanisms that would work, both of which are ordered two-repo migrations.

**Sequencing consequence:** ship the Essential/Pro split on the capabilities that already
differentiate — the **Research Vault is Pro-only today** (`app/research.py::_VIEW_TIERS =
{"pro"}`), the deep chat lane is 15× larger on Pro, and the indicator ladder is 15 vs 31 and
already enforced. Live options moves later, deliberately, or not at all. *That is also what
un-confounds the §7 test: an Essential that keeps live options and gains an honest annual price
is a tier being measured, not a tier being starved.*

**Why Essential keeps no trial:** the trial exists to sell the tier with the compelling
demonstration. Essential's value accrues over weeks; a 7-day window undersells it.

---

## 6. China / RMB

Unchanged from MNZ §3.6 and still correct: WeChat Pay has no recurring billing and Stripe
Alipay recurring is invite-only, so CN customers get an **annual one-time price** via Checkout
with `current_period_end = +365d`, and T-30/T-7 renewal emails carrying a fresh Checkout link.

Two additions:
- **The founder offer should be available in RMB terms at the same USD price.** Founding
  membership is a global cohort; excluding CN customers from it because of a payment rail would
  be an accident, not a decision.
- **Detect via Checkout locale / payment method, never by IP geolocation.** `app/gate.py`'s own
  header findings (2026-08-07) are the reason: the country header arriving at the origin is
  attacker-controllable under some paths, and pricing must never key on a spoofable input.

---

## 7. The pre-registered Essential test

Stated now so it cannot be rationalized later. **Sixty days after paid launch:**

> If Essential is **<15% of new paid subscriptions** AND the Essential→Pro upgrade rate is
> **<10%**, Essential is not a segment — it is a discount. Delete it, migrate existing Essential
> subscribers to Pro at their current price for as long as they stay, and move to
> Architecture 1 (Free → Pro).

Conversely, if Essential clears both bars, the two-tier split is doing real work and Pro should
be *widened* (exports, API, higher deep-chat allowance) rather than Essential narrowed.

**The test only returns information if Essential is a fair contestant.** An earlier draft would
have run it against an Essential that had been stripped of live options, had its annual SKU
withdrawn, had no trial, had no CN payment rail, and was labelled "the flank" on its own pricing
page — a tier that failed under those conditions would have proved nothing except that we
starved it. The four conditions below are therefore part of the pre-registration, not
commentary:

1. Essential keeps `terminal_live_options` for the whole measurement window (§5).
2. Essential has a real annual SKU at $828 and is purchasable on the same rails as Pro,
   including the CN annual one-time price (§6).
3. Neither tier's card carries language that ranks them ("the flank", "most popular") during
   the window.
4. The measurement needs an event that **does not exist yet**: `checkout.completed` carries the
   new tier but not the previous one, so an Essential→Pro upgrade is indistinguishable from a
   new Pro subscription. Add `subscription.tier_changed {from_tier, to_tier, days_at_previous}`
   to `config/growth_events.yml` before launch, or criterion two is unmeasurable.

**Decision date, decision rule, both outcomes, and the conditions that make the test valid are
fixed in advance.** The failure mode this guards against is the one every SaaS company hits: a
tier that never justifies itself but never gets killed either, because killing it feels like
losing revenue.

---

## 8. Summary of config changes

| Change | Where | Operator decision |
|---|---|---|
| Essential annual $900 → $828 | `config/plans.yml` + new Stripe price | **Yes** — this is the Finding A fix |
| Pro annual $1,308 → $1,188 | `config/plans.yml` + new Stripe price | **Yes** |
| Essential monthly $99 → $89 | `config/plans.yml` + new Stripe price | **Yes** (secondary — ladder monotonicity) |
| Founder cap 2,000 → 500 | `config/plans.yml` (`max_redemptions`) | **Yes** |
| Remove `allotment_pacing` | `config/plans.yml` + `app/billing.py` | **Yes** |
| Publish a founder close date + the four founder benefits | `templates/plans.html.j2` | **Yes** |
| `subscription.tier_changed` event | `config/growth_events.yml` + `app/billing.py` | No — required by §7 |
| New feature keys (`board_full`, `history_full`, `watch_pro`, `alerts_realtime`, `chat_deep`, `export_api`) | Stripe **first**, then `config/plans.yml` | With Wave 2 |

**No product is withdrawn from sale in this table**, which is why none of it needs the template
branch and the raise-on-missing-price builder change that a withdrawal would have required.

Every price in the product is already derived from `config/plans.yml` by both plans builders and
re-derived client-side from the same cents in `data-` attributes, so repricing is genuinely a
config change (MNZ-R12) — the savings badges recompute themselves. The Stripe side needs a new
`lookup_key` per changed price, with the old key retained in `legacy_lookup_keys` so existing
subscriptions keep resolving. That mechanism already exists and has been used twice.
