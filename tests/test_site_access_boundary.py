"""Static serving-boundary drift and client-artifact leak tripwires."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
CADDY = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
SITE = ROOT / "site"

# Caddy exclusions that have no home in config/site_access.yml. The policy
# schema classifies static FILE paths under site/; these are reverse-proxied
# ROUTES to macro-api (app/main.py), which enforces its own auth. Excluding them
# from the static matchers is what stops a ws upgrade / API call from being
# swallowed by the file gate — it is not a public-content decision.
NON_POLICY_ROUTES = {"/api/*", "/ws/tape"}

# Public policy entries whose target is a RUNTIME artifact, not a committed
# file. site/live/ is gitignored: the systemd lanes publish by atomic rename
# into /var/lib/macro-live/public and scripts/live_breadth_poller.py force-adds
# a snapshot, so a fresh checkout may hold none of them. The policy line is
# still the boundary of record — only the on-disk existence check is exempt.
#
# /research/ is NOT in this tuple, and adding it back is a regression (#3507 did,
# reverted here). The distinction is the DELIVERY path, not "is it generated":
# site/live/ reaches the edge out-of-band via systemd atomic rename, so a fresh
# checkout legitimately lacks it. site/research/ reaches the edge only by being
# COMMITTED to main — "the VPS serves committed main; there is no Pages-artifact
# fallback" (render.yml) — so the render lane's `git add site/` IS its delivery
# mechanism. Exempting it required gitignoring site/research/, and a gitignored
# subtree makes `git add site/` silently skip every NEW file: the 86 pages already
# tracked kept updating, but each new report's landing page would never land again
# — re-creating the exact "shipped dark" failure #3487 was fixing. The tree is
# committed (#3501), so the plain existence check below passes on its own merits.
RUNTIME_ARTIFACT_PREFIXES = ("/live/",)

# Shown on every missing-target failure. A public entry that points at nothing is a
# REAL defect (the edge advertises a path that 404s), so this stays a hard failure --
# but the cheap-looking fix is the wrong one, and #3488 proved the bait works: when a
# policy entry lands before its generator's first committed output, the red shows up
# as "missing public prefix" and the nearest exit is RUNTIME_ARTIFACT_PREFIXES. Taking
# it would either trip test_runtime_artifact_exemption_stays_honest or force a bogus
# .gitignore entry, and would leave the boundary permanently unable to tell a
# not-yet-built tree from a dead/typo'd one. Name the two real remedies instead.
_MISSING_TARGET_HINT = (
    "config/site_access.yml declares it public but that path does not exist under site/. "
    "Either land the content first (a CI-generated tree must have its builder's first "
    "output committed BEFORE the policy entry -- see #3487/#3488), or drop the policy "
    "entry until it does. Do NOT add it to RUNTIME_ARTIFACT_PREFIXES: that exemption is "
    "only for genuinely gitignored runtime planes, and using it here hides a dead entry."
)


def _caddy_public_exclusions() -> set[str]:
    match = re.search(
        r"# PUBLIC-BOUNDARY-START.*?@reg_asset\s*\{\s*not path ([^\n]+)",
        CADDY,
        flags=re.S,
    )
    assert match, "Caddy public-boundary marker/matcher missing"
    return set(shlex.split(match.group(1)))


def test_caddy_public_boundary_matches_policy_exactly():
    expected = set(NON_POLICY_ROUTES) | {"*.html"}
    expected.update(POLICY["public"]["exact"])
    expected.update(prefix.rstrip("/") + "/*" for prefix in POLICY["public"]["prefixes"])
    assert _caddy_public_exclusions() == expected


def test_public_policy_targets_exist():
    for path in POLICY["public"]["exact"]:
        if path == "/" or path.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        assert (SITE / path.lstrip("/")).is_file(), (
            f"missing public exact path: {path} -- {_MISSING_TARGET_HINT}"
        )
    for prefix in POLICY["public"]["prefixes"]:
        if prefix.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        assert (SITE / prefix.strip("/")).is_dir(), (
            f"missing public prefix: {prefix} -- {_MISSING_TARGET_HINT}"
        )


def test_runtime_artifact_exemption_stays_honest():
    """The existence exemption is only legitimate for genuinely gitignored
    planes. If site/live/ ever became a committed tree, the exemption would
    start hiding typo'd/dead public policy entries instead of runtime churn."""
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        assert f"site{prefix}" in ignored, f"exempt prefix is not gitignored: site{prefix}"


def test_generated_data_is_not_accidentally_public():
    public = _caddy_public_exclusions()
    intentional = {
        "/live/quotes.json",
        "/live/breadth.json",
        "/prophet/showcase.json",
        "/factordata/tech_lab.json",
    }
    exposed_json = {p for p in public if p.endswith(".json")}
    assert exposed_json == intentional
    assert "/factordata/tech_events/*" in public
    assert "/factordata/*" not in public
    assert "/labdata/*" not in public
    assert "/neuralwebdata/*" not in public
    assert "/oracledata/*" not in public
    assert "/signals/*" not in public


def test_no_source_maps_secrets_or_server_source_in_site_tree():
    forbidden_suffixes = {".map", ".py", ".pyc", ".pem", ".key", ".env", ".sql"}
    bad = [
        p.relative_to(SITE).as_posix()
        for p in SITE.rglob("*")
        if p.is_file() and (p.suffix.lower() in forbidden_suffixes or p.name.startswith(".env"))
    ]
    assert bad == []


def test_fail_closed_and_browser_hardening_are_present():
    assert 'rewrite /api/regwall/check' in CADDY
    assert 'rewrite /api/paywall/check' in CADDY
    assert '{"error":"site_access_temporarily_unavailable"}' in CADDY
    assert "Content-Security-Policy \"base-uri 'self'; object-src 'none'; frame-ancestors 'none'\"" in CADDY
    assert 'X-Frame-Options "DENY"' in CADDY
    assert 'Permissions-Policy "camera=(), microphone=(), geolocation=(), usb=()"' in CADDY
