"""Versioned FROZEN price panel for research instruments — an evidence base that holds still.

WHY THIS MODULE EXISTS
======================
Two audits measured that our research evidence base is not reproducible, and that the
irreproducibility is now the LARGER of the two error terms:

* **The breadth close caches move under a finished study.**  ``data/{breadth,
  midcap_breadth,smallcap_breadth}/_closes_cache.parquet`` are re-based at an infrequent
  full rebuild (last ≈2026-05-12) and accrue RAW closes after it.  Receipt: PNC's
  2026-06-22 close read ``234.71`` when #4698 sampled it on 2026-07-01 and ``232.8536``
  on 2026-08-06.  Nothing in the repo recorded that the number changed.  A "frozen replay"
  priced from these caches is replaying against numbers that moved.
* **266 of 1,493 names have no adjusted source at all**, so a result computed on an
  adjusted-first ladder silently sits on an ~82% sub-universe unless the hole is counted.

Measured magnitudes (#4698 §4, and the #4678 veto-leg adjusted re-run): frozen→cache-today
drift moves a decision statistic by up to **0.24pp**, while the cache→adjusted BASIS effect
maxes at **0.15pp**.  Decision boundaries in the Prophet US program run **0.26–0.98pp**.
So the basis fix alone is not enough — an instrument can be on the right basis and still be
unreproducible, because the store it read is not the store the next reader will read.

WHAT THIS FIXES AND WHAT IT DOES NOT
------------------------------------
This module materializes the adjusted-first ladder ONCE into a versioned artifact and then
never touches it again.  An instrument pins a version; every later re-run of that
instrument reads the same bytes.  That removes the drift term entirely.

It does NOT freeze a calendar or an observed-cell mask.  #4698's trap #1 — *coverage
masquerading as basis*, where their first adjusted run grew the admitted population +31%
because the adjusted stores carry the large-cap sleeve ~2 years deeper than the cache — is
still the instrument's problem.  The panel freezes PRICES.  An instrument that compares two
populations still has to pin its own mask.

USAGE
=====
Writing (deliberate, not nightly — see the cadence law in the adoption note)::

    from price_panel import build_panel
    m = build_panel("2026-08-06", tickers, asof="2026-07-31", start="2023-06-27",
                    benchmarks=("SPY",))

Reading — the version is REQUIRED and there is no ``latest()``::

    from price_panel import load_panel
    px, m = load_panel("2026-08-06")
    m["n_covered"]                  # names on an ADJUSTED basis — print this beside your n
    m["uncovered"]["unadjusted_basis"]   # in the panel, but priced from the raw cache
    m["uncovered"]["unresolved"]         # not in the panel at all
    m["price_source"]["PNC"]        # per-name ladder rung

WRITE-ONCE IS ENFORCED, NOT DOCUMENTED
--------------------------------------
:func:`build_panel` REFUSES to overwrite an existing version: it re-reads the manifest and
returns it unchanged.  A new version is a new file, always.  The write itself is atomic
(temp + ``os.replace``) so an interrupted build cannot leave a corrupt file that can never
be rewritten.  :func:`load_panel` verifies the parquet's sha256 against the manifest, so an
out-of-band edit fails loudly instead of quietly becoming the new evidence.

There is deliberately no "latest version" resolver.  An instrument that asks for the latest
is not pinned, and would drift again the moment a new version is minted — the exact defect
this module exists to close.  :func:`available_versions` lists; it does not choose.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

__all__ = [
    "PANEL_SUBDIR", "PanelVersionNotFound", "PanelCorrupt",
    "panel_path", "manifest_path", "available_versions",
    "build_panel", "load_panel", "load_manifest", "coverage_line",
]

#: ``data/research_panels/prices_v<VERSION>.parquet`` + ``..._manifest.json``.
PANEL_SUBDIR = "research_panels"

#: Frozen artifacts are read far more often than written and never rewritten, so pay the
#: slower codec once.  Measured on the 777x1540 build: zstd 6.10 MB vs snappy 8.71 MB.
_COMPRESSION = "zstd"

#: The ladder is #4698's, loaded from its canonical path rather than re-implemented.  This
#: is a RECEIPT recorded into every manifest, not a hard gate: pinning the value here would
#: make a legitimate later revision of the ladder crash every build.  The pin lives in
#: ``tests/test_research_price_panel.py``, which compares against the #4698 ref itself and
#: SKIPS rather than passes when that ref is absent.
_LADDER_REL = "research/prophet_us_audit/price_ladder.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_ladder():
    """Import #4698's price ladder from its canonical path.

    Loaded by path rather than by ``import`` because ``research/`` is not a package and the
    ladder lives beside the prophet_us_audit instruments that also use it — one copy, so
    the two consumers can never drift onto different ladders.
    """
    path = _repo_root() / _LADDER_REL
    if not path.exists():
        raise FileNotFoundError(
            f"price ladder missing at {_LADDER_REL} — the panel writer reuses #4698's "
            "ladder and must never re-implement it"
        )
    spec = importlib.util.spec_from_file_location("price_ladder", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("price_ladder", mod)     # dataclass pickling wants a real name
    spec.loader.exec_module(mod)
    return mod, _sha256(path)


class PanelVersionNotFound(FileNotFoundError):
    """Raised when a caller pins a version that does not exist.

    Deliberately fatal.  Falling back to the live stores — or to another version — would
    reintroduce exactly the drift this artifact exists to remove, and would do it silently.
    """


class PanelCorrupt(RuntimeError):
    """Raised when a version's bytes no longer match the sha256 its manifest recorded."""


