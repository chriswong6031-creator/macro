# Mastermind-X — Paywall System Spec (V1)

**Status:** IMPLEMENTABLE SPEC, 2026-08-12. Companion to `MASTERMIND_COMMERCIAL_ARCHITECTURE.md`.
**Audience:** the agent or engineer building a gate. This document is written to be followed
without reading the others.
**Precedence:** where this document and an existing house law disagree, the house law wins and
this document is wrong — specifically `docs/TIER_PREVIEW_PATTERN.md`, MNZ-R1 (fail-closed),
MNZ-R6 (locked, never silently absent), MNZ-R8 (tiers live in config), and the design doctrine's
banned-vocabulary rules.

---

## 1. The nine canonical rules

Every gate in the product obeys all nine. A gate that cannot obey them is not built.

**PW-1 — The server decides, every time.** Enforcement is server-side only. A client-side tier
check is chrome. If the content is what you charge for, **the shipped bytes must differ**. No
CSS hiding, no `display:none`, no JS filtering of a payload the browser already has.
*(Existing law: `docs/TIER_PREVIEW_PATTERN.md`, MNZ-R6.)*

**The estate does not satisfy this rule today, and the exception is the biggest one.** The
anonymous=1 / Free=3 ranked-board cap — the limit quoted in every tier table, including §5 of
the entitlement matrix — is `templates/tier_preview.js` blurring and hiding rows that are
already in the public HTML. `docs/ops/site-access.md` calls it "presentation-gated"; this
document calls it a marketing wall. Converting it to a split build is the single largest
enforcement gap between the recommended matrix and the shipped one.

**PW-2 — Never hide the existence of value.** Every gated surface shows four things without
exception: **what it is**, **how it is computed**, **how much of it there is** (honest totals),
and **a genuinely readable sample**. A count names nobody; the member rows are the product.

**PW-3 — Preview by recency, never by rank.** For any ordered board, the free slice is the
*newest* rows, never the *best* ones. Previewing a best-first board hands over its head, which is
the part people pay for. For evidence, the free slice is the summary; the receipts are paid.
*(Existing law.)*

**PW-4 — Gate depth, not breadth.** A user at any tier can reach every *page*. What they cannot
reach is the *bottom* of a page. Breadth is our credibility and costs ~nothing marginal to serve;
depth is the product.

**PW-5 — One wall per page. Maximum.** A page with five padlocks is nagging, and it reads as a
product that is mostly withheld. If a page needs more than one wall, the page is gated at the
wrong altitude — gate the page's payload once, in one place.

**PW-6 — No blur, ever.** Blurred content says "we have something and will not tell you what",
which is the least persuasive possible statement. Use a **labelled locked slot**: the count, the
kind, and one line naming what the rows would tell them.

**PW-6b — Classification order is part of the gate.** `app/paywall.py` evaluates
`deny → public → free → premium` and returns `204` for anything classified `free` **before** it
consults `enforced_early(path)`. So a path listed in *both* `free_registered` and
`premium.enforced_early` is FREE, silently, and no test covers the interaction. Anyone widening
`free_registered` must diff it against `enforced_early` first, and ship the test that pins it.

**PW-7 — Locked is never silently absent.** A gated JSON route returns
`403 {"locked": true, "tier": "<required>", "surface": "<id>"}` and the panel renders an explicit
locked state. A missing panel and a gated panel must never look the same. *(MNZ-R6.)*

**PW-8 — The wall names what the user just tried to do.** Generic upgrade copy at a specific
moment is the single largest waste in the funnel. See §5.

**PW-9 — Meter what costs money; never meter what is already computed.** Usage gates belong on
chat, AI analysis, and exports. Pages, boards, and history are already computed nightly — gating
them saves nothing and costs conversion. *(This inverts what the product does today.)*

---

## 2. Choosing a gate type

Seven mechanisms. Pick by the decision table; do not invent an eighth.

