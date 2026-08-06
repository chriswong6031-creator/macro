"""A post must never carry another company's chart.

THE LIVE DEFECT (operator, 2026-08-05). The flagship posted

    $DVN 45.1. Signals are lining up, which is rare for anything in this
    group. I'm watching.

over a chart of RMBS. A reader spotted it ("It is not DAN'S chart?"), which is
the only reason anyone knew.

THE CAUSE, proven from git rather than reasoned about: `chart_id` is the whole
storage key -- media_publish writes `<as_of>/<chart_id>.svg` and uploads the PNG
to the matching public path -- but content_studio's `chart_id_counter` restarted
at 1 on every run. The second content_studio run of a day therefore re-minted
chart-001, chart-002 ... and overwrote the first run's artifacts at the same
paths and the same URLs. `chart-088.svg` was committed as DVN at 09:38Z and
rewritten as RMBS at 16:34Z, same path, same day. The outbox item was correct
the entire time, which is why no metadata check could have seen this.

THE BLAST RADIUS the gate found once it existed: nine posts, four days, three
accounts (flagship EQT/CBOE and ROST/SONO, sophia MSFT/VST, TEL/NRG, ARES/SHW,
ROST/DG, LKFN/BFB, meagan AMCR/AMZN, flagship DVN/RMBS). One was noticed.

TWO HALVES, ONE PER TEST CLASS:
  TestNextChartId       the cause -- the day's id namespace is append-only, so a
                        later run cannot land on an earlier run's key.
  TestCardTickerGate    the class -- the publisher refuses a card that names a
                        symbol other than the one the post claims, whatever
                        future cause produces it.
"""
from __future__ import annotations

from engine.marketing.content_studio import _next_chart_id
from engine.marketing.media_publish import card_symbols, card_ticker_mismatch


def _card(*symbols: str) -> str:
    """Minimal card markup: the symbol as a drawn text node, like every renderer."""
    body = "".join(f'<text x="1" y="1">{s}</text>' for s in symbols)
    return f'<svg xmlns="http://www.w3.org/2000/svg">{body}<text>140.00</text></svg>'


class TestNextChartId:
    def test_an_empty_day_starts_at_one(self, tmp_path):
        assert _next_chart_id(tmp_path, "2026-08-05") == 1

    def test_a_missing_directory_starts_at_one(self, tmp_path):
        assert _next_chart_id(tmp_path / "nope", "2026-08-05") == 1

    def test_it_resumes_above_the_highest_id_present(self, tmp_path):
        d = tmp_path / "data" / "marketing" / "outbox" / "media" / "2026-08-05"
        d.mkdir(parents=True)
        for name in ("chart-001.svg", "chart-088.svg", "chart-088.png",
                     "chart-007.svg"):
            (d / name).write_text("x")
        assert _next_chart_id(tmp_path, "2026-08-05") == 89

    def test_a_second_run_cannot_reuse_a_first_run_id(self, tmp_path):
        """THE REGRESSION. Two runs, one day: the second must not mint an id the
        first already wrote, because that overwrites the file the first run's
        queued items still point at."""
        d = tmp_path / "data" / "marketing" / "outbox" / "media" / "2026-08-05"
        d.mkdir(parents=True)
        run_one = []
        nxt = _next_chart_id(tmp_path, "2026-08-05")
        for _ in range(88):                       # run one mints 001..088
            run_one.append(f"chart-{nxt:03d}")
            (d / f"chart-{nxt:03d}.svg").write_text("x")
            nxt += 1
        assert "chart-088" in run_one
        run_two_first = f"chart-{_next_chart_id(tmp_path, '2026-08-05'):03d}"
        assert run_two_first not in run_one, (
            "the second run of the day re-minted an id the first run already "
            "wrote -- this is exactly the DVN/RMBS overwrite")

    def test_non_chart_files_are_ignored_not_guessed_at(self, tmp_path):
        d = tmp_path / "data" / "marketing" / "outbox" / "media" / "2026-08-05"
        d.mkdir(parents=True)
        (d / "hottape-sector_rout-oil-gas-e-p-1533Z.svg").write_text("x")
        (d / "chart-004.svg").write_text("x")
        assert _next_chart_id(tmp_path, "2026-08-05") == 5


class TestCardTickerGate:
    def test_it_fires_on_the_live_defect(self, tmp_path):
        p = tmp_path / "c.svg"
        p.write_text(_card("RMBS"))
        got = card_ticker_mismatch([{"ticker": "DVN", "path": "c.svg"}],
                                   root=tmp_path)
        assert got and "DVN" in got and "RMBS" in got

    def test_it_passes_the_matching_card(self, tmp_path):
        p = tmp_path / "c.svg"
        p.write_text(_card("RMBS"))
        assert card_ticker_mismatch([{"ticker": "RMBS", "path": "c.svg"}],
                                    root=tmp_path) is None

    def test_punctuation_does_not_split_a_symbol(self, tmp_path):
        (tmp_path / "c.svg").write_text(_card("BRK.B"))
        assert card_ticker_mismatch([{"ticker": "BRK-B", "path": "c.svg"}],
                                    root=tmp_path) is None

    # ── the three abstentions. Each one, if it fired, would quarantine a good
    #    post -- which is worse than the defect, because it is silent and daily.
    def test_absent_artifact_abstains(self, tmp_path):
        assert card_ticker_mismatch([{"ticker": "DVN", "path": "gone.svg"}],
                                    root=tmp_path) is None

    def test_an_unlabelled_card_abstains(self, tmp_path):
        """Older renderers draw no symbol at all. 'Does the claimed ticker
        appear' is unanswerable there, and absence is not disagreement."""
        (tmp_path / "c.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><text>140.00</text></svg>')
        assert card_ticker_mismatch([{"ticker": "DVN", "path": "c.svg"}],
                                    root=tmp_path) is None

    def test_a_pill_only_card_abstains(self, tmp_path):
        """A card whose only ticker-SHAPED token is a pill label must not read
        as 'names a symbol, and not yours'."""
        (tmp_path / "c.svg").write_text(_card("SETUP"))
        assert card_ticker_mismatch([{"ticker": "DVN", "path": "c.svg"}],
                                    root=tmp_path) is None

    def test_a_multi_name_card_is_skipped(self, tmp_path):
        """Sector/theme cards legitimately draw a subset of their members."""
        (tmp_path / "c.svg").write_text(_card("EOG", "FANG"))
        assert card_ticker_mismatch(
            [{"tickers": ["EOG", "DVN", "FANG"], "path": "c.svg"}],
            root=tmp_path) is None

    def test_symbols_in_attributes_do_not_vouch_for_a_card(self, tmp_path):
        """The symbol must be DRAWN. A match inside a URL or an attribute would
        let a footer link vouch for a chart it has nothing to do with."""
        (tmp_path / "c.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<a href="https://mastermind-x.com/DVN"><text>RMBS</text></a></svg>')
        assert card_ticker_mismatch([{"ticker": "DVN", "path": "c.svg"}],
                                    root=tmp_path) is not None

    def test_card_symbols_drops_chrome_and_keeps_symbols(self, tmp_path):
        got = card_symbols(_card("RMBS", "DAILY", "MACD", "SETUP"))
        assert got == {"RMBS"}
