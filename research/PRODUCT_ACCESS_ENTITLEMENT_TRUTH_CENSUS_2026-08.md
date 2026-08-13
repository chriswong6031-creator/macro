# Product Access and Entitlement Truth Census — 2026-08

**Audit date:** 2026-08-11

**Status:** decision-ready technical census; no access, price, Stripe, Prophet-scoring, or UI behavior changed
**Launch verdict:** **BLOCKED on access integrity.** The existing billing and entitlement spine is reusable, but current public delivery exposes paid bytes through anonymous HTML, the GitHub Pages mirror, public R2, and public Git history. Turning on the global paywall before those alternate paths are closed would create a paywall that is both bypassable and likely to false-lock legitimate users.

The governing commercial rule is: **the page is discoverable; the proprietary payload is paid.** The smallest correct program is to finish the existing public-shell/split-payload pattern, not to add another access framework.

## Executive findings

1. **The primary origin is not the largest leak.** Anonymous requests to protected JSON on `mastermind-x.com` currently fail with `401`, but the same or richer artifacts return `200` from GitHub Pages, public R2, or raw public Git. A green primary-domain probe is therefore not an access attestation.
2. **US Stocks/Prophet is visually capped, not byte-gated.** `tier_preview.js` hides rows after they are delivered. The live anonymous document was 1,133,777 bytes and contained 70 Prophet cards plus an inline full stock-table data block. This directly violates the repository's own rule that paid bytes must differ.
3. **Free is not a stable entitlement boundary under the repository/documented staged-off setting.** `PAYWALL_ENABLED=0` allows a signed-in user through ordinary `premium` paths. Only `premium.enforced_early`, explicitly `always=True` APIs, and independent tier gates enforce paid access in that mode. The production environment value was not read, so production Free behavior remains a live unknown.
4. **Current plan config is the best catalog authority, but product copy is contradictory.** Essential is `$99` monthly or `$900` annual with no trial; Pro is `$149` monthly or `$1,308` annual with a seven-day trial; Founding Pro is a Pro entitlement at `$900` annual. The landing, Plans page, Research API, Terminal, and older Insider masterplan disagree about what those prices unlock.
5. **`unlimited` is an operator overlay, not a customer tier, and it is inconsistent.** `/api/me` may display `unlimited`, and the Pro-host gate honors the same allowlist, but the main static paywall and Research Vault do not. An operator can therefore be shown as Unlimited and still be denied.
6. **Mastermind Bot is a whole-host Pro gate over an internally open read application.** That topology can be valid for a Pro-only tool, but it cannot express a public preview, Free, or Essential. Its legacy account endpoint is unmounted and non-authoritative.
7. **The public Prophet proof is winner-selected, not a proof board.** `prophet/showcase.json` explicitly says “selected because they worked”; it has no outcome/receipt fields and does not include representative losses. It cannot satisfy the CEO proof contract.
8. **No production Stripe objects or customer rows were inspected or mutated.** Config and reducers establish expected behavior, not live Stripe parity. Authenticated live behavior remains unverified for Free, Essential, Pro, trial, Founding Pro, and operator accounts.

## Scope, authority, and evidence method

### Frozen inputs

| Input | Revision or digest |
|---|---|
| Macro | `origin/main` at `597d95de3ce7e23578800cc21a08758413ac1abd` |
| Terminal | `origin/master` at `32f4254f11d3abc26ad891bbb14e4395b0ec6e82` |
| Mastermind | `origin/master` at `f268fd8acf6fc462a3f82a8bdca4482979f5446e` |
| Handoff A | SHA-256 `c7f42f1e4e33b5d73bd42c2f80e8e9e12e70e0f54383438ffd2c14e95b077c2b` |
| Access ruling | SHA-256 `c4297c5b30be3b255b269fbbc71772b5f4f69938e069885c0edc873f0eb3f9fe` |
| Prophet ruling | SHA-256 `ea3b8a123ab79a73f3fa48117edb513c2bcf3a1e509c38837fbe232a89ffe433` |
| Execution docket | SHA-256 `f0002f199208a7215479f16654e612aa845e9a56ed4babecdeba8f59f2d95d3b` |

The downloaded ruling packet is not Git-anchored, so its digest is part of this receipt. The CEO ruling is the intended product contract. Current server code, config, generated artifacts, tests, and live responses describe actual enforcement; copy does not.

### Evidence keys

| Key | Kind | Evidence |
|---|---|---|
| `R1` | Ruling | Access ruling lines 9-24, 68-159, 191-315, 408-442 in the digested external packet |
| `R2` | Ruling | Prophet ruling lines 143-203 in the digested external packet |
| `M1` | Source | `config/plans.yml:1-13,17-40,42-136` — catalog, prices, trials, features, indicator-display counts, legacy mappings, Founding offer |
| `M2` | Source | `config/site_access.yml:1-30,249-273,360-453` — broad HTML-open rule, explicit hard denies, public assets, staged wall, early payloads |
| `M3` | Source | `app/paywall.py:77-105,144-159,171-215,242-318,349-386,390-440,507-582` — classification, caches, feature checks, global switch, operator/Pro-host logic |
| `M4` | Source | `app/billing.py:634-667,711-724,781-818`; `app/main.py:760-855,1573-1592` — account authority, reducer, invalidation, portfolio gate |
| `M5` | Source/generated | `templates/tier_preview.js:1-27,68-107,187-307`; `templates/dashboard.html.j2:15609-15642`; generated `site/us_stocks.html` |
| `M6` | Source | `app/research.py:1-30,62-68,219-301` — public three-summary preview, Pro-only catalog/PDF gate |
| `M7` | Source | `app/deploy/Caddyfile:285-377,379-489,649-682,684-745` — static routing, open HTML, Terminal data, Bot host |
| `M8` | Source/live | `.github/workflows/pages.yml:1-13,99-103`; GitHub Pages live probes — whole `site/` mirror |
| `M9` | Source/live | `templates/data_base.js:1-35`; `scripts/publish_r2.py:69-108`; public R2 live probes |
| `M10` | Copy/source | `templates/plans.html.j2:397-510,530-658`; `templates/index.html:690-839`; old `research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md:1-20,80-138,169-180` |
| `M11` | Test | `tests/test_paywall.py:38-207`; `docs/TIER_PREVIEW_PATTERN.md:18-54,121-142,166-173`; `docs/ops/site-access.md:43-85,108-130` |
| `M12` | Generated schema census | Union of 176 tracked `site/prophet/plans/*.json` objects — `prophet.trade_plan/v1` exact top-level and nested keys; values were not reproduced |
| `B1` | Source | Mastermind `app/auth.py:11-24,72-84,236-325`; `app/web.py:526-579,669-714,1225-1249,1282-1338,1608-1674` |
| `B2` | Source | Mastermind `app/main.py:79-104`; `app/account.py:31,58-98,170-200`; `app/static/account.js:155-180,212-218,335-345` |
| `B3` | Source | Mastermind `bridge/macro_snapshot.py:33-54,88-158`; `bridge/nw_feedback.py:1-49,63-68,578-613`; `scripts/export_macro_snapshot.py:33-48,150-284` |
| `B4` | Source | Mastermind `portfolio/prophet_feed.py:1-34,64-120,255-379`; `portfolio/entry_engine.py:160-165,341-343,379-388`; `portfolio/conviction.py:418-463,530-591` |
| `T1` | Source/test | Terminal `lib/subscriptionTier.ts:1-29`; `lib/entitlement.ts:7-45,67-83,97-193`; `lib/useEntitlement.ts:5-48`; entitlement and tier tests — tier, feature, operator, and cache authority |
| `T2` | Source/live | Terminal `lib/upstreams.ts:8-15`; `lib/flowSource.ts:241-308,935-977`; anonymous public-R2 probes at `2026-08-11T21:27:33Z` — paid Options/Prophet origin bypass |
| `T3` | Source/live | Terminal `lib/pine.ts:1-35`; `components/ChartPanel.tsx:1,36,2248-2268`; Scripts page/editor; deployed anonymous Next chunk at `2026-08-11T21:28:31Z` — proprietary Pine delivery |
| `T4` | Source/test | Terminal `lib/suites/registry.ts:46-118`; `components/IndicatorsModal.tsx:37-72,460-525`; `components/TerminalShell.tsx:349-364,596-615,1006-1070,1887-1901,1982-2034,2085-2155`; 11 focused Vitest files / 145 tests — capability counts and watchlist behavior |
| `T5` | Source | Terminal `lib/useEntitlement.ts:23-48`; `components/settings/SettingsPanel.tsx:142-160`; onboarding `plans.ts:1-29`, `OnboardingSheet.tsx:117-124,195-209,303-320`, `StepDone.tsx:62-69` — Terminal offers and post-checkout refresh |
| `T6` | Source/test | Terminal `app/api/alerts/route.ts:17-26,49-103`; `components/AlertsView.tsx:250-265,326-335`; suite-alert registry/tests — account alert types and tiered suite events |
| `L1` | Live | Anonymous probes at `2026-08-11T21:17:34Z`, summarized below |

`S` below means source-declared actual behavior. `T` means test-pinned behavior. `L` means live-observed behavior. Authenticated states without test accounts remain `S/T, live unknown`.

## 1. Canonical current-state matrix

Cell grammar is `I` intended; `A` actual; `E` enforcement; `Ev` evidence; `Δ` discrepancy. “Same as Pro” still names the enforcement and evidence; it is not a separate entitlement implementation.

### Discovery, dashboards, and Prophet

