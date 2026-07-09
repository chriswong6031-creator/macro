# Hong Kong Sector Flow And Rotation Research

Date: 2026-07-09
Author: Codex research continuation
Scope: Hong Kong listed equities. Mainland A-share data is included only where it transmits into HK through Stock Connect, A/H spreads, China policy, ADRs, or cross-market risk.

## 0. Epistemic status

This is a research/build handoff, not a shipped signal and not an investment recommendation.

The key distinction for this work:

- **Actual flow** means a signed buyer/seller or holder channel exists: for example Stock Connect buy minus sell value, Stock Connect shareholding changes, ETF creations/redemptions where available, or reported IPO proceeds.
- **Rotation pressure** means price, turnover, breadth, short activity, and relative-strength evidence imply money is favoring one bucket over another, but it is not literal net dollars moving from one sector to another.

For the dashboard we should show both, but label them differently. A cell that says "Southbound net buy +HK$2.1b" is a flow cell. A cell that says "flow pressure +1.8z" is an inferred pressure cell.

## 1. Short answer

Hong Kong should not be modeled as **sector only** or **small-cap versus large-cap only**. It needs a layered taxonomy:

1. **Official industry layer**: Hang Seng Industry Classification System (HSICS) / Hang Seng Composite Industry Indexes.
2. **Size/style layer**: HSCI LargeCap, MidCap, SmallCap; mega-cap platform tech; high-dividend SOE/banks; IPO/new listing; small-cap/speculation.
3. **Trading theme layer**: China Tech & Internet, banks, insurers, property, EV/auto, healthcare/biotech, materials, energy, telecom/utilities, gaming, HKEX/brokers, high-dividend.
4. **Access/flow layer**: Stock Connect eligible versus not, southbound-held versus not, ADR-linked versus local-only, H-share/AH-dual versus P-chip/red-chip/local HK.
5. **Event layer**: IPO/listing, buyback, placement/dilution, policy/catalyst, earnings, index inclusion, short squeeze.

The user examples map cleanly:

- **IPO stocks doing well while big tech does not** = primary-market/speculative-liquidity layer leading while platform-tech beta lags.
- **Only banks doing well** = dividend/SOE/value/yield or China policy/funding layer leading while growth/tech risk appetite is absent.
- **Big tech doing well while banks do not** = platform catalyst, ADR/KWEB/FXI tailwind, AI/cloud narrative, short covering, or southbound accumulation in discounted internet leaders.

## 2. What HK officially uses

### 2.1 HSICS industry taxonomy

The official market industry taxonomy is HSICS. The current Hang Seng brochure says HSICS is a three-tier system covering 12 industries, 31 sectors, and 114 subsectors, designed for the characteristics of the HK stock market while mapping to international industry systems.

The Hang Seng Composite methodology defines the 12 industry indexes as:

- Energy
- Materials
- Industrials
- Consumer Discretionary
- Consumer Staples
- Healthcare
- Telecommunications
- Utilities
- Financials
- Properties & Construction
- Information Technology
- Conglomerates

This is the right official root taxonomy for sector-level reporting.

### 2.2 Size taxonomy

The Hang Seng Composite Index targets broad market coverage and splits size as:

- LargeCap: top 80% of cumulative market value coverage of the HSCI.
- MidCap: next 15%.
- SmallCap: remaining 5%.

This matters because Stock Connect eligibility and investor behavior are partly size-gated. HKEX's southbound discussion notes that eligible HK shares include Hang Seng Composite LargeCap and MidCap constituents, and SmallCap constituents with market cap at least HK$5 billion.

So the HK rotation map should always have a size/style strip beside the sector strip.

## 3. What the repo currently uses

### 3.1 Current HK heatmap taxonomy

`origin/main` already has a HK market heatmap:

- Producer: `scripts/build_market_heatmap.py`
- Compute layer: `engine/market_heatmap.py`
- Front-end renderer: `site/heatmap.js`
- Page template: `templates/market_heatmap.html.j2`

