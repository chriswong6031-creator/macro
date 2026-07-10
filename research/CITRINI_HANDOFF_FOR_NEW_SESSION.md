# Citrini Intelligence Desk — cold-start handoff for a new session

**Purpose of this file:** everything a fresh Claude session needs to BUILD the Citrini ingestion, with no memory of the prior conversation. Read this first, then the two design docs it points to. The operator will be present in that session to place the login (an interactive step no agent may do).

---

## 0. One-paragraph orientation

The operator subscribes to **CitriniResearch Institutional** ($50k/yr, **with redistribution rights**) — a thematic hedge-fund research product. We are building a pipeline that **mirrors their Citrindex portfolio data into our own backend nightly**, computes analysis on top (what they're adding/trimming, de-risking, theme migration), rebuilds a private UI, and feeds consolidated metrics into our Neural Web as a **graded external evidence source** (they get graded, not blindly trusted). This is NOT public republication — everything Citrini-derived is display/context tier behind operator auth. The authorization basis is the operator's own paid account with redistribution rights; **no agent ever enters or handles the credentials** — the operator places a login session on the runner and our code reads it.

## 1. Read these two docs before writing any code (they are on `main`)
- **`research/CITRINI_INGESTION_ARCHITECTURE_BY_FABLE.md`** — the recon-grounded build spec (transport/auth/data model verified via an authenticated browser session 2026-07-09; the CITR-0..5 wave table; the derived-metrics list; fences). THIS IS THE PRIMARY SPEC.
- **`research/THEMATIC_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §7** — the parent CITR family design + the rulings that fence it (R-TIL-5 LLM-extraction-with-citations, R-TIL-7 Citrini-is-graded-not-trusted).

## 2. The verified facts you're building against (don't re-recon)
- **No JSON API.** citrindex.com is a Next.js App Router app; all data is React Server Component flight payloads (`text/x-component`), hydrated into client state. REST/tRPC probes 404. → **The robust extraction path is a headless browser (Playwright/Chromium) that renders the page and reads the DOM/client-state**, NOT raw flight-parsing (the flight format is deploy-versioned and brittle).
- **Auth = BetterAuth session cookie** (`/api/auth/get-session` returns `{session,user}`). The runner needs an **operator-placed logged-in browser profile / session cookie**. Sessions expire → build a 401/redirect detector that ALERTS the operator to re-place; never auto-auth.
- **URL map:** `/dashboard/portfolios/{id}/{tab}` with tabs `performance|chart|holdings|changes|contribution`; 2 portfolios (`ndqEpbNI`=Citrindex flagship, `Ia-Dh2Hg`=26TF26); `/dashboard/baskets/{id}` (188 baskets); plus `/realtime /macro-trades /baskets-ranking /watchlists`.
- **The team feed = the in-app "Intraday Alerts"** on the Performance view: timestamp + status + theme + free-text rationale + an actions table (ticker → `Initiate Long`/`Decrease Long`/`Increase Short`/`Close`/`Adjust Cash`). This is the qualitative + exact-trade gold. (Confirm with the operator whether there is ALSO a separate off-platform channel.)
- **Cadence:** portfolio snapshot finalizes at **4:00 PM ET close**; intraday alerts fire ad hoc during market hours; the Changes view is date-range queryable (the clean incremental key). → Pull schedule: nightly full snapshot after **4:15 PM ET** + an intraday poller (~every 15–30 min, 09:30–16:00 ET) for alerts.

## 3. What the OPERATOR does in the session (the one blocker for CITR-0)
The operator logs into citrindex.com on the Mac Studio runner (or exports the BetterAuth session cookie) into a runner-local, **gitignored** profile directory — proposed `~/.citrini/session`, resolved via env `CITRINI_SESSION_DIR`. **You build the reader; the operator places the value.** Confirm the exact path with the operator at the start of the session.

## 4. The build (CITR-0 first; each wave = branch off fresh origin/main → PR → same-day squash-merge)
| Wave | Build | Gate |
|---|---|---|
| **CITR-0** | `collectors/citrini_crawler.py` (headless, reads the operator profile) + `engine/citrini/normalize.py` + `data/citrini/` schema + **initial full pull** of current state (all portfolios × tabs + 188 baskets + rankings + macro-trades) | operator session placed (§3) |
| **CITR-1** | daily incremental (Changes-since + new Intraday Alerts + 4:15 PM snapshot) + intraday poller + `engine/citrini/events.py` (deterministic change/action-tag event stream) + session-expiry alerting via `scripts/notify.py` | CITR-0 |
| **CITR-2** | `engine/citrini/crosswalk.py` — their 188 baskets ↔ our `config/theme_crosswalk.yml` theme ids; their memberships become `source: citrini` edges into the TIL pathways graph; holdings-vs-our-basket diffs → operator-reviewed membership candidates | CITR-0 + TIL W2 (already merged) |
| **CITR-3** | `engine/citrini/metrics.py` (de-risking detector, conviction, theme-weight migration, add/trim ledger, active-vs-drift, house-vs-Citrini contradiction) + **our rebuilt UI** `site/citrini/*.html` (operator-auth) | CITR-1 |
| **CITR-4** | substack LLM extraction (R-TIL-5: exact-substring citations, char-span validated) → theme thesis ledger `source: citrini` | operator picks substack access path (different domain from citrindex — needs its own session/email/manual) |
| **CITR-5** | NW wiring: `citrini` block in `thematic_state`, `read_citrini_book` ask_brain tool, mastermind_context, contradiction records, qledger `citrini_*` grading | TIL W5 (merged) + CITR-1..3 |

## 5. HARD FENCES (violating any = the build is wrong)
- **No secret in git, ever.** The session cookie/profile stays runner-local + gitignored. Raw crawl HTML/snapshots → R2 (audit/replay), NEVER git; only small normalized structured rows → `data/citrini/`.
- **Off the render critical path.** The crawler is its own launchd/cron lane, not the 67-min nightly render.
- **Display/context tier only.** Everything Citrini-derived carries a `not_a_signal` / `is_context_only` authority block. **Positioning is NEVER fused into any score** (Signal Commons law). Citrini is a graded evidence source — every change event → qledger `citrini_*` claim families, graded before believed (DannyTrades law).
- **LLM = extraction-only with receipts.** For the substack wave, the LLM structures their prose into records carrying exact-substring citations (char-span validated). No LLM-originated signals/scores.
- **Display scope = operator-auth surfaces + NW synthesis only.** Not public republication (despite redistribution rights — the operator's choice). Derived metrics may surface more freely than verbatim content.
- **Crawl politely** (serialized, backoff); NW always reads OUR mirrored copy, never their live site.

## 6. House laws the new session must follow (project standing rules)
- Branch off **fresh `origin/main`**; finish commit → push → PR → **same-day squash-merge**. Work in a worktree, never the main checkout's git state.
- Before proposing, read `docs/ACTIVE_BUILD_MAP.md` + `research/DO_NOT_REBUILD.md` (don't rebuild in-flight/killed topics).
- CI gotchas: bilingual EN/ZH UI, no translated text in `title=` attributes; the word "validated" is CI-banned in user-facing text; if you register a `config/synapse.yml` artifact you must regen `docs/SIGNAL_BUS.md` (`python -m scripts.gen_signal_bus_doc`) + bump the count pin in `tests/test_signal_bus_doc.py`; run **bare** pytest before every push (a piped exit code hides failures); re-run the count test after any rebase even if it merged cleanly.
- Model routing: Sonnet builds, Opus reviews, the main loop plans/adjudicates/merges.
- UI restraint: build SIMPLE operator-usable surfaces — no crowded jargon dashboards. Dense metrics belong on the admin/signal-lab Citrini pages, not a daily-use front page.

## 7. First actions for the new session
1. Confirm the runner session-profile path with the operator (`~/.citrini/session` / `CITRINI_SESSION_DIR`).
2. Read the two design docs (§1) + `docs/ACTIVE_BUILD_MAP.md` + `research/DO_NOT_REBUILD.md`.
3. Build CITR-0 (crawler + normalize + full pull) on a fresh branch; the operator places the session; run the initial full pull; verify `data/citrini/` populates; PR → merge.
4. Proceed CITR-1 → CITR-3; hold CITR-4 until the operator picks the substack path; CITR-5 wires it into Neural Web.

*(Not urgent per the operator: the handful of free API keys for other TIL leads — GRANTS_GOV / SAM / CENSUS / runner ANTHROPIC — are a separate, later task, unrelated to Citrini.)*
