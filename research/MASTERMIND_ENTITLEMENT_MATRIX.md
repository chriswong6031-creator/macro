# Mastermind-X — Entitlement Matrix (V1)

**Status:** RECOMMENDATION, 2026-08-12. Companion to `MASTERMIND_COMMERCIAL_ARCHITECTURE.md`.
**Authority note:** this document is a *proposal*. The authorities that actually decide access
today are, in order: `config/site_access.yml` (path class), `config/plans.yml` (products and
features), `config.yml` per-desk `gated:` switches, `config/brain.yml` (chat quotas), and
`terminal/lib/entitlement.ts` (Terminal gates). Nothing here takes effect until those change.

---

## 1. How to read this

Two matrices. **§3 is what ships today**, traced in code. **§4 is the recommendation.**
They are kept separate deliberately: conflating "what we sell" with "what we intend to sell"
is how Findings C2–C5 in the architecture document happened.

Access values:

| Symbol | Meaning |
|---|---|
| **●** | Full access |
| **◐ n** | Partial — n rows / n items / n days. Server-enforced **unless the row's Enforced-by cell says otherwise** — three rows below are client-side presentation gates, and the difference is the whole boundary |
| **◔** | Preview only — shell, methodology, honest totals, one sample; no member rows |
| **○** | Not available; shown as a labelled locked state naming what and how much |
| **✕** | Not present in the product at this tier at all |

---

## 2. The entitlement vocabulary

### 2.1 Today
Three feature keys, in `config/plans.yml`:

| Key | Held by | Gates |
|---|---|---|
| `site_full` | essential, pro | `app/paywall.py` — every premium path |
| `terminal_live_options` | essential, pro | `terminal/lib/entitlement.ts::hasLiveOptions` → `/api/flow`, `/api/flow/stream`, `/options` page |
| `chat_opus` | pro | Advertised as the Pro chat lane. **Note:** the deep lane is gated by the tier *quota* in `config/brain.yml` (`pro: {limit: 150}` vs `essential: {limit: 10}` vs `free: {limit: 0}`), not by a feature-key check — the key is currently descriptive rather than enforcing |

Plus two tier-string checks in the Terminal that bypass the feature vocabulary entirely:
`isPaidTier()` (any paid tier — gates Pine-script save, alerts) and `isProTier()` (gates one
alerts branch).

### 2.2 Recommended additions
Six keys, chosen so that every one of them is (a) enforceable server-side today and (b) maps to
a sentence a customer would recognize. **No key is proposed for something we cannot enforce.**

| Key | Tier | Enforces | Why it is a key rather than a tier check |
|---|---|---|---|
| `board_full` | essential, pro | full ranked-board depth (replaces the implicit `site_full`-does-everything) | Lets a single desk be opened or closed without touching the site-wide switch |
| `history_full` | essential, pro | history beyond the Free 7-day window | The cheapest, clearest "there is more here" signal we own |
| `watch_pro` | essential, pro | >1 watchlist, >15 symbols, portfolio positions, concentration/correlation reads | The P3 (Allocator) core |
| `alerts_realtime` | pro | push/email alerts with intraday latency | Real delivery cost; the P2 (Operator) core |
| `chat_deep` | essential, pro | **access** to the deep lane; the per-tier *volume* stays in `config/brain.yml` (Essential 10/mo, Pro 150/mo). Renamed from `chat_opus` because the model behind it has already changed once — Opus 4.8 → GPT-5.6 Sol with an Opus 5 backup — and a key must not name a vendor. **Not Pro-only:** an earlier draft made it Pro-only, which contradicted every tier table in this document set that promises Essential 10 deep chats a month | Real marginal token cost, metered by quota rather than by key |
| `export_api` | pro | CSV/JSON export, API keys | P4 (Builder) ceiling-raiser |

`site_full` is retained unchanged as the estate-wide gate so no existing enforcement path has
to be rewritten in the same change that introduces new keys.

---

## 3. CURRENT STATE — what ships on 2026-08-12

`PAYWALL_ENABLED=0` (`docs/ops/site-access.md:47`), so this is the live matrix, not a
hypothetical one.

