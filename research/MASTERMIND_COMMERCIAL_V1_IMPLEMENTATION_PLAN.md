# Mastermind-X — Commercial V1 Implementation Plan

**Status:** BUILD PLAN, 2026-08-12. Executes `MASTERMIND_COMMERCIAL_ARCHITECTURE.md`.
**Model routing** follows `CLAUDE.md` §Model routing: `builder` (Opus) builds code, `designer`
(Opus) owns user-facing design, `reviewer` (Opus) reviews, `Explore`/`general-purpose`
(Sonnet, explicit `model:`) do mechanical census. Design *choices* never go to a Sonnet builder.
**Spawn law** (`CLAUDE.md` §Spawn-handoff law): acceptance gates go **inline in the spawn
prompt**, phrased "not done unless"; reference images are committed files; flagship UI returns
to the commissioning session rather than self-merging.

---

## §0 — ACCEPTANCE GATES (read first; applies to every task below)

A task in this plan is **not done unless**:

1. **A fresh end-to-end happy path runs with zero manual workarounds**, exercised at every tier
   the change touches — anonymous, Free, Essential, Pro. A race you reload around is a bug you own.
2. **Per-tier visual evidence is posted in the PR body** for any user-facing change: light + dark
   + `zh`, at 375px and 1280px.
3. **The entry point is actually wired.** A capability reachable only by typing a URL is not shipped.
4. **The gate checklist in `MASTERMIND_PAYWALL_SYSTEM_SPEC.md` §8 is copied into the PR and
   ticked**, for any task that adds or moves a gate.
5. **A negative test exists**: the thing that should be refused is demonstrated refused, and the
   test fails against the pre-change code.
6. **No customer-facing quantitative claim is a literal.** It derives from the config that
   enforces it (MNZ-R13).
7. **Telemetry lands.** Any task that adds a funnel step emits its registry event and proves a row
   in `analytics_events`.

---

## 1. Wave map

```
W0  Truth & foundations        ◄── SHIPPED IN THIS PR (partial)
W1  The stranger's first 90s   ◄── PRE-LAUNCH BLOCKER, highest leverage
W2  Instrumentation            ◄── PRE-LAUNCH BLOCKER (measure or fly blind)
W3  Free becomes a product     ◄── PRE-LAUNCH BLOCKER (gates PAYWALL_ENABLED=1)
W4  Contextual upgrades        ◄── PRE-LAUNCH
W5  The retention loop         ◄── LAUNCH-ADJACENT; the reason to return
W6  Pricing & founder changes  ◄── PRE-LAUNCH, operator-gated
W7  Paid depth (Essential/Pro) ◄── POST-LAUNCH
W8  Day Pass, briefing, export ◄── POST-LAUNCH
```

W1, W2, W3 and W6 are the pre-launch critical path. W1 is small and changes the funnel most.

---

## W0 — Truth & foundations *(partially shipped in this PR)*

### W0-1 — Bind chat allowances to the config that enforces them ✅ SHIPPED
**Objective.** Close the last un-derived quantitative claim on a pricing surface. Eight chat
allowance cells were hand-typed literals — correct on 2026-08-12, bound to nothing. (The
"unlimited" cell is the honest rendering of `quotas.pro.fast.limit: -1`, operator ruling
2026-07-28; it was not a false claim.)
**Code areas.** `lib/chat_allowance.py` (new), `templates/plans.html.j2`,
`scripts/build_site.py::_plans_view_model`, `scripts/build_public_pages.py::plans_view_model`,
`tests/test_plans_chat_quota_truth.py`.
**Acceptance.** Both builders receive a `chat_quotas` block derived from `config/brain.yml`; the
tier cards and both comparison-matrix rows render from it; the rendered page is **unchanged**
against the pre-change bytes (proof that the literals were right and the derivation is faithful);
a test fails if either builder drops the block. The two surfaces that cannot derive at build
time — the hand-authored landing (`templates/index.html:783, 832`) and the onboarding sheet
(`templates/onboard.js:267, 407`) — keep their literals and are **pinned to the same config by
the same test**, so a reprice reds CI on all four surfaces at once.
**Model.** builder (Opus). **Pre-launch:** required. **Status:** done.

