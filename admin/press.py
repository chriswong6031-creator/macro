"""admin/press.py — Media Network W1 (D14) press-engine admin inspector.

Read-only, fail-soft (mirrors admin/chronicle.py conventions exactly): the
single public function returns {"ok": True, ...} or {"ok": False, "error": ...}.
Never writes.  Reads only the committed data/press/ store and config/press.yml.

Single entry point: overview(root=None) -> dict, exposing

  kill_switch      PRESS_PUBLISH_ENABLED as this process sees it, plus the
                   plain-words statement of what that means.  The repo VARIABLE
                   is the source of truth; the panel reports the env it can see
                   and says so rather than implying it knows the repo setting.
  cadence          per-desk config: publication, byline, targets, word budget
  thresholds       the validator floors/ceilings actually in force
  staged           passing staged drafts with per-validator pass/fail
  quarantine       quarantined slots with their reasons
  ledger_tail      the last rows of data/press/published.jsonl
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent

_CONFIG_REL = Path("config/press.yml")
_STAGING_REL = Path("data/press/staging")
_LEDGER_REL = Path("data/press/published.jsonl")

_KILL_SWITCH_ENV = "PRESS_PUBLISH_ENABLED"

_ACCRUING_NOTE = (
    "data/press/published.jsonl is empty — the press lane has published nothing "
    "yet.  W1 ships dark: nothing publishes until the PRESS_PUBLISH_ENABLED repo "
    "variable is set to 'true'."
)

_N_LEDGER_TAIL = 20


def _default_root() -> Path:
    """Repo root for panel reads when no explicit ``root=`` is passed.

    Mirrors admin/chronicle.py._default_root(): resolves through admin.paths.ROOT
    so a seeded dev/demo run (MACRO_ADMIN_ROOT=<tmp>) points every panel at the
    fixture tree.  Fail-soft to the package grandparent.
    """
    try:
        from .paths import ROOT  # noqa: PLC0415
        return ROOT
    except Exception:  # noqa: BLE001
        return _HERE.parent


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
        return out
    except Exception:  # noqa: BLE001
        return []


def _read_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _kill_switch() -> dict:
    # Match the WORKFLOW's semantics exactly, or the panel lies about the state
    # of the lane. `.github/workflows/press-publish.yml` gates on the expression
    # `vars.PRESS_PUBLISH_ENABLED == 'true'`; GitHub's `==` ignores case but does
    # NOT trim, so "TRUE" arms the lane and "true " does not. Stripping here
    # would report ARMED for a value the workflow reads as dark.
    raw = os.environ.get(_KILL_SWITCH_ENV) or ""
    armed = raw.lower() == "true"
    return {
        "env_var": _KILL_SWITCH_ENV,
        "value": raw or None,
        "armed": armed,
        "state": "ARMED — the press workflow publishes" if armed
                 else "DARK — every press-publish job is skipped",
        "note": ("The repo VARIABLE is the source of truth; this panel reports "
                 "the value visible to the admin process, which is unset unless "
                 "the console was started with it."),
    }


def _check_summary(report: Any) -> list[dict]:
    """[{name, ok, detail}] for one validator_report — the panel's pass/fail row."""
    if not isinstance(report, dict):
        return []
    return [
        {"name": c.get("name"), "ok": bool(c.get("ok")), "detail": c.get("detail")}
        for c in (report.get("checks") or []) if isinstance(c, dict)
    ]


def _resolved_cap(cfg: dict, desk_cfg: dict, name: str):
    """How many slots this desk may actually plan today.

    The desk's own `cadence_per_day` is only half of a W2R desk's volume; the
    other half is `research_triage.volume`, and the two compose as stricter-of
    with a fail-closed 0.  Delegates to the planner's own resolver rather than
    re-deriving the rule — a panel that computes its own answer is a panel that
    can disagree with the engine.

    Returns None when the resolver is unavailable, which reads as "unknown" in
    the panel rather than as a number nobody computed.
    """
    try:
        from engine.press.desk_planner import _triage_cap  # noqa: PLC0415

        return _triage_cap(cfg, desk_cfg, name=name)
    except Exception as exc:  # noqa: BLE001 — the panel must render regardless
        log.warning("admin.press: resolved cap unavailable for %s: %s", name, exc)
        return None


