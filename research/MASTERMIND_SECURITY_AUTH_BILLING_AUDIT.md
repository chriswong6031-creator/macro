# Mastermind-X — Security, Auth, Entitlement & Billing Audit

**Audit date:** 2026-08-12
**Covers:** Parts III (auth), IV (authorization/isolation), V (entitlement), VI (billing),
XVI (secrets), XVII (input security), XVIII (admin).

**Headline:** I probed this spine for the standard catastrophic failures — auth bypass, IDOR,
cross-tenant leakage, webhook forgery, exposed secrets, admin exposure — and **found none**.
The findings below are real but are cost, availability, and policy issues, not breaches.

---

## 1. Authentication

### 1.1 How identity is actually established

There is **no local JWT verification anywhere in this product.** A search for every
`jwt.`, `HS256`, `verify_signature`, `jwks`, and `SUPABASE_JWT_SECRET` site returns only a
docstring reference in `app/main.py` and an unrelated Cloudflare credential minter in
`engine/fundamental_forensics/`.

Instead, `require_user` (`app/main.py:735`) does a **secretless network verification**:

```python
req = urllib.request.Request(
    f"{SUPABASE_URL}/auth/v1/user",
    headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY})
```

**This is a genuinely strong choice.** It eliminates the entire class of JWT vulnerabilities:
no `alg: none`, no HS256/RS256 confusion, no `verify=False`, no signing secret to leak or
rotate. Expiry and revocation are enforced by Supabase, not by local clock arithmetic.

The trade-off is availability and latency — see MMX-004, the single most important finding
in this document.

### 1.2 Endpoint → identity → enforcement inventory

Extracted mechanically via AST over `app/` and `admin/` (109 route registrations). The
instrument was positive-controlled: it correctly identifies known-authenticated routes.

**Only four authentication dependencies exist in the entire API:**

| Dependency | Routes | Meaning |
|---|---|---|
| `require_site_full_user` | 29 | Registered **and** entitled (paid gate) |
| `require_user` | 11 | Registered user, any tier |
| `_brain_user_or_guest` | 7 | Verified user, or synthetic guest when guest access is on |
| `_current_user` | 6 | Billing/prefs identity |

That concentration is a strength: there is one way in, not a patchwork per feature.

**53 routes carry no dependency.** Classified by intent:

| Class | Count | Assessment |
|---|---|---|
| Correctly public infrastructure (`/api/health`, `/api/status`, `/api/gate/*`) | 4 | Correct. `/api/status` deliberately coarsens error strings to avoid leaking absolute paths (CWE-209). |
| The paywall mechanism itself (`/api/paywall/check`, `check_pro`, `/api/regwall/check`) | 3 | Correct — these *are* the auth check, invoked by Caddy. |
| Public market surfaces (`/api/flow/*`, `/api/overlay`) | 7 | Deliberate product decision. |
| Stripe webhook | 1 | Correct — authenticated by signature, not session. |
| Analytics beacon (`/api/collect`) | 1 | Defended: 16KB body cap, per-IP throttle, event-type allow-list. |
| Support/unsubscribe/reviews | 4 | Body caps in Caddy for support; token-based unsubscribe. |
| **Proprietary intelligence, no auth *and* no rate limit** | **31** | **MMX-008** — see §5. |

### 1.3 Auth failure modes checked

| Attack | Result |
|---|---|
| Forged/unsigned JWT | **Not possible** — no local verification to defeat. |
| Expired token replay | Rejected by Supabase; local cache TTL is capped at 60s (`_seconds(..., 45.0, 1.0, 60.0)`). |
| Auth-vs-authz confusion | Separated: `require_user` (authn) and `enforce_site_full` (authz) are distinct. |
| Client-side-only gating | No. `enforce_site_full` runs server-side and its docstring explicitly notes Caddy cannot cover `/api/*`, so premium APIs call the authority directly. |
| Guest privilege escalation | Blocked. `_brain_user_or_guest` degrades to guest **only** on a 401 — a 502 (Supabase down) propagates unchanged, so an outage cannot silently downgrade a paid user into the guest lane. A guest's email is forced to `''` so operator/unlimited allow-lists can never match. |
| Inconsistent middleware | The only global middleware is `_NoStoreAPI` (cache headers). Auth is per-route dependency, uniformly applied. |

---

## 2. Authorization and user isolation

**This was the highest-priority area per the brief, and it holds.**

### 2.1 No client-supplied identity

Every `user_id` in the API derives from the Supabase-verified record
(`user.get("id")`), never from a request body, query parameter, or path segment. I grepped
every `user_id` assignment in `app/` to confirm this; there are no exceptions.

