"""engine.theme_context — theme_context.v1 producer (display-tier, additive).

Computes a leadership-health read layered on top of the allocation rank so
baskets.html's "Prevailing narrative" can honestly represent a broken leader
without modifying the rank/score/eligible/weights of engine.narrative_rotation.

Contract: /tmp/theme_context_contract.md (pinned).
China delta: /tmp/theme_context_cn_contract.md (pinned; wins on china specifics).

Public API
----------
compute_theme_context(alloc, theme_intel, region='us', root=None) -> dict | None
    Main producer.  Pure/additive — never raises, logs + returns None on shortfall.

write_context(ctx, root=None) -> None
    Write the region-appropriate artifact path (derived from ctx['region']).

read_context(region='us', root=None) -> dict | None
    Consumer API.  Returns None when the artifact is absent.
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "theme_context.v1"

# ── Lane gate — delegates to engine.ledger_lane (single definition) ────────────


def _advance_enabled(region: str) -> bool:
    """True only when the lane for the given region is armed.

    'us'    -> engine.ledger_lane.nightly_advance_enabled()  (COLLECT_LANE=nightly)
    'china' -> engine.ledger_lane.asia_advance_enabled()     (CN_LANE=asia)
    All other regions -> nightly gate (safe default; can be tightened later).
    """
    try:
        from engine.ledger_lane import nightly_advance_enabled, asia_advance_enabled
        if region == "china":
            return asia_advance_enabled()
        return nightly_advance_enabled()
    except Exception:  # noqa: BLE001 — fail-open, never block compute
        return False


# ── Health classification (deterministic; exact precedence per contract §Health) ──


def _classify_health(
    breadth: float | None,
    r10: float | None,
    label: str | None,
    reco: str | None,
    val_state: str | None,
) -> str:
    """Return 'broken' | 'confirmed' | 'mixed'.

    Null-safe: a missing field fails the test it appears in (never treated as
    passing).  If label AND breadth AND r10 are all missing -> 'mixed'.
    """
    # If all three key fields absent -> mixed
    if label is None and breadth is None and r10 is None:
        return "mixed"

    # Rule 1 — broken
    cond_a = (breadth is not None and breadth <= 0.25) and (
        r10 is not None and r10 <= -0.05
    )
    cond_b = label == "deteriorating"
    cond_c = (reco == "avoid") and (r10 is not None and r10 < 0)
    if cond_a or cond_b or cond_c:
        return "broken"

    # Rule 2 — confirmed
    ok_breadth = breadth is not None and breadth >= 0.55
    ok_r10 = r10 is not None and r10 >= -0.02
    ok_label = label in {"dominant", "emerging", "neutral"}
    ok_reco = reco in {"enter", "accumulate", "hold"}
    if ok_breadth and ok_r10 and ok_label and ok_reco:
        return "confirmed"

    return "mixed"


# ── per-theme health row ────────────────────────────────────────────────────────


def _theme_health_row(
    rank_row: dict,
    ti_by_id: dict[str, dict],
    history_map: dict[str, dict],  # {id: {"days_in_label": int|None, "score_delta_5d": int|None}}
) -> dict:
    """Build the per-theme context row for the 'themes' map."""
    tid = rank_row.get("id", "")
    ti = ti_by_id.get(tid, {})
    durability = rank_row.get("durability") or {}

    breadth = durability.get("breadth")
    r10 = rank_row.get("r10")
    label = ti.get("label")
    reco = ti.get("reco")
    val_state = rank_row.get("val_state")
    score = ti.get("score")

    health = _classify_health(breadth, r10, label, reco, val_state)
    hist = history_map.get(tid, {})
    return {
        "label": label,
        "reco": reco,
        "score": score,
        "rank": rank_row.get("rank"),
        "alloc_rank": rank_row.get("rank"),  # same as rank (alloc rank IS the narr rank)
        "health": health,
        "breadth": breadth,
        "r10": r10,
        "val_state": val_state,
        "days_in_label": hist.get("days_in_label"),
        "score_delta_5d": hist.get("score_delta_5d"),
    }


# ── Leadership state machine ────────────────────────────────────────────────────


def _leadership_state(
    leader_health: str,
    strength_entries: list[dict],
    leader_category: str | None,
) -> str:
    """Compute 'steady' | 'strain' | 'rotating'."""
    if leader_health == "broken":
        # rotating requires >=3 strength entries from different category than leader
        cross_category_count = sum(
            1
            for e in strength_entries
            if e.get("category") != leader_category
        )
        if cross_category_count >= 3:
            return "rotating"
    if leader_health != "confirmed":
        return "strain"
    return "steady"


# ── Stance lines ───────────────────────────────────────────────────────────────


_STANCE: dict[str, dict[str, str]] = {
    "rotating": {
        "en": "Rotation under way — favour the fresh leaders, not the old one.",
        "zh": "轮动进行中——关注新领涨主题，勿追旧龙头。",
    },
    "strain": {
        "en": "Leadership under strain — watch, don't chase.",
        "zh": "领涨承压——观望，勿追高。",
    },
    "steady": {
        "en": "Leadership steady — stay with the leaders.",
        "zh": "领涨格局稳定——持有领涨主题。",
    },
}


# ── Category ZH translation map (migration note_zh only — never user-facing in EN) ─────
# US categories + China-specific categories (items 6 in CN contract).
_CAT_ZH: dict[str, str] = {
    # US categories
    "AI & Technology": "AI与科技",
    "Artificial Intelligence": "人工智能",
    "Biotech": "生物技术",
    "Communication Services": "通信服务",
    "Consumer Cyclical": "可选消费",
    "Consumer Defensive": "必需消费",
    "Crypto & Digital Assets": "加密与数字资产",
    "Energy": "能源",
    "Energy & Power": "能源与电力",
    "Financials": "金融",
    "Healthcare": "医疗保健",
    "Industrials": "工业",
    "Industrials & Defense": "工业与国防",
    "Materials & Mining": "原材料与矿业",
    "Other": "其他",
    "Real Estate": "房地产",
    "Semiconductors": "半导体",
    "Semiconductors & Hardware": "半导体与硬件",
    "Software": "软件",
    "Technology": "科技",
    "US Sectors (EW)": "美股行业（等权）",
    "Utilities": "公用事业",
    # China-specific categories (CN contract item 6)
    "Advanced Manufacturing": "先进制造",
    "Consumer & Brands": "消费与品牌",
    "Cyclicals & Resources": "周期与资源",
    "Financials & Value": "金融与价值",
    "New Energy & Autos": "新能源与汽车",
    "Technology & AI": "科技与AI",
}


# ── Migration (category-level breadth/r10 aggregation) ─────────────────────────


def _migration(rank_rows: list[dict], ti_by_id: dict[str, dict]) -> dict:
    """Aggregate breadth/r10 by category for absorbing/bleeding bands.

    absorbing: top 3 by avg_breadth desc (MAX 3)
    bleeding:  top 3 by avg_breadth asc  (MAX 3)
    """
    from collections import defaultdict

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for rr in rank_rows:
        tid = rr.get("id", "")
        cat = rr.get("category") or "Other"
        durability = rr.get("durability") or {}
        breadth = durability.get("breadth")
        r10 = rr.get("r10")
        if breadth is not None or r10 is not None:
            by_cat[cat].append({"breadth": breadth, "r10": r10})

    agg = []
    for cat, items in by_cat.items():
        bvals = [x["breadth"] for x in items if x["breadth"] is not None]
        rvals = [x["r10"] for x in items if x["r10"] is not None]
        avg_breadth = sum(bvals) / len(bvals) if bvals else None
        avg_r10 = sum(rvals) / len(rvals) if rvals else None
        agg.append({
            "category": cat,
            "avg_breadth": round(avg_breadth, 3) if avg_breadth is not None else None,
            "avg_r10": round(avg_r10, 4) if avg_r10 is not None else None,
            "n": len(items),
        })

    # absorbing: highest avg_breadth first
    absorbing_sorted = sorted(
        [x for x in agg if x["avg_breadth"] is not None],
        key=lambda x: -(x["avg_breadth"] or 0),
    )[:3]
    # bleeding: lowest avg_breadth first
    bleeding_sorted = sorted(
        [x for x in agg if x["avg_breadth"] is not None],
        key=lambda x: (x["avg_breadth"] or 0),
    )[:3]

    # Compose ONE plain sentence; ZH uses _CAT_ZH map — never raw EN slug in ZH copy.
    if absorbing_sorted and bleeding_sorted:
        top_abs = absorbing_sorted[0]["category"]
        top_ble = bleeding_sorted[0]["category"]
        note_en = f"Money is moving into {top_abs} and out of {top_ble}."
        note_zh = (f"资金正流入{_CAT_ZH.get(top_abs, top_abs)}，"
                   f"流出{_CAT_ZH.get(top_ble, top_ble)}。")
    elif absorbing_sorted:
        top_abs = absorbing_sorted[0]["category"]
        note_en = f"Money is moving into {top_abs}."
        note_zh = f"资金正流入{_CAT_ZH.get(top_abs, top_abs)}。"
    else:
        note_en = "No clear destination for money yet."
        note_zh = "资金去向暂不明朗。"

    return {
        "absorbing": absorbing_sorted,
        "bleeding": bleeding_sorted,
        "note_en": note_en,
        "note_zh": note_zh,
    }


# ── Alignment vs rotation_events.json ──────────────────────────────────────────


def _alignment(
    strength_ids: list[str],
    root: Path,
    region: str = "us",
) -> dict:
    """Cross-check strength themes vs active sector rotation events.

    Reads rotation_events.json (US) or rotation_events_china.json (china) per CN contract item 5.
    Returns sector_rotation_agrees: True | False | None.
    None = artifact absent/unreadable (fail-open per contract).
    """
    re_path = _alignment_path(region, root)
    if not re_path.exists():
        return {"sector_rotation_agrees": None, "note_en": "", "note_zh": ""}
    try:
        payload = json.loads(re_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"sector_rotation_agrees": None, "note_en": "", "note_zh": ""}
        active = payload.get("active") or []
        if not isinstance(active, list):
            active = []
        # Any active rotation event where the 'to_leg' key is in strength_ids ->
        # sector rotation agrees that a fresh theme is gaining leadership.
        to_legs = {
            (e.get("to_leg") or {}).get("key", "")
            for e in active
            if isinstance(e, dict)
        }
        agrees = bool(strength_ids and to_legs.intersection(strength_ids))
        if agrees:
            note_en = "Sector rotation events agree with strength themes."
            note_zh = "行业轮动事件与强势主题一致。"
        else:
            note_en = "No active sector rotation events aligned with strength themes."
            note_zh = "无活跃行业轮动事件与强势主题对齐。"
        return {
            "sector_rotation_agrees": agrees,
            "note_en": note_en,
            "note_zh": note_zh,
        }
    except Exception as e:  # noqa: BLE001 — fail-open
        log.debug("theme_context._alignment: %s", e)
        return {"sector_rotation_agrees": None, "note_en": "", "note_zh": ""}


# ── Region-aware artifact / history path helpers ────────────────────────────────


def _artifact_path(region: str, root: Path) -> Path:
    """Return the region-scoped theme_context JSON path.

    'us'    -> site/basketdata/theme_context.json    (backward-compat)
    'china' -> site/basketdata/theme_context_cn.json
    """
    if region == "china":
        return root / "site" / "basketdata" / "theme_context_cn.json"
    return root / "site" / "basketdata" / "theme_context.json"


# ── Alignment vs rotation_events*.json (region-aware) ──────────────────────────


def _alignment_path(region: str, root: Path) -> Path:
    """Return the region-scoped rotation_events JSON path."""
    if region == "china":
        return root / "site" / "marketdata" / "rotation_events_china.json"
    return root / "site" / "marketdata" / "rotation_events.json"


# ── History JSONL helpers ───────────────────────────────────────────────────────


def _history_path(root: Path, region: str = "us") -> Path:
    """Return the region-scoped history JSONL path.

    'us'    -> data/themes/context_history.jsonl    (backward-compat)
    'china' -> data/themes/context_history_cn.jsonl
    A china run MUST NEVER touch the US file.
    """
    if region == "china":
        return root / "data" / "themes" / "context_history_cn.jsonl"
    return root / "data" / "themes" / "context_history.jsonl"


def _load_history(root: Path, region: str = "us") -> list[dict]:
    """Load context_history[_cn].jsonl.  Returns [] on any failure."""
    p = _history_path(root, region)
    if not p.exists():
        return []
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as e:  # noqa: BLE001
        log.debug("theme_context._load_history: %s", e)
    return rows


def _write_history(rows: list[dict], root: Path, region: str = "us") -> None:
    p = _history_path(root, region)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, separators=(",", ":"), default=str) for r in rows) + "\n",
        encoding="utf-8",
    )


# ── One-shot seed from baskets.parquet ─────────────────────────────────────────


def _seed_from_archive(root: Path, region: str = "us") -> list[dict]:
    """Best-effort seed from data/signal_archive/baskets[_china].parquet.

    'us'    -> data/signal_archive/baskets.parquet
    'china' -> data/signal_archive/baskets_china.parquet  (CN contract item 4)
    Each row carries snapshot_json with per-theme label/score.  Returns empty
    list on any failure (including missing parquet).
    """
    try:
        import pandas as pd

        archive_name = "baskets_china.parquet" if region == "china" else "baskets.parquet"
        p = root / "data" / "signal_archive" / archive_name
        if not p.exists():
            return []
        df = pd.read_parquet(str(p))
        if df.empty or "snapshot_json" not in df.columns:
            return []
        if "asof" not in df.columns:
            return []

        # Sort by asof ascending so we can build history in order
        df = df.copy()
        df["_asof_s"] = df["asof"].astype(str)
        df = df.sort_values("_asof_s").reset_index(drop=True)

        rows = []
        for _, row in df.iterrows():
            try:
                snap = json.loads(row["snapshot_json"])
            except Exception:  # noqa: BLE001
                continue
            asof = str(row.get("asof", "")).strip()
            if not asof:
                continue
            themes_list = snap.get("themes") or []
            labels = {t["id"]: t.get("label") for t in themes_list if t.get("id")}
            scores = {t["id"]: t.get("score") for t in themes_list if t.get("id")}
            rows.append({
                "asof": asof,
                "leadership_state": None,   # not available from archive
                "trailing_leader_id": None,
                "leader_health": None,
                "labels": labels,
                "scores": scores,
            })
        return rows
    except Exception as e:  # noqa: BLE001
        log.debug("theme_context._seed_from_archive: %s", e)
        return []


# ── History-derived metrics ─────────────────────────────────────────────────────


def _days_in_label_map(history: list[dict], current_labels: dict[str, str]) -> dict[str, int | None]:
    """Count consecutive days each theme has been in its CURRENT label (from the end of history)."""
    if not history:
        return {tid: None for tid in current_labels}
    result = {}
    for tid, cur_label in current_labels.items():
        count = 0
        for row in reversed(history):
            past_label = (row.get("labels") or {}).get(tid)
            if past_label == cur_label:
                count += 1
            else:
                break
        result[tid] = count if count > 0 else None
    return result


def _score_delta_5d_map(
    history: list[dict], current_scores: dict[str, int | None]
) -> dict[str, int | None]:
    """delta between current score and score 5 rows ago in history."""
    if len(history) < 5:
        return {tid: None for tid in current_scores}
    row_5d_ago = history[-5]
    result = {}
    for tid, cur_score in current_scores.items():
        past_score = (row_5d_ago.get("scores") or {}).get(tid)
        if cur_score is not None and past_score is not None:
            try:
                result[tid] = int(cur_score) - int(past_score)
            except (TypeError, ValueError):
                result[tid] = None
        else:
            result[tid] = None
    return result


def _compute_state_changes(
    history: list[dict],
    current: dict,
) -> dict[str, dict]:
    """Compare current snapshot vs last history row to emit change stamps.

    Keys: 'leadership_state', 'trailing_leader_id', 'leader_health',
    plus 'theme_label:<id>' for themes whose label changed.
    """
    if not history:
        return {}
    prev = history[-1]
    today = current.get("asof", "")
    prev_asof = prev.get("asof", "")

    def _stamp(key: str, current_val: Any, prev_val: Any) -> dict | None:
        if current_val is None and prev_val is None:
            return None
        if current_val != prev_val:
            return {
                "current": current_val,
                "prev": prev_val,
                "changed_on": today,
                "days_in_state": 1,
            }
        # Same value — walk back from end of history to find the first row in this run.
        # prev_val is history[-1].get(key); iterate reversed(history) to count consecutive
        # rows matching current_val, and record the asof of the OLDEST one in the run.
        count = 1
        first_asof = prev_asof
        for row in reversed(history):
            val = row.get(key) if key in row else None
            if val == current_val:
                count += 1
                row_asof = row.get("asof", "")
                if row_asof and row_asof < first_asof:
                    first_asof = row_asof
            else:
                break
        return {
            "current": current_val,
            "prev": prev_val,
            "changed_on": first_asof,
            "days_in_state": count,
        }

    changes: dict[str, dict] = {}
    for key in ("leadership_state", "trailing_leader_id", "leader_health"):
        s = _stamp(key, current.get(key), prev.get(key))
        if s is not None:
            changes[key] = s

    # theme labels
    cur_labels = current.get("labels") or {}
    prev_labels = prev.get("labels") or {}
    for tid, cur_lab in cur_labels.items():
        prev_lab = prev_labels.get(tid)
        if cur_lab != prev_lab:
            changes[f"theme_label:{tid}"] = {
                "current": cur_lab,
                "prev": prev_lab,
                "changed_on": today,
                "days_in_state": 1,
            }
    return changes


def _days_in_state(history: list[dict], current_state: str | None) -> int | None:
    """Count consecutive rows (from end) where leadership_state == current_state."""
    if current_state is None or not history:
        return None
    count = 0
    for row in reversed(history):
        if row.get("leadership_state") == current_state:
            count += 1
        else:
            break
    return count if count > 0 else 1  # at least 1 for current day


# ── Repo root helper ────────────────────────────────────────────────────────────


def _repo_root(root: Any = None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from lib import config as _cfg
        return _cfg.ROOT
    except Exception:  # noqa: BLE001
        return Path(__file__).parent.parent


# ── Main producer ───────────────────────────────────────────────────────────────


def _disp(name: Any) -> Any:
    """Display form of a basket name: drop the '(Equal-Weight)' / '（等权）' suffix
    (Tier-1 redundancy — the page footer already discloses equal weighting)."""
    if not isinstance(name, str):
        return name
    return name.replace(" (Equal-Weight)", "").replace("（等权）", "").strip()


def compute_theme_context(
    alloc: dict,
    theme_intel: dict,
    region: str = "us",
    root: Any = None,
) -> dict | None:
    """Compute theme_context.v1.

    Parameters
    ----------
    alloc : dict
        Output of compute_narrative_rotation() — carries 'ranks' (list of per-basket
        dicts with id/durability/r10/val_state) and 'as_of'.
    theme_intel : dict
        Output of compute_theme_intel() — carries 'themes' (list with id/label/reco/score).
    region : str
        'us' | 'china' | 'hk' | 'canada'.
    root : Path | None
        Repo root override (for tests).

    Returns
    -------
    dict | None
        theme_context.v1 payload, or None on shortfall.
    """
    try:
        return _compute(alloc, theme_intel, region, _repo_root(root))
    except Exception as e:  # noqa: BLE001 — never raises
        log.error("compute_theme_context failed: %s", e, exc_info=True)
        return None


def _compute(alloc: dict, theme_intel: dict, region: str, root: Path) -> dict | None:
    # ── Validate inputs ────────────────────────────────────────────────────
    rank_rows: list[dict] = alloc.get("ranks", [])
    as_of: str = alloc.get("as_of", "")
    if not rank_rows or not as_of:
        log.warning("theme_context: alloc has no ranks or as_of — returning None")
        return None

    ti_themes: list[dict] = theme_intel.get("themes", [])
    if not isinstance(ti_themes, list):
        ti_themes = []

    # Index theme_intel by id for O(1) lookup
    ti_by_id: dict[str, dict] = {t["id"]: t for t in ti_themes if t.get("id")}

    # ── Load history (for state_changes / days_in_state / metric deltas) ──
    history = _load_history(root, region)

    # One-shot seed if history absent AND lane armed
    if not history and _advance_enabled(region):
        try:
            seed_rows = _seed_from_archive(root, region)
            if seed_rows:
                _write_history(seed_rows, root, region)
                history = seed_rows
        except Exception as e:  # noqa: BLE001
            log.debug("theme_context: seed_from_archive failed: %s", e)

    # ── Collect label/score for history-based metrics ──────────────────────
    current_labels: dict[str, str | None] = {}
    current_scores: dict[str, int | None] = {}
    for rr in rank_rows:
        tid = rr.get("id")
        if not tid:
            continue
        ti = ti_by_id.get(tid, {})
        current_labels[tid] = ti.get("label")
        current_scores[tid] = ti.get("score")

    days_in_label = _days_in_label_map(history, current_labels)
    score_delta = _score_delta_5d_map(history, current_scores)

    history_map: dict[str, dict] = {
        tid: {
            "days_in_label": days_in_label.get(tid),
            "score_delta_5d": score_delta.get(tid),
        }
        for tid in current_labels
    }

    # ── Per-theme health rows ──────────────────────────────────────────────
    themes_map: dict[str, dict] = {}
    for rr in rank_rows:
        tid = rr.get("id")
        if not tid:
            continue
        themes_map[tid] = _theme_health_row(rr, ti_by_id, history_map)

    # ── Trailing leader (alloc rank 1) ────────────────────────────────────
    sorted_ranks = sorted(rank_rows, key=lambda r: r.get("rank", 9999))
    if not sorted_ranks:
        log.warning("theme_context: no rank rows — returning None")
        return None

    leader_row = sorted_ranks[0]
    leader_id = leader_row.get("id", "")
    leader_dur = leader_row.get("durability") or {}
    leader_breadth = leader_dur.get("breadth")
    leader_r10 = leader_row.get("r10")
    leader_ti = ti_by_id.get(leader_id, {})
    leader_label = leader_ti.get("label")
    leader_reco = leader_ti.get("reco")
    leader_score = leader_ti.get("score")
    leader_val_state = leader_row.get("val_state")

    leader_health = _classify_health(
        leader_breadth, leader_r10, leader_label, leader_reco, leader_val_state
    )

    trailing_leader: dict = {
        "id": leader_id,
        "name": _disp(leader_row.get("name")),
        "name_zh": _disp(leader_row.get("name_zh")),
        "alloc_rank": leader_row.get("rank"),
        "health": leader_health,
        "breadth": leader_breadth,
        "r10": leader_r10,
        "val_state": leader_val_state,
        "label": leader_label,
        "reco": leader_reco,
        "desk_score": leader_score,
    }

    # ── Challenger (rank 2) ────────────────────────────────────────────────
    challenger: dict | None = None
    if len(sorted_ranks) >= 2:
        chall_row = sorted_ranks[1]
        chall_id = chall_row.get("id", "")
        leader_score_val = leader_row.get("score")
        chall_score_val = chall_row.get("score")
        margin = None
        if leader_score_val is not None and chall_score_val is not None:
            try:
                margin = round(float(leader_score_val) - float(chall_score_val), 3)
            except (TypeError, ValueError):
                margin = None
        challenger = {
            "id": chall_id,
            "name": _disp(chall_row.get("name")),
            "name_zh": _disp(chall_row.get("name_zh")),
            "margin": margin,
        }

    # ── Strength entries (health=confirmed, sorted by desk_score desc, MAX 6) ──
    strength: list[dict] = []
    for rr in rank_rows:
        tid = rr.get("id", "")
        row_health = themes_map.get(tid, {}).get("health", "mixed")
        if row_health != "confirmed":
            continue
        ti = ti_by_id.get(tid, {})
        dur = rr.get("durability") or {}
        strength.append({
            "id": tid,
            "name": _disp(rr.get("name")),
            "name_zh": _disp(rr.get("name_zh")),
            "desk_score": ti.get("score"),
            "health": "confirmed",
            "breadth": dur.get("breadth"),
            "r10": rr.get("r10"),
            "category": rr.get("category"),
        })

    strength.sort(key=lambda x: -(x.get("desk_score") or 0))
    strength = strength[:6]

    # ── Breaking entries (health=broken, sorted r10 asc worst first, MAX 4) ──
    breaking: list[dict] = []
    for rr in rank_rows:
        tid = rr.get("id", "")
        row_health = themes_map.get(tid, {}).get("health", "mixed")
        if row_health != "broken":
            continue
        ti = ti_by_id.get(tid, {})
        dur = rr.get("durability") or {}
        breaking.append({
            "id": tid,
            "name": _disp(rr.get("name")),
            "name_zh": _disp(rr.get("name_zh")),
            "desk_score": ti.get("score"),
            "health": "broken",
            "breadth": dur.get("breadth"),
            "r10": rr.get("r10"),
            "category": rr.get("category"),
        })

    breaking.sort(key=lambda x: (x.get("r10") if x.get("r10") is not None else 0))
    breaking = breaking[:4]

    # Ensure trailing_leader is in breaking when it is broken
    if leader_health == "broken":
        leader_ids_in_breaking = {b["id"] for b in breaking}
        if leader_id not in leader_ids_in_breaking:
            breaking.insert(0, {
                "id": leader_id,
                "name": trailing_leader["name"],
                "name_zh": trailing_leader["name_zh"],
                "desk_score": leader_score,
                "health": "broken",
                "breadth": leader_breadth,
                "r10": leader_r10,
                "category": leader_row.get("category"),
            })
            breaking = breaking[:4]

    # ── Leadership state ───────────────────────────────────────────────────
    strength_ids = [s["id"] for s in strength]
    l_state = _leadership_state(leader_health, strength, leader_row.get("category"))

    # ── days_in_state (from history) ───────────────────────────────────────
    dis = _days_in_state(history, l_state) if history else None

    # ── Stance lines ───────────────────────────────────────────────────────
    stance = _STANCE[l_state]

    # ── Migration ──────────────────────────────────────────────────────────
    migration = _migration(rank_rows, ti_by_id)

    # ── Alignment ──────────────────────────────────────────────────────────
    alignment = _alignment(strength_ids, root, region)

    # ── state_changes ──────────────────────────────────────────────────────
    current_snapshot_for_changes = {
        "asof": as_of,
        "leadership_state": l_state,
        "trailing_leader_id": leader_id,
        "leader_health": leader_health,
        "labels": current_labels,
    }
    state_changes = _compute_state_changes(history, current_snapshot_for_changes)

    # ── prev_asof ──────────────────────────────────────────────────────────
    prev_asof = history[-1].get("asof") if history else None

    # ── Assemble output ────────────────────────────────────────────────────
    ctx: dict = {
        "schema": _SCHEMA,
        "as_of": as_of,
        "region": region,
        "display_only": True,
        "leadership": {
            "state": l_state,
            "days_in_state": dis,
            "stance_en": stance["en"],
            "stance_zh": stance["zh"],
            "trailing_leader": trailing_leader,
            "challenger": challenger,
            "strength": strength,
            "breaking": breaking,
        },
        "migration": migration,
        "alignment": alignment,
        "themes": themes_map,
        "state_changes": state_changes,
        "prev_asof": prev_asof,
    }

    # ── Advance history (lane-gated; same-day idempotent) ──────────────────
    history_row = {
        "asof": as_of,
        "leadership_state": l_state,
        "trailing_leader_id": leader_id,
        "leader_health": leader_health,
        "labels": current_labels,
        "scores": current_scores,
    }

    if _advance_enabled(region):
        updated_history = list(history)
        if updated_history and updated_history[-1].get("asof") == as_of:
            # Same-day idempotent: replace last row
            updated_history[-1] = history_row
        else:
            updated_history.append(history_row)
        try:
            _write_history(updated_history, root, region)
        except Exception as e:  # noqa: BLE001
            log.warning("theme_context: history write failed: %s", e)
    # Off-lane: do not touch history file.

    return ctx


# ── Write / Read API ────────────────────────────────────────────────────────────


def write_context(ctx: dict, root: Any = None) -> None:
    """Write the region-scoped artifact.

    Path is derived from ctx['region']:
      'us'    -> site/basketdata/theme_context.json    (backward-compat)
      'china' -> site/basketdata/theme_context_cn.json
    """
    r = _repo_root(root)
    region = ctx.get("region", "us")
    p = _artifact_path(region, r)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ctx, separators=(",", ":"), default=str), encoding="utf-8")


def read_context(region: str = "us", root: Any = None) -> dict | None:
    """Consumer API — returns the committed JSON or None if absent.

    Reads the region-scoped path; returns None when absent or region tag mismatches.
    """
    r = _repo_root(root)
    p = _artifact_path(region, r)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        # Soft region guard: accept if field absent (legacy) but reject if explicitly different.
        stored_region = d.get("region")
        if stored_region is not None and stored_region != region:
            return None
        return d
    except Exception as e:  # noqa: BLE001
        log.debug("theme_context.read_context: %s", e)
        return None
