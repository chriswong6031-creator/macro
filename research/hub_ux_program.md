# Hub UX Program — front-page UI/UX overhaul (2026-07-10)

Operator ask: full UI/UX sweep of mastermind-x.com (the hub / `site/index.html`), fix bugs,
improve responsiveness, enhance the settings pane, add features, add wow factor.
Method: 6-lane multi-agent review (visual / UX+features / responsive / a11y+i18n / bugs /
settings pane) over a 28-shot matrix (5 viewports × dark/light × EN/ZH × key states),
then waved build. Perf substrate: PR #2079 (pause-aware globe, quality governor, `__gdPerf`).

## Shipped waves (this PR)

- **W0 bugs/a11y/i18n** — honest alerts chip ("5 of 12 signals") + in-place expander +
  visible-cut dedupe; hero tagline "backtested" → "disciplined" (house epistemics; note
  `check_validated_claims` tokens don't cover "backtested" — candidate follow-up, mind
  legitimate negations on methodology pages); pebbles `tabindex=-1` (were focusable inside
  `aria-hidden`); `<html lang>` synced on language switch (+ MutationObserver fallback);
  `#gd-live` announces in the active language; lang toggle keyboard-operable; light-theme
  `.pill` WCAG contrast override (48% mix ≈ 5.08:1); ZH statics (中国行业, 美元增长溢价 ·
  风险偏好, 截至 date); `viewport-fit=cover` + safe-area insets (bottom-sheet tooltip,
  `.af` toast, body padding); ≥44px pebble hit areas (≤560 `::after` inset −10px — note:
  this consumes the accent-underline pseudo on mobile); dead `.gd-cluster`/`buildCluster`
  removed.
- **W1 responsive** — ≥1600px: `.wrap` 1180→1360, globe stage cap 640→740; 769–1024
  tablet band: features grid 3-col, globe `min(80vw,560px)`.
- **W2 UX/features** — globe hint chip (first visit, `gdHintSeen`); eyebrow next-bell
  countdown + data-vintage chip (freshness honesty vs the ticking "Live" clock); sign-in
  affordance `#hub-signin` (MDXAuth-gated); rotation snapshot strip
  (`data/sector_central/calls.parquet`, omit-if-stale>7d); latest-report teaser on the
  Reports card (`build_reports` front-matter); regime-changed badges (US-only detectable
  from the home alert feed today); standout ticker chips (US/CN/HK from committed
  `site/factordata/*_standouts.json`). Data-driven sections materialize with the next
  nightly render — the committed page only carries static-safe transplants.
- **W4 settings pane** — 3-way **Auto/Light/Dark** with auto-theme lifted site-wide into
  theme.js (was index-only; re-derives on boot when `themeAuto=1`, rewrites `theme` so
  head pre-paint scripts agree); **Reduced effects** (`fx=min` → `html.fx-min` +
  `__gdSetTier(0)`/`__gdSetMotion(false)` globe API, governor pinned); **Live prices**
  on/off (`liveOff` → `LiveQuotes.pause/resume`, row hidden where LiveQuotes absent);
  **Default view** Markets/Features (hub-only row, `hubView`); pane aria/focus fixes +
  attribute-driven i18n. theme.js/theme.css/live.js are PAIRED templates — token-preserving
  sync (`check_template_site_sync --fix` keeps the baked `SUPABASE_CFG`).

## Gated / follow-ups

- **W3 wow (OPERATOR MOCKUP GATE — pick pending)**: A "Living Planet" (daylight blue-marble
  light globe, scroll-coupled moon-set, 6s auto-tour of market scorecards) · B "Command
  Deck" (≥1400 regime/movers side rails, graded alert timeline, real footer) · C "Calm
  Premium" (restraint + timeline + footer + numbered sections). Working mockups:
  `/tmp/mmx_mock/site_{a,b,c}` + shots. Do NOT build until the operator picks.
- **W2b live quotes**: the hub's 9 index symbols (^GSPC, ^HSI, …) are served by NO feed —
  live.js is a no-op on the front page. Wire into `build_live_overlay` (+ sessions for
  jp/kr/tw/gb/eu; client `regionOf` already mapped, absent sessions are safe-unknown).
- **W2c ZH engine strings**: alert detail bodies leak English into `.l-zh` — needs a
  paired `{text_en, text_zh}` contract at the emitters, not template patches.
- **W5 guards**: landing a11y check (aria-hidden-focusable, `lang` sync, light `.pill`
  contrast) in dark/light × EN/ZH; also the inline-`onclick` gap: `check_inline_js` parses
  `<script>` bodies in `site/*.html` only — a broken onclick in a `build_vector.py`-rendered
  section ships green until rendered (bit us: expander blocker caught in review).
- CN standout chips show bare numeric codes (601326…) — artifact has no alias field.
- Regime-change badges for CN/HK/CA need their regime events surfaced into the home feed.

## Review verdicts folded in

Opus review (block → fixed): expander onclick was invalid JS (quote-nesting — rebuilt with
pre-rendered label spans + class toggle, e2e-tested 5→8→5); `#hub-signin` never unhid
([hidden] vs inline display); observer now syncs `documentElement.lang`; theme segment got
`aria-pressed`; chip counts deduped total; tickers added to `.l-zh` too.
