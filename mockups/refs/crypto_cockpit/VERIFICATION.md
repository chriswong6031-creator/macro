# W0 visual verification

Verified in the Codex in-app Chromium browser against the local repository
server on 2026-07-29. Reference proofs are stitched from ordinary viewport
captures so every shelf is recorded at its true 1280px or 375px responsive
layout without full-page capture reflow.

## Structural checks

| Surface | Desktop | Mobile | Shelf roots | Verdict roots |
| --- | ---: | ---: | --- | ---: |
| Vector | 1280px | 375px | `S1`–`S6` exact | 1 |
| Crypto hub | 1280px | 375px | `H1`–`H8` exact | 0 |

The Chinese mobile hub measured `innerWidth=375` and
`documentElement.scrollWidth=375`; no horizontal overflow was present. Its
English spans computed to `display:none` and Chinese spans to `display:inline`.

## Computed-style evidence

| Mode | Body | Panel | Rule | Up | Down |
| --- | --- | --- | --- | --- | --- |
| Dark EN | `rgb(15,17,21)` | `rgb(24,27,33)` | `rgb(42,47,58)` | `rgb(69,184,115)` | `rgb(224,100,100)` |
| Light EN | `rgb(247,248,250)` | `rgb(255,255,255)` | `rgb(234,236,240)` | token `#1f9a55` | token `#cf4040` |
| Dark ZH | `rgb(15,17,21)` | `rgb(24,27,33)` | `rgb(42,47,58)` | `rgb(224,100,100)` | `rgb(69,184,115)` |

The BTC accent computed from `--btc` as `#f7931a`. Hero numerals resolved to
the shared `ui-monospace` stack. The Chinese direction convention is visibly
and computationally flipped: positive is red and negative is green.

## Proof set

Each surface has these six committed full-page references:

- desktop: dark English, light English, dark Chinese;
- mobile: dark English, light English, dark Chinese.

Files live in `shots/` and use the
`<surface>-<viewport>-<theme>-<language>.jpg` naming contract.