This matters because `_pg()` authenticates to PostgREST with
`SUPABASE_SERVICE_ROLE_KEY`, which **bypasses RLS entirely**. The service-role key is safe
here only because identity is never attacker-controlled — a single endpoint accepting
`user_id` from the client would become a full cross-tenant read/write. **This is the most
important invariant in the codebase and should be protected by a test.**

### 2.2 Row-level security (charting-app)

`charting-app/supabase/migrations/0001_init.sql` enables RLS on **all seven** user tables
(`profiles`, `watchlists`, `watchlist_symbols`, `chart_layouts`, `saved_scripts`, `alerts`,
`favorites`) with owner policies:

```sql
create policy %1$s_owner on public.%1$s
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
```

`watchlist_symbols` has no `user_id` of its own and is correctly gated through its parent:

```sql
for all using (exists (select 1 from public.watchlists w
                       where w.id = watchlist_id and w.user_id = auth.uid()))
```

`saved_scripts` additionally allows `select using (is_public = true)` — an intentional
public-script feature, correctly scoped to SELECT only.

### 2.3 AI conversation isolation (the newest, most "vibe-coded" surface)

The brain run endpoints take a `{run_id}` path parameter — a textbook IDOR shape. Ownership
is enforced **in the artifact**, not merely asserted in a docstring:

```python
# app/brain_runs.py
return run if run.user_id == user_id else None
```

And enumeration is structurally refused for guests: `brain_runs_active` returns `{"runs": []}`
for any guest principal. The reasoning is written out in the handler and is correct — the guest
principal is partly a client-settable cookie, so listing run ids to it would hand one anonymous
visitor another's conversation. The 128-bit run id is treated as the guest's capability.

**Residual:** the `"unknown"` identity sentinel (MMX-011) is the one way two distinct
principals could compare equal here. Low likelihood, high impact — worth closing.

---

## 3. Entitlement matrix

Reconstructed from `app/paywall.py`, `config/plans.yml`, and `config/site_access.yml`.

| Principal | Determined by | Site pages | Premium `/api/*` | Brain fast lane | Brain pro lane |
|---|---|---|---|---|---|
| Anonymous | no token | public paths only | denied | guest daily cap **if** guest access enabled | denied |
| Registered (free) | valid token, `tier=free` | free paths | denied (403 `locked`) | per-user cap | denied |
| Essential | `tier` + `status ∈ {active,trialing}` + feature | gated paths open | allowed | per-tier cap | denied |
| Pro | as above, `_ranks_at_least(tier,"pro")` | all | allowed | per-tier cap | allowed |
| Operator/unlimited | `_operator_unlimited(email)`, email from **verified session only** | all | allowed | uncapped | uncapped |

**The canonical source of truth is `user_entitlements` in Supabase**, written only by the
Stripe webhook and the nightly reconciler, read by `paywall._entitled`. There is exactly one
writer path and one reader path. **Recommendation: keep it that way** — this is already the
"ONE canonical source" the brief asks for, and it does not need re-architecting.

### 3.1 Entitlement fail-open / fail-closed behavior

| Condition | Behavior | Assessment |
|---|---|---|
| Token invalid/expired | Deny | Correct |
| Entitlement store reachable, no row | Deny (`tier=free`) | Correct |
| Entitlement store **unreachable**, no prior positive | Deny | Correct — fails closed |
| Entitlement store unreachable, prior **positive** within 24h | **Allow** | Deliberate (MMX-009). Positive-only grace; negatives never get grace. |
| API-surface check raises | `allowed = False` | Correct — `enforce_site_full` fails closed in every environment |
| `PAYWALL_ENABLED=0` (staging) | Registered-user behavior | Premium routes using `always=True` still fail closed |

The asymmetry — grace for positives only, invalidation on every mutation — is well designed
and I would not change it.

---

## 4. Billing

### 4.1 Webhook integrity

`app/billing.py:webhook` does four things right:

1. **Real signature verification** — `stripe.Webhook.construct_event(payload, sig, secret)`.
   Forged payloads are rejected 400.
2. **Fails closed when unconfigured** — missing `STRIPE_WEBHOOK_SECRET` ⇒ 503, never
   "process anyway".
3. **Idempotency table** — `stripe_events` with `on_conflict=id`.
4. **Threadpool hop** — `run_in_threadpool(_handle_event, event)`, because the handler makes
   blocking Supabase + Stripe + SMTP calls that would otherwise stall the single-process
   event loop for every other user.

### 4.2 The design decision that makes billing robust

`_handle_event` does **not** apply the event as a delta. It calls `_compute_entitlement`,
which re-reads the customer's **live Stripe state** and reduces it through a pure function
`_entitlement_from_state(subs, entitlement_keys)`.

