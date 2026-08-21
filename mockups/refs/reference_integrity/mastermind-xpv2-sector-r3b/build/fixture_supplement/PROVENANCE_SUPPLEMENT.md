# XPV2-SC-R3B fixture SUPPLEMENT — PROVENANCE

Companion capture to `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/`
(the R3A pack). **The R3A fixture directory and its `receipts.json` were NOT
touched, edited, or re-captured by this work** — every file under
`research/reference_integrity/mastermind-xpv2-sector-r3/fixture/` is
byte-identical to what R3A shipped; `git status` on that path shows no diff.
This supplement lives entirely under the R3B build directory
(`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/fixture_supplement/`)
and exists only because the R3A commission's explicit fixture list did not
include four producer artifacts the six-view rebuild needs (R3A
`PROVENANCE.md` §"What is NOT in this fixture set" names them as GAP/adjacent
rows) plus one extracted HTML fragment.

- **Capture commit**: `4c55fe433490adfd75fd901ef25f5793db2202db` — the SAME
  commit the R3A fixture was captured at (`fixture/PROVENANCE.md`), so the
  supplement and the frozen fixture share one epoch. This is deliberate: a
  later commit would let the two halves of one page disagree about what
  night's data they show.
- **Capture date**: 2026-08-20 (recorded in `research/.../fixture/PROVENANCE.md`
  as the R3A capture date; this supplement was captured at the same commit,
  same session, 2026-08-20).
- Every JSON/JS entry below is a byte-for-byte copy of the named `site/...`
  artifact at the capture commit — `git show <commit>:site/<path>`, no
  recompute, no reformatting, no reordering.

## Per-file capture table

| supplement path | source path (at capture commit) | producer | bytes | sha256 |
|---|---|---|---|---|
| `sector_cycles_data.js` | `site/sector_cycles_data.js` | `scripts/build_sector_cycles.py` (window.SECTOR_CYCLES writer, referenced `templates/si_workspace.js:107` `loadCycles()`) | 318,577 | `aa15f230421acda47659c20bff69dd17b6f2e350a389643b7a9c6f258fcae22a` |
| `marketdata/sp500_heatmap.json` | `site/marketdata/sp500_heatmap.json` | Money view's heat treemap (`heatmap.js`, lazy-mounted per `si_workspace.js:79` `money:['heatmap.js']`) | 117,950 | `14309d888dafc5076bf68236365414e743cd53f9a9e703b312e189068c3b5d35` |
| `basketdata/etf_pulse.json` | `site/basketdata/etf_pulse.json` | Money-flow chip source (routing_contract.md lane C §3) | 4,201 | `2d5cbc89df108177d0c5d4e315fdb25ca936e1e4f349199e26c4f579a3cb4479` |
| `basketdata/vol_sentiment.json` | `site/basketdata/vol_sentiment.json` | Money-flow chip source (routing_contract.md lane C §3) | 819 | `845c68eec1c271d55422cc00bf5556bf2a8bca1af22a52e81426b67021f8c647` |
| `fragments/sc_flows.html` | extracted from `site/sector_central.html` | `scripts/build_sector_central.py:263-328 _flows_section_html()` | 8,860 | `a0a3805fb339f9659dac6d1ec81883481246f8b13d8f9f153c060aa0e17cafd3` |

`receipts_supplement.json` (same shape as the R3A `fixture/receipts.json`)
carries the machine-readable form of this table; `build/build_reference.py`
recomputes every hash at build time and aborts on any mismatch.

## Extraction rule — `fragments/sc_flows.html`

`_flows_section_html()` (`scripts/build_sector_central.py:263-328`) returns a
Python string built from exactly two sibling top-level elements with no
wrapper: `<div class='scc-section-h' id='sc-flows'>…</div>` (the section
heading) immediately followed by `<div class='scf-wrap'>…</div>` (the table +
footnote). The Jinja template inserts this string via `{{ flows_html|safe }}`
(autoescape does not re-serialize already-safe content), so it appears
byte-verbatim inside the rendered `site/sector_central.html` — single-quoted
HTML attributes and all, not re-quoted to double quotes.

Extraction was performed against `git show
4c55fe433490adfd75fd901ef25f5793db2202db:site/sector_central.html`
(308,611 bytes) with a Python script, not a manual copy-paste, to avoid a
transcription error in an 8.5KB single-line fragment:

1. Locate the literal start marker `<div class='scc-section-h' id='sc-flows'>`
   (exact string, single-quoted attributes as the producer emits them) — this
   occurs exactly once in the file, at byte offset 164,346.
2. Locate the first occurrence of the literal end marker `</p></div>` at or
   after the start marker — the fragment's only `<p>` element is the
   trailing "Display-only" footnote, immediately followed by the `.scf-wrap`
   div's own close, so this is unambiguous. Found at byte offset 172,877
   (end of marker).
3. The substring `html[164346:172877]` is the complete fragment: 8,531
   Python-string characters / 8,860 UTF-8 bytes (the em-dashes, minus signs,
   and CJK glyphs in the flow table cost more than one byte each).
