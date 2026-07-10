"""engine.metabolism.grounding — Machine grounding check (V3 W2, R-V3-5b).

Informational / display-tier — it FLAGS, it NEVER blocks.

validate_grounding(payload, *, root) -> dict
    Extract referenced ids from a payload (structured fields + free-text regex
    sweep), check each against loaded registries, return a dict describing what
    is grounded, ungrounded, or unverified.

Fail-safe semantics (critical):
    - If a registry CANNOT be loaded → that registry is marked unverified; we
      do NOT falsely report ids as grounded.
    - ``ok=True`` always (never blocks) but ``unverified=True`` signals to the
      caller that checks were incomplete.
    - A loaded registry with a missing id → id appears in ``ungrounded``,
      ``ok=False`` (still informational).

All functions: NEVER-RAISE.  No LLM.  No network.  No ``~/``.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Repo root ──────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── Registry loaders ───────────────────────────────────────────────────────────

def _load_known_lobes(root: Path) -> tuple[set[str], bool]:
    """Load known lobe/artifact ids from config/synapse.yml.

    Returns (set_of_ids, loaded_ok).  set_of_ids is empty and loaded_ok=False
    when the file cannot be parsed — the caller must set unverified=True.
    NEVER raises.
    """
    try:
        p = root / "config" / "synapse.yml"
        if not p.exists():
            log.warning("grounding._load_known_lobes: synapse.yml not found at %s", p)
            return set(), False

        text = p.read_text(encoding="utf-8")
        ids: set[str] = set()

        # Parse the artifacts section: top-level keys under "artifacts:" that are
        # not sub-keys (i.e. lines like "  artifact-name:").
        # synapse.yml uses 2-space-indented artifact names as the dict keys.
        # Pattern: line starting with exactly two spaces then a word-char-or-hyphen key
        # followed by a colon (not inside a string value).
        in_artifacts = False
        for line in text.splitlines():
            stripped = line.rstrip()
            if stripped == "artifacts:":
                in_artifacts = True
                continue
            if in_artifacts:
                # Stop at a non-indented line that starts a new top-level section
                if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                    break
                # Artifact key: exactly 2-space indent, then identifier, then ":"
                m = re.match(r"^  ([a-zA-Z][a-zA-Z0-9_.-]*)\s*:", stripped)
                if m:
                    ids.add(m.group(1))

        if not ids:
            log.warning(
                "grounding._load_known_lobes: no artifact ids parsed from %s "
                "(may be a YAML parse limitation)", p
            )
            return set(), False

        return ids, True

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._load_known_lobes: %s", exc)
        return set(), False


def _load_known_rulings(root: Path) -> tuple[set[str], bool]:
    """Load known ruling_ids from config/ruling_graph.yml.

    Returns (set_of_ruling_ids, loaded_ok).  NEVER raises.
    """
    try:
        p = root / "config" / "ruling_graph.yml"
        if not p.exists():
            log.warning("grounding._load_known_rulings: ruling_graph.yml not found at %s", p)
            return set(), False

        text = p.read_text(encoding="utf-8")
        ids: set[str] = set()

        # Extract ruling_id values from lines like:
        #   - ruling_id: RUL-CL-1
        # or:
        #   - ruling_id: "CYC-U4"
        for m in re.finditer(
            r'ruling_id\s*:\s*["\']?([A-Za-z0-9][-A-Za-z0-9_.]+)["\']?',
            text,
        ):
            ids.add(m.group(1))

        if not ids:
            log.warning("grounding._load_known_rulings: no ruling_ids parsed from %s", p)
            return set(), False

        return ids, True

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._load_known_rulings: %s", exc)
        return set(), False


def _load_known_sensors(root: Path) -> tuple[set[str], bool]:
    """Load known sensor keys from fitness cards and til_fitness.py.

    Best-effort: scans data/metabolism/fitness/*.json for sensor keys.
    If no fitness cards exist yet (Metabolism is paused), returns (empty, False)
    to signal that sensor grounding is unverified rather than falsely clean.
    NEVER raises.
    """
    try:
        fitness_dir = root / "data" / "metabolism" / "fitness"
        if not fitness_dir.exists():
            log.info("grounding._load_known_sensors: fitness dir absent — sensor grounding unverified")
            return set(), False

        keys: set[str] = set()
        found_any_card = False

        for card_path in sorted(fitness_dir.glob("*.json")):
            try:
                card = json.loads(card_path.read_text(encoding="utf-8"))
                sensors = card.get("sensors") or {}
                for k in sensors:
                    if isinstance(k, str):
                        keys.add(k)
                found_any_card = True
            except Exception:  # noqa: BLE001
                continue

        if not found_any_card:
            return set(), False

        return keys, True

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._load_known_sensors: %s", exc)
        return set(), False


# ── Id extraction from payload ─────────────────────────────────────────────────

_RULING_RE = re.compile(r'\b(RUL-CL-\d+|R-V[23]-\d+|NW-RUL-\d+|ESX-RUL-\d+|[A-Z]{2,6}-[A-Z]?\d+)\b')
_LOBE_FIELD_KEYS = {"lobe", "lobe_id", "lobes"}
_RULING_FIELD_KEYS = {"ruling_id", "ruling", "rulings"}
_SENSOR_FIELD_KEYS = {"sensor", "sensor_id", "sensors"}


def _extract_ids(payload: dict | str) -> dict[str, set[str]]:
    """Extract referenced ids from a payload.

    Handles both structured dicts (field-name lookup) and free text
    (regex sweep).

    Returns
    -------
    dict with keys:
        ``lobes``   — set of lobe/artifact id strings referenced
        ``rulings`` — set of ruling_id strings referenced
        ``sensors`` — set of sensor key strings referenced
    NEVER raises.
    """
    lobes: set[str] = set()
    rulings: set[str] = set()
    sensors: set[str] = set()

    try:
        def _walk(obj: Any, depth: int = 0) -> None:
            if depth > 8:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    k_lower = str(k).lower()
                    if k_lower in _LOBE_FIELD_KEYS:
                        if isinstance(v, str):
                            lobes.add(v)
                        elif isinstance(v, list):
                            for item in v:
                                if isinstance(item, str):
                                    lobes.add(item)
                    elif k_lower in _RULING_FIELD_KEYS:
                        if isinstance(v, str):
                            rulings.add(v)
                        elif isinstance(v, list):
                            for item in v:
                                if isinstance(item, str):
                                    rulings.add(item)
                    elif k_lower in _SENSOR_FIELD_KEYS:
                        if isinstance(v, str):
                            sensors.add(v)
                        elif isinstance(v, list):
                            for item in v:
                                if isinstance(item, str):
                                    sensors.add(item)
                    _walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item, depth + 1)

        if isinstance(payload, dict):
            _walk(payload)
            free_text = json.dumps(payload, default=str)
        elif isinstance(payload, str):
            free_text = payload
        else:
            free_text = str(payload)

        # Regex sweep of free text for ruling-id-shaped tokens
        for m in _RULING_RE.finditer(free_text):
            rulings.add(m.group(1))

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._extract_ids: %s", exc)

    return {"lobes": lobes, "rulings": rulings, "sensors": sensors}


# ── Public API ─────────────────────────────────────────────────────────────────

def validate_grounding(
    payload: dict | str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Check whether ids referenced in ``payload`` exist in known registries.

    Parameters
    ----------
    payload:
        The LLM output or structured dict to check.
    root:
        Repo root override for testing.

    Returns
    -------
    dict:
        ``ok``          — bool: True when no ungrounded ids from loaded registries.
                          Always True when everything is unverified (never blocks).
        ``checked``     — int: total number of individual id references checked.
        ``ungrounded``  — list[dict]: each entry has ``type`` and ``id``.
                          Only populated when the registry was successfully loaded.
        ``unverified``  — bool: True if any registry could not be loaded.
                          Callers must surface this as "grounding unverified"
                          rather than "grounding clean".
        ``registry_status`` — dict: per-registry loaded_ok flags for diagnostics.

    NEVER raises.
    """
    try:
        repo = _repo_root(root)

        # Load registries
        known_lobes, lobes_ok = _load_known_lobes(repo)
        known_rulings, rulings_ok = _load_known_rulings(repo)
        known_sensors, sensors_ok = _load_known_sensors(repo)

        unverified = not (lobes_ok and rulings_ok)
        # Note: sensors_ok=False (no fitness cards) is expected when Metabolism is paused;
        # we do NOT count that as unverified for the top-level flag since the
        # spec says "ground only lobes+rulings and document that sensors are unchecked".
        # sensor unverified is tracked separately in registry_status.

        # Extract referenced ids
        refs = _extract_ids(payload)

        ungrounded: list[dict[str, str]] = []
        checked = 0

        # Check lobes
        for lobe_ref in sorted(refs["lobes"]):
            if not lobe_ref:
                continue
            checked += 1
            if lobes_ok and lobe_ref not in known_lobes:
                ungrounded.append({"type": "lobe", "id": lobe_ref})

        # Check rulings
        for ruling_ref in sorted(refs["rulings"]):
            if not ruling_ref:
                continue
            checked += 1
            if rulings_ok and ruling_ref not in known_rulings:
                ungrounded.append({"type": "ruling", "id": ruling_ref})

        # Check sensors — only when we have loaded cards
        for sensor_ref in sorted(refs["sensors"]):
            if not sensor_ref:
                continue
            checked += 1
            if sensors_ok and sensor_ref not in known_sensors:
                ungrounded.append({"type": "sensor", "id": sensor_ref})

        ok = len(ungrounded) == 0  # False when ANY loaded registry found missing id

        return {
            "ok": ok,
            "checked": checked,
            "ungrounded": ungrounded,
            "unverified": unverified,
            "registry_status": {
                "lobes_loaded": lobes_ok,
                "rulings_loaded": rulings_ok,
                "sensors_loaded": sensors_ok,
                "sensors_note": (
                    "sensor grounding unchecked — no fitness cards present"
                    if not sensors_ok
                    else "sensors grounded from fitness cards"
                ),
            },
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding.validate_grounding: %s", exc)
        return {
            "ok": True,   # never blocks — fail open
            "checked": 0,
            "ungrounded": [],
            "unverified": True,
            "registry_status": {
                "lobes_loaded": False,
                "rulings_loaded": False,
                "sensors_loaded": False,
                "error": str(exc),
            },
        }
