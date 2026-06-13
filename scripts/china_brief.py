"""China daily brief — a plain, bilingual narrative for the A-share regime.

China parallel of scripts/daily_brief.py. Reads only stored outputs
(data/china_regime/latest.json), diffs against yesterday's snapshot for the
"what changed" section, frames the day against the measured calibration verdicts
(Growth-scare = robust contrarian bottom; expanding PBoC liquidity = tailwind;
the regime is risk context, not an allocation rule), and publishes
site/china_brief.html + reports/china-brief-<date>.md.

Bilingual: each composed line embeds parallel EN/中文 spans (markdown passes the
inline HTML through; theme.css toggles visibility on data-lang). Mechanical text
only — no LLM.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.i18n import tr  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("china_brief")

PREV = "brief_prev_state.json"
LIQ_ZH = {"expanding": "扩张", "contracting": "收缩", "neutral": "中性", "unknown": "未知"}
CYC_ZH = {"early": "早期", "mid": "中期", "late": "晚期", "unknown": "未知"}


def b(en: str, zh: str) -> str:
    """Inline bilingual span pair (markdown passes raw HTML through)."""
    return f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>'


def _load_latest() -> dict:
    return json.loads((config.data_dir() / "china_regime" / "latest.json").read_text())


def _load_prev() -> dict | None:
    p = config.data_dir() / "china_regime" / PREV
    return json.loads(p.read_text()) if p.exists() else None


def _save_state(latest: dict) -> None:
    state = {k: latest.get(k) for k in ("date", "quad", "quad_name", "growth_score",
                                        "inflation_score", "confidence", "liquidity_overlay")}
    state["ranks"] = {r["ticker"]: r["rank"] for r in latest.get("sector_rs", [])}
    (config.data_dir() / "china_regime" / PREV).write_text(json.dumps(state, indent=1))


def what_changed(latest: dict, prev: dict | None) -> list[str]:
    if prev is None:
        return [b("First brief — day-over-day change tracking starts tomorrow.",
                  "首份简报 — 日间变化跟踪从明天开始。")]
    if prev.get("date") == latest["date"]:
        return [b("No new trading day since the last brief.", "自上次简报以来无新交易日。")]
    out: list[str] = []
    if prev["quad"] != latest["quad"]:
        out.append(b(f"**The regime changed**: {prev['quad_name']} → **{latest['quad_name']}**.",
                     f"**周期已切换**：{tr(prev['quad_name'])} → **{tr(latest['quad_name'])}**。"))
    g0, g1 = prev["growth_score"], latest["growth_score"]
    if abs(g1 - g0) >= 0.1:
        out.append(b(f"The growth dial {'firmed' if g1 > g0 else 'softened'} ({g0:+.2f} → {g1:+.2f}).",
                     f"增长指标{'走强' if g1 > g0 else '走弱'}（{g0:+.2f} → {g1:+.2f}）。"))
    i0, i1 = prev["inflation_score"], latest["inflation_score"]
    if abs(i1 - i0) >= 0.1:
        out.append(b(f"Inflation pressure {'rose' if i1 > i0 else 'eased'} ({i0:+.2f} → {i1:+.2f}).",
                     f"通胀压力{'上升' if i1 > i0 else '缓解'}（{i0:+.2f} → {i1:+.2f}）。"))
    if prev.get("liquidity_overlay") != latest["liquidity_overlay"]:
        out.append(b(f"PBoC liquidity stance moved **{prev.get('liquidity_overlay')} → "
                     f"{latest['liquidity_overlay']}**.",
                     f"央行流动性立场转为 **{LIQ_ZH.get(prev.get('liquidity_overlay'),'?')} → "
                     f"{LIQ_ZH.get(latest['liquidity_overlay'],'?')}**。"))
    pr = prev.get("ranks", {})
    for r in latest.get("sector_rs", [])[:6]:
        old = pr.get(r["ticker"])
        if old and old - r["rank"] >= 3:
            out.append(b(f"**{r['name']}** climbed the RS table ({old} → {r['rank']}).",
                         f"**{tr(r['name'])}** 相对强弱排名上升（{old} → {r['rank']}）。"))
    if not out:
        out.append(b("A quiet day — no regime, liquidity or major rotation changes.",
                     "平静的一天 — 周期、流动性与主要轮动均无变化。"))
    return out


def regime_frame(latest: dict) -> list[str]:
    """Static, measured calibration verdicts keyed to today's regime."""
    quad = latest["quad_name"]
    out = []
    if quad == "Growth-scare":
        out.append(b("✅ Today's regime (**Growth-scare**) is the one signal that survived split-half "
                     "calibration as a **contrarian bottom** — historically the best forward return "
                     "(~+5 to +9% over 63d, ~71% hit). Lean into washout setups, not away.",
                     "✅ 今日周期（**增长恐慌**）是唯一通过折半校验的信号 — 作为**逆向底部**，历史上前瞻收益最佳"
                     "（63日约 +5 至 +9%，命中率约71%）。宜在恐慌洗盘中布局，而非回避。"))
    else:
        out.append(b(f"ℹ️ Today's regime (**{quad}**) is **not** a measured-robust signal — its forward "
                     "return flips between calibration halves. Treat the regime as risk context, not an "
                     "allocation rule. The robust contrarian buy is the **Growth-scare** washout, not now.",
                     f"ℹ️ 今日周期（**{tr(quad)}**）并非经实测稳健的信号 — 其前瞻收益在校验两段间反复。"
                     "请将周期视作风险背景，而非配置规则。稳健的逆向买点是**增长恐慌**式洗盘，而非当下。"))
    liq = latest["liquidity_overlay"]
    if liq == "expanding":
        out.append(b("✅ PBoC liquidity is **expanding** (M2 accelerating) — the cleanest measured "
                     "tailwind in the calibration (+1.7%/63d vs +0.6% when contracting).",
                     "✅ 央行流动性**扩张**（M2 加速）— 校验中最干净的顺风信号（63日 +1.7% vs 收缩时 +0.6%）。"))
    elif liq == "contracting":
        out.append(b("⚠️ PBoC liquidity is **contracting** (M2 decelerating) — a measured headwind; "
                     "size accordingly.",
                     "⚠️ 央行流动性**收缩**（M2 减速）— 实测逆风；据此控制仓位。"))
    return out


