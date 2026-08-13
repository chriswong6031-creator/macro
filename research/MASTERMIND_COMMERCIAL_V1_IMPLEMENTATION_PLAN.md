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

### W0-3 — ~~Remove or enforce the indicator ladder~~ ❌ WITHDRAWN — the premise was false
**What this task said.** That `config/plans.yml terminal_indicators.access` advertises 1/15/31
and nothing enforces it, citing `PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md:735`.

**What is true.** The ladder is enforced and the counts match the catalog exactly.
`terminal/lib/suites/*` carries a per-module `tier`: 1 `free` (`trend/candlePainter.ts`), 14
`essential`, 16 `pro` — cumulative 1 / 15 / 31. Three points enforce it against the tier
resolved from macro-api `/api/me`: the renderer drops non-entitled modules, the picker locks
their rows, the toggle refuses to enable them. `config/plans.yml:33` states the binding in a
comment. A signed-out or Free user sees exactly one module.

**How the error happened, since it is the more useful output:** the claim was inherited from a
masterplan line rather than re-derived, and the confirming search stopped at `indicators.ts` and
`IndicatorsModal.tsx` — the ladder lives in `lib/suites/`. A cited "known gap" is testimony, not
observation.

**What survives as real work,** demoted from pre-launch blocker to hardening:
- **W0-3a — server-side recheck for the indicator ladder.** Enforcement is client-side only and
  a `mm.devTier` localStorage override exists. That is acceptable for a *product* ladder and
  not for anything we would call a boundary. Terminal repo, post-launch.
- **W0-3b — correct two real copy defects found alongside it.**
  (a) `templates/theme.js` `SD_PLAN_FEATURES` tells signed-in Free users "The Terminal —
  3 indicators" while the catalog grants 1 and the Terminal enforces 1. It is on the billing
  summary, so a paying customer reads it. Macro repo; paired plain-copy change
  (`site/theme.js`), `immutable`-cached. **Pre-launch.**
  (b) `terminal/lib/i18n.tsx` (charting-app repo) says `obInsider2: ["20 Pro AI dives a month"]`
  while `config/brain.yml` says Essential deep is **10**/month. Cross-repo, so
  `tests/test_plans_chat_quota_truth.py` cannot reach it — the Terminal needs its own guard
  reading the same contract. **Pre-launch**, Terminal repo.
  *(`templates/chat.html` had a third defect of the same family — "1000 fast" for a lane the
  config makes uncapped, plus the pre-rename "Insider" label. Both are FIXED in this PR.)*

## W1 — The stranger's first 90 seconds  ◄ HIGHEST LEVERAGE

Four tasks. Together they are the difference between the journey in
`…ARCHITECTURE.md` §12 happening and not happening. None is large.

