"""International signal-bridge — Layer-2 stateless registry reader.

This module is the ONLY door from international data into position-sizing and
de-risk logic. Consumers call ``features()`` and must never bypass the ``weight``
field returned for each feature. A weight of zero means "do not act on this
feature" — stale data, unvalidated verdict, killed leg, or a directional add-tilt
edge case all land at weight 0.

Architecture (§4.1 of research/INTL_FIX_MASTERPLAN.md):

  Layer 1 — ``data/intl_bridge/ledger.json`` is emitted by
             ``scripts/intl_phase0.py`` after the validation harness runs.
             It is the machine-readable truth about what has been proved.

  Layer 2 (THIS FILE) — a stateless, consume-time reader that enforces the
             three-state weight policy and the de-risk-dominates arbitration
             rule on every call.  No state is mutated; no service is started.

Weight policy (§4.1 — encoded exactly):
  - ``kill=True``                                      → weight = 0
  - ``verdict in (CONTEXT, INVERTED, PENDING)``        → weight = 0
  - any ``source_series`` on-disk last-date exceeds
    ``freshness_sla_days`` (or series is missing)      → weight = 0, stale=True
  - ``verdict == DIRECTIONAL``                         → weight = weight_cap / 2
    MUST carry ``direction == "de-risk"``.  A DIRECTIONAL add-tilt is a ledger
    bug: surface it as weight 0 + a warning note so it is never silently
    promoted.
  - ``verdict == CONFIRMED``                           → weight = weight_cap

Conflict arbitration (``arbitrate()``):
  De-risk legs strictly dominate add-tilt legs.  If ANY de-risk feature with
  weight > 0 is currently firing, every add-tilt feature's effective weight is
  forced to zero.  This resolves "dollar says de-risk, semi sensor says add-tilt"
  by construction, consistent with the finding that every validated intl edge is
  drawdown-side.

Leaf purity contract:
  This module imports NOTHING from engine.stock_score, engine.conditions,
  engine.playbook, or any other scoring-core module.  Only stdlib + pandas +
  lib.store + lib.config are permitted.  This is enforced by the manifest test
  ``tests/test_manifest_seams.py``.

Fail-soft contract:
  No public function ever raises.  A malformed or absent ledger returns {} with
  a log warning.  Individual stale/missing series are handled per-feature without
  aborting the rest.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Verdict strings that force weight to zero regardless of other fields.
_ZERO_WEIGHT_VERDICTS = frozenset({"CONTEXT", "INVERTED", "PENDING"})

# Relative path from the repo root to the ledger file.
_LEDGER_REL = Path("data") / "intl_bridge" / "ledger.json"


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _repo_root(root: str | Path | None) -> Path:
    """Resolve the repo root.  ``root=None`` → climb from this file's location."""
    if root is not None:
        return Path(root)
    # engine/intl_feed.py → parent is engine/ → parent is repo root
    return Path(__file__).resolve().parent.parent


