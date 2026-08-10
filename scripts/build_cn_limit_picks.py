"""Build the standalone CN Limit-Move Picks page (site/cn_limit_picks.html).

Operator-ordered 2026-08-09: a simple front-end page carrying the CN limit-alpha
forward ledger's live picks, in the china_stocks card language, with NO nav-menu
link.  The page is a RESEARCH PREVIEW, display tier: nothing here ranks, sizes or
gates anything, and no number on it originates a signal — every figure is read
straight off the ledger the nightly lane already writes.

Input  : research/cn_prophet_audit/onset_forward_ledger.jsonl  (one JSON row per
         prediction; the file carries every predict_date, this page renders the
         newest one).  Row fields consumed: ticker, board, ladder_N_at_T,
         p_next_board, p_b0, feature_date_T, predict_date, model_version,
         stamped_at_utc.  `top_features_snapshot` and `fillability_note` are
         deliberately NOT rendered: the feature keys are raw machine slugs
         (banned on the glance tier) and the note is identical on all 100 rows,
         so it is said once per card in plain words by the template instead.
Names  : data/china_search/members.parquet (name_en / name_zh).  Optional — a
         missing store or a missing ticker prints the code alone, never blocks
         the render (DESIGN_DOCTRINE Law 2: never block render on a name lookup).
Output : site/cn_limit_picks.html

AUTHORITY BOUNDARY.  ``onset_v1`` is the pre-registered tolerant working-tape
contract: its Yahoo-derived, back-adjusted research plane is useful for a
display-tier probability window, but it is not exact exchange-limit evidence.
Exact legal-band classification belongs only to unadjusted TuShare ``daily``
joined on ticker and trade date to vendor ``stk_limit``, compared in integer
cents.  The page therefore labels the ledger as tolerant/provisional and must
never promote its percentages into exact-limit claims.

DETERMINISM.  The page carries no wall-clock stamp.  Its one as-of is the
ledger's own newest `stamped_at_utc`, so two runs over the same ledger produce
byte-identical HTML — verifiable with `--check`.  This is also the doctrinally
correct shape: one as-of per panel, and it names the moment the DATA was fixed
rather than the moment the HTML was written.

    python -m scripts.build_cn_limit_picks            # write the page
    python -m scripts.build_cn_limit_picks --check    # render twice, diff bytes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_cn_limit_picks")

ASSETS = ("theme.css", "theme.js")
_PAGE = "cn_limit_picks.html"
_LEDGER = Path("research") / "cn_prophet_audit" / "onset_forward_ledger.jsonl"
_NAMES = Path("data") / "china_search" / "members.parquet"
_N_CARDS = 20

# Board slug -> the label a reader recognises. ChiNext's own English name is the
# display name everywhere on the site; 创业板 is what the ZH side calls it.
_BOARD = {
    "main": ("Main board", "主板"),
    "chinext": ("ChiNext", "创业板"),
}

# Company-name tails that eat the whole 246px card cell without adding meaning.
_NAME_TAILS = (
    "Co., Ltd.", "Co.,Ltd.", "Co., Ltd", "Co.,Ltd", "Company Limited",
    "Corporation Limited", "Group Co., Ltd.", "Corporation", "Company",
    "Limited", "Ltd.", "Ltd", "Inc.", "Inc", "PLC", "S.A.",
)


def _fail(msg: str) -> SystemExit:
    """Fail loud, with the one line that fixes it."""
    print(f"::error title=cn-limit-picks::{msg}", flush=True)
    return SystemExit(2)


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _tidy_name(en: str) -> str:
    """Trim the corporate tail so the name fits the card without truncating."""
    out = (en or "").strip()
    changed = True
    while changed:
        changed = False
        for tail in _NAME_TAILS:
            if out.lower().endswith(tail.lower()):
                out = out[: -len(tail)].rstrip(" ,.-")
                changed = True
    return out or (en or "").strip()


def _names() -> dict[str, tuple[str, str]]:
    """ticker -> (name_en, name_zh). Empty dict when the store is unavailable."""
    path = config.ROOT / _NAMES
    if not path.is_file():
        log.warning("name store %s absent — cards will print tickers alone", path)
        return {}
    try:
        import pandas as pd

        df = pd.read_parquet(path, columns=["name_en", "name_zh"])
    except Exception as exc:  # noqa: BLE001 — names are cosmetic, never fatal
        log.warning("name store unreadable (%s) — cards will print tickers alone", exc)
        return {}
    out: dict[str, tuple[str, str]] = {}
    for ticker, row in df.iterrows():
        en = _tidy_name(str(row.get("name_en") or "").strip())
        zh = str(row.get("name_zh") or "").strip()
        if en or zh:
            out[str(ticker)] = (en or zh, zh or en)
    return out


def _rung(n: int) -> tuple[str, str]:
    """Plain words for where the name stands on the ladder, and what Monday adds.

    `ladder_N_at_T` counts limit-ups already in hand at the feature date, so
    N=0 is a name with no board yet and the prediction is its FIRST one.  Naming
    the rung alone ("首板") would be ambiguous about which side of Monday it
    describes; naming both halves is one line and cannot be misread.
    """
    if n <= 0:
        return ("No board yet — Monday would be the first", "尚未封板 — 周一或封首板")
    return (
        f"{n} in a row — Monday would make {n + 1}",
        f"已{n}连板 — 周一或成{n + 1}连板",
    )


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _flags(row: dict) -> list[dict]:
    """The read-down chips. Both say what to DO with the number, not what it is.

    Order matters: the ladder caution outranks the board caution, because when a
    deep-ladder row is also on ChiNext the rung's own rate is the read that
    replaces the model outright, not merely a discount on it.
    """
    out: list[dict] = []
    n = int(row.get("ladder_N_at_T") or 0)
    if n >= 3:
        base = _pct(float(row.get("p_b0") or 0.0))
        out.append({
            "en": "Trust the rung", "zh": "以板位为准",
            "tip_en": (
                f"Deep on the ladder the model has not beaten its working-tape history: "
                f"names on this rung met the registered tolerant close criterion {base} of "
                f"the time, which is the number to read here. The model's figure is shown "
                f"for comparison, not to replace it."
            ),
            "tip_zh": (
                f"进入高位连板后，模型并未跑赢工作台账历史读数：同板位个股达到预注册宽容收盘口径的"
                f"历史频率为 {base}，这才是此处应读的数字。模型概率仅作对照，不用于替代它。"
            ),
        })
    if str(row.get("board") or "") == "chinext":
        out.append({
            "en": "Read it down", "zh": "应下调",
            "tip_en": (
                "This working-tape model runs hot on ChiNext: it has printed roughly 2.6 "
                "times more tolerant-limit closes on 创业板 names than its registered "
                "outcomes. Treat the percentage as an upper bound, not an estimate."
            ),
            "tip_zh": (
                "该工作台账模型在创业板上偏高：其给出的宽容口径封板次数约为预注册结果的 2.6 倍。"
                "请把这个百分比当作上限，而不是估计值。"
            ),
        })
    return out


def load(ledger: Path | None = None) -> dict:
    """Read the ledger and build the page view-model. Fails loud on a missing file."""
    path = ledger or (config.ROOT / _LEDGER)
    if not path.is_file():
        raise _fail(
            f"forward ledger missing at {path} — recover it with: "
            f"git show origin/claude/cn-limit-w1-onset:{_LEDGER.as_posix()} > {_LEDGER.as_posix()}"
        )

    rows: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise _fail(f"{path}:{lineno} is not valid JSON ({exc}) — the ledger is corrupt")
    if not rows:
        raise _fail(f"{path} is empty — no predictions to render")

    predict_date = max(str(r.get("predict_date") or "") for r in rows)
    if not predict_date:
        raise _fail(f"{path} carries no predict_date — cannot pick the live slice")
    live = [r for r in rows if str(r.get("predict_date") or "") == predict_date]

    # P desc, then ticker asc. The tiebreak is load-bearing, not cosmetic: the
    # model prints heavy ties (six names share the top P in the 2026-08-10
    # slice), so without it "top 20" would reorder between runs. It is also why
    # the page shows no rank numbers — a rank would claim a precision the ties
    # do not support (and the numbered-tape idiom is a standing house veto).
    live.sort(key=lambda r: (-float(r.get("p_next_board") or 0.0), str(r.get("ticker") or "")))

    names = _names()
    out_rows: list[dict] = []
    for r in live:
        ticker = str(r.get("ticker") or "")
        n = int(r.get("ladder_N_at_T") or 0)
        board = str(r.get("board") or "")
        b_en, b_zh = _BOARD.get(board, (board or "—", board or "—"))
        rung_en, rung_zh = _rung(n)
        name_en, name_zh = names.get(ticker, ("", ""))
        out_rows.append({
            "ticker": ticker,
            "name_en": name_en,
            "name_zh": name_zh or name_en,
            "board_en": b_en,
            "board_zh": b_zh,
            "n_at_t": n,
            "rung_en": rung_en,
            "rung_zh": rung_zh,
            "p_txt": _pct(float(r.get("p_next_board") or 0.0)),
            "b_txt": _pct(float(r.get("p_b0") or 0.0)),
            "flags": _flags(r),
        })

    stamps = [str(r.get("stamped_at_utc") or "") for r in live if r.get("stamped_at_utc")]
    return {
        "predict_date": predict_date,
        "feature_date": max(str(r.get("feature_date_T") or "") for r in live),
        "model_version": max(str(r.get("model_version") or "") for r in live) or "—",
        "ledger_stamp": (max(stamps).replace("T", " ").replace("Z", " UTC") if stamps else "—"),
        "n_rows": len(out_rows),
        "cards": out_rows[:_N_CARDS],
        "rows": out_rows,
    }


def render(vm: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    from engine import i18n

    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("cn_limit_picks.html.j2").render(d=vm)


def build(site: Path | None = None) -> dict:
    vm = load()
    html = render(vm)
    site = site or _site_dir()
    site.mkdir(parents=True, exist_ok=True)
    write_page(site / _PAGE, html)
    for a in ASSETS:
        src = config.ROOT / "templates" / a
        if src.exists() and not (site / a).exists():
            site_assets.copy_asset(a, src, site)
    log.info(
        "wrote %s/%s (%d KB, %d names, predicts %s)",
        site, _PAGE, len(html) // 1024, vm["n_rows"], vm["predict_date"],
    )
    return vm


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="render twice and diff the bytes; exit 1 on any drift")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.check:
        a, b = render(load()), render(load())
        if a != b:
            print("::error title=cn-limit-picks::render is not deterministic", flush=True)
            return 1
        log.info("deterministic: two renders byte-identical (%d bytes)", len(a.encode()))
        return 0

    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
