# Onboarding & Subscription Flow ("the front door") — Masterplan by Fable

**Status:** CHARTERED 2026-07-23 (operator brief with Untitled-UI reference shots; this doc is the cold-start handoff).
**Primary repo:** `mastermind-terminal` (checkout `/Users/chriswong/Documents/Cluade/charting-app`, default branch
`master`) — Next.js app at app.mastermind-x.com, Supabase auth. **Secondary repo:** macro (`Macro Dashboard`) —
owns the Stripe billing spine and plan config.
**Mission:** replace the current thin signup with a beautiful multi-step onboarding + subscription experience that
lives entirely in a **large floating sheet/modal** (movable container, never a dedicated page), at the visual bar of
the operator's Untitled-UI references: split layout (form left / live product preview right), calm dark-capable
chrome, generous spacing, stepper dots, selectable cards with check states.

Before building: read this repo's `research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md` (MNZ — the standing
monetization program this extends), `docs/ACTIVE_BUILD_MAP.md`, `research/DO_NOT_REBUILD.md`, and the terminal
repo's `CLAUDE.md`/`AGENTS.md`/`DESIGN_OBSERVATORY.md`.

---

## 0. SURFACE RULING (CORRECTED 2026-07-23 — operator escalation; BINDING, read before anything else)

The original charter set "build home = mastermind-terminal" because the auth/account plumbing lives there.
That was plumbing-first and WRONG about the surface. **The sign-up/onboarding sheet's primary surface is the
LANDING** — www.mastermind-x.com (macro repo: `templates/index.html ↔ site/index.html`, plus `start.html`).
The operator's directive — one floating, movable container, never a dedicated page — means the sheet opens
IN PLACE over the landing when any Start free / trial / Log in CTA is clicked. Navigating the visitor to
app.mastermind-x.com to sign up is exactly the dedicated-page experience he rejected.

