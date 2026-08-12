# Mastermind-X — Pre-Launch Production Red Team

**Audit date:** 2026-08-12
**Scope:** production failure discovery + launch readiness (not code quality, not design)
**Method:** static reconstruction of the running system from deployment contracts, unit files,
Caddy config, and source; mechanical route inventory; targeted verification of the
highest-blast-radius claims.

---

## 0. Verdict up front

**The security spine of this product is materially better than the codebase's own size and
AI-assisted provenance would predict.** Authentication, authorization, user isolation, admin
access, and Stripe webhook handling were each probed for the classic failure and each held.
I opened this audit expecting to find an auth bypass or an IDOR and did not find one.

**The launch risk is not security. It is recoverability and cost/scale control.** Specifically:
there is no verified, tested path to restore customer billing state; the LLM spend cap can be
defeated by ordinary concurrency; and the API is a single process that makes a blocking
network call to Supabase on every authenticated request.

Ranked honestly: **1 launch blocker, 4 severe, 5 important.** Most of this repo does not need
work before launch. Four things do.

---

## 1. What actually runs in production

Reconstructed from `app/deploy/*.service`, `app/deploy/Caddyfile`, `admin/deploy/admin.service`,
and `docs/PRODUCTION_RUNTIME_TRUTH.md`. Three repositories, one product.

| Layer | Reality |
|---|---|
| Edge | EdgeOne CDN → Caddy on the VPS. Every public host is edge-proxied (`Caddyfile:33-68`). |
| Public API | **One** uvicorn process, `app.main:app`, `127.0.0.1:8000`, **no `--workers`** (`macro-api.service:62`). |
| Admin console | Hand-rolled `http.server` on `127.0.0.1:8787`, Caddy-proxied at `admin.mastermind-x.com` (`admin.service`). |
| Static site | Rendered `site/` tree, served by Caddy, refreshed by a 3-minute VPS git pull. |
| Identity | Supabase Auth. Verified **over the network** per request — no local JWT secret. |
| User data | Supabase Postgres. RLS on all seven user tables (`charting-app/supabase/migrations/0001_init.sql`). |
| Entitlements | `user_entitlements` table, written by the Stripe webhook, read by `app/paywall.py`. |
| Billing | Stripe (checkout + hosted portal + webhook + nightly reconciler). |
| AI | Anthropic via `engine/neuralweb/brain_gateway.py`; file-based quota ledger under `/var/lib/macro-api/`. |
| Scheduling | ~25 systemd timers on the VPS (live bars, snapshots, prophet, market-memory lanes, sentinel). |
| Monitoring | External dead-man sentinel (`macro-sentinel.timer`) that deliberately lives **outside** GitHub Actions. |

**Authoritative vs legacy:** the FastAPI `app/` is authoritative for all `/api/*`. The static
site is authoritative for page content. `admin/` is operator-only and is not a user surface.
I found no competing legacy auth or billing system still wired in.

---

## 2. Top 10 risks, ranked

Ranked by **probability × damage × ease of remediation**, not by how alarming they sound.

### RISK-1 — No verified or tested restore path for customer data — **P0, LAUNCH BLOCKER**

A precise search for `pg_dump`, `pg_restore`, `PITR`, and `point-in-time` across
`docs/ ops/ app/ scripts/ .github/` returns **no database backup or restore procedure**.
(The "point-in-time" hits are all market-data PIT semantics, not database recovery.)

The only rollback asset in the repo is `app/deploy/live-rollback.sh`, which moves *published
artifacts* aside. It does not touch Postgres.

Everything that makes a paying customer a paying customer — `user_entitlements`,
`stripe_customer_id` mapping, `profiles`, `watchlists`, `saved_scripts`, `alerts` — lives
in Supabase. Supabase's managed plans do provide automated backups, but **which plan is
active, what the retention is, and whether a restore has ever succeeded are all unverifiable
from this repository, and no restore drill is documented anywhere.**

Why this is the launch blocker and the security findings are not: every other risk here
degrades service. This one can permanently destroy the record of who paid you.

**Remediation (hours, not days):** confirm the Supabase plan's PITR/backup setting; run one
real restore into a scratch project; write down the RTO you actually measured. Add a nightly
`pg_dump` of the seven user tables to R2 as a belt-and-braces second copy.

