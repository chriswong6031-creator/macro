# BUILD-READY SPEC — P2: Wikipedia Pageviews per-ticker "attention" chip (DISPLAY-ONLY)

> Status: DRAFT spec. Ships as a **display-only conditioning chip**. NOT wired into `engine/axes.py`, `engine/top_picks.py::compute_scores` (`:98`), `engine/setups.py::setup_score` (`:57`), regime scoring, or MRS at build time. A separate Phase-0 (§5) runs in parallel and only LATER could promote it — never assume it passes; the honest prior (Da–Engelberg–Gao 2011 "In Search of Attention") is that retail attention predicts **short-horizon reversal/over-extension**, concentrated in small/illiquid names, and is **decayed post-GME** → expect FAIL → permanent display.

---

## 1) Goal / scope

Add a per-ticker **abnormal-attention z-score** chip — a neutral **over-extension / fade-risk caution**, NOT a directional buy/sell — to two existing surfaces:

- **`discovery.html`** (Top Picks board) — beside the existing conviction-driver chips inside the `conv(r)` macro at `templates/discovery.html.j2:18-25` (the `.cchips` span), after the insider `👤{{ r.ins_buyers }}` chip at `:24`.
- **`stock.html`** (single-stock page) — JS-driven. Chips are assembled client-side via `gchip(k, v, dashed)` (`templates/stock.html.j2:414`). The natural home is the **alpha-context chip strip** built at `:922` (`var chips = [gchip(lz('alpha z',...))]`), which already uses the **inline** bilingual helper `lz(en, zh)` (defined `:368`). Do NOT use the separate factor/valuation strip at `:539-551` (that one uses the `LF(k)` dict lookup `:396` and is about smart-beta/valuation, not attention).

> **CORRECTION vs prior draft:** there is **no existing insider `gchip` on `stock.html`** to "mirror" — insider on the stock page is a `posbox` KV table at `:680-698`, and the per-stock `rec` JSON is **never** given an `insider` field (see §3). The attention chip is therefore net-new to the alpha-context strip.

Honest framing baked into the copy and the help-tooltip: *attention spikes mark crowding/extension, not edge — Da–Engelberg–Gao attention→short-horizon reversal, strongest in small/illiquid names, decayed since the 2021 meme era.* Caution-only, never green/up.

Wikimedia counts **offshore (en.wikipedia.org)** attention only. For CN/HK-domiciled tickers the article traffic is GFW-blind to the mainland audience → an **"international attention only"** caveat is mandatory (§4c).

---

## 2) New collector — `collectors/wiki_pageviews.py`

Clone the `Adapter` pattern as `collectors/sentiment.py:22-52` (`NaaimAdapter`). Verified facts the clone must honor:

- Subclass `collectors.base.Adapter` (`collectors/base.py:33`); set `name`, `group`, `stale_after_days`; implement `fetch(full_history=False) -> dict[str, pd.DataFrame]`; use `self.http_get(...)` (`base.py:70-90`, built-in retry/backoff + 429/5xx handling); raise on failure (runner `run_adapter` `base.py:99-130` degrades, never crashes).
- `validate()` (`base.py:47-57`) normalizes the index via `pd.to_datetime(...).normalize()` and drops all-NaN, so store the per-ticker daily-views frame indexed by date with one numeric column.
- `run_adapter` stores **one parquet per series key** via `store.upsert(group, series_name, df, outlier_col=df.columns[0] if len(df.columns)==1 else None, ...)` (`base.py:115-118`). A single-column `views` frame triggers the upsert outlier guard — acceptable for a count series, or pass a multi-col frame to skip it. [VERIFY: whether the outlier guard clips legitimate viral spikes for a single-col count series — if so, store as a 2-col frame (`views`, plus a constant/aux col) to set `outlier_col=None`.]