| Capability | Anonymous | Free | Essential | Pro | Trial Essential | Trial Pro | Founding Pro | Unlimited/operator |
|---|---|---|---|---|---|---|---|---|
| Public HTML shells and navigation | I public. A the broad `*.html` matcher serves documents except explicit hard-deny routes such as Committee; some required assets may still lock. E Caddy open-HTML/hard-deny + IP gate. Ev M2,M7,L1. Δ over-broad and not byte-audited. | I public + identity. A same reachable shell bytes; hard-deny routes stay absent. E Caddy. Ev M2,M7. Δ assets vary. | I public shell. A same; hard denies do not become paid routes. E Caddy. Ev M2,M7. Δ sold Committee conflicts. | I public shell. A same. E Caddy. Ev M2,M7. Δ hard-denied sold surface. | I N/A. A any manually-created user sees the same reachable shells. E Caddy. Ev M1,M7. Δ state is not sold. | I same as Pro. A same reachable shells. E Caddy. Ev M1,M7. Δ none. | I same as Pro. A same reachable shells. E Caddy. Ev M1,M7. Δ none. | I private operator overlay. A same shell/hard-deny result. E Caddy. Ev M3,M7. Δ overlay is irrelevant to shell. |
| Broad context, basic charts, public facts | I public. A many pages and live context public; raw heavy stores also public. E allowlist + R2. Ev R1,M2,M9. Δ R2 mixes ordinary facts with proprietary fields. | I same + saved state. A same public data. E same. Ev R1,M2,M9. Δ field boundary absent. | I full current context. A full HTML; ordinary premium assets depend on staged wall. E Caddy/paywall. Ev M2,M3. Δ source-only authenticated proof. | I same + depth. A as Essential. E same. Ev M2,M3. Δ source-only proof. | I N/A. A same public context. E public routes. Ev M1-M3. Δ not sold. | I Pro during trial. A public context plus any registered staged paths. E regwall/paywall. Ev M1,M3. Δ trial does not distinguish ordinary staged assets. | I Pro. A same. E Pro entitlement. Ev M1,M3. Δ none at catalog level. | I operator access. A public context; main wall may still deny protected assets. E inconsistent allowlist/row gates. Ev M3,M4. Δ false-lockout risk. |
| Ranked-list previews | I one approved item. A UI shows one, but full rows are in HTML. E client `tier_preview.js`. Ev R1,M5,L1. Δ **critical client-only leak**. | I three. A UI shows three, full rows remain in HTML. E client + `/api/me` hint. Ev R1,M5. Δ **critical leak**; live Free unknown. | I full. A full bytes/UI. E client tier hint; server not needed. Ev M5. Δ entitlement is cosmetic. | I full. A full bytes/UI. E client tier hint. Ev M5. Δ entitlement is cosmetic. | I N/A. A `trialing essential` would visually count as paid if `/api/me` returns Essential. E client tier name. Ev M5. Δ unsupported state. | I full. A visually full when tier resolves Pro. E `/api/me` + client. Ev M4,M5. Δ full bytes predate check. | I full. A Pro tier, visually full. E Pro row + client. Ev M1,M5. Δ full bytes predate check. | I full. A visually full if `/api/me` overlays Unlimited. E client. Ev M4,M5. Δ may disagree with server payload gates. |
| Complete current dashboards and premium rows | I no. A full HTML wherever rendered inline; anonymous protected JSON is `401` on primary domain, but mirrors bypass. E regwall/paywall only for non-HTML. Ev R1,M2,M7-M9,L1. Δ **critical**. | I no beyond previews. A(S/T) ordinary premium static/API paths stage open when registered under the documented/default `PAYWALL_ENABLED=0`; early paths deny. Production live unknown. E switch exception. Ev M2,M3,M11. Δ **critical Free over-access in staged mode**. | I yes. A early payloads allow with active/trialing `site_full`; ordinary paths are open in staged mode. E feature check or switch-off. Ev M1-M3,M11. Δ live auth unknown. | I yes. A same site access as Essential. E same `site_full`. Ev M1-M3. Δ site content does not distinguish Pro. | I N/A. A a manually-created active/trialing Essential row with `site_full` would pass early gates. E status+feature. Ev M3. Δ unsupported but technically accepted. | I yes. A passes `site_full`; ordinary paths stage open under the default setting. E status+feature. Ev M1,M3,M11. Δ live auth unknown. | I yes. A identical to Pro row. E Pro `site_full`. Ev M1,M3. Δ none at catalog level. | I yes privately. A may be denied because main paywall ignores email allowlist. E entitlement row only. Ev M3,M4. Δ **false lockout**. |
| Current Prophet board | I one partial card. A UI cap one; live HTML held 70 cards plus full inline table. E client only. Ev R1,R2,M5,L1. Δ **critical**. | I three cards. A UI cap three; same full document. E client only. Ev R1,M5. Δ **critical**. | I full board/plans. A full document; raw primary paths protected from anon but not early-gated for Free. E staged paywall. Ev R1,M2,M3. Δ server split absent. | I full. A same as Essential. E same `site_full`. Ev M1-M3. Δ no Pro distinction intended here. | I unresolved/N/A. A a row would get paid visual treatment and trial quotas. E mixed tier/status rules. Ev M1,M3,M5. Δ operator ruling required. | I full. A paid visual treatment; main raw access source-allowed. E `trialing` + feature. Ev M1,M3. Δ live auth unknown. | I full. A exact Pro. E Pro row. Ev M1,M3. Δ none. | I full. A visual full, raw paths may deny. E inconsistent overlay/row. Ev M3,M4. Δ false lockout. |
| Prophet exact plans and raw index | I withheld. A primary domain anon `401`; Pages `200`; R2 stock payload exposes plan-like geometry. E primary regwall only. Ev R1,R2,M7-M9,L1. Δ **critical alternate-origin leak**. | I withheld. A(S/T) ordinary paths stage open after registration under the documented/default switch; production live unknown; Pages/R2 public regardless. E paywall off except early. Ev M2,M3,M8,M9. Δ **critical**. | I complete. A primary source logic permits; Pages also bypasses. E `site_full` only when global wall armed. Ev M2,M3,L1. Δ live auth unknown. | I complete. A same. E same. Ev M2,M3. Δ none by target. | I N/A. A potential access if row has feature. E feature/status. Ev M3. Δ unresolved. | I complete. A source permits. E feature/status. Ev M1,M3. Δ live unknown. | I complete. A Pro. E same. Ev M1,M3. Δ none. | I complete privately. A Pages/R2 public regardless; primary may deny. E inconsistent. Ev M3,M4,M8,M9. Δ false lockout plus public bypass. |
| Prophet delayed proof / track record | I delayed, timestamped, wins and losses, receipts. A public `delayed_winners` payload, 12 cards, winner-selected, no outcome/receipt fields. E public allowlist. Ev R1,R2,M2,L1. Δ **not a proof board**. | I same. A same. E public. Ev R1,R2,M2. Δ same. | I public proof + paid history. A public winners payload; full history path unclear. E mixed static. Ev R1,R2. Δ paid lifecycle/history mapping unknown. | I deeper history. A no single tiered contract found. E scattered. Ev R1,M6. Δ unknown. | I unresolved. A public proof only. E public. Ev R1,M2. Δ N/A. | I Pro. A public proof; paid history source behavior unknown. E scattered. Ev R1. Δ unknown. | I Pro. A same. E same. Ev R1. Δ unknown. | I operator. A same public proof; private history depends on row. E scattered. Ev M3,M4. Δ inconsistent. |

### Workspace, research, AI, Terminal, and portfolio

