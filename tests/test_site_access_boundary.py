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
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# Non-test inputs of the tier-gate job that no `run:` line names, so the
# reachability test below cannot derive them: the two halves of the boundary this
# module diffs, and the two routers the regwall/paywall suites exercise. Editing
# any of them is exactly the change tier-gate exists to catch.
TIER_GATE_SOURCE_INPUTS = (
    "config/site_access.yml",
    "app/deploy/Caddyfile",
    "app/regwall.py",
    "app/paywall.py",
)

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
# /research/ was added here on 2026-07-25 (#3507) to clear the #3488 red and is
# now REMOVED: #3501/#3512 landed the estate as 87 tracked files, so the tree
# exists and the real assertion passes on its merits. Keeping the exemption would
# have been the bad outcome on both counts — the honesty guard below explains the
# epistemic half, and gitignoring a tracked tree would have made the render lanes'
# `git add site/` silently skip every NEW report page (edits to existing pages
# still stage; new files do not), freezing the estate at 85 reports while the
# hourly research-ingest lane kept growing catalog.json.
RUNTIME_ARTIFACT_PREFIXES = ("/live/",)


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
        assert (SITE / path.lstrip("/")).is_file(), f"missing public exact path: {path}"
    for prefix in POLICY["public"]["prefixes"]:
        if prefix.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        assert (SITE / prefix.strip("/")).is_dir(), f"missing public prefix: {prefix}"


def test_runtime_artifact_exemption_stays_honest():
    """The existence exemption is only legitimate for genuinely gitignored
    planes. If site/live/ ever became a committed tree, the exemption would
    start hiding typo'd/dead public policy entries instead of runtime churn."""
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        assert f"site{prefix}" in ignored, f"exempt prefix is not gitignored: site{prefix}"


def test_no_public_prefix_is_exempted_from_the_existence_check():
    """An exemption may excuse individual runtime FILES, never a whole subtree.

    The /live/ exemption covers two `exact` entries (quotes.json, breadth.json)
    whose on-disk presence really is runtime-dependent — the systemd lanes publish
    them by atomic rename and force-add a fallback snapshot. Exempting a public
    PREFIX is a different act: it disables the is_dir() check for an entire estate,
    so a typo'd or dead prefix passes forever.

    That is what happened on 2026-07-25. Three PRs raced the #3488 red: #3507
    exempted /research/ (and gitignored it) while #3501 committed the 85 baked
    pages and #3512 added a .gitkeep — leaving site/research/ both gitignored and
    holding 87 tracked files. The gitignore half of the honesty guard above was
    then satisfied by a tree that was not runtime at all, and the ignore itself
    was worse than useless: gitignore governs only untracked paths, so every
    render lane's `git add site/` would keep staging edits to the 85 existing
    pages while silently skipping each NEW report page — freezing the estate as
    the hourly research-ingest lane kept growing catalog.json.

    Both halves were reverted; this keeps the door shut. Not vacuous — it walks
    every declared public prefix.
    """
    assert POLICY["public"]["prefixes"], "no public prefixes to check — policy shape changed?"
    exempted = [p for p in POLICY["public"]["prefixes"]
                if p.startswith(RUNTIME_ARTIFACT_PREFIXES)]
    assert exempted == [], (
        f"public prefix(es) exempted from the existence check: {exempted}. A prefix "
        "is committed estate — if its tree is missing, bake and commit it rather "
        "than exempting it. RUNTIME_ARTIFACT_PREFIXES is for individual runtime "
        "files listed under public.exact."
    )


def _gh_path_filter_to_re(pattern: str) -> re.Pattern:
    """GitHub filter-pattern semantics: `*` stops at `/`, `**` crosses it."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "*":
            if pattern[i + 1:i + 2] == "*":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def test_tier_gate_is_reachable_from_its_own_inputs():
    """A guard the guarded change cannot trigger is not a guard.

    tier-gate runs every serving-boundary suite, but ci.yml is `on: pull_request`
    with a ~530-entry `paths:` filter. Until 2026-07-25 not one of the job's
    inputs was in that list, so the job only ever fired incidentally — when a PR
    happened to also touch site/** or templates/**. #3488 changed ONLY
    site_access.yml + Caddyfile + regwall.py, triggered no workflow at all, and
    merged with the boundary test never executed (it then sat red on main). This
    pins the trigger to the job: every test file tier-gate runs, plus the source
    inputs above, must be named in the filter.
    """
    ci = yaml.safe_load(CI_WORKFLOW.read_text())
    # PyYAML resolves the bare key `on` to True (YAML 1.1 booleans).
    triggers = ci.get("on") or ci.get(True)
    paths = triggers["pull_request"]["paths"]
    matchers = [_gh_path_filter_to_re(p) for p in paths]

    steps = ci["jobs"]["tier-gate"]["steps"]
    run_tests = set(re.findall(r"tests/test_[A-Za-z0-9_]+\.py", "\n".join(
        s["run"] for s in steps if "run" in s)))
    assert run_tests, "tier-gate runs no pytest targets — did the job change shape?"

    required = run_tests | set(TIER_GATE_SOURCE_INPUTS)
    unreachable = sorted(t for t in required if not any(m.match(t) for m in matchers))
    assert unreachable == [], (
        "tier-gate inputs missing from ci.yml pull_request paths (a PR touching "
        f"only these would run no boundary guard): {unreachable}")


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