### W0-2 — Growth event registry ✅ SHIPPED
**Objective.** One event vocabulary for six waves.
**Code areas.** `config/growth_events.yml`, `tests/test_growth_events_registry.py`.
**Acceptance.** Every live `_MM_EVENT_TYPES` member appears in the registry marked `live`;
every entry is well-formed; no tier enum contains `insider`.
**Status:** done.

### W0-3 — Remove or enforce the indicator ladder ⚠️ NOT SHIPPED — **operator decision**
**Objective.** `config/plans.yml terminal_indicators.access` advertises 1/15/31 and **nothing
enforces it** (`PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md:735` already names the gap).
Two lawful outcomes; ship one before launch:
- **(a) Enforce** — Terminal repo, `terminal/lib/indicators.ts` + `IndicatorsModal.tsx`, gated by
  a new `indicators_advanced` entitlement resolved through `terminal/lib/entitlement.ts`.
- **(b) Withdraw the claim** — remove the ladder from plans/landing/onboarding copy until (a) ships.
**Recommendation: (b) now, (a) in W7.** Shipping a paid launch with an advertised, unenforced
ladder is a claim with no enforcer at all — a strictly worse defect than an unbound literal — and (a) is a cross-repo build.
**Model.** (b) builder (Opus), macro repo. (a) builder (Opus), Terminal repo.
**Dependencies.** (a) needs `MASTERMIND_ENTITLEMENT_MATRIX.md` §2.2 keys.
**Pre-launch:** **required** (either outcome).

---

## W1 — The stranger's first 90 seconds  ◄ HIGHEST LEVERAGE

Four tasks. Together they are the difference between the journey in
`…ARCHITECTURE.md` §12 happening and not happening. None is large.

### W1-1 — Make the chat reachable by anonymous visitors
**Objective.** `mm_brain.js` is not in the public allowlist, so the chat launcher 401s on 12 of 12
measured pages for anonymous visitors (`PRODUCT_PAGE_CENSUS_2026-08.md` §Exec ¶1) — while
`scripts/check_hub_a11y.py:45` asserts it mounts "on EVERY page". The best acquisition surface in
the product never runs for a stranger.
**Scope.** Promote `mm_brain.js` (and only it — audit its transitive fetches first) to `public` in
`config/site_access.yml`, byte-aligned with the Caddyfile exclusion list.
**Not in scope.** Any brain **API** route. Every `/api/brain/*` route keeps its own auth and
quota. This promotes the *workbench*, never the *work* — the same standard the
`fundamental_forensics.css/js` block in that file already states.
**Acceptance.** Anonymous load of five macro pages shows the launcher and **zero** console
errors; `/api/brain/*` still refuses an unauthenticated caller; `check_hub_a11y.py` passes for
the tier it asserts.
**Code areas.** `config/site_access.yml`, `app/deploy/Caddyfile`,
`tests/test_site_access_boundary.py`.
**Model.** builder (Opus). **Dependencies.** none. **Pre-launch:** **required.**

### W1-2 — Turn on the guest chat lane
**Objective.** Anonymous chat is default-OFF (`brain_gateway._GUEST_CFG_DEFAULT =
{enabled: False, daily_limit: 30}`). A visitor from X cannot ask a single question.
**Scope.** Operator action, not code: set `admin/brain_guest_access.json` to
`{"enabled": true, "daily_limit": 3}`. Untracked, hot-reloaded within ~20s, no deploy, reversible
in seconds.
**Acceptance.** Anonymous visitor gets 3 fast answers/day; the 4th returns a `402` with the
registration CTA, not an error; guest quota is enforced on **both** the `mm_aid` cookie hash and
the IP hash; cost per day is bounded and observable in the admin cost panel for one week
before launch.
**Risk & mitigation.** Abuse/cost. Both quota keys already exist
(`_guest_cookie_quota_file`, `_guest_ip_quota_file`), the config clamps `daily_limit` to
[1, 500], and the monthly token ceiling backstops the lane. Start at 3/day, raise on evidence.
**Model.** operator + builder (Opus) for the CTA-on-exhaustion copy.
**Pre-launch:** **required.** *(This is the single highest impact-to-effort item in the program.)*