| Capability | Anonymous | Free | Essential | Pro | Trial Essential | Trial Pro | Founding Pro | Unlimited/operator |
|---|---|---|---|---|---|---|---|---|
| Saved watchlists, preferences, layouts | I none. A guest named lists persist in browser localStorage; CSV import can add arbitrary symbols despite search-add signup gate. E client only. Ev R1,T4. Δ “create an account to build” is false. | I yes. A only Default list syncs to server/RLS; additional named lists remain local. E identity + RLS. Ev T4. Δ “synced across devices” overstates scope. | I multiple watchlists/alerts. A persistence is the same identity contract; no paid watchlist distinction. E identity + RLS. Ev R1,T4. Δ paid quantity/alert promise is not encoded. | I Essential + deeper workflow. A same persistence authority. E identity. Ev T4. Δ no paid-tier watchlist distinction. | I N/A. A identity persistence if account exists. E auth. Ev M1,T4. Δ unsupported state. | I Pro. A same persistence. E auth. Ev T4. Δ no trial-specific limit. | I Pro. A same. E auth. Ev M1,T4. Δ none. | I private operator. A same identity persistence. E auth. Ev M4,T4. Δ no customer-tier meaning. |
| Personalized alerts and notifications | I none beyond public context. A `/alerts` shows signup gate; no anonymous saved alert delivery. E Terminal identity gate. Ev R1,T6. Δ aligned. | I limited alerts. A four legacy plus eight server-evaluated Options alert types; no suite alerts. E account-authenticated Alerts API, with the eight Options types not requiring the paid Options feature. Ev T6. Δ product name implies a paid-data boundary that the alert evaluator does not use. | I multiple/standard alerts. A Free base types plus 16 accessible suite-alert event types. E client suite tier + authenticated API. Ev R1,T4,T6. Δ no estate-wide quantity/delivery contract. | I deeper alerts/automation. A Free base types plus all 24 suite-alert event types. E client tier + authenticated API. Ev R1,T4,T6. Δ automation remains unimplemented as a customer capability. | I N/A. A raw `essential` could get Essential events even if status is trialing because Terminal trusts upstream tier/features. E upstream contract. Ev T1,T6. Δ unsupported state. | I Pro trial. A same as Pro only if upstream emits `pro`; no distinct trial alert class. E upstream tier. Ev T1,T6. Δ expiry behavior is delegated upstream. | I Pro. A same as Pro when wire tier is `pro`; raw `founding_pro` gets Free behavior. E normalizer. Ev M1,T1,T6. Δ load-bearing representation. | I private operator. A Unlimited receives Pro suite events; explicit Issue Desk operator adds review access, not a customer notification tier. E tier + separate feature. Ev T1,T6. Δ customer and operator axes are conflated in UI. |
| Research catalog and PDFs | I selected delayed summaries, no PDFs. A latest three summaries/search public; PDFs denied. E Research API. Ev R1,M6. Δ broadly aligned. | I limited preview. A same three summaries. E Research API. Ev M6. Δ plans copy says one report, implementation says three summaries. | I standard intelligence, but premium archive is Pro target. A treated exactly like Free by Research API. E `_VIEW_TIERS={pro}`. Ev R1,M6. Δ Plans page falsely claims every report. | I full vault/PDFs. A full catalog/search/view/download for active/trialing Pro. E server tier/status gate. Ev R1,M6. Δ source-only live proof. | I N/A. A Essential trial would still be teaser-only. E tier+status. Ev M6. Δ unsupported. | I full Pro. A trialing Pro passes Research gate. E tier+status. Ev M6. Δ aligned. | I full Pro. A Pro passes. E tier+status. Ev M1,M6. Δ aligned. | I private operator, not customer tier. A an allowlist-only Unlimited value is not in `_VIEW_TIERS`; may deny. E Research row resolver. Ev M4,M6. Δ **false lockout**. |
| History, comparison, and export | I delayed representative proof only. A `/us_track_record.html` is fully anonymous; public winner showcase and separate public Bot snapshot expose mismatched history shapes. E static routing/public Git. Ev R1,R2,M2,B3. Δ no canonical proof/history boundary. | I limited saved/history views. A same public artifacts plus identity-local state; no shared history/export capability was found. E per-surface identity/static rules. Ev R1,M2,T4. Δ target limit is not encoded. | I standard/deeper product history. A full Prophet paths are `site_full`, but Research archive/export remains Pro and no common comparison/export feature exists. E scattered payload and API gates. Ev R1,M1,M3,M6. Δ one tier promise resolves differently by surface. | I deeper history/export. A Research PDF/download and Pro Bot access exist; Prophet/track-record/export still lack one capability contract. E Pro string/host gates. Ev R1,M3,M6,B1. Δ scattered authority. | I N/A. A inherits whatever a manually-created Essential row can reach. E scattered. Ev M3,M6. Δ unsupported. | I Pro. A Research accepts trialing Pro; other history surfaces have no trial-specific rule. E status/tier per API. Ev M6. Δ inconsistent lifecycle semantics. | I Pro. A same when represented as Pro. E same scattered gates. Ev M1,M3,M6. Δ no Founding-specific history behavior intended. | I private operator. A Bot may allow while Research/main paths deny. E allowlist versus tier row. Ev M3,M4,M6,B1. Δ false-lockout risk. |
| Fast AI | I none. A auth required. E Brain gateway. Ev R1,M10. Δ aligned. | I limited. A 5/week. E `config/brain.yml:103-140`. Ev M10. Δ aligned. | I standard. A 300/month. E quota config. Ev M10. Δ aligned. | I higher. A uncapped requests with 5M-token monthly backstop. E quota config. Ev M10. Δ old masterplan's 1,000/month is superseded. | I unresolved/N/A. A any `trialing` status uses generic trial 25 total. E status-first quota. Ev M10. Δ unsupported state. | I trial allowance. A 25 during trial, not Pro uncapped. E generic trial bucket. Ev M10. Δ must be stated in trial copy. | I Pro entitlement; during trial uses 25, then Pro uncapped. A same. E status-first quota. Ev M1,M10. Δ copy does not explain transition. | I private operator. A Unlimited overlay in Brain. E email allowlist. Ev M3,M4. Δ keep out of catalog. |
| Deep/Pro AI | I none. A none. E auth/quota. Ev R1,M10. Δ aligned. | I none. A zero. E quota config. Ev M10. Δ aligned. | I standard. A 10/month despite `chat_opus` absent from Essential features. E quota tier, not feature. Ev M1,M10. Δ feature catalog and actual lane rule disagree. | I frontier lane. A 150/month. E quota config. Ev M10. Δ aligned. | I unresolved/N/A. A generic trial gets 3. E status-first quota. Ev M10. Δ unsupported. | I limited trial. A 3 during trial. E trial bucket. Ev M10. Δ aligned if disclosed. | I Pro; 3 during trial, 150 active. A same. E status-first quota. Ev M1,M10. Δ transition under-disclosed. | I private operator. A allowlist behavior must be kept private. E Brain allowlist. Ev M3,M4. Δ not a plan. |
| Terminal core charting | I public. A public Terminal route returns `200`; all `/data/*` is public at Caddy. E no account gate. Ev R1,M7,L1. Δ payload classification still required. | I public + persistence. A public app plus auth state. E Terminal/UI. Ev R1,M7. Δ live Free unknown. | I core + paid features. A core same public app. E Terminal feature gates only. Ev R1,M1. Δ authenticated proof pending. | I same. A same core. E same. Ev R1,M1. Δ none. | I N/A. A same public core. E public. Ev M1,M7. Δ unsupported. | I same. A public core. E public. Ev M1,M7. Δ none. | I same. A same. E public. Ev M1,M7. Δ none. | I private overlay. A same public core. E public. Ev M7. Δ none. |
| Terminal indicators and live options | I no advanced/options premium. A guests have a three-concurrent-indicator cap and one Free suite module; all suite algorithms and paid inputs still ship client/public-origin. E client state plus route feature gate. Ev R1,T2-T4. Δ confidentiality is not enforced. | I Free indicator set, no live options. A registration removes the classic-study count cap: 22 picker entries/28 runtime keys plus one Free suite module; Options still needs feature. E client tier + `terminal_live_options`. Ev T1,T4. Δ “Free: 3 indicators” is false. | I Essential 15 advanced + live options. A 15 suite modules cumulative and 16 suite-alert types; Options only if feature is emitted. E tier plus `terminal_live_options`. Ev M1,T1,T4. Δ correct only if cross-repo feature contract holds. | I all 31 + live options. A all 31 modules/24 suite-alert types; Options still separately feature-gated. E tier + feature. Ev T1,T4. Δ Pro tier alone is insufficient. | I N/A. A raw tier `trial` normalizes Free; `status=trialing` is display-only unless upstream emits a paid tier/features. E upstream contract + Terminal normalizer. Ev T1,T4. Δ unsupported/ambiguous. | I Pro trial includes live options. A works only when `/api/me` emits `tier=pro` and the feature; no distinct trial class. E upstream tier/feature. Ev M1,T1,T5. Δ checkout/refetch can leave UI stale. | I exact Pro. A Pro only if upstream emits `pro`; raw `founding_pro` normalizes Free. E normalizer. Ev M1,T1. Δ cross-repo wire contract is load-bearing. | I private operator. A raw `unlimited` becomes Pro and automatically grants Issue Desk operator; explicit operator feature can pass its API even while Options UI is locked. E separate feature/tier checks. Ev M4,T1. Δ overgrant/inconsistent UI risk. |
| Pro portfolio brief / Bot desk | I none. A primary Bot host `403`; public Git snapshot leaks detailed portfolio state. E host gate + public Git bypass. Ev R1,B1,B3,L1. Δ **critical bypass**. | I none/basic summaries only. A Bot `403`; raw snapshot public. E same. Ev R1,B3,L1. Δ **critical bypass**. | I standard portfolio awareness; whether Bot is included is unruled. A Bot host denies because Pro floor. E Pro host gate. Ev R1,M3,M7. Δ operator classification required. | I advanced portfolio tooling. A Macro `/api/portfolio/brief` and Bot host admit active/trialing Pro. E server tier gates. Ev R1,M3,M4. Δ Bot app itself has no per-feature gates. | I N/A. A potential Macro brief denial unless tier Pro/unlimited. E tier/status. Ev M4. Δ unsupported. | I Pro. A trialing Pro passes brief and Bot. E status+Pro floor. Ev M3,M4. Δ source-only live proof. | I Pro. A same. E Pro row. Ev M1,M3,M4. Δ none. | I private operator. A Macro brief accepts `unlimited`; Bot honors allowlist. E two implementations. Ev M3,M4. Δ other main-site gates disagree. |
| Customer automation, external API, and privileged writes | I none. A public read endpoints exist; no anonymous customer mutation benefit was found. E per-route auth/write gates. Ev R1,M4,T1,B1. Δ public reads must still be field-classified. | I none beyond saved state and alert evaluation. A no customer automation/API entitlement feature found. E identity/per-route checks. Ev R1,M1,T1. Δ target boundary is not encoded. | I standard workflow, not autonomous issuance. A no Essential automation/API capability found. E feature catalog lacks one. Ev R1,M1. Δ promised future depth is undefined. | I automation and future approved APIs. A no dedicated Pro automation/API feature was found; Bot is a whole-host read tool and Issue Desk operator is not granted by Pro alone. E scattered Pro and operator checks. Ev R1,B1,T1. Δ target benefit is not implemented as a capability. | I N/A. A no distinct behavior. E upstream/per-route. Ev T1. Δ unsupported. | I Pro trial where sold. A no separate automation feature to inherit. E scattered. Ev M1,T1. Δ “full access” cannot name a missing capability. | I Pro. A same as Pro; no separate automation benefit. E same. Ev M1,T1. Δ none beyond missing contract. | I explicit private overlay only. A Terminal `unlimited` or `options_issue_desk_operator` can grant Issue Desk review/write; Executive workers separately deny push, cross-repo publication, portfolio mutation, deploy and billing. E feature/tier route checks + authority map. Ev T1,B4. Δ raw Unlimited may overgrant operator write authority. |
| Account/billing authority | I sign-in explanation only. A public modal assets, authenticated endpoints return `401`. E Supabase auth. Ev R1,M4,L1. Δ aligned. | I authoritative plan/status/features. A Macro `/api/me` and `/api/account` read entitlement row. E billing read. Ev R1,M4. Δ live unknown. | I same. A same row. E billing read. Ev M4. Δ source-only. | I same. A same. E billing read. Ev M4. Δ source-only. | I N/A. A a row would display trialing Essential. E billing row. Ev M4. Δ checkout cannot create it. | I explicit trial/renewal. A status and period available, exact UI proof unknown. E billing row. Ev M4. Δ live UX unverified. | I must say Pro at founding price. A tier is only `pro`; offer provenance is metadata/Stripe. E billing/catalog. Ev M1,M4. Δ account may not identify Founding rate. | I private operator. A `/api/me` overwrites tier; `/api/account` does not apply the same overlay. E divergent endpoints. Ev M4. Δ **account disagreement**. |

### What “actual” does not yet prove

- No Free, Essential, Pro, Trial Pro, Founding Pro, or operator production credentials were used. Authenticated cells are source/test conclusions, not live receipts.
- No production Stripe Product, Price, Promotion Code, Subscription, or Entitlement object was read. `config/plans.yml` is the expected catalog, not proof of remote object parity.
- The broad HTML-open matcher covers hundreds of generated pages except explicit hard denies. US Stocks was byte-inspected; every other page family still needs an automated locked-field/source scan before it can be declared safe.

## 2. P0 page-shell matrix

There is no ratified P0 route registry yet. The page-census packet names six reference families—Today, US Stocks/Prophet, detail, Macro, pricing, and account/onboarding—and the access ruling adds Terminal, research, support, and legal. The table below is the **provisional commercial P0 set** used for this audit. Ratifying the route list is an operator decision, not an excuse to leave these paths unclassified.

Live SEO receipts are authoritative for the deployed edge: at audit time `/` had no `X-Robots-Tag`; every other probed Macro HTML route below returned `X-Robots-Tag: noindex, noarchive`, including routes that the source Caddyfile groups as public funnel pages. Terminal returns `noindex,nofollow,noarchive` by source.