- **Primary build surface:** landing-native sheet in the macro repo, in the LANDING's design language (light
  Swiss / the pyramid-hero idiom — NOT chart-app idiom). Supabase JS handles auth client-side on the static
  page; billing uses the macro-api Stripe endpoints already merged (#3328, #3330).
- **Terminal app = secondary surface:** it reuses the flow for in-app log-in and upgrades. Work already built
  there is salvage material, not the destination.
- **Reference images:** committed under macro `mockups/refs/onboarding/` — the landing owns the look.

Standing lesson (also in CLAUDE.md §Spawn-handoff law): **the build surface follows the FUNNEL, not the
plumbing.** Where the machinery lives never decides where the user experience lives.

## 1. What exists today (verified 2026-07-23)

- **Terminal auth:** `terminal/components/AuthSheet.tsx` (sheet-style auth, includes a **WeChat login button —
  REMOVE it**, operator order), Supabase auth routes under `terminal/app/auth/*` (e.g. `auth/signout/route.ts`),
  i18n in `terminal/lib/i18n.tsx`. AuthSheet's zero-redirect pattern (terminal PR #153) is the ancestor of the
  floating-container requirement — extend the pattern, don't regress to redirects.
- **Stripe billing spine (macro repo, merged PR #3178, MNZ W2):** `app/billing.py` (checkout/webhook/portal +
  entitlements on macro-api), `config/plans.yml` (plan/price config), `scripts/stripe_bootstrap.py` (creates
  products/prices in Stripe), `scripts/deploy/0005_user_entitlements.sql`, `site/account.js`,
  `docs/ops/stripe-setup.md`. **Sandbox mode — operator: "go do whatever you want."**
  Verification trap: macro-api's FastAPI wraps routers in `_IncludedRouter` — verify endpoints with TestClient
  hits (401/503 ≠ 404), never by scanning `app.routes` (memory: cost a prior session an hour).
- **Current signup dashboard:** exists but judged weak by the operator — this is a REVAMP, not a from-scratch
  parallel surface.
- **Supabase on the free plan** — auth emails send from the supabase domain (custom domain needs a paid plan);
  operator accepts this for now.

## 2. Pricing & plans (LOCKED 2026-07-23 — landing already updated in the same charter PR)

| Tier | Monthly | Annual (per-mo) | Annual total | Discount | Trial |
|---|---|---|---|---|---|
| Free | $0 | $0 | — | — | none (no card ever) |
| Insider | **$69** | **$49** | $588 | ~29% | 7-day, card required |
| Pro | **$99** | **$69** | $828 | ~30% | 7-day, card required |

The deliberate wedge: annual Pro is only **$20/mo more than annual Insider** — the flow should surface that
comparison at the plan step ("+$20/mo for everything in Pro"). Naming everywhere: **Flash AI / Pro AI** (never
"Flash analyst"/"Pro Research"). Tier ORDER stays Free → Insider → Pro (operator asked whether Insider should be
the top-tier name; Fable's ruling, operator leaning accepted: keep Pro on top — "Pro" is the universally-read
top tier in SaaS, Pro couples to the Pro AI product name, and a rename would churn billing/copy/CI for a
connotation problem better solved with visual hierarchy. Revisit only if the operator overrules.)

**W0 alignment task:** update `config/plans.yml` + re-run `scripts/stripe_bootstrap.py` against the sandbox so
Stripe products/prices match the table; add the Pro trial (both paid tiers get `trial_period_days: 7`,
card-up-front via Checkout/Elements). The landing (`templates/index.html ↔ site/index.html` pair in the macro
repo) already shows these numbers — if any number changes again, update BOTH repos in one wave (cross-field
checklist: tier cards, badges, matrix headers, toggle %, zh mirrors, plans.yml, Stripe).

## 3. The flow (floating sheet, multi-step, stepper-dots)

Every step lives in one large floating container (drag-movable, dismissible, state-preserving). Split layout
where it earns its keep (form left / live preview right). Steps:

1. **Account** — first + last name (first name feeds personalization everywhere later: greetings, briefs,
   account chip), email + password OR Google OAuth. **No WeChat.** Terms line. Supabase signup + confirm email.
2. **Preferences** —
   - *Market focus*: US · China · Hong Kong · Canada · Global (multi-select chips; drives default dashboard,
     watchlist seeds, and which nightly brief they land on).
   - *Theme*: Light / Dark / **Auto** (operator's "system time-based": follow OS `prefers-color-scheme`, with a
     time-based fallback — dark after sunset — builder picks the cleanest honest implementation and labels it
     plainly).
   - *Optional extras (builder judgment, keep the step light — max 2 more)*: what they trade (stocks / options /
     crypto chips) and experience level. Everything skippable — never gate progress on optional data.
3. **Plan** — the interactive tier selector (see §4). Free / Insider / Pro cards + Annual↔Monthly toggle
   (annual preselected; show the per-tier save badge and the "+$20/mo Insider→Pro annual" wedge).
4. **Billing** (paid choices only — Free skips straight to done, **no card recorded**) — Stripe Elements or
   Checkout inside the sheet (Elements preferred to keep the floating-container experience; Checkout acceptable
   if Elements fights the sheet). Card capture starts the 7-day trial; copy states plainly when the first charge
   lands and that cancelling inside the trial costs nothing.
5. **Done** — personalized ("You're in, {firstName}"), what happens next (confirm email sent; trial end date if
   paid), primary CTA into the product with their market preference applied.

## 4. Plan-step design (operator's open question — RULED)

The operator floated: dropdown expanded details vs. short summarized lists. **Build the interactive summary
switcher** (his second idea — it is clearer than a crammed table): selecting a tier card repaints ONE summary
panel beside/below the cards —
- **Free selected:** "what you get" (short list) AND a visually-distinct "what you're missing" list (the
  Insider/Pro exclusives with their tier chips) — the miss-list is the upsell.
- **Insider selected:** its full short list + a one-line "everything in Free, plus…" framing + a subtle
  "+$20/mo more gets you Pro" row.
- **Pro selected:** "everything in Insider, plus…" list only (research library, 50 Pro AI dives, Bot Portfolios
  beta, MCP soon).
Additive framing ("plus…") keeps each list to 4–6 rows — no giant matrix in the sheet. Link "Compare every
feature →" opens the landing `#pricing` matrix in a new tab for completists. Feature names must match the
landing matrix vocabulary exactly (Flash AI, Pro AI, Insider & Congress desks, 13F flows now Insider-gated,
research reports now Pro — per landing PR #3297).

## 5. Emails (follow-on lane, charter here)

- Signup confirmation: Supabase auth email (supabase-domain sender is accepted for now; revisit custom domain
  when off the free plan).
- Receipts/trial reminders: Stripe's built-in emails ON in sandbox settings for v1; a proper transactional
  sender (Resend/Postmark) + branded templates is a NEXT lane — note it in the PR body, don't build it in W1.
- Trial-ending reminder (day 5) is the one email worth adding early once a sender exists — it is both churn
  courtesy and the annual-upsell moment.

## 6. Laws & guardrails

- **Design bar:** the operator's reference is Untitled-UI-grade polish. Read the terminal repo's design docs +
  invoke the `frontend-design:frontend-design` skill before building. Selectable cards with real check states,
  stepper progress, split preview panes, zero layout jump between steps (fixed sheet size, content transitions).
  No motion excess — recent ruling: labels/chips do NOT animate; motion budget goes to content transitions only.
- **Billing truth:** never fake a trial/price in UI that plans.yml/Stripe doesn't enforce. Free plan records NO
  card. Cancelling in-trial must genuinely not charge (Stripe trial semantics — verify in sandbox end-to-end).
- **The word "validated" is banned in user copy** (macro CI; keep the habit in the terminal repo too).
- Bilingual: terminal i18n (`terminal/lib/i18n.tsx`) — every new string EN+zh.
- Git law (both repos): fresh branch off the default branch, never reuse a squash-merged branch, worktrees, no
  bare `git stash`. Macro paired-template law if the landing is touched.
- Model routing: Opus builds (`builder`), Opus reviews (`reviewer`), design choices via `designer`/main loop.

## 7. Build order

- **W0 (macro repo, small PR):** plans.yml + stripe_bootstrap sandbox alignment to §2 (incl. Pro trial);
  TestClient checks on billing endpoints; confirm webhook entitlements map the new prices.
- **W1 (terminal repo, the flagship PR):** the floating-sheet flow, steps 1–3 + Free path end-to-end (account,
  prefs persisted to the user profile, plan select, done screen). WeChat button removed. Name personalization
  wired to at least the account chip + done screen.
- **W2 (terminal repo):** billing step — Stripe Elements/Checkout in-sheet, both trials live in sandbox,
  entitlements verified end-to-end (signup → trial → webhook → entitlement row → gated feature unlocks).
- **W3 (follow-on):** transactional email sender + branded confirm/trial-reminder templates.
- Each PR: same-day squash-merge, screenshots/crops of every step (light + dark + zh), and a full sandbox
  walkthrough as the verification artifact.

## 8. Open questions for the operator (ask at W1 kickoff)

1. Google OAuth only, or also Apple? (WeChat is dead per order.)
2. Should the plan step default-highlight Pro (anchor high) or Insider (current "MOST POPULAR" badge)?
   Fable's lean: highlight Pro annual with the wedge framing; Insider keeps the popularity badge.
3. Does the landing's "Start free / Start 7-day trial / Try Pro free" CTA set deep-link into this sheet with
   the tier preselected (recommended: yes — `?plan=pro&period=annual` params)?
