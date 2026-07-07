# MomoEdge Alerts & Infrastructure Spec
*Reverse-engineered from client JS for competitive feature study. Sources: notifications.js, alert-renderer.js, config.js, app-config.js, supabase.js, websocket.js, mode-toggle.js, price-subscription.js, access-gate.js.*

---

## 1. Alert Taxonomy

### 1.1 Alert Types (ALERT_TYPES_MATRIX, notifications.js:858–872)

| Key | Label | Notes |
|-----|-------|-------|
| `new_signal` | New signal | Default ON (legacy), ON (modern) |
| `trigger_conf` | Trigger confirmed | Default ON |
| `target` | Target hit | Default ON; fires on T1/T2/T3 hit |
| `danger` | Danger zone | Default ON; zone transition only, rate-cap 30 min |
| `invalidation` | Invalidation | Default ON |
| `flow` | Flow signals | Default OFF |
| `structural` | Structural | Default OFF |
| `position_closed` | Position closed | Default ON |
| `oracle_full_position` | Hold full position | Default ON |
| `whale` | Whale alerts | Default ON |
| `death_watch` | Death watch | Default ON |
| `score_90` | Score 90 or higher | Default OFF; requires explicit opt-in stored in `trader_profiles.score_90_opted_in_at` |
| `security` | Security | `locked: true` — always on, quiet_hours_bypass=true, cannot be toggled |

### 1.2 Internal alert-type keys (used in code, not labels)

From alert-renderer.js ALERT_TYPE_PREF_KEY map:
- `new_signal`, `trigger_confirmed`, `hit_t1`, `hit_t2`, `hit_t3`, `danger`, `invalidated`, `closed`, `full_position`, `whale_qualified`, `death_watch`, `structural_squeeze`, `structural_cascade`

### 1.3 Alert Severity Values
- `urgent` — invalidation, danger; triggers bell `urgent` CSS class, double sound, vibrate pattern `[100, 50, 200]`
- `action` — target hits, trigger confirmed, closed
- `info` — new signal, test alert

### 1.4 Trigger Logic (checkAllAlerts, notifications.js:100–193)
- **Danger zone**: fires when `curZone === 'danger'` AND `prevZone !== 'danger'` AND `prevZone !== 'invalidated'`; rate-capped at **1,800,000 ms (30 min)** per signal (`_lastDangerAlertTs`)
- **Trigger confirmed**: fires once per signal when `parseTriggerHit()` returns `hit === true` AND price is fresh (< 300 s old)
- **T1/T2/T3 targets**: fires once each per signal lifetime; hit state stored in `_notifiedHits[key].t1/.t2/.t3`
- **Invalidation**: fires once when `live.zone === 'invalidated'`; stored in `_notifiedHits[key].invalidated`
- **Position closed**: fires once when `sig.is_active` transitions `true → false` AND the close timestamp is after `oracle_last_seen_at`; gated by `_alertPrefs.position_closed`
- **Crypto/forex exception**: price alerts skip the `isMarketOpen()` gate for these asset classes
- **Price staleness gate**: skips any alert if `cached.time` is more than **300,000 ms (5 min)** old

### 1.5 Alert ID Construction (makeAlertId)
```
alertId = signalId + ':' + alertType_normalized + ':' + eventTime_ISO
```
Deduplication: if the same ID already exists in `_alertLog`, the alert is silently dropped (prevents re-fire on reload).

---

## 2. Notification Channels

### 2.1 Channel Matrix (CHANNELS_MATRIX, notifications.js:873–879)

| Key | Label | Status |
|-----|-------|--------|
| `push` | Push | Live (Web Push via VAPID + SW) |
| `sound` | Sound | Live (Web Audio API, 800 Hz sine, 0.3 s decay) |
| `realtime` | In-app | Live (toast + bell panel) |
| `sms` | SMS | Gated (`sms_dispatch_enabled` app_config flag + phone verify) |
| `email` | Email | `disabled: true` — UI present but not functional |