### W1-3 — The create-before-register module
**Objective.** The anonymous watchlist works and folds into the account on first sign-in
(`watchstore.js`, `mdash.watchstore.folded.v1`) — and **nothing in the product ever invites a
visitor to use it.**
**Scope.** A reusable inline module for deep-link landing surfaces (theme, cohort, ticker,
board pages): "add the tickers you actually hold", one-tap suggestions drawn from the page's own
names, an instant read of the resulting 3–5 names against the current regime, and **one line
naming what those names share**. The save prompt fires on the 3rd symbol or on leave-intent —
**never on arrival**.
**Acceptance.** Not done unless: an anonymous visitor can go from landing to a 3-symbol list with
a rendered read **in under 60 seconds and zero page reloads**; the list survives a refresh; signing
in folds it with no retyping and no duplicates; the module renders correctly in light/dark/zh at
375px and 1280px; and `personal.act` + `watchlist.symbol_added` + `watchlist.folded` all land in
`analytics_events`.
**Code areas.** New `templates/wl_capture.js` + `.css`, `templates/watchlist.js` (seam only),
the landing-surface templates, `config/site_access.yml` (public assets).
**Model.** **designer (Opus)** owns the design; builder (Opus) implements once pinned. This is a
flagship user-facing surface — it does **not** go to a Sonnet builder, and it returns to the
commissioning session rather than self-merging (§Spawn-handoff law §4).
**Dependencies.** W2-1 for telemetry. **Pre-launch:** **required.**

### W1-4 — Social deep-link contract
**Objective.** X posts have nowhere good to land, so they default to the homepage or `/pricing`.
**Scope.** A documented route contract: `/<surface>.html?focus=<entity>&utm_*` where `focus`
scrolls to and highlights the named cohort/theme/ticker and the page's `<title>`/OG card reflect
it. Plus per-surface OG images generated at build. Applies to the launch-critical surfaces only.
**Acceptance.** A link to `flow_velocity.html?focus=silver_miners` opens with that cohort in view,
the OG preview names it, `session.start` carries `source`/`campaign`/`landing_surface`, and the
page's above-the-fold content is **server-rendered** (verifiable with JS disabled).
**Code areas.** `lib/seo.py`, the surface templates, the OG-image builder.
**Model.** builder (Opus); designer (Opus) for the OG card system.
**Pre-launch:** required for the ~6 surfaces the launch campaign will actually link to.

---

## W2 — Instrumentation

