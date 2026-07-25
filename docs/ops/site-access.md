# Main-site access boundary

## What is protected

The origin is default-deny for static content. Only the public funnel, the
reviewed free SEO estate (`stocks/`, `tools/`, `learn/`, `blog/`), and explicit
bootstrap assets in `config/site_access.yml` bypass authentication.
The existing Terminal ingest carve-outs (`factordata/tech_lab.json` and
`factordata/tech_events/`) also remain public until that separate session moves
them behind authenticated transport.
All other HTML, JSON, JavaScript data bundles, images, generated model outputs,
and unknown future extensions pass:

1. the registration wall (`/api/regwall/check`);
2. the paid feature wall (`/api/paywall/check`).

Protected responses are `private, no-store` and cannot be placed in the shared
CDN cache. Internal mockup/QA pages return 404 to every user.

### Keeping the two lists aligned

`config/site_access.yml` is the policy of record; `app/deploy/Caddyfile`'s
`PUBLIC-BOUNDARY` block is the enforcer. `tests/test_site_access_boundary.py`
fails on any drift between them and runs in CI's `tier-gate` job. Two standing
exceptions the policy file cannot express:

- **Proxied routes, not files.** `/api/*` and `/ws/tape` are excluded from the
  static matchers because they are reverse-proxied to `macro-api`, which
  enforces its own auth. The policy schema classifies file paths under `site/`,
  so these live in the test's `NON_POLICY_ROUTES` set instead. Never add a route
  to `public.exact` to silence the drift test — that would tell `app/paywall.py`
  the path is public content.
- **Runtime artifacts.** `site/live/` is gitignored: the systemd lanes publish
  by atomic rename into `/var/lib/macro-live/public`, so a fresh checkout may
  not contain `/live/quotes.json` or `/live/breadth.json`. The
  policy-targets-exist check exempts that prefix; the Caddy-alignment check
  still covers those entries, so a typo'd `/live/*` path is caught.

The paid stage is deliberately independent and defaults off:

```text
REGWALL_ENABLED=1
PAYWALL_ENABLED=0
```

This immediately closes anonymous direct-file bypasses without launching the
paid product before its operational prerequisites are complete.

### Paths already gated ahead of that switch

`premium.enforced_early` in `config/site_access.yml` lists paths that require the
`site_full` entitlement **whatever `PAYWALL_ENABLED` says**, so one paid surface
can ship before the site-wide launch. Currently:

| Prefix | Surface | Free account sees |
|---|---|---|
| `/premiumdata/` | tier-preview payloads (Special Situations desk) | the page's free preview shell + an upgrade wall |

Anything added there must keep a free-visible preview at its page URL rather than
a bare wall — see `docs/TIER_PREVIEW_PATTERN.md`. Probe it exactly like the paid
switch (a signed-in free account gets 403 lock JSON; an active/trialing
`site_full` account gets 200):

```sh
curl -i 'https://www.mastermind-x.com/premiumdata/special_situations.json?probe=UNIQUE'
```

## Paid launch checklist

Do not set `PAYWALL_ENABLED=1` until all of these are true:

- Supabase email verification, custom SMTP, and CAPTCHA/rate protection are live.
- Stripe test checkout, webhook, cancellation, chargeback, and reconciler drills
  have produced the expected `user_entitlements` rows.
- An operator comp account and a real trial account both carry active/trialing
  `site_full`; a free and a `past_due` account do not.
- EdgeOne has an explicit cache-bypass rule for protected paths on both HTTP and
  HTTPS, and cold-cache probes confirm protected responses are never cached.
- The public/free/premium path split in `config/site_access.yml` has product signoff.
- The GitHub Pages mirror has been made private or removed. Until then it remains
  a complete bypass of the main-domain wall.

Then arm the wall without a code deploy:

```sh
printf '\nPAYWALL_ENABLED=1\n' >> /etc/macro-api.env
systemctl restart macro-api
```

Use an idempotent env editor in production rather than appending a duplicate
key. Roll back immediately with `PAYWALL_ENABLED=0` plus a service restart.

## Acceptance probes

Use cache-busting query strings and test both schemes through the edge:

```sh
curl -i 'https://www.mastermind-x.com/neuralwebdata/ruling_graph.json?probe=UNIQUE'
curl -i 'https://www.mastermind-x.com/oracledata/tm_episodes.json?probe=UNIQUE'
curl -i 'https://www.mastermind-x.com/committee.html?probe=UNIQUE'
curl -i 'http://www.mastermind-x.com/neuralwebdata/ruling_graph.json?probe=UNIQUE'
```

Anonymous assets must return 401 JSON from the registration wall; anonymous
documents redirect to sign-in. With the paid switch armed, a signed-in free user
gets 403 lock JSON/HTML, while an active/trialing `site_full` user gets 200.
Every protected response must contain `Cache-Control: private, no-store`.

Stop `macro-api` briefly and repeat the probes. Protected assets must return the
non-cacheable 503 JSON and protected documents must redirect; no requested file
may be served. Restart the service immediately after the drill.

## Important residual boundaries

- Any HTML/JavaScript/data the browser is authorized to receive can still be
  saved and inspected. The wall prevents anonymous access and enforces account
  entitlements; it cannot make delivered client code secret.
- `templates/data_base.js` currently points at a public R2 hostname for heavy
  OHLC/search stores. That bucket is a separate direct-origin bypass. Privatizing
  it requires a signed/authenticated data gateway and a coordinated frontend
  migration; disabling it first would break stock pages because those heavy
  trees are intentionally absent from `site/`.
- The Terminal live-flow surface has its own serving boundary and is not changed
  by this main-site control. Its two current factordata ingest carve-outs are
  explicit in the policy and remain a temporary public residual.
- Secrets remain server-side. The public Supabase publishable/anon key is
  intentionally public; service-role, Stripe secret, R2 secret, and model tokens
  must never enter `site/`.