**Endpoint (keyless, no auth):**
```
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
  en.wikipedia.org/all-access/user/{article}/daily/{YYYYMMDD}/{YYYYMMDD}
```
`agent=user` excludes bots/spiders (the correct choice for attention). Response is a JSON array of `{timestamp, article, views, ...}` per day. Use the descriptive `WIKI_UA` already established at `collectors/equity_profile.py:43` (Wikimedia asks for a contact-bearing UA); pass it via `headers={"User-Agent": WIKI_UA}` to `self.http_get`. Note `Adapter.http_get` already defaults a UA from `config.load()["sponsors"]["user_agent"]` (`base.py:71-72`) — override it explicitly for the Wikimedia contact UA.

**Ticker → article map — REUSE the equity_profile resolution. [VERIFY — CRITICAL GOTCHA]:**
`data/profile/profiles.parquet` schema (CODE FACTS: 1506 rows, columns `['name','as_of','sic_description','exchange','hq','description','source']` [VERIFY: re-confirm exact column set on disk before coding — `fetch_profiles` also writes `ticker` as the index, and `_sec_submission` may add fields]) — **there is NO cached resolved Wikipedia article *title*.** `equity_profile._wiki_description()` (`collectors/equity_profile.py:358-403`) resolves the page (opensearch → `_is_company_page` → `_match_score`) but persists only the **description text** (`fetch_profiles` `:431-453`, `rec["description"] = _wiki_description(display, rec.get("name"))` at `:451`), discarding the title. Three options, in preference order:

1. **(Recommended) Backfill a `wiki_title` field into the profile collector.** Inside `_wiki_description` the matched `s.get("title")` is in scope at the full-match short-circuit (`:394-396`) and the partial branch (`:398`). Refactor it to return `(extract, title)` and have `fetch_profiles` (`:451`) persist `rec["wiki_title"]`. One additive column; zero new HTTP. The pageviews collector then reads titles straight from `profiles.parquet`. **Build dependency:** profiles must be re-fetched once (resumable, `max_new` cap) to populate the column; graceful — missing title ⇒ ticker skipped, no chip.
2. Re-resolve per ticker inside `wiki_pageviews.py` by importing the `_wiki_description` machinery — modest HTTP overhead per ticker, re-incurs the wrong-namesake risk the profile collector already solved.
3. Hand-maintained override map in config for the high-traffic names only.

Pick **(1)**. Map article = the validated company-page title, underscore-joined and URL-quoted the same way as `equity_profile.py:348` (`quote(title.replace(" ", "_"))`), e.g. `Apple_Inc.`, `Nvidia`.

**Adapter shape (illustrative; symbols above are the load-bearing ones):**
```python
class WikiPageviewsAdapter(Adapter):
    name = "wiki_pageviews"
    group = "attention"            # new data/attention/ dir
    stale_after_days = 4           # daily series; small slack for API lag
    def __init__(self):
        self.cfg = config.load()["wiki_pageviews"]
    def fetch(self, full_history=False):
        titles = _ticker_titles()                  # from profiles.parquet wiki_title
        win = self.cfg["history_days_full"] if full_history else self.cfg["history_days"]
        frames = {}
        for tk, title in titles.items():
            try:
                r = self.http_get(URL.format(article=quote(title.replace(" ", "_")), ...),
                                  retries=self.cfg["retries"],
                                  headers={"User-Agent": WIKI_UA})
                df = _parse(r.json())              # date-indexed single 'views' col
                if len(df) >= self.cfg["min_days"]:
                    frames[tk] = df
            except Exception:                       # one bad article never kills the run
                continue
        if not frames:
            raise ValueError("wiki_pageviews: no article resolved to views")
        return frames
```
Set `expected_failure = None` (the endpoint is reachable; per-ticker misses are tolerated internally so the run never lands in `blocked`).

**Config — add to `config.yml`** (mirror the `sentiment:` block referenced at CODE FACTS `config.yml:349-352` [VERIFY: exact `sentiment:` block line range and indentation before inserting]):
```yaml
wiki_pageviews:
  base_url: https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article
  project: en.wikipedia.org
  access: all-access
  agent: user
  history_days: 120          # rolling window the chip's z is computed over
  history_days_full: 740     # --full-history backfill (API serves from 2015-07)
  min_days: 60               # need a baseline to z-score against
  z_window: 90               # abnormal-attention baseline window
  retries: 3
  chip_threshold: 2.0        # z at/above which the caution chip renders
  pace_sec: 0.05             # inter-call sleep (mirror equity_profile :349,372)
```