### 2.2 Push Channel Details
- **VAPID public key**: `BEJmX2euDyPfLc_xcCKM89RDV1frQ9yCoVnIsMLtxheNTy25enUxedoImB02FlKYyxkmSqkmIOVF38MOz_YilVY`
- **Subscribe endpoint**: `/.netlify/functions/push-subscribe` (POST to store, DELETE to remove)
- **Dispatch endpoint**: `/.netlify/functions/push-send` (server-side, not called from client)
- Service worker: `/sw.js`; SW message protocol: `{ type: 'SHOW_NOTIFICATION', title, body, icon, tag, severity, signalId, url }`; click returns `{ type: 'NOTIFICATION_CLICK', signalId }`
- iOS PWA detection: `navigator.standalone || matchMedia('(display-mode: standalone)')` — sent as `is_ios_pwa` flag to push-subscribe
- Push permission check: `Notification.permission !== 'granted'` blocks; requesting on toggle
- Batch window: **3,000 ms** — alerts coalesced before push fires; batches > 1 show count + up to 5 lines

### 2.3 Sound Channel Details
- `AudioContext` / `webkitAudioContext`; oscillator frequency **800 Hz**, type `sine`
- Gain: `0.3` → `0.01` ramp over **0.3 s**
- Urgent alerts double-fire with **300 ms** spacing

### 2.4 In-app (realtime/toast) Channel Details
- Toast duration: `TOAST_DURATION_MS: 3200` (config.js:33)
- Panel: `#notifPanel` sliding panel; badge capped at `99+`; auto-mark-read after **250 ms** open
- Alert log: local cap **200 entries** (two-pass prune: read entries first, then hard truncate)
- `oracle_alert_log` localStorage key (user-scoped via `_userKey()`)
- Archive loads from Supabase in pages of **50**

### 2.5 SMS Channel Details
- Gated by `app_config.sms_dispatch_enabled` (Supabase realtime `app_config` table, key `sms_dispatch_enabled`)
- Also allowlisted per-user: `trader_profiles.sms_allowlist`
- Phone verification flow: Edge Function `phone-verify-send` (POST `{ phone_e164 }`), then `phone-verify-check` (POST `{ phone_e164, code }`)
- OTP resend cooldown: **30,000 ms (30 s)**
- Code format: 6 digits
- E.164 format required; default country prefix `+1`; pattern `^\+[1-9]\d{6,14}$`
- SMS consent stored in `trader_profiles.sms_consent_at` + `sms_opt_in: true`
- Error reasons surfaced from server: `feature_disabled`, `no_credentials`, `invalid_phone`, `rate_limited`, `incorrect_code`, `expired`, `twilio_error` (implies Twilio backend)
- SMS column states: `coming_soon` (master disabled + not allowlisted), `needs_verify` (enabled but no verified phone), `active`

### 2.6 Email Channel
- Present in matrix as `disabled: true`; no client code sends email — server-side only, not implemented on client.

---

## 3. Alert Presets

Defined in `ALERT_PRESETS` (notifications.js:896–943). Applied via `applyPreset(key)` which upserts all matrix rows to `user_alert_channel_prefs`.

### `focused`
| Type | Channels |
|------|----------|
| new_signal | realtime |
| trigger_conf | realtime, sound |
| target | realtime, sound |
| danger | realtime, sound, **push** |
| invalidation | realtime, sound, **push** |
| position_closed | realtime |

### `standard`
| Type | Channels |
|------|----------|
| new_signal | realtime, push, sound |
| trigger_conf | realtime, push, sound |
| target | realtime, push, sound |
| danger | realtime, push, sound |
| invalidation | realtime, push, sound |
| whale | realtime, sound |
| death_watch | realtime, sound |
| oracle_full_position | realtime, sound |
| position_closed | realtime, sound |
| flow | realtime |
| structural | realtime |
| score_90 | realtime |

### `maximum`
All 12 non-security types on all 4 live channels: `realtime, push, sound, sms`

