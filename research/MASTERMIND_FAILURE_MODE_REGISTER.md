# Mastermind-X — Failure Mode Register

**Audit date:** 2026-08-12
**Severity model:** P0 existential/launch blocker · P1 severe · P2 important · P3 improvement
**Detectability:** how quickly the team learns it happened, with current instrumentation.

Ordered by severity, then by probability × damage.

---

## MMX-001 — No verified restore path for customer billing state

| Field | Value |
|---|---|
| **Subsystem** | Database / disaster recovery (Supabase Postgres) |
| **Failure** | Loss or corruption of `user_entitlements`, `profiles`, `watchlists`, `saved_scripts`, `alerts` cannot be demonstrably recovered. |
| **Trigger** | Bad migration; accidental `DELETE`/`TRUNCATE` via service-role key; Supabase project incident; billing-lapse project pause. |
| **User impact** | Every paying customer loses access simultaneously. Watchlists and saved work gone. |
| **Business impact** | Existential. You cannot prove who paid you, cannot restore entitlement, and must refund or re-grant from Stripe records by hand. |
| **Likelihood** | Low per-day, but **cumulative and non-zero**; the service-role key bypasses RLS, so one bad admin action suffices. |
| **Severity** | **P0** |
| **Detectability** | Immediate (total access failure) — but detection is worthless without recovery. |
| **Current controls** | Supabase managed backups *may* exist depending on plan. `app/deploy/live-rollback.sh` recovers published artifacts only — it never touches Postgres. |
| **Evidence** | `grep -rn "pg_dump\|pg_restore\|PITR\|point-in-time" docs ops app scripts .github` → zero database-recovery hits (all matches are market-data point-in-time semantics). No restore runbook in `docs/`. |
| **Remediation** | (1) Confirm the active Supabase plan's PITR/backup retention. (2) Perform one real restore into a scratch project and record measured RTO/RPO. (3) Add a nightly `pg_dump` of the 7 user tables to R2 with 30-day retention. (4) Write the restore runbook. |
| **Owner** | Ops / backend lead |
| **Launch blocker** | **YES** |

---

## MMX-002 — Quota ledger race allows unbounded LLM spend

| Field | Value |
|---|---|
| **Subsystem** | AI gateway — `engine/neuralweb/brain_gateway.py` |
| **Failure** | Non-atomic, unlocked read-modify-write on the quota files. Concurrent requests all read the same count and all write `count+1`, so *N* parallel requests consume **one** unit of quota. |
| **Trigger** | Any client issuing parallel requests — trivially, `xargs -P 20 curl`. Affects guest daily caps, paid lane caps, and the monthly token ceiling alike. |
| **User impact** | None visible (the abuser gets more service). |
| **Business impact** | Direct, uncapped Anthropic spend. This is the single most plausible route from "one enthusiastic or malicious user" to a five-figure surprise bill. |
| **Likelihood** | **High** — requires no sophistication and happens accidentally with a multi-tab client. |
| **Severity** | **P1** |
| **Detectability** | **Poor.** Discovered via the vendor bill, not via an alarm. No alert exists on spend rate. |
| **Current controls** | Dual cookie+IP keying (defeats cookie rotation but not concurrency); a burst throttle `_brain_throttle_check` that limits rate but not the read-modify-write interleave. |
| **Evidence** | `_read_quota` / `_write_quota` in `brain_gateway.py` use bare `read_text`/`write_text`. `grep -n "flock\|FileLock\|fcntl"` over the module returns no quota lock — only `_GUEST_CFG_LOCK` (config) and `_chart_state_lock`. Handlers are sync `def`, so FastAPI runs them in its ~40-thread pool. |
| **Remediation** | Wrap check-and-increment in `fcntl.flock` on the ledger file, or move counters to Postgres and use an atomic `UPDATE ... RETURNING`. Write via `tmp + os.replace`. |
| **Owner** | Backend / AI platform |
| **Launch blocker** | Should fix before launch — it is the cost-control mechanism itself. |

---

## MMX-003 — Torn quota write silently resets a user's cap to zero

