"""Regression coverage for the public account-creation email gate."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ONBOARD = ROOT / "templates" / "onboard.js"


def _email_pattern() -> re.Pattern[str]:
    source = ONBOARD.read_text(encoding="utf-8")
    match = re.search(r"var EMAIL_RE = /(.*)/;", source)
    assert match, "onboarding lost its explicit email-format validator"
    return re.compile(match.group(1))


def test_signup_email_requires_a_domain_suffix() -> None:
    pattern = _email_pattern()
    for email in (
        "reader@example.com",
        "reader+alerts@sub.example.co.uk",
        "first.last@example.finance",
        "reader@xn--bcher-kva.example",
    ):
        assert pattern.fullmatch(email), f"valid signup email was rejected: {email}"

    for email in (
        "reader@example",
        "reader@localhost",
        "reader@domain.",
        "reader@.com",
        "reader@@example.com",
        ".reader@example.com",
        "reader..alerts@example.com",
        "reader @example.com",
    ):
        assert not pattern.fullmatch(email), f"invalid signup email was accepted: {email}"


def test_signup_checks_email_before_calling_supabase() -> None:
    source = ONBOARD.read_text(encoding="utf-8")
    submit = source[source.index("function onAccountSubmit"):source.index("function onGoogle")]
    assert "if (!validEmail(S.email))" in submit
    assert submit.index("if (!validEmail(S.email))") < submit.index("sb.auth.signUp(")
    assert 'emailInput.setAttribute("aria-invalid", "true")' in submit
    assert 'showErr(tx("emailInvalid"))' in submit
