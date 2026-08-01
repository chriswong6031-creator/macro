"""tests/test_landing_pricing_cta.py — the landing's pricing-card CTA contract.

Two layers:

  1. the billing toggle keeps `.js-plan-cta[data-period]` hrefs in step
     (templates/index.html + site/index.html, static-source pins);
  2. the ENTITLEMENT matrix in templates/onboard.js `applyAuthChrome(me)` — a
     signed-in member must never be sold a trial of something they already hold
     ("Start 7-day trial" shown to a Pro Lifetime member, operator 2026-07-31).

Layer 2 is not a grep: the real `applyAuthChrome` body is sliced out of the
SHIPPING file and executed under node against stub DOM nodes, so an edit to the
branch matrix fails the test on behaviour rather than on wording.

  logged-out            -> untouched (applyAuthChrome never runs)
  free (signed in)      -> Free inert "Current plan"; Insider/Pro keep trial copy
  insider (any interval)-> Insider inert "Your plan";  Pro "Upgrade"
  pro + monthly         -> Insider inert "Included";   Pro "Upgrade to Annual"
  pro + annual          -> Insider inert "Included";   Pro inert "Your plan"
  pro lifetime (comp)   -> Insider inert "Included";   Pro inert "Your plan"
  unlimited             -> Insider inert "Included";   Pro inert "Your plan"
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

REL_ONBOARD = ("templates/onboard.js", "site/onboard.js")


# ─────────────────────────── layer 1: the billing toggle ───────────────────────

@pytest.mark.parametrize("rel", ("templates/index.html", "site/index.html"))
def test_billing_toggle_updates_paid_plan_cta_period(rel: str) -> None:
    html = (ROOT / rel).read_text(encoding="utf-8")
    start = html.index("function applyPricing()")
    end = html.index("tog.forEach", start)
    apply_pricing = html[start:end]

    assert "document.querySelectorAll('.js-plan-cta[data-period]')" in apply_pricing
    assert "el.dataset.period = period;" in apply_pricing
    assert "url.searchParams.set('period', period);" in apply_pricing
    assert "el.href = url.toString();" in apply_pricing


# ───────────────────────── source slicing (shared helper) ──────────────────────

def _extract_fn(src: str, name: str) -> str:
    """Slice `function <name>(...) { ... }` out of a JS file by brace matching.

    Skips braces inside strings and comments so a `{` in prose cannot truncate
    the slice — the failure mode that would make this whole test vacuous.
    """
    head = src.index("function " + name + "(")
    i = src.index("{", head)
    depth, j, n = 0, i, len(src)
    while j < n:
        c = src[j]
        if c in "\"'`":
            quote, j = c, j + 1
            while j < n and src[j] != quote:
                j += 2 if src[j] == "\\" else 1
            j += 1
            continue
        if c == "/" and j + 1 < n and src[j + 1] == "/":
            j = src.find("\n", j)
            if j == -1:
                break
            continue
        if c == "/" and j + 1 < n and src[j + 1] == "*":
            j = src.index("*/", j) + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[head:j + 1]
        j += 1
    raise AssertionError("unbalanced braces slicing %s" % name)


def _apply_auth_chrome(rel: str) -> str:
    return _extract_fn((ROOT / rel).read_text(encoding="utf-8"), "applyAuthChrome")


# The three landing pricing cards, in DOM order.
_PLANS = ("free", "insider", "pro")

_HARNESS = """
var CALLS = [];
function _mk(plan, period) {
  var a = { __attrs: { "data-plan": plan } };
  if (period) a.__attrs["data-period"] = period;
  a.getAttribute = function (k) { return (k in this.__attrs) ? this.__attrs[k] : null; };
  a.setAttribute = function (k, v) { this.__attrs[k] = String(v); };
  a.removeAttribute = function (k) { delete this.__attrs[k]; };
  a.classList = { remove: function () {}, add: function () {} };
  a.style = {};
  return a;
}
var CARDS = [_mk("free", null), _mk("insider", "annual"), _mk("pro", "annual")];
var document = {
  getElementById: function () { return null; },
  querySelectorAll: function (sel) { return sel === ".js-plan-cta" ? CARDS : []; }
};
// collaborators applyAuthChrome calls — recorded, never real
function _byId() { return null; }
function snapshotPlanCtas() {}
function setChromeLabel() {}
function bindChromeCta() {}
function bindPlanCta() {}
function renderGearAccount() {}
function makeInert(pc, key) { CALLS.push({ plan: pc.getAttribute("data-plan"), kind: "inert", key: key }); }
function makePlanLive(pc, key, href, target) {
  CALLS.push({ plan: pc.getAttribute("data-plan"), kind: "live", key: key, href: href, target: target });
}