The current HK heatmap is a flat **Sector -> stock** treemap. It is grouped by the repo's practical HK trading sectors and sized by 30-session average dollar turnover because the repo has no shares-outstanding/market-cap feed for HK.

Current HK universe in `data/hk_breadth/constituents.parquet`:

| Repo sector | Names | 30-session ADV share as of local 2026-07-08 data |
|---|---:|---:|
| Internet & Tech | 22 | 53.1% |
| Financials & Banks | 14 with ADV | 7.6% |
| Healthcare & Pharma | 15 | 6.1% |
| Insurance | 8 | 6.0% |
| Materials | 10 | 4.5% |
| Auto & EV | 9 with ADV | 4.4% |
| Energy | 11 | 4.1% |
| Consumer | 20 | 3.6% |
| Property | 17 | 3.0% |
| Telecom & Utilities | 11 | 2.8% |
| Exchange & Diversified | 6 | 2.2% |
| Industrials & Transport | 10 | 2.1% |
| Gaming & Leisure | 5 | 0.5% |

This is already revealing: in the tracked liquid HK universe, Internet & Tech dominates turnover. A cap-weighted or turnover-weighted map can say "HK is tech-led" even when equal-weight participation is weak. Therefore we need both:

- **Weighted map**: where the big money/liquidity is moving.
- **Equal-weight map**: whether the whole sector/theme is participating.

### 3.2 Current thematic baskets

`data/baskets_hk/membership.json` has 14 curated HK thematic baskets:

| Basket | Category | Members | ETF/proxy |
|---|---|---:|---|
| `hk_china_tech` | Tech & Internet | 19 | 3033.HK |
| `hk_consumer` | Consumer & Healthcare | 17 | none |
| `hk_biotech` | Consumer & Healthcare | 15 | none |
| `hk_ev` | Autos & EV | 8 | none |
| `hk_banks` | Financials | 13 | none |
| `hk_insurers` | Financials | 8 | none |
| `hk_conglo` | Financials | 5 | none |
| `hk_property` | Property | 15 | none |
| `hk_gaming` | Gaming & Tourism | 5 | none |
| `hk_energy` | Energy & Resources | 10 | none |
| `hk_materials` | Energy & Resources | 11 | none |
| `hk_telco_util` | Telecom, Utilities & Income | 12 | none |
| `hk_dividend` | Telecom, Utilities & Income | 8 | none |
| `hk_industrials` | Industrials & Transport | 9 | none |

Important caveat: these baskets are hindsight-curated and descriptive. They can explain market structure and watch live rotation, but they must not become a claimed out-of-sample alpha source without a ledger.

## 4. What "net inflow/outflow between sectors" can mean

There is no universal public feed that says "HK$X moved from sector A to sector B" across all investors. Every trade has a buyer and a seller. The dashboard can still show a useful map if it uses three tiers of evidence.

### Tier 1: actual signed flow

Use where available:

- Southbound Stock Connect aggregate buy/sell/net by date.
- Southbound channel split: Shanghai versus Shenzhen.
- Southbound stock-level holdings delta by date, converted to HKD with price.
- Stock-level Stock Connect buy/sell/net if accessible from a licensed or acceptable public vendor.
- ETF flow if available.
- IPO fundraising and first-day/aftermarket data.

Display label: `actual flow`.

Example metric:

```text
sector_southbound_net_hkd =
  sum(stock_connect_buy_hkd - stock_connect_sell_hkd by ticker in sector)

sector_holding_delta_hkd =
  sum((southbound_shares_t - southbound_shares_t-1) * close_t)
```

### Tier 2: tagged-holder or settlement proxy

Use when exact buy/sell is unavailable:

- Stock Connect shareholding change.
- CCASS participant concentration/change if we later add that feed.
- Short-selling turnover and short-position changes.
- Buyback shares/value.

Display label: `holder/positioning proxy`.

### Tier 3: inferred rotation pressure

Use for total market behavior:

