# Frozen research price panel — the contract, and how an instrument pins one

**Status:** infrastructure, display-tier. Freezing an evidence base promotes nothing and
gates nothing; it changes only whether a finished result can be re-derived.
**Module:** `research/research_panels/price_panel.py` · **Store:** `data/research_panels/`
**Guards:** `tests/test_research_price_panel.py` (27 tests, mutation-checked)
**Reference migration:** `research/prophet_us_audit/relay_position_standin.py`

---

## §0 The contract

1. **A version is write-once.** `build_panel("2026-08-06", …)` on an existing version
   re-reads its manifest and returns it. It does not rewrite a byte. A new evidence base is
   a **new version**, always.
2. **A reader pins a version explicitly.** `load_panel(version)` has no default, and
   there is deliberately **no `latest()`** — an instrument that asks for the latest is not
   pinned, and re-drifts the moment someone mints a new version.
3. **An unknown version raises.** `PanelVersionNotFound`, naming what *is* available. It
   never falls back to the live stores. That fallback is the entire defect, restated.
4. **The bytes are checked, not promised.** Every read re-hashes the parquet against the
   sha256 in its manifest. An in-place edit raises `PanelCorrupt` instead of quietly
   becoming the new evidence.
5. **Coverage is stated, not discovered.** Every manifest carries a per-name
   `price_source`, the `covered` list (names on an **adjusted** basis) and an explicit
   `uncovered` split. Print it beside your n.

## §1 Why — the drift is now the larger error term

Two audits measured that our evidence base moves under finished work:

| term | magnitude | source |
|---|---|---|
| frozen → cache-today **drift** | up to **0.24pp** | #4698 §4 |
| cache → adjusted **basis** | up to **0.15pp** | #4698 §4 |
| Prophet US decision boundaries | **0.26–0.98pp** | program preregs |

The receipt: PNC's 2026-06-22 close read `234.71` when #4698 sampled it on 2026-07-01 and
`232.8536` on 2026-08-06. Nothing recorded that it had changed. `data/{breadth,
midcap_breadth,smallcap_breadth}/_closes_cache.parquet` are re-based at an infrequent full
rebuild (last ≈2026-05-12) and accrue RAW closes after it, so a "frozen replay" priced from
them replays against numbers that moved.

Fixing the *basis* alone does not fix this. An instrument can be adjusted-first and still be
unreproducible, because the store it read is not the store the next reader will read. #4698
gave us the ladder; this gives the ladder's output a place to hold still.

The second half is coverage: **266 of 1,493** names carried no adjusted source in #4698's
label-grading sweep (**274 of 1,540** on the 2023-06-27 universe this panel freezes), so an
adjusted-first result silently sits on an **~82%** sub-universe unless the hole is counted.

## §2 How an instrument pins a version

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "price_panel", Path(REPO) / "research/research_panels/price_panel.py")
pp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pp)

PANEL_VERSION = os.environ.get("MY_PRICE_PANEL", "2026-08-06")   # pinned, in the source
px, m = pp.load_panel(PANEL_VERSION)

# Benchmarks share the file so both legs of an excess return are on one basis — but they
# are not members of the cross-section. Drop them before any day-median or ranking step.
px = px.drop(columns=[b for b in m["benchmarks"] if b in px.columns])
```

Record the pin in your results JSON so a reader of the *output* can find the evidence base
without reading the code:

```python
res["price_basis"] = {"basis": "frozen_panel", "reproducible": True,
                      "panel_version": m["version"], "panel_sha256": m["sha256"],
                      "coverage": pp.coverage_line(m)}