### RISK-2 — LLM quota cap is defeated by ordinary concurrency — **P1**

`engine/neuralweb/brain_gateway.py` enforces every quota (guest daily cap, paid lane caps,
monthly token ceiling) through this pair:

```python
def _read_quota(path): return json.loads(path.read_text(...))   # read
def _write_quota(path, data): path.write_text(json.dumps(data)) # write
```

There is **no lock and no atomic replace**. `grep -n "flock\|FileLock\|fcntl"` over that
file returns nothing relevant — the only two locks in the module guard config and chart state.

FastAPI runs non-`async def` handlers in a thread pool (~40 threads by default), and
`brain_chat` is a sync `def`. So the read-modify-write genuinely interleaves: *N* concurrent
requests all read `count = k`, all write `k+1`, and **N requests consume one unit of quota.**

Second defect in the same pair: `path.write_text()` is not atomic. A crash or a full disk
mid-write leaves truncated JSON, `_read_quota` swallows the `ValueError`, returns
`{"count": 0}` — and the user's daily cap **silently resets to zero**.

**Impact:** this is the direct path from "one enthusiastic user" to an unbounded Anthropic
bill, and it applies to anonymous guests.

### RISK-3 — Supabase Auth is a synchronous, uncached, single-point-of-failure dependency — **P1**

`require_user` (`app/main.py:735`) is the dependency behind 40 of the 49 authenticated routes.
Every single request it guards makes a **blocking** `urllib` call to Supabase
`/auth/v1/user` with a 5-second timeout, inside that same ~40-thread pool. There is no cache.

Two consequences:

1. **Scale cliff.** 40 concurrent authenticated requests against a slow Supabase exhaust the
   thread pool. Once exhausted, *every* route stalls — including the unauthenticated ones and
   the health check.
2. **Total outage on vendor degradation.** The handler converts any non-HTTP error into
   `HTTPException(502, "auth check failed")`. Supabase slow or rate-limited ⇒ the entire
   authenticated product is down.

The fix already exists in this repo and is not being used on the hot path:
`app/paywall.py:_fresh_identity` does the same verification with a 45-second
SHA256-keyed cache and shares one upstream call across uid+email. `require_user` should
adopt it.

### RISK-4 — Single API process: no redundancy, deploy is downtime — **P1**

