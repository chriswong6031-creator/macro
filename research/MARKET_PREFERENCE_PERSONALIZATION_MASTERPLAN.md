# Market-Preference Personalization — masterplan

Status: **W1 shipped** (charting-app PR #202) · W2–W6 open
Operator brief: 2026-07-25 · Adjudicated same day
Scope: cross-repo (Macro Dashboard + charting-app/terminal)

---

## §0 ACCEPTANCE GATES (binding — read before building any wave)

A wave is **not done** unless every line below is true. These are gates, not aspirations;
a masterplan pointer in a spawn prompt is context, not enforcement, so any session
commissioned off this doc must carry these inline.

1. **Fresh end-to-end happy path, zero manual workarounds.** Sign up → land → search →
   watchlist, driven for real. A race you reload around is a bug you own.
2. **Per-step visual crops posted in the PR body** — light + dark + `zh` where the surface is
   bilingual. A claim of "verified" with no artifact does not count.
3. **Entry points actually wired.** A surface reachable only by typing a URL is not shipped.
4. **Bilingual or it does not ship.** Every user-visible string lands in `lib/i18n.tsx`
   (Terminal) or the `t()` macro (macro site) with a real Chinese translation. No English
   fallback text in a `zh` render, and no translated text inside `title=` attributes (CI-guarded).
5. **Null-honest, never silently narrowed.** Whenever a preference HIDES something, the UI must
   say so and offer the undo in place. A user who cannot find `0700.HK` must be told it is their
   own setting doing it. This is the difference between "personalized" and "broken".
6. **No claim of `LIVE` on a delayed feed.** Index values, CME/ICE futures and real DXY need
   licensed real-time data. Anything freely sourced is `DELAYED_15M`. Probe a source before
   committing to it — never assume.
7. **The universe merge is additive.** Any pass that writes `manifest.json` must never shrink or
   overwrite rows owned by `build_universe.py` / `expand_universe.py`. Reference incident:
   2026-07-11, manifest 8,740 → 34, caused by a stale refresh copy.
8. **Never commit generated data.** `terminal/public/data/manifest.json` is tracked and is
   production output. Restore it before committing if a local run touched it.
9. **Tests + typecheck + lint-delta.** New logic carries tests; `tsc` clean; ESLint must not
   exceed the file's baseline count (measure the baseline, don't guess).

---

## §1 The finding that reframes the brief

The operator's brief opens "we're letting onboarded users select which market they want to
emphasize on". The selection exists. **Nothing consumes it.**

`templates/onboard.js` writes `user_metadata.market_focus` (chips `us` / `cn` / `hk` / `ca` /
`global`) and stashes it to `mm.pendingPrefs`; the Terminal's `OnboardingProvider` faithfully
pushes that stash into `user_metadata` on first authed mount. Grepping both repos for a reader
returns **zero consumers**. The write path was complete; the read path did not exist.

So the whole brief reduces to one job — *make the preference load-bearing* — expressed across
six surfaces. That is the spine of the waves below.

Enabling fact: **both properties point at the same Supabase project**, so `user_metadata` is
already a working cross-repo channel. No new API is required for settings to follow a user
between the macro site and the Terminal.

---

## §2 Rulings

### R1 — Nav: fold, don't delete. **SHIPPED (#3582)** — hold released, icon pass landed (#3525/#3528).
Operator, 2026-07-25: *"don't we have that international menu? we can just put the other
countries in there?"* and *"a codex session is working on redesigning menu icons, so wait for
them to push that PR before making edits on the menu layout."*

Ruling: non-home country menus fold into the **existing International dropdown**, they are not
deleted. This beats hard removal because the pages keep nav-level internal links (SEO), a
multi-market user keeps a one-hop path, and "where did China go?" support load never happens.
The user's home market keeps its own top-level slot; the freed slots go to core buttons.

**No menu-layout edits until the icon PR merges.** Re-read `docs/ACTIVE_BUILD_MAP.md` for the
collision before starting.

