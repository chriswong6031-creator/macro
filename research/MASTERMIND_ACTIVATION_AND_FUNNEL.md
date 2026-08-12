# Mastermind-X — Activation & Funnel (V1)

**Status:** RECOMMENDATION, 2026-08-12. Companion to `MASTERMIND_COMMERCIAL_ARCHITECTURE.md`.
**Scope:** the journey model, activation definitions, time-to-value, onboarding, the watchlist
engine, retention loops, notifications, the daily brief, lifecycle, and churn — with the
measurement for each transition. Event names are defined once in
`MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md` and referenced here as `event.name`.

**Evidence posture.** Mastermind has ~0 commercial telemetry today: the beacon
(`app/main.py::_MM_EVENT_TYPES`) emits eleven event types, none of them commercial. So every
threshold in this document is a **pre-registered hypothesis with an instrumentation plan**, not
a measured fact, and each is labelled with what would falsify it. Saying so is the point: a
funnel target invented and then quietly forgotten is worse than no target.

---

## 1. PART XXVII — The funnel model

The conventional model — `visit → register → pay` — is wrong for this product, because the thing
that sells Mastermind is *using* Mastermind, and the thing that makes using it valuable is that
it knows what you care about. So the funnel has two extra steps, and both come **before**
registration:

```
    visit
      │
      ▼
  ①  intelligence experienced          ← saw a real, specific, dated read
      │
      ▼
  ②  personal act                      ← typed a ticker, built a list, asked a question
      │
      ▼
  ③  registration                      ← to KEEP ② and to be told when it changes
      │
      ▼
  ④  activation                        ← list + return day + evidence opened
      │
      ▼
  ⑤  upgrade intent                    ← third encounter with one ceiling
      │
      ▼
  ⑥  paid
      │
      ▼
  ⑦  paid activation                   ← used ≥2 paid capability groups on ≥3 days
      │
      ▼
  ⑧  retained
```

The load-bearing claim is that **② precedes ③**. A visitor who has created something has a
reason to register that is about them, not about us. Everything in §4 exists to make ② happen
inside ninety seconds.

### 1.1 Transition metrics and pre-registered targets

| Transition | Metric | Target (hypothesis) | What falsifies it |
|---|---|---|---|
| visit → ① | % sessions with ≥1 `intelligence.viewed` | **60%** | <40% ⇒ landing surfaces are not self-evidently intelligence; fix the surface, not the funnel |
| ① → ② | % of ① sessions with ≥1 `personal.act` | **25%** | <10% ⇒ the create-before-register prompt is invisible or unappealing |
| ② → ③ | % of ② sessions registering within 7d | **30%** | <15% ⇒ the registration reason is not concrete enough; test the four reasons in `…ARCHITECTURE.md` §4.2 individually |
| ③ → ④ | activated / registered, 7-day window | **40%** | <20% ⇒ activation definition is too hard, or onboarding drops people before the watchlist |
| ④ → ⑥ | paid / activated, 30-day window | **8%** | <3% ⇒ the paid promise is not differentiated from Free; re-open the packaging question |
| ⑥ → ⑦ | paid-activated / paid, 14-day window | **70%** | <50% ⇒ the first paid session fails to deliver what was bought |
| ⑦ → ⑧ | D30 retention of paid-activated | **85%** | <70% ⇒ retention loop is absent or the intelligence is not trusted |

These numbers are **priors, not commitments.** They exist so that Week 1 after launch has
something to be surprised by. Revise from data, in writing, in this file.

---

## 2. PART XI — Activation

### 2.1 The definitions

**Anonymous activation** — a visitor is anonymously activated when, in a single session, they do
any **one** of:
- add ≥3 symbols to the local watchlist (`watchlist.symbol_added` ×3), or
- receive ≥1 chat answer (`chat.answer_received`), or
- open ≥2 distinct ticker pages (`ticker.viewed` ×2 distinct).

*Why:* each is an act of intent that a passive reader does not perform. This is the population
worth measuring registration against — not raw visitors, most of whom bounced off a headline.

**Free activation (the primary activation event)** — a registered Free account is ACTIVATED when,
within 7 days of first visit, **all three** hold:

1. **A saved watchlist with ≥3 symbols** (`watchlist.saved` with `symbol_count >= 3`)
2. **A return visit on a second distinct calendar day** (`session.start` on 2 distinct days)
3. **At least one evidence open** — a receipt, an evidence drawer, a Prophet card detail, or a
   chat answer (`evidence.opened` OR `chat.answer_received`)

