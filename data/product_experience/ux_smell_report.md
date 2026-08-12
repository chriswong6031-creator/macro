# Page evidence — measured facts

_Heuristics identify review targets; they do not determine that a page is bad._

Generated 2026-08-11T00:00:00Z · schema `mastermind.ux_smell_report.v1`

| route | page_id | words | h1 | panels | height px | h-overflow | slug hits | TODO hits | as-of | source | shots |
| --- | --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | :---: | :---: | ---: |
| /china.html | macro:china | 427 | 0 | 13 | 1966 | no | 0 | 0 | no | no | 1.0 |
| /confluence_screener.html | macro:confluence_screener | 551 | 1 | 0 | 2097 | no | 0 | 0 | yes | no | 1.0 |
| /hk.html | macro:hk | 585 | 0 | 21 | 2601 | no | 0 | 0 | yes | no | 1.0 |
| /index.html | index.html | 1884 | 1 | 5 | 10526 | no | 0 | 0 | yes | no | 1.0 |
| /macro.html | macro:macro | 513 | 0 | 29 | 2265 | no | 0 | 0 | no | no | 1.0 |
| /plans.html | macro:plans | 693 | 0 | 1 | 3146 | no | 0 | 0 | no | no | 1.0 |
| /products/index.html | macro:products_index | 500 | 1 | 4 | 2331 | no | 0 | 0 | no | no | 1.0 |
| /products/market-dashboards.html | macro:products_market_dashboards | 1399 | 1 | 0 | 9504 | no | 0 | 0 | yes | no | 1.0 |
| /products/market-terminal.html | macro:products_market_terminal | 1330 | 1 | 6 | 8670 | no | 0 | 0 | yes | no | 1.0 |
| /products/mastermind-ai.html | macro:products_mastermind_ai | 1198 | 1 | 0 | 7390 | no | 0 | 0 | yes | no | 1.0 |
| /research_vault.html | macro:research_vault | 657 | 1 | 0 | 2485 | no | 0 | 0 | no | no | 1.0 |
| /start.html | macro:start | 513 | 1 | 43 | 2416 | no | 0 | 0 | no | no | 1.0 |
| /us_stocks.html | macro:us_stocks | 755 | 1 | 8 | 2367 | no | 0 | 0 | yes | no | 1.0 |

## Metric notes

- **asof_present** — approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict
- **console_error_count** — distinct console 'error' texts across every captured state of the page
- **duplicate_heading_texts** — case-folded visible heading text seen more than once; a repeated section label across tabs is a legitimate duplicate
- **panel_count** — class-name heuristic over the configured selector list; both over- and under-counts are expected
- **payload_bytes_total** — sum of response body sizes reported by the driver for the reference state; excludes bodies the driver could not size
- **raw_slug_hits** — visible text matching 3+ segment snake_case; legitimate identifiers (file names, API keys quoted on purpose) match too
- **screenshot_completion** — captured states / attempted states for this page; states the registry excludes are not attempted and are recorded as gaps
- **section_count** — direct <section> children of <body> plus direct element children of <main>; an approximation of 'how many blocks is this page'
- **source_present** — approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict
- **visible_word_count** — whitespace-split innerText of <body>; Chinese text is not word-segmented, so a zh capture undercounts relative to en