### `critical_only`
| Type | Channels |
|------|----------|
| danger | realtime, push, sound |
| invalidation | realtime, push, sound |

### `custom`
Auto-detected when current matrix state matches no preset.

---

## 4. Quiet Hours

Stored in `trader_profiles` columns: `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`, `quiet_hours_tz`. Client reads/writes via `loadQuietHours()` / `saveQuietHours()`.

- UI elements: `#asQhEnabledToggle`, `#asQhStart` (time input), `#asQhEnd` (time input), `#asQhTz` (select)
- Enforcement note: `security` alert type always bypasses quiet hours (`quiet_hours_bypass: true` in matrix row)
- Enforcement at send time: **server-side only** — the client stores the preference but does not locally suppress channels during quiet hours

---

## 5. Rate Caps

| Event | Cap |
|-------|-----|
| Danger zone alert per signal | 1,800,000 ms (30 min), persisted in `oracle_danger_ts` localStorage key |
| Test alert button | 30,000 ms (30 s) client-side cooldown |
| Relay request dedup per ticker | 3,000 ms (`RELAY_REQUEST_MIN_INTERVAL_MS`) |
| Push subscribe store / remove retry | No explicit client rate cap (server enforces) |
| Supabase sync circuit breaker | Opens after 3 consecutive failures; resets after **300,000 ms (5 min)** |

---

## 6. Score ≥ 90 Opt-In Flow

1. User first enables `score_90` cell in matrix
2. If `_score90OptedInAt == null` AND `_score90OptInLoaded`, shows `#score90OptInOverlay` modal
3. On confirm: writes `trader_profiles.score_90_opted_in_at = nowIso`, then proceeds with `toggleMatrixCell`
4. Cancel: no-op, cell stays off

---

## 7. Alert Defaults by Cohort

`C3_FLIP_CUTOFF: '2026-05-27'` (config.js:64). Users created on or after this date get `ALERT_PREF_DEFAULTS_MODERN`; earlier users get `ALERT_PREF_DEFAULTS`.

| Key | Legacy default | Modern (≥ 2026-05-27) default |
|-----|---------------|-------------------------------|
| push | false | **true** |
| sound | false | **true** |
| toast | true | true |
| vibrate | false | false |
| newSignal | true | true |
| target | true | true |
| trigger | true | true |
| danger | true | true |
| invalidation | true | true |
| flow | false | false |
| structural | false | false |
| position_closed | true | true |
| oracle_full_position | true | true |
| whale | true | true |
| death_watch | true | true |
| score_90 | false | false |

---

## 8. Supabase Infrastructure

