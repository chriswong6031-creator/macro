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

Grounding contract (exact scope — do not overstate):
    LOBES:   Grounded from STRUCTURED fields only — ``lobe``, ``lobe_id``,
             ``lobes`` keys in the payload dict, and ``claims[].lobe`` /
             ``claims[].refs.lobes`` if present.  Free-text lobe mentions are
             NOT grounded (too ambiguous; display-tier only).  A structured lobe
             ref absent from config/synapse.yml artifacts → ``ungrounded``.
    RULINGS: Grounded from BOTH structured fields (``ruling_id``, ``ruling``,
             ``rulings`` keys) AND free text.  Free-text detection uses a
             prefix-anchored candidate pattern derived at load time from the
             actual ruling ids in config/ruling_graph.yml — only tokens whose
             prefix matches a known ruling prefix are considered candidates, then
             each candidate is membership-checked against the full id set.  A
             known-prefix token that is NOT a real ruling id → ``ungrounded``.
             Tokens without a known ruling prefix (tickers, macro vars, etc.) are
             NOT treated as ruling references.
    SENSORS: Grounded from structured fields only (``sensor``, ``sensor_id``,
             ``sensors`` keys).  Requires fitness cards in
             data/metabolism/fitness/; absent → sensors_ok=False (unverified for
             sensors, not counted in top-level unverified flag).

All functions: NEVER-RAISE.  No LLM.  No network.  No ``~/``.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# ── Repo root ──────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── Registry loaders ───────────────────────────────────────────────────────────

def _load_known_lobes(root: Path) -> tuple[set[str], bool]:
    """Load known lobe/artifact ids from config/synapse.yml via yaml.safe_load.

    Returns (set_of_ids, loaded_ok).  set_of_ids is empty and loaded_ok=False
    when the file cannot be parsed — the caller must set unverified=True.
    NEVER raises.
    """
    try:
        p = root / "config" / "synapse.yml"
        if not p.exists():
            log.warning("grounding._load_known_lobes: synapse.yml not found at %s", p)
            return set(), False

        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            log.warning("grounding._load_known_lobes: synapse.yml parsed as non-dict")
            return set(), False

        artifacts = data.get("artifacts") or {}
        if not isinstance(artifacts, dict):
            log.warning("grounding._load_known_lobes: artifacts block not a dict in %s", p)
            return set(), False

        ids: set[str] = set(str(k) for k in artifacts.keys())

        if not ids:
            log.warning("grounding._load_known_lobes: no artifact ids found in %s", p)
            return set(), False

        return ids, True

    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._load_known_lobes: %s", exc)
        return set(), False


def _build_ruling_candidate_re(known_rulings: set[str]) -> re.Pattern[str] | None:
    """Build a prefix-anchored regex to detect ruling-id candidates in free text.

    Strategy: extract the alpha prefix of each ruling id (everything before the
    first digit, e.g. ``RUL-CL-1`` → ``RUL-CL-``, ``DT-R11a`` → ``DT-R``).
    Purely alpha ids (no digits, e.g. ``CONST-ARM``) are matched verbatim.
    The returned pattern finds CANDIDATE tokens; the caller must then
    membership-check each candidate against the full ``known_rulings`` set.
    Returns None only if ``known_rulings`` is empty.  NEVER raises.
    """
    if not known_rulings:
        return None

    try:
        prefixes: set[str] = set()
        pure_alpha: set[str] = set()
        for rid in known_rulings:
            m = re.search(r"\d", rid)
            if m:
                prefixes.add(rid[: m.start()])
            else:
                pure_alpha.add(rid)

        parts: list[str] = []
        # Prefix pattern: prefix + at least one alphanumeric/hyphen/dot suffix
        if prefixes:
            sorted_pf = sorted(prefixes, key=len, reverse=True)
            pf_alt = "|".join(re.escape(p) for p in sorted_pf)
            parts.append(r"(?:" + pf_alt + r")[A-Za-z0-9][A-Za-z0-9_.-]*")
        # Pure-alpha ids: verbatim match only
        if pure_alpha:
            sorted_pa = sorted(pure_alpha, key=len, reverse=True)
            pa_alt = "|".join(re.escape(x) for x in sorted_pa)
            parts.append(r"(?:" + pa_alt + r")")

        if not parts:
            return None

        pattern = r"\b(?:" + "|".join(parts) + r")\b"
        return re.compile(pattern)
    except Exception as exc:  # noqa: BLE001
        log.warning("grounding._build_ruling_candidate_re: %s", exc)
        return None