| P0 surface / route | Anonymous shell | Free shell | Premium payload | Static/raw alternate | API gate | Required assets | Redirect / interstitial | SEO / indexing | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Landing `/` and `/index.html` | `200`, meaningful public acquisition page | Same; auth changes CTAs/state | No single protected payload; page embeds a stale delayed-winners showcase | GitHub Pages republishes generated landing; embedded showcase is also in source | Public offer status plus auth/checkout APIs on action | `landing.css`, scene scripts, shared auth/account assets; public | No access redirect; signup/checkout opens modal or Terminal | `/` live indexable by header; `/index.html` classification public | Shell is valid, but pricing/benefit claims need reconciliation |
| Today `/start.html` | `200`; anonymous visual caps apply, but alert banner can silently disappear | Same document; UI may show three rows | Ranked/action depth is inline in generated HTML; per-ticker data fetched from heavy store | Pages has the document; R2 serves `stockdata/*` | `/api/me` only changes presentation; no byte gate | shared theme, `tier_preview.js`, `data_base.js`, stock/chart assets, and required `wh_banner.js`; the banner script is not public-classified | No access redirect; contextual client wall; denied banner fetch degrades silently | Live `noindex,noarchive` | **Fails Shape B** and shell dependency closure: split proprietary rows/data and make approved shell assets public |
| Macro `/macro.html` | `200` broad macro dashboard | Same document | No canonical premium split identified; generated page may carry full inline readings | Pages republishes it and associated public static | Shell has no entitlement check; nonpublic assets use regwall/paywall | shared theme/chart/live context assets | No access redirect | Live `noindex,noarchive` | Decide Shape A public-context fields versus paid interpretation, then byte-audit |
| US Stocks / Prophet `/us_stocks.html` | `200`; JS visually shows one | Same bytes; JS visually shows three | **Missing split.** Full current cards, names, rankings, buy-zone copy, and inline table ship in HTML | Pages returns full page; Pages exposes `/prophet/index.json` and plans; R2 exposes graded stock payloads | `/api/me` is presentation only; raw primary paths use regwall/paywall | `tier_preview.js`, `stocktable.js`, `data_base.js`, shared assets; all shell-critical assets public | Client upgrade wall; no server interstitial for shell | Live `noindex,noarchive` | **P0 blocker: full paid bytes are anonymous** |
| Stock / Prophet detail `/stock.html#<ticker>` | Generic shell `200`; data loads client-side | Same | `stockdata/<ticker>.json` contains proprietary classifications, scores and plan geometry | Main path `401` anon; public R2 returns `200`; GitHub Pages may omit heavy tree but public R2 is hardcoded | Static regwall/paywall on main only | `data_base.js`, chart/stock scripts, per-ticker JSON | Shell never redirects; missing/denied fetch degrades in-page | Live `noindex,noarchive` | **P0 blocker: public R2 bypass** |
| Research Vault `/research_vault.html` + `/research/*` | Shell and latest three summaries/search public | Same preview | Full catalog/search and PDF view/download are Pro-only private API/R2 | Pages carries shell/SEO teasers; no public PDF path found | `app/research.py` tier/status check; `402 paid_required` for non-Pro | `research_vault_app.js`, shared auth; public catalog API | Contextual in-page upgrade; no shell redirect | Live shell `noindex,noarchive`; `/research/*` source is intended SEO estate | Server PDF boundary is good; copy falsely promises Essential all reports |
| Special Situations `/special_situations.html` | Public preview shell | Same preview | `/premiumdata/special_situations.json`, `site_full`, early-enforced | GitHub Pages returns the complete 8,490,693-byte payload anonymously | Main regwall then early paywall | shell JS/CSS, shared auth, hydration code | Shell stays; payload denial leaves contextual wall | Live `noindex,noarchive` | Reference split is correct on main; **mirror nullifies it** |
| Terminal `https://app.mastermind-x.com/terminal` | `200` core app; guests get six-symbol preset and local watchlists | Same + authenticated Default-list persistence | Options/flow requires `terminal_live_options`; suites are 1 Free / 15 Essential cumulative / 31 Pro, but paid algorithms ship client-side | Caddy makes all `/data/*` public; Terminal directly reads public R2 Options/Prophet stores | Next API route feature checks for options/flow; client tier rules for suites | Next static chunks, `/data/manifest.json`, upstream R2 | `/` resolves to `/terminal`; gated actions show product lock, not whole-app redirect | `noindex,nofollow,noarchive` by Caddy | Public shell is correct; **data-origin and client-code confidentiality fail** |
| Plans `/plans.html` | `200` | Same; account may change CTA | Checkout/portal actions require authenticated billing APIs | Page itself is mirrored publicly as intended | Billing endpoints use auth; catalog renders from `config/plans.yml` | shared auth/account/onboarding assets | No access interstitial; checkout return flags in page | Live `noindex,noarchive` | Public route correct; claims/pricing presentation contradictory |
| Signup/signin/onboarding | No dedicated Macro document; public modal on existing shells; Terminal uses query state such as `?signup=1` | Authenticated user exits/changes modal state | None; subscription action invokes billing API | Public JS is expected; Supabase publishable key is intentionally public | Supabase auth, then billing API for checkout | `onboard.css`, `onboard.js`, `theme.js`, Supabase client | Modal/fallback `/?signup=1`; no generic protected-page redirect now | Inherits parent page; no standalone SEO route | Works as overlay; acceptance requires live expired-token and return-flow tests |
| Account and billing | Public modal code, no account data; `/api/account` and `/api/me` return `401` | Authoritative row intended | Customer portal, subscription actions, entitlement refresh | No customer artifact was found in targeted public-static scan | Macro auth + billing read/write; Mastermind's local account router is dead/unmounted | `account.js`, shared auth | In-page sign-in or account card; no standalone page | Inherits parent; not independently indexable | Use Macro broker only; fix Unlimited endpoint disagreement |
| Bot / portfolio `https://bot.mastermind-x.com/` | Whole-host `403` Pro interstitial; `/health` public | `403` | Entire app/read API is Pro/operator behind edge gate | Detailed portfolio snapshot is `401` on main but `200` in raw public Git | Caddy `/api/paywall/check_pro`; Mastermind GETs internally open | self-contained interstitial; Bot static app after allow | Server `403`; no preview shell | `noindex,nofollow,noarchive` | Decide whether Bot is Pro-only; **close raw snapshot bypass regardless** |
| Support `/support.html` and legal `/privacy.html`, `/terms.html`, `/disclaimer.html` | `200` | Same | None | Pages mirror acceptable for this public content | None beyond IP gate | shared theme/nav assets | No auth redirect | Live `noindex,noarchive` despite public acquisition/support purpose | Access good; SEO posture requires an explicit decision |

### Public-shell asset false lockout found outside provisional P0

`/biocatalyst.html` returns `200` anonymously under the broad HTML matcher, while its required `/biocatalyst.css` and `/biocatalyst.js` return `401` and are classified `free_registered` (`config/site_access.yml:394-402`). The anonymous “shell” is therefore unstyled/inert. This proves that a reachable HTML document does not establish anonymous shell usability. The same dependency check must run across every P0/P1 route before launch.

## 3. Prophet access matrix

| Prophet surface | CEO contract | Current primary-domain behavior | Alternate path / Terminal | Discrepancy and exact disposition |
|---|---|---|---|---|
| Anonymous current preview | One current card per chosen surface; allow only subject/ticker, stage, concise why-now, freshness, broad setup class; withhold full plan/book | `tier_preview.js` visually leaves one card, but the live HTML contained 70 cards, an inline `us-stocktable-data` board, scores and current state | GitHub Pages serves another full generated board | Replace server-rendered full board with a one-card public projection. Never derive the public projection by client deletion |
| Free current preview | Three coherent current cards per daily build; no full ranking/archive | Client cap becomes three after `/api/me`; underlying bytes remain full. Under documented/default staged mode, registered Free also passes ordinary premium paths; production live unknown | Pages and R2 remain public regardless of account | Create an authenticated Free-preview payload containing exactly three approved projections; early-enforce the paid remainder |
| Essential full board | Full current board, complete plans, filters, stages, evidence, lifecycle, alerts/history | HTML already contains much of the board for everyone; raw primary paths are ordinary premium, not early-enforced | Pages `/prophet/index.json` returned `200` and 622,923 bytes | Put full board behind `site_full` in `/premiumdata/` or a same-authority API, with `premium.enforced_early`; hydrate the public shell after fresh session resolution |
| Pro / Founding Pro full board | Same full Prophet product as Essential; Pro differentiates elsewhere | Same current full board; Founding is catalog tier `pro` | Same bypasses | Reuse the Essential payload feature. Do not invent a Prophet-Pro gate unless CEO changes the ruling |
| Exact plan object | Paid only; complete entry/stop/target/evidence withheld from public | Main `/prophet/plans/<id>.json` returned `401` anonymous. A representative plan includes trigger, entry, invalidation, targets, tranche, source engines, reliability, action steps, profit plan and internal score fields | GitHub Pages returns plan/index artifacts; public R2 stock payload exposes overlapping exact geometry | Move/serve complete plans only through authenticated paid transport; create a separately generated public field allowlist, never a denylist over the complete object |
| Live overlay `/live/prophet_live.json` | Paid current workflow | Anonymous returns `401`. Policy intentionally leaves it on premium default, but not `enforced_early`; signed-in Free is source-allowed under `PAYWALL_ENABLED=0`, while production live behavior is unknown | Terminal public R2 includes live option/Prophet upstreams; exact overlap needs schema comparison | Add to an early-enforced paid route or API before launch; verify Free `403`, Essential/Pro `200`, private no-store cache behavior |
| Raw index `/prophet/index.json` | Paid full board/history metadata | Anonymous returns `401`; signed-in Free source behavior is staged-open | GitHub Pages returned `200`; Terminal directly reads public R2 `prophet/index.json` | Close Pages and public R2 copies or publish a separately reduced display artifact |
| Per-ticker graded `stockdata/*` | Public ordinary facts may remain; proprietary scores, ranks, classifications and plan geometry paid | Main representative path returns `401` anon | Hardcoded public R2 returned `200`; sampled object contained score/rank/conviction and entry-zone/stop/action fields | Split facts from proprietary projection. Keep ordinary quote/company facts public; move graded fields behind authenticated gateway |
| Delayed proof `/prophet/showcase.json` | Delayed, timestamped origination, subsequent path, outcome, learning, receipts, wins and losses | Public `prophet.showcase/v2`, `kind=delayed_winners`, 12 cards, explicitly winner-selected, no outcome/receipt fields | Landing embeds an older copy and refreshes from public JSON | Replace with an append-only resolved proof projection that includes wins and losses and a visible delay; keep `authority_tier=display_only` |
| Track record and autopsies | Public representative resolved evidence; paid deeper history/export | `/us_track_record.html` is fully anonymous, while Plans describes a Free teaser and deeper paid access; no single access-controlled canonical track-record contract was found | Mastermind public snapshot separately exposes its own track record/reasoning through raw Git | Define one public proof schema and one paid history schema, then align the page claim/gate; do not mix portfolio snapshot proof with current paid Prophet payload |
| Terminal Prophet surfaces | Core chart may show public proof/context; current full Prophet/options surfaces follow paid contract | Terminal has server gates on its own option/flow routes, but its configured public R2 upstreams return complete Prophet/Options Prophet indexes anonymously | Direct R2 receipts in Terminal findings | Proxy protected upstreams through a user-authorized server route; expose only the approved display projection to anonymous/Free |

### Exact current plan-field census

The union below comes from all 176 tracked `site/prophet/plans/*.json` objects at the frozen Macro revision. Every object declares `schema=prophet.trade_plan/v1` and `authority_tier=display`. That authority label governs signal use; it is **not** a publication entitlement. The safe access default for the complete object is paid/private. A public preview may copy only explicitly approved fields into a separate schema.