def _store_dir(root: str | os.PathLike = "data") -> Path:
    return Path(root) / PANEL_SUBDIR


def _checked(version: str) -> str:
    """A version is a filename component, never a path.

    Versions reach this module from env vars and CLI args, so a separator would let a
    caller read or write outside the store — and the WRITE side is the one that matters:
    a build is the only thing here that creates files.
    """
    v = str(version)
    if not v or "/" in v or "\\" in v or v.startswith(".") or os.path.isabs(v):
        raise ValueError(
            f"invalid panel version {version!r}: a version is a plain name like "
            "'2026-08-06', not a path"
        )
    return v


def panel_path(version: str, root: str | os.PathLike = "data") -> Path:
    return _store_dir(root) / f"prices_v{_checked(version)}.parquet"


def manifest_path(version: str, root: str | os.PathLike = "data") -> Path:
    return _store_dir(root) / f"prices_v{_checked(version)}_manifest.json"


def available_versions(root: str | os.PathLike = "data") -> list[str]:
    """Every version with BOTH a parquet and a manifest, sorted.

    Lists; never chooses.  See the module docstring for why there is no ``latest()``.
    """
    store = _store_dir(root)
    if not store.is_dir():
        return []
    out = []
    for p in store.glob("prices_v*.parquet"):
        v = p.stem[len("prices_v"):]
        if manifest_path(v, root).exists():
            out.append(v)
    return sorted(out)


def _version_error(version: str, root: str | os.PathLike) -> PanelVersionNotFound:
    have = available_versions(root)
    return PanelVersionNotFound(
        f"research price panel version {version!r} not found under {_store_dir(root)}. "
        f"Available: {have if have else '(none)'}. "
        "This is fatal ON PURPOSE — a reader that fell back to the live stores would "
        "silently reintroduce the store drift the panel exists to remove."
    )


