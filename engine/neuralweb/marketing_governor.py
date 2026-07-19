"""engine.neuralweb.marketing_governor — Marketing NW lobe governor.

Produces TWO committed artifacts (single writer, never-raise):

  A. data/neuralweb/marketing_state.json   (schema marketing.state/v1)
  B. site/neuralwebdata/marketing_lobe.json (schema marketing.lobe/v1, public-safe)

Never-raise contract: all exceptions are caught; best-effort written.

Entry point:
    build_and_write(root=None) -> {"state_path": ..., "lobe_path": ...}

Run as module: python -m engine.neuralweb.marketing_governor
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Artifact ids (must match config/synapse.yml entries)
_ARTIFACT_STATE = "marketing-state"
_ARTIFACT_LOBE = "marketing-lobe"

# Paths relative to repo root
_STATE_PATH = Path("data") / "neuralweb" / "marketing_state.json"
_LOBE_PATH = Path("site") / "neuralwebdata" / "marketing_lobe.json"
# Unregistered — beside seed ledgers, no synapse pin/SIGNAL_BUS churn
_CONTENT_PLAN_PATH = Path("data") / "marketing" / "content_plan.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _public_safe_subset(state: dict) -> dict:
    """Extract the public-safe subset for marketing_lobe.json (spec §4).

    Included: schema, as_of, lobe (id/name/lifecycle_state/mandate),
              north_star (state only, no dollar value),
              departments (id/name/lifecycle_state/wave only),
              waves (id/title/status), channels_priority.

    Excluded: budgets, internal scorecards, desk-account handles, credentials.
    """
    return {
        "schema": "marketing.lobe/v1",
        "as_of": state.get("as_of", ""),
        "lobe": {
            "id": state.get("lobe", {}).get("id", "marketing"),
            "name": state.get("lobe", {}).get("name", "Marketing"),
            "lifecycle_state": state.get("lobe", {}).get("lifecycle_state", "chartered"),
            "mandate": state.get("lobe", {}).get("mandate", {}),
        },
        "north_star": {
            "state": state.get("north_star", {}).get("state", "accruing"),
        },
        "departments": [
            {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "lifecycle_state": d.get("lifecycle_state", "chartered"),
                "wave": d.get("wave", 0),
            }
            for d in state.get("departments", [])
        ],
        "waves": [
            {
                "id": w.get("id", ""),
                "title": w.get("title", ""),
                "status": w.get("status", "planned"),
            }
            for w in state.get("waves", [])
        ],
        "channels_priority": state.get("channels_priority", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Governor
# ─────────────────────────────────────────────────────────────────────────────

def _build_content_plan(r: Path, cfg: dict) -> dict:
    """Build content plan — fail-soft to a minimal honest plan if unavailable."""
    try:
        from engine.marketing.content_studio import content_plan as _content_plan
        from engine.marketing.chart_render import load_closes

        # Load Prophet plans
        plans: list[dict] = []
        prophet_path = r / "site" / "prophet" / "index.json"
        if prophet_path.exists():
            import json as _json
            _idx = _json.loads(prophet_path.read_text(encoding="utf-8"))
            plans = _idx.get("plans", []) or []

        def closes_loader(ticker: str):  # type: ignore[return]
            return load_closes(ticker, r, n=90)

        return _content_plan(cfg=cfg, plans=plans, closes_loader=closes_loader, root=r)

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing_governor: content_plan build failed: %s", exc)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "schema_version": 1,
            "produced_by": "engine/neuralweb/marketing_governor.py",
            "produced_at": now_str,
            "tier": "display",
            "schema": "marketing.content/v1",
            "as_of": now_str[:10],
            "source": {"prophet_plans": 0, "plans_with_charts": 0, "note": f"Build failed: {exc}"},
            "content_types": [],
            "accounts": [],
            "featured_charts": [],
            "distinctness": {"max_similarity": 0.0, "flags": 0, "note": "unavailable"},
            "summary": {"total_posts": 0, "signal_posts": 0, "charts": 0, "accounts": 0},
        }


def build_and_write(root: Path | str | None = None) -> dict[str, Any]:
    """Build marketing state and write both artifacts.

    Returns {"state_path": str, "lobe_path": str, "content_plan_path": str} on success.
    Never raises — returns error key on failure.
    """
    result: dict[str, Any] = {"state_path": None, "lobe_path": None, "content_plan_path": None}
    try:
        r = _repo_root(root)

        # Load config once
        from engine.marketing.state import _load_cfg
        cfg = _load_cfg(r)

        # Build + write content plan FIRST (state.py reads it for the summary block)
        content_plan_obj = _build_content_plan(r, cfg)
        content_plan_path = r / _CONTENT_PLAN_PATH
        _write_json_atomic(content_plan_path, content_plan_obj)
        result["content_plan_path"] = str(content_plan_path)
        log.info("marketing_governor: wrote %s", content_plan_path)

        # Build static short-link pages (Funnel W1a / D07)
        try:
            from engine.marketing.links import build_short_link_pages as _build_short_link_pages
            _sl = _build_short_link_pages(content_plan_obj, r / "site" / "go", cfg=cfg)
            result["short_link_pages"] = _sl["pages_written"]
            log.info("marketing_governor: wrote %d short-link pages", _sl["pages_written"])
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing_governor: short-link pages failed: %s", exc)

        # Outbox: emit today's D1 items if the feature flag is set.
        try:
            if os.environ.get("MARKETING_OUTBOX_ENABLED") == "1":
                from engine.marketing.outbox import emit_from_content_plan
                outbox_summary = emit_from_content_plan(content_plan_obj, root=r, cfg=cfg)
                result["outbox"] = outbox_summary
                log.info("marketing_governor: outbox emit summary: %s", outbox_summary)
            else:
                log.info(
                    "marketing_governor: outbox emit skipped (MARKETING_OUTBOX_ENABLED not set)"
                )
        except Exception as _exc:  # noqa: BLE001
            log.warning("marketing_governor: outbox emit failed: %s", _exc)

        # Build state
        from engine.marketing.state import build_state
        state = build_state(root=r, cfg=cfg)

        # Stamp with envelope
        try:
            from engine.neuralweb.envelope import stamp
            state = stamp(state, artifact_id=_ARTIFACT_STATE)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing_governor: envelope stamp failed: %s", exc)
            # Add minimal envelope keys manually so artifact is still valid
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            state.setdefault("schema_version", 1)
            state.setdefault("produced_by", "engine/neuralweb/marketing_governor.py")
            state.setdefault("produced_at", now_str)
            state.setdefault("inputs_hash", "sha256:unstamped")
            state.setdefault("tier", "display")

        # Write state artifact
        state_path = r / _STATE_PATH
        _write_json_atomic(state_path, state)
        result["state_path"] = str(state_path)
        log.info("marketing_governor: wrote %s", state_path)

        # Build public-safe subset
        lobe = _public_safe_subset(state)

        # Stamp lobe artifact
        try:
            from engine.neuralweb.envelope import stamp
            lobe = stamp(lobe, artifact_id=_ARTIFACT_LOBE)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing_governor: lobe stamp failed: %s", exc)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            lobe.setdefault("schema_version", 1)
            lobe.setdefault("produced_by", "engine/neuralweb/marketing_governor.py")
            lobe.setdefault("produced_at", now_str)
            lobe.setdefault("inputs_hash", "sha256:unstamped")
            lobe.setdefault("tier", "display")

        # Write lobe artifact
        lobe_path = r / _LOBE_PATH
        _write_json_atomic(lobe_path, lobe)
        result["lobe_path"] = str(lobe_path)
        log.info("marketing_governor: wrote %s", lobe_path)

    except Exception as exc:  # noqa: BLE001
        log.warning("marketing_governor: build_and_write failed: %s", exc, exc_info=True)
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Module entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    res = build_and_write()
    if res.get("error"):
        print(f"marketing_governor: ERROR — {res['error']}", file=sys.stderr)
        sys.exit(1)
    print(
        f"marketing_governor: ok — "
        f"state={res.get('state_path')} "
        f"lobe={res.get('lobe_path')} "
        f"content_plan={res.get('content_plan_path')}"
    )
