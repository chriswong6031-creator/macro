"""Frozen, source-bound metadata for the public /help directory.

This module deliberately owns only a small navigation contract.  It does not
inspect documentation, query a service, or infer availability from runtime
state: a link is either complete against its named template source or an
explicit, non-clickable unknown entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit


LinkState = Literal["complete", "unknown"]

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RELATIVE_HREF_RE = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9][A-Za-z0-9._/-]*\.html"
    r"(?:\?[A-Za-z0-9._~!$&'()*+,;=@%/-]*)?$"
)
_APP_SIGNIN_URL = "https://app.mastermind-x.com/terminal?signin=1"
_STATES = frozenset(("complete", "unknown"))


@dataclass(frozen=True, slots=True)
class HelpCategory:
    """One of the three pre-existing bilingual navigation vocabularies."""

    id: str
    label_en: str
    label_zh: str

    def as_view_model(self) -> dict[str, str]:
        return {"id": self.id, "label_en": self.label_en, "label_zh": self.label_zh}


@dataclass(frozen=True, slots=True)
class HelpLink:
    """A source-bound help entry with no dynamic or editorial fields."""

    id: str
    category: str
    label_en: str
    label_zh: str
    source_template: str
    href: str | None
    state: LinkState = "complete"
    status_en: str | None = None
    status_zh: str | None = None


HELP_CATEGORIES: tuple[HelpCategory, ...] = (
    HelpCategory("research", "Research", "研究"),
    HelpCategory("platform", "Platform", "平台"),
    HelpCategory("account", "Account", "账户"),
)
_CATEGORIES_BY_ID = {category.id: category for category in HELP_CATEGORIES}


HELP_LINKS: tuple[HelpLink, ...] = (
    HelpLink(
        id="market-reference",
        category="research",
        label_en="Market Reference",
        label_zh="市场参考",
        source_template="templates/_navlinks.html.j2",
        href="reference.html",
    ),
    HelpLink(
        id="methodology",
        category="research",
        label_en="Methodology",
        label_zh="方法论",
        source_template="templates/methodology.html.j2",
        href="methodology.html",
    ),
    HelpLink(
        id="cycle-intelligence-calibration-lab",
        category="research",
        label_en="Cycle Intelligence · Calibration Lab",
        label_zh="周期情报 · 校准实验室",
        source_template="templates/measurement.html.j2",
        href="measurement.html",
    ),
    HelpLink(
        id="glossary",
        category="research",
        label_en="Glossary",
        label_zh="词汇表",
        source_template="templates/glossary.html.j2",
        href="glossary.html",
    ),
    HelpLink(
        id="support",
        category="platform",
        label_en="Support",
        label_zh="支持",
        source_template="templates/_public_nav.html.j2",
        href="support.html",
    ),
    HelpLink(
        id="plans-pricing",
        category="platform",
        label_en="Plans & pricing",
        label_zh="方案与定价",
        source_template="templates/_public_footer.html.j2",
        href="plans.html",
    ),
    HelpLink(
        id="billing-payments",
        category="account",
        label_en="Billing & payments",
        label_zh="账单与付款",
        source_template="templates/support.html.j2",
        href="plans.html?billing=portal",
    ),
    HelpLink(
        id="account-sign-in",
        category="account",
        label_en="Account & sign-in",
        label_zh="账户与登录",
        source_template="templates/support.html.j2",
        href=_APP_SIGNIN_URL,
    ),
)


def _is_nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_approved_href(href: str) -> bool:
    return href == _APP_SIGNIN_URL or bool(_RELATIVE_HREF_RE.fullmatch(href))


def _source_path(root: Path, entry: HelpLink) -> Path:
    if not isinstance(entry.source_template, str):
        raise ValueError(f"help entry {entry.id!r}: invalid source_template")
    source = Path(entry.source_template)
    if (
        source.is_absolute()
        or not source.parts
        or source.parts[0] != "templates"
        or ".." in source.parts
    ):
        raise ValueError(f"help entry {entry.id!r}: invalid source_template")
    return root / source


def _validate_source_labels(root: Path, entry: HelpLink) -> None:
    path = _source_path(root, entry)
    try:
        source = unescape(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"help entry {entry.id!r}: source template is unavailable: {path}") from exc
    for field, label in (("label_en", entry.label_en), ("label_zh", entry.label_zh)):
        if label not in source:
            raise ValueError(
                f"help entry {entry.id!r}: source template {entry.source_template} missing {field}"
            )


def _validate_local_target(root: Path, entry: HelpLink) -> None:
    """Bind relative destinations to a committed public-page template.

    The public render may run from a sparse worktree where ``site/`` is omitted,
    so the governed source template — not a possibly absent generated copy — is
    the stable existence check.
    """
    if entry.href == _APP_SIGNIN_URL:
        return
    assert entry.href is not None  # complete-entry validation runs first
    target = Path(urlsplit(entry.href).path)
    template = root / "templates" / f"{target.as_posix()}.j2"
    if not template.is_file():
        raise ValueError(
            f"help entry {entry.id!r}: target template is unavailable: {template}"
        )


def validate_help_directory(root: Path, entries: Iterable[HelpLink] = HELP_LINKS) -> None:
    """Fail closed when a help entry escapes the frozen bilingual source contract."""
    root = Path(root)
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, HelpLink):
            raise ValueError("help directory entries must be HelpLink instances")
        if not _is_nonempty_text(entry.id) or not _ID_RE.fullmatch(entry.id):
            raise ValueError(f"help entry {entry.id!r}: id must be a unique kebab-case string")
        if entry.id in seen_ids:
            raise ValueError(f"duplicate help entry id: {entry.id}")
        seen_ids.add(entry.id)
        if entry.category not in _CATEGORIES_BY_ID:
            raise ValueError(f"help entry {entry.id!r}: category is not in the shared vocabulary")
        for field, value in (("label_en", entry.label_en), ("label_zh", entry.label_zh)):
            if not _is_nonempty_text(value):
                raise ValueError(f"help entry {entry.id!r}: {field} must be non-empty")
        if entry.state not in _STATES:
            raise ValueError(f"help entry {entry.id!r}: state must be complete or unknown")

        if entry.state == "complete":
            if not _is_nonempty_text(entry.href) or not _is_approved_href(entry.href):
                raise ValueError(f"help entry {entry.id!r}: unapproved href")
            if entry.status_en is not None or entry.status_zh is not None:
                raise ValueError(f"help entry {entry.id!r}: complete entries must not define status labels")
        else:
            if entry.href is not None:
                raise ValueError(f"help entry {entry.id!r}: unknown entries must not define href")
            for field, value in (("status_en", entry.status_en), ("status_zh", entry.status_zh)):
                if not _is_nonempty_text(value):
                    raise ValueError(f"help entry {entry.id!r}: unknown entries require {field}")

        _validate_source_labels(root, entry)
        if entry.state == "complete":
            _validate_local_target(root, entry)


def help_directory_view_model(
    root: Path,
    entries: Iterable[HelpLink] = HELP_LINKS,
) -> dict[str, Any]:
    """Return the stable Jinja model after validating the complete input tuple."""
    entries = tuple(entries)
    validate_help_directory(root, entries)
    if not entries:
        directory_state = "empty"
    elif all(entry.state == "unknown" for entry in entries):
        directory_state = "unknown"
    else:
        directory_state = "complete"

    return {
        "directory_state": directory_state,
        "categories": [category.as_view_model() for category in HELP_CATEGORIES],
        "entries": [
            {
                "id": entry.id,
                "category": entry.category,
                "category_en": _CATEGORIES_BY_ID[entry.category].label_en,
                "category_zh": _CATEGORIES_BY_ID[entry.category].label_zh,
                "label_en": entry.label_en,
                "label_zh": entry.label_zh,
                "href": entry.href if entry.state == "complete" else None,
                "state": entry.state,
                "status_en": entry.status_en,
                "status_zh": entry.status_zh,
            }
            for entry in entries
        ],
    }