*Why these three and not others.* Each covers a different failure mode of "looks engaged but
will not return":
- (1) proves **personalization exists**. Without it the product has nothing to tell them
  tomorrow, so there is no loop to retain.
- (2) proves **habit**, and it is the only one of the three that cannot be faked by a curious
  single session. It is also the single strongest predictor in every consumer-subscription
  literature I would trust, which is why it is the one I would keep if forced to pick one.
- (3) proves they understood **what kind of product this is**. A user who never opens evidence
  has experienced Mastermind as a signal feed, and will churn to the next signal feed. The
  evidence open is the moment the differentiator lands.

**Why a conjunction rather than a score.** A weighted activation score is unfalsifiable in
month one and invites tuning until it says what we hoped. Three binary conditions can be
audited, argued with, and *wrong* — which is the property we need.

**Paid activation** — within 14 days of first payment, the account has used **≥2 of the five
capability groups** (Read / Find / Understand / Watch / Prove) on **≥3 distinct days**.
*Why:* a paid user who only ever opens one surface bought a feature, not a product, and will
churn at renewal. This is our earliest cancellable-intent signal, and it fires ~11 months before
the renewal does.

### 2.2 What we should NOT call activation

- **Signup.** It is a transition, not a state.
- **Any single page view**, including the highest-value ones. A view is not an act.
- **Trial start.** It measures our funnel's persuasiveness, not their understanding.
- **Time on site.** Confusion and engagement produce the same number.

### 2.3 Instrumentation required
None of the three activation conditions is measurable today. Required new events:
`watchlist.saved`, `evidence.opened`, `chat.answer_received`, plus a durable
`user_first_seen_at` on the account. All are specified in the instrumentation document; all are
cheap (the beacon already accepts batched events with a verified `user_id`).

---

## 3. PART XII — Time to value

The current worst case is bad: a visitor from X lands on a page whose chat script 401s, whose
data assets may 401, with no prompt to do anything, and the only conversion path in sight is a
pricing page. Time to first *personal* value: unbounded.

The design targets:

| Horizon | What must be true | Surface responsible |
|---|---|---|
| **First 10 seconds** | They can state what this is and see one specific, dated, checkable claim — **without JavaScript having succeeded**. Server-rendered, above the fold | Deep-link landing surfaces (`…ARCHITECTURE.md` §12) |
| **First 60 seconds** | They have interacted: asked the chat a question, or typed a ticker, or added a name. Nothing has been asked of them | Guest chat (3/day) + the inline "add your tickers" prompt |
| **First 5 minutes** | Mastermind has produced something *about them* — their 3–5 names read against the current regime, with one line about what those names share | Anonymous watchlist + the instant read |
| **First day** | They know exactly what will be different tomorrow and have been told it in one sentence | The "we read your list again tonight" promise + the weekly brief opt-in |

**The rule that follows:** *nothing may be asked of a visitor before they have received
something.* No signup wall before value, no preference questionnaire before value, no cookie or
consent interstitial that blocks the first read. Registration is a *save* action, and a save
action requires something to save.

---

## 4. PART XIII — Onboarding

### 4.1 What exists today
`templates/onboard.js` (3,110 lines) is a five-step sheet — `STEP_ACCOUNT` → `STEP_PREFS` →
`STEP_PLAN` → `STEP_BILLING` → `STEP_DONE` — with modes `signup | signin | upgrade | recover |
reset`. The prefs step asks three things (market focus, theme, trade types), all chip-based, and
carries a visible **Skip** control. Preferences land in `LS_PENDING_PREFS`, the *same* key the
Terminal reads on first sign-in — so cross-surface personalization already works.

**Assessment: the onboarding sheet is good, and it is in the wrong place in the journey.** The
prefs step is genuinely minimal (three taps, skippable) and is not the problem. The problem is
that `STEP_PLAN` and `STEP_BILLING` sit inside the *signup* flow, so a person who wanted to save
a watchlist is walked through a plan chooser on their way to a free account. That is the
"complete signup → choose plan → configure → finally see intelligence" shape the handoff warns
against, and it is happening at the exact moment the user's intent is smallest.

### 4.2 Recommended onboarding

**Anonymous onboarding — entirely implicit.** No sheet, ever. We infer market focus from the
pages they read, horizon from whether they open intraday or weekly surfaces, and interest from
the tickers they type. Zero questions.