| Field | Value |
|---|---|
| **Subsystem** | AI gateway — quota persistence |
| **Failure** | `path.write_text()` is not atomic. A crash, restart, or full disk mid-write leaves truncated JSON; `_read_quota` catches the `ValueError` and returns `{"count": 0}`. |
| **Trigger** | Process restart during a write (deploys restart the single uvicorn process), disk pressure on `/var/lib/macro-api`. |
| **User impact** | None visible. |
| **Business impact** | Quota resets to zero, granting a fresh full allowance. Compounds MMX-002. |
| **Likelihood** | Medium — every deploy is a restart, and the ledger is written on every chat request. |
| **Severity** | **P1** |
| **Detectability** | **None.** The reset is indistinguishable from a legitimate new period. |
| **Current controls** | None. |
| **Evidence** | `_write_quota` → `path.write_text(json.dumps(data))`; `_read_quota` → bare `except Exception: pass` then `return {"count": 0}`. |
| **Remediation** | Atomic write (`tmp + os.replace`). Distinguish "missing ledger" from "corrupt ledger" — the latter should alarm, not silently zero. |
| **Owner** | Backend / AI platform |
| **Launch blocker** | Fix with MMX-002 (same two functions). |

---

## MMX-004 — Supabase Auth is an uncached, synchronous, total-outage dependency

| Field | Value |
|---|---|
| **Subsystem** | Authentication — `app/main.py:735` `require_user` |
| **Failure** | Every request on 40 of 49 authenticated routes makes a blocking 5s `urllib` call to Supabase `/auth/v1/user`, with no cache, inside FastAPI's ~40-thread pool. Non-HTTP failure becomes `502`. |
| **Trigger** | Supabase latency, rate limiting, or outage; or simply ≥40 concurrent authenticated users. |
| **User impact** | Thread-pool exhaustion stalls **every** route — including unauthenticated ones and `/api/health`. During a Supabase incident the entire authenticated product returns 502. |
| **Business impact** | Full product outage driven by a vendor you do not control, plus a hard concurrency ceiling far below 5,000 users. |
| **Likelihood** | **High at launch scale.** Supabase Auth enforces per-project rate limits that a real user base will reach. |
| **Severity** | **P1** |
| **Detectability** | Good — `/api/health` and the sentinel would show it, though the health check itself is affected by pool exhaustion. |
| **Current controls** | None on this path. |
| **Evidence** | `require_user` body: no cache, `timeout=5`, `raise HTTPException(502, ...)`. Contrast `app/paywall.py:_fresh_identity`, which implements exactly the needed 45s SHA256-keyed cache and shares one upstream call for uid+email. |
| **Remediation** | Re-implement `require_user` on top of `_fresh_identity` (the cache already exists in-repo). Cap concurrent upstream auth calls with a semaphore so a slow vendor sheds rather than stalls. |
| **Owner** | Backend lead |
| **Launch blocker** | Should fix before launch — this is the #1 scale cliff. |

---

## MMX-005 — Quota system fails open for anonymous guests

| Field | Value |
|---|---|
| **Subsystem** | AI gateway — quota I/O error path |
| **Failure** | When the quota directory is unavailable, `_check_and_increment_guest_quota` returns `allowed=True` with `limit=-1`. `_write_quota` failures log and continue. |
| **Trigger** | `MACRO_API_STATE_DIR` missing (the deploy note says the VPS must `mkdir` it once), permissions error, disk full. |
| **User impact** | None visible. |
| **Business impact** | Unlimited free LLM access to anonymous internet traffic, with no ceiling and no alarm beyond a log line. |
| **Likelihood** | Medium — depends on a one-time manual `mkdir` documented in a docstring. |
| **Severity** | **P1** |
| **Detectability** | Medium — it does emit `::error::` log lines, but nothing pages anyone. |
| **Current controls** | Loud error logging only. |
| **Evidence** | `brain_gateway.py:4598` — `log.error(... "fail-open"); return True, {"limit": -1}`. `_write_quota` comment: "usage uncapped until the state dir is writable." |
| **Remediation** | Keep fail-open for **authenticated paying** users (correct — never lock out a payer); fail **closed** for guests. Add a hard global daily spend ceiling independent of the per-user ledger. Alert on the `::error::` line. |
| **Owner** | Backend / AI platform |
| **Launch blocker** | Should fix before launch (cheap, asymmetric). |

---

## MMX-006 — Single API process: no redundancy, deploy is downtime