| Surface / capability | Anon | Free | Essential | Pro | Enforced by |
|---|---|---|---|---|---|
| Every `*.html` page shell | ● | ● | ● | ● | 2026-08-04 ruling — the `@reg_html` matchers were removed |
| Server-rendered page content | ● | ● | ● | ● | same |
| Non-public assets (JSON/JS/CSS) | ○ 401 | ● | ● | ● | `app/regwall.py::_deny` |
| Ranked-board preview rows | ◐ 1 | ◐ 3 | ● | ● | `templates/tier_preview.js::capFor` — **client-side presentation gate, not a server gate.** Every row is server-rendered into the public shell and only blurred / `display:none`-d in the browser (`tier_preview.js` + `tier_preview.css`), so the capped rows are one view-source away. `docs/ops/site-access.md:8` calls it "presentation-gated"; `docs/TIER_PREVIEW_PATTERN.md` calls the shape "a marketing wall, not a gate" |
| Special Situations desk | ◔ | ◔ | ● | ● | `config.yml:6818 gated:true` + `premium.enforced_early` |
| China Special Situations | ◔ | ◔ | ● | ● | `config.yml:6834` |
| ETFs / fund conviction | ◔ | ◔ | ● | ● | `config.yml:1767` |
| Capital Structure | ◔ | ◔ | ● | ● | `/capital-structure-data/` prefix |
| Research Vault | ◐ 3 newest | ◐ 3 newest | **◐ 3 newest** | ● | `app/research.py::_can_view` — `_VIEW_TIERS = frozenset({"pro"})`. Catalog, search, view and download are **Pro-only**; Essential gets exactly the anonymous 3-report preview and a `402 paid_required`. `config/site_access.yml` only classifies the shell + client as anonymous-public |
| Confluence screener | ◐ rank 1 | ◐ rank 1 | ● | ● | server-side row omission |
| us_stocks summary | ◐ 1 | ◐ 3 | ● | ● | `tier_preview.js` — same client-side presentation gate, not server-enforced |
| **Everything else on the estate** | ○ assets 401 | ● | ● | ● | — **this is the problem** |
| Fast chat | ○ (guest default OFF) | ◐ 5/wk | ◐ 300/mo | ● uncapped | `config/brain.yml quotas` — Pro fast is `limit: -1` (operator ruling 2026-07-28), backstopped by `token_ceilings.fast` 5M tokens/mo |
| Deep chat | ✕ | ○ 0 | ◐ 10/mo | ◐ 150/mo | same |
| Chat launcher present at all | ✕ | ● | ● | ● | `mm_brain.js` absent from public allowlist |
| Terminal charting | ● | ● | ● | ● | free by ruling MNZ-OD4 |
| Terminal live options | ○ | ○ | ● | ● | `hasLiveOptions()` |
| Terminal advanced indicators | ◐ 1 | ◐ 1 | ◐ 15 | ● 31 | `terminal/lib/suites/*` per-module `tier` (1 free / 14 essential / 16 pro), enforced at three points against the tier from `/api/me`. Matches `config/plans.yml` exactly. **Client-side only** — no server recheck, and a `mm.devTier` localStorage override exists — so it is a product ladder, not a boundary |
| Pine script save | ○ | ○ | ● | ● | `isPaidTier()` |
| Alerts | ○ | ○ | ● | ● | `isPaidTier()` — Essential and Pro identical |
| Watchlist (local) | ● | ● | ● | ● | `templates/watchlist.js` localStorage. **Anonymous since 2026-08-12 only** (#5463 promoted `watchlist.js`, `watchstore.js`, `market_books.js`, `portfolio.js`, `mtf.js`); before that every one of the page's ten scripts was default-deny and anonymous production served a cached husk |
| Watchlist cloud sync | ✕ | ● | ● | ● | `templates/watchstore.js`, one-time fold on first sign-in |
| Watchlist — signal stack attached | ○ | ● | ● | ● | `stockdata.js` + `watchlist_risk.js` / `risk_core.js` / `factor_exposure.js` stay gated: the first would render graded per-ticker output to signed-out visitors through the page's `data_base` shim, the other three **are** the calibrated decision rule in code form. So the anonymous list persists and Mastermind says nothing about it |
| Watchlist count / size limit | none | none | none | none | **no limit exists at any tier** |
| History depth | full | full | full | full | **no limit exists at any tier** |
| Export / API | ✕ | ✕ | ✕ | ✕ | not built |
| Daily brief | ✕ | ✕ | ✕ | ✕ | not built |
| "Since you were last here" | ✕ | ✕ | ✕ | ✕ | not built |

**Reading of this table.** The paid delta is four desks, one Terminal surface, a chat quota, and
a Pine-script save button. Three of the four rows that *should* differentiate tiers — watchlist
limits, history depth, alerts granularity — have no limit at any tier, so they cannot
differentiate anything. And the one ladder we do advertise in detail (indicators) is enforced
nowhere.

---

## 4. RECOMMENDED STATE — V1

Organized by the five user-job groups from `MASTERMIND_COMMERCIAL_ARCHITECTURE.md` §5.3, because
that is the vocabulary the plans page and the upgrade copy should share.

### 4.1 READ — "What kind of market is this?"

| Capability | Anon | Free | Essential | Pro | Rationale |
|---|---|---|---|---|---|
| Macro dashboard + regime read | ● | ● | ● | ● | Market context, not our IP. It is the hook, and gating it costs us the SEO estate for nothing |
| Risk Radar state | ● | ● | ● | ● | Same. The *history* of the state is where the ceiling sits |
| Heatmaps (all markets) | ● | ● | ● | ● | "How the market traded" — already public by ruling, correctly |
| Breadth, medians, sector strength | ● | ● | ● | ● | Same |
| Market regime **history** | ◐ 7d | ◐ 7d | ● | ● | `history_full`. Cheap to serve; clearest depth signal we own |
| Methodology / calibration / track record | ● | ● | ● | ● | **Trust surfaces are never gated.** Charging for the proof that we were right converts a research product into a signal-seller |

### 4.2 FIND — "What should I be looking at?"

| Capability | Anon | Free | Essential | Pro | Rationale |
|---|---|---|---|---|---|
| Prophet — graded history of closed picks | ● | ● | ● | ● | Our best proof asset. Already partly public via `prophet/showcase.json` |
| Prophet — today's live board | ◐ 1 | ◐ 3 | ● | ● | Best-first preview hands over the head; newest-first preview per `docs/TIER_PREVIEW_PATTERN.md` |
| Prophet — timing state, armed triggers | ○ | ○ | ◐ state only | ● | Trigger *levels* are the paid part; state is the teaser |
| Flow Velocity cohorts | ◐ 1 | ◐ 3 | ● | ● | The most shareable artifact; the top of the ranking is the product |
| Theme intelligence | ◐ 1 | ◐ 3 | ● | ● | Same |
| Sector / subsector rotation | ● summary | ● summary | ● + detail | ● + detail | Summary is market context; the ranked detail is the read |
| Special situations (both markets) | ◔ | ◐ 3 newest | ● | ● | **Change from today:** Free gains 3 newest rows. A desk that shows a Free user nothing is a desk they never learn to want |
| ETFs / fund conviction | ◔ | ◐ 3 newest | ● | ● | Same |
| Screeners (confluence, etc.) | ◐ 1 | ◐ 3 | ● | ● | Consistent with every other ranked board |
| Alt data, dark pool, GEX, intraday flow | ○ | ◔ | ◐ EOD | ● live | Timeliness is the split — this is Architecture 2's line |

### 4.3 UNDERSTAND — "Why is this happening?"

| Capability | Anon | Free | Essential | Pro | Rationale |
|---|---|---|---|---|---|
| Ticker page — full read | ◐ 3/day | ● | ● | ● | The best single demonstration of cross-domain synthesis. 3/day anonymous is generous on purpose: it is the acquisition surface |
| Ticker page — graded emit (band, score, verdict) | ○ | ● | ● | ● | Registration's honest reward |
| Ticker page — full evidence / receipts | ○ | ◐ 1 open/day | ● | ● | Evidence-opening is the activation signal; Free must be able to do it, at least once a day |
| Fundamental forensics | ◔ | ◔ | ● | ● | Genuinely expensive to compute; no free rows, honest totals only |
| Earnings intelligence | ◔ | ◐ 2 excerpts | ● | ● | Matches the current plans-page promise |
| Capital structure | ◔ | ◔ | ● | ● | Unchanged |
| Chat — fast lane | **◐ 3/day** | **◐ 20/wk** | ◐ 300/mo | ● uncapped | **The two changed cells are the highest-leverage in this document.** Anonymous must be able to ask; and Free must be *materially better* than anonymous or registration is a downgrade (5/wk < 3/day) |
| Chat — deep lane | ✕ | ○ | ◐ 10/mo | ◐ 150/mo | Real marginal cost. Unchanged |
| Chat — receipts / links into site | ● | ● | ● | ● | The chat is a read surface over calibrated artifacts (MNZ-R5); its citations are the point |

### 4.4 WATCH — "What changed for *my* things?"

This group is where the paid product actually lives, and it is the group with the least
built today.

| Capability | Anon | Free | Essential | Pro | Rationale |
|---|---|---|---|---|---|
| Watchlist — create, local | ◐ 5 symbols | — | — | — | **Already built.** The create-before-register engine |
| Watchlist — saved, synced | ✕ | ◐ 1 list, 15 symbols | ◐ 10 lists, 250 symbols | ● unlimited | A limit a user can hold in their head. `watch_pro` |
| Watchlist — signal stack attached | ◐ 5 symbols | ● | ● | ● | The moment the product becomes theirs |
| Portfolio — positions, cost basis | ✕ | ○ | ● | ● | `watch_pro`. P3's core job |
| Concentration / correlated downside | ✕ | ◔ one-line teaser | ● | ● | The most under-sold capability in the estate; the canonical upgrade moment |
| Alerts — end-of-day, email | ✕ | ○ | ● | ● | Delivery cost is real but small |
| Alerts — intraday / push | ✕ | ○ | ○ | ● | `alerts_realtime`. **Change from today**, where `isPaidTier()` gives Essential and Pro identical alerts |
| "Since you were last here" | ✕ | ◐ weekly | ● daily | ● daily + intraday deltas | The retention loop. Free gets a real version — a weekly one — because a Free user with no reason to return is not a funnel |
| Daily brief (email) | ✕ | weekly | daily | daily + catalysts | Same |

### 4.5 PROVE / BUILD

| Capability | Anon | Free | Essential | Pro | Rationale |
|---|---|---|---|---|---|
| Track record, calibration lab, receipts | ● | ● | ● | ● | Never gated. Full stop |
| Research Vault — full catalog + PDFs | ◐ 3 newest | ◐ 3 newest | ◐ 3 newest | ● | **Unchanged, and it is the clearest Pro/Essential differentiator that already exists.** `app/research.py` already ships Pro-only. Essential's plans-page copy ("Every research report — the intelligence hub") does not match it and must be corrected before launch |
| Terminal — charting | ● | ● | ● | ● | Free for everyone, incl. unregistered (MNZ-OD4) |
| Terminal — advanced indicator suites | ◐ 1 | ◐ 1 | ◐ 15 | ● 31 | **Already shipped, byte-for-byte.** No build, no copy withdrawal. The only open item is that enforcement is client-side; a server recheck is a hardening task, not a commercial one |
| Terminal — live options | ○ | ○ | ○ | ● | **Change from today.** Live options is the clearest "timeliness" capability we own and it belongs to the execution tier. Moving it Pro-only is what makes Essential/Pro a segment split rather than a size split |
| Pine scripts — run | ● | ● | ● | ● | — |
| Pine scripts — save | ○ | ◐ 1 | ◐ 5 | ● | `isPaidTier` today; a small Free allowance costs nothing and hooks P4 |
| Export / API | ✕ | ✕ | ✕ | ● | `export_api`. Post-launch |

> **The `terminal_live_options` move is the single most consequential recommendation in this
> matrix, and it is the one I hold least tightly.** It cleanly separates the two tiers and gives
> Pro a reason to exist beyond a chat lane. But it takes a capability *away* from Essential
> relative to today's catalog, so it must not apply to anyone who has already bought Essential —
> see §6.

---

## 5. Limits, in one place

The whole point of §4 is that a customer can recall the ceiling without a table. Four numbers
for Free, five for Essential:

**Free:** 1 watchlist · 15 symbols · 3 board rows · 20 chat questions/week · 7 days of history.
**Essential:** 10 watchlists · 250 symbols · full boards · 300 fast + 10 deep chat/month ·
full history · end-of-day alerts.
**Pro:** everything, plus live options, intraday alerts, uncapped fast + 150 deep chat/month,
31 indicator suites, export.

Anything not on those lists is either free at every tier or does not exist yet. **If a new
feature cannot be placed on one of those lists, it does not get a gate** — it ships free until
someone can say which line it belongs on.

---

## 6. Migration and grandfathering

Non-negotiable: **no existing paying customer loses a capability they are currently paying for.**

- Anyone holding an `essential` entitlement at the cutover date keeps `terminal_live_options`
  permanently. **There is no mechanism for this today and inventing a new feature key does not
  create one:** the gate is `terminal/lib/entitlement.ts::hasLiveOptions`, which tests
  `e.features.includes("terminal_live_options")` — a hardcoded string literal in a different
  repository. A new key is invisible to it.
  Two mechanisms that would actually work, in preference order:
  1. **A second Stripe Product ("Essential Legacy")** that retains the `terminal_live_options`
     ProductFeature while the current Essential Product drops it, with the existing price
     `lookup_key`s moved to `legacy_lookup_keys` so live subscriptions keep resolving. No code
     in either repo changes.
  2. **Widen the Terminal gate first** to accept either key, merged and deployed in the
     charting-app repo **before** the `config/plans.yml` edit lands.
  Either way this is a two-repo, ordered migration, not a catalog edit — and it is the reason
  §5.2 of the architecture document holds this recommendation least tightly.
- **Deleting a feature from `config/plans.yml` does not revoke it.** `app/billing.py:799` reads
  `features = list(entitlement_keys) if entitlement_keys else _tier_features(tier)` — when
  Stripe returns ActiveEntitlements the catalog is not consulted at all — and
  `scripts/stripe_bootstrap.py::_attach_features` is attach-only, with no detach path. So the
  catalog edit is a **no-op** for every subscriber whose Stripe entitlements are non-empty.
  Any feature move is a Stripe-side migration first, a YAML edit second.
- The `insider` → `essential` alias in `lib/tiers.py` stays permanent and untouched. Nothing in
  this document may emit `insider`.
- Founding Pro's `duration: forever` grandfather is honored regardless of any later repricing.
  That is the entire promise of the offer, and breaking it once destroys the mechanism for good.

---

## 7. Cost, licensing, and the surfaces that constrain this matrix

**Marginal cost per active user — and why the first draft of this section was wrong.**

An adversarial pass on 2026-08-12 falsified three "bounded" claims that were here. They are
recorded rather than deleted, because each is a live prerequisite:

| Claim (withdrawn) | What the code does |
|---|---|
| "Pro deep chat cost is bounded by construction via `token_ceilings.pro = 2M`" | **A question is not a call.** `config/brain.yml` sets `tool_budget` 5 (fast) / 10 (pro) / 20 (research), so one turn is up to 6 / 11 / 21 `messages.create` calls, each re-sending the prefix. `brain_gateway` **assigns** `usage_dict` from the *final* response instead of accumulating across rounds, so every earlier round is invisible to both the ceiling and the `lib/ai_costs.py` ledger. Output is undercounted by roughly the round count; input by 2–4×. The ceiling is real but bounds a number that is not the spend |
| "For the uncapped Pro fast lane the admin cost panel is the control" | The panel cannot price the two models that actually serve the lanes: `config/ai_pricing.yml` carries `claude-opus-4-8` but neither `claude-opus-5` nor `gpt-5.6-sol`, and `estimate_cost_usd` returns `None` for both (prefix matching does not rescue it) |
| "Anonymous chat is bounded by the daily cap, the `mm_aid`/IP quota files, and `_GUEST_CFG_HI = 500`" | `_check_and_increment_guest_quota` checks two **request** counters and never reads `token_ceilings` — the signed-in path's only real backstop does not exist for guests. And `_GUEST_CFG_HI` clamps the per-guest *daily limit*: it permits 500 questions/day/visitor. It is a ceiling on generosity, not on spend. Separately, the IP half of the anti-farm is IPv4-only — the hash is over the full address, and one residential IPv6 /64 is 2^64 buckets |

**What is actually true about cost, and what it implies:**

| Capability | Cost driver | Posture |
|---|---|---|
| Deep chat, Pro | frontier tokens × rounds | The dominant per-user cost, and currently **under-measured**, not unbounded-by-design |
| Fast chat, Pro | uncapped requests × cheap model × rounds | The request cap is off (`limit: -1`); the token ceiling is the only bound, and it under-counts |
| Live options | vendor feed, largely fixed | Near-zero marginal per user; the constraint is licensing, not compute |
| Everything else | nightly batch, already paid | ~Zero marginal. **This is why gating breadth is the wrong lever** — hiding an already-rendered page saves nothing |
| Anonymous chat (proposed) | 3/day × guests | The one new cost this matrix introduces, and the only one that is **unbounded in token terms today** |

**Three prerequisites before the guest lane is switched on** (they are cheap, and they are the
difference between a measured bet and an unmetered one):
1. **Accumulate usage across tool rounds** in `brain_gateway` rather than assigning from the
   final response — otherwise every cost number we look at afterwards is wrong by 2–20×.
2. **Add `claude-opus-5` and `gpt-5.6-sol` to `config/ai_pricing.yml`**, so the ledger can price
   what it records.
3. **Give the guest lane a token ceiling and a global daily spend cap**, and collapse IPv6 to a
   /64 before hashing. Start at 3/day and raise on measured evidence.

**The unit-economics rule that survives unchanged:** meter what costs money per call (chat, AI
analysis, exports); do **not** meter what is already computed (pages, boards, history). Today's
matrix does the opposite.

**Licensing — flagged, not concluded.** Three surfaces need verification before their row above
is final. This document does not resolve them and should not be read as legal advice:
1. **Live options / flow** — the Terminal's vendor terms for redistribution to *anonymous*
   visitors. The matrix keeps live options paid-only, which is the conservative posture.
2. **Quote/breadth planes** already served publicly from the VPS live plane
   (`/live/quotes.json`, `/live/breadth.json`) — public today, presumably cleared; confirm the
   clearance covers the anonymous tier's expanded usage.
3. **The China daily-close tile map** (`/marketdata/china_heatmap.json`) — `site_access.yml`
   already records this as a deliberate "give" with the delay disclosed. Re-confirm before
   widening.

**Nothing in the recommended matrix depends on a feature we may be unable to expose to anonymous
users.** Every anonymous cell is either already public today or is our own computation over
public data.

---

## 8. What has to change to get from §3 to §4

Ordered by risk, lowest first. **Two of these are not config edits at all**, and an earlier
draft of this table said they were.

| # | Change | Where | Risk / note |
|---|---|---|---|
| 1 | Turn on the guest chat lane at 3/day | `admin/brain_guest_access.json` (untracked, hot-reloaded, no deploy) | Low to reverse, **not low to arm** — the three §7 prerequisites come first. And note item 2: this flip is not independent of it |
| 2 | Free fast-chat 5/wk → 20/wk | `config/brain.yml` | **Item 1 OVERRIDES this.** `brain_gateway._get_allowance` short-circuits: whenever guest access is enabled, the FREE tier's fast lane returns `{limit: <guest daily_limit>, period: "day"}` *before* `quotas.free.fast` is read. So turning on guest chat silently re-writes the Free allowance to the guest number. Decide the two together, or split the guest cap from the free cap in code |
| 3 | ~~Add `mm_brain.js` to the public allowlist~~ | — | **Done on main 2026-08-12** (#5409/#5463). Remaining: the SEO subtrees, whose document-relative injector still misses |
| 4 | Grow `free_registered` to the §4 set | `config/site_access.yml` | **Medium–high, and it has a trap.** `app/paywall.py` returns `204` for anything classified `free` **before** it consults `enforced_early(path)`, so putting a premium path in `free_registered` silently un-gates it — and no test covers the interaction. Add that test with the change |
| 5 | **Reprice** Essential annual $900 → $828 | `config/plans.yml` + a new Stripe price | Low — and it is the Finding A fix. *Withdrawing* it instead (the first draft's answer) is NOT a one-line edit: deleting the price block renders "$0 /mo", "Billed $0 a year", "SAVE 100%" and a Subscribe button that 400s, because both builders default a missing `unit_amount` to `0` |
| 6 | Move a feature between tiers | Stripe **first**, `config/plans.yml` second | **Not a config edit.** `app/billing.py:799` prefers Stripe ActiveEntitlements over the catalog, and `stripe_bootstrap._attach_features` never detaches. See §6 |
| 7 | Convert the ranked-board row cap from presentation to enforcement | `scripts/build_*` + `premium.enforced_early` | **High, and it is the only Free ceiling in §5 that is not enforced today.** The rows ship in the public shell and are hidden client-side |
| 8 | Watchlist / history / alert limits | macro-api + Terminal | High — real code, Waves 2–3 |
| 9 | Attach a read to the anonymous watchlist | product decision + `config/site_access.yml` | The gated renderers **are** the calibrated decision rule. This is a disclosure ruling, not a boundary edit — see §4.4 |

Items 1 and 2 are what change a stranger's first ninety seconds, and both are reversible within
a minute — once the §7 prerequisites are in place. Item 4 is the one that makes Free a product,
and it must land **before** `PAYWALL_ENABLED=1`, never with it.

**And one thing that is not on this list because it is upstream of all of them:** the repository
is PUBLIC and every `premium.enforced_early` payload is git-tracked, so the boundary this table
tunes is bypassable today by anyone who clones it. That is a hard predecessor to charging money
— see the implementation plan's critical path.