**Registration — `scripts/collect.py`** specs list (`collect.py:30-81`; per-spec lazy import that swallows import failure at `collect.py:82-88`). Add beside the other sentiment/attention sources [VERIFY: exact insertion line — CODE FACTS estimated "~line 49 after `sentiment_aaii`"; confirm the `sentiment_*` tuples and pick the adjacent line]:
```python
("wiki_pageviews", "collectors.wiki_pageviews", "WikiPageviewsAdapter"),  # offshore attention (display-only; Phase-0 in scripts/wiki_attention_phase0.py)
```

---

## 3) Chip compute — abnormal-attention z-score

A new engine builder writing `site/factordata/attention.json`, mirroring **`build_site.build_insider_data`** (`scripts/build_site.py:1172-1201`) precisely (additive + graceful: returns/writes nothing when input missing; same `try/except … return None` idiom).

**Z definition** — per ticker, over the daily `views` series:
```
z = (mean(views, last 5d) − rolling_mean(views, z_window)) / rolling_std(views, z_window)
```
Use a trailing 5d mean over the longer `z_window=90` baseline so a single anomalous day doesn't dominate. Log-transform first (`log1p`); pageview distributions are heavily right-skewed → a robust z (median/MAD) is the safer default. Clip to e.g. `[-3, +6]` for display. The baseline must be **causal** (only views strictly prior to the evaluation point) — this matters for the Phase-0 panel in §5.

**Output shape** (`attention.json`, written like `insider_signals.json` at `build_site.py:1198`):
```json
{ "AAPL": {"z": 1.8, "views": 42100, "asof": "2026-06-12"}, ... }
```

**Wiring into `build_site.main`:** add a `build_attention_data(site)` builder and call it inside the same `try/except` chain as the alpha/insider builders (`build_site.py:1478-1485`), **after** `build_alpha_data` (`:1479`) and `build_insider_data` (`:1483`). It must complete before `build_stock_library` and `build_discovery` consume the factordata JSONs.

**Merge semantics — CORRECTED:**
- For **discovery** (`build_discovery.py`), the chip is fed via a row field (§4a) — there is no per-stock `rec` involved.
- For **stock.html**, `build_stock_library` builds the per-stock `rec` JSON. **Verified:** that `rec` is given only `rec["alpha"]`, `rec["fund_flows"]`, `rec["alerts"]` (and base fields) — it is **NOT** given an `insider` field; insider data is written into the *setup-board* `row` at `build_stock_library.py:294-302`, not into `rec`. So adding `rec["attention"] = attn_map.get(ticker)` is **net-new** (place it beside the `rec["alpha"] = alpha_pt[ticker]` merge at `:291-292`, guarded `if attn_map.get(ticker):`). Load `attention.json` into `attn_map` near the existing factordata loads at `build_stock_library.py:260-275` (mirror the `insider_map = json.loads(isp.read_text())` pattern at `:271-275`). Do **not** thread `attention` into `setup_score` (`:293`) — that would be a scored leg (forbidden, §6.4).

---

## 4) Template + build wiring (exact files, bilingual)

### 4a) discovery.html — `scripts/build_discovery.py`
Verified: `main()` loads JSONs via `_load_json` — `alpha.json` (`:99`), `factors.json` (`:101`), `insider_signals.json` (`:103`). `_clean` (strips NaN) at `:90-92`. The row builder `_row(tk, a)` is at `:122-150`; it reads `ins = insider.get(tk, {})` at `:127` and returns `ins_buyers`/`ins_bps` at `:149`. Mirror it:
- Load near `:103`: `attn = _load_json(site, "attention.json")`.
- In `_row`: `at = attn.get(tk, {})` and add to the returned dict (alongside `:149`): `"attn_z": _clean(at.get("z")),`.

