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

The paid stage is deliberately independent and defaults off:

```text
REGWALL_ENABLED=1
PAYWALL_ENABLED=0
```

This immediately closes anonymous direct-file bypasses without launching the
paid product before its operational prerequisites are complete.

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