| Field class | Exact current keys | Access disposition |
|---|---|---|
| Envelope / identity | `schema`, `id`, `asof`, `asset`, `direction`, `authority_tier` | Never publish the raw envelope. An approved projection may copy `asset`, a bounded direction/setup class, and freshness derived from `asof`; `id` must become a public receipt reference only for resolved proof |
| Dates / provenance | `signal_date`, `entry_date`, `recorded_at`, `formation_date`, `confirmed_date`, `observed_date`, `signal_date_basis`, `source_marker_date`, `price_basis_date`, `backfill_executed_at`, `origination_mode`, `selection_era`, `admission_class` | Paid by default. Public preview/proof may derive explicit freshness/delay and a receipt timestamp; never expose the full origination/provenance bundle by copying the plan |
| Narrative / evidence | `thesis`, `thesis_zh`, `source_engines`, `what_to_do_now`, `what_to_do_now_zh`, `management_ref`, `reliability.plan`, `reliability.option_premium` | Paid. Public `why_now` must be separately written/bounded; source-engine and management/reliability details stay out |
| Plan geometry / risk | `trigger`, `entry`, `invalidation`, `targets`, `horizon_days`, `min_hold_days`, `tranche`, `entry_status`, `profit_plan`, `profit_plan_zh` | Paid; forbidden in anonymous and Free current previews |
| Option contract | `option_contract.delta_approx`, `.entry_premium`, `.expiry`, `.freshness`, `.note`, `.right`, `.strike`, `.structure` | Paid; no contract geometry in public preview/proof |
| Entry basis | `entry_basis.basis_date`, `.basis_source`, `.era`, `.lag`, `.lag_basis`, `.max_lag`, `.run_asof`, `.signal_basis_date`, `.signal_lag_sessions`, `.state` | Paid evidence/provenance |
| Entry zone | `entry_zone.basis`, `.basis_zh`, `.chase_above`, `.conversion_class`, `.conversion_evidence`, `.conversion_evidence_zh`, `.converts_on_expiry`, `.era`, `.expiry_date`, `.expiry_sessions`, `.extension`, `.high`, `.leader_pullback`, `.low`, `.pct_from_entry`, `.price_basis_date`, `.schema`, `.stance`, `.zone_class` | Paid; contains exact geometry and plan-management state |
| Stage internals | `stage_tilt.basis`, `.bear_gate`, `.demoted`, `.ec_call_date`, `.ec_sent`, `.ec_source_path`, `.ec_source_reason`, `.ec_source_state`, `.eligible`, `.leash`, `.provisional`, `.stage_at_entry`; `early_turn.fired`, `.leader_pullback_source`, `.reason`, `.timeframes`, `.washout_state`; `signal_tier`, `signal_provisional` | Paid/internal. Public stage is a separately approved display stage, never the raw nested object |
| Internal scores / gates | `_signal_date`, `_priority_score`, `_conviction_score`, `_act_level`, `_r_unit`, `_gate_go` | Private/internal; forbidden from every public projection and buyer-facing claim |

### Approved public Prophet projection proposed for signoff

This is a translation of the CEO ruling, not a new schema authority. The builder should copy from the canonical paid plan into a separate display object with an allowlist:

```yaml
schema: prophet.public_preview/v1
authority_tier: display_only
as_of: ISO-8601
delayed: true|false
subject: ticker-or-approved-subject
stage: approved-display-stage
why_now: one bounded display sentence
freshness:
  observed_at: ISO-8601
  delayed_by_sessions: integer
setup_class: broad approved class
receipt_id: public receipt reference, only for resolved proof
outcome: win|loss|flat|open, only for delayed resolved proof
```

Forbidden in the public current preview: full ranking, priority/conviction score, exact entry, stop, targets, tranche, option contract, complete evidence stack, alerts, private notes, source-engine internals, plan-management steps, and unreduced raw objects. The operator must approve the final field allowlist and delay before implementation.

## 4. Pricing, naming, and claim drift

### Canonical current catalog

| Product state | Current config truth | Enforcement consequence |
|---|---|---|
| Free | `$0`; no Stripe product | Free quotas and preview/persistence contract |
| Essential | `$99` monthly (`essential_2026_v2_monthly`); `$900` annual (`essential_2026_v2_annual`); no trial; `site_full`, `terminal_live_options` | Full site feature and Terminal options, but not `chat_opus` |
| Pro | `$149` monthly (`pro_2026_v2_monthly`); `$1,308` annual (`pro_2026_v2_annual`); seven-day trial; `site_full`, `terminal_live_options`, `chat_opus` | Pro quotas/features; trialing status uses generic trial AI bucket |
| Founding Pro | Pro entitlement, annual `$900`, base/list `$1,308`, cap 2,000, durable entitlement metadata, forever discount while eligible | **Not a fourth tier.** Account row is `pro`; price/offer provenance must be displayed separately |
| Trial Essential | Checkout cannot create it (`trial_days: 0`) | A manually-created `trialing essential` row would still pass feature gates and use generic trial AI quotas; unsupported state needs an explicit deny/test |
| Trial Pro | Seven-day, card-required; same entitlement features while `trialing`; AI is 25 Fast + 3 Pro for trial period | Research/paid gates generally accept `trialing`; UI must disclose the quota transition |
| Unlimited/operator | Email-allowlist overlay used by Brain and Bot gate; not present in catalog rank | Private operational state only; must not appear as a customer plan or bypass inconsistently |

### Stripe lookup-key compatibility map

This is the repository resolver contract in `config/plans.yml:42-97` and `app/billing.py:113-143`, not a claim that the corresponding live Stripe objects were inspected.

| Input key / metadata | Canonical entitlement | Status |
|---|---|---|
| `essential_2026_v2_monthly`, `essential_2026_v2_annual` | `essential` | Current checkout keys |
| `insider_monthly`, `insider_annual`, `insider_2026_monthly`, `insider_2026_annual`, `insider_2026_v2_monthly`, `insider_2026_v2_annual` | `essential` | Permanent legacy price keys; removal would downgrade existing subscribers |
| Product metadata key `insider` | current product key `essential` | Permanent product-key adoption alias for Stripe bootstrap |
| `pro_2026_v2_monthly`, `pro_2026_v2_annual` | `pro` | Current checkout keys |
| `pro_monthly`, `pro_annual`, `pro_2026_monthly`, `pro_2026_annual` | `pro` | Permanent legacy price keys |
| Founding offer `founding_pro` with `base_lookup_key=pro_2026_v2_annual` | `pro` | Offer/coupon provenance only; no `founding_pro` customer tier or separate entitlement lookup key |

Wire-tier compatibility is separate from Stripe lookup keys: Macro maps the historical `insider` tier to Essential, while Terminal accepts `insider` as Essential but does not accept `founding_pro` as Pro (M1,T1).

### Drift ledger

| Topic | Canonical now | Conflicting evidence | Ruling / disposition |
|---|---|---|---|
| Insider naming | Wire/catalog tier is `essential`; inbound `insider -> essential` alias is permanent | Old monetization masterplan and one paywall test/interstitial still say Insider; immutable cached clients may send it | Mark old document superseded for price/tier policy; preserve aliases and legacy lookup keys forever |
| Essential price | `$99/mo`, `$900/yr` from `config/plans.yml` | Old masterplan ratified `$59/mo`, `$588/yr`; stale narrative remains authoritative-looking | Config is current. Do not edit price in this program |
| Pro list price | `$149/mo`, `$1,308/yr` | Old masterplan says `$89/mo`, `$828/yr` | Config is current; remote Stripe parity unknown |
| Terminal offer prices | Macro catalog says Essential `$99/$900` and Pro `$149/$1,308` monthly/annual | Terminal onboarding independently advertises Essential `$69/mo` or `$588/yr`, Pro `$99/mo` or `$828/yr`, and a seven-day trial (T5) | Stop treating the Terminal plan array as catalog authority; render offers from the Macro billing catalog/API after remote Stripe parity is attested |
| Founding Pro | Pro entitlement at `$900/yr` while offer active | Plans and landing display Essential annual and Founding Pro at the same `$75/mo` annual equivalent with equal visual availability | During offer, de-emphasize/hide Essential annual; keep list Pro visible; one-paid-tier versus Essential monthly remains Chairman decision |
| Trial | Essential none; Pro seven days/card-required | Old masterplan says both paid tiers have a seven-day trial; generic trial quota has no tier dimension | Mark old trial table superseded. Add explicit unsupported Trial-Essential test |
| Essential Options trial claim | No Essential trial; active Essential gets Options through `terminal_live_options` | Plans copy labels Essential Options access “Trial too,” even though only Pro checkout creates a trial | Remove the claim or change the commercial ruling; do not fabricate a Trial-Essential state |
| Research | Public latest three summaries; full archive/PDFs Pro-only | Plans card and matrix promise Essential “Every research report” / “All reports”; landing correctly marks reports Pro | CEO target makes premium archive/PDFs Pro. Fix Plans claims, do not weaken Research API |
| Committee / brief claim | No usable Committee customer route is established | Plans advertises Committee while Caddy hard-404s `/committee.html` for every tier | Remove the sold claim until a supported, classified replacement exists |
| Full-site claim | Essential/Pro `site_full` catalog feature | All HTML is public and ordinary registered premium paths are staged open; some pages contain full paid bytes | Keep public shells, move differentiated payloads behind existing feature |
| Indicator count | Marketing config says 21 core; Free +1 advanced, Essential 15/31, Pro 31/31 | Terminal's actual module/suite mapping and Founding normalization differ; raw count does not prove usable feature parity | Generate claims from a Terminal-exported capability manifest or shared tested contract, not duplicated counts |
| Fast AI | Free 5/week; Essential 300/month; Pro uncapped requests with 5M token backstop; trial 25 | Old masterplan and stale `templates/chat.html` say Pro 1,000/month; Plans comment claims landing differs although current landing and Plans now agree | Config is authority. Remove stale copy/comments and test rendered claims |
| Deep/Pro AI | Free 0; Essential 10/month; Pro 150/month; trial 3 | `chat_opus` feature exists only on Pro even though quota config permits Essential 10 | Decide whether the lane is feature-gated Pro-only or quota-gated Essential 10; then make catalog, gateway and copy agree |
| Terminal options | Catalog grants `terminal_live_options` to Essential and Pro, including trialing feature rows | Terminal has correct API route checks, but its raw public R2 inputs bypass those routes | Preserve feature contract; privatize/proxy protected upstreams |
| Account labels | Macro maps both `insider` and `essential` to Essential | Mastermind account router is unmounted and reads user metadata; `/api/me` and `/api/account` disagree on Unlimited | Make Macro `/api/me` the sole broker; delete/retire alternate metadata authority after consumers migrate |
| Stripe lookup keys | Current and all legacy lookup keys are retained in `config/plans.yml` | Production Stripe object parity was not inspected | Run read-only parity tool in a separately authorized operational gate; never infer remote truth from config |
| Old monetization masterplan | Historical implementation record only | It explicitly accepted the Pages leak and contains old names, prices, trials, AI quotas and page wall doctrine | Add a supersession banner pointing to the approved matrix; preserve history, do not silently rewrite it |

### Current claim contradictions that affect a buyer

- The Plans page says Essential unlocks “all the research” while the Research API intentionally makes Essential a teaser tier.
- The landing labels some differentiated desks Pro-only while the Plans page says Essential gets all dashboards/desks; actual anonymous HTML may expose both.
- Plans and landing put Essential annual and Founding Pro annual at the same `$900` total, making Essential annual economically dominated.
- Founding Pro is displayed as a Pro card but the account entitlement only says `pro`; without offer provenance, a founder cannot verify the grandfathered rate from product state.
- `templates/chat.html` still advertises the superseded Pro 1,000 Fast messages/month even though the active config and primary pricing surfaces say Unlimited.
- A test pins the phrase “Insider members” in the old interstitial even though the canonical customer name is Essential.
- The Plans matrix says Essential Options access applies to a trial even though Essential checkout has no trial.
- Plans sells Committee/brief/track-record value, but Committee is hard-404 for every tier and the track-record page is entirely anonymous rather than tiered.