| Mechanism | Use when | Never use when | Reference implementation |
|---|---|---|---|
| **Preview slice (`◐ n`)** | Ordered board, list, or feed | The list has <5 items — a 3-of-4 preview is a joke | The **split build** (`docs/TIER_PREVIEW_PATTERN.md`, `special_situations`). **Not** `templates/tier_preview.js` on its own: that file caps rows by adding `mx-tier-blurred` / `mx-tier-hidden` in the browser, over rows the server already put in the public shell. It is the right *chrome* for a split build and a marketing wall without one |
| **Shell preview (`◔`)** | A desk whose every row is proprietary | The page has free-standing market context that could be shown | `special_situations` (the ratified reference) |
| **History window** | Any time series or state history | The series is <30 points | *(to build — `history_full`)* |
| **Detail limitation** | Summary is legible alone and evidence is the depth | The summary is meaningless without the evidence — that is a broken surface, not a gate | Ticker page evidence drawer |
| **Usage limit** | Real marginal cost per call | Cost is zero (see PW-9) | `brain_gateway._check_and_increment_quota` |
| **Hard lock** | Real licensing or cost constraint on the whole surface — live options, exports | Anything else. Hard locks are the last resort, not the default | `hasLiveOptions()` |
| **Delayed data** | Licensing permits delayed but not real-time | We have not verified the licensing | China heatmap (delay disclosed) |

**Blur, disabled buttons scattered across a page, and "hidden by CSS" are not on this list.**

### 2.1 The gate-selection decision procedure

```
Is the surface's value 100% proprietary rows, with no free-standing market context?
  YES → Shell preview (◔). Show totals + methodology + the upgrade wall. One wall.
  NO  ↓
Is it an ordered board / list / feed?
  YES → Preview slice (◐ n), NEWEST-first. n = 1 anon / 3 free.
  NO  ↓
Is it a time series or a state history?
  YES → History window. 7 days free, full paid.
  NO  ↓
Does each call cost real money (LLM tokens, vendor API, export compute)?
  YES → Usage limit, server-metered, with the remaining count visible BEFORE the last one.
  NO  ↓
Is there a licensing or feed-cost constraint on the whole capability?
  YES → Hard lock, with a preview of what it looks like (a screenshot or a sample, not a blur).
  NO  → SHIP IT FREE. If none of the above applies, the surface has no business being gated.
```

The last line is load-bearing. The default answer is free.

---

## 3. Tier resolution — the contract

**One authority: `public.user_entitlements`, written only by the Stripe webhook, the reconciler,
the Substack sync, and operator comps.** Nothing else writes it; LLMs never touch it (MNZ-R3).

Every gate resolves tier through one of exactly three paths, all of which already exist:

| Context | Path | Cache | Failure mode |
|---|---|---|---|
| Caddy-served static asset | `/api/regwall/check` → `/api/paywall/check` | 45s auth, 60s entitlement | **Deny** (MNZ-R1) |
| macro-api route | in-process entitlement read (`app/billing._pg`) | 60s | **Deny** |
| Terminal route/page | `GET {BILLING_BASE}/api/me` via `terminal/lib/entitlement.ts` | 45s, **positive-only** | **Deny** |

**Rules for anyone adding a gate:**
1. **Normalize before you compare.** Always `normalize_tier()` (`lib/tiers.py`) / `normTier()`
   (JS). The legacy string `insider` arrives from pre-rename entitlement rows and from
   far-future-cached `immutable` JS, and has **no expiry**. An un-normalized comparison silently
   drops a paying customer into the free bucket — the exact failure `lib/tiers.py` documents.
2. **Never cache a negative.** A fail-closed "no" must be re-derived from the authority every
   time, or a user who just paid stays locked out for the cache TTL.
3. **Never gate on a client-supplied tier**, an `/api/me` response the client forwarded, or a
   `profiles.is_pro`-style UI hint.
4. **Write paths resolve fresh** — no cache on any gate that authorizes a mutation.

---

## 4. Wall anatomy

Every wall, at every tier, in every language, has exactly five parts and no sixth.