### 8.1 Project
- **Project URL**: `https://pojiqfeemksvocnaellu.supabase.co`
- **REST base**: `https://pojiqfeemksvocnaellu.supabase.co/rest/v1`
- **Anon key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBvamlxZmVlbWtzdm9jbmFlbGx1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEyNjg2NTgsImV4cCI6MjA4Njg0NDY1OH0.oOrfkygK_MM-zZyemF0D2HtL8YRuzrryRQ2dmSRwAXI` (public anon; not a secret)
- **Custom auth domain**: `auth.momoedge.ai` (proxies Supabase; does NOT properly proxy WebSocket upgrades — price client uses direct URL)

### 8.2 Tables (named in client code)

| Table | Key columns observed | Notes |
|-------|---------------------|-------|
| `user_alert_preferences` | user_id, push_enabled, sound_enabled, toast_enabled, vibrate_enabled, new_signal, target, trigger_conf, danger, invalidation, flow, structural, position_closed, oracle_full_position, whale, death_watch, score_90, updated_at | Embedded DDL in notifications.js:6–21; RLS enabled |
| `user_alerts` | id (text PK), user_id, severity, icon, message, signal_id, alert_type, read (bool), read_at, created_at, trashed_at, data | Soft delete via trashed_at; DDL in notifications.js:27–42; RLS; indexes on (user_id, created_at DESC) and unread |
| `user_notified_hits` | user_id, signal_id, hit_type, notified_at | PK (user_id, signal_id, hit_type); DDL in notifications.js:44–54; RLS |
| `user_alert_channel_prefs` | user_id, alert_type, channel, enabled, quiet_hours_bypass | Upsert conflict: `user_id,alert_type,channel`; loaded in `loadAlertMatrix()` |
| `trader_profiles` | user_id, is_admin, subscription_status, stripe_subscription_id, terms_accepted_at, sms_consent_at, sms_opt_in, sms_allowlist, phone_number_e164, phone_verified_at, quiet_hours_enabled, quiet_hours_start, quiet_hours_end, quiet_hours_tz, score_90_opted_in_at | Central user profile table |
| `alert_templates` | alert_type, channel, locale, version, title, body, severity, is_active | Loaded by alert-renderer.js; filtered by `is_active=true` AND `locale='en-US'`; versioned (highest version wins); Mustache `{{var}}` template syntax |
| `signals` | (realtime subscription only; columns from supabase.js) | Realtime channel `oracle-terminal` on `postgres_changes event=*` |
| `performance` | (realtime subscription only) | Realtime channel `oracle-terminal` |
| `broadcast` | (realtime subscription only) | Realtime channel `oracle-terminal` |
| `app_settings` | (realtime subscription only) | Realtime channel `oracle-terminal` |
| `app_config` | key, value | Realtime channel `app-config`; drives feature flags like `sms_dispatch_enabled`; auto-boots on `db.client` ready |
| `notification_deliveries` | channel, status (sent/suppressed/rate_limited/failed), sent_at | Read-only from client (delivery stats panel, 7-day window, limit 5000 rows) |
| `cached_prices` | ticker, price, prev_close, change_pct | Pre-seed table written by broadcaster; read by `seedFromCachedPrices()` |
| `gex_snapshots` | ticker, snap_date, spot, gamma_flip, gamma_flip_confidence, call_wall, put_support, hvl, net_gex, regime, strike_data (JSONB array `[{s,c,p,t,g}]`) | Read by `loadGexSnapshot()`; ordered by snap_date desc, limit 1 |
| `access_codes` | id, user_id, is_active | Gate: `is_active=true, limit 1`; `beta_codes` is a legacy view bridging old name |
| `user_onboarding` | user_id, learning_completed_at | Gate: course completion |

**Total named tables: 18** (user_alert_preferences, user_alerts, user_notified_hits, user_alert_channel_prefs, trader_profiles, alert_templates, signals, performance, broadcast, app_settings, app_config, notification_deliveries, cached_prices, gex_snapshots, access_codes, user_onboarding + implied `push_subscriptions` stored server-side by push-subscribe function).

### 8.3 Realtime Channels

| Channel name | Schema | Tables | Events |
|---|---|---|---|
| `oracle-terminal` | public | signals, performance, broadcast, app_settings | `*` |
| `app-config` | public | app_config | `*` |
| `user-alerts-{uid}` | public | user_alerts | `UPDATE` only, filter `user_id=eq.{uid}` |
| `price-feed` | — | Broadcast (not Postgres) | broadcast events: `price`, `option-price` |
| `subscription-requests` | — | Broadcast, private (RLS: `is_active_member()`) | relay subscribe/unsubscribe requests |

### 8.4 Supabase Client Configuration (price-subscription.js:776–791)
- Dedicated `_priceClient` for price feed: `auth: { persistSession: false, autoRefreshToken: false }`
- `realtime: { params: { eventsPerSecond: 500 }, timeout: 30000 }`
- Reason: prevents token rotation race on iOS webviews; the price feed channel is public broadcast, no auth needed

### 8.5 Fetch / Auth Helpers (supabase.js)
- `db.select(table, params)` — GET with boot gate check
- `db.insert(table, row)` — POST
- `db.upsert(table, row)` — POST with `Prefer: resolution=merge-duplicates`
- `db.del(table, id)` — DELETE by `id=eq.{id}`
- `db.rpc(name, args)` — POST to `/rpc/{name}`
- `FETCH_TIMEOUT_MS: 15000` — all fetch calls abort after 15 s
- `SESSION_READ_TIMEOUT_MS: 10000` — `getSession()` timeout
- Auth retry on 429: `_priceBackoff[upper] = Date.now() + 60000`
- Telemetry beacon: `/.netlify/functions/client-telemetry` (sendBeacon, non-blocking)
- Session loss → `auth:sessionLost` event → 1.5 s delay → `refreshSession()` (12 s timeout) → if transient keep session, if auth error purge localStorage `sb-*-auth-token` keys → redirect `/login.html?msg=session_expired`

---

## 9. WebSocket / Price Relay

### 9.1 Price Transport Architecture (price-subscription.js v3, 2026-06-12)

**Primary**: Direct WebSocket to Railway relay
- **Default URL**: `wss://momoedge-price-relay-production.up.railway.app/ws`
- Auth: `?token=<supabase-access-token>` query param
- Relay rejection code `4401` = bad JWT; retry with fresh token on next backoff
- Relay wire protocol frames: `{ event: 'hello'|'price'|'option-price'|'pong', payload }`
- Payload shapes identical to Supabase broadcasts — shared handlers `handlePriceBroadcast` / `handleOptionBroadcast`
- Config override: `config.RELAY_WS_URLS` array (add more relay endpoints)

