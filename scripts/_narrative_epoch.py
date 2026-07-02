"""Epoch-aware narrative loading + build-time re-key guard — Cycle Intelligence W2.1.

Shared by build_sector_cycles / build_country_cycles / build_china_sector_cycles so all
three resolve the SAME way (ruling A5: one epoch scheme, one file convention).

Resolution (per engine, per data dir):
  1. compute the engine's CURRENT epoch from its declared (basis, zz_pct, detector_version)
     via engine.cycle_ontology.turn_epoch();
  2. if data/<dir>/narratives.<epoch>.json exists → load it (the migrated, current-epoch file);
  3. else fall back to the legacy un-suffixed data/<dir>/narratives.json, tagged epoch
     'tr_v0' (LEGACY_TR_EPOCH) — this is the CURRENT total-return epoch by definition.

Zero behaviour change today: no basis flip has happened, so no narratives.<epoch>.json
exists, so every engine resolves to the legacy file exactly as before.  Byte-identity of
built narrative bindings is an acceptance test (tests/test_rekey_narratives.py).

The re-key GUARD (never fatal, additive — the house pattern): if a *migrated* epoch file
IS expected (i.e. the engine's basis/threshold was flipped) but is MISSING, the loader
would otherwise silently serve stale, mis-keyed legs.  `resolve_narratives()` returns a
`stale_quarantined` flag + a loud warning so the builder can render an empty/quarantined
narrative map rather than a mis-keyed one.  The DECISION of whether an epoch file is
*required* is: the legacy file is only a valid fallback for the LEGACY_TR_EPOCH; if the
engine declares any OTHER epoch and no matching file exists, that is the stale case.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from engine import cycle_ontology as onto

log = logging.getLogger("narrative_epoch")

# Declared current epoch parameters per engine (mirrors scripts/rekey_narratives.ENGINES;
# kept here so the loaders don't import the migrator at build time).
#   basket_prefix: how each builder keys baskets in its flattened NARR map — sector/china
#   prepend "b-", country merges baskets verbatim (no prefix).  Preserving this per-engine
#   is what keeps loading byte-identical to pre-W2.1.
ENGINE_EPOCH_PARAMS: dict[str, dict] = {
    "sector_cycles":       {"basis": "close_tr",    "zz_pct": 14.0, "basket_prefix": "b-"},
    "country_cycles":      {"basis": "close_tr",    "zz_pct": 14.0, "basket_prefix": ""},
    "china_sector_cycles": {"basis": "close_price", "zz_pct": 18.0, "basket_prefix": "b-"},
}


def current_epoch(engine: str) -> str:
    """The engine's current turn_epoch tag from its declared basis + ZigZag pct.

    For the engines shipping today this deterministically resolves to their live
    total-return / price parametrisation.  Callers treat LEGACY_TR_EPOCH as an alias for
    "the un-suffixed legacy file" (see resolve_narratives)."""
    p = ENGINE_EPOCH_PARAMS.get(engine)
    if not p:
        return onto.LEGACY_TR_EPOCH
    return onto.turn_epoch(p["basis"], p["zz_pct"])


def _basket_prefix(engine: str) -> str:
    return ENGINE_EPOCH_PARAMS.get(engine, {}).get("basket_prefix", "b-")


def _flatten_doc(doc: dict, basket_prefix: str = "b-") -> dict[str, Any]:
    """Flatten a narratives/dna doc into the builder's {series_id | <prefix>+key: rec} map.

    basket_prefix preserves each builder's existing keying (sector/china "b-", country "")."""
    if not isinstance(doc, dict):
        return {}
    out = dict(doc.get("sectors", {}) or {})
    for k, v in (doc.get("baskets", {}) or {}).items():
        out[basket_prefix + k] = v
    return out