def build_panel(
    version: str,
    tickers,
    *,
    asof: str | pd.Timestamp,
    start: str | pd.Timestamp | None = None,
    benchmarks=(),
    root: str | os.PathLike = "data",
    data_dir: str | os.PathLike = "data",
    allow_unadjusted: bool = True,
) -> dict:
    """Materialize ``version`` and return its manifest.  NEVER overwrites.

    If ``version`` already exists, this reads its manifest back and returns it without
    touching the parquet — so re-running a build after the underlying stores have moved is
    a no-op, which is the whole point.  Mint a new version instead.

    ``benchmarks`` are resolved through the SAME ladder and stored in the SAME file, so an
    excess return computed from this panel has both legs on one basis.  They are tracked
    separately in the manifest, so a cross-sectional consumer can exclude them without
    guessing which columns are not names.
    """
    store = _store_dir(root)
    ppath, mpath = panel_path(version, root), manifest_path(version, root)
    if ppath.exists() and mpath.exists():
        with open(mpath) as fh:
            existing = json.load(fh)
        existing["_rebuild_was_a_noop"] = True
        return existing
    if ppath.exists() or mpath.exists():
        raise PanelCorrupt(
            f"version {version!r} is half-written ({'parquet' if ppath.exists() else 'manifest'} "
            "present, sibling missing). Remove BOTH by hand after recording why — an "
            "automatic repair here would be a mutation of a frozen artifact."
        )

    ladder, ladder_sha = _load_ladder()

    names = list(dict.fromkeys(str(t) for t in tickers))
    bench = [b for b in dict.fromkeys(str(b) for b in benchmarks) if b not in names]

    panel, prov = ladder.close_panel(
        names + bench, asof=asof, start=start, data_dir=str(data_dir),
        allow_unadjusted=allow_unadjusted,
    )
    if panel.empty:
        raise ValueError(
            f"panel for version {version!r} resolved zero names from {data_dir} — refusing "
            "to freeze an empty evidence base"
        )

    # Column order must not depend on the caller's ticker order: the artifact is the thing
    # under test, and two callers asking for the same universe in a different order must
    # not produce two different files.
    panel = panel.reindex(sorted(panel.columns), axis=1).sort_index()

    src = prov["price_source"]
    is_adj = ladder.is_adjusted
    covered = sorted(t for t in names if is_adj(src.get(t)) is True)
    unadj = sorted(t for t in names if is_adj(src.get(t)) is False)
    unresolved = sorted(t for t in names if src.get(t) is None)

    store.mkdir(parents=True, exist_ok=True)
    # Atomic, so an interrupted build cannot leave a half-written version that write-once
    # would then refuse to ever replace. A failed write takes its temp with it.
    tmp = ppath.with_suffix(".parquet.tmp")
    try:
        panel.to_parquet(tmp, compression=_COMPRESSION)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, ppath)

    manifest = {
        "version": version,
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asof": str(asof),
        "start": str(start) if start is not None else None,
        "panel_file": ppath.name,
        "sha256": _sha256(ppath),
        "rows": int(panel.shape[0]),
        "columns": int(panel.shape[1]),
        "cells_non_null": int(panel.notna().to_numpy().sum()),
        "panel_range": [str(panel.index.min().date()), str(panel.index.max().date())],
        # --- the coverage receipt an instrument prints beside its n --------------------
        "n_requested": len(names),
        "n_covered": len(covered),
        "coverage_pct": round(100.0 * len(covered) / len(names), 1) if names else 0.0,
        "covered": covered,
        "uncovered": {
            # In the panel, but priced from the raw cache: usable, NOT on the adjusted
            # basis, and the source of the distribution-shaped bias #4698 measured.
            "unadjusted_basis": unadj,
            # Not in the panel at all — no column exists for these names.
            "unresolved": unresolved,
        },
        "n_uncovered": len(unadj) + len(unresolved),
        "price_source": {t: src.get(t) for t in names},
        "resolved_from": prov["resolved_from"],
        "benchmarks": bench,
        "benchmark_price_source": {b: src.get(b) for b in bench},
        "ladder": prov["ladder"],
        "adjusted_sources": prov["adjusted_sources"],
        "unadjusted_sources": prov["unadjusted_sources"],
        "allow_unadjusted": bool(allow_unadjusted),
        "price_ladder_source": _LADDER_REL,
        "price_ladder_sha256": ladder_sha,
        "contract": (
            "WRITE-ONCE. This file and its parquet are never mutated; a new evidence base "
            "is a new version. Pin a version explicitly — there is no 'latest'. The panel "
            "freezes PRICES only: an instrument still pins its own calendar and "
            "observed-cell mask (#4698 trap 1, coverage masquerading as basis)."
        ),
    }
    tmpm = mpath.with_suffix(".json.tmp")
    with open(tmpm, "w") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(tmpm, mpath)
    return manifest