Template `templates/discovery.html.j2` — the `conv(r)` macro is at `:18-25`. Insert inside the `.cchips` span, after the insider chip at `:24`:
```jinja
{%- if r.attn_z and r.attn_z >= 2.0 -%}<span class="cchip attn" title="{{ t('Abnormal Wikipedia attention (offshore) — z %+.1f. Da–Engelberg–Gao: attention → short-horizon reversal; extension/fade caution, not a buy.', '维基百科异常关注度（境外）— z %+.1f。Da–Engelberg–Gao：关注度→短期反转；过度/回吐风险提示，非买入信号。')|format(r.attn_z, r.attn_z) }}">👁{{ '%+.1f'|format(r.attn_z) }}</span>{%- endif -%}
```
> Note: `t(...)` here is the **local macro** defined at `templates/discovery.html.j2:1-3` (`{% macro t(en, zh='') %}`), which renders BOTH `l-en`/`l-zh` spans — not the Python `engine.i18n.t`. Bilingual coverage comes from that macro emitting both spans. The `|format(...)` interpolation must produce text safe inside the dual-span macro; if `%+.1f` interpolation collides with the macro's span markup, pass the formatted string as the macro arg instead of formatting the macro output. [VERIFY: that `{{ t(...)|format(...) }}` composes correctly given the macro returns `Markup` with two spans — if not, precompute the sentence in `_row` and pass it through.]

Add CSS beside `.cchip.ins` (`discovery.html.j2:98`):
```css
.cchip.attn { color:var(--muted); border-style:dashed; border-color:var(--muted); }
```
(Dashed + muted = the display-only caution idiom, matching `.gchip.dashed` at `stock.html.j2:129`.)

### 4b) stock.html — client-rendered chip
Verified mechanics: `gchip(k, v, dashed)` at `:414`; inline bilingual `lz(en, zh)` at `:368`; the `LF(k)` dict-lookup helper at `:396` reads the `TF` object (`TF.en` / `TF.zh`, defined ~`:374-394`) — **there is no `LF`/`LZ` *dictionary*; `TF` is the dict and `LF` is the accessor.** The alpha-context chips array is built at `:922` and pushes via `lz(...)` (e.g. `:922,924,926,928`).

Steps:
1. Ensure `build_stock_library` merges `rec.attention = {z, views, asof}` (§3, net-new at `:291-292`).
2. **Use inline `lz(en, zh)`** for the attention chip (consistent with the alpha strip at `:922`) — do NOT add a `TF`/`LF` key unless you also add the matching `TF.zh` entry; inline is lower-risk here. Append to the alpha-context `chips` array (after `:928`):
   ```js
   if (rec.attention && rec.attention.z >= 2.0)
     chips.push(gchip(lz('Wiki attention','维基关注度'),
                      '👁 ' + sgn(rec.attention.z, 1) + 'σ', true)); // dashed = context
   ```
   Reuse the existing signed-number helper used in this strip (`sgn(...)`, as at `:922-928`) rather than introducing `fmtSigned`. The `dashed=true` 3rd arg renders `.gchip.dashed` (muted, `opacity:.7`, `:129`).
3. [VERIFY: that the alpha-context `chips` array at `:922` is the strip actually rendered into the page for every stock (it is gated on `a`/alpha presence) — if attention should show on names without alpha, append to a strip that always renders instead, or add an independent render.]

### 4c) OFFSHORE-attention caveat for CN/HK names (mandatory)
Tickers on the China/HK boards (`*.SS`, `*.SZ`, `*.HK`) draw a mainland-blind audience. Append the caveat to the chip tooltip for these. In the discovery Jinja chip, gate off the ticker suffix:
```jinja
{% if r.ticker.endswith('.SS') or r.ticker.endswith('.SZ') or r.ticker.endswith('.HK') %} {{ t('— measures international attention only (mainland traffic not counted)', '— 仅衡量境外关注度（不含大陆访问）') }}{% endif %}
```
For `stock.html`, build the same suffix-gated caveat in JS (concatenate `lz('— international attention only (mainland not counted)','— 仅境外关注度（不含大陆）')` into the chip key/title when the ticker matches) before assembling the chip string.