def build_markdown(latest: dict) -> str:
    prev = _load_prev()
    rs = latest.get("sector_rs", [])
    leaders = rs[:3]
    laggards = rs[-3:][::-1] if len(rs) >= 3 else []
    g, i = latest["growth_score"], latest["inflation_score"]

    md = [f"# {b('China A-share daily brief', '中国A股每日简报')} — {latest['date']}", ""]

    # 1. today in one paragraph
    md += [b(f"The A-share regime is **{latest['quad_name']}** "
             f"(growth {g:+.2f}, inflation {i:+.2f}), with {latest['confidence']:.0%} of signals "
             f"agreeing. PBoC liquidity is **{latest['liquidity_overlay']}**; the index cycle reads "
             f"**{latest['cycle_tag']}**.",
             f"A股周期为 **{tr(latest['quad_name'])}**（增长 {g:+.2f}，通胀 {i:+.2f}），"
             f"{latest['confidence']:.0%} 的信号一致。央行流动性**{LIQ_ZH.get(latest['liquidity_overlay'],'?')}**；"
             f"指数周期处于**{CYC_ZH.get(latest['cycle_tag'],'?')}**。"), ""]

    # 2. what the calibration says about today
    md += [f"## {b('What the record says', '历史记录怎么说')}", ""]
    md += [f"- {line}" for line in regime_frame(latest)]
    md += [""]

    # 3. what changed
    md += [f"## {b('What changed since the last brief', '自上次简报以来的变化')}", ""]
    md += [f"- {line}" for line in what_changed(latest, prev)]
    md += [""]

    # 4. sector tape
    md += [f"## {b('Sector tape (relative strength)', '板块盘面（相对强弱）')}", ""]
    if leaders:
        led = ", ".join(f"**{x['name']}**" for x in leaders)
        led_zh = "、".join(f"**{tr(x['name'])}**" for x in leaders)
        md.append("- " + b(f"📈 Leading the tape: {led} — strongest 60-day relative strength vs CSI 300.",
                           f"📈 盘面领先：{led_zh} — 相对沪深300的60日相对强弱最强。"))
    if laggards:
        lag = ", ".join(f"**{x['name']}**" for x in laggards)
        lag_zh = "、".join(f"**{tr(x['name'])}**" for x in laggards)
        md.append("- " + b(f"📉 Lagging: {lag} — weakest RS; avoid reaching for these.",
                           f"📉 盘面落后：{lag_zh} — 相对强弱最弱；不宜抄底硬接。"))
    pc = latest.get("preference_check") or {}
    if pc.get("agreement") is not None:
        md.append("- " + b(f"Framework-vs-tape agreement: {pc['agreement']:.0%} — {pc.get('note','')}.",
                           f"框架与盘面一致度：{pc['agreement']:.0%} — {pc.get('note','')}。"))
    md += [""]

    md += ["---", "*" + b(
        "Mechanical, generated from the day's free public data (yfinance + Eastmoney). Calibration "
        "figures are measured 2008-2026 base rates, not predictions. Not investment advice. "
        "Details: [the China dashboard](china.html).",
        "机械生成，数据来自当日免费公开来源（yfinance + 东方财富）。校验数据为 2008-2026 实测基准，"
        "而非预测。非投资建议。详见：[中国仪表盘](china.html)。") + "*"]
    return "\n".join(md)


