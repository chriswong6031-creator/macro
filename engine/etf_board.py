"""Board synthesis for the rebuilt ``etfs.html`` (Real Fund Moves).

Turns the raw per-fund holding decisions (``engine.holdings_signals``) and the
cross-fund consensus (``engine.etf_consensus``) into the Tier-1 reads the page
shows at a glance — a plain-word verdict, a doctrine stance per name, the
"fresh conviction" shelf, and the rotation backdrop shaped from ``etf_pulse``.

Everything here is DISPLAY-TIER context (where curated / active managers are
putting money, on a lagged filing cadence) — never a gauntleted buy signal.
Stances follow the user-first doctrine vocabulary (Act · Get ready ·
Watch — don't chase · Protect gains · Stand aside · Ignore); the honest default
for a pure fund-flow read is "Watch — don't chase", and we only escalate when a
real forming setup (the cycle ladder) agrees.

Pure functions, no I/O, never raises on shape drift — a bad row degrades to a
calm default rather than crashing the render.
"""
from __future__ import annotations

import re
from collections import defaultdict

# ── display hygiene ────────────────────────────────────────────────────────

# Money-market / cash-sweep vehicles leak into thematic-fund snapshots as if
# they were equity conviction (First American Government Obligations, Invesco
# Government & Agency Portfolio, …). They are cash, not a manager bet — the page
# intro already promises they're excluded, so drop them everywhere.
_CASH_RE = re.compile(
    r"money[\s-]*market|government\s+ob?lig|govt?\s+oblig|treasury\s+oblig|"
    r"liquidity\s+fund|cash\s+manage|prime\s+oblig|agency\s+portfolio|"
    r"t-?bill|repo\b|premier\s+deposit|us\s+treasury\s+(fund|portfolio)",
    re.I,
)
_CASH_TICKER_RE = re.compile(r"^[A-Z]{2,}XX$")  # 5-letter mutual-fund cash classes

_SHARECLASS_RE = re.compile(
    r"\s*[-–]\s*(cl|class|series|ser)\s+[a-z0-9]+\s*$|"
    r"\s+(class|cl|series)\s+[a-z0-9]+\s*$|"
    r"\s+[-–]\s*(cl|class)\s*[a-z]$",
    re.I,
)


def is_cash(ticker: str | None, name: str | None) -> bool:
    """True if this holding is a money-market / cash-sweep line, not an equity."""
    tk = (ticker or "").strip().upper()
    nm = name or ""
    if tk and _CASH_TICKER_RE.match(tk):
        return True
    return bool(_CASH_RE.search(nm))


def drop_cash(rows: list[dict]) -> list[dict]:
    """Filter cash / money-market lines out of the raw signal rows."""
    return [r for r in (rows or []) if not is_cash(r.get("ticker"), r.get("name"))]


def clean_name(name: str | None) -> str:
    """Tidy a raw holdings display name: collapse the double-spaces the feeds
    leave, and strip a trailing share-class marker ("Meta Platforms Inc-Class A"
    → "Meta Platforms Inc"). Conservative — never touches the core name."""
    nm = re.sub(r"\s+", " ", (name or "").strip())
    if not nm:
        return ""
    stripped = _SHARECLASS_RE.sub("", nm).strip(" -–")
    # a bare trailing share-class letter the feeds leave once the "Class" word is
    # dropped ("Cerebras Systems Inc A"). Only on a long-enough name, A–C only, so
    # we never mangle a short real name that happens to end in a letter.
    m = re.match(r"^(.*\w{2,})\s+[A-C]$", stripped)
    if m and len(m.group(1).split()) >= 3:
        stripped = m.group(1)
    # keep the strip only if it left something meaningful
    return stripped if len(stripped) >= 3 else nm


# ── doctrine stance (the "so what do I do?" word) ──────────────────────────

# tone drives colour: lift=act, ready=forming, watch=neutral, trim=protect,
# aside=stand-aside/avoid. Words are the doctrine vocabulary, bilingual.
_STANCE = {
    "act":   {"en": "Act",                  "zh": "行动"},
    "ready": {"en": "Get ready",            "zh": "准备进场"},
    "watch": {"en": "Watch — don't chase",  "zh": "观望 · 勿追"},
    "trim":  {"en": "Protect gains",        "zh": "保护盈利"},
    "aside": {"en": "Stand aside",          "zh": "回避"},
    "ignore":{"en": "Ignore",               "zh": "忽略"},
}

_BULLISH_LADDER = {"FRESH BUY", "TURN SIGNALED", "RALLY ON", "BOTTOM WATCH"}


def _stance(tone: str, why_en: str = "", why_zh: str = "") -> dict:
    s = dict(_STANCE.get(tone, _STANCE["watch"]))
    s["tone"] = tone
    s["why"] = {"en": why_en, "zh": why_zh}
    return s