| Field | Value |
|---|---|
| **Subsystem** | Deployment — `macro-api.service` |
| **Failure** | One uvicorn process, no `--workers`. No rolling restart, no drain, no horizontal capacity. |
| **Trigger** | Every deploy; any hang or crash. |
| **User impact** | Dropped in-flight requests on each deploy; total outage on any hang; cold caches cause a thundering herd against every upstream after each restart. |
| **Business impact** | Visible downtime during ordinary shipping; no headroom. |
| **Likelihood** | Certain (deploys are routine). |
| **Severity** | **P1** |
| **Detectability** | Good. |
| **Current controls** | `Restart=always`. |
| **Evidence** | `macro-api.service:62` — `ExecStart=... uvicorn app.main:app --host 127.0.0.1 --port 8000` (no worker flag). |
| **Remediation** | `--workers 2+` behind existing Caddy. **Ordering constraint:** multiple workers make MMX-002/003 strictly worse (separate processes, same files), so this must land *after* the quota ledger is made atomic and cross-process safe. |
| **Owner** | Ops |
| **Launch blocker** | No — but sequence it correctly. |

---

## MMX-007 — Stripe webhook TOCTOU produces duplicate side effects

| Field | Value |
|---|---|
| **Subsystem** | Billing — `app/billing.py:webhook` |
| **Failure** | `_event_seen` (read) → `_handle_event` (slow: Supabase + Stripe + SMTP) → `_record_event` (write). Concurrent duplicate deliveries both pass the seen-check. |
| **Trigger** | Stripe retry overlapping the original; Stripe's documented at-least-once delivery. Also: `_event_seen` returns `False` on **any** exception, so a PostgREST blip re-opens every retry. |
| **User impact** | Duplicate billing emails. Entitlement itself stays correct — `_handle_event` recomputes from live Stripe state, so it is genuinely idempotent for DB state. |
| **Business impact** | Trust damage from duplicate mail; wasted Stripe/SMTP calls. **Not** duplicate charges — Stripe owns charging, and the webhook does not create charges. |
| **Likelihood** | Medium (Stripe duplicates are routine). |
| **Severity** | **P2** |
| **Detectability** | Poor — surfaces as customer complaints about repeated email. |
| **Current controls** | Signature verification; `stripe_events` table with `on_conflict=id`; threadpool hop; idempotent recompute. |
| **Evidence** | Handler body sequence; `_event_seen` `except: return False`. |
| **Remediation** | Claim-before-handle: `INSERT` the event id **first** (relying on the unique constraint to reject duplicates), then handle, then mark complete. Treat a store exception as "cannot verify" and let Stripe retry rather than proceeding. |
| **Owner** | Payments |
| **Launch blocker** | No |

---

## MMX-008 — 31 unauthenticated, unthrottled proprietary-intelligence endpoints

| Field | Value |
|---|---|
| **Subsystem** | Public API — `app/government_revenue.py` (24 routes), `app/hub.py` (7 routes) |
| **Failure** | No auth dependency and no rate limiting. Freely enumerable and bulk-extractable. |
| **Trigger** | Any scraper. |
| **User impact** | None directly. |
| **Business impact** | Proprietary government-contract and options-analytics intelligence — a core part of what subscribers pay for — is available to anyone with `curl`. No app-layer shed valve under flood. |
| **Likelihood** | High once the product has any visibility. |
| **Severity** | **P2** |
| **Detectability** | Poor — first-party analytics would show traffic, but nothing alarms on extraction patterns. |
| **Current controls** | Responses are served from an in-memory mtime-keyed artifact cache, so cost per request is low. Caddy applies body-size caps to two unrelated paths only. |
| **Evidence** | `grep -c "_allow_request\|rate_limit\|RATE_LIMIT\|429"` → `government_revenue.py: 0`, `hub.py: 0`, `company_intelligence.py: 26`, `research.py: 4`. Only global middleware is `_NoStoreAPI`. Caddyfile has no `rate_limit` directive. |
| **Remediation** | Apply the `company_intelligence` `_allow_request` pattern uniformly, ideally as one middleware rather than per-module. Decide deliberately which of these are public marketing surfaces and which are subscriber value. **Open question for the operator:** whether EdgeOne provides edge rate limiting — not verifiable from the repo. |
| **Owner** | Backend + product |
| **Launch blocker** | No — but decide the policy before marketing drives traffic. |

