# Tier-preview pattern — how a paid page still gives Free something real

Ratified 2026-07-25 with the Special Situations gate (the reference
implementation). Read this before gating any other page.

## The problem it solves

Our page-level access control is all-or-nothing: `config/site_access.yml`
classifies a path `public | free_registered | premium | deny`, and once
`PAYWALL_ENABLED=1` a premium page answers a Free account with a 403
interstitial. That is the right control for a data artifact and the wrong one for
a product page — a visitor who never sees the desk work has no reason to pay for
it. The Research Vault already showed the better shape: everyone gets the newest
report, members get the shelf.

Two things make this non-trivial:

1. **Our desks are server-rendered.** Hiding rows with CSS or a JS tier check is
   a marketing wall, not a gate: the rows are still in the document, one
   `view-source` away. If the content is what you charge for, the shipped bytes
   have to differ.
2. **The paywall is still staged off** (`PAYWALL_ENABLED=0`, see
   `docs/ops/site-access.md`). Waiting for the site-wide launch to gate one desk
   is not an option, and arming the whole estate to gate one desk is worse.

## The shape

**Split the build. The split is the gate.**

```
site/<page>.html                     free-visible shell  ── free_registered
  · honest totals + methodology + a small, genuinely readable preview slice
  · an upgrade wall where the rest of the content would be
  · inert copies of the controls the paid board needs (see "controls" below)

site/premiumdata/<page>.json         paid payload  ── premium, enforced NOW
  · {schema: tier_payload.v1, gated, required_tier, built, …, *_html}
  · the rows/panels the shell does NOT contain, rendered from the SAME partials
```

At runtime the shell **attempts to hydrate**: it asks for the payload and, on
`200`, appends the rows, swaps the skeletons for the real panels, drops the wall
and re-enables the controls. On `403` the wall simply stays. No client-side tier
check is load-bearing — the server decides, every time, and a hostile client can
only ever ask.

### Why `/premiumdata/`

Caddy's static boundary is default-deny (`@reg_asset`), so a new prefix needs
**no Caddyfile change**: it already flows through `/api/regwall/check` then
`/api/paywall/check`. What it does need is `premium.enforced_early` in
`config/site_access.yml`, which makes `app/paywall.py` require the `site_full`
entitlement on those paths *regardless of `PAYWALL_ENABLED`*. That is the whole
mechanism for shipping one paid surface ahead of the launch switch.

Deploy is automatic: `app/deploy/update.sh` (cron, every ~3 min) restarts
`macro-api` whenever `app/*.py` or `config/site_access.yml` changes on main.

## Applying it to a page — the checklist

1. **Extract the repeated markup into a partial** (`templates/_<page>_rows.html.j2`)
   that renders nothing but the `rows` it is handed, and carries no tier logic.
   One source, rendered twice — the preview slice and the paid remainder can then
   never drift apart.
2. **Builder**: read the switch from `config.yml` (`gated`, `preview_rows`), split
   the rows, render the shell with the preview slice + a `gate` dict
   (`{tier, payload, preview, locked}`), and write the payload with
   `schema: tier_payload.v1`.
   *Choose the preview newest-first, not best-first* — show the desk working
   without handing over the ranked board. Prefer rows that read as product (a
   real ticker, a summary) over the literal newest filing.
3. **Template**: `{% if gate %}` → skeleton panels in place of paid ones, an
   upgrade wall (plain words, honest counts, `plans.html` CTA, a sign-in line for
   the signed-out member), and the attempt-hydrate script.
4. **Policy**: add the page path to `free_registered.exact` (otherwise an armed
   paywall 403s the preview itself) and confirm the payload prefix is under
   `premium.enforced_early`.
5. **Plans page**: state the boundary in the same PR — a tier card line *and* a
   comparison-matrix row. Free's cell says what Free actually gets
   ("3 newest filings"), never "—".
6. **Render lane**: make sure the page's builder actually runs in `render.yml`
   (the desk PAGE, not its slow collector) so a template fix reaches the baked
   shell in minutes. Reuse the last real build's `built` stamp on a no-refresh
   rebake so an unchanged desk rebakes byte-identically and commits nothing.
7. **Tests**: prove the split hermetically (fake rows → the shell contains only
   the preview), and assert the shipped bytes carry no payload row. Assert on
   full class attributes, never a bare selector substring — the page's own CSS
   mentions every skeleton class, so `"setup-ghost" in html` is vacuously true.

### Controls (filters, search, sort)

Bake them **fully** and mark the container inert (`.gated` → `pointer-events:
none`, dimmed, and non-sticky on phones). Hydration removes the class and the
same controls start working on the full board. Do not omit them for Free — the
entitled viewer hydrates into the same DOM and would end up with no filters. Say
why they are inert with one plain line above the bar; dead buttons with no
explanation read as a bug.

### Session freshness (a trap worth remembering)

The shared session cookie carries a ~1h access token, so a long-idle member can
be signed in with a token the server will reject. Call
`MDXAuth.client().then(sb => sb.auth.getSession())` before the payload fetch to
refresh and rewrite the cookie — the same fix as the onboarding wall (PR #3454).
`theme.js` is deferred, so `MDXAuth` does not exist while an inline page script
runs: wait for its `mdx-auth` event with a timeout fallback.

## What Free actually sees today

| Surface | Free / anon | Insider · Pro |
|---|---|---|
| Special Situations | 3 newest filings, all totals, coverage note | whole board, top setups, search/filter/sort |
| Research Vault | newest report summary (Insider 3), no PDFs | every desk + PDFs, Top Picks |

Note both pages sit **behind the registration wall** — "Free" here means a signed-in
free account. Anonymous visitors are redirected to sign in by the regwall; the
public estate is the landing/plans funnel plus `/stocks/ /tools/ /learn/ /blog/`.

## Reference implementation

- `templates/special_situations.html.j2` — shell, wall, attempt-hydrate
- `templates/_special_situations_rows.html.j2`, `_special_situations_setups.html.j2`
- `scripts/build_special_situations.py` — `_gate_cfg`, `_write_premium_payload`
- `config/site_access.yml` — `premium.enforced_early`, `free_registered`
- `app/paywall.py` — `enforced_early()`
- `tests/test_special_situations_gate.py`, `tests/test_paywall.py`
- CI: the `tier-gate` job in `.github/workflows/ci.yml`