def _load_known_rulings(root: Path) -> tuple[set[str], bool]:
    """Load known ruling_ids from config/ruling_graph.yml via yaml.safe_load.

    Returns (set_of_ruling_ids, loaded_ok).  NEVER raises.
    """
    try:
        p = root / "config" / "ruling_graph.yml"
        if not p.exists():
            log.warning("grounding._load_known_rulings: ruling_graph.yml not found at %s", p)
            return set(), False

        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            log.warning("grounding._load_known_rulings: ruling_graph.yml parsed as non-dict")
            return set(), False

        rulings = data.get("rulings") or []
        if not isinstance(rulings, list):
            log.warning("grounding._load_known_rulings: 'rulings' is not a list in %s", p)
            return set(), False

        ids: set[str] = set()
        for item in rulings:
            if isinstance(item, dict):
                rid = item.get("ruling_id")
                if isinstance(rid, str) and rid:
                    ids.add(rid)

        if not ids:
            log.warning("grounding._load_known_rulings: no ruling_ids found in %s", p)
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

_LOBE_FIELD_KEYS = {"lobe", "lobe_id", "lobes"}
_RULING_FIELD_KEYS = {"ruling_id", "ruling", "rulings"}
_SENSOR_FIELD_KEYS = {"sensor", "sensor_id", "sensors"}


def _extract_ids(
    payload: dict | str,
    *,
    known_rulings: set[str],
    ruling_candidate_re: re.Pattern[str] | None,
) -> dict[str, set[str]]:
    """Extract referenced ids from a payload.

    Lobe refs: structured fields ONLY (``lobe``, ``lobe_id``, ``lobes`` keys,
    and ``claims[].lobe`` / ``claims[].refs.lobes`` if present).  Free-text
    lobe mentions are NOT extracted — too ambiguous to parse reliably from prose.

    Ruling refs: structured fields (``ruling_id``, ``ruling``, ``rulings``) AND
    free text.  Free-text detection uses ``ruling_candidate_re``, which is built
    from the actual ruling prefixes in the registry.  Every candidate token is
    membership-checked against ``known_rulings``; only tokens that match a known
    prefix are returned (false positives like tickers are silently dropped
    because they don't share a prefix with any real ruling id).

    Sensor refs: structured fields only (``sensor``, ``sensor_id``, ``sensors``).

    Returns
    -------
    dict with keys:
        ``lobes``   — set of lobe/artifact id strings referenced (structured only)
        ``rulings`` — set of ruling_id candidate strings found (structured + free-text)
        ``sensors`` — set of sensor key strings referenced (structured only)
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

        # Free-text sweep for ruling-id candidates using the prefix-anchored
        # regex derived from the actual registry.  Each matched token is then
        # membership-checked: a prefix-matching but unknown token is passed
        # through (the caller will flag it as ungrounded).  Tokens without a
        # known ruling prefix never match ruling_candidate_re, so tickers /
        # macro variables never enter the ruling candidate set.
        if ruling_candidate_re is not None:
            for m in ruling_candidate_re.finditer(free_text):
                token = m.group(0)
                # Include if it's a real ruling (will pass grounding check) OR
                # if it has a known prefix (will fail grounding check = ungrounded).
                # known_rulings=empty means registry not loaded; skip.
                if known_rulings:
                    rulings.add(token)

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

        # Build prefix-anchored ruling candidate regex from actual registry data.
        # This is done AFTER loading so the regex reflects the real ruling id set.
        ruling_candidate_re = _build_ruling_candidate_re(known_rulings) if rulings_ok else None

        # Extract referenced ids
        refs = _extract_ids(
            payload,
            known_rulings=known_rulings,
            ruling_candidate_re=ruling_candidate_re,
        )

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