def load_manifest(version: str, root: str | os.PathLike = "data") -> dict:
    """The manifest for ``version``, or :class:`PanelVersionNotFound`."""
    mpath = manifest_path(version, root)
    if not mpath.exists():
        raise _version_error(version, root)
    with open(mpath) as fh:
        return json.load(fh)


def load_panel(
    version: str,
    *,
    root: str | os.PathLike = "data",
    columns=None,
    verify_sha256: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Read a pinned version.  Touches NOTHING but ``data/research_panels/``.

    ``version`` is required and unknown versions raise — this function has no path back to
    the live price stores, structurally, so it cannot reintroduce the drift.

    ``verify_sha256`` re-hashes the parquet against the manifest and raises
    :class:`PanelCorrupt` on a mismatch.  Leave it on: it is what makes "frozen" a checked
    property rather than a promise.  ~15 ms on the 6 MB build.
    """
    manifest = load_manifest(version, root)
    ppath = panel_path(version, root)
    if not ppath.exists():
        raise _version_error(version, root)
    if verify_sha256:
        got = _sha256(ppath)
        if got != manifest.get("sha256"):
            raise PanelCorrupt(
                f"{ppath} sha256 {got} != manifest {manifest.get('sha256')}. A frozen panel "
                "was edited in place. Do not 'repair' it — mint a new version and record why."
            )
    px = pd.read_parquet(ppath, columns=list(columns) if columns is not None else None)
    px.index = pd.to_datetime(px.index)
    return px.sort_index(), manifest


def coverage_line(manifest: dict, n: int | None = None) -> str:
    """One-line coverage receipt for an instrument's own results block.

    The audit's finding was not that 266 names lack an adjusted source — it was that a
    result could sit on an 82% sub-universe without SAYING so.  This is the saying-so.
    """
    u = manifest["uncovered"]
    head = f"n={n} over " if n is not None else ""
    return (
        f"{head}{manifest['n_covered']}/{manifest['n_requested']} adjusted-basis names "
        f"({manifest['coverage_pct']}%); {len(u['unadjusted_basis'])} on the unadjusted "
        f"cache, {len(u['unresolved'])} unresolved; panel v{manifest['version']} "
        f"asof {manifest['asof']}"
    )


def _cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Mint a frozen research price panel version.")
    ap.add_argument("version", help="version tag, e.g. 2026-08-06 (a NEW file, always)")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--start", default=None)
    ap.add_argument("--benchmarks", default="SPY",
                    help="comma-separated, resolved on the same ladder (default: SPY)")
    ap.add_argument("--root", default="data")
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args(argv)

    # The universe is the union of the three breadth caches' columns: that is the
    # population the instruments this panel serves actually measure.  Names are taken from
    # the caches; their PRICES are not.
    names: list[str] = []
    for g in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = Path(a.data_dir) / g / "_closes_cache.parquet"
        if p.exists():
            names += [str(c) for c in pd.read_parquet(p).columns]

    m = build_panel(a.version, names, asof=a.asof, start=a.start,
                    benchmarks=[b for b in a.benchmarks.split(",") if b],
                    root=a.root, data_dir=a.data_dir)
    if m.get("_rebuild_was_a_noop"):
        print(f"version {a.version} already exists — NOT rewritten (write-once).")
    print(json.dumps({k: v for k, v in m.items()
                      if k not in ("covered", "price_source", "uncovered")}, indent=1))
    print(coverage_line(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