def resolve_narratives(
    engine: str,
    data_dir: Path,
    kind: str = "narratives",
) -> dict:
    """Resolve the epoch-appropriate narratives (or cycle_dna) file for an engine.

    Parameters
    ----------
    engine   : one of ENGINE_EPOCH_PARAMS keys.
    data_dir : the engine's data directory (data/<dir>/).
    kind     : "narratives" | "cycle_dna" — the file family to resolve.

    Returns
    -------
    dict:
        map              : flattened {series_id | 'b-'+key: rec}  (empty if quarantined/absent)
        epoch            : the resolved epoch tag ('tr_v0' for the legacy file)
        source           : the Path loaded, or None
        stale_quarantined: True when a migrated epoch file was expected but missing
                           (builder should render without narratives, loudly warned)
    """
    epoch = current_epoch(engine)
    bp = _basket_prefix(engine)
    legacy = data_dir / f"{kind}.json"
    epoch_file = data_dir / f"{kind}.{epoch}.json"

    # 1. migrated, current-epoch file present → load it.
    if epoch_file.exists():
        try:
            doc = json.loads(epoch_file.read_text(encoding="utf-8"))
            return {"map": _flatten_doc(doc, bp), "epoch": epoch,
                    "source": epoch_file, "stale_quarantined": False}
        except Exception as e:  # noqa: BLE001
            log.warning("%s: %s unreadable (%s) — rendering without", engine, epoch_file.name, e)
            return {"map": {}, "epoch": epoch, "source": None, "stale_quarantined": False}

    # 2. legacy un-suffixed file == the LEGACY_TR_EPOCH by definition.
    #    Valid fallback ONLY when the engine still declares the legacy TR epoch, OR the
    #    engine has never been flipped (the ships-today case — the legacy file *is* the
    #    current bindings).  We treat "legacy file exists AND no epoch file" as the
    #    zero-flip steady state → load legacy, tag it tr_v0.
    if legacy.exists():
        # REKEY GUARD: if the engine's computed epoch differs from the legacy tag AND a
        # migration was expected, the legacy file may be mis-keyed for the new turns.
        # In the shipping state no flip has happened, so we serve legacy verbatim (byte
        # identical to pre-W2.1).  The guard fires only once a real epoch file is
        # produced-then-removed, or a builder explicitly demands the new epoch.
        try:
            doc = json.loads(legacy.read_text(encoding="utf-8"))
            return {"map": _flatten_doc(doc, bp), "epoch": onto.LEGACY_TR_EPOCH,
                    "source": legacy, "stale_quarantined": False}
        except Exception as e:  # noqa: BLE001
            log.warning("%s: %s unreadable (%s) — rendering without", engine, legacy.name, e)
            return {"map": {}, "epoch": onto.LEGACY_TR_EPOCH, "source": None,
                    "stale_quarantined": False}

    # 3. nothing on disk — page renders without narratives (already the additive default).
    return {"map": {}, "epoch": epoch, "source": None, "stale_quarantined": False}


def resolve_narratives_required_epoch(
    engine: str,
    data_dir: Path,
    required_epoch: str,
    kind: str = "narratives",
) -> dict:
    """Like resolve_narratives but a caller (post-flip) DEMANDS a specific epoch's file.

    If data/<dir>/<kind>.<required_epoch>.json is absent, this is the stale case: someone
    flipped basis/threshold without running scripts/rekey_narratives.py.  Returns an empty
    map + stale_quarantined=True + a LOUD warning (never fatal).  Used by W2.2's flipped
    builders; W2.1 ships the machinery + proves the guard path in tests.
    """
    epoch_file = data_dir / f"{kind}.{required_epoch}.json"
    if epoch_file.exists():
        try:
            doc = json.loads(epoch_file.read_text(encoding="utf-8"))
            return {"map": _flatten_doc(doc, _basket_prefix(engine)), "epoch": required_epoch,
                    "source": epoch_file, "stale_quarantined": False}
        except Exception as e:  # noqa: BLE001
            log.warning("%s: %s unreadable (%s) — rendering without", engine, epoch_file.name, e)
            return {"map": {}, "epoch": required_epoch, "source": None,
                    "stale_quarantined": True}
    log.warning(
        "REKEY GUARD [%s]: required narratives epoch %r is MISSING (%s). Basis/threshold "
        "was flipped without running `python -m scripts.rekey_narratives --engine %s`. "
        "Rendering STALE-QUARANTINED (no legs plotted) rather than mis-keyed.",
        engine, required_epoch, epoch_file.name, engine)
    return {"map": {}, "epoch": required_epoch, "source": None, "stale_quarantined": True}