```
┌─────────────────────────────────────────────────────────────┐
│  ① WHAT THIS IS      one plain-word line, no internal names  │
│  ② HOW MUCH          honest total: "312 filings ranked"      │
│  ③ THE SAMPLE        the readable free slice (PW-3)          │
│  ─────────────────────────────────────────────────────────── │
│  ④ THE SPECIFIC ASK  names what THEY were reaching for       │
│  ⑤ ONE ACTION        one primary button. one.                │
└─────────────────────────────────────────────────────────────┘
```

**Copy law** (inherits the design doctrine; violations are CI-checkable):
- **Plain words only.** No internal state names, no study names, no untranslated statistics, no
  raw slugs. A wall is a glance-tier surface.
- **No falsifier / refutation vocabulary**, ever, on a customer surface (operator ruling
  2026-07-27). Full verdicts live on the Calibration Lab, below the fold.
- **Never say "unlock advanced analytics."** It says nothing. See §5 for what to say instead.
- **Bilingual EN/ZH**, dual-span pattern, and never translated text in a `title=` attribute
  (CI-guarded).
- **Never use the word "validated"** in user-facing text (`scripts/check_validated_claims.py`).

---

## 5. The contextual upgrade system

**The problem this solves.** `templates/tier_preview.js::openUpgrade()` currently sends every
user to the same sheet with `plan: "essential"` hardcoded, regardless of what they were reaching
for. The moment we know most about a user's intent is the moment we say the least specific thing.

### 5.1 The contract

Every wall, lock, and ceiling emits an **upgrade context** object, and the upgrade sheet renders
from it:

```js
{
  surface:  "portfolio_concentration",   // stable id — matches the entitlement matrix
  reason:   "ceiling" | "tier" | "usage" | "history",
  wanted:   "correlated downside across your 8 holdings",  // plain-word, specific
  evidence: { symbols: ["NVDA","AMD","AVGO"], count: 3 },  // OPTIONAL, user's own data only
  required: "essential",                 // the LOWEST tier that satisfies it
  hits:     3                            // encounters of THIS surface in 14 days
}
```

**`required` must be the lowest sufficient tier.** Sending a user to Pro for something Essential
covers is both a worse conversion and a small dishonesty.

### 5.2 Message construction

Three sentences, in this order, always:

```
1. THE OBSERVATION   — what is true about THEIR data or THEIR behavior right now
2. THE CAPABILITY    — what Mastermind does about it, continuously
3. THE ACTION        — one button, naming the outcome, not the tier
```

**Do not write:**
> Upgrade to Pro to unlock advanced portfolio analytics.

**Write:**
> **Three of your eight positions are driven by the same semiconductor factor.**
> Mastermind Essential watches correlated downside across everything you hold, every night, and
> tells you when the overlap gets dangerous.
> **[ See it on your list ]**

### 5.3 Escalation by encounter count

The same ceiling produces a different response depending on how many times they have hit it.
`hits` counts encounters of *this* `surface` in a rolling 14 days.

| `hits` | Response | Rationale |
|---|---|---|
| 1 | **Inline, quiet.** The locked slot, its count and kind. No modal, no CTA beyond a text link | The first encounter is information: "there is more here." Selling now is selling to someone who has not decided they want it |
| 2 | **Inline + the observation sentence.** Still no modal | Reinforce specificity, still no interruption |
| 3 | **The upgrade sheet**, contextual, with the Day Pass offered if eligible | Third time is intent. This is the **primary upgrade trigger** |
| 4+ | Return to level 2 | Never nag. A user who declined twice is not persuaded by a fourth modal; they are annoyed by it |

**Never show a modal on a user's first session, at any `hits` count.** A stranger who has not
yet received anything cannot be asked for anything.

### 5.4 The catalogue of upgrade moments

Nine moments, each with its surface id, trigger and the specific thing it names.

