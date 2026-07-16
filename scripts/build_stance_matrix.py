"""scripts/build_stance_matrix.py — MLC W2b / W2b-2 stance-matrix builder.

Program: MLC (Megacap Leadership Coherence) W2b + W2b-2 coherence layer.
Rulings: MLC-W2b, MLC-W2b-2.

Per basket slug (union of theme_intel.themes ids), emits a row collecting
each available verdict mapped onto one signed tier scale (-2..+2).  MLC-W2b-2
ADDITIVE: also emits a top-level `sectors` array (one row per SPDR sector ETF
present in the freshness-gated sector_central doc) with three verdicts each:
  • conviction — same label→tier map as the basket-side sector organ
  • rs         — momentum.lead → tier (leading +1, mid-pack 0, lagging −1;
                 narrower ±1 range: RS lead is a coarser read)
  • baskets    — median tier of member-basket theme verdicts (reverse-mapped
                 via the existing inline sector-proxy dict; emitted only when
                 ≥1 member basket carries a theme verdict)
Schema stays mlc.stance_matrix.v1 (additive key; no version bump).

Tier-mapping tables are pre-registered-arbitrary (MLC-W2b, MLC-W2b-2; frozen
— no tuning on observed cases). All mappings are DISPLAY-ONLY: nothing here
ranks, gates, sizes, or escalates. CONST-ART2 authority: false.

Output: site/mlcdata/stance_matrix.json  (schema: mlc.stance_matrix.v1)

Covered by existing `git add data/ site/` commit step in daily.yml engine job.

Always exits 0 — fail-soft; absent inputs yield null fields / row omission.
Accepts --root <path> for test redirects (all reads and writes under that root).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-registered tier-mapping tables (MLC-W2b; frozen — no tuning on observed cases)
# ---------------------------------------------------------------------------

# sector conviction label -> signed tier
_SECTOR_TIER: dict[str, int] = {
    "Accumulate": +2,
    "Constructive": +1,
    "Neutral": 0,
    "Cautious": -1,
    "Reduce": -2,
}

# theme reco -> signed tier
_RECO_TIER: dict[str, int] = {
    "enter": +2,
    "accumulate": +1,
    "hold": 0,
    "trim": -1,
    "avoid": -2,
}

# basket confluence class -> signed tier
_CONFLUENCE_TIER: dict[str, int] = {
    "entry_now": +2,
    "forming": +1,
    "tailwind": +1,
    "neutral": 0,
    "late": -1,
    "headwind": -2,
}

# mag7 trend_state -> signed tier (only applied to the "mag7" basket row)
_M7C_TIER: dict[str, int] = {
    "running_broad": +2,
    "running_narrow": +1,
    "turning_up": +1,
    "cooling": 0,
    "rolling_over": -1,
    "down": -2,
}

# basket id -> SPDR sector ETF (reused from engine/theme_scoring._SECTOR_PROXY;
# imported at runtime so the map stays single-source; also inline for test isolation).
_SECTOR_PROXY_INLINE: dict[str, str] = {
    "mag7": "XLK", "ai_infra": "SMH", "ai_software": "XLK", "defense": "XLI",
    "power_grid": "XLU", "reshoring": "XLI", "regional_banks": "XLF",
    "managed_care": "XLV", "housing": "XLY", "payments_fintech": "XLF",
    "energy_complex": "XLE", "defensives": "XLP", "travel": "XLY", "retail": "XLY",
    "ai_semiconductors": "SMH", "semicap_equipment": "SMH", "memory_storage": "SMH",
    "data_center_power": "XLI", "nuclear_power": "XLU",
}

# Fallback ETF when the proxy ETF has no sector_central row (GICS SPDRs only).
# Twin of engine/theme_scoring._CONVICTION_ETF_FALLBACK — keep in sync.
# Pre-registered-arbitrary (MLC-W2b; frozen): semis inherit Technology (XLK).
_CONVICTION_ETF_FALLBACK_INLINE: dict[str, str] = {
    "SMH": "XLK",  # pre-registered-arbitrary (MLC-W2b; frozen): semis inherit Technology
}

# RS momentum.lead -> signed tier for sector rows (MLC-W2b-2; frozen — no tuning on observed cases).
# Deliberately narrower ±1 range: RS lead is a coarser read than conviction.
# Pre-registered-arbitrary (MLC-W2b-2; frozen — no tuning on observed cases).
_RS_LEAD_TIER: dict[str, int] = {
    "leading": +1,
    "mid-pack": 0,
    "lagging": -1,
}


def _sector_proxy_map() -> dict[str, str]:
    """Return basket_id -> SPDR ETF; prefer the live engine map, fall back to inline."""
    try:
        from engine.theme_scoring import _SECTOR_PROXY  # type: ignore[import]
        return dict(_SECTOR_PROXY)
    except Exception:  # noqa: BLE001 — test isolation / import not available
        return dict(_SECTOR_PROXY_INLINE)


def _conviction_etf_fallback_map() -> dict[str, str]:
    """Return proxy-ETF -> fallback-ETF; prefer engine map, fall back to inline.

    Twin of engine/theme_scoring._CONVICTION_ETF_FALLBACK — do NOT import from there
    (build_stance_matrix must stay importable without the engine package).
    """
    try:
        from engine.theme_scoring import _CONVICTION_ETF_FALLBACK  # type: ignore[import]
        return dict(_CONVICTION_ETF_FALLBACK)
    except Exception:  # noqa: BLE001 — test isolation
        return dict(_CONVICTION_ETF_FALLBACK_INLINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | list | None:
    """Return parsed JSON or None on any error."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("build_stance_matrix: cannot read %s: %s", path, exc)
        return None