def stance_for(*, ladder: dict | None, confirmed: bool, contested: bool,
               direction: str, n_accum: int = 1, n_new: int = 0,
               net_pp: float = 0.0) -> dict:
    """Map a fund-flow read to a doctrine stance.

    The flow itself (managers accumulating) is lagged filing data, so the honest
    floor for accumulation is "Watch — don't chase". We escalate only when the
    price-cycle ladder confirms a live setup, and we down-rank contested / thin
    names. Distribution reads as "Protect gains / Stand aside"."""
    # distribution side
    if direction == "trimming" or (net_pp < 0 and direction != "accumulating"):
        if ladder and str(ladder.get("action", "")).upper().startswith("TAKE PROFIT"):
            return _stance("trim", "managers trimming into a high", "经理人在高位减持")
        return _stance("aside", "managers are stepping back", "经理人正在退出")

    # contested with no net edge → no signal
    if contested and abs(net_pp) < 0.5:
        return _stance("aside", "funds are split — no net edge", "多空分歧 · 无净向")

    act = str((ladder or {}).get("action", "")).upper()
    urg = str((ladder or {}).get("urgency", "")).lower()

    # a live buy setup that agrees with the flow → Act (rare, honest)
    if ladder and urg == "now" and ("BUY" in act):
        return _stance("act", "fund flow and a live buy setup agree",
                       "资金流与实时买点共振")
    # forming setup, or a broad + fresh crowd → Get ready
    if ladder and (urg in ("imminent", "soon") or ladder.get("state") in _BULLISH_LADDER):
        return _stance("ready", "a setup is forming under the accumulation",
                       "增持下方形态正在形成")
    if confirmed:
        return _stance("ready", "accumulation with a forming setup",
                       "增持且形态正在形成")
    if ladder and ("TAKE PROFIT" in act):
        return _stance("trim", "extended — managers may be late", "已延伸 · 或追高")
    if ladder and (urg in ("avoid", "caution") or "AVOID" in act or "HIGH-RISK" in act):
        return _stance("aside", "weak setup despite the buying", "买盘之下形态偏弱")

    # pure fund-flow read, no cycle confirm → the honest default
    if n_accum >= 3 and n_new >= 2:
        return _stance("watch", "a fresh crowd is forming — wait for your entry",
                       "新资金正在聚集 · 等待自身入场点")
    return _stance("watch", "smart money is in; time your own entry",
                   "聪明钱已进场；自行把握入场点")


# ── verdict + rotation synthesis ───────────────────────────────────────────

_RISK_READ = {
    "RISK-ON":  {"en": "credit and cyclicals leading — a supportive tape for new bets",
                 "zh": "信用与周期领先 · 有利于新仓位的市场环境"},
    "NEUTRAL":  {"en": "no clear risk lean — treat conviction reads on their own merit",
                 "zh": "风险偏好不明 · 个别信念自身评判"},
    "RISK-OFF": {"en": "defensives leading — accumulation is fighting the tape",
                 "zh": "防御领先 · 增持在逆势而行"},
}


def _theme_tally(favored: list[dict]) -> tuple[list[dict], list[dict]]:
    """Net cross-fund consensus per theme, THEN split into building vs leaving by
    each theme's TOTAL — so a theme never appears on both sides at once."""
    tally: dict[str, dict] = defaultdict(lambda: {"net": 0.0, "n": 0})
    for c in favored or []:
        theme = (c.get("sector") or "").strip()
        if not theme:
            continue
        tally[theme]["net"] += c.get("net_conviction_pp") or 0.0
        tally[theme]["n"] += 1
    themes = [{"label": k, "net": round(v["net"], 2), "n": v["n"]}
              for k, v in tally.items()]
    build = sorted([t for t in themes if t["net"] > 0], key=lambda x: -x["net"])
    leave = sorted([t for t in themes if t["net"] < 0], key=lambda x: x["net"])
    return build, leave


# a light EN→ZH map for the theme words that surface in the verdict; unknown
# themes fall back to the English label (honest, never blocks render).
_THEME_ZH = {
    "Space": "太空", "Semiconductors": "半导体", "Gold Miners": "金矿",
    "Junior Gold Miners": "小型金矿", "Copper Miners": "铜矿", "Rare Earth": "稀土",
    "Nuclear": "核能", "Uranium": "铀", "Biotech": "生物科技", "Genomics": "基因组",
    "AI": "人工智能", "Robotics / AI": "机器人/AI", "Autonomous / Robotics": "自动化/机器人",
    "Blockchain": "区块链", "Fintech / Blockchain": "金融科技/区块链", "Metaverse": "元宇宙",
    "Obesity / GLP-1": "减肥/GLP-1", "Aerospace & Defense": "航空国防",
    "Space / Defense": "太空/国防", "Sports Betting": "体育博彩", "Energy": "能源",
    "Energy Infra": "能源基建", "Financials": "金融", "Regional Banks": "区域银行",
    "Banks": "银行", "Health Care": "医疗", "Technology": "科技",
    "Information Technology": "信息技术", "Communication Services": "通讯服务",
    "Materials": "材料", "Industrials": "工业", "Metals & Mining": "金属采矿",
    "3D Printing": "3D打印", "Israel Tech": "以色列科技", "Homebuilders": "住宅建筑",
    "Retail": "零售", "Meme / Retail": "散户热门", "Pharmaceuticals": "制药",
}


