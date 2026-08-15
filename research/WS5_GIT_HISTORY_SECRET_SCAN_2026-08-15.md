# WS-5 / GATE-5 — Full Git-history secret scan

**Date:** 2026-08-15
**Workstream:** WS-5 (P0 launch gate; isolated from other Wave-1 lanes)
**Scanner:** gitleaks 8.30.1 (`gitleaks detect --log-opts="--all" --redact`)
**This note contains no secret values.** Hits are referenced by repository, commit SHA, and `file:line` only.

---

## 0. Verdict

**No first-party live secret (Stripe, GitHub PAT, Supabase service-role, private key, Slack, AWS) was found in current `HEAD` of any of the three repositories.**

Gitleaks reported **11,603 findings** across full history (macro 11,578 · Mastermind 9 · terminal 16). Every finding was triaged. All but one class are false positives (generated IDs, localStorage keys, named `FAKE_*` fixtures, public IndexNow / Chrome-extension keys, documentation).

**One credible detector class remains an operator decision, not a code change:**

| Credential | Where | HEAD state | Rotation |
|---|---|---|---|
| Amplify ETF holdings Google/Firebase web key (`gcp-api-key`; env name `AMPLIFY_FIREBASE_KEY`) | macro `collectors/etf_holdings.py` and `scripts/backfill_etf.py` at `59a6b34ce3da` (2026-07-13, #2487) | Removed from source in `5d3088c386d5` (2026-07-18, #2975); now `config.secret("AMPLIFY_FIREBASE_KEY")` | **OPERATOR ACTION REQUIRED** — confirm whether this is Amplify's published fund-page JS key (third-party; we cannot rotate) or a key minted in a Mastermind-owned Google Cloud project (rotate and prove the old value 401s). This session has no GCP/Firebase console access. |

Do **not** rewrite Git history. The #2975 removal is the correct non-history-rewrite remediation; it already landed. No additional source PR is required for this lane.

GATE-5 is **scan-complete and triaged**. It is **not fully closed** until the operator records the Amplify-key ownership/rotation decision above.

---

## 1. Method

| Item | Value |
|---|---|
| Tool | gitleaks **8.30.1** (official `linux_x64` release) |
| Command | `gitleaks detect --source <repo> --log-opts="--all" --redact --no-banner --report-format json --exit-code 0` |
| Config | default rule set (no repo `.gitleaks.toml`) |
| Repos | `macro` working clone after `git fetch origin --prune --tags`; bare mirrors of `Mastermind` (`master`) and `mastermind-terminal` (`master`) |
| Tips scanned | macro `origin/main` `6685df10a3e0`; Mastermind `d3d6a6cae356`; terminal `82cb8cbf799f` |
| Redaction | `--redact` on the scanner; Secret/Match fields stripped before any report was read; raw JSON overwritten and deleted. Nothing from `/tmp/ws5-scan/reports/*.raw.json` is in this repository. |

### Positive control (instrument is live)

A throwaway repo with invented Stripe / Slack / PEM fixtures produced **3 findings** (`stripe-access-token`, `slack-bot-token`, `private-key`). AWS documentation example keys (`AKIAIOSFODNN7EXAMPLE`) are allowlisted by gitleaks and correctly produced a null — that null was discarded.

### Scan bounds (absence claims)

| Repo | `git rev-list --all` | gitleaks "commits scanned" | `rev-list --all --no-merges` |
|---|---:|---:|---:|
| macro | 13,821 | 13,415 | 13,475 |
| Mastermind | 402 | 358 | 359 |
| mastermind-terminal | 1,186 | 977 | 985 |

Gitleaks' `--log-opts="--all"` walk matches **non-merge** history to within ~1%. Merge commits are the residual gap. Unique file blobs still appear via a parent, so a secret introduced only in a merge-conflict resolution would be the uncovered case. No path filter and no `--max-target-megabytes` cap were applied. Macro scanned **~61.35 GB** of blob text in 54m19s.

**Not a gitleaks hit, recorded as a bound:** the same #2975 commit also moved Eastmoney page-JS tokens (`EASTMONEY_UT_TOKEN`, `EASTMONEY_WEB_TOKEN`) out of `collectors/china_flows.py` and `collectors/china_property.py`. Those literals did not match a default gitleaks rule. They are the same class as the Amplify key (third-party public-page tokens, now env-only).

---

## 2. High-signal findings (every row)

| Repo | Commit | File:line | Detector | Verdict | Remediation |
|---|---|---|---|---|---|
| macro | `59a6b34ce3da` | `scripts/backfill_etf.py:159` | gcp-api-key | **Credible.** Default `api_key=` fallback was a Google `AIza…` web key for Amplify's Firestore holdings feed. | Removed from HEAD in `5d3088c386d5` (#2975). History still contains it. **Operator: confirm ownership / rotate if first-party.** |
| macro | `59a6b34ce3da` | `collectors/etf_holdings.py:475` | gcp-api-key | Same literal, same commit, collector path. | Same as row above. |
| macro | `be9d58ff6ef7` | `tests/test_seo_search_console.py:79` | private-key | **False positive.** Named test fixture (`BEGIN PRIVATE KEY`) whose comment says the body must never be emitted by the module. | None. Still on HEAD; keep as a redaction fixture. |
| macro | `49409865b805` | `research/momoedge/alerts_infra_spec.md:207` | jwt | **Expected-public.** Spec line labeled "Anon key" / "public anon; not a secret". JWT payload `role=anon` (project ref `pojiqfeemksvocnaellu`, distinct from the product project). | None. Do not treat as service-role. |
| terminal | `ba932610a073` | `apps/ios/MastermindTerminal/AppConfig.swift:20` | jwt | **Expected-public.** Assignment `supabaseAnonKey`. JWT payload `role=anon`, project ref `fsldfzlxyavsuwqbceod`. Still on HEAD. No `service_role` in that file. | None. Client anon key; RLS is the control. |

No `sk_live_` / `sk_test_` / `whsec_` / `ghp_` / `xoxb-` / `SERVICE_ROLE` / `sb_secret_` (except named `FAKE_*` fixtures) detector family fired.

---

## 3. Mastermind — all findings

9 hits / 2 files / 3 commits. All **false positive**.

| Commit | File:line | Detector | Verdict | Remediation |
|---|---|---|---|---|
| `ef5a957cf01c` (and squash `0e96e3392ee5`) | `tests/test_secret_redaction.py:35,36,37,122` | generic-api-key | Named `FAKE_SB_SECRET`, `FAKE_HEX_KEY`, `FAKE_POLYGON_KEY`, and a short `sb_secret_` shape used to prove a length rule. | None. Intentional fixtures; still on HEAD. |
| `bde5511723d9` | `tests/fixtures/market_view/regime_snapshot_incident.json:353` | generic-api-key | JSON field `"key": "B4_absorption"` next to `"label": "Cross-asset absorption"`. Metric id, not a credential. | None. Still on HEAD. |

---

## 4. mastermind-terminal — remaining findings

16 hits / 7 files / 8 commits. The JWT row is in §2. The rest are **false positive**.

| Commit(s) | File:line | Detector | Verdict | Remediation |
|---|---|---|---|---|
| `42df3dc25fb4`, `6c26ee7c5db7` | `terminal/components/TerminalShell.tsx` | generic-api-key | `const WLS_MIGRATED_KEY = "wls:migrated"` (localStorage flag). | None. |
| `42df3dc25fb4`, `6c26ee7c5db7` | `terminal/e2e/watchlist-server-migration.spec.ts:12` | generic-api-key | `const MIGRATED_KEY = "wls:migrated"`. | None. |
| `9293985e70f6`, `8a1e3d9531e8` | `terminal/lib/__tests__/issueDeskRoutes.test.ts:13,31,35` | generic-api-key | Test `idempotency_key` field. | None. |
| `9293985e70f6`, `8a1e3d9531e8` | `terminal/test-fixtures/options_issue_desk_fixture.json:20` | generic-api-key | Fixture `idempotency_key`. | None. |
| `65dac2624719` | `docs/MARKET_STRUCTURE_CORE_MASTERPLAN_2026-08-01.md:231` | generic-api-key | Prose: "REST API, Snowflake FTP delivery". | None. |
| `52a2178bc1ce`, `3a0afabb50e4` | `terminal/components/DrawingSidebar.tsx:78` | generic-api-key | `const FAVORITES_STORAGE_KEY = "drawing:favorites"`. | None. |

---

## 5. macro — grouped triage (all 11,578 hits)

`generic-api-key` dominates (11,574). High-signal rows are in §2. Every other unique `(file, detector)` is classified below. Finding counts include the same literal recurring across nightly data commits.

### 5.1 Generated ledgers / site artifacts — false positive

High-entropy **entity keys, theme keys, chart keys, claim ids, fingerprints, IndexNow URL hashes**. Not credentials.

| n | File | Exemplar commit | What matched |
|---:|---|---|---|
| 7276 | `data/qledger/claims.jsonl` | `002fd5ce1d9f`…`f8b1173a7c68` (47 SHAs) | `item_id` / claim fields next to desks and `bench: SPY` |
| 1771 | `site/subsector/b-obesity-glp1.html` | 885 SHAs | `DETAIL` / `CHART_KEY` baked JSON |
| 480 | `site/funddata/polen.json` | 240 SHAs | 13F theme / holding keys |
| 438 | `site/allocationdata/special_situations.json` | 120 SHAs | allocation `source_url` query + ids |
| 336 | `site/funddata/casdin.json` | 84 SHAs | same family as other `funddata/*.json` |
| 170 | `data/vector/regime_latest.json` | 85 SHAs | regime `"key"` / `"label"` |
| 154 | `site/leader_radar.html` | 26 SHAs | `data-chip-key="monthly_rsi_80"` |
| 132 | `site/marketdata/basket_confluence.json` | 47 SHAs | `basket_id` / `chart_key` |
| 121 | `site/funddata/giverny.json` | 121 SHAs | fund-holdings keys |
| 111 | `site/funddata/soros.json` | 111 SHAs | fund-holdings keys |
| 90 | `site/funddata/berkshire.json` | 90 SHAs | fund-holdings keys |
| 71 | `site/funddata/viking.json` | 71 SHAs | fund-holdings keys |
| 70 | `site/funddata/bakerbros.json` | 70 SHAs | fund-holdings keys |
| 65 | `site/funddata/gates.json` | 65 SHAs | fund-holdings keys |
| 63 | `site/funddata/scion.json` | 63 SHAs | fund-holdings keys |
| 25 | `site/marketdata/index_leadership.json` | 25 SHAs | basket/stage keys |
| 15 | `data/us_sector_rotation/forward_log.jsonl` | 15 SHAs | `"key": "xlb"` sector ids |
| 15 | `data/cycle_pattern/lattice/batch2.json` | `0cd6295462a2` | lattice cell keys |
| 12 | `data/rates_command/latest.json` | 7 SHAs | rates-command `"key"` / `"direction"` |
| 11 | `data/us_sector_rotation/latest.json` | 11 SHAs | sector ids |
| 11 | `data/marketing/ad_central/assignments.jsonl` | `40e793a4a440` | `arena_id` / `unit_key` / `creative_id` |
| 9 | `data/marketing/seo/indexnow_state.json` | 4 SHAs | public IndexNow URL→key map |
| 6 | `data/qbus/audit_latest.json` | 2 SHAs | audit entity keys |
| 6 | `data/qbus/audit_run_status.json` | 2 SHAs | same |
| 3 | `data/marketing/x_intel/exemplar_store.json` | `bb0e422f6351` | tweet id / URL, not a token |
| 2 | `data/stock_identity/partition/partition_manifest_v1.json` | `7b51d82bb5c6` | partition ids |
| 2 | `data/reflexes/cortex_attention/firings.jsonl` | `5a29572e6dec` | `claim_id` / `trigger_key` |
| 2 | `data/marketing/share_cards/fingerprints.json` | `0d7ad0d95ec3` | content hashes |
| 1 each | `data/international_macro/{EZ,IN,KR,GB,JP}_latest.json` | `d94a85dd096c` | series `"key"` / `"label_en"` |
| 1 | `data/marketing/ad_central/outcomes.jsonl` | `40e793a4a440` | assignment ids |
| 1 | `data/neuralweb/marketing_state.json` | `b53316fb57c8` | prose ("API") |
| 1 | `data/sector_cycles/narratives.price_c4414dcb.json` | `896471652cea` | narrative/epoch keys |
| 1 | `data/index_leadership/snapshots.jsonl` | `7d8b80523c70` | `"key":"insurance"` |
| 1 | `data/regime/latest.json` | `dd3d94c6b87e` | `"key"` + "Cross-asset absorption" |
| 2 | `data/stock_identity/expert_events/family_registry.json` | `01cc418c1472` | family ids (file absent on current `origin/main`) |

### 5.2 Expected-public client keys — not secrets

These are the product Supabase **publishable / anon** key (`sb_publishable_…` / JWT `role=anon`, project `fsldfzlxyavsuwqbceod`). Comments on the matching lines say the publishable key is public and RLS enforces isolation. **Not service-role.**

| n | File | Exemplar commit | Notes |
|---:|---|---|---|
| 6 | `site/theme.js` | `3a49b4646e14` | comment: "publishable key is PUBLIC by design" |
| 5 | `config.yml` | `2571ccd87ff7` | `supabase.anon_key` |
| 3 | `site/committee.html` | `674aee4609f1` | `window.SUPABASE_CFG.anonKey` |
| 2 | `site/watchlist.html` | `674aee4609f1` | same |
| 1 | `app/main.py` | `ededc062dbf3` | `SUPABASE_ANON_KEY` env default |
| 1 | `site/supabase.js` | `788f69404ad1` | vendored client bundle (minified) |
| 1 | `templates/supabase.js` | `ad21722f44b6` | paired template copy of the same bundle |

### 5.3 Source / tests / docs — false positive

| n | File | Commit | What matched |
|---:|---|---|---|
| 12 | `engine/rates_inflation_command.py` | `2f60b7cb949a` | `"key": "H2_breakeven_momentum"` |
| 7 | `engine/signal_frontier_docket.py` | `e5ef4a957e08` | Oxford Academic URL `guestAccessKey=` query |
| 7 | `research/signal_lab_frontier_phase0_2026-07-06.json` | `e5ef4a957e08` | same URL |
| 5 | `config/compiled_kill_registry.yml` | `3093f6aad91f` | kill-registry topic prose |
| 3 | `tests/test_market_memory_operating_cortex.py` | `15b722201db5` | `registration_key="synthetic:cortex…"` |
| 3 | `engine/biocatalyst/activation.py` | `3eb95c8096db` | object-store key argument |
| 2 | `engine/stock_identity/replay/naive.py` | `546af36eafc6` | `family_key == "low20d_bounce"` (not on current HEAD) |
| 2 | `engine/institutional_census/storage.py` | `5abf126cc1fa` | `credential_namespace = "INSTITUTIONAL_13F_R2"` (namespace name, not a secret) |
| 2 | `engine/prophet_arena.py` | `242aafda0dc7` | `key="C4_dispersion_cap"` |
| 2 | `templates/hk.html.j2` | `d39e6e81a108` | comment "VM key `hk_1d_velocity_desk`" |
| 1 | `agentos/decisions/DEC-CN-PB3-A-PRIMARY-B-CORROBORATIVE.md` | `6419ca5ed574` | frontmatter `key: PB3-A-PRIMARY-B-CORROBORATIVE` (not on current HEAD) |
| 1 | `research/theme_graph/w3a_finviz/receipts/01_map_page.html` | `c4a4c2f858cf` | captured third-party `integrity=` / CDN URL (not on current HEAD) |
| 1 | `browser/momoedge_capture/manifest.json` | `60bb11a27283` | Chrome extension **public** key (`"key": "MIIBIjAN…"`) |
| 1 | `tests/test_research_factory_market_memory.py` | `dfd6a982d568` | `trial_key="synthetic:spy…"` |
| 1 | `tests/test_market_memory_forward_store.py` | `45b4100e7db1` | same |
| 1 | `app/deploy/market-memory-options-dropin-migration.sh` | `eb3aa9ad8efa` | `MM_LEGACY_API_DROPIN_SHA256` (content hash pin) |
| 1 | `tests/test_options_issue_desk_api.py` | `d140d09eda97` | test `idempotency_key` |
| 1 | `tests/test_nav_hover_bridge.py` | `943b202ca3e8` | `NAV_RELEASE_KEY` cache-bust constant |
| 1 | `engine/fundamental_forensics/disclosure_bundle.py` | `ad5f0d044f46` | `DISCLOSURE_BUNDLE_LATEST_KEY` object name |
| 1 | `scripts/research/build_company_intelligence_golden_corpus.py` | `f135056b9879` | golden-corpus `"key": "claim.citations_pending…"` |
| 1 | `research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json` | `f135056b9879` | same |
| 1 | `tests/test_fundamental_forensics_attested_history_operator.py` | `59478c96de6a` | operator-key name in a test |
| 1 | `site/sector_central_china.html` | `8691f7e662d3` | `localStorage` key `cnfw:btbl:sort` |
| 1 | `templates/baskets_china_factorwatch.html.j2` | `6f5f202dfe82` | same |
| 1 | `templates/sector_central_china.html.j2` | `6f5f202dfe82` | same |
| 1 | `site/baskets_china.html` | `064cd670f4fb` | same |
| 1 | `site/baskets_china_ths.html` | `064cd670f4fb` | same |
| 1 | `templates/baskets_china.html.j2` | `cc06f25f9a07` | same |
| 1 | `app/deploy/biocatalyst-setup.sh` | `3eb95c8096db` | usage text `<Cloudflare account id>` (placeholder) |
| 1 | `research/CAPITAL_STRUCTURE_COMPANYFACTS_INTAKE_DOCKET.md` | `124773b368f3` | docket prose |
| 1 | `tests/test_billing_emails.py` | `a38833eb2ce8` | Stripe **price lookup_key** `essential_2026_v2_monthly` (public catalog id) |
| 1 | `engine/fundamental_forensics/source_sync.py` | `2b69de87469a` | `object_key=` store path |
| 1 | `engine/marketing/indexnow.py` | `1dc83564d0f8` | `INDEXNOW_KEY` — comment: public on purpose (`site/<key>.txt`) |
| 1 | `tests/test_marketing_press_feeds.py` | `78073f032132` | fixture `next_page_token` |
| 1 | `tests/test_rates_command.py` | `2f60b7cb949a` | `"key": "D1_dots_vs_market"` |
| 1 | `tests/test_context_index_privacy.py` | `014433eae719` | **fake** `AIzaSyFAKE0TEST…` used to prove the CXI tripwire; comment forbids real credentials |
| 1 | `reports/rotation-time-machine-extended-patterns.md` | `eb5d3229781d` | "artifact keyed by sector ETF" |
| 1 | `scripts/china_policy_events_phase0.py` | `66be2ff5b7c2` | `key` loop variable |
| 1 | `research/SIGNAL_LAB_FRONTIER_PHASE0_2026-07-06.md` | `e5ef4a957e08` | same Oxford URL as the docket |
| 1 | `engine/options_stamp.py` | `5c17ef46385a` | docstring "keys `opt_skew`, `opt_skew_5d_chg`" |
| 1 | `scripts/gex_polygon_panel.py` | `dd8059962274` | comment "awaiting the Polygon API key" — no literal (file absent on current HEAD) |

---

## 6. Operator action required

1. **Amplify / Google web key (`AMPLIFY_FIREBASE_KEY`)** — the only gitleaks-credible secret class.
   - History window: `59a6b34ce3da` (2026-07-13) through the parent of `5d3088c386d5` (2026-07-18).
   - #2975 already removed the source literal and wired GitHub Actions `secrets.AMPLIFY_FIREBASE_KEY`.
   - If the value is Amplify's published fund-page JS key: record that and close. We do not own rotation.
   - If the value was minted in a Mastermind Google Cloud / Firebase project: rotate, restrict the new key (HTTP referrer + API allowlist), update the GitHub secret / VPS env, and prove a request with the old key is rejected.
   - This session cannot perform that proof (no GCP console, and the live value must not be replayed from git).
2. **Do not `git filter-repo` / force-push.** History rewrite is out of scope and would invalidate every SHA in this note.
3. Optional follow-up (not this lane): add a committed `.gitleaks.toml` allowlist for the named `FAKE_*` fixtures and the public IndexNow / Chrome-extension / Supabase publishable shapes so a future GATE-5 re-run is quiet. Not required for triage.

No other credential in this scan is this session's to rotate.

---

## 7. Reproduction

```bash
# gitleaks 8.30.1
gitleaks detect --source <macro|Mastermind.git|mastermind-terminal.git> \
  --log-opts="--all" --redact --no-banner --report-format json --report-path /tmp/out.json
# Then drop Secret/Match before reading the JSON.
```

Positive-control fixture (invented Stripe/Slack/PEM shapes) must still fire before a clean repo is trusted.

---

## 8. What this note is not

- Not a working-tree-only scan. `--log-opts="--all"` walked reachable history.
- Not a claim that every third-party page-JS token on the internet has been rotated.
- Not a history rewrite.
- Not a merge of any other Wave-1 workstream.
