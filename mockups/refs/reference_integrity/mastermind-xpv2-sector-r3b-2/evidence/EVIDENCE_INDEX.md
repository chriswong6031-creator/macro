# Evidence index — XPV2-SC-R3B.2 final continuation

**Candidate:** `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`

**Candidate SHA-256:** `091bc578d18876ae1e9f922235ddac82d8d7519e0ceb579d7a92010a4915bd0b`

**Capture method:** fresh headless Playwright/Chromium contexts against the exact
assembled `file://` candidate above; no rebuild during capture.

**Visual packet:** 61 PNG files, each byte-hashed and state-described in
`capture_manifest.json`.

**Total evidence packet:** 75 files before the freeze/CI text receipts are added.

The orange `R3 REFERENCE HARNESS — not product UI` drawer is reference-only
test chrome. It remains visible in ordinary full-view evidence and is hidden
only in the 320-physical/200% element capture where fixed chrome would cover the
subject.

## All-six matrices

`capture_manifest.json` is the exhaustive screenshot inventory. The programmatic
matrix contains:

- `all6-<view>-1440-dark-en.png` — all six views;
- `all6-<view>-1440-light-en.png` — all six views;
- `all6-<view>-390-dark-en.png` — all six views;
- `all6-<view>-390-dark-zh.png` — all six views.

Every capture asserted `.si-view.on[data-view]` matched the requested view before
the screenshot was written.

## Changed-state evidence

| obligation | visual files | machine receipt |
|---|---|---|
| B2-01 one path/one customer term | Overview/Map matrix plus `b2-08-map-rank-scope-390-dark-{en,zh}.png` | `closure_audit.json`: five Strength/强度 sites plus second-term exclusion, EN/ZH |
| B2-05 complete figure naming | `b2-05-overview-figures-*` and `b2-05-conviction-*` at 1440/390/320, EN/ZH, including 320 physical at 200% | `fig_naming_audit.json`: 18 figures/cell, 4 valueless by construction, 0 unnamed, 0 mobile-naked, 0 desktop duplicate captions, 30/30 exact-value proofs |
| B2-06 treemap collision | `money-heatmap-{320,390}-*` plus the 820 controls | `treemap_labels_audit.json`: 12 cells, 5,928 tiles, 288 painted labels, 0 cross-owner overlaps |
| B2-08 rank scope proximity | tight `b2-08-map-rank-scope-390-dark-{en,zh}.png` crops | `state_smoke.json` and `closure_audit.json` |
| B2-09 neutral Recent Wrong | `b2-09-moving-recent-wrong-1440-light-{en,zh}.png` | reference-authored contrast matrix: 0 AA failures; source/state guard retained |
| B2-10 mobile ramp relationship | all-six Confluence mobile captures | `mobile_geometry_audit.json`: ramp painted only in 2/2 five-track cells, suppressed in 8/8 stacked cells |
| B2-11 wrapped receipt | `b2-11-headline-receipt-{320,390}-dark-{en,zh}.png` | `mobile_geometry_audit.json`: 10/10 on/after final wrapped line and inside the statement box |
| B2-12 distinct authority terms | Confluence all-six captures | `closure_audit.json`: coverage omission and in-table low reliability have distinct customer terms, nonzero census, EN/ZH |
| B2-13 shared receipt target | `b2-13-shared-receipt-control-390-dark-en.png` | `closure_audit.json`: one target, Overview control + three Moving controls, exact control census 4; `aria_id_audit.json`: 75/75 refs resolved in each language |
| B2-14 ZH target floor | all-six Confluence mobile captures | `mobile_geometry_audit.json`: 36 controls measured, 13 ZH 收起, 0 below 44px on either axis |
| B2-15 context/5d qualification | `b2-15-money-context-{1440,390}-dark-{en,zh}.png` | `closure_audit.json`: producer `is_context_only=true`, only 5d proven, 21d false; three localized clauses; explicit separate 21d line/hairline |

## Heatmap / Browse matrix

- `money-heatmap-{320,390,820}-{dark,light}-{en,zh}.png` — twelve
  colour-field cells.
- `money-browse-names-320-dark-en.png` and
  `money-browse-names-390-dark-zh.png` — opened, nonempty per-stock escape hatch.
- `treemap_labels_audit.json` — painted-width collision and noninteractive-tile
  census.

The heatmap glyph/colour-field contrast axis remains **UNMEASURED**. The flat-
surface audit excludes 440 shadowed glyph cells because it has no valid method
for a data-driven field; neither this index nor the verifier promotes that axis
to PASS. `contrast_audit.json` separately measures 15,388 reference-authored
flat-surface cells with 0 AA failures. Seventy-five low-contrast cells in the
receipt-bound `sc_flows` producer fragment remain upstream/R3C-only.

## Programmatic receipts

| file | result |
|---|---|
| `zoom_sweep.json` | 48/48 cells green: six views x 320/390/768/820 physical x EN/ZH at 200%; 0 document overflow, semantic clipping, or clipped primary controls |
| `fig_naming_audit.json` | 6/6 cells green; candidate SHA-256 bound |
| `treemap_labels_audit.json` | 12/12 cells green |
| `mobile_geometry_audit.json` | 10/10 cells green |
| `closure_audit.json` | 40/40 rendered semantic checks green across EN/ZH; candidate SHA-256 bound |
| `closure_mutation_results.json` / `CLOSURE_MUTATION_RESULTS.md` | 8/8 independent removals produced nonempty, pairwise-distinct reds; candidate SHA-256 bound |
| `MUTATION_RESULTS.md` | inherited inventory suite: 11/11 mutations produced unique reds; 13/13 suite checks green |
| `state_smoke.json` | 6 canonical + 21 legacy view routes; 20/21 legacy DOM targets with documented `#sc-top` absence; gated/hydrated/ungated; four isolated Confluence universes; `href="#"` count 0 |
| `aria_id_audit.json` | EN and ZH: 253 IDs, 0 duplicate IDs, 75 references resolved, 0 unresolved |
| `LANG_PROBE.txt` | 7/7 document-language transitions green |
| `contrast_audit.json` / `CONTRAST_TABLE.md` | 0 relevant AA failures, 0 sub-ramp text, 0 parser-suspect cells; excluded axes disclosed above |
| `capture_manifest.json` | exhaustive 61-file screenshot hash and state ledger bound to candidate SHA-256 |

## Withdrawn and upstream-only truth receipts

The final Sol handoff supersedes the older draft commission for these axes:

- **Old B2-02 is withdrawn and not scored.** The fresh rendered census records
  one `📊` glyph in the Moving view and zero in the other five. This is an exact-
  byte receipt discrepancy with the recovered rerun premise that reported zero
  rendered hits. No candidate change was made because the final handoff
  explicitly forbids reviving old B2-02.
- **Old B2-03 is withdrawn/reclassified.** Candidate-owned heatmap flat-surface
  failures are zero; the 440-glyph colour-field axis is UNMEASURED, never PASS.
- **Old B2-04 is withdrawn from candidate scope.** Producer `note_zh` /
  `category_zh` and language-of-parts debt remain upstream/R3C-only and are
  recorded, not translated in the reference.

## Freeze binding

The immutable freeze commit is stamped here after the candidate/evidence commit
is created. No screenshot, machine receipt, build source, or candidate byte may
change after that commit; only the RIG frozen-SHA/status metadata stamp may
follow it.
