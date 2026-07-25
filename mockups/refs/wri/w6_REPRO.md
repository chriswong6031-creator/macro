# W6.1 coverage-honesty verification — crop reproduction

The `w6_dark.png` / `w6_zh.png` crops for the W6.1 crypto extension show the **L2 Book Risk
hero** computed over a fixture book that mixes a now-modeled crypto ETF (IBIT), an unmodeled
HK name (0700.HK), and 6 US names. This file regenerates the exact page state so the crops
can be captured in any browser (the build agent's sandbox had no headless-browser-to-disk
tooling, so the PNGs are reproduced here rather than committed stale).

## What the crops must show (the acceptance the PR verifies)

- Hero reads **"Your 7 names move as about 2 bets"** — 7, not 8: the HK name is excluded
  from the book math (WRI-R6 coverage honesty).
- **"What drives your swings"** lists a **Bitcoin** row with a non-zero share (~5%) — the
  crypto factor share is now real because IBIT is modeled and loads btc-heavy.
- **"Biggest single risks"** lists **IBIT ~15%** — the crypto ETF has a real MCTR share.
- Method line names the unmodeled ticker: *"1 name (0700.HK) isn't modeled and sits outside
  these numbers."*
- **IBIT card chip** = "15% of book risk / 占组合风险15%" (modeled — real contribution).
- **0700.HK card chip** = "price signals only — not in the risk model / 仅价格信号——未纳入风险模型"
  (unmodeled — honest chip). Both EN and ZH render.

## Reproduce

1. Regenerate a local `site/factor_betas.json` that includes the crypto rows (the baked file
   is render-owned; do NOT commit the regenerated copy):

   ```bash
   python3 - <<'PY'
   import json
   from engine.factor_exposure import compute_exposure
   json.dump(compute_exposure(), open('site/factor_betas.json', 'w'))
   PY
   ```

   (Restore it afterward: `git checkout site/factor_betas.json`.)

2. Serve `site/` and open `watchlist.html`, then paste the fixture book into the console and
   reload:

   ```js
   // seed fixture: IBIT (modeled crypto) + 0700.HK (unmodeled HK) + 6 US names
   var now = new Date().toISOString();
   var items = ['IBIT','0700.HK','AAPL','NVDA','MSFT','AMD','AVGO','GOOGL']
     .map(function(t){ return { t:t, added:now, note:'' }; });
   localStorage.setItem('mdash.watchlist.v1',
     JSON.stringify({ v:1, updated:now, items:items, order:items.map(function(i){return i.t;}) }));
   location.reload();
   ```

3. `w6_dark.png` — dark scheme, EN; frame the `#wri_hero` block + the IBIT / 0700.HK cards.
   `w6_zh.png` — run `setLang('zh')` in the console, same frame.

## Verified this build (DOM-extracted, headless preview)

`RiskCore.coverage(data, equalWeightBook)` returned:
`modeled = [AAPL, AMD, AVGO, GOOGL, IBIT, MSFT, NVDA]`, `unmodeled = ['0700.HK']`,
`unmodeledFrac = 0.125`, `abstain = false`; `RiskCore.book(...)` held IBIT with
`mctrShare['IBIT'] ≈ 0.166` and `betas['IBIT'].btc = 0.888`. Card chips rendered
"15% of book risk / 占组合风险15%" (IBIT) and "price signals only — not in the risk model /
仅价格信号——未纳入风险模型" (0700.HK) in both EN and ZH. No `watchlist_risk.js` change was
needed — coverage is presence-driven (`data.betas[t]`), so adding crypto to the emit modeled
it automatically and the HK name stayed unmodeled.
