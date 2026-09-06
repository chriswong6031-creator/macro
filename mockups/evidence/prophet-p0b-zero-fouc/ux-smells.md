# Page evidence — measured facts

_Heuristics identify review targets; they do not determine that a page is bad._

Generated 2026-09-06T10:50:42Z · schema `mastermind.ux_smell_report.v1`

| route | page_id | words | h1 | panels | height px | h-overflow | slug hits | TODO hits | as-of | source | shots |
| --- | --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | :---: | :---: | ---: |
| /canada_stocks.html | macro:canada_stocks | 533 | 1 | 9 | 3357 | no | 0 | 0 | yes | no | 1.0 |
| /hk_stocks.html | macro:hk_stocks | 980 | 1 | 9 | 3978 | no | 1 | 0 | yes | no | 1.0 |

## Metric notes

- **asof_present** — approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict
- **console_error_count** — distinct console 'error' texts across every state of the page the driver attempted, captured or not — a state that failed to load is often the one carrying the evidence
- **duplicate_heading_texts** — case-folded visible heading text seen more than once; a repeated section label across tabs is a legitimate duplicate
- **panel_count** — class-name heuristic over the configured selector list; both over- and under-counts are expected
- **payload_bytes_total** — sum of response body sizes reported by the driver for the reference state; excludes bodies the driver could not size
- **raw_slug_hits** — visible text matching 3+ segment snake_case; legitimate identifiers (file names, API keys quoted on purpose) match too
- **screenshot_completion** — captured states / attempted states for this page; states the registry excludes are not attempted and are recorded as gaps
- **section_count** — direct <section> children of <body> plus direct element children of <main>; an approximation of 'how many blocks is this page'
- **source_present** — approximate contract probe (selector OR case-insensitive text pattern); absence is a prompt to look, not a verdict
- **visible_word_count** — whitespace-split innerText of <body>; Chinese text is not word-segmented, so a zh capture undercounts relative to en