## Live receipt ledger

All receipts below are anonymous, cache-busted where relevant, and record status/bytes without reproducing protected values. Main-domain URLs redirect to `www`; effective statuses are shown.

| Time UTC | URL / surface | Result | Meaning |
|---|---|---|---|
| `2026-08-11T21:17:34Z` | `https://mastermind-x.com/api/health` | `200`; `checkout=597d95de3ce`; static `commit=59b5fcfefc9` | VPS checkout matched audited Macro main; static artifact was an older build revision |
| same | Main `/us_stocks.html` | `200`, 1,133,777 bytes, 70 `.pvcard` elements, one inline stock-table data block | Anonymous full-board bytes despite visual cap |
| same | Main `/prophet/showcase.json` | `200`, 29,485 bytes, 12 winner-selected cards | Public display artifact, not balanced proof |
| same | Main `/live/prophet_live.json`, `/prophet/index.json`, representative plan, `stockdata`, `premiumdata` | each `401`, 76-byte JSON | Primary anonymous asset wall works |
| same | Pages `/macro/us_stocks.html` | `200`, 1,108,251 bytes, 65 cards | Static mirror bypasses HTML policy |
| same | Pages `/macro/prophet/index.json` | `200`, 622,923 bytes | Full Prophet index bypass |
| same | Pages `/macro/premiumdata/special_situations.json` | `200`, 8,490,693 bytes | Early-enforced primary payload fully bypassed |
| same | Public R2 representative `stockdata` object | `200`, 112,877 bytes | Public origin exposes graded per-ticker store |
| same | Terminal `/terminal` | `200`, 82,338 bytes | Core Terminal public as intended |
| same | Terminal `/data/manifest.json` | `200`, 2,134,560 bytes | Entire Terminal static manifest publicly served; contents require classification |
| `2026-08-11T21:27:33Z` | Terminal public R2 `live_flow/tide_current.json`, `options_hub/gex/SPY.json`, `options_prophet/index.json`, `prophet/index.json` | each `200`; 53,989 / 35,423 / 138,803 / 813,772 bytes | Paid route gates are bypassed at the configured origin |
| `2026-08-11T21:28:31Z` | Terminal anonymous deployed Next chunk at audited `dpl=32f4254…` | `200`, 664,595 bytes; full-source signature tokens present | Proprietary Pine implementation is delivered before authentication |
| same | Bot `/` | `403`; `/health` `200` | Whole-host Pro gate works on public hostname |
| same | Main `/mastermind/mastermind_snapshot.json` | `401`, 76 bytes | Primary wall works |
| same | Raw Git `site/mastermind/mastermind_snapshot.json` | `200`, 184,196 bytes | Public Git bypass for portfolio payload |
| same | Raw Git `site/mastermind/nw_feedback.json` | `200`, 9,673 bytes | Public cross-system feedback payload |
| same | Raw Git `data/mastermind/cost_summary.json`, `key_events.jsonl`, `key_pool_status.json` | `200`, 32,754 / 43,676 / 1,140 bytes | Operational telemetry is public-repository data |
| later same audit | Macro `/`, all named P0 HTML | `200`; only `/` lacked live `noindex`; all other probed P0 routes had `noindex,noarchive` | Deployed SEO posture differs from source grouping |
| later same audit | `/biocatalyst.html`, `.css`, `.js` | HTML `200`; CSS and JS `401` | Concrete public-shell asset false lockout |

## 5. Leakage audit

### Confirmed leaks and bypasses

| Severity | Leak / path | Evidence and enforcement gap | Exposure | Smallest fix and acceptance proof |
|---|---|---|---|---|
| P0 | Full US Stocks/Prophet rows in anonymous HTML | `templates/dashboard.html.j2:15609-15642` serializes complete graded rows; generated `site/us_stocks.html` contains full cards/table; `tier_preview.js:198-247` hides after delivery | Current roster, names, scores/classifications, ranked detail and plan-adjacent fields | Split builder output into public one-card shell, authenticated Free three-card projection, and paid remainder under early-enforced path. Test forbidden strings/fields are absent from anonymous/Free bytes |
| P0 | Regional stock pages opened without a preview split | Full cards are present in generated `site/china_stocks.html:6881-6974`, `site/canada_stocks.html:1558-1677`, `site/hk_stocks.html:1234`, `site/intl_stocks.html:989-1050`; these outputs do not load the US preview controller | Complete named regional current rows to anonymous visitors | Apply the same server split by page family; do not add the client controller as the “fix” |
| P0 | GitHub Pages mirrors all generated `site/` | `.github/workflows/pages.yml:1-13,99-103`; live full US page, Prophet index and 8.49 MB early-gated payload all returned `200` | Any tracked/generated paid artifact in the deployed tree bypasses Caddy, cookies, features and no-store | Immediately stop full-tree deployment or make environment private; later deploy only a generated public projection. Alternate-origin tests must enumerate forbidden keys and require `404/403` |
| P0 | Public R2 mixes ordinary market facts with proprietary graded data | `templates/data_base.js:1-35`, `scripts/publish_r2.py:69-108`; live representative `stockdata` returned `200` and contained score/rank/conviction/entry-plan fields | Per-ticker proprietary classification and plan geometry | Split object families/fields; keep generic prices/charts public and serve graded data from private bucket through entitlement-aware gateway |
| P0 | Terminal options/Prophet data routes are gated, origins are not | Terminal `lib/upstreams.ts:8-18` hardcodes public R2; `lib/flowSource.ts:241-308,935-977` maps/probes complete live-flow, GEX, Options Prophet and Prophet indexes. Direct anonymous R2 GETs returned `200` | Full premium options/flow and Prophet inputs without `terminal_live_options` | Private upstream plus server proxy using `hasLiveOptions`/paid feature; public chart receives a separately reduced context artifact |
| P0 | Proprietary Terminal Pine source ships in anonymous JS | Terminal `lib/pine.ts:1-4,20-35` derives the Oracle overlay from full `FLAGSHIP_PINE`; client `ChartPanel.tsx:1,36,2248-2268` imports/runs it. Live anonymous Next chunk at audited deploy SHA returned `200`, 664,595 bytes and contained distinctive source tokens | Complete proprietary indicator implementation in any anonymous browser/cache | Remove full source from all client imports. Execute protected algorithm server-side or ship an approved compiled/non-secret public implementation. Bundle test must reject source signatures |
| P0 | Registered Free receives the full proprietary Pine source | Terminal `app/(shell)/scripts/page.tsx:15-18,29-39` prepends `PROPRIETARY_SCRIPT` for every signed-in tier; read-only only prevents editing | Free user can read/copy network/React payload despite UI lock | Only deliver full source if it is intentionally a Free benefit; otherwise deliver metadata/compiled result and gate source server-side. Test response bytes, not editor controls |
| P0 | Free receives ordinary premium paths under documented/default staged switch | `app/paywall.py:349-383`; `tests/test_paywall.py:38-42,140-167`; Prophet index/plans/live overlay are not `enforced_early` | Any signed-in user with a known URL can receive paid static/API data unless the route has its own gate | Migrate each P0 paid payload to `premium.enforced_early` or `enforce_site_full(always=True)` before global activation; test Free denial while switch is off |
| P0 | Mastermind portfolio snapshot in public Git | Main URL returns `401`; raw public Git `site/mastermind/mastermind_snapshot.json` returns `200`, 184,196 bytes. Publisher includes tickers, weights, reasoning, entry prose, decisions, research, track record and rejected candidates (`bridge/macro_snapshot.py:33-54,88-158`) | Detailed portfolio state bypasses product and host gate; sampled artifact was stale relative to current default book | Decide delayed-public-proof versus private-current classification. Reduce and delay an approved public schema or move current output to private transport; purge/rotate future publication, acknowledging Git history persists |
| P1 | Public Git Neural Web/operator and ops telemetry | Raw `site/mastermind/nw_feedback.json` plus `data/mastermind/{cost_summary,key_events,key_pool_status}` return `200`; source permits bounded operator text and provider/key-pool metadata | Operator prose and operational metadata are public by repository design, without a field-level ruling | Approve a public allowlist or move to private artifact store; scrub ticker/operator text and provider key identifiers if kept public |
| P1 | Mastermind Bot confidentiality depends entirely on one edge gate | Mastermind `app/auth.py:11-24,72-84,236-325` intentionally permits reads; `app/web.py` exposes dashboards, research/PDF, holdings/decisions/fills. Public hostname gate works, direct origin `:8001` reachability was not proved | A firewall/bind/topology regression would expose the whole read application | Attest loopback bind/firewall/serve-only topology and add defense-in-depth user/feature checks to sensitive APIs or an origin-auth control |
| P1 | Legacy cross-repo publisher pushes directly to public Macro main | Mastermind `scripts/export_macro_snapshot.py:150-230`; scheduler calls it and treats push failure softly | Bypasses PR review/access scanners; stale or over-broad payload can persist silently | Replace direct-main writer with canonical reviewed publication lane, schema allowlist, attested SHA and alerting |

### Public or acceptable bytes that are not leaks

- Supabase publishable/anonymous client configuration is intentionally public; service-role, Stripe secret, R2 secret, and model tokens are not expected in `site/`.
- Generic delayed quotes, basic charts, public filings/event facts, methodology, coverage counts, page shells, and reduced public proof are intended public content.
- Research PDFs were not found at a public static URL; `app/research.py` streams them from a private bucket after a Pro/status check.
- Main-domain protected responses observed here were non-cacheable `401` JSON; no primary-origin protected byte leak was seen anonymously.

### Customer-data publication audit

No reviewed builder or publication path was found writing account rows, emails, watchlists, preferences, subscription records, or other customer-specific data into `site/`. Account data is fetched at runtime through bearer-authenticated APIs. That is a **targeted negative finding, not an estate-wide PII attestation**: the current boundary test checks dangerous file classes, not semantic PII. Wave 1 must add a generated-artifact field/content scanner and owner-scoped fixtures before launch.

## 6. False-lockout and entitlement-divergence audit

