# BioCatalyst P1-AVAIL-1 entitled production re-acceptance — 2026-08-28

Operation `BIOCATALYST-P1-AVAIL-1-20260827` / MAS-172. Companion to
`research/BIOCATALYST_P1_AVAIL_1_AVAILABILITY_AUDIT_2026-08-28.md` (the
origin-plane audit, merged as PR #6594 → `2299cbafe425…`). This receipt
records the step-(9) **real entitled production journey**, run under Sol's
option-(b) ruling and its no-credential-handling fence, after the Chairman
independently signed back in.

## Verdict

**P1-1 ENTITLED PRODUCTION RE-ACCEPTANCE: PASS.** The existing P1-1 Trial
Milestones capability is genuinely healthy in production on the real
authenticated path. The availability regression's root cause is confirmed:
**the Chairman's browser had been signed out of mastermind-x.com** (zero
Supabase session cookies at reproduction time); the signed-out designed
locked state is exactly the reported "interface is down". No code, config,
data, or infrastructure defect existed; no repair was needed or performed.
Sign-in alone restored the product, exactly as predicted by the audit.

## Session and method

- Real standard Google Chrome on the fleet host, paired via claude-in-chrome.
- The session was established by the Chairman/operator themselves; the agent
  never entered, requested, copied, refreshed, or otherwise handled any
  credential, token, or cookie value, and never mutated auth state. Only
  presence booleans and safe status/entitlement fields were read.
- All measurements below are from the live production page and live
  production APIs — no fixture, no diagnostic stylesheet, no server-side
  substitute. Timestamps ~2026-08-28 11:05–11:25Z.

## Authentication and HTTP contract (real browser, page context)

| Probe | Result |
|---|---|
| authenticated `/api/me` | **200**; `status=active`; features include `site_full` |
| entitled default Radar (`limit=50&horizon=next_365d&milestone_kind=all`) | **200**; `cache-control: private, no-store`; `Vary: Authorization, Accept-Encoding`; via Caddy through TencentEdgeOne |
| entitled invalid horizon (`horizon=bogus`) | **400** `detail=invalid horizon`; `private, no-store` |
| unsigned control (same origin, no Authorization header) | **401** `detail=missing bearer token`; `private, no-store`; `Vary: Authorization` |

## Current generation and payload (entitled response)

| Field | Production value |
|---|---|
| `as_of` | `2026-08-28T11:00:36.962572Z` (current-hour natural generation) |
| schema | `biocatalyst_api.v1` |
| health state | `fresh` |
| coverage class / configured / observed | `current_only` / 4 / 4 |
| returned rows / next cursor | 4 / none |
| timing states | 3 `upcoming` + 1 `occurred` + 0 `current` |
| beyond horizon / total events | 4 / 8 — exact arithmetic `3+1+0+4=8` |
| trials in cohort / with events | 4 / 4 |
| absent / unusable dates, missing identity | 0 / 0 / 0 |
| NCTs | `NCT06602479`, `NCT05020236` |
| revision states | 2 `has_revisions`, 2 `history_not_collected` |
| public lineage entries | 6 |

## Rendered journey

- Page hydrates from first-load skeleton to `ready`; **4 real Radar cards**;
  subtitle "4 trial milestones."; Radar summary line "3 upcoming trial
  milestones · 1 already reached · 4 beyond horizon · Current cohort: 4
  registered trials, 4 with a recorded milestone date."
- Trial dossier opened from the populated `NCT06602479` row: current
  official record renders; public link
  `https://clinicaltrials.gov/study/NCT06602479`; Evidence & Trust shows
  provider ClinicalTrials.gov, coverage "Current record only", source update
  May 19 2026, retrieved/as-of Aug 28 2026.
- **Revision lineage, EN and ZH, identical to the P1-1R standing lineage:**
  `2025-09-15 → 2026-12-18` (record version 9 → 10), `2026-09-07 →
  2025-09-15` (6 → 7), `2026-09-02 → 2026-09-07` (1 → 2); ZH renders the
  same pairs as `版本 9 → 10` etc. Language toggled through the page's own
  `data-lang`/`langchange` mechanism and restored to EN afterwards.

## Geometry — populated page, real deployed bytes

Measured per card: `scrollHeight<=clientHeight`, `scrollWidth<=clientWidth`
(row containment), every visible descendant rect inside its card (±1px),
pairwise adjacent-card overlap, document/body horizontal overflow, and
`#bci-queue` computed overflow.

| Viewport | Language | row / descendant / adjacent failures | doc horizontal overflow | queue |
|---|---|---|---|---|
| 2055×1270 | EN | 0 / 0 / 0 | none | `auto` (293/524) |
| 2055×1270 | ZH | 0 / 0 / 0 | none | `auto` (309/524) |
| 1280×900 | EN | 0 / 0 / 0 | none | `auto` (237/524) |
| 1280×900 | ZH | 0 / 0 / 0 | none | `auto` (254/524) |
| 500×844 (see deviation) | EN | 0 / 0 / 0 | none | `visible` (556/556) |
| 500×844 (see deviation) | ZH | 0 / 0 / 0 | none | `visible` (508/508) |

Minimum adjacent-row gap 7 CSS px at every cut — identical to P1-1R.

**Recorded deviation — mobile cut width.** The matrix names 390×844. A real
Chrome window on this host cannot go below ~500 px outer width; a popup
window was blocked by the popup blocker, and self-framing at 390 px is
forbidden by the site's own `frame-ancestors 'none'`. The authenticated
populated mobile layout was therefore measured at the narrowest real window,
**500×844**, which sits inside the same ≤760 px mobile breakpoint as 390 and
exhibits the designed mobile behavior (height-auto, `overflow-y: visible`
queue) with zero failures in both languages. The exact-390 viewport was
separately proven clean the same day for the page shell via real Chromium
viewport emulation (unauthenticated; see the audit doc). No fixture or page
mutation was used to force the cut.

## Runtime, network, and served-byte identity

- Console/page-error sweep on the fully tracked authenticated session:
  **zero errors**.
- Full first-party network window for the load + drill-down: 27 requests,
  every one **200/204** (fonts/assets/page/`api/collect`; entitled Radar
  200; `trials/NCT06602479` 200). **Zero 4xx/5xx/524.**
- Browser resource inventory carries exactly the accepted immutable stamps:
  `biocatalyst.css?v=712a3a77`, `biocatalyst.js?v=c35dac39`,
  `theme.js?v=0956049c` — the same assets SHA-256-proven byte-identical to
  `origin/main` in the audit. Serving checkout at audit: `/opt/macro` on the
  current main line (`eca7c761` era, advancing naturally).

## Root cause, finally stated

1. The Chairman's report window contained one genuine transient production
   incident — Supabase-upstream `/api/me` 502s, 22:56–22:59Z Aug 27,
   self-healed — but the durable cause of "the interface is down" was the
   **signed-out browser**: reproduced exactly (locked panel, empty Radar,
   "Full access required") in the Chairman's own Chrome while every server
   plane was healthy, and resolved by the Chairman signing back in.
2. No BioCatalyst code, data, serving, or edge defect existed. Nothing was
   repaired because nothing was broken; nothing production-side was mutated
   at any point in this operation.

## Non-claims

- This re-proves P1-1 at its existing bounded claim
  (`PROVEN_LIVE_COHORT_LIMITED`, four-NCT cohort). No full-parity,
  production-scale, post-soak, or P1-2 claim is made or implied.
- #6389 was not touched. No soak transition, no dossier-quote work (its
  separate 503 observation remains flagged to Sol in the audit doc).
- Terminal acceptance of this wave remains Sol's decision.