- Relative return versus HSI/HSCEI/HSTECH.
- Turnover share delta: today's sector turnover share versus 20d baseline.
- Dollar turnover impulse z-score.
- Breadth: percent up, percent above 20/50d, new highs/new lows.
- Weighted versus equal-weight spread.
- Short-sale intensity.
- Gap/fade behavior.

Display label: `inferred pressure`, never `net inflow`.

## 5. Proposed map architecture

### 5.1 One data product, four views

Add `site/factordata/hk_sector_flow.json` with this shape:

```json
{
  "as_of": "2026-07-08",
  "status": "display_only",
  "taxonomy_version": "hk_sector_flow.v0",
  "source_freshness": {
    "prices": "2026-07-08",
    "turnover": "2026-07-08",
    "southbound": null,
    "ipo": null
  },
  "buckets": [
    {
      "key": "internet_tech",
      "label": "Internet & Tech",
      "official_hsics": ["Information Technology", "Consumer Discretionary"],
      "n_names": 22,
      "adv_share": 0.531,
      "ret_1d": 0.0,
      "ret_5d": 0.0,
      "ew_ret_5d": 0.0,
      "rel_to_hsi_5d": 0.0,
      "turnover_share_delta_z": 0.0,
      "breadth_up_pct": 0.0,
      "southbound_net_hkd": null,
      "southbound_holding_delta_hkd": null,
      "flow_pressure_z": 0.0,
      "flow_quality": "inferred_pressure",
      "state": "needs_data"
    }
  ]
}
```

Then render four compact views:

1. **Sector Flow Heatmap**
   - Rows = sectors/themes.
   - Columns = 1D, 5D, 20D, 60D.
   - Color = `flow_pressure_z`.
   - Badges = actual southbound net when available.
   - Gray hatch = inferred only.

2. **Rotation Quadrant**
   - X-axis = relative strength versus HSI.
   - Y-axis = flow/turnover acceleration.
   - Bubble size = average dollar turnover or market cap if we later add cap.
   - Color = sector/theme.
   - Quadrants:
     - `accumulation`: flow up, RS not yet strong.
     - `leadership`: flow up, RS strong.
     - `exhaustion`: flow high, RS rolling over.
     - `outflow`: flow/pressure down, RS weak.

3. **Style/Size Strip**
   - Mega-cap platform tech.
   - Large-cap banks/dividend/SOE.
   - Mid/small growth.
   - IPO/new listings.
   - Local HK defensives.
   - ADR-linked China internet.

4. **Route Map**
   - Show inferred rotation from losing buckets to gaining buckets by comparing change in turnover share and relative strength.
   - Label it `inferred rotation route`, not literal dollars.

### 5.2 Score formula v0

Use a transparent composite. Do not tune it for returns yet.

```text
flow_pressure_z =
  0.30 * z(relative_return_vs_hsi_5d)
  + 0.25 * z(turnover_share_delta_5d_vs_20d)
  + 0.20 * z(dollar_turnover_impulse_5d)
  + 0.15 * z(breadth_thrust_5d)
  + 0.10 * z(southbound_or_holding_delta_intensity)
```

If the southbound leg is missing, reweight the available legs and mark `flow_quality = inferred_pressure`.

For top-risk/exhaustion:

```text
exhaustion_z =
  z(extension_vs_20d)
  + z(turnover_surge)
  - z(equal_weight_participation)
  + z(flow_price_divergence)
  + z(short_sale_intensity)
```

## 6. Why different HK categories lead at different times

### 6.1 Big tech / internet leads

Typical conditions:

- ADR/KWEB/FXI tailwind into the HK open.
- Southbound accumulation in liquid platform leaders.
- China platform-policy or AI/cloud/product catalyst.
- Oversold short-covering after a drawdown.
- Global rates/USD easing.

Dashboard label:

- `platform_tech_accumulation`
- `tech_ignition`
- `alibaba_tencent_bellwether_lead`
- `tech_chase_risk` if extended.

### 6.2 Banks, insurers, SOEs, dividend names lead

Typical conditions:

- Mainland southbound demand for high dividend/yield.
- China policy supports state-owned or financial stability assets.
- Tech growth risk appetite is weak, so money hides in yield/value.
- A/H discount compression in banks.
- Turnover rises in financial brokers/HKEX when market activity returns.

