# Accounts — setup & operations

User accounts for the dashboard: a frosted-glass sign-in / sign-up modal (matching
`site/index.html`'s `.glass` look), reachable from the **⚙ Settings → Account**
section on every page. Sign-in methods:

- **Google** — `signInWithOAuth`
- **Email + password** — no email verification (instant sign-in)
- **WeChat** — shown as *coming soon* (no native Supabase provider yet; see below)

The session is kept in **permanent cookies** (~390-day, `Path=/`, `SameSite=Lax`,
`Secure` on https) so a user stays signed in across visits and across every page.

## How it's wired (code)

| Piece | Where |
|------|-------|
| Account module (cookie storage, shared Supabase client, glass modal, `window.MDXAuth`) | `templates/theme.js` → copied to `site/theme.js` |
| Watchlist cloud-sync (rides the shared session) | `templates/auth.js` → `site/auth.js` |
| Self-hosted SDK (CDN is blocked in mainland China) | `templates/supabase.js` → `site/supabase.js` |
| Config (public URL + publishable key) | `config.yml` → `watchlist.supabase` |
| Build-time bake | `scripts/build_site.py` replaces the `/*__SUPABASE_CFG__*/null` token in `theme.js` with the config, so **every** page gets `window.SUPABASE_CFG` |
| Per-user data isolation (RLS) | `templates/watchlist_supabase.sql` |

The Supabase **publishable (anon) key is PUBLIC by design** — it ships in the client.
Per-user isolation is enforced entirely by Row-Level-Security against the caller's
JWT. The `service_role` key must **never** be put in the site or this repo.

Anonymous visitors fetch **zero** third-party bytes: the SDK loads lazily only when
the modal opens or a prior cookie session must be restored.

## One-time Supabase dashboard setup (REQUIRED)

Project: `https://fsldfzlxyavsuwqbceod.supabase.co` (dashboard → that project).

1. **Disable email confirmation** (so sign-up logs the user straight in):
   - Authentication → **Sign In / Providers → Email** → turn **Confirm email OFF** → Save.
   - (Without this, sign-up returns no session and the modal will say "check your inbox".)

2. **Enable Google**:
   - Google Cloud Console → create an **OAuth 2.0 Client ID** (type: Web application).
     - Authorized redirect URI: `https://fsldfzlxyavsuwqbceod.supabase.co/auth/v1/callback`
   - Supabase → Authentication → Sign In / Providers → **Google** → paste the Client ID +
     Client Secret → enable → Save.

3. **Allow the site's origins** (Authentication → **URL Configuration**):
   - **Site URL:** `https://mastermind-x.com` — the apex, **not** `www.`
     (www has broken TLS at the Tencent EdgeOne edge as of 2026-07-05; a www
     Site URL would strand every fallback redirect on a host that can't
     complete a handshake).
   - **Redirect URLs (add each):**
     - `https://mastermind-x.com/**`
     - `https://app.mastermind-x.com/**` (Terminal — shared SSO session)
     - `https://chriswong6031-creator.github.io/macro/**` (Pages mirror)
     - any other subdomain where sign-in is *initiated*
     - for local testing: `http://localhost:*/**`
   - OAuth + the implicit flow return to the page the user started on, so the page's
     exact origin must be allow-listed here.

4. **Run the SQL** once (SQL Editor) if not already done:
   `templates/watchlist_supabase.sql` — creates the `watchlists` table + RLS policies
   used by the watchlist cloud-sync.

5. **Turn on Attack Protection** (recommended — the anon key is public, so the auth
   endpoints are reachable by anyone): Authentication → **Attack Protection** →
   enable **rate limiting** and a **CAPTCHA** (hCaptcha / Cloudflare Turnstile).
   This is the real defence against bot sign-up/sign-in abuse and against email
   *enumeration* — with confirmation OFF, "this email already exists" is inherently
   detectable at the API regardless of UI wording, so rate-limit/CAPTCHA is what
   actually blunts automated probing. (If you add a CAPTCHA, also set its site key
   on the client — see Supabase's captcha docs.)

After this, email/password and Google sign-in work end-to-end on the live site.

## Security model (what's deliberate)

- **PKCE flow**, not implicit: the OAuth return carries a one-time `?code=` (not
  tokens). It's useless without the `code_verifier` stored locally before redirect,
  so tokens never land in the URL/history and a pasted `#access_token=` link can't
  seed a session (no login-CSRF / fixation).
- **Cookie session is JS-readable** (no `HttpOnly` is possible for a client SDK).
  That's standard for Supabase on a static site; isolation is via RLS. Keep strict
  `textContent`/no-`innerHTML`-of-user-data discipline so any future XSS can't lift
  the token — the account UI only ever sets user text via `textContent`.

## WeChat (future)

Supabase has **no native WeChat provider**. Wiring it up needs, in order:

1. A **微信开放平台 (WeChat Open Platform)** account — verified business, paid
   registration (~¥300/yr) — and an approved **网站应用 (website app)** to get an
   `AppID` + `AppSecret`.
2. A small backend bridge (e.g. a **Supabase Edge Function**) that handles WeChat's
   OAuth2 callback (`code` → `openid`/`access_token`) and mints a Supabase session
   for that identity (via the Admin API / a custom JWT). WeChat does not issue an
   OIDC `id_token` that `signInWithIdToken` accepts directly, hence the bridge.
3. Point the modal's WeChat button at that flow (replace the "coming soon" handler
   in `templates/theme.js`, `_wireAuthModal` → `auth-wechat`).

Until then the button renders but shows a polite "coming soon" notice.

## Notes

- **Cookie size:** a Supabase session JSON can exceed the ~4 KB single-cookie limit,
  so `COOKIE_STORAGE` in `theme.js` chunks it (`<key>` = count, `<key>.0..n`).
- **Free-tier pause:** free projects sleep after ~7 days idle. A nightly keep-alive
  curl is documented at the bottom of `templates/watchlist_supabase.sql`.
- **Changing project/keys:** edit `config.yml → watchlist.supabase`; the next render
  bakes the new values into `theme.js` and `watchlist.html`.