```

## §3 Print the covered count beside your n

The audit's finding was not that 266 names lack an adjusted source. It was that a result
could sit on an 82% sub-universe **without saying so**. `coverage_line()` is the saying-so:

```
n=28692 events over 1266/1540 adjusted-basis names (82.2%); 274 on the unadjusted cache,
0 unresolved; panel v2026-08-06 asof 2026-07-31
```

The `uncovered` block splits the two failure modes, because they are not the same problem:

* `uncovered.unadjusted_basis` — **in** the panel, priced from the raw cache. Usable, but
  carrying the distribution-shaped bias #4698 measured. 274 names on v2026-08-06.
* `uncovered.unresolved` — **not** in the panel. No column exists. 0 on v2026-08-06.

Studies that would rather lose a name than mix bases build with `allow_unadjusted=False`,
which moves the cache-only names into `unresolved` and drops their columns.

## §4 What the panel does NOT freeze

**It freezes prices. It does not freeze a calendar, a universe, or an observed-cell mask.**

This matters more than it sounds. #4698's first adjusted re-run grew its admitted population
**+31%**, because the adjusted stores carry the large-cap sleeve ~2 years deeper than
`data/breadth`'s cache — a coverage change that reads exactly like a basis effect if you are
not counting. Adopting the panel reproduces that shape: on the reference migration,
observed cells went **941,718 → 1,181,892 (+25.5%)** and events **14,427 → 28,692 (+98.9%)**
in one step.

So: an instrument that compares two populations still pins its own mask. A delta measured
against a pre-migration result is **basis + coverage together**, and must be reported that
way unless the mask was held fixed. The panel makes the population *visible*
(`panel_range`, `cells_observed`, per-name `price_source`); it does not make it constant.

The panel is also **close-only**. Instruments needing high/low/volume (`ignition_standins`,
`roc_extremes_battery`) cannot migrate until an OHLCV sibling exists — see §7.

## §5 Storage — the layout choice, deliberately

**Measured** on v2026-08-06 (777 sessions × 1,541 columns, 1,196,580 cells):

| layout | size | |
|---|---|---|
| **wide, float64, zstd** | **6.11 MB** | **chosen** |
| wide, float64, brotli | 5.91 MB | −3%, slower codec, no reader gain |
| wide, float64, snappy | 8.71 MB | +43% |
| wide, float32, zstd | 5.99 MB | saves 1.8% by perturbing every price |
| long (date,ticker,close), zstd | 5.37 MB | −12%, but see below |

Manifest: 59 KB. Build: ~10 s. Read + sha256 verify: ~0.13 s.

**One wide parquet per version, no partitioning.** The monthly-part
(`engine/us_context_vector.py`) and month-grouped-day-part
(`engine/us_prophet_grades.py`) precedents exist to solve **accretion**: a nightly writer
rewrites one accreting blob, so git stores a fresh multi-MB copy every night, and
partitioning bounds the churn to the current part. This artifact has the opposite lifecycle
— write-once, minted deliberately, never rewritten. No part would ever be rewritten, so
partitioning buys nothing, costs the reader a glob+concat, and weakens the central property:
**one version is one file whose bytes are the thing under test.**

*Wide over long*, despite long being 12% smaller: wide is the shape every consumer wants
(`px.rolling(63).max()`, `px.shift(-H)/px - 1`). Long forces a pivot on every read, and a
pivot's column order is a function of the data — non-determinism at the exact spot where
this artifact must be deterministic.

*float64 over float32*: 1.8% smaller for a silent perturbation of every price. An artifact
whose only job is exact replay does not introduce its own basis error to save 110 KB.

*Full snapshots over deltas between versions*: a delta chain makes v2 unreadable without an
unmutated v1, which reintroduces the dependency the design removes. At 6 MB, false economy.

### Growth math

Per session at current width: 6.11 MB / 777 ≈ **7.9 KB**. At ~252 sessions/year, a version
minted a year later costs **≈ +2.0 MB** (≈8.1 MB), two years **≈10.1 MB** — linear, with
universe width the other multiplier.

**Cadence is the real cost control, not layout.** Every version is a full independent
snapshot, so store growth is `size × versions`:

| cadence | year-1 growth |
|---|---|
| per program / ratification cycle (**intended**, ~4/yr) | ~25–30 MB |
| monthly | ~75 MB |
| nightly (**never do this**) | ~1.5 GB |

**Mint a version when a research program needs an evidence base, not on a schedule.** There
is no nightly job and none should be added; a nightly frozen panel is a contradiction.

### Committed, not gitignored

`data/research_panels/` is **git-tracked**. The gitignore precedent excludes stores that are
*"regenerated every daily run"* (`data/factordata/panel/`). This is the exact opposite: the
panel is **not regenerable**, because the stores mutate underneath it — that is the whole
thesis. An uncommitted frozen panel is not frozen. House precedent for tracked frozen
evidence: `data/personality_timing/relief_hazard_audit_grid_v1.parquet` (42.3 MB),
`data/china_search/closes.parquet` (13.0 MB). 6 MB/version is well inside the norm.

## §6 Minting a version

```bash
python3 research/research_panels/price_panel.py 2026-09-01 --asof 2026-08-31 --start 2023-06-27
```

Default universe = the union of the three breadth caches' columns (the population these
instruments measure). The names come from the caches; the **prices do not** — every name is
re-resolved through #4698's adjusted-first ladder
(`baskets_ohlcv → yahoo → data_stocks → closes_cache_UNADJUSTED`). Benchmarks (`--benchmarks`,
default `SPY`) ride the same ladder into the same file.

Re-running an existing version prints `NOT rewritten (write-once)` and changes nothing.

## §7 Reference migration + backlog

**Migrated (this PR):** `research/prophet_us_audit/relay_position_standin.py` — 124 lines,
priced by concatenating the three caches at run time. Now pinned to v2026-08-06, reports its
coverage beside its n, and writes `relay_position_standin_panel_v2026-08-06.json`. The
pre-migration `relay_position_standin_results.json` is **retained untouched**.

Measured on the pre-migration code, same repo, 2026-08-06: **6 of its 31 numeric statistics
had already moved** against its own committed JSON — two events re-partitioned between the
`mid` and `late` buckets, four cell statistics by 0.01pp. Small here (the outcome is
day-demeaned, which cancels most of a common re-base), but unbounded and unrecorded.

**Backlog — NOT migrated in this PR.** Priced from the unadjusted caches (basis + freeze):

| instrument | note |
|---|---|
| `fresh_ticks_extension_replay.py` | **collides with open PR #4698** (adds a `PRICE_BASIS` switch) — migrate after it lands |
| `label_grading_battery.py` | **collides with #4698** |
| `reclaim_veto_packet.py` | **collides with #4698**; also CI-wired (`tests/test_us_reclaim_veto_packet.py`) |
| `leader_reset_study.py` | clean lane |
| `name_score_pk_benchmark.py` | clean lane |
| `runner_exclusion_audit.py` | clean lane |
| `superintelligence_standins.py` | clean lane |

Already adjusted-first but **unpinned** (freeze only — and blocked on a close-only panel,
§4): `ignition_standins.py`, `roc_extremes_battery.py`. Both glob
`data/baskets/ohlcv/*.parquet` for high/low/volume; migrating them needs an OHLCV panel
sibling, which is deliberately out of scope here.

Migrating an instrument does **not** re-open its finding. A pinned re-run is a new run
against a new population (§4) and is reported as such — never written over a frozen results
JSON, and never presented as a correction of one without a mask-pinned decomposition.