This single choice neutralizes most of the classic billing failure modes below. It is the
strongest architectural decision in the billing subsystem.

### 4.3 The brief's eight cases, answered from the code

| Case | Outcome | Basis |
|---|---|---|
| **A — same webhook ×5** | **DB state correct.** Sequential retries short-circuit on `_event_seen`. *Concurrent* duplicates both pass the check (MMX-007) → duplicate **emails**, not duplicate entitlement. | `_event_seen` → slow `_handle_event` → `_record_event` |
| **B — events out of order** | **Correct.** State is recomputed from live Stripe, so arrival order is irrelevant. | `_compute_entitlement` |
| **C — checkout opened twice** | **Defended.** `_has_live_subscription` is an explicit no-double-subscribe 409 guard, checked at **both** `/subscribe/init` and `/subscribe/complete` to close the two-tab window. | `_has_live_subscription` docstring + call sites |
| **D — payment succeeds, server crashes** | **Self-heals.** No record written ⇒ Stripe retries ⇒ idempotent recompute. Explicitly reasoned in the handler comment. | `webhook` |
| **E — webhook down 6 hours** | **Self-heals.** `reconcile_entitlements()` re-syncs every known customer from live Stripe nightly. A genuine backstop, not aspiration. | `reconcile_entitlements` |
| **F — renewal payment fails** | **User loses access immediately** — see MMX-014. Deliberate, documented, and a business risk. | `_entitlement_from_state` |
| **G — cancel then resubscribe** | **Correct.** Recompute sees the new live sub. | `_entitlement_from_state` |
| **H — tier changed twice rapidly** | **Converges.** Each event recomputes from live state; the reconciler is the tiebreak. `max(entitled, key=rank)` picks the highest tier if two subs briefly coexist. | `_entitlement_from_state` |

**Duplicate charges:** not a risk from this code path. The webhook never creates charges;
Stripe owns charging, and the app only reads state.

### 4.4 Chargeback handling (a nice catch by the original authors)

`charge.dispute.created` is in `_REVOKING` and triggers `_cancel_subscriptions` **before**
the recompute — because a disputed subscription stays `active` in Stripe, so a plain
recompute would keep granting premium. Refunds are deliberately *not* auto-revoking
(often partial/goodwill). This is correct and unusually thoughtful.

### 4.5 Comp-grant preservation

`reconcile_entitlements` contains a specific guard so the nightly cron cannot silently delete
operator comp grants: Stripe overrides a comp only when it actually has an entitling
subscription to override it with. The failure it prevents (switching `STRIPE_SECRET_KEY`
from test to live turning every `cus_…` into `resource_missing` and wiping lifetime comps)
is real and was clearly learned the hard way.

---

## 5. Rate limiting and abuse (Parts XVII, XXVI)

Rate limiting is **inconsistent and per-module**, which is the finding:

```
government_revenue.py : 0 rate-limit tokens   (24 unauthenticated routes)
hub.py                : 0 rate-limit tokens   ( 7 unauthenticated routes)
research.py           : 4
company_intelligence.py: 26                   (correctly protected)
```

Caddy adds **no** rate limiting — only `request_body max_size` on `/api/support/*` (64KB) and
one biocatalyst path (16KB). Any further protection would come from the EdgeOne edge, which
**I could not verify from the repository** — this is an operator question, not a code fact.

**Input security checks (Part XVII):**

| Vector | Result |
|---|---|
| SQL injection | Not applicable at the app layer — all DB access goes through PostgREST with parameterized filters and `urllib.parse.quote` on identifiers. |
| Path traversal | **Checked and clean.** The gov-revenue artifact path comes from `_artifact_path()`, a fixed location — not from the `{ticker}`/`{award_key}` parameters. |
| Parameter injection | Cursors validated `re.fullmatch(r"[A-Za-z0-9_-]+")` with length caps; tickers normalized-or-422; flow roots sanitized to `[A-Z.]{1,8}`. |
| Oversized requests | 16KB cap on `/api/collect`, Caddy caps on support paths. Not universal. |
| Error-message leakage | Actively defended — `/api/status` coarsens artifact errors specifically to avoid echoing absolute paths to anonymous callers (CWE-209). |

---

## 6. Secrets (Part XVI)

**No secrets reach the browser.** Verified:

- `grep -rln "SERVICE_ROLE" templates/ site/` → **nothing**. The service-role key is
  server-side only.
- No JWT-shaped literals in shipped templates (the one `eyJ` hit is a Plotly bundle
  false positive).
- All secrets are sourced from root-only systemd `EnvironmentFile`s
  (`/etc/macro-api.env`, `/etc/macro-admin.env`, `0600`), documented as **never in git**.
