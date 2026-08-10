#!/usr/bin/env python3
"""Generate the W-L1 provisional board mockups.

Self-contained HTML per (lang, theme). Token layer + .pvcard CSS are sliced
VERBATIM out of the real templates so the mockup cannot drift from production.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "mockups" / "refs" / "breathing-platform"
OUT.mkdir(parents=True, exist_ok=True)

theme_css = (ROOT / "templates" / "theme.css").read_text()
card_j2 = (ROOT / "templates" / "_prophet_card.html.j2").read_text()

# ---- token layer: :root .. end of the ink-token block (theme.css 21..276) ----
# Line-indexed slices, so they move whenever theme.css does. Re-anchored 2026-08-09
# when the W-L1 --prov/--prov-ink pair landed in the ink block (+14 lines); the pair now
# falls INSIDE the TOKENS slice, which is the point — the mockup then reads the shipped
# token rather than its own copy of it and the two cannot drift.
# Re-anchored again 2026-08-10 (+15) for the --ink-pv-near comment, and a third time
# the same day (+15 again) for the dark --ink-pv-avoid rung. Note the pattern:
# these indices move on PROSE edits inside the token block, not just structural ones,
# and this file's comment density makes that routine — expect to re-anchor on most
# theme.css token edits. The asserts are what keep that loud instead of silent.
# Re-anchor by CONTENT, then prove it: the relocated slices must differ from the old
# ones only by the edit you intended (LANGCSS byte-identical), or the anchors have
# skidded onto a different block and the mockup will quietly render the wrong tokens.
tl = theme_css.splitlines()
assert tl[275].lstrip().startswith("--prov-ink"), "TOKENS slice moved — re-anchor it"
TOKENS = "\n".join(tl[20:276])
# language visibility toggle + CJK face + body font
assert tl[290].startswith("/* ---- language visibility"), "LANGCSS slice moved — re-anchor it"
LANGCSS = "\n".join(tl[290:301] + tl[326:330])

# ---- .pvcard CSS verbatim from the partial's pv_css() macro ----
m = re.search(r"\{% macro pv_css\(\) %\}\s*<style>(.*?)</style>\s*\{% endmacro %\}", card_j2, re.S)
PVCSS = m.group(1)
# strip jinja comments {# ... #} — they are documentation, not CSS
PVCSS = re.sub(r"\{#.*?#\}", "", PVCSS, flags=re.S)

PANEL = """
html body{background:var(--bg);color:var(--text);margin:0;padding:26px 22px 40px;font-size:15px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
h2{font-size:17px;margin:0;letter-spacing:.01em}
.muted{color:var(--muted)}
.nbgrid{display:grid;gap:12px;margin-top:12px}
.mk-lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);
  margin:30px 0 8px;font-weight:800;display:flex;align-items:center;gap:10px}
.mk-lbl::after{content:"";flex:1;height:1px;background:var(--line)}
.mk-lbl:first-child{margin-top:0}
.help{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;
  border-radius:50%;border:1px solid color-mix(in srgb,var(--muted) 45%,transparent);
  color:var(--muted);font-size:9px;font-weight:800;cursor:help;flex:none;line-height:1}
"""

# ══════════════════════════════════════════════════════════════════════════════
# THE NEW SURFACE — W-L1 board-state stamp. This block is the spec's CSS.
# ══════════════════════════════════════════════════════════════════════════════
NEW = """
/* ═══ W-L1 BOARD STATE STAMP ═══════════════════════════════════════════════
   ONE axis, asked once: where does this board stand relative to the nightly
   board of record?
     data-boardstate="ahead"   provisional blue, DASHED  — built from today's
                               close; the overnight pass has not countersigned it
     data-boardstate="behind"  muted, SOLID              — the record did not
                               arrive (or the market is shut); this is the last
                               confirmed board
     attribute ABSENT          no stamp at all           — the board IS the record
   Absence is the third state and it is load-bearing: the stamp appears only when
   the board is NOT the current record, so a reader never has to read a badge to
   learn that nothing is unusual.

   Dashed=pending is not invented here — .pv-trg-soon already ships it for the
   'imminent' trigger chip. The blue is the P1 provisional hue (.pv-live --plvc)
   reused ON PURPOSE: the ◐ strip above and this stamp name the SAME epistemic
   tier — settled by the tape, not yet by the record — and a second vocabulary
   for one idea is a tax on the reader. Do not give this its own hue.
   NOT a directional token, so 红涨绿跌 holds by construction. */