def overview(root=None) -> dict:
    """Kill-switch + cadence + thresholds + staged/quarantine + ledger tail."""
    repo = Path(root) if root is not None else _default_root()
    try:
        cfg = _read_yaml(repo / _CONFIG_REL)
        validators_cfg = (cfg.get("validators") or {}) if isinstance(cfg, dict) else {}
        desks_cfg = (cfg.get("desks") or {}) if isinstance(cfg, dict) else {}
        pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}

        cadence = [
            {
                "desk": name,
                "publication": d.get("publication"),
                "publication_domain": (pubs.get(d.get("publication")) or {}).get("domain"),
                "byline": d.get("byline"),
                # THE CEILING AND THE RESOLVED CAP ARE DIFFERENT NUMBERS, and
                # the panel now shows both (review M11). A W2R desk's real
                # volume is the STRICTER of its own ceiling and the triage
                # volume knob, so a panel printing only `cadence_per_day` told
                # the operator a dark lane was running at its target rate.
                "per_day": d.get("cadence_per_day"),
                "resolved_per_day": _resolved_cap(cfg, d, name),
                "triage_tier": d.get("triage_tier"),
                "min_per_day": d.get("cadence_min_per_day"),
                "words": f"{d.get('min_words')}–{d.get('max_words')}",
                "model_key": d.get("model_key"),
            }
            for name, d in sorted(desks_cfg.items()) if isinstance(d, dict)
        ]

        thresholds = {
            "paraphrase_max_jaccard": validators_cfg.get("paraphrase_max_jaccard"),
            "our_value_min": validators_cfg.get("our_value_min"),
            "max_quotes": validators_cfg.get("max_quotes"),
            "max_quote_words": validators_cfg.get("max_quote_words"),
            "self_similarity_max_jaccard": validators_cfg.get("self_similarity_max_jaccard"),
            "self_similarity_window_days": validators_cfg.get("self_similarity_window_days"),
            "cutover": cfg.get("cutover") if isinstance(cfg, dict) else None,
        }

        staged: list[dict] = []
        quarantine: list[dict] = []
        run_summary = None
        stage_dir = repo / _STAGING_REL
        if stage_dir.exists():
            for path in sorted(stage_dir.glob("*.json")):
                obj = _read_json(path)
                if not isinstance(obj, dict):
                    continue
                if path.name.startswith("_"):
                    if path.name == "_run_summary.json":
                        run_summary = obj
                    continue
                report = obj.get("validator_report")
                row = {
                    "id": obj.get("id"),
                    "desk": obj.get("desk"),
                    "publication": obj.get("publication"),
                    "as_of": obj.get("as_of"),
                    "staged_at": obj.get("staged_at"),
                    "slug": obj.get("slug") or None,
                    "title": (obj.get("draft") or {}).get("title")
                             if isinstance(obj.get("draft"), dict) else None,
                    "attempts": len(obj.get("attempts") or []),
                    "checks": _check_summary(report),
                    "our_value_share": (report or {}).get("our_value_share")
                                       if isinstance(report, dict) else None,
                    "max_block_jaccard": (report or {}).get("max_block_jaccard")
                                         if isinstance(report, dict) else None,
                    "words": (report or {}).get("words") if isinstance(report, dict) else None,
                }
                if obj.get("status") == "passed":
                    staged.append(row)
                else:
                    row["reason"] = obj.get("quarantine_reason")
                    quarantine.append(row)

        ledger = _read_jsonl(repo / _LEDGER_REL)
        tail = [
            {
                "id": r.get("id"),
                "ts": r.get("ts"),
                "desk": r.get("desk"),
                "publication": r.get("publication"),
                "slug": r.get("slug"),
                "urls": r.get("urls") or [],
                "sources": r.get("sources") or [],
                "our_value_share": (r.get("validator_report") or {}).get("our_value_share")
                                   if isinstance(r.get("validator_report"), dict) else None,
            }
            for r in ledger[-_N_LEDGER_TAIL:]
        ]

        out = {
            "ok": True,
            "kill_switch": _kill_switch(),
            "cadence": cadence,
            "publications": pubs,
            "thresholds": thresholds,
            "staged": staged,
            "quarantine": quarantine,
            "run_summary": run_summary,
            "total_published": len(ledger),
            "ledger_tail": tail,
        }
        if not cfg:
            out["note"] = "config/press.yml not found — press lane is not configured."
        elif not ledger:
            out["note"] = _ACCRUING_NOTE
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("press.overview failed: %s", exc)
        return {"ok": False, "error": str(exc)}