| Surface id | Trigger | Names |
|---|---|---|
| `watchlist_capacity` | 16th symbol / 2nd list | "You're tracking 15 names. Essential watches 250 across 10 lists." |
| `board_depth` | Expand a board past row 3 | "You're seeing the 3 newest of 47 ranked names." |
| `history_window` | Scroll a series past 7 days | "You're looking at 7 days. The full history goes back to <date>." |
| `evidence_depth` | Open a receipt beyond the free daily one | "Every read here has its working shown. Essential opens all of it." |
| `portfolio_concentration` | View the concentration teaser | The correlated-factor observation (§5.2) |
| `prophet_timing` | Open a timing/armed-trigger detail | "You can see the board. Pro shows when each name arms." |
| `alerts_realtime` | Configure an alert faster than EOD | "You'll hear at 6pm. Pro tells you when it happens." |
| `chat_allowance` | Reach the weekly/monthly fast-lane cap | "You've used your 20 questions this week. Essential is 300 a month." |
| `chat_deep` | Request the deep lane without entitlement | "This one needs the deep research lane." |

Each id is stable, emitted in telemetry (`paywall.encountered` with `surface`), and joins
directly to conversion analysis — so within 30 days we know which of the nine actually sells.

---

## 6. Usage gates

For the three metered capabilities (chat fast, chat deep, exports):

1. **The remaining count is visible before the last one is spent** — a meter, not a surprise.
2. **The last one is not a cliff.** At zero: state what they used, when it resets, and the
   upgrade. Never a bare error.
3. **Server-enforced, settled from actual usage** (`response.usage`), never a client-reported
   count. *(MNZ-R10 — already implemented in `brain_gateway`.)*
4. **The period is stated in the same words as the plans page.** "20 a week" on the plans page
   and "resets Monday" in the meter are the same promise; they must not drift. Both derive from
   `config/brain.yml` (see the truth fix in `…ARCHITECTURE.md` §8).
5. **A quota refusal is a `402`, not a `403`.** `403` means "not your tier"; `402` means "your
   tier, spent". The upgrade copy differs, so the status must.

---

## 7. What must never be gated

A short, absolute list. Anything on it that acquires a gate is a bug.

1. **Trust surfaces** — track record, calibration lab, methodology, receipts on already-visible
   claims, coverage/abstention disclosures. Charging for the proof that we were right converts a
   research product into a signal-seller.
2. **Honest totals.** The count of things behind a wall is free, always. A count names nobody.
3. **The disclosure surfaces** — staleness banners, "read being updated" chips, data-source
   notes. These load-bear on trust and on the freshness sentinel's dead-man switch.
4. **Legal, support, unsubscribe, about.** Already public by ruling, for structural reasons.
5. **The chat launcher itself.** The allowance may be zero; the *presence* of the capability is
   an acquisition surface. *(`mm_brain.js` became public on 2026-08-12; the guest lane it
   talks to is still switched off, so the launcher opens and the first question 402s.)*
6. **Anything a search crawler must read to rank a page we want ranked.** A 302 to `/?signin=1`
   is a soft-404 to Googlebot; `config/site_access.yml` already records that lesson.

---

## 8. Implementation checklist for a new gate

Copy this into the PR description.

- [ ] Gate type chosen via the §2.1 decision procedure; the "ship it free" branch was genuinely
      considered and the reason for rejecting it is stated.
- [ ] The split is a **build split**: the free shell and the paid payload are rendered from the
      **same partial**, so the preview and the remainder cannot drift.
- [ ] Paid payload lives under a path covered by `premium.enforced_early` in
      `config/site_access.yml` (or the site-wide premium class post-launch).
- [ ] `config.yml` carries a `gated:` switch for the desk, so it can be re-opened without code.
- [ ] The page renders all five wall parts (§4); copy passes the banned-vocabulary check.
- [ ] The JSON route returns `403 {"locked":true,"tier":…,"surface":…}`; the panel renders a
      locked state, not an empty one.
- [ ] The upgrade context object (§5.1) is emitted with a **stable surface id**.
- [ ] `paywall.encountered` telemetry fires with that id.
- [ ] Tier comparison goes through `normalize_tier` / `normTier`.
- [ ] Negative entitlement answers are **not** cached.
- [ ] Tests: signed-out → locked; Free → locked; entitled → 200; **entitled-then-revoked →
      locked within one TTL**; and a `?probe=UNIQUE` cold-cache check on both schemes.
