"""Hong Kong daily brief — a plain, bilingual narrative for the Hang Seng regime.

Hong Kong parallel of scripts/china_brief.py. Reads only stored outputs
(data/hk_regime/latest.json), diffs against yesterday's snapshot for the
"what changed" section, and frames the day HONESTLY: the regime quad is risk
context (no contrarian Growth-scare edge — that was China). The HK-distinctive
reads are the GLOBAL RISK overlay (HK is ~2x as sensitive to global risk-on/off
as the A-shares) and the HKD peg state (HKMA defends the 7.75–7.85 band; a
weak-side peg signals capital-outflow pressure on HSI). Publishes
site/hk_brief.html + reports/hk-brief-<date>.md.

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
log = logging.getLogger("hk_brief")

PREV = "brief_prev_state.json"
LIQ_ZH = {"expanding": "扩张", "contracting": "收缩", "neutral": "中性", "unknown": "未知"}
CYC_ZH = {"early": "早期", "mid": "中期", "late": "晚期", "unknown": "未知"}
RISK_ZH = {"Risk-on": "风险偏好", "Risk-off": "风险规避", "Neutral": "中性"}


def b(en: str, zh: str) -> str:
    """Inline bilingual span pair (markdown passes raw HTML through)."""
    return f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>'


def _risk_zh(state: str | None) -> str:
    return RISK_ZH.get(state, state or "?")


def _load_latest() -> dict:
    return json.loads((config.data_dir() / "hk_regime" / "latest.json").read_text())


def _load_prev() -> dict | None:
    p = config.data_dir() / "hk_regime" / PREV
    return json.loads(p.read_text()) if p.exists() else None


def _save_state(latest: dict) -> None:
    state = {k: latest.get(k) for k in ("date", "quad", "quad_name", "growth_score",
                                        "inflation_score", "confidence", "liquidity_overlay",
                                        "risk_state", "peg_state")}
    state["ranks"] = {r["ticker"]: r["rank"] for r in latest.get("sector_rs", [])}
    (config.data_dir() / "hk_regime" / PREV).write_text(json.dumps(state, indent=1))


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
        out.append(b(f"Dual liquidity (PBoC + Fed-via-peg) moved **{prev.get('liquidity_overlay')} → "
                     f"{latest['liquidity_overlay']}**.",
                     f"双重流动性（央行 + 经联系汇率传导的美联储）转为 **{LIQ_ZH.get(prev.get('liquidity_overlay'),'?')} → "
                     f"{LIQ_ZH.get(latest['liquidity_overlay'],'?')}**。"))
    if prev.get("risk_state") != latest.get("risk_state"):
        out.append(b(f"Global risk regime flipped **{prev.get('risk_state')} → {latest.get('risk_state')}**.",
                     f"全球风险状态切换 **{_risk_zh(prev.get('risk_state'))} → {_risk_zh(latest.get('risk_state'))}**。"))
    if prev.get("peg_state") != latest.get("peg_state"):
        out.append(b(f"HKD peg state moved **{prev.get('peg_state')} → {latest.get('peg_state')}**.",
                     f"港元联系汇率状态转为 **{prev.get('peg_state')} → {latest.get('peg_state')}**。"))
    pr = prev.get("ranks", {})
    for r in latest.get("sector_rs", [])[:6]:
        old = pr.get(r["ticker"])
        if old and old - r["rank"] >= 3:
            out.append(b(f"**{r['name']}** climbed the RS table ({old} → {r['rank']}).",
                         f"**{tr(r['name'])}** 相对强弱排名上升（{old} → {r['rank']}）。"))
    if not out:
        out.append(b("A quiet day — no regime, liquidity, risk, peg or major rotation changes.",
                     "平静的一天 — 周期、流动性、风险、联系汇率与主要轮动均无变化。"))
    return out


def regime_frame(latest: dict) -> list[str]:
    """Honest framing: regime as risk context + the HK-distinctive global-risk and peg overlays."""
    quad = latest["quad_name"]
    out = []
    # (a) the quad is risk context — no contrarian edge claim for HK.
    out.append(b(f"ℹ️ Today's regime (**{quad}**) is **risk context, not an allocation rule** — "
                 "read it as the backdrop HSI is trading in, not a buy/sell signal.",
                 f"ℹ️ 今日周期（**{tr(quad)}**）是**风险背景，而非配置规则** — "
                 "应将其视作恒指所处的环境，而非买卖信号。"))
    # (b) global risk overlay — HK is ~2x as sensitive as A-shares.
    risk = latest.get("risk_state")
    if risk == "Risk-off":
        out.append(b("⚠️ Global risk is **Risk-off** — a direct headwind, and HK is ~2x as sensitive to "
                     "the global risk factor as the A-shares. Size down.",
                     "⚠️ 全球风险处于**风险规避** — 直接逆风，且香港对全球风险因子的敏感度约为A股的2倍。宜降低仓位。"))
    elif risk == "Risk-on":
        out.append(b("✅ Global risk is **Risk-on** — a tailwind, amplified for HK (~2x the A-share "
                     "sensitivity to the global risk factor).",
                     "✅ 全球风险处于**风险偏好** — 顺风，且对香港的放大效应更强（对全球风险因子的敏感度约为A股的2倍）。"))
    else:
        out.append(b("ℹ️ Global risk reads **Neutral** — no clear global push either way; HK remains the "
                     "high-beta proxy when it turns.",
                     "ℹ️ 全球风险为**中性** — 暂无明确的全球方向推动；一旦转向，香港仍是高贝塔代理。"))
    # (c) HKD peg — capital-flow read.
    peg = latest.get("peg_state") or ""
    if "weak" in peg.lower():
        out.append(b(f"⚠️ The HKD peg is **{peg}** — capital-outflow pressure, with the HKMA defending the "
                     "7.85 weak-side band; an HSI headwind until flows turn.",
                     f"⚠️ 港元联系汇率为 **{peg}** — 资本流出压力，金管局正捍卫 7.85 弱方兑换保证；在资金转向前对恒指构成逆风。"))
    elif "strong" in peg.lower():
        out.append(b(f"✅ The HKD peg is **{peg}** — capital-inflow support pinning the strong-side band; "
                     "a tailwind for HSI liquidity.",
                     f"✅ 港元联系汇率为 **{peg}** — 资本流入支撑，触及强方兑换保证；为恒指流动性提供顺风。"))
    else:
        out.append(b(f"ℹ️ The HKD peg is **{peg or 'mid-band'}** — flows balanced within the band, no peg "
                     "pressure on HSI right now.",
                     f"ℹ️ 港元联系汇率为 **{peg or '区间中段'}** — 资金在区间内大致平衡，当前联系汇率对恒指无压力。"))
    # (d) dual liquidity stance.
    liq = latest["liquidity_overlay"]
    if liq == "expanding":
        out.append(b("✅ Dual liquidity (PBoC + Fed-via-peg) is **expanding** — a tailwind for HK, which "
                     "imports both the mainland and US liquidity cycles.",
                     "✅ 双重流动性（央行 + 经联系汇率传导的美联储）**扩张** — 对香港构成顺风，"
                     "香港同时输入内地与美国的流动性周期。"))
    elif liq == "contracting":
        out.append(b("⚠️ Dual liquidity (PBoC + Fed-via-peg) is **contracting** — a headwind, doubly so for "
                     "HK as it imports both liquidity cycles; size accordingly.",
                     "⚠️ 双重流动性（央行 + 经联系汇率传导的美联储）**收缩** — 逆风，且因香港同时输入两套流动性周期而加倍；据此控制仓位。"))
    return out


def build_markdown(latest: dict) -> str:
    prev = _load_prev()
    rs = latest.get("sector_rs", [])
    leaders = rs[:3]
    laggards = rs[-3:][::-1] if len(rs) >= 3 else []
    g, i = latest["growth_score"], latest["inflation_score"]

    md = [f"# {b('Hong Kong daily brief', '香港每日简报')} — {latest['date']}", ""]

    # 1. today in one paragraph — foreground the global-risk + peg reads.
    md += [b(f"The Hang Seng regime is **{latest['quad_name']}** "
             f"(growth {g:+.2f}, inflation {i:+.2f}), with {latest['confidence']:.0%} of signals "
             f"agreeing. The HK-distinctive read: global risk is **{latest.get('risk_state')}** and the "
             f"HKD peg is **{latest.get('peg_state')}**. Dual liquidity (PBoC + Fed-via-peg) is "
             f"**{latest['liquidity_overlay']}**; the index cycle reads **{latest['cycle_tag']}**.",
             f"恒指周期为 **{tr(latest['quad_name'])}**（增长 {g:+.2f}，通胀 {i:+.2f}），"
             f"{latest['confidence']:.0%} 的信号一致。香港的独特读数：全球风险为 **{_risk_zh(latest.get('risk_state'))}**，"
             f"港元联系汇率为 **{latest.get('peg_state')}**。双重流动性（央行 + 经联系汇率传导的美联储）"
             f"**{LIQ_ZH.get(latest['liquidity_overlay'],'?')}**；指数周期处于**{CYC_ZH.get(latest['cycle_tag'],'?')}**。"), ""]

    # 2. what the framing says about today
    md += [f"## {b('How to read today', '今日解读')}", ""]
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
        md.append("- " + b(f"📈 Leading the tape: {led} — strongest 60-day RS vs HSI.",
                           f"📈 盘面领先：{led_zh} — 相对恒指的60日相对强弱最强。"))
    if laggards:
        lag = ", ".join(f"**{x['name']}**" for x in laggards)
        lag_zh = "、".join(f"**{tr(x['name'])}**" for x in laggards)
        md.append("- " + b(f"📉 Lagging: {lag} — weakest RS vs HSI; avoid reaching for these.",
                           f"📉 盘面落后：{lag_zh} — 相对恒指的相对强弱最弱；不宜抄底硬接。"))
    pc = latest.get("preference_check") or {}
    if pc.get("agreement") is not None:
        md.append("- " + b(f"Framework-vs-tape agreement: {pc['agreement']:.0%} — {pc.get('note','')}.",
                           f"框架与盘面一致度：{pc['agreement']:.0%} — {pc.get('note','')}。"))
    md += [""]

    md += ["---", "*" + b(
        "Mechanical, generated from the day's free public data (yfinance + Eastmoney macro). The regime "
        "is risk context, not a prediction. Not investment advice. "
        "Details: [the Hong Kong dashboard](hk.html).",
        "机械生成，数据来自当日免费公开来源（yfinance + 东方财富宏观）。周期为风险背景，"
        "而非预测。非投资建议。详见：[香港仪表盘](hk.html)。") + "*"]
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
</head><body><p><a href="hk.html"><span class="l-en">&larr; Hong Kong dashboard</span><span class="l-zh">&larr; 香港仪表盘</span></a> · <button class="lang-btn">中文</button> · <button class="theme-btn">☀️ <span class="l-en">Light</span><span class="l-zh">浅色</span></button></p>{body}
<footer class="site-footer">
  <span class="made"><span class="l-en">Made with ❤️ in Canada</span><span class="l-zh">用 ❤️ 在加拿大制作</span></span>
  <span class="dev"><span class="l-en">Developed by Chris Wong</span><span class="l-zh">开发者 Chris Wong</span></span>
</footer>
<script src="theme.js"></script></body></html>"""


def main() -> int:
    try:
        latest = _load_latest()
    except FileNotFoundError:
        log.warning("hk_brief: no hk_regime/latest.json — run build_hk first")
        return 0
    md = build_markdown(latest)
    rdir = config.ROOT / config.load()["storage"]["reports_dir"]
    rdir.mkdir(exist_ok=True)
    (rdir / f"hk-brief-{latest['date']}.md").write_text(md)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(exist_ok=True)
    (site / "hk_brief.html").write_text(render_html(md, f"Hong Kong brief {latest['date']}"))
    _save_state(latest)
    log.info("wrote reports/hk-brief-%s.md and site/hk_brief.html", latest["date"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