def _freshness_ok(as_of_str: str | None, max_days: int = 5) -> bool:
    """True if as_of_str is a valid ISO date no older than max_days calendar days."""
    if not as_of_str:
        return False
    try:
        d = date.fromisoformat(str(as_of_str)[:10])
        return (date.today() - d).days <= max_days
    except Exception:  # noqa: BLE001
        return False


def _agreement(spread: int | None) -> str | None:
    if spread is None:
        return None
    if spread <= 1:
        return "aligned"
    if spread == 2:
        return "mixed"
    return "split"


def _build_tip(verdicts: dict[str, dict]) -> tuple[str, str]:
    """Build label:value receipt strings for data-tip-en / data-tip-zh."""
    label_map_en = {
        "sector": "Sector",
        "theme": "Theme",
        "confluence": "Setup",
        "allocation": "Allocation",
        "m7c": "Mag-7",
    }
    label_map_zh = {
        "sector": "板块",
        "theme": "主题",
        "confluence": "配置",
        "allocation": "持仓",
        "m7c": "Mag-7",
    }
    # raw value -> display label (English)
    raw_en: dict[str, dict[str, str]] = {
        "sector": {
            "Accumulate": "Accumulate", "Constructive": "Constructive",
            "Neutral": "Neutral", "Cautious": "Cautious", "Reduce": "Reduce",
        },
        "theme": {
            "enter": "Enter", "accumulate": "Accumulate", "hold": "Hold",
            "trim": "Trim", "avoid": "Avoid",
        },
        "confluence": {
            "entry_now": "entry now", "forming": "forming", "tailwind": "tailwind",
            "neutral": "neutral", "late": "late", "headwind": "headwind",
        },
        "allocation": {"held": "held", "not_held": "not held"},
        "m7c": {
            "running_broad": "running broad", "running_narrow": "running narrow",
            "turning_up": "turning up", "cooling": "cooling",
            "rolling_over": "rolling over", "down": "down",
        },
    }
    raw_zh: dict[str, dict[str, str]] = {
        "sector": {
            "Accumulate": "积极配置", "Constructive": "建设性",
            "Neutral": "中性", "Cautious": "谨慎", "Reduce": "减配",
        },
        "theme": {
            "enter": "建仓", "accumulate": "加仓", "hold": "持有",
            "trim": "减仓", "avoid": "回避",
        },
        "confluence": {
            "entry_now": "立即入场", "forming": "成型中", "tailwind": "顺风",
            "neutral": "中性", "late": "偏晚", "headwind": "逆风",
        },
        "allocation": {"held": "持有中", "not_held": "未持有"},
        "m7c": {
            "running_broad": "广泛上行", "running_narrow": "窄幅上行",
            "turning_up": "企稳向上", "cooling": "降温",
            "rolling_over": "走软", "down": "下行",
        },
    }
    parts_en: list[str] = []
    parts_zh: list[str] = []
    for organ in ("sector", "theme", "confluence", "allocation", "m7c"):
        v = verdicts.get(organ)
        if not v:
            continue
        raw = v.get("raw")
        if raw is None:
            continue
        lbl_en = label_map_en.get(organ, organ)
        lbl_zh = label_map_zh.get(organ, organ)
        val_en = raw_en.get(organ, {}).get(str(raw), str(raw))
        val_zh = raw_zh.get(organ, {}).get(str(raw), str(raw))
        parts_en.append(f"{lbl_en}: {val_en}")
        parts_zh.append(f"{lbl_zh}：{val_zh}")
    return " · ".join(parts_en), " · ".join(parts_zh)