4. Sanity check performed at capture time: the extracted substring contains
   exactly 2 `<div` opens and 2 `</div>` closes (the outer `#sc-flows` div
   and the `.scf-wrap` div; no nested `<div>` appears inside the table/p
   content), confirming the end marker did not cut the fragment short or run
   past a sibling element.

The fragment is embedded by the assembler as
`<script type="text/x-ref-fragment" data-path="fragments/sc_flows.html">`
(inert, not auto-executed) — a view partial that wants to show the flow
board reads this script's `.textContent` and inserts it via `innerHTML`,
exactly mirroring how production ships it as pre-rendered server HTML rather
than a client-side fetch.

## Hero context / `data-regime` / `generated_utc` — confirmed equivalent, NOT separately captured

The commission asked to check whether the hero context block
(`theme_context`/`factor_season`), the `data-regime` attribute, and the
`generated_utc` footer need their own capture beyond what the R3A fixture
already carries in `basketdata/si_handoff.json`. They do not — confirmed by
direct comparison against `site/sector_central.html` at the same capture
commit:

- `si_handoff.json.theme_context` and `si_handoff.json.factor_season` are the
  exact objects `scripts/build_sector_central.py:448-449` passes into the
  template as `theme_context=ctx.get("theme_context")` /
  `factor_season=ctx.get("factor_season")` — no independent compute happens
  in the template (`fixture/PROVENANCE.md` row for `si_handoff.json` says the
  same: "assembles theme_context/factor_season/flow/… no independent
  compute").
- `data-regime` — the rendered page carries `data-regime="broad"` (confirmed
  by grep of `site/sector_central.html` at the capture commit). The fixture's
  `si_handoff.json.flow.cluster.regime` is `"broad"`. Identical value,
  confirming the attribute is a direct restatement of that field
  (`scripts/build_sector_central.py:450`: `flow=ctx.get("flow")`).
- `generated_utc` footer — the rendered page's footer text and
  `si_handoff.json.generated_utc` both read `"2026-08-20 16:51 UTC"`
  (confirmed by grep of both sources at the capture commit). Identical value,
  confirming `scripts/build_sector_central.py:453`:
  `generated_utc=ctx.get("generated_utc") or data.get("as_of") or ""` reached
  the `ctx.get("generated_utc")` branch and passed it straight through.

Since all three are byte-identical restatements of fields the R3A fixture
already carries, capturing them again as separate files would only create a
second copy that could silently drift from the first. `build_reference.py`
reads `data-regime` and the footer date directly from the embedded
`si_handoff.json` bytes at assembly/render time rather than from any new
capture.

## Addendum — 2026-08-21: `marketdata/nasdaq_internals.json`

Captured after the D1 follow-up lane identified that the Confluence view's
Nasdaq internals organ (`templates/subsectors.js:417-448` — a RETAIN
capability, rendered by `build/views/confluence.html`'s `internalsDisc()`)
was fully built but rendered nowhere: its producer artifact was in neither
the R3A fixture nor this supplement's original five entries, so the organ's
code path had only been proven via an in-memory smoke test, never against
real producer bytes.

- **Capture commit**: `4c55fe433490adfd75fd901ef25f5793db2202db` — the SAME
  commit as every other entry in this supplement and the R3A fixture, so
  this addendum does not introduce a second epoch.
- **Capture date**: 2026-08-21 (this addendum's capture date; the commit and
  fixture epoch remain 2026-08-20 as recorded above).
- Byte-for-byte copy of `site/marketdata/nasdaq_internals.json` at the
  capture commit — `git show 4c55fe433490adfd75fd901ef25f5793db2202db:site/marketdata/nasdaq_internals.json`,
  no recompute, no reformatting, no reordering.

| supplement path | source path (at capture commit) | producer | bytes | sha256 |
|---|---|---|---|---|
| `marketdata/nasdaq_internals.json` | `site/marketdata/nasdaq_internals.json` | Nasdaq internals organ (`templates/subsectors.js:417-448` `niSection()`, mounted by `build/views/confluence.html` `internalsDisc()`, hard-gated on the Nasdaq tab) | 4,004 | `d21d64ee2a417d88097386479cbc02b968c1693d249881c87081042046dfb4d6` |

Embedded the same way as the other supplement JSON entries (`marketdata/sp500_heatmap.json`,
`basketdata/etf_pulse.json`, `basketdata/vol_sentiment.json`): a plain
`application/json` data-registry `<script>` block keyed by its
production-relative path (`build/build_reference.py`'s `SUPPLEMENT_JSON_PATHS`
set), read via `reg('marketdata/nasdaq_internals.json')` exactly as
production's own client fetch resolves it
(`build/views/confluence.html:1048`).

## What this supplement explicitly does NOT capture

Per the commission's OUT-OF-SCOPE instruction and the orchestrator's Time
Machine ruling: `oracledata/tm_episodes.json` and the per-year Time Machine
chunk files are **not captured**. The Explore view's Time Machine mount
renders manifest-driven from the in-fixture `oracledata/tm_manifest.json`
only; any episode/chunk fetch the mount would normally issue is recorded by
the runtime shim as `recorded-not-executed` rather than served from an
embedded artifact. See `build/README_BUILD.md` §"Time Machine" for the full
ruling and `build/runtime_shim.js`'s registry-miss behavior.
