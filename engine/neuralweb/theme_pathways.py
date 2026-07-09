"""engine.neuralweb.theme_pathways — TIL W2 Beneficiary/Loser Pathway Graph compiler.

Display-only, authority block is_context_only=True with all promotion flags False.
Mirrors mechanism_pathways.py and thematic_state.py conventions:
  - Tolerant reads: missing/stale input → honest null + stale_legs entry, never crash.
  - envelope.stamp() with artifact_id from config/synapse.yml.
  - Atomic writes via temp-file + rename.
  - exit-0-always: run_stage() never raises.
  - EN/ZH strings in all data labels.
  - No bare ticker lists — tickers via basket_refs only.

TI-R5 fence: forbidden_uses includes runtime shock-to-beneficiary escalation.
Loser legs are AVOID-shaped evidence, never directional short calls.

Public API
----------
compile(root=None) -> dict
    Compile the theme_pathways artifact from config/theme_pathways.yml.
    Returns schema neuralweb.theme_pathways.v1 dict. Never raises.

run_stage(root: Path) -> None
    Integration point for scripts/build_thematic_state.py auto-discovery.
    Writes data/neuralweb/theme_pathways.json and site/neuralwebdata/theme_pathways.json.
    Never raises.
"""
from __future__ import annotations

import json
import logging
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.theme_pathways.v1"

_STALE_DAYS = 5  # calendar days, mirroring mechanism_pathways / thematic_state

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "display",
    "horizon_role": "context",
    "weights": "none",
    "scored_path_surfaces": [],
    "forbidden_uses": [
        "runtime shock-to-beneficiary escalation (TI-R5)",
        "board ordering",
        "brain-prompt escalation",
        "short-side direction",
        "ranking",
        "sizing",
        "alert_escalation",
        "mastermind_arming",
    ],
}

# ---------------------------------------------------------------------------
# Source artifact paths (relative to repo root)
# ---------------------------------------------------------------------------

_PATHWAYS_CONFIG = "config/theme_pathways.yml"
_CROSSWALK_CONFIG = "config/theme_crosswalk.yml"
_MEMBERSHIP_PATH = "data/baskets/membership.json"
_FORESIGHT_PATH = "site/basketdata/foresight_cascade.json"
_RADAR_PATH = "site/basketdata/radar.json"

# Output paths
_DATA_OUT = "data/neuralweb/theme_pathways.json"
_SITE_OUT = "site/neuralwebdata/theme_pathways.json"

# Artifact id in synapse.yml
_ARTIFACT_ID = "theme-pathways"
_SITE_ARTIFACT_ID = "site-theme-pathways"

# ---------------------------------------------------------------------------
# Language law
# ---------------------------------------------------------------------------

_BANNED_WORDS = ("validated", "caused", "proved", "proof", "buy", "sell", "short", "rotate now")


def _check_banned_words(text: str) -> list[str]:
    """Return banned words found in text (for tests and enforcement)."""
    if not text:
        return []
    tl = text.lower()
    return [w for w in _BANNED_WORDS if w in tl]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
        return yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load %s: %s", path, exc)
        return None


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not load %s: %s", path, exc)
        return None


def _days_since(asof_str: str | None) -> int | None:
    """Calendar days since asof_str (YYYY-MM-DD or ISO-8601)."""
    if not asof_str:
        return None
    try:
        s = str(asof_str).strip()
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - dt).days
    except Exception:  # noqa: BLE001
        return None


def _is_stale(asof_str: str | None) -> bool:
    days = _days_since(asof_str)
    return days is None or days >= _STALE_DAYS


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


# ---------------------------------------------------------------------------
# Crosswalk helpers
# ---------------------------------------------------------------------------

def _load_valid_theme_ids(crosswalk: dict | None) -> set[str]:
    """Return set of canonical theme ids from the crosswalk."""
    if not crosswalk:
        return set()
    return {t["id"] for t in crosswalk.get("themes", []) if "id" in t}


