"""engine.neuralweb.thematic_state — TIL W0 State Composition Organ.

Display-only, authority block is_context_only=True with all promotion flags False.
Mirrors engine/neuralweb/mechanism_pathways.py and engine/neuralweb/liquidity_plumbing.py
conventions: tolerant-read each input (missing/stale → honest null + stale_legs entry),
envelope.stamp(), atomic writes, exits 0 always.

Public API
----------
compose(root=None) -> dict
    Compose the theme_state artifact from existing downstream artifacts.
    Never raises. Returns a schema neuralweb.theme_state.v1 dict.

append_phase_history(root, artifact) -> int
    Append PIT rows to data/neuralweb/theme_phase_history.jsonl for themes
    whose tracked state changed, plus a weekly heartbeat for all themes.
    Returns number of rows written.

Schema: neuralweb.theme_state.v1
Output paths:
    data/neuralweb/theme_state.json       (primary; git-committed)
    site/neuralwebdata/theme_state.json   (site mirror)
    data/neuralweb/theme_phase_history.jsonl  (append-only PIT tape)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's engine-job
    env.  US_LANE is accepted as a legacy alias.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"

# ---------------------------------------------------------------------------
# Schema / authority constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.theme_state.v1"
HISTORY_SCHEMA = "neuralweb.theme_phase_history.v1"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "display",
    "forbidden_uses": [
        "ranking",
        "sizing",
        "alert_escalation",
        "board_ordering",
        "mastermind_arming",
        "scored_path",
    ],
}

_STALE_DAYS = 5   # calendar days before an input is flagged stale

# ---------------------------------------------------------------------------
# Source artifact paths (relative to repo root)
# ---------------------------------------------------------------------------

_CROSSWALK_PATH = "config/theme_crosswalk.yml"
_FORESIGHT_PATH = "site/basketdata/foresight_cascade.json"
_BASKETS_PATH = "site/basketdata/baskets.json"
_RADAR_PATH = "site/basketdata/radar.json"
_RADAR_ENRICHED_PATH = "site/basketdata/radar_enriched.json"
_NARRATIVE_PATH = "site/basketdata/narrative_emergence.json"
_SUBSECTOR_PATH = "site/marketdata/subsector_rotation.json"
_DIVERGENCE_LOG_PATH = "data/foresight/divergence_log.jsonl"

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

_DATA_OUT = "data/neuralweb/theme_state.json"
_SITE_OUT = "site/neuralwebdata/theme_state.json"
_HISTORY_OUT = "data/neuralweb/theme_phase_history.jsonl"

# ---------------------------------------------------------------------------
# Heartbeat cadence: write a row at least every N days even without state change
# ---------------------------------------------------------------------------
_HEARTBEAT_DAYS = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path, label: str) -> tuple[dict | None, str | None]:
    """Load JSON from path.  Returns (data, error_str).  error_str is None on success."""
    if not path.exists():
        return None, f"{label}: file not found at {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: parse error — {exc}"


def _load_yaml(path: Path, label: str) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, f"{label}: file not found at {path}"
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: parse error — {exc}"


def _parse_asof(val: Any) -> datetime | None:
    if val is None:
        return None
    try:
        s = str(val).strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _is_stale(asof_val: Any) -> bool:
    dt = _parse_asof(asof_val)
    if dt is None:
        return True
    age_days = (datetime.now(tz=timezone.utc) - dt).days
    return age_days >= _STALE_DAYS


def _asof_today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _row_hash(row: dict) -> str:
    """SHA-256 of canonical JSON of a history row (for hash-chaining)."""
    text = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------

def _read_foresight(root: Path) -> tuple[dict, list[str]]:
    """Read foresight_cascade.json.  Returns ({theme_id: theme_rec}, stale_legs)."""
    path = root / _FORESIGHT_PATH
    data, err = _load_json(path, "foresight_cascade")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"foresight_cascade: {err}"]
    asof = data.get("asof")
    if _is_stale(asof):
        stale.append(f"foresight_cascade: stale (as_of={asof})")
    themes_list = data.get("themes", [])
    by_id = {t["theme"]: t for t in themes_list if isinstance(t, dict) and "theme" in t}
    return by_id, stale


def _read_baskets(root: Path) -> tuple[dict, list[str]]:
    """Read baskets.json theme_intel.themes.  Returns ({basket_id: intel_rec}, stale_legs)."""
    path = root / _BASKETS_PATH
    data, err = _load_json(path, "baskets")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"baskets: {err}"]
    asof = data.get("as_of") or data.get("theme_intel", {}).get("as_of")
    if _is_stale(asof):
        stale.append(f"baskets: stale (as_of={asof})")
    ti_themes = (data.get("theme_intel") or {}).get("themes", [])
    by_id = {t["id"]: t for t in ti_themes if isinstance(t, dict) and "id" in t}
    return by_id, stale


def _read_radar_flags(root: Path) -> tuple[dict, list[str]]:
    """Read radar_enriched.json flags.  Returns ({basket_id: flag_rec}, stale_legs).

    flags[] carries lifecycle/divergence per basket.
    """
    path = root / _RADAR_ENRICHED_PATH
    data, err = _load_json(path, "radar_enriched")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"radar_enriched: {err}"]
    asof = data.get("as_of")
    if _is_stale(asof):
        stale.append(f"radar_enriched: stale (as_of={asof})")
    flags = data.get("flags", [])
    by_id: dict = {}
    for flag in flags:
        if isinstance(flag, dict):
            bid = flag.get("basket")
            if bid:
                by_id[bid] = flag
    return by_id, stale


def _read_radar_hypotheses(root: Path) -> tuple[dict, list[str]]:
    """Read radar.json hypotheses.  Returns ({basket_id: hyp_rec}, stale_legs)."""
    path = root / _RADAR_PATH
    data, err = _load_json(path, "radar")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"radar: {err}"]
    asof = data.get("as_of")
    if _is_stale(asof):
        stale.append(f"radar: stale (as_of={asof})")
    hyps = data.get("hypotheses", [])
    by_id: dict = {}
    for h in hyps:
        if isinstance(h, dict):
            bid = h.get("subject")
            if bid:
                by_id[bid] = h
    return by_id, stale


def _read_narrative_tickers(root: Path) -> tuple[dict, list[str]]:
    """Read narrative_emergence.json.  Returns ({ticker: True}, stale_legs) for active tickers.

    Used to link baskets by member overlap.
    """
    path = root / _NARRATIVE_PATH
    data, err = _load_json(path, "narrative_emergence")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"narrative_emergence: {err}"]
    asof = data.get("as_of")
    if _is_stale(asof):
        stale.append(f"narrative_emergence: stale (as_of={asof})")
    # Collect tickers that appear in any narrative leg
    active: dict = {}
    narratives = data.get("narratives", [])
    for n in narratives:
        if isinstance(n, dict):
            for leg in n.get("legs", []):
                if isinstance(leg, dict):
                    for t in leg.get("tickers", []):
                        active[t] = True
    return active, stale


def _read_subsector(root: Path) -> tuple[dict, list[str]]:
    """Read subsector_rotation.json.  Returns ({theme_name: quad_rollup}, stale_legs)."""
    path = root / _SUBSECTOR_PATH
    data, err = _load_json(path, "subsector_rotation")
    stale: list[str] = []
    if err or data is None:
        return {}, [f"subsector_rotation: {err}"]
    asof = data.get("asof")
    if _is_stale(asof):
        stale.append(f"subsector_rotation: stale (as_of={asof})")
    themes_list = data.get("themes", [])
    by_name: dict = {}
    for t in themes_list:
        if isinstance(t, dict) and "theme" in t:
            by_name[t["theme"]] = {
                "quadrant": t.get("quadrant"),
                "rs": t.get("rs"),
                "accel_z": t.get("z_accel"),
                "emerging_score": t.get("emerging_score"),
            }
    return by_name, stale


def _read_divergence_log(root: Path) -> tuple[dict, list[str]]:
    """Read divergence_log.jsonl.  Returns ({theme_id: latest_row}, stale_legs)."""
    path = root / _DIVERGENCE_LOG_PATH
    stale: list[str] = []
    if not path.exists():
        return {}, [f"divergence_log: file not found at {path}"]
    latest: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line.strip())
                theme = row.get("theme")
                asof = row.get("asof")
                if not theme or not asof:
                    continue
                existing = latest.get(theme)
                if existing is None or asof > existing.get("asof", ""):
                    latest[theme] = row
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        return {}, [f"divergence_log: read error — {exc}"]
    # Check freshness of latest rows
    for theme, row in latest.items():
        if _is_stale(row.get("asof")):
            stale.append(f"divergence_log[{theme}]: stale (as_of={row.get('asof')})")
    return latest, stale


# ---------------------------------------------------------------------------
# Per-theme composition
# ---------------------------------------------------------------------------

def _compose_theme(
    theme_cfg: dict,
    foresight_by_id: dict,
    baskets_by_id: dict,
    radar_flags: dict,
    radar_hyps: dict,
    narrative_tickers: dict,
    subsector_by_name: dict,
    divergence_log: dict,
    membership_by_basket: dict,
) -> dict:
    """Build a single theme block from all source artifacts (tolerant-read)."""
    tid = theme_cfg["id"]
    basket_ids: list[str] = theme_cfg.get("basket_ids", [])
    subsector_keys: list[str] = theme_cfg.get("subsector_keys", [])
    foresight_id = theme_cfg.get("foresight_id")

    # ── Foresight ─────────────────────────────────────────────────────────
    fc = foresight_by_id.get(foresight_id) if foresight_id else None
    foresight_block: dict | None = None
    if fc:
        foresight_block = {
            "stage": fc.get("stage"),
            "tier": fc.get("tier"),
            "score": fc.get("score"),
            "entry_ready": fc.get("entry_ready"),
            "bottleneck_band": fc.get("bottleneck_band"),
            "source": _FORESIGHT_PATH,
        }

    # ── Basket theme_intel (lifecycle/score/crowding) ─────────────────────
    basket_intel_blocks: list[dict] = []
    for bid in basket_ids:
        bi = baskets_by_id.get(bid)
        if bi:
            basket_intel_blocks.append({
                "basket_id": bid,
                "name_en": bi.get("name"),
                "name_zh": bi.get("name_zh"),
                "score": bi.get("score"),
                "label": bi.get("label"),
                "label_en": bi.get("label_en"),
                "label_zh": bi.get("label_zh"),
                "crowding": bi.get("components", {}).get("crowding"),
                "reco": bi.get("reco"),
                "source": _BASKETS_PATH,
            })

    # ── Radar divergence flags ─────────────────────────────────────────────
    radar_flag_blocks: list[dict] = []
    for bid in basket_ids:
        rf = radar_flags.get(bid)
        if rf:
            radar_flag_blocks.append({
                "basket_id": bid,
                "state": rf.get("state"),
                "lifecycle": rf.get("lifecycle"),
                "divergence": rf.get("divergence"),
                "salience": rf.get("salience"),
                "source": _RADAR_ENRICHED_PATH,
            })
        rh = radar_hyps.get(bid)
        if rh:
            radar_flag_blocks.append({
                "basket_id": bid,
                "lean": rh.get("lean"),
                "horizon_d": rh.get("horizon_d"),
                "check_by": rh.get("check_by"),
                "thesis_snippet": (rh.get("thesis") or "")[:120],
                "source": _RADAR_PATH,
            })

    # ── Narrative link (ticker overlap with basket members) ────────────────
    # Check if any basket member appears in the active narrative ticker set
    narrative_present = False
    for bid in basket_ids:
        members = membership_by_basket.get(bid, [])
        if any(m in narrative_tickers for m in members):
            narrative_present = True
            break
    narrative_block: dict | None = None
    if narrative_present:
        narrative_block = {
            "has_forming_narrative": True,
            "source": _NARRATIVE_PATH,
        }

    # ── Subsector RRG quadrant rollup ─────────────────────────────────────
    subsector_blocks: list[dict] = []
    for sk in subsector_keys:
        sr = subsector_by_name.get(sk)
        if sr:
            subsector_blocks.append({"key": sk, **sr})

    # Rollup: dominant quadrant (most common among subsector keys)
    rollup_quadrant: str | None = None
    if subsector_blocks:
        from collections import Counter
        quads = [b["quadrant"] for b in subsector_blocks if b.get("quadrant")]
        if quads:
            rollup_quadrant = Counter(quads).most_common(1)[0][0]

    # ── Divergence board (latest divergence_log row) ───────────────────────
    divlog = divergence_log.get(tid)
    divergence_block: dict | None = None
    if divlog:
        divergence_block = {
            "quadrant": divlog.get("quadrant"),
            "divergence": divlog.get("divergence"),
            "narrative_pct": divlog.get("narrative_pct"),
            "money_pct": divlog.get("money_pct"),
            "asof": divlog.get("asof"),
            "source": _DIVERGENCE_LOG_PATH,
        }

    return {
        "theme_id": tid,
        "name_en": theme_cfg["name_en"],
        "name_zh": theme_cfg["name_zh"],
        "foresight": foresight_block,
        "basket_intel": basket_intel_blocks or None,
        "radar": radar_flag_blocks or None,
        "narrative": narrative_block,
        "subsector_rotation": {
            "keys": subsector_keys,
            "rollup_quadrant": rollup_quadrant,
            "subsectors": subsector_blocks or None,
        },
        "divergence_board": divergence_block,
        "basket_ids": basket_ids,
        "subsector_keys": subsector_keys,
    }


# ---------------------------------------------------------------------------
# Main composition
# ---------------------------------------------------------------------------

def compose(root: Path | None = None) -> dict:
    """Compose the theme_state artifact.  Never raises; returns a valid dict."""
    if root is None:
        root = _repo_root()
    root = Path(root)

    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    as_of = _asof_today()
    all_stale_legs: list[str] = []

    # ── Load crosswalk ─────────────────────────────────────────────────────
    xwalk_data, xwalk_err = _load_yaml(root / _CROSSWALK_PATH, "theme_crosswalk")
    if xwalk_err or xwalk_data is None:
        log.error("theme_crosswalk load failed: %s", xwalk_err)
        # Return minimal valid artifact on fatal crosswalk failure
        return {
            "schema": SCHEMA,
            "as_of": as_of,
            "generated_at": now_str,
            "authority": AUTHORITY_BLOCK,
            "themes": [],
            "stale_legs": [f"theme_crosswalk: {xwalk_err}"],
            "error": "crosswalk unavailable — no theme blocks composed",
        }

    theme_cfgs = xwalk_data.get("themes", [])

    # ── Load all sources (tolerant — each returns ({}, stale_reasons) on error) ──
    foresight_by_id, sl1 = _read_foresight(root)
    all_stale_legs.extend(sl1)

    baskets_by_id, sl2 = _read_baskets(root)
    all_stale_legs.extend(sl2)

    radar_flags, sl3 = _read_radar_flags(root)
    all_stale_legs.extend(sl3)

    radar_hyps, sl4 = _read_radar_hypotheses(root)
    all_stale_legs.extend(sl4)

    narrative_tickers, sl5 = _read_narrative_tickers(root)
    all_stale_legs.extend(sl5)

    subsector_by_name, sl6 = _read_subsector(root)
    all_stale_legs.extend(sl6)

    divergence_log_data, sl7 = _read_divergence_log(root)
    all_stale_legs.extend(sl7)

    # ── Build basket membership lookup ────────────────────────────────────
    # Read from membership.json for ticker-level overlap with narrative_tickers
    membership_by_basket: dict = {}
    membership_path = root / "data/baskets/membership.json"
    try:
        if membership_path.exists():
            mbdata = json.loads(membership_path.read_text(encoding="utf-8"))
            for bid, bdata in mbdata.get("baskets", {}).items():
                membership_by_basket[bid] = bdata.get("tickers", []) if isinstance(bdata, dict) else []
    except Exception as exc:  # noqa: BLE001
        log.warning("membership.json read failed (non-fatal): %s", exc)

    # ── Compose per-theme ─────────────────────────────────────────────────
    theme_blocks: list[dict] = []
    for cfg in theme_cfgs:
        try:
            block = _compose_theme(
                theme_cfg=cfg,
                foresight_by_id=foresight_by_id,
                baskets_by_id=baskets_by_id,
                radar_flags=radar_flags,
                radar_hyps=radar_hyps,
                narrative_tickers=narrative_tickers,
                subsector_by_name=subsector_by_name,
                divergence_log=divergence_log_data,
                membership_by_basket=membership_by_basket,
            )
            theme_blocks.append(block)
        except Exception as exc:  # noqa: BLE001
            log.warning("theme %s compose failed (non-fatal): %s", cfg.get("id"), exc)
            all_stale_legs.append(f"theme[{cfg.get('id')}]: compose error — {exc}")

    artifact: dict = {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_at": now_str,
        "authority": AUTHORITY_BLOCK,
        "n_themes": len(theme_blocks),
        "themes": theme_blocks,
        "stale_legs": all_stale_legs,
        "sources": {
            "theme_crosswalk": _CROSSWALK_PATH,
            "foresight_cascade": _FORESIGHT_PATH,
            "baskets": _BASKETS_PATH,
            "radar": _RADAR_PATH,
            "radar_enriched": _RADAR_ENRICHED_PATH,
            "narrative_emergence": _NARRATIVE_PATH,
            "subsector_rotation": _SUBSECTOR_PATH,
            "divergence_log": _DIVERGENCE_LOG_PATH,
        },
    }

    return artifact


# ---------------------------------------------------------------------------
# PIT tape: phase history
# ---------------------------------------------------------------------------

def _extract_tracked_state(theme_block: dict) -> dict:
    """Extract the four tracked state fields for phase-history comparison."""
    fc = theme_block.get("foresight") or {}
    basket_intel = theme_block.get("basket_intel") or []
    bi0 = basket_intel[0] if basket_intel else {}
    divboard = theme_block.get("divergence_board") or {}
    radar = theme_block.get("radar") or []
    r0 = radar[0] if radar else {}

    return {
        "foresight_stage": fc.get("stage"),
        "scoring_lifecycle": bi0.get("label") if bi0 else None,
        "radar_lifecycle": r0.get("lifecycle") if r0 else None,
        "divergence_quadrant": divboard.get("quadrant"),
    }


def append_phase_history(root: Path, artifact: dict) -> int:
    """Append PIT rows to theme_phase_history.jsonl.

    Rules:
      - One row per (theme_id, as_of) — hard dedup for idempotency.
      - Log on state transition (any of the four tracked fields changes vs last row).
      - Weekly heartbeat: log even without transition if last row >= _HEARTBEAT_DAYS old.
      - Fields: as_of, theme_id, foresight_stage, scoring_lifecycle, radar_lifecycle,
        divergence_quadrant, evidence_z (crowding+divergence), prev_hash (hash-chain),
        schema.
      - Append-only; nightly is sole advancer.
    """
    path = root / _HISTORY_OUT
    path.parent.mkdir(parents=True, exist_ok=True)

    as_of = artifact.get("as_of", _asof_today())

    # ── Read existing rows ─────────────────────────────────────────────────
    existing_lines: list[str] = []
    if path.exists():
        try:
            existing_lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:  # noqa: BLE001
            log.warning("phase_history read failed: %s", exc)

    # Indexes
    seen_pairs: set[tuple] = set()
    last_row: dict[str, dict] = {}   # theme_id -> last full row
    last_hash: dict[str, str] = {}   # theme_id -> hash of last row

    for line in existing_lines:
        try:
            row = json.loads(line)
            tid = row.get("theme_id")
            row_asof = row.get("as_of")
            if not tid or not row_asof:
                continue
            seen_pairs.add((tid, row_asof))
            prev = last_row.get(tid)
            if prev is None or row_asof > prev.get("as_of", ""):
                last_row[tid] = row
                last_hash[tid] = _row_hash(row)
        except Exception:  # noqa: BLE001
            continue

    try:
        as_of_date = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        as_of_date = None

    now_ts = datetime.now(tz=timezone.utc).isoformat()
    new_lines: list[str] = []

    for theme_block in artifact.get("themes", []):
        tid = theme_block.get("theme_id")
        if not tid:
            continue

        # Hard dedup
        if (tid, as_of) in seen_pairs:
            continue

        state = _extract_tracked_state(theme_block)

        # Decide: transition or heartbeat?
        prev = last_row.get(tid)
        should_log = False
        if prev is None:
            should_log = True   # first ever row for this theme
        else:
            prev_state = {
                "foresight_stage": prev.get("foresight_stage"),
                "scoring_lifecycle": prev.get("scoring_lifecycle"),
                "radar_lifecycle": prev.get("radar_lifecycle"),
                "divergence_quadrant": prev.get("divergence_quadrant"),
            }
            if state != prev_state:
                should_log = True   # state transition
            else:
                # Heartbeat check
                prev_asof = prev.get("as_of", "")
                try:
                    prev_date = datetime.strptime(prev_asof[:10], "%Y-%m-%d").date()
                    days_since = (as_of_date - prev_date).days if as_of_date else None
                    if days_since is not None and days_since >= _HEARTBEAT_DAYS:
                        should_log = True
                except Exception:  # noqa: BLE001
                    should_log = True   # unparseable prev → log anyway

        if not should_log:
            continue

        # Build evidence_z (crowding + divergence scores for context)
        basket_intel = theme_block.get("basket_intel") or []
        bi0 = basket_intel[0] if basket_intel else {}
        divboard = theme_block.get("divergence_board") or {}
        evidence_z: dict = {
            "crowding": bi0.get("crowding") if bi0 else None,
            "divergence_score": divboard.get("divergence"),
        }

        row: dict = {
            "schema": HISTORY_SCHEMA,
            "as_of": as_of,
            "ts": now_ts,
            "theme_id": tid,
            "foresight_stage": state["foresight_stage"],
            "scoring_lifecycle": state["scoring_lifecycle"],
            "radar_lifecycle": state["radar_lifecycle"],
            "divergence_quadrant": state["divergence_quadrant"],
            "evidence_z": evidence_z,
            "prev_hash": last_hash.get(tid),   # None for first row
        }

        new_lines.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        # Update last_hash for subsequent themes in same run (ordering-safe)
        last_hash[tid] = _row_hash(row)

    if new_lines:
        if not _ledger_advance_enabled():
            log.debug(
                "thematic_state.append_phase_history: write skipped "
                "(COLLECT_LANE != nightly)"
            )
            return 0
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(new_lines) + "\n")
        except Exception as exc:  # noqa: BLE001
            log.error("phase_history write failed: %s", exc)
            return 0

    return len(new_lines)