Dashboard label:

- `dividend_value_rotation`
- `banks_income_bid`
- `financial_turnover_beta`
- `defensive_southbound_bid`

### 6.3 IPOs and new listings lead

Typical conditions:

- Primary-market window reopens.
- Retail subscription frenzy returns.
- New economy listings attract attention.
- Secondary market is broad enough to support risk-taking.

But this can mean two opposite things:

- Early/mid recovery: IPO receptivity confirms liquidity and confidence.
- Late rally: speculative small/new issues outperform while large-cap breadth fades.

Dashboard label:

- `ipo_reopening_confirm`
- `ipo_froth_warning`
- `large_to_small_speculation`

### 6.4 Property leads

Typical conditions:

- China property policy easing.
- HK/local rate pressure eases.
- Short covering after extreme pessimism.
- A/H or credit stress improves.

Dashboard label:

- `policy_short_cover`
- `property_repair`
- `fragile_funding_dependent`

### 6.5 Materials/energy lead

Typical conditions:

- Commodity impulse.
- China fixed-asset/infrastructure optimism.
- SOE yield plus cyclical reflation.
- USD/real yield changes.

Dashboard label:

- `cyclical_reflation`
- `commodity_beta`

## 7. Implementation lanes

### W0: taxonomy and feed truth

Add:

- `engine/hk_sector_taxonomy.py`
- `tests/test_hk_sector_taxonomy.py`

Responsibilities:

- Map each HK ticker to repo sector, HSICS industry if available, thematic baskets, size/style bucket, Stock Connect eligibility, ADR/AH flags, and IPO/new-listing age if available.
- Emit a small audit table: missing sector, missing basket, missing ADV, stale price, duplicated ticker.
- Keep current/static taxonomy caveat visible.

### W1: pressure-only feed from existing repo data

Add:

- `engine/hk_flow_pressure.py`
- `scripts/build_hk_sector_flow.py`
- `tests/test_hk_flow_pressure.py`

Inputs already present:

- `data/hk_breadth/constituents.parquet`
- `data/hk_breadth/_closes_cache.parquet`
- `data/hk_stocks/*.parquet`
- `data/baskets_hk/membership.json`
- `site/marketdata/hk_heatmap.json`

Outputs:

- `site/factordata/hk_sector_flow.json`

Definition of done:

- Can show sector/theme/size `flow_pressure_z` without claiming actual net flow.
- Can show weighted and equal-weight performance divergence.
- Heatmap degrades if data is stale.

### W2: actual southbound overlay

Add:

- `collectors/hk_southbound_flow.py`
- `engine/hk_southbound_sector_flow.py`
- `tests/test_hk_southbound_sector_flow.py`

Preferred sources:

- HKEX Stock Connect historical daily/monthly stats for aggregate southbound.
- C&SD table 340-95005 for Stock Connect trading value with API/download support.
- HKEX Stock Connect shareholding search for stock-level holdings.
- Optional third-party stock-level buy/sell feed only if provenance and terms are acceptable.

Outputs:

- `data/hk_southbound/aggregate.parquet`
- `data/hk_southbound/shareholding.parquet`
- `site/factordata/hk_southbound_sector_flow.json`

Definition of done:

- Sector map shows actual southbound net where available.
- Per-stock holdings delta is separate from buy/sell net.
- SH/SZ channel split is retained.

### W3: size and IPO overlay

Add:

- `collectors/hk_ipo_tape.py`
- `engine/hk_ipo_smallcap_rotation.py`

Inputs:

- HKEX IPO/new listing stats.
- Listing date, IPO proceeds, first-day return, first 5/20 trading-day returns.
- HSCI size bucket where available.
- Repo fallback size proxy: ADV rank and turnover share.

Outputs:

- `site/factordata/hk_size_rotation.json`
- `site/factordata/hk_ipo_rotation.json`

Definition of done:

