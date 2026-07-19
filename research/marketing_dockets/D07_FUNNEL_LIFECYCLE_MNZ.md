# MKT-D07 — Funnel W1: UTM Attribution + Trial-Conversion Join (MNZ)

**Department:** Funnel (lifecycle) · **Priority: P2** · **Status: link plumbing buildable now; conversion join needs operator analytics access**
**Charter:** id=`lifecycle` ("Lifecycle, Conversion & Monetization", wave 2). **Monetization truth:** the MNZ program (#2923 + #2943) — Insider $59/$49, Pro $89/$69 annual-default, 14-day trial posture; every chart CTA already prints "Powerful stock signals · free 14-day trial · mastermind-x.com".

## Why

The north star is **marketing-attributable retained contribution profit** (Command's scorecard), and today we cannot attribute a single signup to a single post, account, or format. Funnel W1 is the thinnest honest attribution chain: tagged links out, conversion records in, joined in one ledger the CMO loop and Lab can read.

## What already exists (do not rebuild)

- CTA footer in `engine/marketing/chart_render.py` (image text — NOT clickable; the clickable URL lives in the post text, which is where tagging matters).
- Post provenance ids in `content_plan.json` / outbox items (D02) — the join key.
- MNZ signup/billing stack (Supabase + site auth) from the MNZ program.

## Deliverables

### W1a — tagged links (buildable now)
1. `engine/marketing/links.py` — canonical link builder: `https://mastermind-x.com/?utm_source=x&utm_medium=<account_id>&utm_campaign=<content_kind>&utm_content=<post_id>`. Content Studio + fastlane call it for every post-text URL. Keep URLs short and honest — no redirect cloaking.
2. Optional short-link map if raw UTM URLs prove ugly in posts: a static `site/go/<code>` → meta-refresh page generated nightly from the outbox (static-site-compatible; no server). Codes deterministic from post_id.
3. Tests: every planned post containing a URL contains exactly one tagged canonical link; codes stable across rebuilds.

### W1b — conversion join (needs operator: read access to signup records w/ UTM landing data)
4. Capture: ensure the landing page stores first-touch UTM params into the signup record (site-side change; coordinate with the MNZ stack — likely a small JS localStorage→signup-form field).
5. `engine/marketing/attribution.py` — nightly join: signups (exported/queried with utm fields) × outbox posted items → `data/marketing/attribution_ledger.jsonl` (post_id, account, kind, signup_at, plan, trial→paid flag when observable). Feed Lab (D03) and the Command scorecard.
6. Admin **Funnel page** (via `designer`): posts → clicks (if measurable) → trials → paid, per account/format, small-N honest.

## Acceptance

- W1a: content plan run → all post URLs tagged; fixture test green.
- W1b: a test signup with UTM params lands in the attribution ledger joined to its post; Funnel page renders the chain with printed Ns.

## Traps

- **Privacy/honesty:** first-touch UTM only, no fingerprinting, no cross-site tracking; the ledger stores plan tier + timestamps, not personal data beyond an opaque user id.
- Static-site law: no server-side redirects exist — the short-link lane must be static-page-based or skipped.
- Trial→paid lag is weeks; the Funnel page must show cohort windows, not same-day conversion (which will read as zero and panic the operator).