---

## MMX-009 — 24-hour positive-entitlement grace on store outage

| Field | Value |
|---|---|
| **Subsystem** | Paywall — `app/paywall.py:_entitled` |
| **Failure** | `PAYWALL_GRACE_SECONDS` defaults to 86400: a previously-confirmed positive entitlement survives up to 24h of entitlement-store unreachability. |
| **Trigger** | PostgREST/Supabase outage. |
| **User impact** | Positive — payers are not locked out during an outage. This is the intended behavior. |
| **Business impact** | A user who cancels during an outage window retains Pro for up to 24h. Bounded and small. |
| **Likelihood** | Low. |
| **Severity** | **P2** |
| **Detectability** | Good — `log.warning("paywall: entitlement store unavailable")`. |
| **Current controls** | Grace applies to **positive** verdicts only; `invalidate_entitlement` is called on every mutation; API surfaces fail **closed** via `enforce_site_full`. Well-reasoned design. |
| **Evidence** | `_entitled` grace branch and its comment; `_seconds("PAYWALL_GRACE_SECONDS", 86400.0, 0.0, 86400.0)`. |
| **Remediation** | None required. Ratify 24h as deliberate policy, or shorten to ~1h. Document it. |
| **Owner** | Product |
| **Launch blocker** | No |

---

## MMX-010 — Naive `datetime.now()` in three date-bearing engine paths

| Field | Value |
|---|---|
| **Subsystem** | Engine — `special_arb.py:194`, `congress_members.py:155`, `signal_sanity.py:344` |
| **Failure** | `datetime.now().date()` on a UTC server resolves to **tomorrow's** date after 20:00 ET. |
| **Trigger** | Any run in the 20:00–24:00 ET window (i.e. the evening render lane). |
| **User impact** | A signal or as-of date attributed to the wrong trading day. |
| **Business impact** | For a financial product, a one-day-early signal invalidates the intelligence and is very hard to explain to a paying trader. |
| **Likelihood** | Low-medium — depends whether these specific paths run in the evening lane. |
| **Severity** | **P2** |
| **Detectability** | Poor — produces a plausible wrong date, not an error. |
| **Current controls** | Codebase-wide convention is strong: **762** tz-aware `datetime.now(...)` calls and **zero** `datetime.utcnow()`. These three are the exceptions. |
| **Evidence** | `grep -rn "datetime\.now()" app engine` → 10 hits, 7 of which are comments forbidding the pattern; 3 real call sites as listed. |
| **Remediation** | Pass an explicit `ZoneInfo("America/New_York")` or accept an injected `now`, matching the house pattern already used in `world_state.py`. |
| **Owner** | Engine |
| **Launch blocker** | No |

---

## MMX-011 — Identity fallback collapses distinct users into a shared `"unknown"` bucket

| Field | Value |
|---|---|
| **Subsystem** | `app/main.py` — 14 call sites |
| **Failure** | `user_id = user.get("id") or user.get("email") or "unknown"`. A user record lacking both fields is keyed as the literal string `"unknown"`, shared by all such users. |
| **Trigger** | A Supabase user record without `id` and without `email` (e.g. an unusual provider or a schema change). |
| **User impact** | Shared quota bucket; and because brain-run ownership compares `run.user_id == user_id`, two `"unknown"` users could read each other's AI conversations. |
| **Business impact** | Cross-user data exposure — but only in a state Supabase does not currently produce. |
| **Likelihood** | **Low** (Supabase always returns `id`). |
| **Severity** | **P2** — low likelihood, high impact if reached. |
| **Detectability** | Poor. |
| **Current controls** | Supabase's own guarantee that `id` is present. |
| **Evidence** | Pattern repeated at `app/main.py:796, 826, 887, 916, 1172, 1235, 1314, 1326, 1342, 1359, 1377, 1422, 1436` and elsewhere. |
| **Remediation** | Raise `HTTPException(401)` when a verified record yields no stable id. Never use a constant sentinel as an identity key. |
| **Owner** | Backend |
| **Launch blocker** | No |

---

## MMX-012 — Mixed identity namespace (UUID or email) in one key space

