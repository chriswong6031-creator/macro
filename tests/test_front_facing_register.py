"""Front-facing copy beyond the Policy Watch estate carries no falsifier register.

Operator ruling 2026-07-27 (#3821): the falsifier MACHINERY keeps evaluating in
the background — schema keys (``falsifier_text``, ``falsifier.check``,
``cycle_falsifier_fired:*`` rule ids, ``th.falsifiers`` payload paths) stay —
but display text never says "falsified / refuted / 证伪".  Sanctioned register:
"Changes this read: <condition>" / zh "改判条件：<条件>", "checkable / 可检验"
for "falsifiable / 可证伪", "holding / 仍成立" for "not falsified / 未被证伪",
and "READ BEING UPDATED / 解读更新中" for revision states.  #4208
(tests/test_policy_watch_register.py) fences the Policy Watch estate; this file
fences the surfaces de-registered in the follow-up sweep.

Scope is exactly the surfaces that sweep fixed — template/JS needle scans plus
per-emitter regression pins on the display phrases that were removed.  It is a
regression fence, not a repo-wide vocabulary sweep: the Calibration Lab
(measurement.html, engine/calibration_hub.py, engine/desk_placebo.py) is the
sanctioned technical home and stays out of scope, as do registry artifacts
(signal lab / experiments / neural-web governance graphs), LLM-internal prompt
framing, and quoted external news headlines.  The dated archival reports
(report_*.html.j2) were deferred by the first sweep as an editorial question;
the retroactive-edit decision landed with this PR — semantic conditions kept
verbatim, register vocabulary swapped — so the four report templates are now
inside the fence.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1) Template + shipped-JS needle scan (same needle set as #4208): label/prose
#    tokens a reader sees.  Bare lowercase "falsifier(s)" is allowed — it is the
#    payload-key vocabulary (attribute paths, loop vars, CSS class stubs).
# ---------------------------------------------------------------------------
NEEDLES = ("证伪", "Falsif", "FALSIF", "falsifiable", "falsified",
           "falsification", "refuted", "REFUTED", "refutation")

CLEAN_TEMPLATES = [
    "ai_desk.html.j2", "alt_data.html.j2", "aibrief.html.j2",
    "allocation.html.j2", "china_radar.html.j2", "china_intel.html.j2",
    "china_history.html.j2", "china_stocks_lab.html.j2", "committee.html.j2",
    "foresight.html.j2", "neural_web.html.j2", "state_of_themes.html.j2",
    # paired plain-copy JS (site/ copies are byte-locked to these by
    # scripts/check_template_site_sync.py, so pinning templates/ pins both)
    "ai_desk.js", "aidesk_lean.js", "ai_desk_thematic.js",
    # dated archival reports, de-registered retroactively (semantic conditions
    # verbatim; EN "Kill:" stays, 证伪 -> 改判条件 family, falsifiable ->
    # checkable/可检验; dashboards retitled to the accountability family)
    "report_second_act.html.j2", "report_haven_audition.html.j2",
    "report_relapse_jul8.html.j2", "report_bessent_jun24.html.j2",
]


@pytest.mark.parametrize("tpl", CLEAN_TEMPLATES)
def test_templates_have_no_front_facing_register(tpl):
    text = (ROOT / "templates" / tpl).read_text(encoding="utf-8")
    for needle in NEEDLES:
        assert needle not in text, (
            f"templates/{tpl} carries front-facing falsifier-register token "
            f"{needle!r} (sanctioned: 'Changes this read/改判条件', "
            f"'checkable/可检验', 'holding/仍成立')"
        )


# ---------------------------------------------------------------------------
# 2) Emitter regression pins — the exact display phrases the sweep removed.
#    These modules legitimately keep "falsifier" as machinery vocabulary
#    (module names, keys, docstrings), so each file bans only the user-shown
#    phrases that used to leak from it.
# ---------------------------------------------------------------------------
EMITTER_PINS = {
    "engine/master_brain_scorer.py": ["not falsified", "未被证伪"],
    "engine/ai_desk_scorer.py": ["not falsified", "未被证伪"],
    "engine/demand_ledger.py": ["则证伪", "FALSE if"],
    "engine/btc_alerts.py": ["证伪", "structural falsifier —"],
    "engine/falsifier_tripwires.py": ["证伪", "Cycle falsifier FIRED",
                                      "Direction: {r.direction}",
                                      "direction: {r.direction}"],
    # build_vector still MATCHES the legacy "Cycle falsifier FIRED" wording to
    # translate pre-#3821 logged alerts — only its zh OUTPUT is pinned here.
    "scripts/build_vector.py": ["周期证伪条件触发"],
    "engine/china_radar.py": ["可证伪", "falsifiable hypothesis"],
    "engine/hub_track_record.py": ["A falsifiable scorecard"],
    "engine/index_leadership_track.py": ["A falsifiable scorecard"],
    "engine/desk_grader.py": ["A falsifiable scorecard"],
    "engine/subsector_track_record.py": ["A falsifiable scorecard", "可证伪"],
    "engine/china_intel_analysis.py": ["falsifiable hypotheses", "可证伪"],
    "engine/intel_hub.py": ["names its falsifier"],
    "engine/briefing.py": ["carries a falsifier"],
    "engine/thematic_desk.py": ["FALSIFIABLE hypotheses"],
    "engine/ai_desk.py": ["FALSIFIABLE judgement"],
    "engine/altdata_brain.py": ["accountable and falsifiable"],
    "engine/narrative_rotation.py": ["falsifiable conditional lean"],
    "engine/neuralweb/theme_asymmetry.py": ["假证伪器", "n_falsifiers="],
    "scripts/build_state_of_themes.py": ["Falsifier clarity", "假证伪清晰度"],
    "scripts/build_reports.py": ["被证伪"],
}


@pytest.mark.parametrize("rel", sorted(EMITTER_PINS))
def test_emitter_display_strings_are_register_clean(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    for phrase in EMITTER_PINS[rel]:
        assert phrase not in src, (
            f"{rel} reintroduced front-facing register phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 3) LLM-desk prompt guard — the falsifier_text fields these desks author are
#    displayed under a "Changes this read" label, so each prompt must carry the
#    display-register prohibition (mirrors engine/policy_intent_desk.py, #4208).
# ---------------------------------------------------------------------------
PROMPT_GUARDED = [
    "engine/thematic_desk.py", "engine/ai_desk.py", "engine/altdata_brain.py",
    "engine/master_brain.py", "engine/stock_desk.py",
]


@pytest.mark.parametrize("rel", PROMPT_GUARDED)
def test_desk_prompts_forbid_register_in_falsifier_text(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    # "never write" (not the full phrase) — the prohibition line is wrapped
    # across adjacent string literals in some prompts.
    assert "never write" in src and "falsifier_text" in src, (
        f"{rel} lost the falsifier_text display-register prohibition "
        "(never write 'falsified'/'falsify'/'refuted' in user-shown text)"
    )


# ---------------------------------------------------------------------------
# 4) Healed forward log — the shipped alert log is baked into start.html
#    nightly, so a register row here re-publishes the old wording.
# ---------------------------------------------------------------------------
def test_alert_log_messages_are_register_clean():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    df = pd.read_parquet(ROOT / "data" / "alerts" / "alerts_log.parquet")
    ban = re.compile(r"falsif|refut|证伪", re.IGNORECASE)
    bad = df[
        df["message"].astype(str).str.contains(ban)
        | df["message_zh"].astype(str).str.contains(ban)
    ]
    assert bad.empty, (
        "data/alerts/alerts_log.parquet carries falsifier-register display "
        f"text in {len(bad)} row(s): {bad['rule'].tolist()[:5]}"
    )


# ---------------------------------------------------------------------------
# 5) AI-scout watch de-registration (#3821 follow-up).  thematic_desk's
#    ``emerging_watch`` is LLM prose printed VERBATIM by two live panels — the
#    Forming Narratives panel (baskets_*, via engine/narrative_emergence.py)
#    and the thematic desk block on allocation*.html — and the scout prompt
#    used to ask for a "kill-criterion", which shipped as a front-facing
#    "Kill criterion: <condition>" line.  Pin all three legs: the prompt no
#    longer asks for one, and neither panel prints the raw payload value.
# ---------------------------------------------------------------------------
KILL_REGISTER = ("kill-criterion", "kill criterion", "Kill criterion", "Kill:")


def test_scout_prompt_does_not_ask_for_a_kill_criterion():
    src = (ROOT / "engine" / "thematic_desk.py").read_text(encoding="utf-8")
    for phrase in ("kill-criterion", "kill criterion"):
        # the prohibition line quotes the banned wording; every other use is gone
        uses = [ln for ln in src.splitlines()
                if phrase in ln.lower() and "never write" not in ln]
        assert not uses, (
            f"engine/thematic_desk.py still asks the scout for a {phrase!r}: {uses[:2]}"
        )
    assert "never write 'kill criterion'" in src, (
        "emerging_watch prompt lost its display-register prohibition"
    )


# (emitter, raw expression the panel must no longer render)
WATCH_PANELS = {
    "templates/forming_narratives.js": "esc(d.ai_watch.text)",
    "templates/ai_desk_thematic.js": "esc(brief.emerging_watch)",
}


@pytest.mark.parametrize("rel", sorted(WATCH_PANELS))
def test_watch_panels_normalize_the_scout_text(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert WATCH_PANELS[rel] not in src, (
        f"{rel} prints the scout's watch text raw ({WATCH_PANELS[rel]}) — a stale "
        "brief would leak the falsifier register straight to a user-cycle surface"
    )
    # both halves of the normalizer must be present: the EN label swap and the
    # zh label (the condition body stays EN — the payload carries no zh field).
    assert "'Watching for: '" in src, f"{rel} lost the EN watching-register label"
    assert "关注条件：" in src, f"{rel} lost the zh watching-register label"