**Fallback**: Supabase Realtime broadcast channel `price-feed`

**Degradation chain**: relay WS → Supabase Realtime → REST polling (every 60 s)

### 9.2 Relay Transport Tuning Constants
```
RELAY_BACKOFF_MIN_MS:              1000
RELAY_BACKOFF_MAX_MS:              30000
RELAY_FAILURES_BEFORE_FALLBACK:    3      (consecutive failed connects on ALL sockets)
RELAY_MAX_CYCLES_BEFORE_FALLBACK:  6      (health-check stale cycles)
RELAY_RETRY_WHILE_FALLBACK_MS:     180000 (probe relay every 3 min while in Supabase fallback)
HIDDEN_SUSPEND_MS:                 60000  (close sockets after 60 s hidden; resume on visibility)
```

### 9.3 Supabase Realtime Price Feed Channel
- Channel name: `price-feed`
- Events: `broadcast` with event `price` and event `option-price`
- `CHANNEL_JOIN_TIMEOUT_MS: 30000`; `STALE_THRESHOLD_MS: 60000`; `HEALTH_CHECK_INTERVAL: 15000`
- Circuit breaker: `MAX_REBUILDS_PER_SESSION: 20`

### 9.4 Subscription Request Channel
- Channel name: `subscription-requests` (private, RLS `is_active_member()`)
- Message format: `{ type: 'broadcast', event: 'subscribe'|'unsubscribe', payload: { ticker: 'AAPL' } }`
- Dedup: `RELAY_REQUEST_MIN_INTERVAL_MS: 3000` per ticker per action
- Auth denial handling: `RELAY_MAX_AUTH_ERRORS: 3` CHANNEL_ERROR → give up for session; backoff = `RELAY_ERROR_BACKOFF_MS (2000) * attempt#`

### 9.5 Legacy WS Message Protocol (websocket.js — direct Polygon WS path, now disabled in favor of relay)
Subscribe: `{ action: 'subscribe', params: 'A.AAPL' }` (equities), `'CA.EURUSD,C.EURUSD'` (forex), `'XA.BTCUSD,XT.BTCUSD'` (crypto)
Unsubscribe: same with `action: 'unsubscribe'`
Message events handled: `T` (trade), `XT` (crypto trade), `C` (forex quote), `AM`/`A` (aggregate/second agg), `CA`/`XA` (forex/crypto agg)
Price extraction: `msg.c || msg.p || msg.bp` for aggregates; `msg.p || msg.bp || msg.ap` for trades