### W2-1 — Wire the registry into the beacon
**Objective.** `_MM_EVENT_TYPES` is a closed whitelist; unknown types are dropped silently. Every
emitter built before this lands is a no-op.
**Scope.** Extend the whitelist from `config/growth_events.yml` (read the registry, do not
re-type the names); add typed property validation for the closed enums; keep the existing
throttle and batching untouched.
**Acceptance.** A test asserts whitelist ≡ registry `client`-sourced entries; an unknown type is
still dropped; an event carrying `tier: "insider"` is **normalized, not rejected** (a paying
customer's telemetry must not vanish because of the legacy string).
**Code areas.** `app/main.py`, `config/growth_events.yml`, `tests/`.
**Model.** builder (Opus). **Pre-launch:** **required.**

### W2-2 — Client emitters
**Scope.** `intelligence.viewed`, `personal.act`, `watchlist.*`, `evidence.opened`,
`paywall.encountered`, `upgrade.clicked`, `plans.viewed`, `sincelast.viewed`.
**Acceptance.** Each event has a positive test **and a near-miss negative test** — in particular,
a locked slot must **not** emit `intelligence.viewed`. That distinction is the entire value of
the event.
**Model.** builder (Opus). **Pre-launch:** required.

### W2-3 — Server emitters
**Scope.** `account.created`, `checkout.*`, `trial.*`, `subscription.*`, `chat.*`,
`alert.*`, `digest.*`. Emitted from `app/billing.py` (after the entitlement upsert succeeds, so
telemetry never claims a state the authority does not hold) and `brain_gateway`.
**Acceptance.** Webhook replay does not double-emit (the handler is already idempotent on
`event.id` — the emitter must ride that idempotency, not add its own).
**Model.** builder (Opus). **Pre-launch:** required.

### W2-4 — Activation job + CEO report
**Scope.** Nightly idempotent job computing `account.activated`; a weekly report rendering the
nine numbers and the largest-leak sentence from
`MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md` §5.
**Constraint.** Off the render path — VPS cron, per `CLAUDE.md` (render budget is law).
**Acceptance.** Re-running the job produces no duplicate activations; the report renders from a
seeded fixture with known-correct numbers.
**Model.** builder (Opus). **Pre-launch:** the job yes; the report may follow within week 1.

### W2-5 — Funnel smoke test
**Scope.** A scripted session walking visit → interact → register → activate, asserting every
expected row lands.
**Why it is a task and not a nicety.** Without it, a whitelist edit or a template refactor
silently deletes a funnel step and nobody notices until a monthly review.
**Model.** builder (Opus). **Pre-launch:** required.

---

## W3 — Free becomes a product   ◄ GATES `PAYWALL_ENABLED=1`

### W3-1 — Grow `free_registered`
**Objective.** `free_registered` lists 11 exact paths and 3 prefixes. The day the paywall arms,
Free collapses to "shells with no data". There is currently **no configuration in which Free is a
real product.**
**Scope.** Expand to the Free set in `MASTERMIND_ENTITLEMENT_MATRIX.md` §4.
**Acceptance.** With `PAYWALL_ENABLED=1` **in staging**, a signed-in Free account loads every
launch-critical surface with real content and meets a wall only at the four documented ceilings;
an anonymous visitor still meets the anonymous boundary; the boundary test and the Caddy
byte-alignment check both pass.
**Model.** builder (Opus) + **reviewer (Opus)** — this is the highest-blast-radius config change
in the program.
**Pre-launch:** **required, and it must land before the switch, not with it.**

### W3-2 — The four Free ceilings
**Scope.** Watchlist capacity (1 list / 15 symbols), board depth (3 rows — already built in
`tier_preview.js`), chat allowance (`config/brain.yml` 5/wk → 20/wk), history window (7 days).
History is the only genuinely new enforcement.
**Acceptance.** Each ceiling refuses server-side, emits `paywall.encountered` with its stable
surface id, and renders a labelled locked state — never a blur, never an empty panel. A Free
account at the ceiling and an Essential account past it produce **different bytes**.
**Model.** builder (Opus). **Pre-launch:** required.

### W3-3 — Free rows on the three gated desks
**Scope.** Special Situations, China Special Situations, ETFs currently show Free users a shell
with zero rows. Give Free the 3 newest (`config.yml preview_rows` already exists for two of them).
**Rationale.** A desk that shows a Free user nothing is a desk they never learn to want.
**Acceptance.** Newest-first, never best-first (PW-3); zero paid rows in the built shell,
**verified by grepping the built HTML**, not by reading the template.
**Model.** builder (Opus). **Pre-launch:** recommended, not blocking.

---

## W4 — Contextual upgrades

### W4-1 — The upgrade-context contract
**Scope.** Implement the object in `MASTERMIND_PAYWALL_SYSTEM_SPEC.md` §5.1; replace
`tier_preview.js::openUpgrade()`'s hardcoded `plan: "essential"`.
**Acceptance.** Every wall emits a context with a stable `surface`; the sheet renders the
three-sentence message; `required` is the **lowest** sufficient tier (a test asserts a
`watchlist_capacity` context never routes to Pro).
**Model.** builder (Opus); designer (Opus) for the sheet.
**Pre-launch:** required.

### W4-2 — Escalation ladder
**Scope.** The `hits` counter and the 1/2/3/4+ ladder (§5.3): quiet → observation → sheet → quiet.
**Acceptance.** No modal on a first session at any hits count; a 4th encounter does **not**
re-open the sheet. Both are tested.
**Model.** builder (Opus). **Pre-launch:** required.

### W4-3 — The nine upgrade moments
**Scope.** Wire all nine from §5.4 with their copy.
**Model.** designer (Opus) writes the copy (it is glance-tier product copy, not decoration);
builder (Opus) wires. **Pre-launch:** at least the four that exist pre-W7:
`watchlist_capacity`, `board_depth`, `history_window`, `chat_allowance`.

---

## W5 — The retention loop

### W5-1 — "Since you were last here"
**Objective.** The single reason to open Mastermind tomorrow. It does not exist.
**Scope.** A per-user nightly diff over watchlist/portfolio symbols and followed boards: state
changes, theme moves, risk deterioration, upcoming catalysts — ordered by how much it should
change what the user does.
**Constraints.** Computed **off the render path** (VPS lane, per `CLAUDE.md`). Reads product
artifacts only, never repo internals (CXI-R23). Never originates a signal — it *diffs* states the
engines already graded (A7 / MNZ-R5).
**Acceptance.** Not done unless: a user away 7 days sees a 7-day diff, not 7 daily cards; a user
with no changes sees one honest line saying so; every item links to its evidence; it renders
above the fold on return; `sincelast.viewed` fires with `item_count` and `days_since_last`.
**Model.** builder (Opus) for the diff engine; **designer (Opus)** for the surface.
**Dependencies.** W3-1. **Pre-launch:** launch-adjacent — ship within 2 weeks of paid launch.
Without it the funnel has no loop and D7 will read as a product failure when it is an absence.

### W5-2 — Digest email
**Scope.** The same diff, rendered as email. Free weekly, Essential/Pro daily pre-open in the
user's timezone. `app/mailer.py` and `app/marketing_emails.py` already exist.
**Acceptance.** The subject line names the single biggest change for that user; unsubscribe is
RFC 8058 one-click (the public `/unsubscribe.html` path already exists); no intelligence content
in a marketing-classified send.
**Model.** builder (Opus). **Pre-launch:** no. Week 2–3.

---

## W6 — Pricing & founder changes *(operator-gated)*

Every task blocks on an operator decision (`MASTERMIND_PRICING_AND_PACKAGING.md` §8). All are
one-line config changes plus a Stripe-side price/coupon.

| # | Change | Files | Pre-launch |
|---|---|---|---|
| W6-1 | Withdraw Essential annual while Founding Pro is live | `config/plans.yml`, `templates/plans.html.j2` | **required** — it is a dominated purchase on our own page |
| W6-2 | Pro annual $1,308 → $1,188 | `config/plans.yml` + new Stripe `lookup_key`; old key into `legacy_lookup_keys` | required if adopted |
| W6-3 | Founder cap 2,000 → 500; remove `allotment_pacing`; publish a close date + the four founder benefits | `config/plans.yml`, `app/billing.py` (pacing removal), `templates/plans.html.j2` | required if adopted |
| W6-4 | New feature keys + Stripe Entitlements | `config/plans.yml`, `scripts/stripe_bootstrap.py` | with W7 |

**Acceptance for all of W6.** Repricing changes **no** displayed literal — the savings badges
recompute from config (MNZ-R12), verified by a test that changes a price fixture and asserts the
rendered percentage moves. Existing subscriptions keep resolving through `legacy_lookup_keys`;
a test asserts an old key still maps to its tier.

---

## W7 — Paid depth *(post-launch)*

| # | Task | Notes | Model |
|---|---|---|---|
| W7-1 | Portfolio concentration / correlated downside | The canonical Essential upgrade moment. Coordinate with the Watchlist+Portfolio revamp program; **display-tier composite rules apply** (`DNR:KILL-FUSED-COMPOSITE` Amendment 2: transparent printed legs, v0-equal weights, abstention, day-one grading) | builder (Opus) |
| W7-2 | `alerts_realtime` split | Today `isPaidTier()` gives Essential and Pro identical alerts; `isProTier()` exists and is nearly unused | builder (Opus), Terminal repo |
| W7-3 | Indicator ladder enforcement | W0-3(a) | builder (Opus), Terminal repo |
| W7-4 | `terminal_live_options` → Pro-only, with Essential grandfathering by feature key | **Operator decision.** Never by a code branch | builder (Opus) |
| W7-5 | Export / API (`export_api`) | P4 ceiling-raiser | builder (Opus) |

---

## W8 — Post-launch growth

| # | Task | Notes |
|---|---|---|
| W8-1 | 72-hour Pro Day Pass | `comp`-source entitlement with a 72h `current_period_end` — a shape `app/billing.py` already supports |
| W8-2 | Shareable artifacts | Prophet cards, cohort rankings, regime cards as OG images with a link back. Never include a user's holdings |
| W8-3 | SEO deepening | Ticker/theme/sector pages already largely public. **Do not add SEO sludge**; add only where a search user is genuinely served |
| W8-4 | Churn reason capture | The one-screen flow in `…ACTIVATION_AND_FUNNEL.md` §10.1 |
| W8-5 | The Essential test | Run the §7 pre-registered decision at day 60. **Calendar it now** |

---

## 2. Pre-launch critical path

Ordered. Everything else can follow.

```
W0-3  decide + ship (remove or enforce the indicator claim)   ← operator
W1-1  mm_brain.js public                                       ← 1 PR
W1-2  guest chat on at 3/day                                   ← operator, seconds
W2-1  registry → beacon whitelist                              ← 1 PR
W2-2/3 emitters                                                ← 2 PRs
W1-3  create-before-register module                            ← designer + builder
W3-1  grow free_registered                                     ← 1 PR + reviewer
W3-2  the four Free ceilings                                   ← 2 PRs
W4-1/2 contextual upgrade contract + ladder                    ← 2 PRs
W6-1  withdraw Essential annual                                ← operator + 1 PR
W6-3  founder cap + pacing + close date                        ← operator + 1 PR
      ── ops checklist (docs/ops/site-access.md) ──
      PAYWALL_ENABLED=1
W5-1  since-you-were-last-here                                 ← within 2 weeks
```

**Two blockers that are not tasks in this plan, and must be resolved by their owners:**

1. **The GitHub Pages mirror** republishes the entire site nightly, including every premium
   artifact. MNZ-OD3 recorded it as an accepted risk *before* there was a paid product. It is
   already on the launch checklist in `docs/ops/site-access.md`; it needs an explicit decision
   now that real money is involved, not an inherited one.
2. **Email verification + custom SMTP + CAPTCHA** — MNZ-R2 gates all content gating on these.
   Verify the current state before assuming it is done.

---

## 3. Estimation and sequencing notes

- **Parallel-safe:** W1-1, W1-2, W2-1, W6-1 touch disjoint files and can run concurrently in
  separate worktrees. W3-1 must be alone — it is the highest-blast-radius config change here.
- **Serial:** W2-1 → W2-2/W2-3 (emitters are no-ops before the whitelist). W3-1 → W3-2 →
  `PAYWALL_ENABLED=1`.
- **Cross-repo:** W0-3(a), W7-2, W7-3, W7-4 are Terminal-repo lanes. Per `CLAUDE.md`
  §Spawn-handoff law §6, **audit `terminal/AGENTS.md` before spawning** and put the acceptance
  gates inline in the prompt — a masterplan pointer is context, not enforcement.
- **Render budget:** nothing in W5 may run on the render path. The nightly diff is a VPS lane.
- **Every PR** follows the house ship loop: fresh `origin/main` worktree → commit → push → PR →
  `merge-on-green` → `scripts/ci_handoff.py`.

---

## 4. What this plan deliberately does not do

- **It does not rebuild the billing spine.** `app/billing.py` (1,677 lines) is sound: idempotent
  webhooks, negative propagation, reconciler, portal, enforced offer allotment. Leave it alone.
- **It does not touch the paywall enforcement path.** `app/paywall.py` is fail-closed with a
  documented staleness bound. Only its *inputs* (config lists) change.
- **It does not redesign any page.** Where a surface is named, the design-system workstream owns
  the visual execution; this plan specifies behavior and acceptance.
- **It does not add a second control plane.** Entitlement authority stays `user_entitlements`,
  written only by the webhook, the reconciler, the Substack sync, and operator comps (MNZ-R3).
- **It does not gate anything new for revenue's sake.** Every gate it moves is justified by
  either a real marginal cost or a real segment boundary — and three of its tasks (W3-2 chat
  allowance, W3-3 free rows, W1-2 guest chat) give *more* away than today.