**Account onboarding — two screens, both skippable, plan chooser removed.**
1. **Account** (email/Google) — unchanged.
2. **Prefs** — unchanged, and now *pre-filled from behavior*: if they read three China pages,
   the CN chip is already on. Prefilling turns a questionnaire into a confirmation.

`STEP_PLAN` and `STEP_BILLING` **leave the signup flow entirely** and become the `upgrade` mode
only. A free account is created in two screens. The plan conversation happens later, at a
ceiling, with context — which is where it converts anyway (§5).

*Expected objection:* removing the plan step from signup will reduce day-0 paid conversions.
*Response:* it will, and that is the trade. Day-0 conversion from a cold signup is a small
number multiplied by a low-intent population; the same person converts at a much higher rate
three days later at a ceiling they chose to hit. If measured day-30 paid conversion falls after
this change, it is wrong and should be reverted — that test is in §11.

**Advanced personalization — gradual and earned.** Never a screen. It accretes: the horizon
chip appears after the fifth session; the "which of these matter to you" prompt appears the
first time we have five candidate themes from their behavior.

---

## 5. PART XIV — The watchlist as activation engine

This is the most important surface in the funnel and it is **already ~70% built**.

**What exists:** `templates/watchlist.js` is pure client state in a versioned `localStorage`
blob, with an empty-state that renders **starter chips** validated against the live index.
`templates/watchstore.js` is the Supabase sync adapter; it folds the local blob into the account
on first sign-in via a one-time `mdash.watchstore.folded.v1` marker, merging rather than
overwriting. The page is anonymous-reachable and its `access_shell` is `anonymous`.

**What is missing is not the machinery — it is the invitation.** Nothing anywhere in the product
tells a visitor to build a list. `watchlist.html` is a nav item you must already want.

### 5.1 The flow, and where each step lives today

| Step | Today | Change needed |
|---|---|---|
| 1. User enters a ticker | Only on `watchlist.html` | **Add an inline "add your tickers" module to the deep-link landing surfaces** (theme, cohort, ticker pages) with the page's own names as one-tap suggestions |
| 2. Mastermind analyzes it | Works — the signal stack attaches | none |
| 3. User adds more | Works | none |
| 4. Cross-security relationships | Partly — `watchlist_risk.js` renders a regime rail | **Add the one-line "what these three share" read.** This is the moment that reads as magic and it is one sentence |
| 5. Creates a watchlist | Works, locally | none |
| 6. Register to save | **Missing** | The save prompt, fired on the 3rd symbol or on leave-intent — never on arrival |
| 7. Intelligence changes over time | Engines already do this nightly | none |
| 8. User returns | **Missing** | "Since you were last here" (§7) |
| 9. Advanced analysis → Pro conversion | Concentration/correlation not built | Portfolio intelligence, Wave 3 |

### 5.2 Tiering (see the entitlement matrix for the full table)
Anonymous 5 symbols, local · Free 1 list / 15 symbols, synced · Essential 10 lists / 250
symbols + portfolio + concentration · Pro unlimited + intraday alerts.

**The 5-symbol anonymous cap is a product decision, not a cost decision** — it is the number
where "I have built something" is true and "I have everything I need for free" is not.

*Coordination:* the Watchlist+Portfolio CEO revamp program owns the UI. This document
specifies only the commercial behavior — caps, the save moment, and the sync promise.

---

## 6. PART XVI — Retention architecture

Mastermind's natural loops are all **overnight state changes**, which is exactly what a
nightly-compute product should sell. The loops, ranked by expected pull:

| Loop | The question | Cadence |
|---|---|---|
| **My things** | What changed in my list / holdings? | Daily, pre-open |
| **Prophet** | What entered, what exited? | Daily |
| **Risk** | What deteriorated? | Daily + on-change |
| **Regime** | Did the market change character? | On-change (rare, high value) |
| **Themes** | What is accelerating? | Weekly |
| **Catalysts** | What is coming this week? | Weekly + T-1 |
| **Market open** | What is the read this morning? | Daily |

### 6.1 "Since you were last here" — the canonical surface

**One surface, computed per user, shown first on return.** Not a feed and not a notification
center: a **diff**, bounded to what changed *since their last session*, ordered by how much it
should change what they do.

Content, in order:
1. **Your names** — state changes on watchlist/portfolio symbols, with the one-line why.
2. **Your themes** — acceleration or deceleration in themes their names sit in.
3. **The market** — regime or risk-state changes, only if there was one.
4. **Coming up** — catalysts in the next 5 sessions for their names.