### 9.6 REST Price Fallback Endpoints
- Single: `/.netlify/functions/price?symbol=<mapped>`; returns `{ price, prevClose, changePercent }`
- Batch: `/.netlify/functions/price-batch?symbols=<comma-list>`; returns `{ count, total, ms, results: { [sym]: { price, prevClose, changePercent } } }`
- Rate limit: HTTP 429 → backoff 60 s; fetch error → backoff 30 s
- Cache freshness gate: skip fetch if entry `time` < 30 s old AND not `_relayPlaceholderPct`
- Equity poll interval (market open, relay mode): **120,000 ms**; (default polling): **60,000 ms**
- Crypto/forex REST poll (market open): **30,000 ms**; (default): **20,000 ms**

### 9.7 PRICE_CACHE Structure
```js
PRICE_CACHE[ticker] = {
  price, change, changePercent, _pc (prev close),
  time (epoch ms), _tickDir ('up'|'down'|null),
  _spark (array, last 30 ticks), volume, source ('realtime'|'rest'),
  _relayPlaceholderPct (bool), _fromCache (bool, from cached_prices table)
}
```
- Eviction sweep every `EVICT_SWEEP_INTERVAL_MS: 300000 (5 min)`; max age `EVICT_MAX_AGE_MS: 1800000 (30 min)`
- Active symbols not evicted; aliases and futures mappings share cache entries

### 9.8 Symbol Map (price-subscription.js / websocket.js)
Futures aliases (e.g. `ES → SPY`, `NQ → QQQ`, `GC → GLD`, `CL → USO`, `ZB → TLT`), crypto (`BTC → X:BTCUSD`), forex (`EURUSD → C:EURUSD`), options (`O:` prefix for OCC symbols).

### 9.9 Option Mark Cache (OPT_MARK_CACHE)
`OPT_MARK_CACHE[occ] = { mark, prevMark, time }` — separate from PRICE_CACHE. Fed by `batchFetchOptionMarks()` and relay `option-price` events. Dispatches `optMarkUpdate` CustomEvent. Batch capped at **50 OCC symbols**.

---

## 10. Price-Subscription Module Public API

`window.MomoEdge.priceSubscription`:
- `init()` — boots transport, idempotent
- `subscribe(tickers)` — add to watch list
- `unsubscribe(tickers)` — remove from watch list
- `getPrice(ticker)` — cache lookup
- `getPriceCache()` — full cache reference
- `getStatus()` — `'live'|'reconnecting'|'polling'`
- `getDiagnostics()` — full diagnostic object (transport, relay sockets, lastBroadcastAgo, etc.)

---

## 11. Mode-Toggle Routing (mode-toggle.js)

### 11.1 Modes
```js
var _currentMode = 'oracle';  // always starts on oracle regardless of localStorage
```
Five top-level modes, each with its own layout:
- **oracle** — signal cards left, analysis center, oracle right; tabs: `analysis`, `history`
- **research** — Flow V2 three-pane (left: flow summary, center: Flow V2/V1, right: GEX widget + catalyst alerts + live flow)
- **heatmap** — React heatmap widget (`refreshInterval: 30000`)
- **gex** — GEX terminal as iframe (`/gex.html?ticker=`), flat-scroll height bridge via postMessage
- **prism** — PRISM (strike × expiry matrix) as iframe (`/heatseeker.html?embed=1&flat=1&ticker=`), same height bridge

### 11.2 Mode Switch Persistence
`localStorage.setItem('momoedge_mode', mode)` — but overridden to `oracle` on every fresh load (line 9).

### 11.3 Iframe Protocol (postMessage)
All iframes exchange messages with `location.origin` as target origin.

**GEX frame messages received from iframe**:
- `{ source: 'gexFrame', kind: 'ready' }` → pause if not gex mode
- `{ source: 'gexFrame', kind: 'struct', struct, ticker, expiry }` → writes `STRUCT_CACHE[ticker]` + fires `gex-cache-update`
- `{ source: 'gexFrame', kind: 'height', height }` → resizes iframe
- `{ source: 'gexFrame', ticker }` → syncs `STRUCT_ACTIVE_TICKER`