**[VERIFY: `china_stock.html.j2` / `hk_stock.html.j2` render model]** — both templates exist. Confirm whether they reuse the same `gchip`/`lz` JS chip model as `stock.html.j2` (then reuse the JS chip + caveat) or render chips server-side (then mirror the discovery-style Jinja chip). This determines exactly where the CN/HK caveat is injected on those pages.

**i18n module** — the Python helpers `t(en, zh)` (`engine/i18n.py:24`), `tr(en)` (`:30`), `td(en)` (`:37`) are wired as Jinja globals; template usage confirmed in `discovery.html.j2`. **NOTE:** CODE FACTS referenced `lib/i18n.py` in one bullet — that is wrong; the helpers live in `engine/i18n.py`. Composed caution sentences are translated **inline at the call site** (the module's own convention); finite glossary terms can go in the `LEX`/`TF` dictionaries but the caution sentences here are inline. [VERIFY: exact `engine/i18n.py` `LEX` line range only if adding glossary entries — not required for inline sentences.]

---

## 5) Phase-0 harness — `scripts/wiki_attention_phase0.py`

Clone the structure of `scripts/insider_phase0.py` (351 lines, verified). The gate: **does abnormal Wikipedia attention add cross-sectional return-predictive information INCREMENTALLY over the named incumbents** — net of multiple-testing and DSR haircuts. **Expected verdict: FAIL → display-only.**

Symbol attribution (verified):
- From **`engine/validation.py`**: `rank_ic` (`:312`), `ic_summary` (`:345`, Newey-West `t_hac`/`p_hac`), `benjamini_hochberg` (`:362`), `deflated_sharpe` (`:132`), `dsr_verdict` (`:162`), `ret_moments` (`:115`), `block_bootstrap_ci` (`:201`), `resid_z` (`:380`).
- **Local helpers in `scripts/insider_phase0.py` (NOT in validation.py)**: `quintile_ls` (`:110`), `month_grid` (`:98`), `_split_half_ic` (`:148`), `_closes_deep` (`:56`), `score()` (`:158`). Re-implement or import these from the insider harness.
- Panel sources imported as in `insider_phase0.py:44`: `from engine.equity_factors import _closes, _names_sectors`. The deep-coverage variant uses `_closes_deep()` (`:56`, gated by `--deep`); the wiki harness backtests on the same close matrix.

**Harness outline (mirror `insider_phase0.score()` `:158-220`):**
1. **Panel**: load `data/attention/*.parquet` daily views; compute the §3 causal z per ticker per date. Use `_closes()`/`_closes_deep()` + `_names_sectors()` for the close matrix + GICS sectors.
2. **Forward returns**: `closes.pct_change(horizon).shift(-horizon)` (as `insider_phase0.py:173`), horizons **5d, 21d, 63d** (attention is short-horizon — 5d is the key test; the reversal prior predicts a **negative** IC there).
3. **Raw + sector-neutral IC**: per-date `rank_ic(z, fwd)` and the within-GICS demeaned `|SN` variant (as `insider_phase0.py:193-194`); summarize with `ic_summary(..., periods_per_year=12)` over the monthly grid (`month_grid`, `:98`).
4. **INCREMENTAL test (load-bearing — there is NO shared incremental-over-incumbent helper; do it ad hoc here):** orthogonalize the attention z against each incumbent per date, then re-run IC on the **residual**:
   - **vs momentum** — sector-neutral residual-momentum z (`engine/residual_alpha.py`, confirmed present; per-ticker values on disk in `site/factordata/alpha.json` under `per_ticker`, the same source `build_discovery.py:99` reads). Regress attention-z on momentum-z cross-sectionally each date; keep the residual.
   - **vs NDI** — **[VERIFY: NDI per-ticker symbol/series]** — a grep for `news_diffusion`/`ndi`/`news_*`/`*sentiment*` per-ticker factor returned no confirmed per-ticker NDI in the facts. If no per-ticker NDI exists, **state that explicitly in the report and test only vs momentum + VIX-regime** (do not invent an NDI series).
   - **vs VIX** — a *time-series* conditioner, not cross-sectional. Test whether attention's IC survives **within VIX regime buckets** (split dates into low/high VIX terciles, recompute IC per bucket). Pull VIX from the existing close/yahoo cache. [VERIFY: exact VIX series key in the price cache.]
   - Use `resid_z` (`validation.py:380`) or a plain per-date OLS for the cross-sectional orthogonalization.
5. **BH-FDR** across {raw, SN, residual-vs-mom, residual-vs-NDI(if present)} × {5d,21d,63d} p-values via `benjamini_hochberg(pvals, alpha=0.10)` (as `insider_phase0.py:211`). Report survivors (expect **NONE**, or only a *negative*-IC 5d reversal — still a fade-caution, not a tradable long).
6. **DSR**: dollar-neutral top-vs-bottom decile L/S on the residual z via the local `quintile_ls(...)` (`insider_phase0.py:110`) → `deflated_sharpe(..., n_trials=...)` + `dsr_verdict` + `block_bootstrap_ci`. Honest `n_trials` = full count of signals × horizons × orthogonalizations tested (lesson from memory `base-scanner-phase0` / `rvol-phase0`: a lenient L/S gate gives FALSE GOs → rest the verdict on the **clean incremental IC + honest n_trials**, not the headline L/S).
7. **Split-half** stability via `_split_half_ic` (`insider_phase0.py:148`).
8. Writes `reports/wiki-attention-phase0.md` (pattern `insider_phase0.py:282+/main`). No commit, no site build.

**Named incumbents the chip must beat incrementally:** **momentum (residual-alpha)**, **NDI [VERIFY: exists per-ticker; else drop]**, **VIX-regime**. Prior: it won't. Ship as display regardless.

> **API-window caveat for the backtest:** `/per-article` serves from **2015-07-01** only → the Phase-0 span is ~2015→present, materially shorter than the insider panel's 2006→. State this explicitly in the report (limits statistical power / DSR n).

---

## 6) Tests — `tests/test_wiki_pageviews.py`

Mirror the additive/graceful test idiom. Cover:
1. **Collector parse** — feed a canned Wikimedia JSON array (`[{timestamp, article, views}, ...]`) to `_parse`; assert a date-indexed single-column numeric frame; assert `Adapter.validate(name, df)` (`base.py:47`) accepts it.
2. **Missing article map** — `_ticker_titles()` with a `profiles.parquet` lacking `wiki_title` (or a ticker absent) ⇒ that ticker is **skipped**, no exception; a fully-empty result raises `ValueError` (so `run_adapter` degrades, not crashes).
3. **Chip compute / shape** — `build_attention_data` on a fixture views panel emits `attention.json` of `{ticker: {z, views, asof}}`; z within clip bounds; quiet names produce no chip (z below `chip_threshold` ⇒ absent or filtered).
4. **Display-only invariant (critical guard)** — assert the strings `attention` / `wiki_pageviews` / `attn_z` / `attn` do **NOT** appear in the source of `engine/axes.py`, `engine/top_picks.py` (`compute_scores`), and `engine/setups.py` (`setup_score`). This enforces the core rule. (Read each module's source and assert absence — pattern: a string-presence assertion over the file text.)
5. **Bilingual render** — render `discovery.html.j2` with a row carrying `attn_z=2.5`; assert BOTH `l-en` and `l-zh` spans appear (the `t(en, zh)` macro emits both) and the CN-suffix caveat fires for a `.SS`/`.HK` ticker but not a US ticker. (Template-render test pattern exists: `tests/test_advanced_page.py`, per memory `advanced-page-pct-fix`.)

Run: `.venv/bin/python -m pytest tests/test_wiki_pageviews.py`. **Verify via grep + pytest, NOT live preview** (templates + `site/*.html` are concurrently edited by parallel sessions).

---

## 7) Effort, gotchas, [VERIFY]

**Effort:** ~1–1.5 days. Collector clone ~2h; the **profiles `wiki_title` backfill is the real cost** (refactor `_wiki_description` to return the title + one resumable re-fetch pass) ~3h; chip compute + build wiring ~2h; templates + i18n (discovery + stock + CN/HK) ~2h; Phase-0 harness ~4h (the incremental orthogonalization is the bulk); tests ~2h.

**Gotchas:**
- **No cached article title** (`profiles.parquet` has no `wiki_title`) — the gating dependency. `_wiki_description` *computes* the title (`equity_profile.py:394,398`) and throws it away; §2 option (1) recovers it.
- **`rec["insider"]` does NOT exist on stock.html** — insider on the stock page is a `posbox` KV (`stock.html.j2:680-698`), and `build_stock_library` writes insider into the *setup row* (`:294-302`), not the per-stock `rec`. The attention `rec["attention"]` merge is net-new (§3) — do not "mirror" a nonexistent insider `rec` merge.
- **Two chip strips on stock.html** — the alpha-context strip (`:922`, inline `lz`) vs the factor/valuation strip (`:539-551`, `LF`/`TF` dict). Use the alpha strip + `lz` for attention; don't mix helpers.
- **Wrong-namesake risk is already solved** in `_wiki_description` (`_is_company_page` + `_match_score` walk, `:386-403`) — reuse it; do NOT naively `opensearch` the ticker yourself (MSFT→EU antitrust case, the documented trap + memory `equity-profile-wiki-fix`).
- **GFW / offshore-only** — en.wikipedia.org pageviews are mainland-blind; the CN/HK caveat is non-optional. zh.wikipedia.org is *also* GFW-blocked (measures Taiwan/HK/diaspora, not mainland) → out of scope; document, don't build.
- **Race-safety** — never commit regenerated `site/*.html` (`pages.yml` upload-only); work in a worktree, commit own paths only (memory `repo-backup-hygiene`: a parallel `git add -A` can sweep your hunks — pathspec-commit or isolated index). `discovery.html.j2` and `stock.html.j2` are hot files — re-grep before editing; verify by render-test, not preview.
- **Wikimedia API window** — `/per-article` serves from **2015-07-01** only; the rolling-z (`history_days=120`) is fine, but `--full-history` and the Phase-0 backtest cap at ~2015.
- **upsert outlier guard** — single-col count series triggers `outlier_col=df.columns[0]` in `store.upsert` (`base.py:115-118`); verify it doesn't clip legitimate viral spikes (see §2 [VERIFY]).

**[VERIFY] before building:**
- `[VERIFY: profiles.parquet exact columns]` — re-confirm the on-disk column set (incl. `ticker` index) before relying on it.
- `[VERIFY: NDI per-ticker symbol]` — the exact in-repo NDI series for the incremental Phase-0 test; if none exists, test vs momentum + VIX-regime only and say so in the report.
- `[VERIFY: config.yml `sentiment:` block lines]` — exact range/indentation before inserting the `wiki_pageviews:` block.
- `[VERIFY: scripts/collect.py insertion line]` — confirm the `sentiment_*` tuple region and pick the adjacent line (CODE FACTS estimated ~49).
- `[VERIFY: Wikimedia per-article quota/pacing]` — keyless tier is generous but ~1500 tickers/day = ~1500 calls; confirm whether a `time.sleep(cfg["pace_sec"])` between calls is needed (equity_profile uses `time.sleep(0.05)` at `:349,372`). Steady-state is cheap (daily incremental upsert).
- `[VERIFY: china_stock.html.j2 / hk_stock.html.j2 render model]` — confirmed both exist; verify `gchip`/`lz` JS vs server-side rendering to place the CN/HK caveat.
- `[VERIFY: VIX series key]` — exact key in the price/yahoo cache for the VIX-regime bucketing.
- `[VERIFY: discovery `t(...)|format(...)` composition]` — that formatting the dual-span macro output works; if not, precompute the sentence in `_row`.
- `[VERIFY: alpha-context chips strip render gating]` — that `stock.html.j2:922` renders for every name (it is alpha-gated); choose an always-rendered strip if attention must show without alpha.
- `[VERIFY: build order]` — `build_attention_data` runs in the `build_site.main` try-chain after `build_alpha_data` (`:1479`) / `build_insider_data` (`:1483`) and before `build_stock_library` / `build_discovery` consume the factordata JSONs.