/* Two tokens, following theme.css's own --ink-* convention exactly: --prov is
   the FILL-grade hue (tints, rules, borders), --prov-ink is the TEXT-grade one.
   Dark keeps ink ≡ raw so dark renders byte-identical to a single-token version;
   light deepens toward --text, because the fill-grade blue measured 4.22:1 as
   type on its own 11% tint over white — under AA, and invisible to anyone who
   only ever looked at the dark shot. (Doctrine §5.8: light is a design target,
   not a translation.) Measured after: 5.05:1 light / 5.35:1 dark. */
:root{--prov:#62a0e8;--prov-ink:var(--prov)}
html[data-theme="light"]{--prov:#2f6fd0;
  --prov-ink:color-mix(in srgb,var(--prov) 82%,var(--text))}

.pbs{display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:800;
  letter-spacing:.06em;text-transform:uppercase;line-height:1.35;padding:2.5px 9px;
  border-radius:6px;white-space:nowrap;flex:none}
/* squarer than the board's 999px pills on purpose: this is a stamp on the whole
   board, not another chip in the chip row. 6px matches the .pv-mk marks family. */
.pbs-ahead{color:var(--prov-ink);background:color-mix(in srgb,var(--prov) 11%,transparent);
  border:1px dashed color-mix(in srgb,var(--prov) 62%,transparent)}
.pbs-behind{color:var(--muted);background:color-mix(in srgb,var(--muted) 9%,transparent);
  border:1px solid color-mix(in srgb,var(--muted) 34%,transparent)}
.pbs-dt{font-variant-numeric:tabular-nums}

/* THE UNSEALED EDGE — the one place this design spends boldness.
   A board-level state has to survive a full-page scroll-past, and the house has
   already measured that a header chip alone does not (the .pv-featured note:
   a rim treatment ALONE vanished in a dense grid). So the panel's own top edge
   goes perforated while the board is uncountersigned. Long dash (15/9), never a
   fine dot — a fine dotted line reads as a broken border, a long dash reads as
   a deliberate perforation. Costs zero height: it rides the existing 1px border.
   Static by choice: 15 cards and a strip that already animates its rows in are
   enough movement on this page, so there is no animation here and therefore no
   prefers-reduced-motion kill block to keep in sync. */
.panel[data-boardstate]{position:relative}
.panel[data-boardstate="ahead"]::before{content:"";position:absolute;left:-1px;right:-1px;top:-1px;
  height:2px;border-radius:14px 14px 0 0;pointer-events:none;
  background:repeating-linear-gradient(90deg,
    color-mix(in srgb,var(--prov) 78%,transparent) 0 15px,transparent 15px 24px)}

/* SLOT B — one line under the header. Three mutually exclusive contents
   (provisional stance / confirmation receipt / last-confirmed stance), never
   two at once, so the panel header height moves by at most one line and the
   board below never shoves. NOT a second footnote: .pb-fn stays the panel's
   single permanent methodology note (doctrine Law 4, one footnote per panel).
   Deliberately NOT .nb-stale-note's amber-on-tint banner: this is quiet
   honesty, not a caution — no fill, no border, muted ink. */
/* text-wrap:pretty is load-bearing, not polish: without it the trailing `?`
   help icon wrapped alone onto a second line on the two longest notes, which
   reads as a stray glyph rather than as the receipt handle for the sentence
   above it. */
.pbs-note{font-size:11.5px;line-height:1.5;margin:7px 0 1px;color:var(--muted);
  max-width:94ch;text-wrap:pretty}
.pbs-note b{font-weight:700;color:var(--text)}
.pbs-fig{font-variant-numeric:tabular-nums;font-weight:700;color:var(--text)}
.pbs-note .help{margin-left:5px;vertical-align:1px}

/* PER-CARD DELTA — exactly one new marks kind. 'Confirmed' is deliberately NOT
   a chip: it is the other N-1 cards, and a constant belongs in the receipt line
   once, never stamped N times (doctrine Law 4 — the vetoed "T+1 58% fade on
   every row" defect). Overnight ADDITIONS need no new kind either; they are new
   to the board and the existing 'new' mark already says so.

   DESATURATED ON PURPOSE (caught in the first render): at the marks row's full
   formula — color-mix(<hue> 58%, --text) on a 12% tint — this chip came out the
   same blue as .pv-mk-new, which sits inches away on the same board and means
   something completely different ("new to the board" is a signal; "adjusted" is
   a receipt). Two meanings in one hue is a defect no amount of wording fixes.
   The fix is weight, not hue: 'adjusted' resolves toward --muted so it reads as
   the quietest thing in the row, while --new keeps the saturated --info. That
   also matches what the mark is worth to the reader — the honest answer to "so
   what do I do" here is nothing, the card already shows the updated numbers. */
.pv-mk-adj{font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:color-mix(in srgb,var(--prov-ink) 42%,var(--muted));
  background:color-mix(in srgb,var(--prov) 7%,transparent);
  border-color:color-mix(in srgb,var(--prov) 30%,transparent)}

@media (max-width:680px){
  .pbs{font-size:9.5px;padding:2px 7px}
  .pbs-note{font-size:11px}
}
"""

# ---------------------------------------------------------------- copy table --
C = {
    "stamp_ahead":   ("◐ Tonight's picks", "◐ 今晚选股"),
    "stamp_behind":  ("Last confirmed", "上次确认"),
    "note_ahead":    (
        "<b>Get ready</b> — set from today's close, confirmed by morning.",
        "<b>可以开始准备</b> — 依今日收盘价选出，明早完成确认。"),
    "note_confirmed": (
        '<span class="pbs-fig">13</span> of <span class="pbs-fig">15</span> confirmed overnight '
        '· <span class="pbs-fig">1</span> adjusted, <span class="pbs-fig">1</span> left the board',
        '<span class="pbs-fig">15</span> 只中 <span class="pbs-fig">13</span> 只隔夜确认 '
        '· 调整 <span class="pbs-fig">1</span> 只，离榜 <span class="pbs-fig">1</span> 只'),
    "note_behind": (
        "Tonight's early update isn't in — these are last night's confirmed picks. "
        "Check a live quote before you act.",
        "今晚的提前更新未到位，以下为昨晚确认的选股名单。操作前请先看一下实时报价。"),
    "note_closed": (
        "Markets are closed — these are the last confirmed picks. "
        "The board updates after the next session's close.",
        "休市中，以下为最近一次确认的选股名单。下一个交易日收盘后更新。"),
    "h2":       ("Prophet Stock Signals", "先知选股"),
    "sub":      ("15 shown · 93 setups · green dot = entry open, yellow = wait for pullback.",
                 "已显示 15 · 93 个形态 · 绿点＝现在可入场，黄点＝等回调。"),
    "mk_adj":   ("Adjusted", "已调整"),
    "mk_feat":  ("★ Featured", "★ 精选"),
    "mk_new":   ("New", "新增"),
}

STATE_LBL = {
    "s1": ("STATE 1 — EVENING PROVISIONAL  ·  ~17:30–18:30 ET, until the nightly lands",
           "状态 1 — 傍晚临时榜"),
    "s2": ("STATE 2 — POST-NIGHTLY CONFIRMATION  ·  next morning",
           "状态 2 — 隔夜确认后"),
    "s3": ("STATE 3 — EARLY UPDATE DIDN'T LAND  ·  falls back to the last confirmed board",
           "状态 3 — 提前更新未到位"),
    "s4": ("STATE 4 — WEEKEND / HOLIDAY", "状态 4 — 休市"),
}


def t(key, lang):
    return C[key][1 if lang == "zh" else 0]


SPARK = ('<svg viewBox="0 0 240 74" preserveAspectRatio="none">'
         '<polyline fill="none" stroke-width="1.6" points="{pts}"/></svg>')


def spark(seed):
    import math
    pts = []
    for i in range(41):
        x = i * 6
        y = 52 - 22 * math.sin((i + seed) / 7.0) - (i * 0.28 if seed % 2 else -i * 0.2)
        pts.append(f"{x},{max(6, min(68, y)):.1f}")
    return SPARK.format(pts=" ".join(pts))


VEN = {"buy": ("Buy", "买入"), "near": ("Near", "临近"), "wait": ("Wait", "等待")}

# ticker, name_en, name_zh, sector_en, sector_zh, verb, stage, edge, px, zone, date, marks
ROWS = [
    ("NVDA", "NVIDIA", "英伟达", "Semiconductors", "半导体", "buy", 4, "82", "182.44", ("active", "168.20", "176.90"), "08-08", ["feat"]),
    ("ROIV", "Roivant Sciences", "罗益万科学", "Biotechnology", "生物科技", "buy", 3, "77", "14.86", ("active", "13.90", "14.60"), "08-08", ["feat"]),
    ("XPEL", "XPEL Inc", "XPEL", "Auto Components", "汽车零部件", "near", 3, "71", "38.12", ("muted", "35.40", "36.80"), "08-08", []),
    ("SOUN", "SoundHound AI", "声猎人工智能", "Software", "软件", "buy", 4, "69", "11.03", ("active", "10.10", "10.70"), "08-08", ["feat"]),
    ("NGVT", "Ingevity", "英力士", "Specialty Chemicals", "特种化工", "wait", 2, "63", "51.77", ("confirm",), "08-08", []),
    ("VSEC", "VSE Corporation", "VSE 公司", "Aerospace & Defense", "航空国防", "near", 3, "61", "128.40", ("muted", "119.00", "124.50"), "08-08", []),
    ("GPCR", "Structure Therapeutics", "结构治疗", "Biotechnology", "生物科技", "wait", 2, "58", "27.35", ("confirm",), "08-08", []),
    ("CTS", "CTS Corporation", "CTS 公司", "Electronic Equipment", "电子设备", "wait", 1, "54", "46.90", ("none",), "08-08", []),
]


def card(r, lang, marks_override=None, date_override=None):
    tk, nm_en, nm_zh, sec_en, sec_zh, verb, stage, edge, px, zone, date, marks = r
    marks = marks_override if marks_override is not None else marks
    # A board that fell back to the last confirmed night is showing THAT night's
    # cards, so their as-of stamps must read that night too. A crop whose stamp
    # says "last confirmed Aug 7" over cards dated Aug 8 teaches the builder a
    # contradiction — and the crop is the spec.
    date = date_override or date
    nm = nm_zh if lang == "zh" else nm_en
    sec = sec_zh if lang == "zh" else sec_en
    v = VEN[verb][1 if lang == "zh" else 0]
    cls = f"pvcard pv-{verb}" + (" pv-featured" if "feat" in marks else "")

    mk = ""
    for k in marks:
        if k == "feat":
            mk += f'<span class="pv-mk-i pv-mk-feat">{t("mk_feat", lang)}</span>'
        elif k == "new":
            mk += f'<span class="pv-mk-i pv-mk-new">{t("mk_new", lang)}</span>'
        elif k == "adj":
            mk += f'<span class="pv-mk-i pv-mk-adj">{t("mk_adj", lang)}</span>'
    mkrow = f'<div class="pv-mk">{mk}</div>'

    stp = ""
    for i in (1, 2, 3, 4):
        if i > 1:
            stp += f'<span class="pv-seg{" pa" if stage >= i else ""}"></span>'
        stp += f'<span class="pv-dot{" on" if stage == i else (" pa" if stage > i else "")}"></span>'

    lbls = [("Bottoming", "筑底"), ("Turning", "转向"), ("Ready", "就绪"), ("Trend", "趋势")]
    stl = "".join(
        f'<span{" class=\"on\"" if stage == i + 1 else ""}>{L[1 if lang == "zh" else 0]}</span>'
        for i, L in enumerate(lbls))

    zl, zh_ = ("买区", "回补") if lang == "zh" else ("Zone", "Re-add")
    if zone[0] == "active":
        zn = f'<span class="pv-znl">{zl}</span><span class="pv-znr">{zone[1]}–{zone[2]}</span>'
    elif zone[0] == "muted":
        zn = f'<span class="pv-znl">{zl}</span><span class="pv-znm">{zone[1]}–{zone[2]}</span>'
    elif zone[0] == "confirm":
        zn = f'<span class="pv-znm">{"买区待确认后生成" if lang == "zh" else "Zone sets on confirmation"}</span>'
    else:
        zn = f'<span class="pv-znm">{"无买区 — 观望" if lang == "zh" else "No zone — stand aside"}</span>'

    MN = {"08": "Aug", "07": "Jul"}
    dt = date if lang == "zh" else f'{MN[date[:2]]} {int(date[3:])}'
    edl = "优势" if lang == "zh" else "Edge"

    return f'''<a class="{cls}" href="#">
  <div class="pv-chart">{spark(len(tk) + stage)}
    <span class="pv-ov pv-ovl"><span class="pv-chip">{v}</span><span class="pv-live" hidden></span></span>
    <span class="pv-ov pv-ovr"><span class="nb-px pv-px">{px}</span></span>
  </div>
  <div class="pv-bd">
    <div class="pv-hd"><span class="pv-idw"><span class="pv-tk">{tk}</span><span class="pv-nm">{nm}</span></span>
      <span class="pv-edge"><span class="pv-edl">{edl}</span><span class="pv-edn">{edge}</span></span></div>
    <div class="pv-ind">{sec}</div>
    {mkrow}
    <div class="pv-stp">{stp}</div>
    <div class="pv-stl">{stl}</div>
  </div>
  <div class="pv-zn">{zn}<span class="pv-dt">{dt}</span></div>
</a>'''


def board(state, lang):
    """One panel in one of the four states."""
    if state == "s1":
        attr, stamp = ' data-boardstate="ahead"', f'<span class="pbs pbs-ahead">{t("stamp_ahead", lang)}</span>'
        note = t("note_ahead", lang)
        rows = [(r, None, None) for r in ROWS]
    elif state == "s2":
        attr, stamp = "", ""
        note = t("note_confirmed", lang)
        rows = []
        for i, r in enumerate(ROWS):
            if i == 2:
                rows.append((r, r[11] + ["adj"], None))
            elif i == 5:
                rows.append((r, ["new"], None))
            else:
                rows.append((r, None, None))
    elif state == "s3":
        d = "08-07" if lang == "zh" else "Aug 7"
        attr = ' data-boardstate="behind"'
        stamp = f'<span class="pbs pbs-behind">{t("stamp_behind", lang)} · <span class="pbs-dt">{d}</span></span>'
        note = t("note_behind", lang)
        rows = [(r, None, "08-07") for r in ROWS]
    else:
        d = "08-07" if lang == "zh" else "Aug 7"
        attr = ' data-boardstate="behind"'
        stamp = f'<span class="pbs pbs-behind">{t("stamp_behind", lang)} · <span class="pbs-dt">{d}</span></span>'
        note = t("note_closed", lang)
        rows = [(r, None, "08-07") for r in ROWS]

    cards = "\n".join(card(r, lang, mo, do) for r, mo, do in rows)
    return f'''<div class="panel span12"{attr}>
  <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
    <h2>{t("h2", lang)}</h2>
    {stamp}
    <span class="muted" style="font-size:11.5px">{t("sub", lang)}<span class="help">?</span></span>
  </div>
  <div class="pbs-note">{note}<span class="help">?</span></div>
  <div class="nbgrid">
{cards}
  </div>
</div>'''


def page(lang, theme):
    secs = ""
    for s in ("s1", "s2", "s3", "s4"):
        secs += f'<div class="mk-lbl">{STATE_LBL[s][1 if lang == "zh" else 0]}</div>\n{board(s, lang)}\n'
    return f'''<!doctype html>
<html lang="{'zh' if lang == 'zh' else 'en'}" data-theme="{theme}" data-lang="{lang}">
<head><meta charset="utf-8"><title>W-L1 provisional board — {lang} {theme}</title>
<style>
{TOKENS}
{LANGCSS}
{PANEL}
{PVCSS}
{NEW}
</style></head>
<body>
{secs}
</body></html>'''


for lang in ("en", "zh"):
    for theme in ("dark", "light"):
        p = OUT / f"wl1_board_{lang}_{theme}.html"
        p.write_text(page(lang, theme))
        print("wrote", p)