`ExecStart=/opt/macro-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
— no `--workers`, no process manager beyond `Restart=always`.

One process means: any deploy is a hard restart with dropped in-flight requests; any hang
(see RISK-3) takes down 100% of the API; there is no rolling restart and no way to drain.
It also means all the in-memory caches (`_AUTH_CACHE`, `_ENT_CACHE`, flow TTL caches, the
gov-revenue artifact cache) are cold on every deploy — a thundering herd against every
upstream at once.

### RISK-5 — Quota system fails **open** on I/O error — **P1**

`brain_gateway.py:4598`, on failure to create the quota directory:

```python
log.error("::error::brain_gateway: GUEST QUOTA DIR UNAVAILABLE (%s) — fail-open", exc)
return True, {"lane": lane, "remaining": -1, "limit": -1, "period": "day"}
```

and `_write_quota` logs loudly but continues on write failure, explicitly documenting
"usage uncapped until the state dir is writable."

This is a *deliberate* availability trade-off and the reasoning ("a broken ledger must never
lock out paying users") is sound for paying users. It is not sound for **anonymous guests**,
where the same fail-open grants unlimited free LLM access to the internet with no ceiling.
The correct asymmetry: fail open for authenticated payers, fail **closed** for guests.

### RISK-6 — Stripe webhook has a genuine TOCTOU window — **P2**

`app/billing.py:webhook` is otherwise exemplary — real signature verification via
`stripe.Webhook.construct_event`, an idempotency table, and a `run_in_threadpool` hop so a
slow Stripe doesn't stall the event loop. But the sequence is:

```
_event_seen(event_id)        # read
await _handle_event(event)   # SLOW: Supabase + Stripe + an SMTP conversation
_record_event(event_id)      # write
```

Two concurrent deliveries of the same event both pass `_event_seen` before either records.
The database row is safe (`on_conflict=id`), but the **side effects already fired twice** —
most visibly, duplicate billing emails to the customer.

Additionally `_event_seen` returns `False` on any exception, so a brief PostgREST blip
converts every in-flight retry into a re-execution.

### RISK-7 — 31 unauthenticated, unthrottled proprietary-data endpoints — **P2**

24 `/api/government-revenue/*` routes and 7 `/api/hub/*` routes have no auth dependency
**and** no rate limiting: `grep -c` for rate-limit tokens returns **0** for both
`government_revenue.py` and `hub.py`, versus **26** for `company_intelligence.py`, which is
correctly protected. The only global middleware is `_NoStoreAPI` (cache headers).

Caddy adds no rate limiting either — only two `request_body max_size` caps. Any protection
would have to come from the EdgeOne edge, **which I could not verify from the repository.**

These serve an in-memory cached artifact, so each request is cheap. The exposure is bulk
extraction of proprietary government-contract intelligence by anyone with `curl`, and no
app-layer shed valve if someone points a scraper at it.

### RISK-8 — Entitlement grace window is 24 hours — **P2**

`app/paywall.py:_entitled` preserves a previously-confirmed *positive* entitlement for
`PAYWALL_GRACE_SECONDS` (default **86400**) when the entitlement store is unreachable.
Negative verdicts get no grace, and `invalidate_entitlement` is called on every mutation,
so this cannot resurrect a cancelled user under normal operation.

The residual: if PostgREST is down for a day, a user who cancels in that window keeps Pro
for up to 24 hours. That is a defensible business trade (never lock out a payer), but it
should be a stated policy, not an accident of a default.

### RISK-9 — Three naive `datetime.now()` sites in date-bearing engine code — **P2**

Timezone hygiene here is, overall, **excellent**: 762 timezone-aware `datetime.now(...)`
calls, **zero** `datetime.utcnow()`. Most bare-`now()` grep hits are comments *forbidding*
its use.

Three real call sites remain: `engine/special_arb.py:194`, `engine/congress_members.py:155`
(both `datetime.now().date()`), and `engine/signal_sanity.py:344`. The VPS runs UTC, so
after 20:00 ET these resolve to **tomorrow's date** for US-session logic — the classic
"signal appears one day early" defect.

### RISK-10 — Identity fallback collapses to a shared `"unknown"` bucket — **P2**

The pattern `user_id = user.get("id") or user.get("email") or "unknown"` appears at
14 sites in `app/main.py`. Any user record lacking both fields is keyed as the literal
string `"unknown"` — a bucket **shared across all such users**, used for quota accounting
and brain-run ownership. Supabase always returns `id` in practice, so likelihood is low,
but the failure mode is cross-user identity collision, which deserves a hard error rather
than a sentinel.

---

## 3. What I verified as sound (and why that matters for ranking)

These were each probed adversarially for the standard failure and each held. Listing them is
not politeness — it is what makes the four findings above credible as *the* priorities.

| Area | Probe | Result |
|---|---|---|
| JWT handling | Searched every `jwt.`, `HS256`, `verify_signature`, `jwks` site | **No local JWT decode anywhere.** Tokens are verified over the network against Supabase. There is no signing secret to leak and no `verify=False` bypass. |
| Client-supplied identity (IDOR) | Grepped every `user_id` derivation in `app/` | **All** identity derives from the verified token. No endpoint trusts a `user_id` from body, query, or path. |
| Row-level isolation | Read `0001_init.sql` | RLS enabled on all 7 user tables; owner policies `user_id = auth.uid()`; `watchlist_symbols` gated through parent ownership; `saved_scripts` public-read is explicit and intentional. |
| AI conversation IDOR | Read `brain_runs.get` | Ownership enforced **in the artifact**, not just the docstring: `return run if run.user_id == user_id else None`. Guests are structurally barred from enumeration (`active_for` returns `[]`). |
| Admin exposure | Traced `auth_enabled()` → `startup_check()` → unit file | I formed a P0 here and **retracted it**. `auth_enabled()` is `bool(ADMIN_PASSWORD)`, which looks fail-open — but `startup_check()` refuses to boot when `ADMIN_DEPLOYED=1` without a password, and the unit hardcodes `--deployed` in `ExecStart`, so the guard fires even if the env file is missing. Fail-closed. |
| Admin transport | Read `_guard()` | Host allow-list (DNS rebinding), `Content-Type` pinning, Origin check on writes, HMAC-signed session with constant-time compare, double-submit CSRF, login throttle. |
| Webhook authenticity | Read `webhook()` | Real signature verification. Unsigned or missigned payloads are rejected 400. `STRIPE_WEBHOOK_SECRET` unset ⇒ 503, not open. |
| Guest quota farming | Read `_check_and_increment_guest_quota` | Dual-keyed on cookie **and** IP, blocking when **either** is exhausted — so rotating the client-settable `mm_aid` cookie does not mint fresh quota. |
| Secrets in the browser | Grepped `templates/`, `site/` for `SERVICE_ROLE` and JWT literals | Nothing. The service-role key is server-side only. |
| Path traversal / injection | Checked param handling on the open routes | Cursors validated with `re.fullmatch`, tickers normalized-or-422, and the artifact path is fixed, not param-derived. |
| Staleness honesty | Checked API and UI | The product does **not** silently render last-known as current: `{"stale": true}` is merged into degraded responses, 503 only when never fetched, and the UI carries a `.stale` class and staleness chip. |
| Alarm independence | Read `macro-sentinel.service` | A dead-man freshness sentinel that deliberately runs **outside** GitHub Actions, written after a real 6-day outage in which every alarm lived inside the failing system. This is mature operational thinking. |

---

## 4. Architectural weaknesses (structural, not bugs)

1. **Two identity paths with different semantics.** `require_user` (uncached, 502-on-failure)
   and `paywall._fresh_identity` (45s cache, deny-on-failure) both verify the same token
   differently. One should be built on the other.
2. **Durable counters on a local filesystem.** Quota, token ceilings, and free-credit pools
   are JSON files with non-atomic writes. This is the wrong substrate for money-adjacent
   counters and it is already the source of RISK-2 and RISK-5.
3. **Single-process everything.** No horizontal capacity, and every in-memory cache is
   process-local, so scaling out later will change correctness (quota, throttles), not just
   throughput.
4. **Rate limiting is per-module and inconsistent.** `company_intelligence` is well
   protected; `government_revenue` and `hub` have none. This should be one policy at one
   layer, not a per-file decision.

---

## 5. Recommended actions

**Before launch (in this order):**

1. Verify and *test* the Supabase restore path; add a nightly `pg_dump` of the seven user
   tables to R2. (RISK-1)
2. Put a lock and an atomic write under the quota ledger; make the guest path fail closed.
   (RISK-2, RISK-5)
3. Give `require_user` the 45-second cache `_fresh_identity` already implements. (RISK-3)
4. Run uvicorn with `--workers 2` behind the existing Caddy, or accept and document that
   deploys are downtime. Note: workers ×N makes the file-based quota race worse, so this
   must land **after** fix 2. (RISK-4)

**Before scale:** webhook idempotency claim-before-handle (RISK-6); one rate-limit policy
covering the 31 open routes (RISK-7).

**Post-launch hardening:** the three naive datetimes (RISK-9); replace the `"unknown"`
identity sentinel with a hard error (RISK-10); state the 24h grace as policy (RISK-8).

---

## 6. Coverage and honesty statement

**Verified by reading the artifact this session:** Parts I, III, IV, V, VI, VIII, XII, XIII,
XVI, XXII, XXVI, and the freshness half of VII/XX.

**Inspected but not exhaustively verified:** Parts IX, X, XIV, XV, XVII, XXI, XXIII, XXIV.
I sampled these and found no P0-class defect, but I did not trace every pipeline, every
cache key, or every scheduler unit. The ~25 systemd timers in particular deserve a dedicated
overlap/locking pass.

**Not covered:** Part XXV (live browser testing) and Part XXIX (chaos tests) require a
running environment. Chaos tests are *proposed* in the reliability audit but were not
executed.

**Claims I could not close from the repository:** whether EdgeOne provides edge rate
limiting; which Supabase plan is active and therefore what backup retention exists. Both are
one operator check away and both are called out as launch gates rather than assumed.

---

*Companion documents:* `MASTERMIND_FAILURE_MODE_REGISTER.md` ·
`MASTERMIND_SECURITY_AUTH_BILLING_AUDIT.md` ·
`MASTERMIND_PRODUCTION_RELIABILITY_AUDIT.md` · `MASTERMIND_LAUNCH_GATES.md` ·
`MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md`
