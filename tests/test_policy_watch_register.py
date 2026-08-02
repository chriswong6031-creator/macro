"""Policy Watch front-facing copy carries no falsifier/refutation register.

Operator ruling 2026-07-27 (#3821; extended 2026-07-29 to every public surface):
the falsifier MACHINERY keeps evaluating in the background — schema keys like
``falsifier_text`` / ``falsifier.check`` stay — but display text never says
"falsified / refuted / 证伪".  Sanctioned register: "Changes this read:
<condition>" / zh "改判条件：<条件>", and "READ BEING UPDATED / 解读更新中" for
revision states.  Full technical verdicts live on the Calibration Lab
(measurement.html), which is the sanctioned home and out of scope here.

Scope = the Policy Watch estate's deterministic sources: the hand-curated
substrate (data/policy/intel.json — refreshed by operator-signed PRs with no
generator, so this file IS the reintroduction vector), the two policy
templates, and the intent desk's hardcoded display constants.  The desk's
LLM-authored falsifier_text content is prompt-guarded in
engine/policy_intent_desk.py rather than pinned here (nightly LLM output must
not be able to fail the suite).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# stems, not words: catches falsified/falsifiable/FALSIFICATION, refuted/refutation
BANNED = re.compile(r"falsif|refut|证伪", re.IGNORECASE)


def _strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def test_policy_intel_substrate_is_register_clean():
    """Every string VALUE in the curated substrate is display text (the schema
    has no falsifier-named keys), so the whole file must scan clean."""
    intel = json.loads((ROOT / "data" / "policy" / "intel.json").read_text(encoding="utf-8"))
    bad = [s[:120] for s in _strings(intel) if BANNED.search(s)]
    assert not bad, (
        "data/policy/intel.json carries falsifier-register display text "
        f"(sanctioned form: 'Changes this read: …' / '改判条件：…'): {bad[:5]}"
    )


@pytest.mark.parametrize("tpl", ["policy_watch.html.j2", "china_policy_watch.html.j2"])
def test_policy_templates_have_no_front_facing_register(tpl):
    """`th.falsifier.text` etc. are payload KEY paths (background machinery,
    exempt); the ban is on label/prose tokens a reader sees.  Lowercase
    `falsifier` as an attribute access is therefore allowed — the banned set is
    the display vocabulary."""
    text = (ROOT / "templates" / tpl).read_text(encoding="utf-8")
    for needle in ("证伪", "Falsif", "FALSIF", "falsifiable", "falsified",
                   "falsification", "refuted", "REFUTED", "refutation"):
        assert needle not in text, (
            f"templates/{tpl} carries front-facing falsifier-register token {needle!r}"
        )


def test_intent_desk_display_constants_are_register_clean():
    """DISCLAIMER / DISCLAIMER_ZH are baked verbatim into site/policy_intent.json
    and rendered on policy_watch.html.  Scanned as source text (not imported) so
    the check runs under minimal CI-pack deps."""
    src = (ROOT / "engine" / "policy_intent_desk.py").read_text(encoding="utf-8")
    m = re.search(r"DISCLAIMER = \((.*?)\)\nDISCLAIMER_ZH = \((.*?)\)\n", src, re.S)
    assert m, "DISCLAIMER constants moved in engine/policy_intent_desk.py — update this guard"
    for blob in m.groups():
        assert not BANNED.search(blob), (
            f"intent-desk disclaimer carries falsifier register: {blob[:120]!r}"
        )
