"""Frozen, source-bound metadata for the public /help directory.

This module deliberately owns only a small navigation contract for
``HelpLink``: a link is either complete against its named template source or
an explicit, non-clickable unknown entry.  ``HelpAnswer`` (added for packet
B-F13-3) is a deliberate, narrow exception: its *destination* stays
source-bound the same way, but its *sentence is authored* — an authored,
plain-word answer is the entire product of ledger row MO-PAID-088, and is
validated (bilingual, non-empty, no duplicate id) rather than matched against
template source text. ``SupportPlan``/``route_for_tier`` (also added here)
are the single source of truth for support-ticket routing by plan (ledger row
MO-PAID-058); ``app/support.py`` imports from this module and never the other
way around, so the static site build never drags in FastAPI.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit


LinkState = Literal["complete", "unknown"]
Queue = Literal["community", "priority"]

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


# --------------------------------------------------------------------------- #
# Answers (packet B-F13-3 / MO-PAID-088) — authored sentences, source-bound href
# --------------------------------------------------------------------------- #

# One shared plain-language vocabulary law: applies to every user-facing
# sentence produced by this module (help answers, changelog entries, support
# plan copy) — never a per-section list (review finding M3). "queue" is
# ordinary English (used in the support-plan promise text: "priority queue")
# and is intentionally NOT on this list; the banned set is internal
# state/module/vendor names, not everyday words.
_BANNED_WORDS = (
    "falsifier", "refuted", "\u8bc1\u4f2a", "generated_utc", "slo", "tier",
    "pipeline", "artifact", "render", "slug", "entitlement", "view_model",
    "supabase", "postgrest", "idem_key", "backfill", "null", "nan",
)
_FILENAME_RE = re.compile(r"[A-Za-z_]+\.(py|j2|yml|css|js)")
_SHOUTY_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")


def _banned_word_pattern(word: str) -> re.Pattern[str]:
    """Whole-word match for ASCII words (review finding M2: plain containment
    false-positived on ordinary English — 'nan' inside 'financial', 'tier'
    inside 'frontier', 'render' inside 'surrender', 'null' inside 'annulled').
    Non-ASCII terms (the Chinese banned phrase) keep plain containment since
    CJK text carries no word-boundary characters for \b to anchor on."""
    if word.isascii():
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])")
    return re.compile(re.escape(word))


_BANNED_PATTERNS = tuple((w, _banned_word_pattern(w)) for w in _BANNED_WORDS)


def _check_banned_vocabulary(label: str, en: str, zh: str) -> None:
    lowered = en.lower()
    zh_lowered = zh.lower()
    for word, pattern in _BANNED_PATTERNS:
        if pattern.search(lowered) or pattern.search(zh_lowered):
            raise ValueError(f"{label}: banned vocabulary {word!r}")
    for text in (en, zh):
        if _FILENAME_RE.search(text):
            raise ValueError(f"{label}: leaks a raw filename")
        if _SHOUTY_RE.search(text):
            raise ValueError(f"{label}: leaks a raw slug/constant")


@dataclass(frozen=True, slots=True)
class HelpAnswer:
    """One question the user actually asks, answered in a single plain sentence.

    Destination stays source-bound (``href``, when set, must be an approved,
    reachable local target — the same rule ``HelpLink`` enforces); the
    question/answer sentences themselves are authored copy, not matched
    against any template source.
    """

    id: str
    category: str
    question_en: str
    question_zh: str
    answer_en: str
    answer_zh: str
    href: str | None = None
    link_en: str | None = None
    link_zh: str | None = None


HELP_ANSWERS: tuple[HelpAnswer, ...] = (
    HelpAnswer("read-a-signal", "research",
        "How do I read a signal on this site?", "\u6211\u8be5\u600e\u4e48\u8bfb\u8fd9\u91cc\u7684\u4fe1\u53f7\uff1f",
        "Every signal shows a plain-word stance first; the method behind it is on the Methodology page.",
        "\u6bcf\u4e2a\u4fe1\u53f7\u5148\u7ed9\u51fa\u4e00\u53e5\u5927\u767d\u8bdd\u7ed3\u8bba\uff1b\u80cc\u540e\u7684\u65b9\u6cd5\u5728\u201c\u65b9\u6cd5\u8bba\u201d\u9875\u9762\u3002",
        "methodology.html", "Methodology", "\u65b9\u6cd5\u8bba"),
    HelpAnswer("what-is-calibration", "research",
        "What does calibration mean here?", "\u8fd9\u91cc\u8bf4\u7684\u201c\u6821\u51c6\u201d\u662f\u4ec0\u4e48\u610f\u601d\uff1f",
        "It is our own scorecard: we publish how our past calls turned out, wins and misses together.",
        "\u90a3\u662f\u6211\u4eec\u81ea\u5df1\u7684\u6210\u7ee9\u5355\uff1a\u6211\u4eec\u628a\u8fc7\u53bb\u5224\u65ad\u7684\u7ed3\u679c\u516c\u5e03\u51fa\u6765\uff0c\u5bf9\u7684\u548c\u9519\u7684\u90fd\u5728\u3002",
        "measurement.html", "Calibration Lab", "\u6821\u51c6\u5b9e\u9a8c\u5ba4"),
    HelpAnswer("how-do-you-know", "research",
        "How do you know a signal works?", "\u4f60\u4eec\u600e\u4e48\u77e5\u9053\u4e00\u4e2a\u4fe1\u53f7\u6709\u6548\uff1f",
        "We write the test down before it runs and publish the result either way, including when there is none.",
        "\u6211\u4eec\u5728\u6d4b\u8bd5\u5f00\u59cb\u524d\u5148\u628a\u6807\u51c6\u5199\u4e0b\u6765\uff0c\u65e0\u8bba\u7ed3\u679c\u5982\u4f55\u90fd\u516c\u5e03\uff0c\u5305\u62ec\u6ca1\u6709\u6548\u679c\u7684\u60c5\u51b5\u3002",
        "measurement.html", "Calibration Lab", "\u6821\u51c6\u5b9e\u9a8c\u5ba4"),
    HelpAnswer("look-up-a-term", "research",
        "Where do I look up a market term?", "\u6211\u5728\u54ea\u91cc\u67e5\u5e02\u573a\u672f\u8bed\uff1f",
        "Market Reference explains the terms and figures used across the site, in both languages.",
        "\u201c\u5e02\u573a\u53c2\u8003\u201d\u7528\u4e2d\u82f1\u53cc\u8bed\u89e3\u91ca\u7ad9\u5185\u7528\u5230\u7684\u672f\u8bed\u548c\u6570\u5b57\u3002",
        "reference.html", "Market Reference", "\u5e02\u573a\u53c2\u8003"),
    HelpAnswer("how-often-updated", "platform",
        "How often do the pages update?", "\u9875\u9762\u591a\u4e45\u66f4\u65b0\u4e00\u6b21\uff1f",
        "Pages rebuild once a day, overnight. Each page carries the time it was last built.",
        "\u9875\u9762\u6bcf\u5929\u591c\u95f4\u91cd\u5efa\u4e00\u6b21\u3002\u6bcf\u4e2a\u9875\u9762\u90fd\u6807\u6709\u6700\u8fd1\u4e00\u6b21\u751f\u6210\u7684\u65f6\u95f4\u3002"),
    HelpAnswer("what-is-in-each-plan", "platform",
        "What do I get on each plan?", "\u6bcf\u4e2a\u65b9\u6848\u5206\u522b\u5305\u542b\u4ec0\u4e48\uff1f",
        "Plans and pricing lists what is included, with the free plan's limits stated in full.",
        "\u201c\u65b9\u6848\u4e0e\u5b9a\u4ef7\u201d\u9875\u9762\u5217\u51fa\u5404\u65b9\u6848\u5305\u542b\u7684\u5185\u5bb9\uff0c\u514d\u8d39\u65b9\u6848\u7684\u9650\u5236\u4e5f\u5b8c\u6574\u5199\u660e\u3002",
        "plans.html", "Plans & pricing", "\u65b9\u6848\u4e0e\u5b9a\u4ef7"),
    HelpAnswer("change-or-cancel", "account",
        "How do I change or cancel my plan?", "\u6211\u600e\u4e48\u66f4\u6539\u6216\u53d6\u6d88\u65b9\u6848\uff1f",
        "Open the billing portal from Plans and pricing; changes take effect at the end of the period you paid for.",
        "\u5728\u201c\u65b9\u6848\u4e0e\u5b9a\u4ef7\u201d\u6253\u5f00\u8d26\u5355\u7ba1\u7406\u5165\u53e3\uff1b\u66f4\u6539\u4f1a\u5728\u4f60\u5df2\u4ed8\u8d39\u7684\u5468\u671f\u7ed3\u675f\u540e\u751f\u6548\u3002",
        "plans.html?billing=portal", "Billing", "\u8d26\u5355"),
    HelpAnswer("how-do-i-sign-in", "account",
        "How do I sign in?", "\u6211\u600e\u4e48\u767b\u5f55\uff1f",
        "Use the sign-in link at the top right of any page, with the email address on your account.",
        "\u5728\u4efb\u610f\u9875\u9762\u53f3\u4e0a\u89d2\uff0c\u7528\u4f60\u8d26\u6237\u7684\u90ae\u7bb1\u5730\u5740\u767b\u5f55\u3002",
        _APP_SIGNIN_URL, "Sign in", "\u767b\u5f55"),
    HelpAnswer("reach-a-person", "account",
        "How do I get help from a person?", "\u6211\u600e\u4e48\u8054\u7cfb\u771f\u4eba\u5ba2\u670d\uff1f",
        "Write to us from the support page. You get a reference number straight away and a reply by email.",
        "\u5728\u201c\u652f\u6301\u201d\u9875\u9762\u5199\u4fe1\u7ed9\u6211\u4eec\u3002\u4f60\u4f1a\u7acb\u5373\u62ff\u5230\u4e00\u4e2a\u5de5\u5355\u7f16\u53f7\uff0c\u56de\u590d\u901a\u8fc7\u90ae\u4ef6\u53d1\u9001\u3002",
        "support.html", "Support", "\u652f\u6301"),
    HelpAnswer("after-i-write-in", "account",
        "What happens after I send a support message?", "\u63d0\u4ea4\u5ba2\u670d\u4fe1\u606f\u4e4b\u540e\u4f1a\u600e\u6837\uff1f",
        "We store it, show you a reference number, and email you a copy of what you wrote.",
        "\u6211\u4eec\u4f1a\u4fdd\u5b58\u4f60\u7684\u4fe1\u606f\u3001\u7ed9\u4f60\u4e00\u4e2a\u5de5\u5355\u7f16\u53f7\uff0c\u5e76\u628a\u4f60\u5199\u7684\u5185\u5bb9\u6284\u9001\u5230\u4f60\u7684\u90ae\u7bb1\u3002"),
    HelpAnswer("report-something-wrong", "platform",
        "Can I report something that looks wrong?", "\u6211\u53ef\u4ee5\u53cd\u9988\u770b\u8d77\u6765\u4e0d\u5bf9\u7684\u5730\u65b9\u5417\uff1f",
        "Yes. Pick \"Something is broken\" on the support form and tell us the page and what you saw.",
        "\u53ef\u4ee5\u3002\u5728\u652f\u6301\u8868\u5355\u91cc\u9009\u201c\u6709\u529f\u80fd\u574f\u4e86\u201d\uff0c\u544a\u8bc9\u6211\u4eec\u662f\u54ea\u4e2a\u9875\u9762\u3001\u4f60\u770b\u5230\u4e86\u4ec0\u4e48\u3002",
        "support.html", "Support", "\u652f\u6301"),
    HelpAnswer("email-and-marketing", "account",
        "Will you send me marketing email?", "\u4f60\u4eec\u4f1a\u7528\u6211\u7684\u90ae\u7bb1\u53d1\u8425\u9500\u90ae\u4ef6\u5417\uff1f",
        "Only while you leave marketing email switched on. Every marketing email carries an unsubscribe link.",
        "\u53ea\u6709\u5728\u4f60\u4fdd\u7559\u8425\u9500\u90ae\u4ef6\u5f00\u5173\u65f6\u624d\u4f1a\u3002\u6bcf\u5c01\u8425\u9500\u90ae\u4ef6\u90fd\u5e26\u6709\u9000\u8ba2\u94fe\u63a5\u3002"),
    HelpAnswer("why-a-dash", "research",
        "Why does a page show a dash instead of a number?", "\u4e3a\u4ec0\u4e48\u6709\u7684\u5730\u65b9\u663e\u793a\u4e00\u6761\u6a2a\u7ebf\u800c\u4e0d\u662f\u6570\u5b57\uff1f",
        "A dash means the number is not available yet. A zero always means a real zero.",
        "\u6a2a\u7ebf\u8868\u793a\u8fd9\u4e2a\u6570\u5b57\u76ee\u524d\u8fd8\u6ca1\u6709\u3002\u96f6\u5c31\u662f\u771f\u7684\u96f6\u3002"),
    HelpAnswer("what-changed-recently", "platform",
        "How do I see what changed recently?", "\u6211\u600e\u4e48\u77e5\u9053\u6700\u8fd1\u6709\u4ec0\u4e48\u53d8\u5316\uff1f",
        "The \"What changed\" list on this page is dated, newest first, and covers changes you can see.",
        "\u672c\u9875\u7684\u201c\u66f4\u65b0\u8bb0\u5f55\u201d\u6309\u65e5\u671f\u5012\u5e8f\u6392\u5217\uff0c\u53ea\u5217\u51fa\u4f60\u80fd\u770b\u5230\u7684\u53d8\u5316\u3002"),
)


def help_answers_view_model(root: Path, answers: Iterable[HelpAnswer] = HELP_ANSWERS) -> dict[str, Any]:
    """Validate then project. Always returns ``answers_state`` and ``answers``."""
    root = Path(root)
    answers = tuple(answers)
    seen_ids: set[str] = set()
    for a in answers:
        if not isinstance(a, HelpAnswer):
            raise ValueError("HELP_ANSWERS entries must be HelpAnswer instances")
        if not _is_nonempty_text(a.id) or not _ID_RE.fullmatch(a.id):
            raise ValueError(f"help answer {a.id!r}: id must be unique kebab-case")
        if a.id in seen_ids:
            raise ValueError(f"duplicate help answer id: {a.id}")
        seen_ids.add(a.id)
        if a.category not in _CATEGORIES_BY_ID:
            raise ValueError(f"help answer {a.id!r}: category is not in the shared vocabulary")
        for field, value in (("question_en", a.question_en), ("question_zh", a.question_zh),
                              ("answer_en", a.answer_en), ("answer_zh", a.answer_zh)):
            if not _is_nonempty_text(value):
                raise ValueError(f"help answer {a.id!r}: {field} must be non-empty")
        if a.question_zh == a.question_en:
            raise ValueError(f"help answer {a.id!r}: question_zh must differ from question_en")
        if a.answer_zh == a.answer_en:
            raise ValueError(f"help answer {a.id!r}: answer_zh must differ from answer_en")
        if a.href is not None:
            if not _is_approved_href(a.href):
                raise ValueError(f"help answer {a.id!r}: unapproved href")
            if not _is_nonempty_text(a.link_en) or not _is_nonempty_text(a.link_zh):
                raise ValueError(f"help answer {a.id!r}: href set without link_en/link_zh")
            if a.href != _APP_SIGNIN_URL:
                target = Path(urlsplit(a.href).path)
                template = root / "templates" / f"{target.as_posix()}.j2"
                if not template.is_file():
                    raise ValueError(f"help answer {a.id!r}: target template is unavailable: {template}")
        _check_banned_vocabulary(f"help answer {a.id!r}", a.question_en, a.question_zh)
        _check_banned_vocabulary(f"help answer {a.id!r}", a.answer_en, a.answer_zh)

    return {
        "answers_state": "published" if answers else "empty",
        "answers": [
            {"id": a.id, "category": a.category, "question_en": a.question_en, "question_zh": a.question_zh,
             "answer_en": a.answer_en, "answer_zh": a.answer_zh, "href": a.href,
             "link_en": a.link_en, "link_zh": a.link_zh}
            for a in answers
        ],
    }


# --------------------------------------------------------------------------- #
# Product changelog (packet B-F13-3 / MO-PAID-088)
# --------------------------------------------------------------------------- #

_CHANGELOG_SCHEMA = "mastermind.product_changelog.v1"
_CHANGELOG_EMPTY_EN = ("No changes are listed yet. Entries appear here once a change "
                        "you can see goes live.")
_CHANGELOG_EMPTY_ZH = "\u76ee\u524d\u8fd8\u6ca1\u6709\u66f4\u65b0\u8bb0\u5f55\u3002\u4f60\u80fd\u770b\u5230\u7684\u6539\u52a8\u4e0a\u7ebf\u540e\u624d\u4f1a\u51fa\u73b0\u5728\u8fd9\u91cc\u3002"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def product_changelog(root: Path, *, limit: int = 20) -> dict[str, Any]:
    """Read data/product/changelog.yml. Always returns state/entries/note_en/note_zh."""
    import yaml  # noqa: PLC0415

    path = Path(root) / "data" / "product" / "changelog.yml"
    if not path.is_file():
        return {"state": "empty", "entries": [], "note_en": _CHANGELOG_EMPTY_EN, "note_zh": _CHANGELOG_EMPTY_ZH}

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if doc.get("schema") != _CHANGELOG_SCHEMA:
        raise ValueError(f"changelog: schema must be {_CHANGELOG_SCHEMA!r}")
    note_en = doc.get("note_en")
    note_zh = doc.get("note_zh")
    if not _is_nonempty_text(note_en) or not _is_nonempty_text(note_zh):
        raise ValueError("changelog: note_en/note_zh must be non-empty")
    _check_banned_vocabulary("changelog note", note_en, note_zh)
    raw_entries = doc.get("entries") or []
    seen_ids: set[str] = set()
    entries: list[dict[str, Any]] = []
    for e in raw_entries:
        eid = e.get("id")
        if not _is_nonempty_text(eid):
            raise ValueError("changelog entry: id must be non-empty")
        if eid in seen_ids:
            raise ValueError(f"changelog: duplicate entry id {eid!r}")
        seen_ids.add(eid)
        date = e.get("date")
        if hasattr(date, "isoformat") and not isinstance(date, str):
            date = date.isoformat()
        if not isinstance(date, str) or not _ISO_DATE_RE.fullmatch(date):
            raise ValueError(f"changelog entry {eid!r}: date must be ISO YYYY-MM-DD")
        pr = e.get("pr")
        if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
            raise ValueError(f"changelog entry {eid!r}: pr must be a positive int")
        en, zh = e.get("en"), e.get("zh")
        if not _is_nonempty_text(en) or not _is_nonempty_text(zh):
            raise ValueError(f"changelog entry {eid!r}: en/zh must be non-empty")
        if zh == en:
            raise ValueError(f"changelog entry {eid!r}: zh must differ from en")
        _check_banned_vocabulary(f"changelog entry {eid!r}", en, zh)
        entries.append({"id": eid, "date": date, "pr": pr, "en": en, "zh": zh})

    entries.sort(key=lambda e: (e["date"], e["pr"]), reverse=True)
    return {"state": "published" if entries else "empty", "entries": entries[:limit],
            "note_en": note_en, "note_zh": note_zh}


# --------------------------------------------------------------------------- #
# Support routing by plan (packet B-F13-3 / MO-PAID-058)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class SupportPlan:
    id: str
    queue: str
    name_en: str
    name_zh: str
    promise_en: str
    promise_zh: str


SUPPORT_PLANS: tuple[SupportPlan, ...] = (
    SupportPlan("free", "community", "Free", "\u514d\u8d39",
        "Ask on this page, or write to support. We read every message and reply by email within three working days.",
        "\u5728\u672c\u9875\u67e5\u770b\u89e3\u7b54\uff0c\u6216\u5199\u4fe1\u7ed9\u5ba2\u670d\u3002\u6211\u4eec\u4f1a\u9605\u8bfb\u6bcf\u4e00\u6761\u4fe1\u606f\uff0c\u5e76\u5728\u4e09\u4e2a\u5de5\u4f5c\u65e5\u5185\u901a\u8fc7\u90ae\u4ef6\u56de\u590d\u3002"),
    SupportPlan("essential", "priority", "Essential", "\u6807\u51c6\u7248",
        "Your message goes to the priority queue. We aim to reply by email within one working day.",
        "\u4f60\u7684\u4fe1\u606f\u4f1a\u8fdb\u5165\u4f18\u5148\u961f\u5217\u3002\u6211\u4eec\u7684\u76ee\u6807\u662f\u5728\u4e00\u4e2a\u5de5\u4f5c\u65e5\u5185\u901a\u8fc7\u90ae\u4ef6\u56de\u590d\u3002"),
    SupportPlan("pro", "priority", "Pro", "\u4e13\u4e1a\u7248",
        "Your message goes to the priority queue and is looked at first. We aim to reply by email the same working day.",
        "\u4f60\u7684\u4fe1\u606f\u4f1a\u8fdb\u5165\u4f18\u5148\u961f\u5217\u5e76\u4f18\u5148\u67e5\u770b\u3002\u6211\u4eec\u7684\u76ee\u6807\u662f\u5728\u5f53\u4e2a\u5de5\u4f5c\u65e5\u5185\u56de\u590d\u3002"),
)
for _p in SUPPORT_PLANS:
    _check_banned_vocabulary(f"support plan {_p.id!r} name", _p.name_en, _p.name_zh)
    _check_banned_vocabulary(f"support plan {_p.id!r} promise", _p.promise_en, _p.promise_zh)
del _p

_PLANS_BY_ID = {p.id: p for p in SUPPORT_PLANS}

_TIER_TO_PLAN = {"free": "free", "essential": "essential", "insider": "essential",
                 "pro": "pro", "unlimited": "pro"}

_NOTE_SIGNED_OUT = ("You were not signed in, so this went to the general queue.",
                    "\u4f60\u5f53\u65f6\u672a\u767b\u5f55\uff0c\u56e0\u6b64\u8fd9\u6761\u4fe1\u606f\u8fdb\u5165\u4e86\u666e\u901a\u961f\u5217\u3002")
_NOTE_READ_FAILED = ("We could not read your plan just now, so this went to the general queue. "
                     "If you pay for a plan, reply to the receipt and we will move it.",
                     "\u6211\u4eec\u6682\u65f6\u8bfb\u4e0d\u5230\u4f60\u7684\u65b9\u6848\uff0c\u56e0\u6b64\u8fd9\u6761\u4fe1\u606f\u8fdb\u5165\u4e86\u666e\u901a\u961f\u5217\u3002\u5982\u679c\u4f60\u5df2\u4ed8\u8d39\uff0c\u8bf7\u56de\u590d\u6536\u636e\u90ae\u4ef6\uff0c\u6211\u4eec\u4f1a\u8f6c\u5230\u4f18\u5148\u961f\u5217\u3002")
_NOTE_UNRECOGNISED = ("Your plan was not recognised, so this went to the general queue.",
                      "\u65e0\u6cd5\u8bc6\u522b\u4f60\u7684\u65b9\u6848\uff0c\u56e0\u6b64\u8fd9\u6761\u4fe1\u606f\u8fdb\u5165\u4e86\u666e\u901a\u961f\u5217\u3002")


def route_for_tier(tier: str | None, *, tier_known: bool = True) -> dict[str, Any]:
    """Pure. Always returns plan_id, queue, plan_read, promise_en/zh, note_en/zh."""
    if tier is not None:
        plan_id = _TIER_TO_PLAN.get(tier)
        if plan_id is not None:
            plan = _PLANS_BY_ID[plan_id]
            return {"plan_id": plan.id, "queue": plan.queue, "plan_read": True,
                    "promise_en": plan.promise_en, "promise_zh": plan.promise_zh,
                    "note_en": None, "note_zh": None}
        note_en, note_zh = _NOTE_UNRECOGNISED
    elif not tier_known:
        note_en, note_zh = _NOTE_READ_FAILED
    else:
        note_en, note_zh = _NOTE_SIGNED_OUT

    free = _PLANS_BY_ID["free"]
    return {"plan_id": free.id, "queue": free.queue, "plan_read": False,
            "promise_en": free.promise_en, "promise_zh": free.promise_zh,
            "note_en": note_en, "note_zh": note_zh}


def support_routing_view_model() -> dict[str, Any]:
    return {"support_plans": [
        {"id": p.id, "state": "ok", "name_en": p.name_en, "name_zh": p.name_zh,
         "promise_en": p.promise_en, "promise_zh": p.promise_zh}
        for p in SUPPORT_PLANS
    ]}
