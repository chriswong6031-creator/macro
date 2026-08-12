# Mastermind-X — Growth Instrumentation Spec (V1)

**Status:** IMPLEMENTABLE SPEC, 2026-08-12. Companion to `MASTERMIND_ACTIVATION_AND_FUNNEL.md`.
**Machine-readable companion:** `config/growth_events.yml` — the canonical registry, pinned by
`tests/test_growth_events_registry.py`. **That file is the authority; this document explains it.**

---

## 1. Where instrumentation stands today

The product has a competent first-party analytics beacon and **no commercial telemetry at all**.

**What exists** (`app/main.py`, `templates/theme.js::loadMMAnalytics`):
- Same-origin sink `POST /api/collect`, batched (≤40 rows), fire-and-forget, non-blocking.
- Anonymous by default via the httpOnly `mm_aid` cookie scoped to `.mastermind-x.com` — **shared
  with the Terminal**, so a visitor is one identity across both apps. This is a real asset.
- Signed-in visitors are additionally attributed to a **server-verified** Supabase `user_id`.
  A client-claimed identity is never trusted.
- Rows land in the shared Supabase `analytics_events` table via PostgREST with the service-role
  key, deny-all RLS; geo is backfilled off the hot path by `scripts/geo_enrich.py`.
- Per-IP burst throttle on the anonymous beacon.

**The whitelist** (`app/main.py::_MM_EVENT_TYPES`) — eleven types:
`pageview · route · ticker_view · search · terminal_jump · click · scroll · session_start ·
heartbeat · exit · ad_exposure`

**What is missing.** Not one event for: registration, activation, paywall encounter, upgrade
click, plans view, checkout, trial, cancellation, watchlist creation, chat usage, or evidence
opening. **Every transition in the funnel model is currently unmeasurable.** We could ship the
entire commercial architecture and not know whether any of it worked.

The good news is that the hard parts — identity, verification, batching, cross-app cookie,
throttling, storage — are done. What is needed is a vocabulary and about a dozen emitters.

---

## 2. Design principles

1. **Measure acts, not clicks.** An event exists to answer a question in
   `MASTERMIND_ACTIVATION_AND_FUNNEL.md` §1.1. If no transition needs it, it is not in the registry.
2. **One vocabulary.** Six implementation waves must emit the same names. That is what
   `config/growth_events.yml` is for, and why a test pins it.
3. **Server-truth for money, client-truth for behavior.** Anything about entitlement, payment, or
   quota is emitted **server-side** from the authority (`app/billing.py`, `brain_gateway`).
   A client may never report that a checkout completed.
4. **Properties are typed and closed.** Every property has a type and, where it is an enum, an
   explicit value list. An open-ended `meta` blob becomes unqueryable within a month.
5. **Stable ids over labels.** `surface` is a stable id (`portfolio_concentration`), never a page
   title. Titles get rewritten; joins break silently.
6. **Privacy.** Never put a user's holdings, position sizes, or notes into an event. Symbol lists
   are permitted only as **counts** except in `watchlist.symbol_added`, where the single symbol
   is the datum. Never place personal data in a URL or query string.
7. **No PII in properties.** Email never rides in a property; `user_id` is the join key and is
   stamped server-side from a verified token.

---

## 3. The canonical events

39 events total: the 11 live ones (unchanged) plus 28 new. Full property schemas are in
`config/growth_events.yml`; this section is the map.

### 3.1 Acquisition

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `session.start` *(live: `session_start`)* | client | `source`, `campaign`, `landing_surface`, `referrer_host`, `is_first_ever` | Where do visitors come from and where do they land? |
| `intelligence.viewed` **new** | client | `surface`, `surface_group`, `tier_seen`, `rows_visible` | **visit → ①.** Did they see a real read, or a shell? |
| `ad_exposure` *(live)* | client | `arena`, `creative` | Split-test arm |

`intelligence.viewed` fires **once per surface per session**, and only when a genuine read has
rendered — a locked slot or an empty state does **not** count. This is the whole point of the
event: it separates "the page loaded" from "the product worked."

### 3.2 Engagement and activation

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `ticker.viewed` *(live: `ticker_view`)* | client | `ticker`, `surface` | Interest breadth |
| `personal.act` **new** | client | `act`, `surface` | **① → ②.** The umbrella intent marker |
| `watchlist.symbol_added` **new** | client | `symbol`, `count_after`, `storage` | Watchlist funnel |
| `watchlist.saved` **new** | client | `symbol_count`, `list_count`, `storage` | **Activation condition 1** |
| `watchlist.folded` **new** | client | `symbol_count` | Did anonymous→account state transfer work? |
| `evidence.opened` **new** | client | `surface`, `evidence_kind` | **Activation condition 3** |
| `chat.question_sent` **new** | server | `lane`, `surface`, `tier`, `remaining_after` | Chat demand + quota pressure |
| `chat.answer_received` **new** | server | `lane`, `latency_ms`, `had_citations` | **Activation condition 3** (alt) |
| `alert.configured` **new** | server | `alert_kind`, `channel` | Retention intent |
| `search` *(live)* | client | `query_len`, `result_kind` | Discovery |
| `terminal_jump` *(live)* | client | `surface` | Cross-app flow |

