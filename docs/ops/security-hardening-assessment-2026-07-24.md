# Paid-beta security assessment — 2026-07-24

## Executive finding

The engine source is not embedded in the production HTML, but the previous
serving boundary was not protective enough: Caddy authenticated non-public
`.html` only. Thousands of generated JSON artifacts and data-bearing JavaScript
files were anonymously downloadable and shared-cacheable by direct URL.

Browser developer tools cannot be disabled in a meaningful security sense.
Anything an authorized browser receives can be saved. The durable boundary is:

- algorithms, prompts, credentials, and private corpora stay server-side;
- every customer-specific or paid read is authorized server-side;
- static generated outputs are treated as protected data, not harmless assets;
- shared caches never store protected responses;
- public samples are an explicit, reviewed allowlist.

## Observed production posture

| Area | Finding | Risk / disposition |
|---|---|---|
| Main HTML | Registration wall worked for non-public `.html` | Good base control |
| Main JSON/JS/data | Direct URLs bypassed the HTML wall | High; closed by this build |
| CDN cache | Ungated JSON had public 300s cache headers | High; protected paths now `private, no-store` |
| Paid entitlement | Billing and `site_full` existed, but no static-site consumer | High for launch; staged fail-closed consumer added |
| Premium APIs | Legacy `/api/ask*` required login but not `site_full` | Closed when paid switch is armed |
| Browser headers | No main-site CSP, anti-frame header, or Permissions Policy | Added conservative enforced headers |
| Client secret scan | No private keys, service-role keys, Stripe secrets, or source maps found under `site/` | Green; regression test added |
| Public R2 | Heavy OHLC/search data uses a public `r2.dev` origin | High residual; coordinated private gateway required |
| GitHub/Pages | Public repository/mirror remains a complete alternate read path | Temporarily accepted by operator; privatize on runner migration |
| Terminal live flow | Separate public serving boundary; two factordata ingest paths remain public | Explicitly preserved and deferred to the other active session |
| VPS network | App APIs bind localhost; UFW exposes SSH/HTTP(S) only | Good |
| VPS SSH | Password and keyboard auth disabled; root key login allowed | Moderate; key-only, but dedicated deploy user is preferred |
| API process | Runs as root and holds several high-value model/billing credentials | High blast radius; systemd sandbox strengthened now, dedicated user/secrets split next |
| Host patching | `unattended-upgrades` enabled and active | Good |

## Build delivered in this wave

1. Default-deny Caddy static routing with a small reviewed public allowlist.
2. Registration checks for non-public HTML, JSON, JS, images, and unknown paths.
3. A distinct paid feature gate using active/trialing `site_full`, with:
   - fresh auth verification bounded to 60 seconds;
   - short entitlement caching and webhook invalidation;
   - fail-closed config/auth/store behavior;
   - positive-only store-outage grace capped at 24 hours;
   - bilingual HTML locks and structured JSON locks.
4. The same paid dependency on `/api/ask` and `/api/ask/stream`.
5. Non-cacheable protected responses, crawler exclusion, clickjacking/object/base
   protection, and restrictive device permissions.
6. Internal mockup/QA pages changed to unconditional 404.
7. Systemd hardening (`PrivateTmp`, `PrivateDevices`, `ProtectHome`, kernel and
   control-group protections, `RestrictSUIDSGID`, `LockPersonality`, `UMask=0077`).
8. Deployment updater fixed so any changed `app/*.py`, site policy, or service
   sandbox actually restarts/reloads the running service.
9. Tests that reject public-boundary drift, fail-open regressions, secret/source
   artifacts under `site/`, invalid entitlement states, and cacheable lock responses.
10. Local backup environment/key patterns added to `.gitignore`.

The paid switch remains off. Registration protection can ship immediately:

```text
REGWALL_ENABLED=1
PAYWALL_ENABLED=0
```

## Remaining work in priority order

### P0 — before paid launch

1. Complete the prerequisites and acceptance probes in `docs/ops/site-access.md`.
2. Privatize the repository and stop/privatize the Pages mirror when the
   self-hosted runner migration is ready.
3. Replace the public heavy-data R2 origin with one of:
   - a private bucket behind a server-side authenticated streaming gateway; or
   - short-lived signed object URLs minted only after entitlement checks.
   The migration must preserve range requests, content types, bounded object
   keys, rate limits, and revocation behavior. Do not make the current bucket
   private first: those heavy objects are intentionally absent from `site/`, so
   stock pages would break immediately.
4. Finish and verify the Terminal live-options entitlement lane in its owning session.
   Then remove the temporary `/factordata/tech_lab.json` and
   `/factordata/tech_events/*` public carve-outs from the main-site policy.
5. Verify Supabase custom SMTP, email confirmation, CAPTCHA/rate limits, and
   recovery/redirect allowlists.
6. Exercise Stripe test clocks for trial, payment failure, cancellation,
   chargeback, webhook replay, and reconciler recovery.

### P1 — reduce breach blast radius

1. Run `macro-api` as a dedicated unprivileged user with explicit
   `ReadOnlyPaths=/opt/macro` and `ReadWritePaths=/var/lib/macro-api`.
2. Split model OAuth tokens away from the public request-serving process. The
   API should receive only the credentials required by its enabled routes.
3. Replace root SSH operations with a dedicated deploy account and tightly
   scoped sudo commands; keep password authentication disabled.
4. Add per-route rate limits for auth checks, expensive model calls, downloads,
   and large data objects, plus anomaly alerts for scraping patterns.
5. Add a first-party CSP report collector, then migrate inline scripts/styles to
   nonces or hashes before enforcing a strict `script-src`/`style-src`.

## Acceptance standard

Security is considered materially improved when an anonymous request, a
registered free request, an entitled request, a lapsed request, an origin-down
request, and a scheme-crossed CDN request all produce the expected distinct
result—and no protected bytes can be obtained through an alternate origin.