**GEX frame messages sent to iframe**:
- `{ target: 'gexFrame', ticker }` — ticker change
- `{ target: 'gexFrame', kind: 'pause'|'resume' }` — freeze audit
- `{ target: 'gexFrame', kind: 'parentScroll' }` — scroll bridge

**PRISM frame**: same pattern with `source/target: 'prismFrame'`; also `kind: 'toggleGuide'` from mode bar.

### 11.4 Flow View V2 Lazy Loading
Flow V2 assets (`flow-inspector.js`, `flow-view-v2.js`, `flow-v2.css`) loaded on first activation. SW precache keeps them available. Toggle off: `localStorage.setItem('flow_v2', '0')`.

### 11.5 Heatmap Lazy Loading
React 18.2.0 + ReactDOM loaded from jsdelivr CDN on first activation. Widget in `js/heatmap-widget.js`. `window.HeatmapModule.default` component with `{ watchlist: null, refreshInterval: 30000 }`.

### 11.6 Research Right Panel Timers
- Live flow feed refresh: **30,000 ms** interval
- Radar strip refresh: **30,000 ms** interval
- Notable flow filter: `score ≥ 60 AND premium ≥ $500,000`
- Radar strip: top 12 tickers by premium (excluding RADAR_EXCLUSIONS), animation duration `max(20, count * 4) s`

---

## 12. Access / Entitlement Gate (access-gate.js)

### 12.1 Two-Gate Model
- **ENTRY gate**: `hasClaimedCode` (row in `access_codes` with `is_active=true`) OR `isBypassed` → determines checkout vs. waitlist for non-subscribers
- **ENTITLEMENT gate**: `hasActiveSub` → determines terminal access vs. checkout

### 12.2 Subscription Status Classes
```js
COMP_STATUSES   = ['moderator']                          // comp access; no Stripe required
STRIPE_STATUSES = ['active', 'trialing', 'past_due']    // real Stripe subscription required
```
`is_admin` also bypasses all gates.

`'founding'` and `'beta'` are pricing labels (wave-based), NOT access tiers (amended MOM-403, 2026-06-15).

### 12.3 `decideAccess()` Decision Matrix
Input: `{ session, profile, hasClaimedCode, courseCompleted, waitlistEnabled, ctx: { surface, loginDest } }`

| Condition | Verdict | Destination/Modal |
|-----------|---------|------------------|
| No session | reject | `/login.html` |
| Bypassed or active sub + no terms | grant | modal: `terms` |
| Active sub (non-bypass) + course not complete + surface=terminal | grant | modal: `required_course` |
| Active sub (non-bypass) + course not complete + other surface | redirect | `/learning.html` |
| Active sub + all checks pass | grant | — |
| `unpaid` status + surface=terminal | grant | modal: `unpaid` (grace) |
| oracle-entry surface + hasClaimedCode | grant | — (entry gate only) |
| hasClaimedCode OR waitlistEnabled=false | redirect | `/checkout.html` |
| Unclaimed + waitlistEnabled=true | redirect | `/waitlist-confirmation.html` |

### 12.4 fetchGateInputs() Reads (3 parallel queries)
1. `trader_profiles` — `is_admin, subscription_status, stripe_subscription_id, terms_accepted_at`
2. `access_codes` — `id` where `user_id=eq AND is_active=true LIMIT 1`
3. `user_onboarding` — `learning_completed_at` (fail-open: error → courseCompleted=true)

### 12.5 Error Classification
- `classifyError(err)`: matches `/jwt|invalid_grant|unauthor|forbidden|401|403|bad_jwt|token|no_session/i` → `'auth'`; everything else → `'transient'`
- Auth error → `purgeSession()` (removes `sb-*-auth-token` localStorage keys) + redirect `/login.html?reason=auth`
- Transient error → call `opts.onTransient` hook, do not purge