def render_html(md_text: str, title: str) -> str:
    import markdown
    body = markdown.markdown(md_text, extensions=["tables"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('lang');if(l)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}</script>
<link rel="stylesheet" href="theme.css">
<style>body{{background:var(--bg);color:var(--text);font:15px/1.65 -apple-system,'Segoe UI',sans-serif;
max-width:760px;margin:0 auto;padding:24px}}html[data-lang="zh"] body{{font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",-apple-system,sans-serif}}
h1,h2{{color:var(--text)}}h2{{margin-top:28px}}a{{color:#7aa7e0}}li{{margin:6px 0}}hr{{border:none;border-top:1px solid var(--line);margin:24px 0}}
em{{color:var(--muted)}}</style>
</head><body><p><a href="china.html"><span class="l-en">&larr; China dashboard</span><span class="l-zh">&larr; 中国仪表盘</span></a> · <button class="lang-btn">中文</button> · <button class="theme-btn">☀️ <span class="l-en">Light</span><span class="l-zh">浅色</span></button></p>{body}
<footer class="site-footer">
  <span class="made"><span class="l-en">Made with ❤️ in Canada</span><span class="l-zh">用 ❤️ 在加拿大制作</span></span>
  <span class="dev"><span class="l-en">Developed by Chris Wong</span><span class="l-zh">开发者 Chris Wong</span></span>
</footer>
<script src="theme.js"></script></body></html>"""


def main() -> int:
    try:
        latest = _load_latest()
    except FileNotFoundError:
        log.warning("china_brief: no china_regime/latest.json — run build_china first")
        return 0
    md = build_markdown(latest)
    rdir = config.ROOT / config.load()["storage"]["reports_dir"]
    rdir.mkdir(exist_ok=True)
    (rdir / f"china-brief-{latest['date']}.md").write_text(md)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(exist_ok=True)
    (site / "china_brief.html").write_text(render_html(md, f"China brief {latest['date']}"))
    _save_state(latest)
    log.info("wrote reports/china-brief-%s.md and site/china_brief.html", latest["date"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