### W1-1 — ~~Make the chat reachable by anonymous visitors~~ ✅ LANDED ON MAIN 2026-08-12
`/mm_brain.js` is in `config/site_access.yml` `public.exact` (#5409, #5463), so the launcher
mounts for anonymous visitors on every root-level page. Nothing to build.

**Two remainders, both smaller than the original task:**
- **W1-1a — the SEO subtrees.** `theme.js` injects the widget with a *document-relative* `src`,
  so pages under the SEO subtrees request a path the allowlist does not cover. Named in
  `config/site_access.yml` as a known, pre-existing gap. Pre-launch if those pages are campaign
  landing targets; otherwise post-launch.
- **W1-1b — one boundary check is narrower than the others.**
  `tests/test_site_access_boundary.py` does iterate the four matchers (`reg_asset`,
  `gate_html`, `reg_asset_err`, `gate_html_err`) for structural assertions, but only
  `@reg_asset` gets the set-equality check against `public`. A promotion applied to
  `@reg_asset` and forgotten in `@reg_asset_err` therefore passes. Extend the set-equality
  check to the error matcher. Pre-launch, small.

### W1-2 — Turn on the guest chat lane  ◄ **now the whole of W1's headline value**
**Objective.** With `mm_brain.js` public, the launcher opens for a stranger and then refuses to
ask anything: `brain_gateway._GUEST_CFG_DEFAULT` is `{enabled: False, daily_limit: 30}`, boot's
`/api/brain/me` 401s, and `send()` bounces to the sign-in sheet rather than sending.
**Scope.** Set `admin/brain_guest_access.json` to `{"enabled": true, "daily_limit": 3}` —
untracked, hot-reloaded within ~20s, no deploy, reversible in seconds.

**It is NOT "operator action, not code", and an earlier draft was wrong to say so.** Four things
must land first; three are code:
1. **Accumulate token usage across tool rounds.** `config/brain.yml` sets `tool_budget` 5/10/20,
   so one "question" is up to 6/11/21 model calls — and `brain_gateway` assigns `usage_dict`
   from the *final* response instead of accumulating, so every earlier round is invisible to
   both the ceiling and the `lib/ai_costs.py` ledger. Turning on an unmetered lane while the
   meter under-reads by 2–20× is the wrong order.
2. **Add `claude-opus-5` and `gpt-5.6-sol` to `config/ai_pricing.yml`** — `estimate_cost_usd`
   returns `None` for both today, so the admin cost panel cannot price what it records.
3. **Give the guest lane a token ceiling and a global daily spend cap.**
   `_check_and_increment_guest_quota` checks two request counters and never reads
   `token_ceilings`. Collapse IPv6 to a /64 before hashing while you are there — the IP half of
   the anti-farm is IPv4-only today.
4. **Decide the guest/Free interaction deliberately.** `_get_allowance` short-circuits: whenever
   guest access is on, the FREE tier's fast lane returns the *guest* daily limit, before
   `quotas.free.fast` is read. So this flip silently re-writes the Free allowance too. Either
   split the two in code, or choose one number for both and say so.
**Acceptance.** Anonymous visitor gets 3 fast answers/day; the 4th returns a `402` with the
registration CTA, not an error (402 is correct *here* — an accepted identity whose allowance is
spent, per the paywall spec §6); the quota holds on both the `mm_aid` cookie hash and the
/64-collapsed IP hash; and **one week of measured cost-per-turn from the ledger** (p50/p95
rounds and tokens per guest turn) exists before launch.
*(An earlier draft asked for a test pinning `_get_allowance('free','active','fast')` under the
flip and claimed none existed. `tests/test_brain_guest.py::test_free_fast_flips_to_daily_when_enabled`
already covers it. What is genuinely missing is a test asserting the FREE tier's configured
allowance is what a signed-in free user gets while guest access is ON — i.e. that item 4's
decision, once made, holds.)*
**Model.** builder (Opus) for 1–4; operator for the flip. **Pre-launch:** **required.**

### W1-3 — The create-before-register module
**Objective.** The anonymous watchlist works and folds into the account on first sign-in
(`watchstore.js`, `mdash.watchstore.folded.v1`) — as of 2026-08-12, when #5463 promoted the five
funnel-shell scripts. Two gaps remain: **nothing in the product invites a visitor to use it**,
and **Mastermind says nothing about the list once built** — `stockdata.js` and the three
decision-rule modules stay gated for anonymous visitors by design. The second is the one the
pattern turns on, and it is a disclosure decision: this task builds the **regime-and-context
read with no graded per-ticker claim**, which needs none of the four gated modules.
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
**The trap this task must not fall into.** `app/paywall.py` classifies `deny → public → free →
premium` and returns `204` for anything classified `free` **before** it calls
`enforced_early(path)`. So adding a path to `free_registered` silently un-gates it even when it
is listed in `premium.enforced_early` — verified by execution, and no test covers the
interaction. Diff the new `free_registered` against `enforced_early` before merging.
**Acceptance.** With `PAYWALL_ENABLED=1` **in staging**, a signed-in Free account loads every
launch-critical surface with real content and meets a wall only at the four documented ceilings;
an anonymous visitor still meets the anonymous boundary; the boundary test and the Caddy
byte-alignment check both pass; and a **new test asserts that no path appears in both
`free_registered` and `premium.enforced_early`**, with a synthetic overlap proving it reds.
**Model.** builder (Opus) + **reviewer (Opus)** — this is the highest-blast-radius config change
in the program.
**Pre-launch:** **required, and it must land before the switch, not with it.**

### W3-2 — The four Free ceilings
**Scope.** Watchlist capacity (1 list / 15 symbols), board depth (3 rows), chat allowance
(`config/brain.yml` 5/wk → 20/wk — see W1-2 item 4, this interacts with the guest flip), history
window (7 days).
**Two of these are new enforcement, not one.** The 3-row board cap is *presentation* today:
`tier_preview.js` adds `mx-tier-blurred` / `mx-tier-hidden` to rows the server already put in
the public shell, so they are one view-source away. Converting it to the split build
(`docs/TIER_PREVIEW_PATTERN.md`) is real work and it is the only Free ceiling quoted in the
entitlement matrix that nothing enforces.
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
| W6-1 | **Essential annual $900 → $828** ($69/mo-equiv) | `config/plans.yml` + new Stripe price; old key into `legacy_lookup_keys` | **required** — this is the Finding A fix, and it replaces the earlier "withdraw Essential annual", which was not a config change: deleting the price block ships "$0 /mo", "SAVE 100%" and a Subscribe button that 400s, because both builders default a missing `unit_amount` to `0` |
| W6-2 | Pro annual $1,308 → $1,188 | same | required if adopted |
| W6-3 | Essential monthly $99 → $89 | same | secondary — keeps the ladder monotone |
| W6-4 | Founder cap 2,000 → 500; remove `allotment_pacing`; publish a close date + the four founder benefits | `config/plans.yml`, `app/billing.py`, `templates/plans.html.j2` | required if adopted |
| W6-5 | `subscription.tier_changed` event | `config/growth_events.yml` (added) + `app/billing.py` emitter | **required** — without it the pre-registered Essential test's second criterion cannot be computed |
| W6-6 | Make the builders **raise** on a missing price instead of defaulting to `0` | `scripts/build_site.py`, `scripts/build_public_pages.py` | recommended — it is what made W6-1's alternative dangerous |
| W6-7 | Feature moves between tiers (e.g. `terminal_live_options`) | **Stripe first**, catalog second | deferred past launch — see the matrix §6; the catalog edit alone is a no-op and the grandfather has no carrier |

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

**PL-0 — CLOSE THE PUBLICATION BYPASS. Nothing else on this list matters until it is done.**

`gh repo view --json visibility` returns **PUBLIC**, and every payload
`config/site_access.yml` promises to "403 for anonymous AND Free" is git-tracked:
`site/premiumdata/{etfs,special_situations,china_special_situations,confluence_screener}.json`,
`site/allocationdata/special_situations.json`, `site/chinaspecialdata/special.json`,
`site/capital-structure-data/`. The nightly Pages mirror uploads `site/` on every run and its
prune step removes only the bulk per-ticker trees. So the paid boundary is bypassable today by
anyone who clones the repository — no session, no URL to guess.

MNZ-OD3 accepted the *mirror* leak as a recorded risk in July, **before there was a paid
product**, and the repo went public on 2026-08-12 for CI billing, after that ruling. Neither
decision was made in the presence of the other. Options, any of which closes it:
gitignore those payloads and serve them from R2 like the other private artifacts; prune them in
`daily.yml`/`weekly.yml` before `upload-pages-artifact`; or take the repo private.
Until one lands, **every W3 acceptance criterion is unfalsifiable as a commercial boundary** —
it can pass at Caddy and be false on the internet. Owner: operator + builder. Blocks payment,
not the build.

Then, ordered:

```
W0-3b  fix "The Terminal — 3 indicators" on the billing summary       ← 1 PR (paired asset)
W1-2   guest chat: meter fix, pricing rows, guest ceiling, then flip  ← 3 PRs + operator
W2-1   registry → beacon whitelist (keyed on `wire`, never `name`)    ← 1 PR
W2-2/3 emitters                                                       ← 2 PRs
W1-3   create-before-register module + the anonymous-safe read        ← designer + builder
W3-1   grow free_registered (+ the free/enforced_early overlap test)  ← 1 PR + reviewer
W3-2   the four Free ceilings (incl. converting the board cap to a
       split build — it is presentation today, not enforcement)       ← 2–3 PRs
W4-1/2 contextual upgrade contract + escalation ladder                ← 2 PRs
W6-1/2/5 Essential annual $828, Pro annual $1,188, tier_changed event ← operator + 2 PRs
W6-4   founder cap + pacing + close date                              ← operator + 1 PR
       ── ops checklist (docs/ops/site-access.md) ──
       ── PL-0 CONFIRMED CLOSED ──
       PAYWALL_ENABLED=1
W5-1   since-you-were-last-here                                       ← within 2 weeks
```

**One more blocker that is not a task here:** MNZ-R2 gates all content gating on email
verification, custom SMTP and CAPTCHA being live. Verify the current state rather than assuming
it; this plan did not re-derive it.

**What changed in this section after review.** The first draft opened with W1-1 (promote
`mm_brain.js`) and filed the mirror as a parallel note. `mm_brain.js` landed on main the same
day, and the mirror turned out to be the smaller half of a publication problem whose larger half
— a public repository — postdates the ruling that accepted it. The critical path now leads with
the thing that must be true before money changes hands.

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
