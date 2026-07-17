# Site Access Gate — operator guide

The site-access gate lets the operator block specific IPs, IP ranges (CIDRs), or
whole countries from reaching the HTML pages of mastermind-x.com.  Blocked visitors
see a bilingual coming-soon page (site/coming-soon.html).

## What it does

The gate is enforced at the origin (macro-api) and consulted by Caddy for every
HTML navigation (paths `/` and `*.html`).  Assets (JS, CSS, images, JSON, fonts)
are NOT gated — the coming-soon page is fully self-contained and needs no assets.

Components:

| File | Role |
|---|---|
| `app/gate.py` | Gate decision engine: loads rules, checks IP/country, returns allow/block |
| `admin/site_gate.py` | Admin backend: validates and persists rule changes |
| `app/deploy/Caddyfile` | Consults the gate for HTML requests; fail-open on upstream error |
| `site/coming-soon.html` | Fully self-contained 403 page (no external deps) |
| `app/deploy/geoip-setup.sh` | Downloads the MaxMind GeoLite2-Country db (optional) |

## Default state: SAFE (disabled)

The gate ships disabled (`enabled: false`).  When disabled, **every visitor is
allowed** regardless of any lists.  A missing, unreadable, or corrupt store file
is also treated as disabled (fail-open).

The admin panel's master switch defaults to OFF; the operator must explicitly enable
the gate before any blocking takes effect.

## Store file

The runtime blocklist is stored at `SITE_GATE_STATE` (default
`/var/lib/macro-api/site_gate.json`).  This file:

* Is NOT in git — it is ephemeral operational state (survives `git reset --hard`).
* Is written atomically (tempfile + os.replace) by the admin server.
* Is read by macro-api on every check, cached by mtime so changes take effect
  immediately without a restart.

Schema:

```json
{
  "version": 1,
  "enabled": false,
  "blocked_ips": ["203.0.113.4", "198.51.100.0/24"],
  "blocked_countries": ["RU", "KP"],
  "allow_ips": ["203.0.113.9"],
  "updated_at": "2026-01-01T00:00:00Z",
  "updated_by": "admin"
}
```

## Fail-open: the gate can NEVER break the site

The gate is designed so that failures make it MORE permissive, not less:

1. **Missing/corrupt store** → treated as `{enabled:false}` → allow everyone.
2. **gate module unavailable** → main.py falls back to allow (204) with no gate check.
3. **Caddy: gate upstream down** → the gate `reverse_proxy` inside the
   `handle @gate_html { route { … } }` block errors; Caddy's `handle_errors`
   block serves the requested static HTML with a forced `200` → the page is served
   normally, never a `502` white-page (which EdgeOne could surface as its own error
   page). Verified with a local Caddy + stub-gate test across all cases: allow →
   200 page (`max-age=60`); block → 403 coming-soon (`no-store`); genuine 404 → 404;
   gate down → 200 page. **If you change the Caddyfile gate/route/handle_errors
   shape, re-run that test** — an earlier `handle` + `handle_response @blocked`
   shape shipped INERT (the gate was never consulted; blocklist did nothing).
4. **country = None** (header absent, no GeoIP) → ALLOW even if country blocklist
   is non-empty.  You cannot accidentally block all traffic by enabling a country
   list without a working detection source (the admin panel's country-detection
   badge shows `unavailable` until a real request resolves a country).

## Self-lockout guard

`allow_ips` is a whitelist that takes precedence over every block rule.  The admin
server always auto-inserts the operator's current IP into `allow_ips` on every
save, and warns (but still saves) if that IP is also in `blocked_ips`.  It is
**impossible** to lock yourself out via the admin panel.

## Country detection: CDN header (primary)

The CDN must emit a country header.  The gate reads, in order:

1. `SITE_GATE_COUNTRY_HEADER` env (default `EO-Client-IPCountry` for EdgeOne)
2. `EO-Client-Country`
3. `CF-IPCountry` (Cloudflare fallback)

### EdgeOne console setup

To enable country detection with EdgeOne:

1. Open the EdgeOne console → your domain → **Edge Functions** (or **Rules**).
2. Add a rule that forwards the visitor's country to the origin as
   `EO-Client-IPCountry`.  EdgeOne's "Client Country/Region" variable (e.g.
   `${geo_country}` in a rule action) can be mapped to a custom request header.
3. Verify that the header reaches the origin: check `/api/gate/status` and
   confirm `last_seen_country` is populated after a real visitor request.

The exact header name varies by EdgeOne product version.  Use `/api/gate/status`
→ `country_detection.source` to confirm which source the gate is actually reading.
If `source` is `"unavailable"`, the CDN is not forwarding a country header and
GeoIP is absent.

## Country detection: GeoIP (fallback)

If no CDN country header is present, the gate can optionally look up the country
from the visitor's IP using a MaxMind GeoLite2-Country database.  This is entirely
optional — the gate works without it.

Setup:

```bash
# 1. Get a free MaxMind account and licence key at:
#    https://www.maxmind.com/en/geolite2/signup
# 2. Run geoip-setup.sh with the key:
MAXMIND_LICENSE_KEY=your_key bash /opt/macro/app/deploy/geoip-setup.sh
```

The db is written to `GEOIP_DB` (default `/var/lib/macro-api/GeoLite2-Country.mmdb`).
The gate re-opens it lazily on the next request — no restart needed.

Add a weekly cron to keep it current (MaxMind updates GeoLite2 twice a week):

```cron
0 4 * * 0  MAXMIND_LICENSE_KEY=<key> bash /opt/macro/app/deploy/geoip-setup.sh >> /var/log/geoip-setup.log 2>&1
```

## Security note: soft gate (header spoofing)

IP and country blocking via CDN headers is a **soft gate**.  A determined actor
hitting the origin server directly (bypassing the CDN) can spoof any header.  This
is consistent with the existing `noindex` + Supabase auth posture — the gate is
intended to deter casual access from certain regions, not to provide cryptographic
security.  For hard enforcement, use a CDN-level WAF rule or firewall to block
direct origin access (the existing `firewall-cloudflare.sh` locks the origin to
CDN IPs only, which makes header spoofing impossible from public internet).

## Admin API

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/site_gate` | admin session | Returns current rules + your IP + gate_status |
| `POST /api/site_gate/save` | admin session + CSRF | Validate and persist new rules |
| `GET /api/gate/check` | none | Gate decision (called by Caddy) |
| `GET /api/gate/status` | none | Gate status + country detection health |

## Environment variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `SITE_GATE_STATE` | macro-api, admin | `/var/lib/macro-api/site_gate.json` | Store file path |
| `SITE_GATE_COUNTRY_HEADER` | macro-api | `EO-Client-IPCountry` | CDN country header name |
| `GEOIP_DB` | macro-api | `/var/lib/macro-api/GeoLite2-Country.mmdb` | MaxMind db (optional) |
| `SITE_GATE_PAGE` | macro-api | `site/coming-soon.html` | Coming-soon page path |
