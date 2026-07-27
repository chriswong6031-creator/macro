"""admin/personas.py — Persona Roster admin panel (Persona Network W1, docket D13).

Read-only, fail-soft (mirrors admin/chronicle.py + admin/marketing.py conventions
exactly): the single public function returns {"ok": True, ...} or
{"ok": False, "error": ...}. Never writes, never raises.

Single entry point: roster(root=None) -> dict.

What it joins
-------------
``config/personas/*.yml`` (the spec layer, engine.marketing.personas) LEFT JOIN
``config/marketing.yml`` ``desk_network`` (the account layer, resolved through
engine.marketing.accounts so the operator override file is honoured).

  LIVE        spec + a desk_network entry that is enabled
  CONFIGURED  spec + a desk_network entry that is disabled
  PLANNED     spec only — no account behind it (valid at W1: the trial cohort
              and the publication anchors are specs long before they are handles)

A desk_network account with no spec is equally valid at W1 and is listed
separately rather than hidden, so the two layers can be seen to disagree.

Honest-skeleton columns
-----------------------
Health (masterplan §2 per-account signals) and arm size are W2/W3 deliverables:
every cell reads "no data yet" rather than 0, because a zero would look like a
measurement. The isolation checklist counts the §2 SIX-item list while the spec
carries five slots — "Registration identity (own email + phone)" has no spec
field at W1, so it is shown as unrecorded instead of being quietly dropped to
make a 5/5 look complete.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent

_CONFIG_REL = Path("config/marketing.yml")
_SPEC_DIR_REL = Path("config/personas")

_ABSENT_NOTE = (
    "config/personas/ not found — no persona specs committed yet. "
    "The roster fills in as specs land (Persona Network W1)."
)

#: Masterplan §2 isolation checklist — SIX items, gate for going live. The spec's
#: ``isolation`` block carries five of them; "Registration identity" has no spec
#: field at W1, so its slot is None and it can never read as complete.
_ISOLATION_CHECKLIST: tuple[tuple[str | None, str], ...] = (
    ("profile_id", "Browser profile / fingerprint"),
    ("egress", "Egress IP"),
    (None, "Registration identity (own email + phone)"),
    ("registered_at", "Registration timing (spaced)"),
    ("warmed_through", "Human-paced warm-up"),
    ("rail", "Posting rail (channel / credential)"),
)

#: Masterplan §2 per-account health signals. W2 ships the monitor that fills them.
_HEALTH_SIGNALS: tuple[str, ...] = (
    "Reach vs own baseline",
    "Warning / label events",
    "Failed-post rate",
    "Follower-quality shift",
)

_NO_DATA = "no data yet"


def _default_root() -> Path:
    """Repo root for panel reads when no explicit ``root=`` is passed.

    Mirrors admin/chronicle.py._default_root(): resolves through admin.paths.ROOT
    so a seeded dev/demo run (MACRO_ADMIN_ROOT=<tmp>) points every panel at the
    fixture tree. Fail-soft to the package grandparent if paths can't be imported.
    """
    try:
        from .paths import ROOT  # noqa: PLC0415
        return ROOT
    except Exception:  # noqa: BLE001
        return _HERE.parent


def _read_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        return {}


def _pct(value: Any) -> str:
    """0.015 -> '1.5%'. Non-numeric falls through as an em dash."""
    try:
        return f"{float(value) * 100:g}%"
    except (TypeError, ValueError):
        return "—"


def _cadence_compact(cadence: dict) -> str:
    """'3/d · 110m+~20m · wknd light' — the whole posting profile in one cell."""
    try:
        return (
            f"{cadence['posts_per_day']}/d · "
            f"{cadence['min_spacing_min']}m+~{cadence['jitter_min']}m · "
            f"wknd {cadence['weekend_shape']}"
        )
    except (KeyError, TypeError):
        return "—"


def _isolation_block(isolation: dict) -> dict:
    """Six-item §2 checklist: per-item state plus the 'n/6' headline."""
    items = []
    done = 0
    for field, label in _ISOLATION_CHECKLIST:
        if field is None:
            items.append({"label": label, "done": False, "value": None,
                          "note": "no spec field at W1"})
            continue
        value = (isolation or {}).get(field)
        ok = bool(value)
        done += 1 if ok else 0
        items.append({"label": label, "done": ok, "value": value,
                      "note": None if ok else "not recorded"})
    total = len(_ISOLATION_CHECKLIST)
    return {"done": done, "total": total, "label": f"{done}/{total}", "items": items}


def _scorecard_block(scorecard: dict) -> dict:
    """Pre-registered gates, printed so their power is legible (masterplan §3)."""
    promote = (scorecard or {}).get("promote_after") or {}
    kill = (scorecard or {}).get("kill_after") or {}
    floor = (scorecard or {}).get("min_impressions")
    return {
        "min_impressions": floor,
        "min_impressions_label": f"{floor:,}" if isinstance(floor, int) else "—",
        "promote_label": (
            f"promote: {promote.get('weeks', '—')}w · "
            f"ER CI-lower > {_pct(promote.get('engagement_rate_ci_lower_above'))}"
        ),
        "kill_label": (
            f"kill: {kill.get('weeks', '—')}w · "
            f"ER CI-upper < {_pct(kill.get('engagement_rate_ci_upper_below'))}"
        ),
        "arm_size_label": "arm size: n/a until live (W4 report card)",
        "alpha_note": (scorecard or {}).get("alpha_note") or "",
    }


def _health_block() -> dict:
    """W2 deliverable. Every signal reads 'no data yet' — never a misleading 0."""
    return {
        "state": _NO_DATA,
        "signals": [{"label": s, "value": None, "note": _NO_DATA} for s in _HEALTH_SIGNALS],
    }


def _status(provisioned: bool, enabled: bool) -> str:
    if not provisioned:
        return "PLANNED"
    return "LIVE" if enabled else "CONFIGURED"


def roster(root=None) -> dict:
    """Every committed persona spec, joined to desk_network liveness.

    Returns ok:True with an honest empty state (never ok:False) when
    config/personas/ has not been created yet. An individual spec that fails
    validation becomes an error ROW — one bad file must not blank the panel.
    """
    repo = Path(root) if root is not None else _default_root()
    try:
        from engine.marketing import personas as _personas  # noqa: PLC0415
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        cfg = _read_yaml(repo / _CONFIG_REL)
        accounts = {
            str(a.get("id", "")): a for a in effective_accounts(cfg, repo)
        }

        spec_dir = repo / _SPEC_DIR_REL
        paths = _personas.spec_paths(repo)
        if not spec_dir.is_dir() or not paths:
            return {
                "ok": True,
                "note": _ABSENT_NOTE if not spec_dir.is_dir() else
                        "config/personas/ is empty — no persona specs committed yet.",
                "personas": [],
                "counts": {"total": 0, "live": 0, "configured": 0, "planned": 0, "invalid": 0},
                "accounts_without_spec": sorted(i for i in accounts if i),
                "isolation_items": [label for _f, label in _ISOLATION_CHECKLIST],
                "health_signals": list(_HEALTH_SIGNALS),
            }

        rows: list[dict] = []
        for path in paths:
            spec, errors = _personas.load_spec(path)
            if errors:
                rows.append({
                    "ok": False,
                    "id": path.stem,
                    "source": path.name,
                    "errors": errors,
                    "status": "INVALID",
                })
                continue
            acct = accounts.get(spec.id)
            provisioned = acct is not None
            enabled = bool(acct.get("enabled")) if provisioned else False
            rows.append({
                "ok": True,
                "id": spec.id,
                "source": path.name,
                "persona_kind": spec.persona_kind,
                "archetype": spec.archetype,
                "voice": spec.voice,
                "beat": spec.beat,
                "pipeline": spec.pipeline,
                "model_tier": spec.model_tier,
                "zh": bool(spec.voice_codex.get("zh")),
                "emoji_policy": spec.voice_codex.get("emoji_policy"),
                "cadence": dict(spec.cadence),
                "cadence_label": _cadence_compact(spec.cadence),
                "isolation": _isolation_block(spec.isolation),
                "health": _health_block(),
                "scorecard": _scorecard_block(spec.scorecard),
                "memory": spec.memory,
                "context_packs": dict(spec.context_packs),
                "provisioned": provisioned,
                "enabled": enabled,
                "status": _status(provisioned, enabled),
            })

        counts = {
            "total": len(rows),
            "live": sum(1 for r in rows if r.get("status") == "LIVE"),
            "configured": sum(1 for r in rows if r.get("status") == "CONFIGURED"),
            "planned": sum(1 for r in rows if r.get("status") == "PLANNED"),
            "invalid": sum(1 for r in rows if not r.get("ok")),
        }
        spec_ids = {r["id"] for r in rows}
        return {
            "ok": True,
            "personas": rows,
            "counts": counts,
            "accounts_without_spec": sorted(i for i in accounts if i and i not in spec_ids),
            "isolation_items": [label for _f, label in _ISOLATION_CHECKLIST],
            "health_signals": list(_HEALTH_SIGNALS),
        }
    except Exception as exc:  # noqa: BLE001 — fail-soft: a panel never 500s
        log.warning("personas.roster failed: %s", exc)
        return {"ok": False, "error": str(exc)}