`personal.act` is deliberately a **separate umbrella event** rather than a derived query. The
①→② transition is the single most important number in the funnel, and it should be readable
without a five-way `UNION`.

**Activation condition 2** (return on a second distinct day) is derived from `session.start`
and needs no event of its own.

### 3.3 Registration

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `account.created` **new** | server | `method`, `had_local_watchlist`, `prefs_skipped`, `days_since_first_seen` | **② → ③.** Does create-before-register work? |
| `account.activated` **new** | server, once | `days_to_activate`, `completing_condition` | **③ → ④** |

`had_local_watchlist` is the direct test of the create-before-register thesis. If registrants with
a local watchlist convert to activation at a materially higher rate than those without, the
thesis holds and the prompt should be everywhere. If not, it is wrong and this document is wrong.

### 3.4 Conversion

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `paywall.encountered` **new** | client | `surface`, `reason`, `required_tier`, `hits` | Which ceilings do users actually meet? |
| `upgrade.clicked` **new** | client | `surface`, `required_tier`, `hits`, `placement` | Which ceilings *sell*? |
| `plans.viewed` **new** | client | `source_surface`, `billing_period_default` | Does contextual entry beat nav entry? |
| `checkout.started` **new** | server | `tier`, `interval`, `offer_key`, `source_surface` | **⑤ → ⑥** |
| `checkout.completed` **new** | server (webhook) | `tier`, `interval`, `offer_key`, `amount_cents`, `is_trial` | Revenue truth |
| `checkout.failed` **new** | server | `tier`, `interval`, `failure_kind` | Payment friction |
| `trial.started` **new** | server | `tier`, `trial_days` | — |
| `trial.ended` **new** | server | `tier`, `outcome` | Trial efficacy |
| `daypass.granted` **new** | server | `trigger_surface`, `hits` | Day-Pass efficacy (Wave 2) |

**The join that matters most in the whole system** is `paywall.encountered.surface` →
`upgrade.clicked.surface` → `checkout.completed`. It answers "which of the nine upgrade moments
in `MASTERMIND_PAYWALL_SYSTEM_SPEC.md` §5.4 actually sells", and within 30 days it will tell us
whether the paid product is packaged around the right capability. Nothing else we can build gives
that answer.

### 3.5 Retention

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `sincelast.viewed` **new** | client | `item_count`, `changed_symbols`, `days_since_last` | Does the loop pull? |
| `digest.sent` **new** | server | `cadence`, `tier`, `item_count` | — |
| `digest.opened` **new** | server | `cadence`, `tier` | Subject-line efficacy |
| `digest.clicked` **new** | server | `cadence`, `item_kind` | Which loop content pulls |
| `alert.delivered` / `alert.opened` **new** | server | `alert_kind`, `channel` | Alert value (delivered vs opened is the "glad you told me" proxy) |

### 3.6 Churn

| Event | Source | Key properties | Answers |
|---|---|---|---|
| `subscription.past_due` **new** | server | `tier`, `interval` | Involuntary churn |
| `subscription.canceled` **new** | server | `tier`, `interval`, `reason_code`, `days_subscribed`, `paid_activated` | Voluntary churn, joined to behavior |
| `subscription.reactivated` **new** | server | `tier`, `days_churned` | Win-back |

`paid_activated` on the cancellation row is what makes churn analysis possible *at the moment of
churn* instead of six weeks later — it is the primary hypothesis in
`MASTERMIND_ACTIVATION_AND_FUNNEL.md` §10.2, answerable with a single `GROUP BY`.

---

## 4. Property conventions

| Property | Type | Notes |
|---|---|---|
| `surface` | string, stable id | Snake_case. Matches the entitlement matrix and the upgrade catalogue. **Never a page title** |
| `surface_group` | enum | `read · find · understand · watch · prove` — the five user-job groups |
| `tier` / `required_tier` / `tier_seen` | enum | `anon · free · essential · pro · unlimited`. **Always normalized** — `insider` must never appear in an event |
| `reason` | enum | `ceiling · tier · usage · history` |
| `source` / `campaign` | string | From URL params, allowlisted keys only, truncated to 64 chars |
| `interval` | enum | `month · year` |
| `outcome` | enum | `converted · expired · canceled` |
| `storage` | enum | `local · cloud` |