### R2 — Default landing = home market's macro dashboard, with an override.
`loginDest()` in `onboard.js` returns a hardcoded `start.html`. That is the single hook point.
New users default to their home market's macro page; `start.html` stays available as an explicit
choice, because it was deliberately made the signed-in home on 2026-07-22 and should not be
undone by side effect. Setting lives in the global settings dashboard, Preferences tab.

### R3 — US-only signups default to US-only search; other markets do not.
Operator's asymmetry, implemented verbatim in `defaultEnabledFor()`. **Crypto stays enabled
even for a US-only signup** — it is an asset class spanning every country, not a country market,
and silently removing BTC from a US trader would be a bug rather than a personalization.
Everything is reversible in settings, and the narrowing is disclosed (`autoNarrowed`) rather
than being presented as the natural state of the world.

### R4 — An index belongs to its market.
`^HSI` is hidden for a user who switched Hong Kong off, exactly like `0700.HK`. FX and
commodities are filed under `us` — they belong to no single exchange, and stranding them in
`intl` would hide gold and the dollar index from the trader most likely to want them.

### R5 — Personalization reorders ties; it never overrides what was typed.
The home-market ranking boost is deliberately smaller than one match tier, so a foreign **exact
ticker** always beats a home-market substring. A China-home user typing `NVDA` gets NVDA.

### R6 — Deleting a section deletes the divider, not the holdings.
Rows fall back to the section above. Matches TradingView, and avoids a data-loss trap where
removing a label silently drops symbols.

---

## §3 Waves

### W1 — Preference contract + ranked search + market filters + sections + macro instruments ✅ SHIPPED
charting-app PR #202. `lib/markets.ts`, `lib/useMarketPrefs.ts` (module store, so the settings
pane and search cannot disagree), `lib/macroSymbols.ts`, `ingest/macro_catalog.py`,
`ingest/build_macro_symbols.py`. 704 tests green.

Universe went 8,796 → 8,870: 22 indices, 4 benchmark yields, 13 FX incl. DXY, 15 futures, +20
crypto majors — filling the Forex / Futures / Indices / Bonds search tabs, which had shipped
**disabled** because nothing in the universe carried those `sec` values.

### W2 — Nightly wiring (macro repo) 🔜 next
`app/deploy/terminal-refresh.sh` calls `ingest/build_macro_symbols.py` after
`build_universe` / `expand_universe`. Note `charting-app/ingest/terminal-refresh.sh` is a
**stub** — the canonical script lives in this repo. Gate: after one nightly, the live manifest
shows the macro rows and the equity count has not dropped.

### W3 — Premade per-market watchlists
Seed on first sign-in from `prefs.markets.home`, with sections pre-built (the section model
from W1 makes this possible). US → mega-caps + one leader per sector; CN → A-share majors by
board; HK → HSI heavyweights + southbound favourites; CA → TSX banks / energy / materials.
Multi-market picks get one list per market. Seeding must be idempotent and must never clobber
a list the user has edited.

### W4 — Settings surfaces
- New **Terminal** subpage in the global settings dashboard (`theme.js` `_renderSDash`, which
  already has an Account / Billing / Usage / Preferences / Sync rail).
- Market focus + home market move into Preferences (today it holds only theme + language, and
  `prefs` there is a *different nested shape* from top-level `market_focus` — unify them).
- Embed the shared account panel in the Terminal. `account.js` is **already written as a
  dual-mode component** (standalone + embed) — but `MM_API` points at `app.mastermind-x.com`,
  where `/api/account` currently 404s. Resolve that before assuming the embed works.

### W5a — Nav fold ✅ SHIPPED (#3582)
`templates/nav_market.js`, loaded by `account.js` (already on every page via `theme.js`), folds
the non-home country dropdowns into International under an "Other markets" eyebrow. Client-side
by necessity — the home market is per-user and the nav is baked once per page — which also keeps
the served html complete for crawlers, the SEO property R1 was protecting. No home market ⇒ DOM
untouched.