| Field | Value |
|---|---|
| **Subsystem** | Quota ledger keying |
| **Failure** | The same fallback chain keys ledgers by UUID *or* by email depending on which is present, so one human can occupy two ledger identities across time. |
| **Trigger** | Any record where `id` is absent but `email` is present. |
| **User impact** | Quota accounting inconsistency. |
| **Business impact** | Minor. |
| **Likelihood** | Low. |
| **Severity** | **P3** |
| **Detectability** | Poor. |
| **Current controls** | None. |
| **Evidence** | Same sites as MMX-011. |
| **Remediation** | Fold into MMX-011's fix — one canonical identity type. |
| **Owner** | Backend |
| **Launch blocker** | No |

---

## MMX-013 — Dead `_PUBLIC_GET` allow-list in the admin dispatcher

| Field | Value |
|---|---|
| **Subsystem** | `admin/server.py` |
| **Failure** | `_PUBLIC_GET` is defined but the dispatcher uses explicit inline `if path in (...)` checks instead. The set is not consulted. |
| **Trigger** | N/A — latent. |
| **User impact** | None today. |
| **Business impact** | A future maintainer adding a path to `_PUBLIC_GET` would believe they had made it public (or, worse, believe the set *bounds* what is public) and be wrong in either direction. |
| **Likelihood** | Low. |
| **Severity** | **P3** |
| **Detectability** | N/A. |
| **Current controls** | The real gate (`if settings.auth_enabled() and not self._authed()`) sits before all non-public dispatch and is correct. |
| **Evidence** | `_PUBLIC_GET` defined immediately above `do_GET`; `do_GET` never references it. |
| **Remediation** | Delete the constant, or make the dispatcher actually use it. |
| **Owner** | Backend |
| **Launch blocker** | No |

---

## MMX-014 — `past_due` subscribers are paywalled instantly, before dunning completes

| Field | Value |
|---|---|
| **Subsystem** | Billing / entitlement — `app/billing.py:_entitlement_from_state` |
| **Failure** | Only `status ∈ {active, trialing}` is entitling. A `past_due` subscription falls through to `tier=free` and loses access immediately. |
| **Trigger** | Any soft decline on renewal — expired card, travel-triggered bank decline, temporary insufficient funds. |
| **User impact** | A customer who is still paying, and whose payment will most likely succeed on Stripe's retry, is locked out mid-session with no grace. |
| **Business impact** | Churn and support load at exactly the worst moment. Stripe's dunning runs ~2 weeks and a large share of soft declines recover; this policy converts a recoverable payment event into a cancellation trigger. |
| **Likelihood** | **High** — renewal card failure is among the most common subscription events at scale. |
| **Severity** | **P2** |
| **Detectability** | Poor — presents as churn, not as an error. |
| **Current controls** | **Deliberate design**, not an oversight. The reducer documents it: "DELIBERATE, fail-closed: a `past_due` sub … loses access immediately — consistent with the masterplan (MNZ: grace never extends to past_due/canceled)." The real status is still recorded for the admin view. |
| **Evidence** | `_entitlement_from_state` entitled-set filter and the comment block beneath it. |
| **Remediation** | Product decision, not an engineering fix. Suggested: bounded dunning grace (3–7 days past `current_period_end`) for `past_due` **only**, plus an in-product "update your payment method" banner. Keep `canceled`/`unpaid` fail-closed unchanged. The code notes this is a read-side policy change (`brain_gateway._get_allowance` / the paywall read path), not a rewrite. |
| **Owner** | Product (with payments) |
| **Launch blocker** | No — but make it an explicit call before the first renewal cycle rather than an inherited default. |

---

## Register summary

| Severity | Count | IDs |
|---|---|---|
| **P0** | 1 | MMX-001 |
| **P1** | 5 | MMX-002, 003, 004, 005, 006 |
| **P2** | 6 | MMX-007, 008, 009, 010, 011, 014 |
| **P3** | 2 | MMX-012, 013 |

**Clustering:** MMX-002/003/005 are all the same 15 lines of quota persistence.
MMX-011/012 are the same one-line identity expression. Four small, well-scoped edits close
seven of the thirteen findings.

**Deliberately not raised as findings:** authentication bypass, IDOR on user resources,
cross-tenant RLS gaps, admin exposure, webhook forgery, and secrets in client bundles were
each probed and each held. See §3 of `MASTERMIND_PRELAUNCH_RED_TEAM.md` for the probes and
results.