Rules that keep it honest and keep it from becoming noise:
- **If nothing changed, say so in one line.** "Nothing material changed for your 12 names since
  Tuesday." A product that manufactures a change every day teaches users to ignore it.
- **It is a diff, not a digest.** A user away for a week sees a week's diff, not seven days of
  cards.
- **Every item links to its evidence.** The loop and the trust surface are the same surface.
- **Free gets a weekly version.** A Free user with no reason to return is not in a funnel.

This is the one genuinely new surface the commercial architecture requires. Everything it needs
exists — the engines compute the states nightly, the ledgers are already forward-graded, and the
per-user watchlist is already in Supabase. The work is the diff and the presentation.

---

## 7. PART XVII — Notifications and alerts

**Standard: an alert must earn the sentence "I'm glad Mastermind told me."** If we cannot say
which decision an alert changes, it is a digest item, not an alert.

| Category | Urgency | Channel | Configurable | Entitlement |
|---|---|---|---|---|
| Portfolio risk deterioration | **High** | Push + email | Threshold | Essential (EOD) · Pro (intraday) |
| Regime change | High | Push + email | On/off | Free (rare enough to be free, and it is market context) |
| Prophet entry/exit on **my** names | High | Push + email | Per-list | Essential (EOD) · Pro (intraday) |
| Major catalyst on my names, T-1 | Medium | Email | On/off | Free (weekly digest) · Essential+ (per-event) |
| Unusual flow on my names | Medium | Push | Threshold | **Pro only** — this is the timeliness product |
| Theme acceleration | Low | Digest | On/off | Essential+ |
| Watchlist event (target, band change) | Low | Digest | Per-symbol | Free (weekly) · Essential+ (daily) |
| Product/marketing | — | Email | Opt-out | All — and never mixed into the intelligence channels |

**Volume caps, enforced server-side, not by user diligence:** at most 3 high-urgency pushes per
user per day; at most 1 digest per day. A cap that exists only in a settings screen is not a cap.

**Default state is quiet.** New accounts get the weekly digest and regime changes, nothing else.
Every other channel is opt-in from a moment where the user asked for that thing.

---

## 8. PART XVIII — The daily briefing

**Verdict: yes — build it, as the *email body of the same diff* in §6.1, not as a second system.**

The scope justification is that it is nearly free: the diff must exist anyway for the on-site
return surface, and an email is a rendering of it. Building a separate briefing pipeline would
not be justified; rendering the existing diff is.

| | Free | Essential | Pro |
|---|---|---|---|
| Cadence | Weekly (Sunday PM) | Daily, pre-open | Daily, pre-open |
| Your names | Top 3 changes | All | All + intraday follow-up |
| Market read | Regime + risk state | + sector rotation | + flow/positioning |
| Prophet | Entries only | Entries + exits + timing state | + armed triggers |
| Catalysts | — | Next 5 sessions | + earnings intelligence |
| Subject line | Names the single biggest change | same | same |

**The subject line is the product.** "3 of your names changed state; NVDA left the board" earns
an open. "Your Mastermind briefing" does not. Personalization here is worth more than everything
below the fold.

*Timing:* pre-open in the user's own timezone (we already have `market_focus` from prefs and
timezone from the beacon fingerprint). A US-market brief delivered at 06:00 local to a
Shanghai-based user is a brief nobody reads.

---

## 9. PART XXX — Customer lifecycle

Interventions must be **product-led** — a state change inside the product — rather than CRM spam.
One intervention per stage. If a stage needs three, the product is failing at that stage.

| Stage | Definition | Intervention | Channel |
|---|---|---|---|
| **Visitor** | No account | The create-before-register prompt (§5) | In-product only |
| **Registered** | Account, not activated | The single missing activation condition, named: *"You have a list — come back tomorrow and we'll show you what changed"* | In-product + 1 email at 48h |
| **Activated** | §2.1 satisfied | Nothing. Let them use it. Show ceilings when they reach them | In-product |
| **Trialing** | Pro trial active | Day 1: the one thing they came for, set up. Day 5: what they used, and what it costs to keep | In-product + 2 emails |
| **Paid new** | 0–30 days | Paid-activation check at day 14; if <2 capability groups, surface the unused one that matches their behavior | In-product |
| **Paid retained** | >30 days, active | Nothing. Ship. | — |
| **At risk** | Paid, no session in 14d, or paid-activation never reached | One honest email: *"You haven't opened Mastermind in two weeks. Here is what happened to your names while you were away."* — the diff itself as the win-back | Email |
| **Churned** | Canceled or lapsed | Structured reason capture (§10), then a 90-day quiet period. One re-engagement only when something they specifically wanted ships | Email |
| **Win-back** | Churned >90d | The diff for their old list, plus what changed in the product since | Email |