### 12.6 Session Access Keys
- `localStorage.setItem('momoedge_access_verified', 'true')` on grant
- `localStorage.removeItem('momoedge_signed_out')` + `momoedge_oauth_choice` on grant

---

## 13. app-config Module (app-config.js)

- Loads `app_config` table (key/value) on boot; auto-retries every 100 ms until `db.client` ready (max 100 attempts = 10 s)
- Realtime: Supabase channel `app-config` watches `postgres_changes event=* table=app_config`; fires registered onChange callbacks
- `ac.isSmsEnabled()` → `ac.get('sms_dispatch_enabled') === true`
- `ac.onChange(key, callback)` → returns unsubscribe function

---

## 14. Netlify Functions Referenced

| Path | Method | Purpose |
|------|--------|---------|
| `/.netlify/functions/price` | GET `?symbol=` | Single price lookup |
| `/.netlify/functions/price-batch` | GET `?symbols=` | Batch price lookup (equities + options via `O:` prefix) |
| `/.netlify/functions/uw-flow` | — | Unusual whales flow data |
| `/.netlify/functions/uw-chain` | — | Unusual whales chain data |
| `/.netlify/functions/technical` | — | Technical analysis |
| `/.netlify/functions/push-subscribe` | POST/DELETE | Store/remove push subscription |
| `/.netlify/functions/push-send` | — | Server-side push dispatch |
| `/.netlify/functions/client-telemetry` | POST (beacon) | Auth/session telemetry |

### Supabase Edge Functions Referenced
| Name | Invoked via |
|------|------------|
| `phone-verify-send` | `sb.functions.invoke('phone-verify-send', { body: { phone_e164 } })` |
| `phone-verify-check` | `sb.functions.invoke('phone-verify-check', { body: { phone_e164, code } })` or `{ body: { remove: true } }` |

---

## 15. Key Business Logic Constants (config.js)

```js
PREMIUM_STANDARD:       300000   // $300K — premium threshold for "standard" flow
PREMIUM_CLUSTER:        100000   // $100K — cluster threshold
CLUSTER_RULES:          ['RepeatedHits', 'AscendingFill']
SCORE_GRADE_THRESHOLDS: { WHALE: 90, INSTITUTIONAL: 80, HIGH_CONVICTION: 70, MODERATE: 60, LOW: 50 }
CONFIDENCE_CEILING:     92       // max displayed confidence %
DEDUP_WINDOW_MS:        1800000  // 30 min flow dedup window
FLOW_RETENTION_DAYS:    7
STRUCT_CACHE_TTL_MS:    120000   // 2 min GEX struct cache TTL
MARKET_OPEN_MINS:       570      // 9:30 AM ET
MARKET_CLOSE_MINS:      975      // 4:15 PM ET
```

Flow dedup key: `ticker + '_' + strike + '_' + type[0] + '_' + timestamp + '_' + contracts + '_' + round(premium)`

---

## 16. Alert-Renderer Module (alert-renderer.js)

`window.MomoEdge.alertRenderer`:
- `loadTemplates()` — loads `alert_templates` table (active, en-US locale; highest version wins per alert_type+channel key)
- `renderAlertMessage(alertRow, channel)` — priority: (1) template rendered from `alertRow.data`, (2) `alertRow.message` string, (3) template with empty vars
- `renderTemplate(alertType, channel, vars)` — Mustache `{{var}}` substitution
- `renderAlertParts(alertType, channel, vars)` → `{ title, body, severity }`
- Type bridging: `trigger_confirmed → trigger_conf`, `hit_t1/t2/t3 → target` etc. via `ALERT_TYPE_PREF_KEY` + `PREF_KEY_TO_MATRIX_AT`
- `state()` → `{ loaded, loading, templateCount, lastLoadAt }`
- Logged with tag `[MOM-288/289]`

---

*All server-side logic (push dispatch, SMS send, quiet-hours enforcement, score computation, flow scoring) is NOT in this client code and is inferred as server-side only.*