def _load_ledger(root: Path) -> list[dict] | None:
    """Return the features list from ledger.json, or None on any error."""
    p = root / _LEDGER_REL
    if not p.exists():
        log.warning("intl_feed: ledger not found at %s; returning empty feature set", p)
        return None
    try:
        raw = json.loads(p.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("intl_feed: ledger parse error (%s); returning empty feature set", exc)
        return None
    if not isinstance(raw, dict):
        log.warning("intl_feed: ledger root is not a dict; returning empty feature set")
        return None
    feats = raw.get("features")
    if not isinstance(feats, list):
        log.warning("intl_feed: ledger missing 'features' list; returning empty feature set")
        return None
    return feats


def _series_age(group: str, name: str, root: Path) -> int | None:
    """Days since the last observation in data/<group>/<name>.parquet.

    Resolves the parquet path as  root / "data" / group / "<safe_name>.parquet"
    using the same name-sanitisation as lib.store._path, so tests that point at
    a fixture root get the right file without going through lib.config (which is
    hardwired to the real repo root).

    Returns None if the file does not exist or cannot be read (treated as stale).
    """
    try:
        safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
        p = root / "data" / group / f"{safe}.parquet"
        if not p.exists():
            return None
        import pandas as pd  # noqa: PLC0415 — stdlib-only import at module level would add numpy dep
        df = pd.read_parquet(p)
        if df.empty:
            return None
        idx = pd.to_datetime(df.index)
        last: date = idx.max().date()
        return (date.today() - last).days
    except Exception as exc:  # noqa: BLE001
        log.debug("intl_feed: series_age(%s/%s) read failed (%s)", group, name, exc)
        return None


def _parse_source_series(raw: list[str]) -> list[tuple[str, str]]:
    """Split 'group/series' strings into (group, name) tuples.
    Entries that don't match 'group/series' format are skipped with a warning.
    """
    out: list[tuple[str, str]] = []
    for entry in raw:
        if "/" not in entry:
            log.warning("intl_feed: malformed source_series entry %r (expected group/name)", entry)
            continue
        group, _, name = entry.partition("/")
        out.append((group.strip(), name.strip()))
    return out


def _feature_state(feat: dict, root: Path) -> dict[str, Any]:
    """Compute the resolved feature state dict for one ledger entry."""
    fid = str(feat.get("id", ""))
    channel = str(feat.get("channel", ""))
    direction = str(feat.get("direction", ""))
    verdict = str(feat.get("verdict", "PENDING"))
    weight_cap = float(feat.get("weight_cap", 0.0))
    validation_ref = str(feat.get("validation_ref", ""))
    notes = str(feat.get("notes", ""))
    sla_days = int(feat.get("freshness_sla_days", 7))
    source_series: list[str] = feat.get("source_series") or []
    kill = bool(feat.get("kill", False))

    # ---- staleness check ------------------------------------------------
    stale = False
    data_age_days: int | None = None
    pairs = _parse_source_series(source_series)
    for group, name in pairs:
        age = _series_age(group, name, root)
        if age is None:
            # series missing → stale
            stale = True
            log.debug("intl_feed: feature %s: source %s/%s missing → stale", fid, group, name)
            break
        if data_age_days is None or age > data_age_days:
            data_age_days = age
        if age > sla_days:
            stale = True
            log.debug(
                "intl_feed: feature %s: source %s/%s age %dd > SLA %dd → stale",
                fid, group, name, age, sla_days,
            )
            break

    # ---- weight policy --------------------------------------------------
    effective_notes = notes
    if kill:
        weight = 0.0
        log.debug("intl_feed: feature %s weight=0 (kill=True)", fid)
    elif verdict in _ZERO_WEIGHT_VERDICTS:
        weight = 0.0
    elif stale:
        weight = 0.0
    elif verdict == "DIRECTIONAL":
        if direction != "de-risk":
            # Ledger bug: DIRECTIONAL must be de-risk-only.
            weight = 0.0
            warning = (
                f"[intl_feed WARNING] feature '{fid}': DIRECTIONAL verdict with "
                f"direction='{direction}' is a ledger bug — only de-risk legs may be "
                "DIRECTIONAL. Weight forced to 0 until the ledger is corrected."
            )
            log.warning(warning)
            effective_notes = (effective_notes + " " + warning).strip()
        else:
            weight = weight_cap / 2.0
    elif verdict == "CONFIRMED":
        weight = weight_cap
    else:
        # Unknown verdict string → safe default
        weight = 0.0
        log.warning("intl_feed: feature %s has unknown verdict %r → weight=0", fid, verdict)

    return {
        "id": fid,
        "channel": channel,
        "direction": direction,
        "verdict": verdict,
        "weight": round(weight, 6),
        "weight_cap": round(weight_cap, 6),
        "stale": stale,
        "data_age_days": data_age_days,
        "validation_ref": validation_ref,
        "notes": effective_notes,
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def features(root: str | Path | None = None) -> dict[str, dict]:
    """Return the resolved feature-state map from the intl bridge ledger.

    Parameters
    ----------
    root:
        Repo root path.  Defaults to the directory two levels above this file.
        Pass an explicit path in tests to point at a fixture directory.

    Returns
    -------
    dict mapping feature id → feature state dict with keys:
        id, channel, direction, verdict, weight, weight_cap,
        stale, data_age_days, validation_ref, notes.

    Weight enforcement (the whole point — never bypass this field):
        weight = 0  if  kill=True
                    OR  verdict in {CONTEXT, INVERTED, PENDING}
                    OR  stale (any source_series missing or beyond freshness_sla_days)
                    OR  DIRECTIONAL with direction != 'de-risk' (ledger bug)
        weight = weight_cap / 2  if  DIRECTIONAL + de-risk
        weight = weight_cap      if  CONFIRMED

    Never raises.  Returns {} on any ledger error.
    """
    rp = _repo_root(root)
    raw_feats = _load_ledger(rp)
    if raw_feats is None:
        return {}

    out: dict[str, dict] = {}
    for feat in raw_feats:
        if not isinstance(feat, dict):
            log.warning("intl_feed: skipping non-dict feature entry: %r", feat)
            continue
        try:
            state = _feature_state(feat, rp)
            fid = state["id"]
            if not fid:
                log.warning("intl_feed: skipping feature with empty id")
                continue
            out[fid] = state
        except Exception as exc:  # noqa: BLE001
            log.warning("intl_feed: error resolving feature %r (%s); skipping", feat, exc)
    return out


def arbitrate(states: dict[str, dict], *, firing: set[str] | None = None) -> dict:
    """Apply the de-risk-dominates conflict rule to a feature state map.

    Parameters
    ----------
    states:
        Feature state dict as returned by ``features()``.
    firing:
        Set of feature ids that are currently signaling (i.e. the upstream
        data says the feature's condition is active).  Defaults to the empty
        set (no features firing) so this function can be unit-tested without
        live data.

    Returns
    -------
    dict with keys:
        derisk_active (bool):
            True if at least one de-risk feature with weight > 0 is in
            ``firing``.
        suppressed_add_tilts (list[str]):
            Feature ids of add-tilt features whose effective weight is zeroed
            because ``derisk_active`` is True.

    Rule:
        If ANY de-risk feature with weight > 0 is firing, every add-tilt
        feature's effective weight is zero for that book.  This is a PURE
        function — it does not mutate ``states``.  Live firing values are
        produced by W2 consumer work; this function encodes the rule and is
        unit-tested here.
    """
    if firing is None:
        firing = set()

    derisk_active = any(
        s["direction"] == "de-risk" and s["weight"] > 0 and fid in firing
        for fid, s in states.items()
    )

    suppressed: list[str] = []
    if derisk_active:
        suppressed = [
            fid
            for fid, s in states.items()
            if s["direction"] == "add-tilt" and s["weight"] > 0
        ]

    return {
        "derisk_active": derisk_active,
        "suppressed_add_tilts": suppressed,
    }