**The at-risk intervention is the one that matters**, and it is the same artifact as the
retention loop. That is not a coincidence — it is the test of whether the loop is real.

---

## 10. PART XXIX — Churn analysis

### 10.1 Capture without annoying
Cancellation flow: **one screen, one required question, one optional field.** The required
question is a single-select with these options, which are the hypotheses we can act on:

1. Not enough value for the price
2. Too expensive right now
3. Overwhelming — I couldn't find what I needed
4. I already have a tool that does this
5. The signals weren't accurate for me
6. I'm not trading/investing actively at the moment
7. Missing something I need (free-text)
8. Something else (free-text)

No retention offer *before* the reason is captured. A discount offered before we know why loses
both the customer and the datum.

### 10.2 Tie churn to behavior
Every cancellation row joins to that user's prior 90 days: paid-activation status, capability
groups used, sessions, alerts received vs opened, the last upgrade context. The analysis
questions that matter, in order:

- Do churners differ from retainers in **paid-activation** (§2.1)? *This is the primary hypothesis:
  if paid-activation predicts retention, it becomes the operating metric for the whole company.*
- Does reason (3) "overwhelming" concentrate in users who arrived on a *broad* surface (macro,
  homepage) rather than a *specific* one (theme, ticker)? If so, acquisition surface choice is a
  retention lever, not just a conversion lever.
- Does reason (5) "not accurate" correlate with users who never opened evidence? If so, the
  accuracy complaint is really a *legibility* problem, and the fix is the evidence surface.
- Does reason (2) concentrate in monthly vs annual? That is a pricing-structure answer, not a
  price-level answer.

### 10.3 The involuntary half
Failed payments are a churn category that is fixable with plumbing rather than product. Stripe
dunning is on by default via the Customer Portal; what we must add is the **in-product** signal —
a persistent, non-blocking banner on a `past_due` entitlement with a one-click portal link.
`app/billing.py` already recomputes `status` from Stripe and busts the cache on
`invoice.payment_failed`, so the state is available; nothing renders it.

---

## 11. Measurement plan and the experiments worth running

### 11.1 What must be instrumented before launch
Without these, none of §1–§10 is measurable. Full definitions in the instrumentation spec.
`intelligence.viewed` · `personal.act` · `watchlist.symbol_added` · `watchlist.saved` ·
`evidence.opened` · `chat.answer_received` · `paywall.encountered` · `upgrade.clicked` ·
`plans.viewed` · `checkout.started` · `checkout.completed` · `trial.started` ·
`subscription.canceled` + reason.

### 11.2 Experiments worth running at ~100 users
Only things with large expected effects and cheap reversal:
1. **Anonymous chat on vs off.** Expected the largest single effect in the funnel. Measure
   ①→② and ②→③.
2. **Create-before-register prompt: on the 3rd symbol vs on leave-intent.**
3. **Deep-link landing (theme/cohort page) vs homepage** for social traffic.
4. **Removing the plan step from signup** (§4.2) — measured on day-30 paid conversion, not day-0.

### 11.3 Experiments worth running at ~1,000 users
5. Free board rows: 3 vs 5.
6. Free chat allowance: 20/wk vs 40/wk.
7. Upgrade copy: contextual (names the thing) vs generic. *Prediction: contextual wins by a
   lot; if it does not, the ceiling we chose is not one users care about.*
8. Trial: 7-day card-required vs the 72-hour no-card Day Pass, as parallel arms.

### 11.4 Decide by judgment, do not test
- Whether trust surfaces are free. (They are. Testing this is testing whether to be trustworthy.)
- Whether trust surfaces carry a "how we grade ourselves" link. (They do.)
- Whether Essential annual should be sold alongside an identically-priced superior product. (No.)
- Button colors, card orders, microcopy — at our traffic these produce noise, and the noise
  will be read as signal.

**Standing rule:** an experiment without a pre-registered metric, a pre-registered duration, and
a pre-registered decision rule is not an experiment; it is a change with a dashboard next to it.