- [ ] The free shell contains **zero** paid rows — verified by grepping the built HTML, not by
      reading the template.

That last item catches the most common failure in this codebase's own history: a template that
looks split while the builder still bakes every row into the shell.

---

## 9. Anti-patterns, each with a real precedent

| Anti-pattern | Why it is banned | Precedent in this repo |
|---|---|---|
| Client-side row hiding | One `view-source` away | `docs/TIER_PREVIEW_PATTERN.md` opens with this |
| Blur | Says "we have something, won't say what" | — |
| A styled shell whose every data fetch 401s | Worst of both boundaries: protects nothing a stranger wanted, advertises nothing we sell | `config/site_access.yml`, the fundamental_forensics block — its exact words |
| Gating an asset an open shell requires | Same class; 69 instances found estate-wide | `research/SITE_ACCESS_ASSET_CENSUS_2026_08_11.md` |
| Best-first preview | Hands over the ranked head | `config/site_access.yml`, the etfs block |
| Gating a page a crawler must read | 302 → soft-404; costs the crawl, gains nothing | `site_access.yml`, the special_situations block |
| A wall over content that is free | "A wall over content that is free would be a lie" | `site_access.yml`, china_heatmap block |
| Five walls on one page | "would be nagging" | same block |
| A marketing claim with no enforcer | Sells something we do not deliver | `terminal_indicators` 1/15/31, unenforced |
| A quota copy string that is a literal | It is right until someone reprices the lane, then it is silently wrong and no test notices | ~20 hand-typed chat cells across **five** surfaces — plans page, landing, onboarding sheet, and `theme.js`'s signed-in billing summary. All correct on 2026-08-12, all bound to nothing until this PR. The fifth surface was found only by adversarial review, after the first four were pinned — which is the argument for deriving rather than pinning wherever a build step exists |

The last two are the ones to watch, because they fail *silently* and only the customer finds out.

---

## 10. Rollout sequence for `PAYWALL_ENABLED=1`

The switch is estate-wide and binary. Turning it on today would collapse Free to "shells with no
data", because `free_registered` in `config/site_access.yml` currently lists 11 exact paths and
3 prefixes. The order is therefore non-negotiable:

1. **Grow `free_registered`** to the full Free set in `MASTERMIND_ENTITLEMENT_MATRIX.md` §4.
   Verify with a signed-in Free account against every launch-critical surface.
2. **Ship the depth gates** (board rows, history window, watchlist capacity) as
   `premium.enforced_early` paths, so they are live and observable while the switch is still off.
3. **Verify the ops checklist** already written in `docs/ops/site-access.md` — email
   verification, SMTP, CAPTCHA, Stripe drills, comp/trial/free/past_due account probes, EdgeOne
   cache-bypass on both schemes, and the GitHub Pages mirror decision.
4. **Then, and only then,** `PAYWALL_ENABLED=1`.

**Publication is a hard blocker, not a caveat — and the mirror is only half of it.** Two
addresses serve the premium payloads without ever touching Caddy:
1. **The repository is PUBLIC** (`gh repo view --json visibility` → `PUBLIC`, since 2026-08-12
   for CI billing), and `site/premiumdata/{etfs,special_situations,china_special_situations,
   confluence_screener}.json`, `site/allocationdata/special_situations.json`,
   `site/chinaspecialdata/special.json` and `site/capital-structure-data/` are all git-tracked.
   Those are exactly the paths `config/site_access.yml` promises to "403 for anonymous AND
   Free". One `git clone` returns them.
2. **The nightly GitHub Pages mirror** uploads `site/` on every run; its prune step removes only
   the bulk per-ticker trees.

MNZ-OD3 recorded the mirror as an operator-accepted risk *before* there was a paid product, and
the public-repo half is newer than that ruling and has never been adjudicated against it.
Until both are closed — by gitignoring/pruning those payloads, or by the repo going private —
`PAYWALL_ENABLED=1` gates a door in a building with no walls, and W3's acceptance criteria are
unfalsifiable as *commercial* boundaries even when they pass at the edge.
