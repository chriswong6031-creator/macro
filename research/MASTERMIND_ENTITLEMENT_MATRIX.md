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
| **◐ n** | Partial — n rows / n items / n days, server-enforced |
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
| `chat_deep` | pro | deep lane (rename of `chat_opus` — the model behind it has already changed once, from Opus 4.8 to GPT-5.6 Sol with Opus 5 backup, and the key should not name a vendor) | Real marginal token cost |
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
| Ranked-board preview rows | ◐ 1 | ◐ 3 | ● | ● | `templates/tier_preview.js::capFor` |
| Special Situations desk | ◔ | ◔ | ● | ● | `config.yml:6818 gated:true` + `premium.enforced_early` |
| China Special Situations | ◔ | ◔ | ● | ● | `config.yml:6834` |
| ETFs / fund conviction | ◔ | ◔ | ● | ● | `config.yml:1767` |
| Capital Structure | ◔ | ◔ | ● | ● | `/capital-structure-data/` prefix |
| Research Vault | ◐ 3 newest | ◐ 3 newest | ● | ● | `site_access.yml` — PDFs behind `/api/research/*` |
| Confluence screener | ◐ rank 1 | ◐ rank 1 | ● | ● | server-side row omission |
| us_stocks summary | ◐ 1 | ◐ 3 | ● | ● | `tier_preview.js` |
| **Everything else on the estate** | ○ assets 401 | ● | ● | ● | — **this is the problem** |
| Fast chat | ○ (guest default OFF) | ◐ 5/wk | ◐ 300/mo | ● uncapped | `config/brain.yml quotas` — Pro fast is `limit: -1` (operator ruling 2026-07-28), backstopped by `token_ceilings.fast` 5M tokens/mo |
| Deep chat | ✕ | ○ 0 | ◐ 10/mo | ◐ 150/mo | same |
| Chat launcher present at all | ✕ | ● | ● | ● | `mm_brain.js` absent from public allowlist |
| Terminal charting | ● | ● | ● | ● | free by ruling MNZ-OD4 |
| Terminal live options | ○ | ○ | ● | ● | `hasLiveOptions()` |
| Terminal advanced indicators | ● all 31 | ● all 31 | ● all 31 | ● all 31 | **nothing** — the 1/15/31 ladder is advertised and unenforced |
| Pine script save | ○ | ○ | ● | ● | `isPaidTier()` |
| Alerts | ○ | ○ | ● | ● | `isPaidTier()` — Essential and Pro identical |
| Watchlist (local) | ● | ● | ● | ● | `templates/watchlist.js` localStorage |
| Watchlist cloud sync | ✕ | ● | ● | ● | `templates/watchstore.js` |
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
| Terminal — charting | ● | ● | ● | ● | Free for everyone, incl. unregistered (MNZ-OD4) |
| Terminal — advanced indicator suites | ◐ 1 | ◐ 1 | ◐ 15 | ● 31 | **Requires building the enforcement that `config/plans.yml` already advertises.** Until it exists, the claim must come off the plans page |
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
  permanently, via a grandfather feature key written by the migration
  (`essential_legacy_live_options`) rather than by a code branch. New Essential subscriptions
  after the cutover do not receive it.
- The `insider` → `essential` alias in `lib/tiers.py` stays permanent and untouched. Nothing in
  this document may emit `insider`.
- Founding Pro's `duration: forever` grandfather is honored regardless of any later repricing.
  That is the entire promise of the offer, and breaking it once destroys the mechanism for good.

---

## 7. Cost, licensing, and the surfaces that constrain this matrix

**Marginal cost per active user (rough, order-of-magnitude, for tiering decisions only):**

| Capability | Cost driver | Rough monthly cost at cap |
|---|---|---|
| Deep chat, Pro | 150 msgs × frontier model | The dominant per-user cost. `config/brain.yml` sets `token_ceilings.pro = 2M`, and `_check_and_increment_quota` enforces it as a backstop — so the cost is *bounded by construction*, which is the right design |
| Fast chat, Pro | uncapped msgs × DeepSeek/Haiku | **The request cap is off (`limit: -1`); the 5M-token monthly ceiling is the only bound.** That is the right shape — a fair-use ceiling rather than a counted allowance — but it means Pro fast-lane cost is bounded by tokens alone, so the admin cost panel is the control, not the config |
| Live options | Vendor feed, largely fixed | Near-zero marginal per user; the constraint is licensing, not compute |
| Everything else | Nightly batch, already paid | ~Zero marginal. **This is why gating breadth is the wrong lever** — we are not saving anything by hiding a page that was already rendered |
| Anonymous chat (new) | 3/day × guest | The one new cost this matrix introduces. Bounded by the existing daily cap + `mm_aid`/IP quota files, and by `_GUEST_CFG_HI = 500` |

**The unit-economics rule that follows:** meter what costs money per call (chat, AI analysis,
exports); do **not** meter what is already computed (pages, boards, history). Today's matrix does
the opposite — it gates cheap breadth and leaves expensive chat generous at every tier.

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

## 8. What has to change in config to get from §3 to §4

Ordered by risk, lowest first. Each is a config edit, not a rewrite.

| # | Change | File | Risk |
|---|---|---|---|
| 1 | Turn on the guest chat lane at 3/day | `admin/brain_guest_access.json` (untracked, hot-reloaded, no deploy) | Low — reversible in 20s |
| 2 | Add `mm_brain.js` to the public allowlist | `config/site_access.yml` + the Caddyfile byte-aligned list | Low — payload-free client; every brain API route keeps its own auth |
| 3 | Free fast-chat 5/wk → 20/wk | `config/brain.yml` | Low |
| 4 | Grow `free_registered` to the §4 set | `config/site_access.yml` | Medium — this is the change that makes Free a product, and it must land **before** `PAYWALL_ENABLED=1` |
| 5 | Withdraw Essential annual from sale | `config/plans.yml` + plans template | Low, operator decision |
| 6 | New feature keys + tier membership | `config/plans.yml` + Stripe Entitlements | Medium — requires the Stripe-side products to match |
| 7 | Watchlist / history / alert limits | new enforcement, macro-api + Terminal | High — real code, Waves 2–3 |
| 8 | Indicator ladder enforcement | Terminal repo | High — **or remove the claim.** Do not ship launch with an advertised, unenforced ladder |

Items 1–3 are the ones that change a stranger's first 90 seconds, and they are all reversible
within a minute. They should not wait for the rest.