def _theme_zh(label: str) -> str:
    return _THEME_ZH.get(label, label)


def _verdict(build: list[dict], leave: list[dict], risk_label: str,
             fresh_n: int) -> dict:
    top = [b["label"] for b in build[:3] if b["net"] > 0]
    if not top:
        return {"en": "Managers are quiet this cycle — no theme is drawing broad "
                      "cross-fund conviction.",
                "zh": "本轮经理人动作平静 —— 暂无主题获得广泛的跨基金信念。"}
    def join(words, conj):
        words = list(words)
        if len(words) == 1:
            return words[0]
        return f"{', '.join(words[:-1])} {conj} {words[-1]}"
    en_themes = join(top, "and")
    zh_themes = "、".join(_theme_zh(t) for t in top)
    tape_en = {"RISK-ON": " — into a risk-on tape", "RISK-OFF": " — against a risk-off tape",
               "NEUTRAL": ""}.get(risk_label, "")
    tape_zh = {"RISK-ON": "，且身处风险偏好的市场", "RISK-OFF": "，却逆着避险的市场",
               "NEUTRAL": ""}.get(risk_label, "")
    en = f"Fund managers are building conviction in {en_themes}{tape_en}."
    zh = f"基金经理人正在{zh_themes}上积累信念{tape_zh}。"
    if leave and leave[0]["net"] < -0.5:
        en = en[:-1] + f", and stepping back from {leave[0]['label']}."
        zh = zh[:-1] + f"，同时正从{_theme_zh(leave[0]['label'])}撤出。"
    return {"en": en, "zh": zh}


def _rotation(pulse: dict) -> dict:
    """Shape etf_pulse (style / risk / sector) into display-ready reads."""
    pulse = pulse or {}
    # risk backdrop
    risk = pulse.get("risk") or {}
    rl = risk.get("label_en") or "NEUTRAL"
    risk_out = {
        "label": {"en": rl, "zh": risk.get("label_zh") or rl},
        "tilt": risk.get("tilt"),
        "tone": "lift" if (risk.get("tilt") or 0) > 0.1 else
                "drag" if (risk.get("tilt") or 0) < -0.1 else "neutral",
        "read": _RISK_READ.get(rl, _RISK_READ["NEUTRAL"]),
        "legs": [{"label": {"en": lg.get("label_en"), "zh": lg.get("label_zh")},
                  "dir": lg.get("direction"), "chg20": lg.get("chg_20d")}
                 for lg in (risk.get("legs") or [])],
    }
    # sector leadership (ranked by momentum; leaders/laggards already provided)
    sec = pulse.get("sector") or {}
    srows = sec.get("rows") or []
    def sec_row(r):
        return {"ticker": r.get("ticker"), "label": {"en": r.get("label_en"),
                "zh": r.get("label_zh")}, "mom60": r.get("mom_60d"),
                "mom20": r.get("mom_20d"), "pctile": r.get("pctile_252d"),
                "above200": r.get("above_200d"), "rank": r.get("rank")}
    sector_out = {
        "rows": [sec_row(r) for r in srows],
        "mom_max": max((abs(r.get("mom_60d") or 0.0) for r in srows), default=1.0) or 1.0,
    }
    # style tug-of-war
    style_out = [{"label": {"en": s.get("label_en"), "zh": s.get("label_zh")},
                  "lead": {"en": s.get("lead_en"), "zh": s.get("lead_zh")},
                  "tilt": s.get("tilt"), "chg20": s.get("chg_20d"),
                  "chg60": s.get("chg_60d")}
                 for s in (pulse.get("style") or [])]
    return {"risk": risk_out, "sector": sector_out, "style": style_out,
            "as_of": pulse.get("as_of")}