- Both units use `EnvironmentFile=-` (optional). For `macro-api` this is safe by design —
  routes return 503 when their key is unset rather than running unprotected. For `admin` the
  optional file is safe because `--deployed` is hardcoded in `ExecStart`, so `startup_check()`
  fires regardless (see §7).

**I did not scan git history for previously-committed secrets.** That is a recommended
pre-launch step (`gitleaks detect --log-opts="--all"`), listed in the launch gates.

---

## 7. Admin console (Part XVIII)

**I formed a P0 here and then retracted it.** The retraction is worth recording, because the
first two layers of evidence pointed the wrong way.

`auth_enabled()` is simply `bool(admin_password())`. Read alone, that means: no
`ADMIN_PASSWORD` ⇒ auth disabled ⇒ every admin API open. And the console is genuinely
internet-reachable (Caddy proxies `admin.mastermind-x.com` → `127.0.0.1:8787`), so the
loopback bind is not a mitigation.

What closes it:

1. `settings.startup_check()` raises `SystemExit` when `ADMIN_DEPLOYED=1` and no password is
   set, and `serve()` calls it before binding.
2. `admin.service` hardcodes `--deployed` in `ExecStart`, which sets `ADMIN_DEPLOYED=1` in
   `__main__.py` — so the guard fires **even if `/etc/macro-admin.env` is missing entirely**.

The unit file's own comment states this reasoning explicitly. **Verdict: fail-closed.**

Other admin controls, all present and correct:

- Global gate **before** path dispatch: `if settings.auth_enabled() and not self._authed(): 401`
- HMAC-signed stateless session cookie, `hmac.compare_digest` before trusting payload bytes
- Double-submit CSRF token required on writes
- Host allow-list (DNS-rebinding defense)
- `Content-Type: application/json` pinning on writes
- Origin check on writes
- Login throttle
- systemd hardening: `NoNewPrivileges`, `ProtectSystem=full`, `ProtectHome`, `PrivateTmp`
- Console writes nothing to disk — config edits go out via the GitHub API

**One P3:** `_PUBLIC_GET` is defined but never consulted; the dispatcher uses inline path
checks (MMX-013). Cosmetic today, misleading later.

---

## 8. New finding raised by this section

### MMX-014 — `past_due` subscribers are paywalled instantly, before Stripe's dunning completes

`_entitlement_from_state` admits only `status ∈ {active, trialing}`. A `past_due`
subscription therefore falls through to `tier=free` and loses access **immediately**.

This is **deliberate and documented** in the code:

> "DELIBERATE, fail-closed: a `past_due` sub (soft decline in Stripe's dunning window) is not
> in the entitled set above, so it lands here and loses access immediately — consistent with
> the masterplan (MNZ: grace never extends to past_due/canceled)."

I am raising it not as a defect but as a **business risk the brief explicitly asks about**
("legitimate users being incorrectly paywalled"). Stripe's default dunning retries run for
roughly two weeks and a large share of soft declines — expired cards, travel-triggered bank
declines, temporary insufficient funds — recover on retry. Under the current policy those
customers are locked out of a product they are still paying for, and the most likely reaction
from a trader mid-session is to churn rather than to update a card.

The code itself notes the fix is a read-side policy change, not a rewrite:
`brain_gateway._get_allowance` / the paywall read path.

**Recommendation:** grant a bounded dunning grace (e.g. 3–7 days from
`current_period_end`) for `past_due` **only**, with an in-product banner asking the user to
update payment. Keep `canceled`/`unpaid` fail-closed exactly as now. This is a product
decision, not an engineering one — flagging it for an explicit call rather than leaving it as
an inherited default.

| Field | Value |
|---|---|
| Severity | **P2** |
| Likelihood | **High** — card failure on renewal is among the most common subscription events |
| Detectability | Poor — appears as churn, not as an error |
| Launch blocker | No — but decide deliberately before the first renewal cycle |

---

## 9. Summary

| Area | Verdict |
|---|---|
| Authentication | **Strong.** Secretless network verification eliminates the JWT vulnerability class. |
| Authorization / isolation | **Strong.** No client-supplied identity; RLS complete; AI-run ownership enforced in the artifact. |
| Entitlement | **Strong.** One canonical source, one writer, fail-closed API surfaces. |
| Billing | **Strong.** Signature-verified, recompute-from-live-state, nightly reconciler, chargeback handling. One TOCTOU on side effects. |
| Secrets | **Clean** in the working tree. Git history unscanned. |
| Admin | **Fail-closed**, defense in depth. |
| Rate limiting | **The weak spot.** Inconsistent, per-module, absent on 31 open routes. |
| Cost control | **The real problem** — see the reliability audit. Not a security failure but the most likely source of financial damage. |