| Severity | Failure mode | Current truth | Required correction / test |
|---|---|---|---|
| P0 | Public shell assets gated | `/biocatalyst.html` is `200` anonymous while its required CSS/JS are `401`; `/start.html` requires `wh_banner.js`, but it is not public-classified and the alert ticker silently disappears | Generate a transitive asset manifest per public shell; anonymous-probe every required asset. A shell passes only if its critical path is functional, not merely `200` |
| P0 | Sold capability hard-404 | Plans sells Committee/brief/track-record access, but `/committee.html` is in Caddy `@never_site` and hard-404s for every customer | Remove claim or provide the approved customer route before checkout; acceptance starts from rendered plan claim and reaches a usable capability |
| P1 | Unlimited shown but main payload denied | `/api/me` overlays `tier=unlimited`; main paywall reads only the entitlement row and has no operator bypass | Centralize an effective-entitlement resolver and return features/status; main paywall test with operator fixture must match `/api/me` |
| P1 | `/api/me` and `/api/account` disagree | `/api/me` applies Unlimited overlay; `/api/account` returns the billing row unchanged | Make `/api/account` consume the same effective resolver or retire it in favor of one broker; snapshot-test both if both remain |
| P1 | Unlimited denied by Research | Research exact allowlist is `{"pro"}`, so literal Unlimited/allowlist-only operator can be denied | Gate on an explicit research feature/capability or canonical effective Pro equivalence, not a scattered string comparison |
| P1 | Founding representation can downgrade at a consumer boundary | Macro correctly emits Founding as `pro`; Terminal normalizes raw `founding_pro` to Free because only `pro/unlimited/essential/insider` are recognized | Add cross-repo contract test proving Founding always arrives as `tier=pro` plus offer metadata; optionally tolerate `founding_pro` inbound without ever writing it |
| P1 | Unlimited becomes unintended Issue Desk operator in Terminal | Terminal normalizes Unlimited to Pro and `hasIssueDeskOperator` also auto-grants the operator capability | Keep explicit `options_issue_desk_operator` feature as authority; decide whether email-allowlist Unlimited should imply issuance power and test that ruling |
| P1 | Stale UI hint temporarily hides paid rows | `tier_preview.js` paints cached/session hint first, then refreshes session and `/api/me`; a transient failure sets Free. It does not protect bytes, but can visually lock a payer | Keep session refresh, add loading/unknown state instead of downgrading presentation on transient failure, and let server-authorized payload decide final state |
| P1 | Trial contract varies by capability | Generic site/Research gates accept `trialing`; AI always uses 25+3 trial quota; unsupported Trial Essential would pass features; Terminal options use features; plan copy says “full access” | Define Trial Pro feature/quota table explicitly, make Trial Essential impossible at reducer/admin boundaries, and test activation/expiry/cancel across all consumers |
| P1 | Terminal does not refetch entitlement after checkout | `useEntitlement` refetches only when signed-in identity changes; Settings fetches once per email; checkout completion advances onboarding and closes without invalidating either cache (T5) | Add one entitlement refresh/invalidation event after checkout/portal return and on subscription mutation; browser-test an unchanged signed-in Free user upgrading to Essential/Pro without reload |
| P1 | Free Discover promises tabs whose data API is paid | Terminal mounts Screener, Heatmap and Leaders/Radar for every account; Screener works from public manifest, while Leaders/Radar call feature-gated `/api/flow` and error for Free | Gate/label each tab from the same capability response or provide an approved delayed Free projection; test the rendered Free promise through the final data response |
| P1 | Essential claim versus Research denial | Plans promises all reports, server intentionally denies Essential | Keep CEO Pro-only archive and fix claim, or explicitly change the ruling and feature catalog; do not weaken server gate to match accidental copy |
| P1 | Mastermind account page is not authoritative | Local account router is unmounted, reads `user_metadata.plan`, and calls removed helpers; frontend shows disabled/coming-soon state | Migrate Bot to Macro `/api/me` broker and remove metadata as authority |
| P2 | Authenticated Free experiences inconsistent “paid” estate | Early paths deny, ordinary premium paths stage open, independent APIs vary | P0-by-P0 early enforcement before launch; contextual lock must name exact capability and plan |
| Pass | Positive entitlement cache | Macro caches positive verdicts only, limits outage grace to last confirmed positive, invalidates on billing mutations; Terminal caches positive options verdicts 45 seconds and resolves write gates fresh | Retain. Test token isolation, revocation TTL, outage grace, and no negative cache |
| Pass | Session refresh before preview resolution | `tier_preview.js:287-307` calls Supabase `getSession()` before `/api/me` | Retain and apply to every hydration route; add expired-token browser test |
| Pass | Main protected asset failure direction | Regwall/paywall failures return non-cacheable denial/503 and do not fall through to file server | Retain; verify both HTTP/HTTPS and edge cold-cache behavior |

Past-due and canceled subscriptions reduce to Free immediately in the reducer (`app/billing.py:793-818`). That is internally consistent with current policy. Whether a dunning grace period is commercially desired is an operator decision; it must not be implemented by extending stale positive cache.

## 7. Recommended launch matrix

This matrix translates the CEO ruling into the existing catalog, policy and API spine. `config/plans.yml` remains the product/feature catalog; `config/site_access.yml` remains the static path policy; Macro `/api/me` remains the account broker. No second tier catalog is proposed.

| Capability / path family | Anonymous | Free | Essential | Pro / Founding Pro | Trial Pro | Required authority and enforcement |
|---|---|---|---|---|---|---|
| Public context shells | Page purpose, totals, methodology, freshness, generic context | Same + identity/persistence | Same shell, paid hydration | Same | Same | Caddy public HTML plus generated transitive public-asset manifest; no paid rows inline |
| Ranked lists generally | One newest/representative approved projection | Three approved projections per build | Complete board, filters/search/sort | Same | Same complete board | Public projection + authenticated Free projection + `/premiumdata/<surface>.json` with `site_full`, `premium.enforced_early` |
| Prophet current board | One card with approved field allowlist | Three approved cards | Full board and exact plans | Same | Full board/plans for trial term | Existing `site_full`; paid payload/API early-enforced even while global switch is off |
| Prophet live overlay | No armed names/current live state | No | Full | Full | Full | Same paid Prophet capability/path; `private,no-store`, Free `403` |
| Prophet public proof | Delayed resolved wins and losses with receipts and visible delay | Same | Same + paid full history | Same + deeper/exportable history | Same as paid during trial | Separate `display_only` proof projection; no current complete plans |
| Basic stock/company facts and charts | Delayed/current ordinary facts, basic chart | Same + save/watch | Same | Same | Same | Public fact schema/bucket; explicitly excludes ranks/scores/plan geometry |
| Graded stock intelligence | Preview only if approved | Limited preview if approved | Full current graded object | Full | Full | Private R2 or Macro API with `site_full`; never direct public bucket |
| Research Vault | Latest three summaries and public SEO teasers | Same | Same teaser/standard non-archive intelligence | Full catalog/search/PDFs | Full Pro archive | Add/retain a catalog feature for premium research; server status+feature check, not tier string |
| Terminal core | Core chart, basic data, public indicator set | Same + saved workspace/watchlists | Same | Same | Same | Public Terminal route; account-required persistence via RLS |
| Terminal advanced indicators | None beyond explicitly Free modules | Free module set | Essential 15-module set | All 31 | Explicitly choose Pro indicator set during trial | Generate/validate one Terminal capability manifest; server-authorize paid code/data where secrecy matters |
| Terminal live options/flow | Product explanation and reduced delayed context | Same | Full live options | Full | Full | `terminal_live_options` feature at every API; private upstream; no public R2 bypass |
| Pine / proprietary script | No source; approved rendered behavior only | No source unless explicitly made a Free benefit | Use/run according to product ruling | Use/run plus approved workflow | Same as Pro if promised | Source stays server-side/private; save/write resolves fresh entitlement |
| Fast AI | No high-cost lane | 5/week | 300/month | Unlimited requests with token backstop | 25 for trial | Existing Brain quota config; auth required; copy generated/tested from config |
| Deep AI | None | None | **Decision required:** 10/month versus Pro-only feature | 150/month | 3 for trial | Resolve `chat_opus` feature versus quota mismatch; one server rule |
| Portfolio brief | Public product explanation only | Basic watchlist summary if built | Standard portfolio-aware monitoring if approved | Advanced brief/Bot/automation | Pro behavior during trial | Explicit portfolio feature(s); current `/api/portfolio/brief` Pro rule until CEO classifies Essential boundary |
| Bot desk | Purpose-built public explanation, not internal app | Same | Operator decision: standard view or explanation | Full Pro app | Full for trial if promised | Edge gate plus defense-in-depth API checks; raw snapshots separately classified |
| Account/billing | Sign-in/Free value explanation | Authoritative tier/status/features/limits | Same + renewal | Same + Founding rate provenance when applicable | Trial end, quota and next charge | Macro effective-entitlement broker; positive cache; fresh write checks; one customer-facing account model |
| Private/admin/execution/customer data | Never | Never | Never | Never | Never | Shape E deny/private origin; explicit operator feature for issuance/mutation |

### Non-runtime decision packet

This block is intentionally not a new application schema. It is a compact, reviewable representation of the matrix that later workers must encode in the existing config and tests.

```yaml
tiers:
  anonymous:
    current_preview_items: 1
    persistence: false
    paid_payload: false
  free:
    current_preview_items: 3
    persistence: true
    paid_payload: false
    fast_ai: 5_per_week
  essential:
    site_full: true
    prophet_full: true
    research_archive: false
    terminal_live_options: true
    terminal_advanced_modules: 15
    fast_ai: 300_per_month
    deep_ai: decision_required_10_or_pro_only
  pro:
    site_full: true
    prophet_full: true
    research_archive: true
    terminal_live_options: true
    terminal_advanced_modules: 31
    fast_ai: unlimited_with_token_backstop
    deep_ai: 150_per_month
    advanced_portfolio: true
  trial_pro:
    entitlement_equivalence: pro_except_quota
    fast_ai: 25_per_trial
    deep_ai: 3_per_trial
  founding_pro:
    entitlement_equivalence: pro
    billing_offer: founding_pro
  operator:
    customer_tier: false
    capabilities: explicit_private_features_only
```

## 8. Exact implementation waves

No wave below is authorized by this census itself. Freeze the approved matrix first. Each wave is intentionally a small PR with an independently reversible boundary.

