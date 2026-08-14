"""engine/entry_radar/producers/boards.py — the nightly single-name boards.

Three readers over the nightly stock-library build (Track C rows #22/#23):

  ``read_us_standouts``   ``site/factordata/us_standouts.json``   MKT   nominations
  ``read_setups``         ``site/factordata/setups.json``         MKT   nominations
  ``read_stock_library``  ``site/stockdata/<T>.json``             MKT   FEATURES ONLY

ARTIFACT SHAPES (verified from writer code this session, not from bytes — the
worktree is sparse):

  ``us_standouts.json`` is a **dict**, not a list: root ``as_of`` plus the lane
  lists ``buy`` / ``watch`` / ``leaders`` / ``laggards``
  (``scripts/build_stock_library.py``, write at :6022).  ``setups.json`` is
  ``{as_of, buy, laggards}`` (``engine/setups.py::rank_setups``, :293).
  Both carry the same ``setup_score()`` row: ``ticker, name, sector, alpha,
  alpha_entry, state, label, urgency, dir, eq_dir, sector_rank, sector_n,
  setup`` (``engine/setups.py``:100-106); ``us_standouts``'s ``buy`` rows
  additionally carry ``score_rank`` / ``display_rank`` / ``stage``
  (``engine/us_board_rank.py``:1092-1161).

  NOTE — the PR-0 census's ``eq_score`` / ``alpha_z`` are NOT keys on these
  rows; they belong to a different, ``action_board.json``-bound structure.  The
  real numbers are ``alpha`` / ``alpha_entry``, and this adapter reads those.

CORRELATED FAMILY — DISCLOSED, NOT HIDDEN
------------------------------------------
Both boards are cut from ONE upstream (``engine/setups.py::rank_setups``) in
ONE nightly build, so they share the ``factordata:`` source-id prefix and the
bus discloses them as a single correlated family.  Two badges off one upstream
are not two confirmations (Track C §1.3).  ``stockdata:master`` rides the same
nightly build; it emits no nominations, so it cannot double-count either.

WHAT THIS MODULE DOES *NOT* DO
-------------------------------
It reads these boards' ARTIFACTS; it never imports ``engine/setups.py``,
``engine/entry_signal.py`` or ``scripts/build_stock_library.py``
(contract §16 non-interference).  And it never promotes their numbers:
``alpha`` / ``score_rank`` / ``urgency`` ride along as
``source_value`` / ``source_rank`` — the PRODUCER's own figures, preserved
verbatim as provenance — and are forbidden from entering any Radar score (§9).
Board membership buys a name a look; it does not buy it a point.

The ``us_standouts`` buy rows also carry a ``prophet`` block (score,
components, points).  It is DELIBERATELY NOT READ.  Ingesting it would make
Radar a Prophet consumer through the artifact door, which is precisely the
coupling §1 exists to prevent.

WHY THE STOCK LIBRARY EMITS NO NOMINATIONS
-------------------------------------------
``site/stockdata/<T>.json`` is the per-ticker master record, and its
single-name content is *other organs' verdicts* — ``entry_signal``,
``conviction.potential`` (name_score), ``washout_turn``, ``personality``.
Minting Radar nominations off those would launder another organ's opinion into
Radar's funnel wearing Radar's provenance.  So this reader is a **feature
provider**: Layer-A names, Layer-B liquidity, Layer-C attention, and
``history_days`` for the IPO/young cohort.  Names still reach the Probe Set —
through Layers A/B/C, on facts Radar measured itself.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import ProducerRead, utcnow
from engine.entry_radar.producers.base import (
    AdapterResult,
    artifact_asof,
    build_read,
    first_key,
    grade_staleness,
    read_json,
    row_ticker,
    stale_after,
    unavailable,
)

log = logging.getLogger(__name__)

STANDOUTS_SOURCE_ID = "factordata:us_standouts"
SETUPS_SOURCE_ID = "factordata:setups"
STOCK_LIBRARY_SOURCE_ID = "stockdata:master"

#: ``(lane key, reason suffix, human label)`` — the board's own lanes, kept
#: DISTINCT.  A "watch" row and a "buy" row are different facts about coverage
#: and collapsing them would be a flattening (contract §16 A1.2).
_STANDOUT_LANES: tuple[tuple[str, str, str], ...] = (
    ("buy", "buy", "buy lane"),
    ("watch", "watch", "watch lane"),
    ("leaders", "leader", "leaders lane"),
    ("laggards", "laggard", "laggards lane"),
)
_SETUP_LANES: tuple[tuple[str, str, str], ...] = (
    ("buy", "buy", "buy lane"),
    ("laggards", "laggard", "laggards lane"),
)

_RANK_KEYS = ("score_rank", "display_rank", "rank")
#: ``alpha`` / ``alpha_entry`` are the real row numbers (engine/setups.py:100-106).
_VALUE_KEYS = ("alpha", "alpha_entry")


def _ttl(cfg: Mapping[str, Any] | None, source_id: str) -> float:
    """Nomination TTL = the artifact's own staleness budget: a nightly board's
    nomination must not outlive the next nightly build."""
    return stale_after(cfg, source_id)


def _board_read(path: Path, *, source_id: str, board_label: str,
                lanes: Sequence[tuple[str, str, str]], now: datetime | None,
                cfg: Mapping[str, Any] | None) -> ProducerRead:
    stamp = now or utcnow()
    payload, reason = read_json(path)

    def emit(doc: Any, ctx: Mapping[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(doc, Mapping):
            return out
        for lane_key, suffix, lane_label in lanes:
            block = doc.get(lane_key)
            rows = [r for r in (block or ()) if isinstance(r, Mapping)]
            for pos, row in enumerate(rows, start=1):
                sym = row_ticker(row)
                if not sym:
                    continue
                rank = first_key(row, _RANK_KEYS)
                try:
                    rank = int(rank) if rank is not None else pos
                except (TypeError, ValueError):
                    rank = pos
                value = first_key(row, _VALUE_KEYS)
                try:
                    value = float(value) if value is not None else None
                except (TypeError, ValueError):
                    value = None
                text = f"On the nightly {board_label} {lane_label} at #{rank}"
                label = row.get("label") or row.get("state")
                if label:
                    text += f" ({label})"
                out.append({
                    "ticker": sym, "source_id": ctx["source_id"],
                    "source_family": "market_price",
                    "reason_code": f"board.{suffix}",
                    "reason_text": text,
                    "observed_at": ctx["observed_at"], "source_asof": ctx["source_asof"],
                    "source_rank": rank, "source_value": value,
                    "source_horizon": "nightly", "ttl_until": ctx["ttl_until"],
                    "evidence_ref": f"{path.name}#{lane_key}/{sym}",
                    "data_quality": ctx["data_quality"],
                })
        return out

    return build_read(source_id, payload=payload, reason=reason, path=path, now=stamp,
                      cfg=cfg, emit=emit, ttl_minutes=_ttl(cfg, source_id))


def read_us_standouts(path: Path, *, now: datetime | None = None,
                      cfg: Mapping[str, Any] | None = None) -> ProducerRead:
    """``site/factordata/us_standouts.json`` — the macro-page standout board.

    CAP=60, |score| floor, per-sector cap 5 (Track C row #22): an absent name is
    a BOARD-CUT fact, not market silence.  The adapter therefore says nothing
    at all about names it does not see — it never emits a negative.
    """
    return _board_read(path, source_id=STANDOUTS_SOURCE_ID, board_label="US standouts",
                       lanes=_STANDOUT_LANES, now=now, cfg=cfg)


def read_setups(path: Path, *, now: datetime | None = None,
                cfg: Mapping[str, Any] | None = None) -> ProducerRead:
    """``site/factordata/setups.json`` — the setups board (same upstream as above)."""
    return _board_read(path, source_id=SETUPS_SOURCE_ID, board_label="setups",
                       lanes=_SETUP_LANES, now=now, cfg=cfg)


# ---------------------------------------------------------------------------
# stock library master record — FEATURES ONLY (see module docstring)
# ---------------------------------------------------------------------------

#: ``(artifact keys, Radar feature key)``.  Primary names verified against
#: ``engine/stock_technicals.py::snapshot()``: ``dollar_vol_20d`` (:349),
#: ``rel_volume`` (:348), ``atr_pct`` (:320), ``ret_1m``, ``history_days``.
#: Alternates are tolerated because the snapshot's naming has drifted across
#: builder generations and a hard key-miss would silently zero a whole layer.
_FEATURE_KEYS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dollar_vol_20d", "dollar_volume_20d"), "dollar_vol_20d"),
    (("rel_volume", "relative_volume"), "rel_volume"),
    (("atr_pct", "realized_range_pct", "hv20"), "realized_range_pct"),
    (("ret_1m", "momentum_20d_pct", "chg_20d_pct"), "momentum_20d_abs_pct"),
    (("history_days", "history_age_sessions", "n_sessions"), "history_age_sessions"),
    (("dollar_vol_rank", "adv_rank"), "dollar_vol_rank"),
    # No gap producer exists in W1: engine/entry_primitives.py:651 gap_hold_events
    # is appendix-locked DORMANT and is deliberately NOT resurrected here
    # (Track C §3).  The `gap_abs_pct` knob in config/entry_radar.yml therefore
    # has no feeder yet — an honest empty lane, not a silent zero.
    (("gap_pct", "gap_abs_pct", "overnight_gap_pct"), "gap_abs_pct"),
)

#: Containers the technical snapshot has lived in.  ``tech`` is the live one
#: (``scripts/build_stock_library.py``:3483 merges ``stock_technicals.snapshot()``
#: into ``rec["tech"]``).
_SNAPSHOT_CONTAINERS: tuple[str, ...] = ("tech", "technicals", "snapshot", "metrics")


def _snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the record's technical snapshot plus its scalar top-level fields."""
    flat: dict[str, Any] = {k: v for k, v in record.items()
                            if not isinstance(v, (dict, list))}
    for container in _SNAPSHOT_CONTAINERS:
        block = record.get(container)
        if isinstance(block, Mapping):
            flat.update({k: v for k, v in block.items()
                         if not isinstance(v, (dict, list))})
    return flat


def read_stock_library(records: Mapping[str, Mapping[str, Any]] | None = None, *,
                       stockdata_dir: Path | None = None,
                       tickers: Sequence[str] | None = None,
                       now: datetime | None = None,
                       cfg: Mapping[str, Any] | None = None) -> AdapterResult:
    """Read the per-ticker master records → Layer A/B/C features (no nominations).

    ``records`` (ticker → record) short-circuits the filesystem, which is what
    tests use: this worktree is sparse, so a directory read would find nothing,
    and an adapter reporting "no names" from that would be lying about the
    market rather than about the host.

    When ``stockdata_dir`` is given, ``tickers`` bounds the read — walking
    ~2,966 files every pass is not a budget anyone signed up for.  Coverage is
    uneven by design (~2,966 stamped, ~1,595 with full dossiers — Track C §3),
    so a name missing a feature is recorded as missing, never as zero.
    """
    stamp = now or utcnow()
    source_id = STOCK_LIBRARY_SOURCE_ID
    docs: dict[str, Mapping[str, Any]] = {}

    if records is not None:
        docs = {str(k).strip().upper(): v for k, v in records.items()
                if isinstance(v, Mapping)}
    elif stockdata_dir is not None:
        if not stockdata_dir.is_dir():
            return AdapterResult(
                unavailable(source_id, f"{stockdata_dir} absent — stock library not "
                                       "readable on this host", now=stamp))
        wanted = [str(t).strip().upper() for t in (tickers or ())]
        paths = ([stockdata_dir / f"{t}.json" for t in wanted] if wanted
                 else sorted(stockdata_dir.glob("*.json")))
        for path in paths:
            doc, _ = read_json(path)
            if isinstance(doc, Mapping):
                docs[path.stem.strip().upper()] = doc
    else:
        return AdapterResult(
            unavailable(source_id, "neither records nor stockdata_dir supplied", now=stamp))

    if not docs:
        return AdapterResult(
            unavailable(source_id, "stock library yielded zero records — treated as an "
                                   "outage, not an empty universe", now=stamp))

    features: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}
    history_age: dict[str, int] = {}
    newest: datetime | None = None
    quality = "ok"

    for sym, doc in docs.items():
        asof, doc_quality = artifact_asof(doc, None)
        if asof is not None:
            newest = asof if newest is None else max(newest, asof)
        elif doc_quality != "ok":
            quality = "degraded"
        profile = doc.get("profile") if isinstance(doc.get("profile"), Mapping) else {}
        label = str(first_key({**dict(doc), **dict(profile)},
                              ("name", "company", "company_name", "long_name")) or "")
        if label:
            names[sym] = label
        flat = _snapshot(doc)
        row: dict[str, Any] = {}
        for keys, feat in _FEATURE_KEYS:
            val = first_key(flat, keys)
            if val is None:
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            row[feat] = abs(num) if feat.endswith("_abs_pct") else num
        try:
            if profile.get("mktcap_bn") is not None:
                row["mktcap_bn"] = float(profile["mktcap_bn"])
        except (TypeError, ValueError):
            pass
        if row:
            features[sym] = row
        if "history_age_sessions" in row:
            history_age[sym] = int(row["history_age_sessions"])

    status, age = grade_staleness(newest, now=stamp,
                                  stale_after_minutes=stale_after(cfg, source_id))
    read = ProducerRead(source_id=source_id, status=status, nominations=(),
                        source_asof=newest, observed_at=stamp, age_seconds=age,
                        stale_after_seconds=stale_after(cfg, source_id) * 60.0,
                        detail=f"{len(docs)} master record(s); {len(features)} with "
                               f"features; vintage={quality}; feature-provider only "
                               "(emits no nominations by design)")
    return AdapterResult(read, features=features, names=names,
                         history_age=history_age)