- Dashboard can tell "IPO/new listing bid" apart from "small-cap bid" and "large-cap tech bid."

### W4: UI integration

Add a compact panel to either `hk_heatmap.html` or `hk.html`:

- Tabs: `Sector`, `Theme`, `Size`, `IPO`.
- Toggle: `Actual flow only` / `Flow pressure`.
- Controls: 1D, 5D, 20D, 60D.
- Badges: `actual`, `proxy`, `inferred`, `stale`.
- Click sector -> shows top contributors, laggards, southbound evidence, and caveats.

Keep copy tight. The panel should not explain finance concepts in the UI; it should make the labels unambiguous.

## 8. First dashboard interpretation rules

Use these as plain-language states:

| State | Rule | Meaning |
|---|---|---|
| `actual_inflow` | actual signed flow > threshold and price/breadth confirms | Real buyer channel is visible. |
| `pressure_inflow` | turnover share + RS + breadth rise, no signed flow | Money appears to favor the bucket, but source is inferred. |
| `flow_absent_rally` | price up, turnover/flow not confirming | Could be thin squeeze or delayed data. |
| `flow_saturation` | signed flow high, price response fades | Mainland/retail demand may be crowded. |
| `outflow_pressure` | RS weak, turnover share down, signed/proxy flow negative | Bucket losing sponsorship. |
| `large_to_small_rotation` | large-cap pressure down, small/IPO pressure up | Speculative phase or late-cycle broadening. |
| `banks_defensive_bid` | banks/dividend up, tech/growth down | Yield/value defense, not broad risk-on. |
| `tech_beta_ignition` | platform tech pressure up with breadth and turnover | China internet beta is leading. |

## 9. Already covered / excluded fence

Do not duplicate or overwrite:

- The existing HK heatmap. Extend it with flow/pressure overlays.
- The existing HK market-structure paper's freshness/fast-overlay/bellwether ideas.
- The existing HK basket page and allocation page. Reuse their baskets, but do not claim those hindsight-curated baskets are proven alpha.
- The existing HK stock-selection verdict that HK residual stock selection is weak/dead until a new forward gate proves otherwise.

Do not claim:

- A sector "received net inflow" unless there is signed flow or holder data.
- A route map is literal money transfer.
- IPO strength is always bullish. It can be a liquidity confirmation or a froth warning.

## 10. Source links

External:

- Hang Seng Industry Classification System brochure: https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/brochures/B_HSICSe.pdf
- Hang Seng Composite Index Series methodology: https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/methodologies/IM_hscie.pdf
- HKEX Stock Connect statistics: https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics?sc_lang=en
- HKEX Stock Connect historical daily: https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en
- C&SD Stock Connect trading value table 340-95005: https://www.censtatd.gov.hk/en/web_table.html?id=340-95005
- HKEX Stock Connect shareholding search: https://www2.hkexnews.hk/Shareholding-Disclosures/Stock-Connect-Shareholding/Shanghai-Connect-and-Shenzhen-Connect?sc_lang=en
- HKEX Monthly Market Highlights: https://www.hkex.com.hk/Market-Data/Statistics/Consolidated-Reports/HKEX-Monthly-Market-Highlights?sc_lang=en
- HKEX IPO Centre: https://www.hkex.com.hk/Listing/IPO-Centre?sc_lang=en
- HKEX Southbound trends article: https://www.hkexgroup.com/Media-Centre/Insight/Insight/2024/HKEX-Insight/Southbound-Stock-Connect-Trends-and-Prospects?sc_lang=en

Repo-local:

- `CLAUDE.md`
- `research/HK_DATA_AUDIT.md`
- `research/HK_CANADA_STOCKS_PROBLEM_AUDIT_FOR_FABLE.md`
- `scripts/build_market_heatmap.py`
- `engine/market_heatmap.py`
- `site/heatmap.js`
- `templates/market_heatmap.html.j2`
- `data/hk_breadth/constituents.parquet`
- `data/hk_breadth/_closes_cache.parquet`
- `data/hk_stocks/*.parquet`
- `data/baskets_hk/membership.json`