Two things worth carrying forward:
- **Restore-then-fold, never fold-in-place.** A folded country lives *inside* the International
  menu, so swapping a dropdown back where it currently sits nests it permanently: `us→cn→hk`
  left the rail with no country at all and sign-out never restored. Restore the whole
  `.nav-links` innerHTML from a pristine snapshot each time.
- **`theme.js` binds the mobile accordion per node** at DOMContentLoaded, so any innerHTML
  restore drops those handlers. Re-bind after.

Also closed a live contract split: #3560 shipped a desk-prefs pane writing ONLY `market_focus`
while the Terminal reads `markets` and treats it as authoritative — so a macro-side edit was
silently ignored for anyone who had used the Terminal. `_sdSaveDesk` now writes both.

### W5b — Market-aware landing (open)
`loginDest()` in `onboard.js` returns a hardcoded `start.html`; point it at the home market's
macro page with `start.html` kept as an explicit choice (R2). Deliberately NOT bundled with the
nav fold — `onboard.js` was the other file #3560 rewrote and deserves its own diff.

### W6 — Data coverage, second pass
- **Chinese commodity futures** via Sina (`hq.sinajs.cn`) — probed working, incl. the night
  session: AU/AG/CU/AL/ZN/NI/RB, DCE iron ore, INE crude.
- **FRED macro series** (DFII10 and friends) via the keyless `fredgraph.csv` endpoint — probed
  working. These are *daily published series*, not ticks; they belong in the Economy tab and
  must never be dressed as live prices.
- Non-US index futures where a lawful free source exists.
- Replace the remaining `window.prompt` calls (new list, rename list, rename section) with the
  TradingView-style modal in **one consistent pass** — half-converting is worse than either end.

---

## §4 Source-honesty table (probed 2026-07-25, not assumed)

| Class | Source | Basis | Note |
|---|---|---|---|
| China A-shares, CN indices | Tencent `qt.gtimg.cn` | **LIVE** | Indices share the `sh######`/`sz######` codes — already wired |
| Crypto | Coinbase (via Quote Hub) | **LIVE** | ~400 USD pairs listed; curated majors shipped |
| CN commodity futures | Sina `hq.sinajs.cn` | **LIVE** | Probed incl. night session; W6 |
| US equities | Polygon (via Quote Hub) | DELAYED_15M | Existing |
| Indices, FX, DXY, futures, yields | Yahoo spark | **DELAYED** | 20-symbol batch cliff — a 23-symbol request returns *zero*, not a partial |
| FRED series | `fredgraph.csv`, keyless | Daily publish | Not a tick feed; do not present as one |
| Real-time CME / ICE / index values | — | **Licensed** | Not held. Do not claim `LIVE`. |

---

## §5 Traps found the hard way

- **Stale local checkouts lie.** `charting-app`'s primary checkout sat on a July-13 branch;
  `SearchModal` was 387 lines there vs 652 on `origin/master`. Always work from a fresh worktree
  off the remote default (`master` here, not `main`).
- **The local `manifest.json` fixture is 34 symbols; production is 8,796.** Verify market logic
  against a production copy or a fixture cut from one, never against the local file.
- **Turbopack served a stale `globals.css` and a stale JS chunk across edits** — a section header
  rendered 1186px tall with an unstyled SVG, and a `ReferenceError` persisted for a variable that
  existed on disk with `tsc` clean. When the browser contradicts `tsc`, suspect the cache: stop
  the server, `rm -rf .next`, restart.
- **`tsc ... | head` masks the exit code** (you get `head`'s). Redirect to a file and check `$?`.
- **Browser console messages persist across navigations** — a fixed error keeps reappearing.
  Cross-check against `preview_logs` and the live DOM before chasing it.
- **The Terminal caches the manifest in IndexedDB (`mm-data-cache`) *and* the HTTP cache.**
  Swapping the file locally is not enough; clear both and restart.
- **React strict mode double-invokes state updaters** — a `persist()` side effect inside
  `setState` double-writes the account. Derive from current state instead.
- **Bulk edits must not be loops over a single-item toggle**: each call derives from the same
  snapshot, so only the last survives. Give the store a real bulk setter.
