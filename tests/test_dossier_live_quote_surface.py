"""The dossier surface may not claim freshness the served bytes do not have.

These are static-source assertions over the template and its client module.
They exist because the defect they pin was invisible to every runtime test:
the page rendered perfectly, the JSON was well-formed, nothing threw — and it
still told the reader a day-old price was live.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "ticker.html.j2"
CLIENT = ROOT / "site" / "assets" / "js" / "dossier-live-quote.js"


@pytest.fixture(scope="module")
def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client_text() -> str:
    if not CLIENT.exists():
        pytest.skip("site/ is not checked out in this sparse worktree")
    return CLIENT.read_text(encoding="utf-8")


# ── the stamp may not be minted from the build's own date ───────────────────

def test_stamp_does_not_ship_a_hard_coded_live_label(template_text: str) -> None:
    """`{% else %}...Live...` keyed off `stale` is the original defect."""
    assert "t('Live', '实时')" not in template_text
    assert 't("Live", "实时")' not in template_text


def test_stamp_ships_in_the_baked_state_and_names_its_date(template_text: str) -> None:
    assert 'data-dq-state="baked"' in template_text
    assert "t('As of ' ~ freshness, '截至 ' ~ freshness)" in template_text


def test_only_the_live_state_gets_the_pulsing_green_pip(template_text: str) -> None:
    """Decoration must not imply currency for any weaker state."""
    assert '.dq-stamp[data-dq-state="live"] .live-dot{background:var(--ok);' in template_text
    # every non-live state is explicitly de-animated
    assert ".dq-stamp[data-dq-state] .live-dot{background:var(--muted);box-shadow:none;animation:none;}" in template_text


# ── price ownership: one writer per node ────────────────────────────────────

def test_hero_and_sticky_price_left_the_shared_nb_px_race(template_text: str) -> None:
    """live.js owns .nb-px. The dossier price must not also be its target.

    Asserted on the BINDING, not the token: live.js selects
    ``.nb-px[data-sym]``, so a prose mention of the class is harmless while a
    live element carrying it is the race.
    """
    assert 'class="nb-px"' not in template_text, "dossier price is back in the shared live.js race"
    assert "nb-px" not in re.sub(r"\{#.*?#\}", "", template_text, flags=re.S), \
        "a non-comment nb-px binding survives"
    assert template_text.count('class="dq-px" data-dq-sym=') == 2, "expected hero + sticky"


def test_the_day_move_is_bound_not_static(template_text: str) -> None:
    assert "data-dq-abs" in template_text
    assert "data-dq-pct" in template_text
    assert "data-dq-chg" in template_text


def test_the_client_module_is_actually_loaded(template_text: str) -> None:
    assert re.search(r'src="\.\./assets/js/dossier-live-quote\.js\?v=', template_text)


# ── client honesty ──────────────────────────────────────────────────────────

def test_client_requires_both_realtime_feed_and_open_regular_session(client_text: str) -> None:
    assert "q.freshness === 'live' && q.session === 'regular'" in client_text


def test_client_keeps_baked_values_when_the_server_disowns_the_quote(client_text: str) -> None:
    assert "if (q.freshness === 'stale') { lapse(); return; }" in client_text


def test_a_lapsed_feed_stops_claiming_live(client_text: str) -> None:
    """A tab left open while the feed dies must not hold a green "Live".

    Keeping the last measured NUMBERS is right — they beat a day-old baked
    price — but the currency CLAIM beside them has expired, and holding it is
    the original defect in a different costume.
    """
    body = client_text[client_text.index("function lapse()"):]
    body = body[: body.index("function paint(")]
    assert "if (!painted || !stamp) return;" in body
    assert "stamp.setAttribute('data-dq-state', 'closed');" in body
    assert "LABELS.lapsed[0], LABELS.lapsed[1]" in body
    assert not re.search(r"\b(false|0)\s*&&", body), "lapse() is short-circuited off"
    assert re.search(r"lapsed: \['[^']+', '[^']+'\]", client_text)


def test_every_way_a_quote_can_stop_arriving_demotes_the_claim(client_text: str) -> None:
    """The blocker this pins: only a 200-marked-stale used to demote.

    A 503 (hub down), a 429 (throttled), a dropped connection and the abort
    timeout all produced `q === null` or a thrown fetch, so paint() never ran
    and the stamp kept whatever it last said — a pulsing green "Live" on a
    frozen price, indefinitely. The hub going down is the EXPECTED fault; a hub
    that stays up and self-reports stale is the rare one, and it was the only
    one handled.
    """
    # non-200 -> null -> lapse, and a thrown fetch -> lapse
    assert "if (q) { paint(q); } else { lapse(); }" in client_text
    catch_body = client_text[client_text.index(".catch(function ()"):]
    catch_body = catch_body[: catch_body.index("\n")]
    assert "lapse();" in catch_body, f"thrown fetch does not demote: {catch_body}"
    # the watchdog releases inflight AND demotes, with or without AbortController
    watchdog = client_text[client_text.index("var killer = setTimeout("):]
    watchdog = watchdog[: watchdog.index("function done()")]
    assert "inflight = false;" in watchdog
    assert "lapse();" in watchdog


def test_client_never_paints_a_quote_for_another_ticker(client_text: str) -> None:
    assert "q.ticker !== ticker" in client_text


def test_client_writes_price_and_move_together_or_not_at_all(client_text: str) -> None:
    """The guards must precede the first write, or a partial paint is possible."""
    first_write = client_text.index("priceNodes[i].textContent")
    for guard in (
        "if (!q || q.ticker !== ticker) { lapse(); return; }",
        "if (q.freshness === 'stale') { lapse(); return; }",
        "if (!isFiniteNumber(q.price) || q.price <= 0) { lapse(); return; }",
        "if (!isFiniteNumber(q.change_abs) || !isFiniteNumber(q.change_pct)) { lapse(); return; }",
    ):
        assert client_text.index(guard) < first_write, f"guard runs after the paint: {guard}"
    # Ordering alone is not enough: the writes themselves must be unconditional
    # once the guards pass. Disabling just the absNode write left a CURRENT
    # price beside the BAKED dollar move and a LIVE percent — three numbers from
    # two different moments — and every ordering assertion still passed.
    for write in (
        "if (absNode) absNode.textContent = fmtAbs(q.change_abs);",
        "if (pctNode) pctNode.textContent = fmtPct(q.change_pct);",
    ):
        assert write in client_text, f"move write missing or altered: {write}"


def test_the_live_reading_is_not_reachable_unconditionally(client_text: str) -> None:
    """`readingOf` must not be able to return live before its own condition.

    Inserting an unconditional `return {state:'live'}` as the first statement —
    leaving the asserted condition intact below it — made every session and
    every freshness print "Live", and the substring assertions all still passed.
    """
    body = client_text[client_text.index("function readingOf(q) {"):]
    body = body[: body.index("function lapse()")]
    first_stmt = body[body.index("{") + 1:].lstrip()
    assert first_stmt.startswith("if (q.freshness === 'live' && q.session === 'regular')"), (
        "the first statement of readingOf must be the live CONDITION, not a return"
    )
    # exactly one live-state return, and it lives inside that conditional
    assert body.count("state: 'live'") == 1


def test_the_52_week_bar_repaints_with_the_price(client_text: str) -> None:
    """A bar left baked places the NEW price at the OLD point on the scale."""
    assert "data-dq-lo" in client_text and "data-dq-hi" in client_text
    assert "fillEl.style.width" in client_text
    assert "dotEl.style.left" in client_text


def test_client_sets_both_languages_for_every_state(client_text: str) -> None:
    """A one-language write leaves the other showing the previous claim."""
    for key in ("live", "delayed", "pre", "post", "closed"):
        assert re.search(rf"{key}: \['[^']+', '[^']+'\]", client_text), key
    assert "enNode.textContent = en" in client_text
    assert "zhNode.textContent = zh" in client_text


def test_client_stands_down_without_fetch_instead_of_throwing(client_text: str) -> None:
    """A missing `fetch` throws synchronously, ahead of the promise chain.

    The `.catch` in poll() cannot see it, so the page would keep its correct
    baked values while logging an uncaught error on every tick.  The guard must
    therefore come BEFORE the first call site.
    """
    guard = "if (typeof window.fetch !== 'function'"
    assert guard in client_text
    assert client_text.index(guard) < client_text.index("fetch('/api/dossier-quote/")


def test_revealing_a_background_tab_reads_immediately(client_text: str) -> None:
    """A dossier opened in a background tab must not show baked bytes on reveal.

    `start()` used to bail on an existing timer.  A page loaded while hidden
    installs that timer, every tick no-ops on the hidden check, and the reveal
    then returned early — so the reader's first look got the baked price for up
    to a full poll period.
    """
    assert "if (timer) return;\n    poll();" not in client_text
    start_body = client_text[client_text.index("function start()"):]
    start_body = start_body[: start_body.index("function stop()")]
    assert "poll();" in start_body
    assert "if (!timer) timer = setInterval(poll, POLL_MS);" in start_body


def test_client_names_the_session_date_outside_regular_hours(client_text: str) -> None:
    """Upstream can hand back a PREVIOUS session's move; the reader is told."""
    assert "q.regular_session_date" in client_text