**The `insider` rule is load-bearing.** `lib/tiers.py` documents that the legacy string arrives
indefinitely from pre-rename entitlement rows and far-future-cached `immutable` JS. If it reaches
telemetry un-normalized, every tier-segmented number splits in two and the split is invisible.
Normalize at the emitter, and assert it in the registry test.

---

## 5. The CEO dashboard

Weekly. **Nine numbers and one sentence.** Not a dashboard of dashboards.

```
MASTERMIND — week of <date>

ACQUISITION      1,840 qualified visitors        (+12% w/w)
PRODUCT VALUE      612 experienced intelligence  (33% of visitors)
REGISTRATION       241 registered                (39% of those who acted)
ACTIVATION         143 activated                 (59% of registrations)
CONVERSION          36 paid                      (25% of activations)
REVENUE         $4,120 MRR · $38,400 cash collected YTD
RETENTION      D1 44% · D7 31% · D30 22%
USAGE               71% of paid users created a watchlist before purchasing
                     8% of non-activated users ever used the chat

LARGEST LEAK    Visitors arriving on the homepage instead of a specific
                surface convert to an interaction at 9% vs 41% for
                deep-linked arrivals. 63% of traffic lands on the homepage.
```

*(Illustrative shape and numbers — not measurements. The shape is the deliverable.)*

**Definitions, so the numbers cannot drift:**

| Line | Definition |
|---|---|
| Qualified visitor | Distinct `mm_aid` with ≥1 `session.start`, excluding bots and internal IPs |
| Experienced intelligence | ≥1 `intelligence.viewed` |
| Registered | `account.created` |
| Activated | `account.activated` (the three-condition definition) |
| Paid | `checkout.completed` with `is_trial=false`, or `trial.ended{outcome:converted}` |
| MRR | Sum of active subscriptions normalized to monthly; annual ÷ 12. Founder rates at their actual rate |
| Cash collected | Actual charges — **reported separately from MRR**, because annual-heavy mix makes them diverge sharply and conflating them flatters or panics at random |
| D1/D7/D30 | Of registrations in the cohort week, % with a `session.start` on day 1 / 7 / 30 |
| Largest leak | The transition in §1.1 with the largest gap between measured and target, **stated in words** |

**Explicitly not on this dashboard:** page views, total events, time on site, bounce rate,
"engagement". Each is either unactionable or ambiguous between success and confusion.

---

## 6. Implementation notes

### 6.1 Wiring order
1. **Extend the whitelist.** `app/main.py::_MM_EVENT_TYPES` is a closed set; unknown types are
   dropped. Add the client-emitted names from the registry there first, or every emitter you
   build is silently a no-op. *(This is the single most likely way this program ships dead.)*
2. **Client emitters** ride `window.mmTrack` (already exposed in `templates/theme.js`).
3. **Server emitters** go through the same `analytics_events` insert path `app/main.py` uses,
   with the verified `user_id` — never via a client round-trip.
4. **Billing events** are emitted from the webhook handler in `app/billing.py`, which is already
   idempotent on `event.id`. Emit **after** the entitlement upsert succeeds, so a telemetry row
   never claims a state the authority does not hold.

### 6.2 Backfill and derived state
- `account.activated` is computed by a nightly job over the prior 7 days of events; it fires
  **once** per account, and the job is idempotent on `user_id`.
- `hits` on `paywall.encountered` is computed client-side from a rolling 14-day local counter
  keyed by `surface`, and re-derived server-side for analysis. The client copy drives the
  escalation ladder; the server copy is the truth for reporting. They will disagree slightly
  across devices — that is acceptable, and the analysis uses the server copy.

### 6.3 Verification
An instrumentation program that cannot fail is not instrumented. Three gates:
1. **Registry test** (`tests/test_growth_events_registry.py`, shipped): every live beacon type
   appears in the registry; every registry entry is well-formed; no enum lists `insider`.
2. **Emitter test, per wave:** each new event has one test asserting it fires on the intended
   act and does **not** fire on the near-miss (a locked slot must not emit
   `intelligence.viewed`).
3. **Funnel smoke test, weekly:** a scripted session walks visit → interact → register →
   activate and asserts every expected event landed in `analytics_events`. Without this, a
   whitelist edit or a template refactor silently deletes a funnel step and nobody notices
   until a monthly review.

---

## 7. What NOT to instrument

Named explicitly, because analytics spam is the default failure mode:

- Individual button clicks that are not one of the acts above.
- Scroll depth beyond the existing coarse `scroll` event.
- Hover, focus, mouse movement.
- Every panel expand on a page (only `evidence.opened` matters).
- Anything on the admin console (already excluded in `theme.js` — keep it that way).
- Any event whose analysis question nobody can state in one sentence.

**Standing rule:** to add an event to the registry, name the funnel transition or decision it
serves. No transition, no event.