def _round_half_away_from_zero(x: float) -> int:
    """Round a float to int, rounding halves away from zero (not banker's rounding).

    Python's built-in round() uses banker's rounding (round-half-to-even), which
    would map 0.5 → 0 and -0.5 → 0. For the sector baskets-median verdict we want
    conventional half-away-from-zero: 0.5 → 1, -0.5 → -1.
    Rounding rule: pre-registered-arbitrary (MLC-W2b-2; frozen — no tuning on observed cases).
    """
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def _build_sector_tip(conviction_raw: str | None, rs_raw: str | None,
                      baskets_tier: int | None, n_members: int) -> tuple[str, str]:
    """Build Tier-2 receipt strings for sector row data-tip-en / data-tip-zh.

    Format mirrors basket rows: label:value pairs separated by ' · '.
    ZH conviction labels sourced from engine/sector_central.TIERS (canonical).
    ZH RS labels sourced from _leadership_board.html.j2 rs_word_zh macro.
    Pre-registered-arbitrary (MLC-W2b-2; frozen — no tuning on observed cases).
    """
    # EN conviction display
    conv_en_map = {
        "Accumulate": "Accumulate", "Constructive": "Constructive",
        "Neutral": "Neutral", "Cautious": "Cautious", "Reduce": "Reduce",
    }
    # ZH conviction labels — from engine/sector_central.TIERS (lines 43-49)
    conv_zh_map = {
        "Accumulate": "积极配置", "Constructive": "建设性",
        "Neutral": "中性", "Cautious": "谨慎", "Reduce": "减配",
    }
    # RS lead display — mirrors rs_word_en/rs_word_zh in _leadership_board.html.j2
    rs_en_map = {"leading": "leading", "mid-pack": "mid-pack", "lagging": "lagging"}
    rs_zh_map = {"leading": "领先", "mid-pack": "中游", "lagging": "落后"}
    # Baskets tier → hold/trim/enter word (same 0-level map; display only)
    _tier_word_en = {2: "enter", 1: "accumulate", 0: "hold", -1: "trim", -2: "avoid"}
    _tier_word_zh = {2: "建仓", 1: "加仓", 0: "持有", -1: "减仓", -2: "回避"}

    parts_en: list[str] = []
    parts_zh: list[str] = []

    if conviction_raw:
        parts_en.append(f"Conviction: {conv_en_map.get(conviction_raw, conviction_raw)}")
        parts_zh.append(f"评级：{conv_zh_map.get(conviction_raw, conviction_raw)}")
    if rs_raw:
        parts_en.append(f"RS: {rs_en_map.get(rs_raw, rs_raw)}")
        parts_zh.append(f"动量：{rs_zh_map.get(rs_raw, rs_raw)}")
    if baskets_tier is not None:
        bword_en = _tier_word_en.get(baskets_tier, "hold")
        bword_zh = _tier_word_zh.get(baskets_tier, "持有")
        parts_en.append(f"Baskets: {bword_en} (median of {n_members})")
        parts_zh.append(f"篮子：{bword_zh}（{n_members}个中位数）")

    return " · ".join(parts_en), " · ".join(parts_zh)


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build(root: Path | None = None) -> dict:
    """Build the stance matrix and write site/mlcdata/stance_matrix.json.

    Args:
        root: repo root override (for test isolation). Defaults to repo root
              (two directories above this file).

    Returns:
        The emitted payload dict.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent

    site = root / "site"
    data_root = root / "data"

    today_str = date.today().isoformat()

    # ── 1. Load input artifacts ──────────────────────────────────────────────

    # theme_intel (baskets.json)
    baskets_doc = _read_json(site / "basketdata" / "baskets.json") or {}
    theme_intel = baskets_doc.get("theme_intel") or {}
    ti_as_of = theme_intel.get("as_of")
    themes_list: list[dict] = theme_intel.get("themes") or []

    # basket_confluence — freshness gate: stale (>5d) → organ omitted (honest null)
    confluence_doc = _read_json(site / "marketdata" / "basket_confluence.json") or {}
    confluence_as_of = confluence_doc.get("as_of") or confluence_doc.get("generated_utc")
    _confluence_fresh = _freshness_ok(str(confluence_as_of) if confluence_as_of else None)
    confluence_by_id: dict[str, dict] = {}
    if _confluence_fresh:
        confluence_by_id = {
            b["basket_id"]: b for b in (confluence_doc.get("baskets") or [])
            if b.get("basket_id")
        }
    else:
        log.debug("build_stance_matrix: confluence stale or absent (as_of=%s) — organ omitted",
                  confluence_as_of)

    # sector_central — T-1 (last committed, RLT-R6 semantics)
    # Freshness gate: stale (>5d) → sector organ omitted for all rows (honest null)
    sc_doc = _read_json(site / "sectordata" / "sector_central.json") or {}
    sc_as_of = sc_doc.get("as_of")
    _sc_fresh = _freshness_ok(sc_as_of)
    # Build ETF ticker -> conviction label_en map (only when fresh)
    _sc_by_etf: dict[str, dict] = {}
    if _sc_fresh:
        for _sec in (sc_doc.get("sectors") or []):
            _etf = _sec.get("ticker")
            _conv = _sec.get("conviction") or {}
            if _etf and _conv.get("label_en"):
                _sc_by_etf[_etf] = {
                    "label_en": _conv["label_en"],
                    "label_zh": _conv.get("label_zh") or _conv["label_en"],
                }
    else:
        log.debug("build_stance_matrix: sector_central stale or absent (as_of=%s) — organ omitted",
                  sc_as_of)

    # allocation — freshness gate: stale (>5d) → allocation organ omitted
    alloc_doc = _read_json(site / "allocationdata" / "allocation.json") or {}
    alloc_as_of = alloc_doc.get("as_of")
    _alloc_fresh = _freshness_ok(alloc_as_of)
    held_ids: set[str] = set()
    if _alloc_fresh:
        held_ids = {
            w["id"] for w in ((alloc_doc.get("allocation") or {}).get("weights") or [])
            if w.get("id")
        }
    else:
        log.debug("build_stance_matrix: allocation stale or absent (as_of=%s) — organ omitted",
                  alloc_as_of)

    # mag7 trend_state — freshness gate: stale (>5d) → m7c organ omitted
    # Note: mag7 as_of is routinely 1 calendar day behind build time; 5d threshold passes that.
    mag7_doc = _read_json(data_root / "mag7_regime" / "latest.json") or {}
    mag7_as_of = mag7_doc.get("as_of")
    _mag7_fresh = _freshness_ok(mag7_as_of)
    mag7_trend_state: str | None = mag7_doc.get("trend_state") if _mag7_fresh else None
    if not _mag7_fresh:
        log.debug("build_stance_matrix: mag7 stale or absent (as_of=%s) — m7c organ omitted",
                  mag7_as_of)

    # sector proxy map
    sector_proxy = _sector_proxy_map()
    conviction_etf_fallback = _conviction_etf_fallback_map()

    # ── 2. Build rows ────────────────────────────────────────────────────────
    rows: list[dict] = []
    for th in themes_list:
        bid = th.get("id") or ""
        if not bid:
            continue

        verdicts: dict[str, dict[str, Any]] = {}

        # — sector organ —
        # Two-step lookup: try direct proxy ETF first, fall back via conviction_etf_fallback
        # (e.g. SMH -> XLK) when sector_central only carries GICS SPDRs, not SMH.
        # Twin of the same two-step in engine/theme_scoring._apply_sector_conflict_demotion.
        etf = sector_proxy.get(bid)
        sc_verdict = _sc_by_etf.get(etf) if etf else None
        if sc_verdict is None and etf:
            fallback_etf = conviction_etf_fallback.get(etf)
            sc_verdict = _sc_by_etf.get(fallback_etf) if fallback_etf else None
        if sc_verdict:
            raw_label = sc_verdict["label_en"]
            tier_val = _SECTOR_TIER.get(raw_label)
            if tier_val is not None:
                v: dict[str, Any] = {"raw": raw_label, "tier": tier_val}
                if sc_as_of:
                    v["as_of"] = sc_as_of
                verdicts["sector"] = v

        # — theme reco organ —
        reco = th.get("reco") or ""
        reco_tier = _RECO_TIER.get(reco)
        if reco_tier is not None:
            verdicts["theme"] = {"raw": reco, "tier": reco_tier}

        # — confluence class organ —
        cf_row = confluence_by_id.get(bid)
        cf_class = (cf_row.get("class") or "") if cf_row else ""
        cf_tier = _CONFLUENCE_TIER.get(cf_class)
        if cf_tier is not None:
            verdicts["confluence"] = {"raw": cf_class, "tier": cf_tier}

        # — allocation organ — absence is weak evidence, NEVER negative;
        # omitted entirely when source is stale (honest null vs. fake "not_held" signal)
        if _alloc_fresh:
            alloc_raw = "held" if bid in held_ids else "not_held"
            alloc_tier = 1 if bid in held_ids else 0
            verdicts["allocation"] = {"raw": alloc_raw, "tier": alloc_tier}

        # — m7c organ (mag7 basket only) —
        if bid == "mag7" and mag7_trend_state and mag7_trend_state in _M7C_TIER:
            verdicts["m7c"] = {"raw": mag7_trend_state, "tier": _M7C_TIER[mag7_trend_state]}

        # — aggregate —
        n_reads = len(verdicts)
        tiers = [v["tier"] for v in verdicts.values()]
        if len(tiers) >= 2:
            spread: int | None = max(tiers) - min(tiers)
        else:
            spread = None
        agreement = _agreement(spread)

        tip_en, tip_zh = _build_tip(verdicts)

        row: dict[str, Any] = {
            "id": bid,
            "name": th.get("name") or th.get("name_en") or bid,
            "name_zh": th.get("name_zh") or "",
            "sector_etf": etf,
            "verdicts": verdicts,
            "n_reads": n_reads,
            "spread": spread,
            "agreement": agreement,
            "tip_en": tip_en,
            "tip_zh": tip_zh,
        }
        rows.append(row)

    # ── 2b. Build sector-grain rows (MLC-W2b-2 additive) ────────────────────
    # Derives entirely from already-loaded artifacts: sector_central (_sc_by_etf,
    # sc_doc) and the per-basket rows built above. Zero new input reads.
    # Only emitted when sector_central is fresh (same gate as the basket-side
    # sector organ: _sc_fresh must be True).
    sector_rows: list[dict] = []
    if _sc_fresh:
        # Build reverse map: ETF -> list of basket theme-verdict tiers
        # (includes the SMH-proxied baskets via conviction_etf_fallback: they
        # count toward XLK's member set — same twin as the basket-side two-step).
        _etf_basket_tiers: dict[str, list[int]] = {}
        for _brow in rows:
            _bid = _brow.get("id") or ""
            _raw_etf = sector_proxy.get(_bid)  # direct proxy (may be SMH)
            # resolve to GICS SPDR ETF via fallback (e.g. SMH -> XLK)
            _resolved_etf = conviction_etf_fallback.get(_raw_etf, _raw_etf) if _raw_etf else None
            if not _resolved_etf:
                continue
            _theme_verdict = _brow.get("verdicts", {}).get("theme")
            if _theme_verdict is not None:
                _etf_basket_tiers.setdefault(_resolved_etf, []).append(
                    _theme_verdict["tier"]
                )

        for _sec in (sc_doc.get("sectors") or []):
            _etf = _sec.get("ticker") or ""
            if not _etf:
                continue
            _conv_block = _sec.get("conviction") or {}
            _conv_label = _conv_block.get("label_en") or ""
            _conv_zh = _conv_block.get("label_zh") or _conv_label
            _mom = _sec.get("momentum") or {}
            _lead = _mom.get("lead")  # "leading" / "mid-pack" / "lagging"
            _name = _sec.get("name") or _etf
            _name_zh = _sec.get("name_zh") or ""

            sec_verdicts: dict[str, dict[str, Any]] = {}

            # — conviction verdict (reuses same map and constants as basket-side) —
            _conv_tier = _SECTOR_TIER.get(_conv_label)
            if _conv_tier is not None:
                _sv: dict[str, Any] = {"raw": _conv_label, "tier": _conv_tier}
                if sc_as_of:
                    _sv["as_of"] = sc_as_of
                sec_verdicts["conviction"] = _sv

            # — rs verdict (new narrower ±1 map; pre-registered-arbitrary MLC-W2b-2) —
            _rs_tier = _RS_LEAD_TIER.get(_lead) if _lead else None
            if _rs_tier is not None:
                sec_verdicts["rs"] = {"raw": _lead, "tier": _rs_tier}

            # — baskets verdict (median of member-basket theme tiers) —
            # Emitted only when ≥1 member basket carries a theme verdict.
            # Rounding: half-away-from-zero (see _round_half_away_from_zero docstring).
            # Pre-registered-arbitrary (MLC-W2b-2; frozen — no tuning on observed cases).
            _member_tiers = _etf_basket_tiers.get(_etf) or []
            _n_members = len(_member_tiers)
            _baskets_tier: int | None = None
            if _n_members >= 1:
                _median_raw = statistics.median(_member_tiers)
                _baskets_tier = _round_half_away_from_zero(float(_median_raw))
                sec_verdicts["baskets"] = {"raw": _baskets_tier, "tier": _baskets_tier,
                                           "n_members": _n_members}

            # — aggregate spread / agreement —
            sec_n_reads = len(sec_verdicts)
            sec_tiers = [sv["tier"] for sv in sec_verdicts.values()]
            if len(sec_tiers) >= 2:
                sec_spread: int | None = max(sec_tiers) - min(sec_tiers)
            else:
                sec_spread = None
            sec_agreement = _agreement(sec_spread)

            # — bilingual Tier-2 receipts —
            stip_en, stip_zh = _build_sector_tip(
                _conv_label or None,
                _lead,
                _baskets_tier,
                _n_members,
            )

            sector_rows.append({
                "ticker": _etf,
                "name": _name,
                "name_zh": _name_zh,
                "verdicts": sec_verdicts,
                "n_reads": sec_n_reads,
                "spread": sec_spread,
                "agreement": sec_agreement,
                "tip_en": stip_en,
                "tip_zh": stip_zh,
            })

    # ── 3. Assemble payload ──────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "schema": "mlc.stance_matrix.v1",
        "as_of": today_str,
        "inputs": {
            "theme_intel": ti_as_of,
            "sector_central": sc_as_of,
            "basket_confluence": str(confluence_as_of) if confluence_as_of else None,
            "allocation": alloc_as_of,
            "mag7": mag7_as_of,
        },
        "rows": rows,
        "sectors": sector_rows,  # MLC-W2b-2 additive; empty list when sector_central stale/absent
    }

    # ── 4. Write ─────────────────────────────────────────────────────────────
    out_dir = site / "mlcdata"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "stance_matrix.json"
        out_path.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("build_stance_matrix: wrote %s (%d rows)", out_path, len(rows))
    except Exception as exc:  # noqa: BLE001 — additive, never fatal
        log.error("build_stance_matrix: write failed: %s", exc)

    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="MLC W2b stance-matrix builder")
    ap.add_argument("--root", type=Path, default=None,
                    help="Repo root override (for testing)")
    args = ap.parse_args()
    try:
        result = build(root=args.root)
        log.info("build_stance_matrix: done, %d basket rows, %d sector rows",
                 len(result.get("rows") or []), len(result.get("sectors") or []))
    except Exception as exc:  # noqa: BLE001 — must never raise from main()
        log.error("build_stance_matrix: unexpected error: %s", exc, exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
