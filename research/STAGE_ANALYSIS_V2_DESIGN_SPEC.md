# Stage Analysis v2 — design spec (the visual contract the hub is built to)

Authored main-loop (Fable) as the taste anchor. The opus `designer` implements to THIS spec exactly;
deviations only to raise quality, never to reinterpret scope. Every surface is **browser-verified in dark
mode with real data** before it ships. The v1 defect — hardcoded near-black text on a dark background,
unreadable — is a hard fail; contrast is a gate, not a nicety.

## 0. What we're beating

EquityDesk is a light-only, flat, utilitarian data terminal: white background, tiny colored score pills,
dense unstyled tables, no chart on the list surfaces, no motion, system fonts. It reads like an internal admin
tool. We keep their **information density and completeness** (that's the substance) and replace everything
else with a dark-first, chart-forward, editorial product surface at the macro.html / Terminal quality bar.

## 1. Foundations (non-negotiable)

- **Theme:** dark-first. Use ONLY `theme.css` tokens for color — `--bg, --panel, --panel2, --text, --muted,
  --up, --down, --info, --link, --glass-*, --border`. NEVER a literal `#000`/`#111`/`color:black` for text.
  Text on any panel is `var(--text)`; secondary is `var(--muted)`. Light mode must also pass (tokens flip).
- **Contrast gate:** body text ≥ 7:1 on its background; chips/labels ≥ 4.5:1. Verified with `preview_inspect`
  computed color, not by eye. Any element that renders `< 4.5:1` fails review.
- **Type:** Inter (via `_interfonts`) for UI/body. One characterful display face for the hero + section
  numerals — a tight grotesk or a distinctive numeric face for the big stage digits (e.g. the "1·2·3·4"
  cycle markers) so the page has a signature, not a default. Tabular-nums everywhere numbers align.
- **Grid:** a real 12-col content grid, generous gutters, sticky table headers, virtualized long tables.
- **Motion:** restrained and purposeful — a page-load stagger on the hero + KPI row, hover elevation on
  rows, a smooth tab crossfade. Respect `prefers-reduced-motion`. No decorative ambient loops.

## 2. The hub shell

A single page (`stage_analysis.html`) with a **left rail or top segmented tab bar** switching six surfaces
client-side over committed JSON. The shell carries: our site nav (`_site_nav`), a hero strip (below), the
tab switcher, a region toggle (N.America / Europe / Asia), a tag toggle (L1/L2), and a global stock search.
Tab state in the URL hash so views are linkable. One as-of stamp, one honest data-provenance line.

**Hero (signature):** the market-on-one-cycle stage arc — the idealized Weinstein curve (base→advance→top→
decline) as an SVG, the whole universe scattered as density dots along it, per-stage counts, and ONE plain
stance line ("Most stocks are advancing — good weather for fresh breakouts"). This is our motif, not their
plain table header. Dot color = stage palette (below). Reduced-motion: static.

**Stage palette (page-local accents over theme tokens, never redefining core):**
S1 base = steel `#7f97b3`-family · S2 advance = `var(--up)` · S3 top = amber `#d9a441`-family ·
S4 decline = `var(--down)`. In dark mode these sit on `--panel`; verify each is legible.

## 3. The six surfaces (anatomy)

### A · Screener (flagship, mirrors Overview)
The full combined table. Columns EXACTLY: Ticker · Name · Industry · **Ind %ile** · **SATA** (0–10) ·
**Δ SATA** · **Stage** (`2X Bullish` / `2X Catch` chip) · **Weeks** · **ATR Ext** · **ATR % Price** ·
**Tags** · **EC Sent** · **EC Perf** · **Rating** (0–100) · Add. Filter bar over every score column with
their exact bands (Ind %ile, SATA ≥N, ΔSATA, Stage type, Weeks ≤N, ATR Ext, EC Sent >N, EC Perf >N).
Score cells are chips with a shared-scale color ramp + `data-tip-en/zh` explaining what high/low means
(Tier-1 doctrine). Row expand → the mini weekly stage chart (§4) + tag cloud + EC highlights + slide link.
Sticky header, sort on any column, CSV export, "Showing X of N".

### B · Stage Board — Daily / Weekly (mirrors Trending Stocks)
Same row engine as A, a Daily/Weekly segmented toggle, columns tuned to the stage read: Ind %ile · SATA ·
Stage · ATR Ext · ATR % Price · Weeks · **Stage Δ** (chip: turned/steady) · **SATA Δ** · **M.RS** · **RS Δ**.
This is the "what changed this week" board — lead with fresh Stage-2 entries and stage transitions.

### C · Industries — 4 views (segmented within the surface)
1. **Ranking** — region × Industries/Sub-industries × Leaders/Laggards × timeframe (1D/1W/1M/3M/6M/12M);
   Industry Group, Performance%, top-5 names (as chips). Bar-in-cell for performance.
2. **Heatmap** — industry × timeframe grid, cell = rank/percentile, diverging color ramp (our tokens).
3. **EC Heatmap** — industry × week, cell = avg EC combined, with fresh-EC count; the earnings-tone rotation.
4. **Flows** — the rotation engine: per-industry stage2/stage4 counts + ratio, fresh-Stage-2 %, breadth 4w,
   RS-change, turn flag. Render as a sortable board + a small stage2-vs-stage4 diverging bar per industry.
   This is our most differentiated surface — make it read as "where the money is rotating, by stage."

### D · Earnings Calls — 3 views
1. **Table** — Company · Industry · Date · **Score** (EC Sent over EC Perf, stacked, colored) · Tags ·
   Positive Highlights · Negative Highlights · slide. Filter: industry, sentiment band, rating band, tag search.
2. **Season** — per-quarter (Q2'26/Q1'26/…) Raisers (Δ>5) vs Decliners (Δ<−5), industry-allocation breakdown,
   tag-frequency cloud, Combined-Rating & Performance range sliders.
3. **Comparison** — current vs prior quarter: current score+tags, prev score+tags, **Δ Combined** (chip).

### E · Alt-Data — Google · Reddit · Wikipedia · TikTok
Per source: trending-topics table (Topic · YoY% · 2W Δ% · Type · Description · matched Company chip · Add).
Lead each source with a compact "what's surging" strip. TikTok is a genuine edge — surface it prominently.
Honest label: seeded from backfill; our own collectors continue forward (TikTok = seed-only, disclosed).

### F · Research — deep dives + transcript reader
Per-company research index (from `company_generated_info`): thesis summary, model used, links. A **transcript
reader** panel that renders the earnings-call `summary` + `unified_analysis` (positive/negative factors,
guidance, hot topics, KPI mentions) cleanly — this is the "I can't view the transcripts" fix. No raw dict repr.

## 4. The signature component — weekly stage chart

A weekly candlestick (3yr) with the **10-week and 30-week SMA** overlaid, up/down weeks colored by
`is_up_week`, the current stage band shaded behind price (S1–S4 palette), and a marker at the Stage-2 start /
breakout. Appears in row-expand (A/B) and full-size on the stock detail. Lightweight (canvas or minimal SVG),
dark-native. This is what their list surfaces lack entirely — our charts lead.

## 5. Copy & honesty (DESIGN_DOCTRINE)

Every score has a plain-word meaning on Tier 1 (SATA = "trend-quality strength, 0–10"; Stage = plain phrase;
EC Sent = "how upbeat the call tone was"). Stances from the doctrine six. Nulls in plain words. No "validated".
Bilingual EN/ZH parity, ZH equally plain. No trading verbs beyond the sanctioned stances.

## 6. Review gate (before merge)

1. Dark-mode screenshot of every surface with real data — legible, no black-on-dark, no `{{ }}` residue.
2. `preview_inspect` computed-contrast check on body text + chips (≥7:1 / ≥4.5:1).
3. 5-second test per surface: a cold reader knows what it shows and what to do.
4. Faithfulness check: every EquityDesk column/view present and correct.
5. Responsive to 390px; keyboard focus visible; reduced-motion honored.