| Wave / owner | Files and change boundary | Dependencies | Required tests / live proof | Rollback | Principal risk |
|---|---|---|---|---|---|
| **W0A — stop alternate publication**; Platform/Security | Disable full `site/` Pages uploads in `.github/workflows/pages.yml`, `daily.yml`, `weekly.yml`; preserve only approved public projection or make environment private | Operator approves immediate containment and public mirror disposition | Pages forbidden URLs `404/403`; approved public pages still `200`; record deployment/environment receipt | Re-enable last known public-only artifact, never full tree | SEO/demo links depending on mirror |
| **W0B — classify and split R2**; Platform + Macro/Terminal | `templates/data_base.js`, `scripts/publish_r2.py`, relevant workflow publishers, Terminal `lib/upstreams.ts`/server proxies; separate public facts from private graded/options/Prophet keys | Field allowlists and private gateway design; do not break chart data | Anonymous direct-origin forbidden keys deny; public quote/chart keys work; Essential/Pro proxy `200`, Free `403`; CORS/cache tests | Restore public fact bucket only; feature-flag private proxy fallback | Breaking live charts/options; CDN cache residue |
| **W0C — stop public cross-repo portfolio/ops payloads**; Mastermind + Platform | Mastermind `bridge/macro_snapshot.py`, `bridge/nw_feedback.py`, `scripts/export_macro_snapshot.py`, scheduler; Macro `site/mastermind/*`, `data/mastermind/*` publication contract | Operator classifies each artifact and public fields | Raw Git future head contains only approved delayed projection; private destination receipt; stale-writer alert | Disable publisher and retain last approved reduced artifact | Git history remains public; bot consumers may depend on raw paths |
| **W1 — freeze registry and byte contracts**; Access owner | Generated P0 registry or existing page registry lane; `config/site_access.yml`; tests only where possible: shell dependency closure, HTML forbidden-field scan, alternate-origin manifest, static PII scan | Approved P0 list and field classification | Source/generated parity; every P0 shell/assets; anon/Free byte snapshots; audit-unrun/CI pack registration for new tests | Revert registry/tests only | False confidence from incomplete field signatures |
| **W2 — split US and regional ranked boards**; Macro product-data owner | `scripts/build_site.py`, `templates/dashboard.html.j2`, regional templates/builders, new/reused row partials, `config/site_access.yml`, `tests/test_public_dashboard_preview.py` and gate tests | W1 contracts; public card fields approved | Anonymous 1, Free 3, paid full; forbidden fields absent from HTML/Free JSON; hydration/session refresh; source/generated parity | Feature flag returns to last public projection, not full inline board | Large generated-page collision and stale builder output |
| **W3 — private Prophet plane**; Prophet + Access owners | `scripts/build_prophet.py`, paid/public projection writers, `/prophet` publishers, `live/prophet_live` serving, policy, APIs and Prophet access tests | W0B and W2; exact public proof/preview schema | Anon/Free full index/plans/live deny on every origin; Essential/Pro/trial pass; no-store; plan fields absent from public projection | Dark paid hydration and retain delayed public preview | Disrupting nightly/Terminal consumers; stale R2 copies |
| **W4 — Terminal source and entitlement closure**; Terminal owner | `lib/pine.ts`, client `ChartPanel`, Scripts page/editor, `lib/upstreams.ts`, flow/hub routes, indicator suite manifest, subscription normalization/tests | W0B; decision on script benefit, Founding wire contract, Unlimited issuance | Production bundle has no proprietary signatures; Free cannot receive source; options upstream direct deny; feature gates/test all tiers/trial; watchlist regression | Disable proprietary client indicator and fall back to approved server-rendered signals | Feature regression in core chart; exposing compiled logic incorrectly |
| **W5 — one effective entitlement broker**; Billing/Access owner | Macro `app/main.py`, `app/paywall.py`, `app/research.py`, billing resolver; Terminal consumer; retire Mastermind metadata account route | Decisions on operator capabilities, Deep AI and Research feature | `/api/me` and `/api/account` parity; Insider alias; Founding=Pro; operator explicit features; Research/portfolio/Bot state matrix; cache/revocation tests | Revert consumers to billing row while keeping protected paths closed | Accidental operator denial or overgrant |
| **W6 — reconcile buyer-facing contract**; Product + Billing | `templates/plans.html.j2`, `templates/index.html`, `templates/chat.html`, interstitial, account copy; add supersession banner to old monetization plan | Chairman Founding presentation and Deep AI/Committee/Research decisions | Rendered prices/quotas generated from config; claim-to-route tests; EN/ZH; checkout CTA and interval tests | Revert copy only; do not change catalog/prices | Copy promises a capability before its gate ships |
| **W7 — balanced Prophet proof**; Prophet evidence owner | `scripts/build_prophet.py` showcase/proof builder, landing integration, proof tests; append-only receipts | Public delay/outcome schema approved; W3 private current plane | Winners and losses, timestamped receipts, selection/disclosure tests, no current plan fields, PIT/vintage checks | Fall back to existing labeled delayed showcase, not live board | Survivorship bias or authority leakage |
| **W8 — authenticated production matrix**; QA + Support + Platform | No broad feature work; fixtures/accounts, browser harness, EdgeOne cache rules, support/runbook | W0-W7 merged; SMTP/CAPTCHA/Stripe test drills complete | Anonymous, Free, Essential, Pro, Trial Pro, Founding Pro, operator, past-due/canceled; HTTP+HTTPS; cold/warm cache; upgrade/expiry/return; alternate origins; support/legal | Keep `PAYWALL_ENABLED=0`; retain early gates | Test accounts or edge caching differ from source assumptions |
| **W9 — arm global wall**; Operator + Platform | Production env only after checklist, service restart, monitoring | W8 signed receipt and explicit go decision | Health/checkout SHA, protected-path matrix, customer account smoke, rollback drill, support on-call | Set `PAYWALL_ENABLED=0`, restart, verify; early gates remain | False lockout at launch or shared-cache data leak |

### Cross-repo contract work that must accompany the waves

- Add a declared Mastermind `prophet.index/v1` import contract and exact Macro SHA attestation. `portfolio/prophet_feed.py` currently claims to “gate nothing,” while downstream entry/conviction logic can park or reject candidates using its geometry.
- Classify Bot, portfolio brief, autonomous-book snapshot and Neural Web feedback separately. “Portfolio” is not one capability or one access level.
- Replace the legacy Mastermind direct-to-Macro-main publisher with a canonical writer, reviewed schema and failure alert. Executive-worker denial fences do not govern that legacy scheduler today.
- Keep Terminal's owner-scoped Macro portfolio brief distinct from the autonomous Mastermind portfolio. No direct current-head Terminal-to-autonomous-book contract was found.

## Operator decisions required

| # | Decision | Recommended default | Why it blocks |
|---|---|---|---|
| 1 | During Founding Pro, show one paid tier or retain Essential monthly? | Retain Essential monthly only if a lower-commitment path is strategically valuable; hide/de-emphasize Essential annual. This is the Chairman-reserved decision | Determines pricing surface and CTA matrix |
| 2 | Disable/private the full GitHub Pages mirror now? | **Yes, immediately**; later publish only approved public projection | It is a complete live bypass of every main-domain gate |
| 3 | Which R2 object families/fields are truly public? | Public: ordinary facts/charts. Private: ranks, scores, classifications, current board membership, plan geometry, premium options/flow | Private gateway and data migration cannot be scoped without this |
| 4 | Approve the exact public Prophet card fields and delay | Use the allowlist in section 3; delayed proof must include wins and losses | Required before board split/proof builder |
| 5 | Is Essential's Research benefit teaser-only or full archive? | Teaser/standard intelligence for Essential; full vault/PDF archive Pro | Server and two sales surfaces currently conflict |
| 6 | Does Essential receive Deep AI 10/month, or is `chat_opus` Pro-only? | If the 10/month lane is real, add/rename an Essential-capable feature; otherwise set Essential quota to zero and fix copy | Catalog feature and quota authority disagree |
| 7 | Is the Committee a customer surface, and at what tier? | Do not sell it until a supported route exists; classify its replacement explicitly | Current advertised capability hard-404s |
| 8 | Is the Bot desk Pro-only, and what public/Essential explanation exists? | Keep the internal Bot app Pro until its sensitive APIs are defended; give non-Pro a separate product explanation | Whole-host gate cannot express CEO preview/Essential nuance |
| 9 | How is Founding rate provenance shown in account state? | Tier remains `pro`; add read-only offer/rate provenance from billing authority | Founder needs proof of grandfathered rate without inventing a tier |
| 10 | What capabilities does operator Unlimited imply? | Explicit private feature grants only; do not infer issuance power or customer benefits from the label | Current consumers grant/deny different things |
| 11 | Does Trial Pro include full non-AI Pro behavior and reduced AI quota? | Yes, if “full access” remains; disclose 25+3 quota and test every feature/expiry. Trial Essential remains invalid | Trial rules are status-, feature-, and tier-dependent today |
| 12 | Past-due/dunning grace policy | Keep immediate feature loss unless Support/Billing approves a bounded fresh-authority grace; never use stale cache as billing grace | Avoid accidental access extension or surprise lockout |
| 13 | Classify public portfolio snapshot, Neural Web operator prose, and cost/key-pool telemetry | Current portfolio/operational state private; publish only delayed reduced proof with field allowlist | These are public Git artifacts today |
| 14 | May Prophet plan geometry reject/park Mastermind portfolio entries? | Ratify explicitly with schema, PIT/vintage and imported-SHA contract, or constrain it to candidate sourcing | Cross-boundary effective authority is undocumented |
| 15 | May the legacy scheduler push cross-repo directly to Macro main? | No; use reviewed canonical publication lane with failure alert | Current direct writer bypasses delivery/access review |
| 16 | Ratify the P0 route list and SEO posture | Adopt the provisional list here; explicitly index public acquisition/support/legal pages and keep private/app routes noindex | No canonical registry exists; live edge noindexes nearly every P0 route |
| 17 | Who owns the static customer-data/PII attestation? | Access/Security owner with generated scan and signed release receipt | Current audit is targeted, not exhaustive |
| 18 | When may `PAYWALL_ENABLED=1` be set? | Only after W8 and a same-SHA rollback drill | Global activation does not close Pages/R2/Git and can false-lock users |

## Verification performed

- Macro access regression command passed: `276 passed, 121 warnings, 0 failed`. The warnings were existing Starlette/FastAPI deprecations.

  ```text
  python3 -m pytest -q tests/test_paywall.py tests/test_paywall_pro_gate.py tests/test_public_dashboard_preview.py tests/test_site_access_boundary.py tests/test_research_api.py tests/test_research_vault_page.py tests/test_special_situations_gate.py tests/test_china_special_situations_gate.py tests/test_etfs_gate.py
  ```

- Terminal isolated-clone verification passed 11 entitlement/access Vitest files: `145 passed, 0 failed`. It covered entitlement caching and normalization, settings labels, suite catalog/alerts/tier refresh, Issue Desk and intraday/alerts route gates, portfolio-brief proxy, and watchlist settings. It did not cover the confirmed public R2/bundle disclosures, post-checkout refresh, Founding wire representation, guest CSV behavior, or client tampering.
- Live observations were anonymous only and are timestamped in the receipt ledger. No paid credential, customer row, production environment variable, or Stripe object was used.
- The census PR changes this report only. It deliberately does not change access policy, catalog/prices, Stripe, Prophet scoring, generated UI, public artifacts, or runtime code.

## Final ruling

The launch matrix can be reached with the current architecture: public shells, split payloads, `premium.enforced_early`, feature-bearing entitlements, fresh `/api/me`, and existing server gates. The two non-negotiable moves are to **stop shipping paid bytes to public origins** and to **make one effective entitlement answer reach every consumer**. Prices, Prophet scoring, and the visual system do not need to change to achieve that.

The safe order is containment → byte contracts → payload splits/private transport → authority convergence → claim reconciliation → authenticated live matrix → global activation. Reversing that order would put a tollbooth in front of a road whose side gates are still open.