def _load_valid_basket_ids(crosswalk: dict | None) -> set[str]:
    """Return set of basket ids mentioned in the crosswalk."""
    if not crosswalk:
        return set()
    ids: set[str] = set()
    for t in crosswalk.get("themes", []):
        ids.update(t.get("basket_ids", []))
    # Also add unmapped baskets
    for b in crosswalk.get("unmapped_baskets", []):
        if "id" in b:
            ids.add(b["id"])
    return ids


# ---------------------------------------------------------------------------
# Basket membership index for collision map
# ---------------------------------------------------------------------------

def _build_ticker_basket_index(
    membership: dict | None,
    valid_theme_basket_ids: set[str],
    theme_basket_map: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Build {ticker: [basket_id, ...]} for active members only.

    Only includes baskets that appear in at least one theme's basket_refs
    (so we map per-theme, not per all 46 baskets).
    """
    if not membership:
        return {}
    baskets = membership.get("baskets", {})
    ticker_baskets: dict[str, list[str]] = defaultdict(list)
    for basket_id, b in baskets.items():
        if basket_id not in valid_theme_basket_ids:
            continue
        members = b.get("members", [])
        for m in members:
            if isinstance(m, dict):
                if m.get("removed") is not None:
                    continue
                ticker = m.get("ticker", "")
            else:
                ticker = str(m)
            if ticker:
                ticker_baskets[ticker].append(basket_id)
    return dict(ticker_baskets)


def _build_basket_to_themes(theme_basket_map: dict[str, list[str]]) -> dict[str, list[str]]:
    """Invert theme→baskets to basket→themes."""
    basket_to_themes: dict[str, list[str]] = defaultdict(list)
    for theme_id, basket_ids in theme_basket_map.items():
        for bid in basket_ids:
            basket_to_themes[bid].append(theme_id)
    return dict(basket_to_themes)


def _build_collision_map(
    ticker_basket_index: dict[str, list[str]],
    basket_to_themes: dict[str, list[str]],
) -> list[dict]:
    """Compute purity-weighted cross-theme node collision map.

    For every ticker appearing in >1 theme's basket_refs:
    - purity_weight = 1 / n_themes
    - weight_share_by_theme: {theme_id: purity_weight}
    - warning_en/zh flagging the multi-theme confluence

    Only flags when a ticker appears in baskets that belong to ≥2 distinct themes.
    """
    collisions: list[dict] = []
    for ticker, basket_ids in ticker_basket_index.items():
        # Collect all themes this ticker belongs to (via basket → theme mapping)
        ticker_themes: set[str] = set()
        ticker_theme_baskets: dict[str, list[str]] = defaultdict(list)
        for bid in basket_ids:
            for theme_id in basket_to_themes.get(bid, []):
                ticker_themes.add(theme_id)
                ticker_theme_baskets[theme_id].append(bid)

        n_themes = len(ticker_themes)
        if n_themes <= 1:
            continue

        purity_weight = round(1.0 / n_themes, 4)
        weight_share = {t: purity_weight for t in sorted(ticker_themes)}

        collisions.append({
            "ticker": ticker,
            "themes": sorted(ticker_themes),
            "n_themes": n_themes,
            "baskets": sorted(set(basket_ids)),
            "purity_weight": purity_weight,
            "weight_share_by_theme": weight_share,
            "warning_en": (
                f"{ticker} appears in {n_themes} theme baskets "
                f"({', '.join(sorted(ticker_themes))}); "
                f"apparent multi-theme confluence may reflect shared basket membership, "
                f"not independent confirmation. Purity weight per theme: {purity_weight:.2f}."
            ),
            "warning_zh": (
                f"{ticker} 出现在 {n_themes} 个主题篮子中 "
                f"（{', '.join(sorted(ticker_themes))}）；"
                f"表面上的多主题汇聚可能源于共享篮子成员关系，而非独立确认。"
                f"每主题权重：{purity_weight:.2f}。"
            ),
        })

    # Sort by n_themes descending, then ticker ascending
    collisions.sort(key=lambda x: (-x["n_themes"], x["ticker"]))
    return collisions


# ---------------------------------------------------------------------------
# Evidence enrichment from existing artifacts
# ---------------------------------------------------------------------------

def _load_foresight_band_by_theme(root: Path) -> tuple[dict[str, str | None], list[str]]:
    """Load bottleneck_band per foresight theme. Returns ({theme_id: band}, stale_legs)."""
    stale_legs: list[str] = []
    path = root / _FORESIGHT_PATH
    data = _load_json(path)
    if data is None:
        stale_legs.append(f"foresight_cascade unavailable: {_FORESIGHT_PATH}")
        return {}, stale_legs

    asof = data.get("asof")
    if _is_stale(asof):
        stale_legs.append(f"foresight_cascade stale: asof={asof}")
        return {}, stale_legs

    band_by_theme: dict[str, str | None] = {}
    for t in data.get("themes", []):
        tid = t.get("theme")
        if tid:
            band_by_theme[tid] = t.get("bottleneck_band")
    return band_by_theme, stale_legs


def _load_radar_z_by_basket(root: Path) -> tuple[dict[str, float | None], list[str]]:
    """Load divergence z per basket from radar.json. Returns ({basket_id: z}, stale_legs)."""
    stale_legs: list[str] = []
    path = root / _RADAR_PATH
    data = _load_json(path)
    if data is None:
        stale_legs.append(f"radar unavailable: {_RADAR_PATH}")
        return {}, stale_legs

    asof = data.get("as_of")
    if _is_stale(asof):
        stale_legs.append(f"radar stale: asof={asof}")
        return {}, stale_legs

    z_by_basket: dict[str, float | None] = {}
    for flag in data.get("flags", []):
        basket_id = flag.get("basket")
        if basket_id:
            z_by_basket[basket_id] = flag.get("divergence")
    return z_by_basket, stale_legs


# ---------------------------------------------------------------------------
# Theme pathway compiler
# ---------------------------------------------------------------------------

def _compile_theme_pathway(
    theme_cfg: dict,
    valid_theme_ids: set[str],
    valid_basket_ids: set[str],
    bottleneck_band_by_theme: dict[str, str | None],
    radar_z_by_basket: dict[str, float | None],
    as_of: str,
) -> dict | None:
    """Compile one theme's pathway record.

    Returns None on integrity errors (unknown theme_id) — caller will record stale_leg.
    Never raises.
    """
    theme_id = theme_cfg.get("theme_id", "")
    if theme_id not in valid_theme_ids:
        log.warning("theme_pathways: unknown theme_id %r — skipped", theme_id)
        return None

    raw_nodes: list[dict] = theme_cfg.get("nodes", [])
    raw_edges: list[dict] = theme_cfg.get("edges", [])

    # Index nodes by id
    node_ids = {n["id"] for n in raw_nodes if "id" in n}

    # Compile nodes with evidence enrichment
    compiled_nodes: list[dict] = []
    for n in raw_nodes:
        node_id = n.get("id", "")
        node_type = n.get("node_type", "")
        basket_refs = n.get("basket_refs", []) or []

        # Evidence: radar z for any basket_refs this node has
        basket_evidence: list[dict] = []
        for bid in basket_refs:
            z = radar_z_by_basket.get(bid)
            basket_evidence.append({
                "basket_id": bid,
                "radar_divergence_z": z,
                "note_en": (
                    f"Radar divergence z={z:+.2f}" if z is not None
                    else "Radar data absent or stale"
                ),
                "note_zh": (
                    f"雷达背离z={z:+.2f}" if z is not None
                    else "雷达数据缺失或过期"
                ),
            })

        # Evidence: bottleneck_band for bottleneck nodes
        bottleneck_band: str | None = None
        if node_type == "bottleneck":
            bottleneck_band = bottleneck_band_by_theme.get(theme_id)

        compiled_nodes.append({
            "id": node_id,
            "label_en": n.get("label_en", ""),
            "label_zh": n.get("label_zh", ""),
            "node_type": node_type,
            "basket_refs": basket_refs,
            "rationale": n.get("rationale", ""),
            "evidence": {
                "basket_activity": basket_evidence,
                "bottleneck_band": bottleneck_band,
            },
        })

    # Compile edges
    compiled_edges: list[dict] = []
    orphan_edges: list[str] = []
    for e in raw_edges:
        src = e.get("src", "")
        dst = e.get("dst", "")
        if src not in node_ids:
            orphan_edges.append(f"edge src={src!r} not in nodes")
            continue
        if dst not in node_ids:
            orphan_edges.append(f"edge dst={dst!r} not in nodes")
            continue
        compiled_edges.append({
            "src": src,
            "dst": dst,
            "order": e.get("order", 1),
            "side": e.get("side", "winner"),
            "confidence": e.get("confidence", "low"),
            "rationale": e.get("rationale", ""),
        })

    return {
        "theme_id": theme_id,
        "as_of": as_of,
        "node_count": len(compiled_nodes),
        "edge_count": len(compiled_edges),
        "nodes": compiled_nodes,
        "edges": compiled_edges,
        "orphan_edge_warnings": orphan_edges,
    }


# ---------------------------------------------------------------------------
# Main compile function
# ---------------------------------------------------------------------------

def compile(root: Path | None = None) -> dict:  # noqa: A001
    """Compile the theme_pathways artifact from config/theme_pathways.yml.

    Never raises — returns a minimal error artifact on any unrecoverable error.
    """
    if root is None:
        root = _repo_root()

    as_of = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    stale_legs: list[str] = []

    # -- Load config/theme_pathways.yml -------------------------------------------
    pathways_cfg = _load_yaml(root / _PATHWAYS_CONFIG)
    if pathways_cfg is None:
        stale_legs.append(f"config unavailable: {_PATHWAYS_CONFIG}")
        return _null_artifact(as_of, stale_legs)

    # -- Load crosswalk for valid theme/basket ids --------------------------------
    crosswalk = _load_yaml(root / _CROSSWALK_CONFIG)
    if crosswalk is None:
        stale_legs.append(f"crosswalk unavailable: {_CROSSWALK_CONFIG}")
    valid_theme_ids = _load_valid_theme_ids(crosswalk)
    all_crosswalk_basket_ids = _load_valid_basket_ids(crosswalk)

    # -- Load membership for collision map ----------------------------------------
    membership = _load_json(root / _MEMBERSHIP_PATH)
    if membership is None:
        stale_legs.append(f"membership unavailable: {_MEMBERSHIP_PATH}")

    # -- Evidence enrichment inputs -----------------------------------------------
    bottleneck_band_by_theme, fc_stale = _load_foresight_band_by_theme(root)
    stale_legs.extend(fc_stale)

    radar_z_by_basket, radar_stale = _load_radar_z_by_basket(root)
    stale_legs.extend(radar_stale)

    # -- Build theme→baskets map (from config) ------------------------------------
    # Used for collision map: which baskets does each theme actually reference?
    theme_basket_map: dict[str, list[str]] = {}
    for theme_cfg in pathways_cfg.get("themes", []):
        tid = theme_cfg.get("theme_id", "")
        if not tid:
            continue
        basket_refs: list[str] = []
        for node in theme_cfg.get("nodes", []):
            for bid in node.get("basket_refs", []) or []:
                if bid not in basket_refs:
                    basket_refs.append(bid)
        theme_basket_map[tid] = basket_refs

    # -- Compile per-theme pathways -----------------------------------------------
    theme_pathways: list[dict] = []
    for theme_cfg in pathways_cfg.get("themes", []):
        try:
            rec = _compile_theme_pathway(
                theme_cfg=theme_cfg,
                valid_theme_ids=valid_theme_ids,
                valid_basket_ids=all_crosswalk_basket_ids,
                bottleneck_band_by_theme=bottleneck_band_by_theme,
                radar_z_by_basket=radar_z_by_basket,
                as_of=as_of,
            )
            if rec is not None:
                theme_pathways.append(rec)
        except Exception as exc:  # noqa: BLE001
            theme_id = theme_cfg.get("theme_id", "?")
            log.error("theme_pathways: compile error for %s: %s", theme_id, exc)
            stale_legs.append(f"compile error: theme_id={theme_id}: {exc}")

    # -- Build cross-theme collision map ------------------------------------------
    collision_map: list[dict] = []
    if membership is not None:
        # Only baskets referenced in config theme nodes
        config_referenced_baskets: set[str] = set()
        for bids in theme_basket_map.values():
            config_referenced_baskets.update(bids)

        basket_to_themes = _build_basket_to_themes(theme_basket_map)
        ticker_basket_index = _build_ticker_basket_index(
            membership=membership,
            valid_theme_basket_ids=config_referenced_baskets,
            theme_basket_map=theme_basket_map,
        )
        try:
            collision_map = _build_collision_map(
                ticker_basket_index=ticker_basket_index,
                basket_to_themes=basket_to_themes,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("theme_pathways: collision map error: %s", exc)
            stale_legs.append(f"collision map error: {exc}")
    else:
        stale_legs.append("collision_map skipped: membership unavailable")

    # -- Assemble artifact --------------------------------------------------------
    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": as_of,
        "display_only": True,
        "not_a_signal": True,
        "authority": AUTHORITY_BLOCK,
        "config_version": pathways_cfg.get("version", 1),
        "theme_count": len(theme_pathways),
        "theme_pathways": theme_pathways,
        "cross_theme_collision_map": {
            "collision_count": len(collision_map),
            "note_en": (
                "Tickers appearing in basket_refs of 2+ canonical themes. "
                "Apparent multi-theme confluence may reflect shared basket membership rather than "
                "independent confirmation. Purity weight = 1/n_themes per ticker."
            ),
            "note_zh": (
                "出现在2个及以上主题篮子引用中的股票。"
                "多主题表面汇聚可能源于共享篮子成员资格，而非独立确认。"
                "纯度权重 = 1/主题数。"
            ),
            "collisions": collision_map,
        },
        "stale_legs": stale_legs,
    }

    return artifact


def _null_artifact(as_of: str, stale_legs: list[str]) -> dict:
    """Minimal honest-null artifact when config is unavailable."""
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "display_only": True,
        "not_a_signal": True,
        "authority": AUTHORITY_BLOCK,
        "theme_count": 0,
        "theme_pathways": [],
        "cross_theme_collision_map": {
            "collision_count": 0,
            "collisions": [],
        },
        "stale_legs": stale_legs,
    }


# ---------------------------------------------------------------------------
# run_stage — integration point for build_thematic_state.py
# ---------------------------------------------------------------------------

def run_stage(root: Path) -> None:
    """Build theme_pathways artifacts.

    Contract: never raises, always exits cleanly.
    Writes:
        data/neuralweb/theme_pathways.json  (primary; git-committed)
        site/neuralwebdata/theme_pathways.json  (site mirror)
    """
    try:
        artifact = compile(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("theme_pathways.run_stage: compile failed unexpectedly: %s", exc)
        as_of = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        artifact = _null_artifact(as_of, [f"compile exception: {exc}"])

    # Stamp with envelope
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        artifact = stamp(artifact, artifact_id=_ARTIFACT_ID)
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_pathways: envelope stamp failed (non-fatal): %s", exc)

    # Write data artifact (atomic)
    data_path = root / _DATA_OUT
    try:
        _atomic_write_json(data_path, artifact)
        log.info("theme_pathways: wrote %s", data_path)
        n_themes = artifact.get("theme_count", 0)
        n_stale = len(artifact.get("stale_legs", []))
        n_collisions = artifact.get("cross_theme_collision_map", {}).get("collision_count", 0)
        print(
            f"[theme_pathways] themes={n_themes} collisions={n_collisions} stale_legs={n_stale}",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("theme_pathways: data write failed: %s", exc)

    # Write site mirror (atomic)
    site_path = root / _SITE_OUT
    try:
        _atomic_write_json(site_path, artifact)
        log.info("theme_pathways: wrote site mirror %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.error("theme_pathways: site write failed: %s", exc)
