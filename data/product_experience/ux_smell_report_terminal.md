# Page evidence — measured facts

_Heuristics identify review targets; they do not determine that a page is bad._

Generated 2026-08-11T00:00:00Z · schema `mastermind.ux_smell_report.v1`

| route | page_id | words | h1 | panels | height px | h-overflow | slug hits | TODO hits | as-of | source | shots |
| --- | --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | :---: | :---: | ---: |
| /discover | terminal:discover | 76 | 1 | 0 | 900 | no | 0 | 0 | no | no | 1.0 |
| /options | terminal:options | 76 | 1 | 0 | 900 | no | 0 | 0 | no | no | 1.0 |
| /portfolio | terminal:portfolio | 81 | 1 | 0 | 900 | no | 0 | 0 | no | no | 1.0 |
| /terminal | terminal:terminal | 533 | 0 | 1 | 900 | no | 0 | 0 | yes | no | 1.0 |

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