def _fresh_conviction(accumulation: list[dict], cap: int = 8) -> list[dict]:
    """Brand-new positions initiated this cycle, grouped by stock — the highest
    information moves (a manager starting a fresh stake beats adding to an old
    one). Ranked by how many funds opened it, then conviction."""
    by_tk: dict[str, dict] = {}
    for r in accumulation or []:
        if not r.get("is_new"):
            continue
        tk = r.get("ticker")
        if not tk:
            continue
        g = by_tk.setdefault(tk, {"ticker": tk, "name": r.get("name"),
                                  "sector": r.get("sector"), "funds": [],
                                  "conviction_pp": 0.0, "ladder": None,
                                  "confirmed": False})
        g["funds"].append({"fund": r.get("etf"), "conviction_pp": r.get("conviction_pp"),
                           "is_active": r.get("is_active")})
        g["conviction_pp"] += r.get("conviction_pp") or 0.0
        if r.get("ladder") and not g["ladder"]:
            g["ladder"] = r.get("ladder")
        g["confirmed"] = g["confirmed"] or bool(r.get("confirmed"))
    out = list(by_tk.values())
    for g in out:
        g["n_funds"] = len(g["funds"])
        g["funds"].sort(key=lambda f: -(abs(f.get("conviction_pp") or 0)))
        g["stance"] = stance_for(ladder=g["ladder"], confirmed=g["confirmed"],
                                 contested=False, direction="accumulating",
                                 n_accum=g["n_funds"], n_new=g["n_funds"],
                                 net_pp=g["conviction_pp"])
    out.sort(key=lambda g: (-g["n_funds"], -g["conviction_pp"]))
    return out[:cap]


def board_context(rows: list[dict], accumulation: list[dict], trims: list[dict],
                  favored: list[dict], coverage: list[dict],
                  pulse: dict | None) -> dict:
    """Assemble the Tier-1 board context and attach a stance to each shown row.

    Mutates ``favored`` / ``accumulation`` / ``trims`` in place to add a
    ``stance`` dict (cheap, keeps the template declarative). Returns the hero /
    rotation / fresh-conviction synthesis."""
    accumulation = accumulation or []
    trims = trims or []
    favored = favored or []

    # attach stance to every shown row
    for c in favored:
        c["stance"] = stance_for(
            ladder=c.get("ladder"), confirmed=bool(c.get("confirmed")),
            contested=bool(c.get("contested")),
            direction="accumulating" if (c.get("net_conviction_pp") or 0) >= 0 else "trimming",
            n_accum=c.get("n_accum") or 0, n_new=c.get("n_new") or 0,
            net_pp=c.get("net_conviction_pp") or 0.0)
    for r in accumulation:
        r["stance"] = stance_for(
            ladder=r.get("ladder"), confirmed=bool(r.get("confirmed")),
            contested=False, direction="accumulating",
            n_accum=1, n_new=1 if r.get("is_new") else 0,
            net_pp=r.get("conviction_pp") or 0.0)
    for r in trims:
        r["stance"] = stance_for(
            ladder=r.get("ladder"), confirmed=False, contested=False,
            direction="trimming", net_pp=r.get("conviction_pp") or 0.0)

    rotation = _rotation(pulse or {})
    risk_label = rotation["risk"]["label"]["en"]
    build, leave = _theme_tally(favored)
    fresh = _fresh_conviction(accumulation)

    n_funds = sum(1 for c in coverage or [] if (c.get("n_snapshots") or 0) > 0)
    n_active = sum(1 for c in coverage or [] if c.get("is_active"))
    fresh_names = len({r.get("ticker") for r in accumulation if r.get("is_new")})

    # hero tiles
    top = favored[0] if favored else None
    tiles = []
    if top:
        tiles.append({"k": {"en": "Strongest consensus", "zh": "最强共识"},
                      "v": top.get("ticker"),
                      "m": {"en": f"{top.get('n_accum', 0)} funds building"
                                  + (" · contested" if top.get("contested") else ""),
                            "zh": f"{top.get('n_accum', 0)} 只基金增持"
                                  + (" · 有分歧" if top.get("contested") else "")},
                      "tone": "lift", "stance": top.get("stance")})
    tiles.append({"k": {"en": "Fresh conviction", "zh": "全新建仓"},
                  "v": str(fresh_names),
                  "m": {"en": "brand-new positions this cycle",
                        "zh": "本轮全新建立的仓位"}, "tone": "accent"})
    tiles.append({"k": {"en": "Market backdrop", "zh": "市场环境"},
                  "v": risk_label,
                  "m": rotation["risk"]["read"],
                  "tone": rotation["risk"]["tone"]})

    return {
        "verdict": _verdict(build, leave, risk_label, fresh_names),
        "coverage": {"funds": n_funds, "active": n_active},
        "tiles": tiles,
        "themes_building": build[:4],
        "themes_leaving": leave[:3],
        "fresh": fresh,
        "rotation": rotation,
        # magnitude for normalising the consensus pressure bars (never zero)
        "scale": {
            "consensus_pp": max((abs(c.get("net_conviction_pp") or 0.0) for c in favored),
                                default=1.0) or 1.0,
        },
    }
