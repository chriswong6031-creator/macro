"""BTC Override panel (owner view) — Override-Registry program W3 (N6, owner decisions D2/D3).

Reads the committed owner honesty artifact (data/vector/override_shadow.json, emitted by
scripts.build_vector.build_override_shadow) and serves it to the console's BTC Override tab:
the full payload the subscriber-facing "Proprietary cycle timer" scrub hides — n=3 provenance,
in-sample pivot MAE, amplitude dampening, the discretionary-override status, the ungated
counterfactual, falsifier health WITH evaluability, and the live gated-vs-raw shadow strip.

D2: this payload is OWNER-ONLY — the route sits behind the console's auth like every other
panel; nothing here may leak to subscriber surfaces. D3: the shadow strip is both-sides
framed and carries NO action affordances — this module (and the tab) render numbers only,
never buttons.

Same shape as the other panels (experiments.py): read a committed JSON from the local repo
clone (the VPS pulls main within minutes), add freshness, degrade gracefully when absent.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .paths import DATA

_ARTIFACT = DATA / "vector" / "override_shadow.json"


def _age_hours(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        dt = datetime.strptime(str(stamp)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
    except Exception:  # noqa: BLE001
        return None


def panel() -> dict:
    """The owner honesty payload + freshness. Never raises."""
    try:
        d = json.loads(_ARTIFACT.read_text())
    except FileNotFoundError:
        return {"ok": False,
                "reason": ("No override_shadow.json yet — the macro build emits "
                           "data/vector/override_shadow.json (scripts.build_vector, W3). "
                           "Run a build (or wait for the nightly) to populate it.")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"could not read override_shadow.json: {e}"}
    return {"ok": True, "age_hours": _age_hours(d.get("generated_at")), **d}