__APPLY_AUTH_CHROME__

var out = {};
JSON.parse(__ME_LIST__).forEach(function (me) {
  CALLS = [];
  CARDS = [_mk("free", null), _mk("insider", "annual"), _mk("pro", "annual")];
  applyAuthChrome(me.payload);
  out[me.name] = CALLS;
});
process.stdout.write(JSON.stringify(out));
"""


def _run_matrix(rel: str, personas: dict[str, dict]) -> dict[str, list[dict]]:
    me_list = [{"name": k, "payload": v} for k, v in personas.items()]
    script = (
        _HARNESS
        .replace("__APPLY_AUTH_CHROME__", _apply_auth_chrome(rel))
        .replace("__ME_LIST__", json.dumps(json.dumps(me_list)))
    )
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
    return json.loads(res.stdout)


# ───────────────────────── layer 2: the entitlement matrix ─────────────────────

# (tier, status, source, interval, current_period_end) as /api/me returns them.
PERSONAS: dict[str, dict] = {
    "free": {"tier": "free", "status": "none", "source": None,
             "interval": None, "current_period_end": None},
    "insider-monthly": {"tier": "insider", "status": "active", "source": "stripe",
                        "interval": "monthly", "current_period_end": "2026-08-30T00:00:00Z"},
    "insider-annual": {"tier": "insider", "status": "active", "source": "stripe",
                       "interval": "annual", "current_period_end": "2027-07-31T00:00:00Z"},
    "pro-monthly": {"tier": "pro", "status": "active", "source": "stripe",
                    "interval": "monthly", "current_period_end": "2026-08-30T00:00:00Z"},
    "pro-annual": {"tier": "pro", "status": "active", "source": "stripe",
                   "interval": "annual", "current_period_end": "2027-07-31T00:00:00Z"},
    "pro-lifetime": {"tier": "pro", "status": "active", "source": "comp",
                     "interval": None, "current_period_end": None},
    "unlimited": {"tier": "unlimited", "status": "active", "source": "comp",
                  "interval": None, "current_period_end": None},
    # ── the two legs of the lifetime predicate that `interval` alone cannot reach.
    # A comp grant that still carries interval="monthly" is LIFETIME (no period end)
    # and must not be sold an annual upgrade…
    "pro-comp-monthly": {"tier": "pro", "status": "active", "source": "comp",
                         "interval": "monthly", "current_period_end": None},
    # …while a CANCELED comp is not lifetime, so the ordinary monthly upsell returns.
    "pro-comp-canceled": {"tier": "pro", "status": "canceled", "source": "comp",
                          "interval": "monthly", "current_period_end": None},
}

# name -> {plan: (kind, label-key)}. `None` as the key on a live CTA means "leave
# the card's own signed-out copy alone" (today's free-tier behaviour).
EXPECTED: dict[str, dict[str, tuple[str, str | None]]] = {
    "free": {
        "free": ("inert", "current"),
        "insider": ("live", None),
        "pro": ("live", None),
    },
    "insider-monthly": {
        "free": ("inert", "included"),
        "insider": ("inert", "yourPlan"),
        "pro": ("live", "upgrade"),
    },
    "insider-annual": {
        "free": ("inert", "included"),
        "insider": ("inert", "yourPlan"),
        "pro": ("live", "upgrade"),
    },
    "pro-monthly": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("live", "upgradeAnnual"),
    },
    "pro-annual": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("inert", "yourPlan"),
    },
    "pro-lifetime": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("inert", "yourPlan"),
    },
    "unlimited": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("inert", "yourPlan"),
    },
    "pro-comp-monthly": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("inert", "yourPlan"),
    },
    "pro-comp-canceled": {
        "free": ("inert", "included"),
        "insider": ("inert", "included"),
        "pro": ("live", "upgradeAnnual"),
    },
}


@needs_node
@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_entitlement_cta_matrix(rel: str) -> None:
    got = _run_matrix(rel, PERSONAS)
    for name, want in EXPECTED.items():
        calls = {c["plan"]: c for c in got[name]}
        assert set(calls) == set(_PLANS), f"{name}: not every card was painted ({sorted(calls)})"
        for plan, (kind, key) in want.items():
            c = calls[plan]
            assert (c["kind"], c["key"]) == (kind, key), (
                f"{name} / {plan} card: expected {kind}:{key}, got {c['kind']}:{c['key']}"
            )


@needs_node
@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_every_actionable_paid_cta_targets_pro_annual(rel: str) -> None:
    """Insider and Pro-Monthly are both sold UP to Pro Annual — the sheet's own
    lane matrix (upgradeLanes) then tailors the panel; no new upgrade UI here."""
    got = _run_matrix(rel, PERSONAS)
    for name in ("insider-monthly", "insider-annual", "pro-monthly"):
        pro = [c for c in got[name] if c["plan"] == "pro"][0]
        assert pro["kind"] == "live", f"{name}: Pro card must stay actionable"
        assert pro["target"] == {"plan": "pro", "period": "annual"}, (
            f"{name}: Pro CTA must preselect Pro Annual, got {pro['target']}"
        )


@needs_node
@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_no_paid_member_is_offered_a_trial(rel: str) -> None:
    """The operator bug, stated as an invariant: for every non-free signed-in
    payload, NO pricing CTA may be left carrying its own (trial) copy."""
    got = _run_matrix(rel, PERSONAS)
    for name, me in PERSONAS.items():
        if me["tier"] == "free":
            continue
        for c in got[name]:
            assert not (c["kind"] == "live" and c["key"] is None), (
                f"{name}: the {c['plan']} card kept its signed-out trial label"
            )


# ─────────────────────── label table + inert-state mechanics ───────────────────

@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_upchrome_carries_the_bilingual_entitlement_labels(rel: str) -> None:
    src = (ROOT / rel).read_text(encoding="utf-8")
    table = src[src.index("var UPCHROME = {"):src.index("function _byId(")]
    for key, en, zh in (
        ("upgrade", "Upgrade", "升级"),
        ("upgradeAnnual", "Upgrade to Annual", "升级为年付"),
        ("included", "Included", "已包含"),
        ("current", "Current plan", "当前方案"),
        ("yourPlan", "Your plan", "当前方案"),
    ):
        assert f'{key}: ["{en}", "{zh}"]' in table, f"UPCHROME.{key} drifted"


@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_inert_cta_drops_data_period_so_a_toggle_cannot_revive_it(rel: str) -> None:
    """applyPricing() re-writes `.js-plan-cta[data-period]` hrefs on every billing
    /language toggle, and `new URL("", location.href)` does NOT throw — so its
    try/catch is no protection. Dropping data-period is what keeps an inert card
    out of that selector."""
    body = _extract_fn((ROOT / rel).read_text(encoding="utf-8"), "makeInert")
    assert 'pc.removeAttribute("href")' in body
    assert 'pc.removeAttribute("data-period")' in body
    assert 'pc.setAttribute("aria-disabled", "true")' in body
    assert 'pc.style.pointerEvents = "none"' in body


@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_revert_restores_the_signed_out_pricing_ctas(rel: str) -> None:
    """A hard 401 must put the trial copy back, not leave a dead session's
    "Your plan" on the page."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    revert = _extract_fn(src, "revertAuthChrome")
    assert 'document.querySelectorAll(".js-plan-cta").forEach(restorePlanCta)' in revert

    restore = _extract_fn(src, "restorePlanCta")
    for expected in ('restorePlanLabel(pc)', 'aria-disabled', 'data-period', '"href"'):
        assert expected in restore, f"restorePlanCta no longer restores {expected}"

    # the snapshot has to be taken BEFORE any repaint, or there is nothing to restore
    init = _extract_fn(src, "initAuthChrome")
    assert "snapshotPlanCtas();" in init
    assert init.index("snapshotPlanCtas();") < init.index("applyAuthChrome(")

    # …and a reverted card must not keep firing the upgrade sheet
    bind = _extract_fn(src, "bindPlanCta")
    assert "if (!pc.__upgradePlan) return;" in bind


@pytest.mark.parametrize("rel", REL_ONBOARD)
def test_lifetime_predicate_matches_theme_js(rel: str) -> None:
    """The canonical lifetime test lives in templates/theme.js `_sdPlanChip`;
    onboard.js must not drift from it."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    apply_body = _extract_fn(src, "applyAuthChrome")
    assert 'tier === "unlimited" || me.source === "comp"' in apply_body
    assert "!me.current_period_end" in apply_body
    assert 'me.status !== "canceled"' in apply_body

    theme = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
    assert "p.tier === 'unlimited' || p.source === 'comp'" in theme, (
        "theme.js lifetime predicate moved — re-derive the onboard.js copy"
    )
