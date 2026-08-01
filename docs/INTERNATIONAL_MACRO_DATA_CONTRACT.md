# International macro dashboards — data contract

## Scope

`japan.html`, `south_korea.html`, `euro_area.html`,
`united_kingdom.html`, and `india.html` are five views over one
`international_macro_dashboard.v1` contract. The shared engine is descriptive.
It does not score individual stocks and does not expose Prophet.

The Euro Area route means the currency union, not the European Union. Current
official Eurostat adapters use EA21 composition in 2026. Any legacy EA19/EA20
fallback is identified in provenance. STOXX Europe 600 is broader-Europe market
context and never substitutes for euro-area macro data.

## Normalized contract

Each route receives:

- regime: growth, inflation, confidence, liquidity, recession stress, and the
  engine’s data-limited state;
- decision: a transparent 0–100 descriptive score, component receipt, current
  posture, action, and transition conditions;
- history: the same descriptive score over the latest 60 sessions;
- market: local index and FX context;
- policy and verified central-bank calendar;
- risk: the existing market-specific calibrated forward-pullback probability,
  its measure, scare families, and trajectory;
- metrics: normalized numeric value, display unit, and release period;
- local lenses: explicit country questions with a named authoritative source;
- health and sources: fresh/stale/missing states, access mode, cadence,
  licensing note, fallback role, and source URL.

Missing is a state, not zero. A local lens with no production-verified series
renders “Awaiting verified official adapter.” It cannot vote in the regime.

The descriptive decision score is:

`50 + 22×growth − 10×positive inflation pressure − 0.18×recession stress
+ liquidity adjustment + current calibrated-risk-state adjustment`

It is not a probability. The 21-session pullback probability is separately
calibrated by `engine/risk_radar_intl.py` on each market’s own history.

## Source hierarchy and current production state

| Market | Authoritative sources | Access / cadence | Current operational state |
|---|---|---|---|
| Japan | Bank of Japan; Statistics Bureau; Cabinet Office; METI; Ministry of Finance | BOJ keyless JSON/CSV API plus official downloads; daily to quarterly | Price/FX and OECD/FRED macro fallbacks are live. BOJ’s 2026 API is the preferred next series-by-series adapter. The stale CPI fallback remains visibly stale. |
| South Korea | Bank of Korea ECOS; KOSIS/Statistics Korea; MOTIE | ECOS and KOSIS require registered API keys; MOTIE official releases | Price/FX and configured OECD/FRED fallbacks are live. Key-gated official series remain explicit access blockers. |
| Euro Area | ECB Data Portal; Eurostat; European Commission | Keyless SDMX/Statistics APIs; daily to quarterly | ECB deposit rate and Eurostat EA21 unemployment are official overrides. Other configured FRED series remain documented fallbacks. |
| United Kingdom | Bank of England; ONS; OBR | BoE downloads; keyless ONS v1 beta API; release dependent | Price/FX and configured OECD/FRED fallbacks are live. ONS beta endpoints require dataset-specific release/version adapters before replacing fallbacks. Labour measurement uncertainty is called out in the UI. |
| India | RBI DBIE; MoSPI; Commerce Ministry; IMD | Official downloads, MoSPI CPI API/eSankhyiki, bulletins; daily to quarterly | Price/FX and configured FRED fallbacks are live. Official adapters remain blank until their units and release-period semantics pass fixtures. |

Authoritative documentation:

- BOJ API launch and statistical search:
  <https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm>
- Bank of Korea ECOS / KOSIS:
  <https://ecos.bok.or.kr/> and
  <https://kosis.kr/openapi/index/index.jsp>
- ECB API / Eurostat API:
  <https://data.ecb.europa.eu/help/api/data> and
  <https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction>
- ONS developer hub:
  <https://developer.ons.gov.uk/>
- MoSPI API / RBI DBIE:
  <https://api.mospi.gov.in/> and
  <https://data.rbi.org.in/DBIE/>

Source reuse remains subject to each linked provider’s terms. The dashboard
stores observations and source metadata, not copyrighted release prose.

## Collection, cache, and failure semantics

`collectors/intl_macro.py` fetches every series independently with bounded
timeouts, exponential backoff, a circuit breaker, and frozen-tail detection.
Official ECB/Eurostat series override the matching FRED operational frame only
after parser and unit validation. Failure preserves the fallback or the
last-known-good parquet and writes the error to
`data/intl_macro/provenance.json`.

Parquets under `data/intl_macro/` are deterministic, upserted observation
caches. The provenance sidecar retains provider, source ID and URL, request and
source timestamps, last observation, unit, release-period semantics, and
official/fallback/missing status.

Central-bank calendars are hand-verified against official schedules in
`data/intl_risk/cb_calendar.yml`. A past event receives a “released” outcome
state but no fabricated policy decision. The user follows the official link for
the release outcome.

## Update and rendering path

The existing scheduled collector runs `IntlMacroAdapter`. The `intl` renderer
recomputes the shared regime histories and renders the comparative dashboard
plus all five country routes. Template or builder changes are included in the
render scope, and generated `site/*.html` pages are committed with their source
changes where required by the repository’s render contract.
