"""Quant Lab model registry — what the vendor DISCLOSES vs what we can BUILD.

Every field here is either quoted from a public source (with `provenance`) or marked as
our inference. That boundary is load-bearing: Fintel's QV/QVM/QVO are proprietary and
only PARTIALLY disclosed, so a recreation is necessarily a reconstruction from the
published lineage plus the numeric readouts the vendor prints in its own syndicated
articles. Pretending otherwise would manufacture a fidelity we do not have.

FIDELITY GRADES (per leg, per mode):
    faithful  our input is the vendor's stated input, computed the stated way
    proxy     a defensible stand-in with a NAMED distortion (recorded in `distortion`)
    absent    our substrate cannot compute it at all -> the leg is dropped and DISCLOSED

MODES:
    live      latest cross-section. May use non-point-in-time panels, so it is a
              SNAPSHOT, never backtest evidence.
    pit       point-in-time. Only panels with a real filing/availability date
              (fundamentals_panel.asof_date, statements_quarterly.filed) qualify.
              This is the only mode `study.py` will score.

The `statements.parquet` panel is deliberately NOT a pit source: its `as_of` column
holds five FETCH timestamps (all 2026-06-15), not filing dates, so every row would be
knowable at every historical rebalance. Using it in a backtest would leak the future.
"""
from __future__ import annotations

# The options family's pre-registration and its measured nulls are IMPORTED, never restated.
# One pre-registration exists, in the module the dormant gate reads; a second copy here would
# be free to drift away from the one that gets tested. `_options_dislocation_legs()` asserts
# it covers both dictionaries exactly, so adding a primitive upstream fails loudly here
# instead of silently shipping a leg the page never shows.
from engine.options_dislocation import MEASURED_NULLS, PREREG_SIGNS

# --------------------------------------------------------------------------------------
# Provenance. Fintel's own pages sit behind a Cloudflare bot-verification interstitial we
# do not bypass, so the primary sources here are Fintel's SYNDICATED articles (published
# by Fintel on Nasdaq under its own byline), which carry the same boilerplate methodology
# blocks as the site plus per-name numeric readouts the site does not print in prose.
# --------------------------------------------------------------------------------------
SOURCES = {
    "fintel_amr_qvf": {
        "title": "Coal Miner Alpha Metallurgical Resources Begins 2023 Leading the QVF Quant Model",
        "publisher": "Fintel, syndicated on Nasdaq",
        "date": "2023-01-04",
        "url": "https://www.nasdaq.com/articles/coal-miner-alpha-metallurgical-resources-begins-2023-leading-the-qvf-quant-model",
        "why": "The ONLY public source that names the actual inputs behind each sub-score.",
    },
    "fintel_momentum_monday": {
        "title": "Mid-August Momentum Monday Ranks Are Sparse as Only a Half-Dozen Names Garner High Scores",
        "publisher": "Fintel, syndicated on Nasdaq",
        "date": "2023-08-21",
        "url": "https://www.nasdaq.com/articles/mid-august-momentum-monday-ranks-are-sparse-as-only-a-half-dozen-names-garner-high-scores",
        "why": "Ten (Q, V, M, QVM) tuples — the evidence the combination rule is fitted to.",
    },
    "fintel_qv": {
        "title": "Quality + Value: Most Promising Multi-Bagger Candidates",
        "publisher": "Fintel", "date": "accessed 2026-08-05",
        "url": "https://fintel.io/qv",
        "why": "Vendor landing page. Cloudflare-gated; content known via syndication + operator quote.",
    },
    "fintel_qvm": {
        "title": "Quality + Value + Momentum: Undervalued Multi-Bagger Candidates with Momentum",
        "publisher": "Fintel", "date": "accessed 2026-08-05",
        "url": "https://fintel.io/qvm", "why": "Vendor landing page. Cloudflare-gated.",
    },
    "fintel_quant_models": {
        "title": "Beat the Market With Advanced Quantitative Models",
        "publisher": "Fintel", "date": "accessed 2026-08-05",
        "url": "https://fintel.io/quant-models", "why": "Vendor model index. Cloudflare-gated.",
    },
    "quant_investing_qvm": {
        "title": "Quality, value, momentum - the best strategy you have never heard of?",
        "publisher": "Quant Investing", "date": "accessed 2026-08-05",
        "url": "https://www.quant-investing.com/blog/quality-value-momentum-the-best-strategy-you-have-never-heard-of",
        "why": "A FULLY specified QVM screen — the reproducible control against Fintel's opaque one.",
    },
    "options_dislocation_module": {
        "title": "engine/options_dislocation.py — the feature layer, its pre-registration and its nulls",
        "publisher": "Macro Dashboard (this repo)", "date": "2026-08-05",
        "url": "https://github.com/chriswong6031-creator/macro/blob/main/engine/options_dislocation.py",
        "why": "Unlike every other model here, this one is OURS — the construction is fully "
               "readable, so 'what the vendor says' and 'what we built' are the same text.",
    },
    "options_dislocation_assessment": {
        "title": "OPTIONS_INFORMATION_DISLOCATION_ASSESSMENT.md",
        "publisher": "Macro Dashboard (this repo)", "date": "2026-08-05",
        "url": "https://github.com/chriswong6031-creator/macro/blob/main/research/options_estate/"
               "OPTIONS_INFORMATION_DISLOCATION_ASSESSMENT.md",
        "why": "The raw-vs-neutralised IC table: why every primitive is residualised against "
               "(iv30, log_spot) before it is allowed to mean anything.",
    },
}

# The operator-supplied quote from fintel.io/qv, reproduced as a vendor CLAIM.
FINTEL_QV_CLAIM = (
    "The Quality+Value Score was analysed by an independent firm and they found that an "
    "investing strategy based on the model outperformed both the Russell 2000 and the S&P "
    "over time. In one test over the period of 1992 to 2013, the theoretical CAGR of the "
    "Quality+Value score was 20.73% vs. the Russell 2000 CAGR of 10.33%. In that analysis, "
    "the Sharpe Ratios were 0.91 (Q+V) vs. 0.46 (R2000) and the Sortino Ratios were 1.18 "
    "(Q+V) vs. 0.48 (R2000)."
)

# ---------------------------------------------------------------------------------------
# The per-name numeric readouts Fintel printed. These are the ONLY quantitative window
# into the models, and they carry two independent findings (see score.py):
#   (a) QVM EXCEEDS all three of its own sub-scores for MCEM and WSM -> it cannot be a
#       CONVEX weighted average of them; it is a re-percentiled blend.
#   (b) A locally affine fit recovers V:Q:M ~ 0.59 : 0.41 : 0.11 in the top decile.
# ---------------------------------------------------------------------------------------
FINTEL_OBSERVED_SCORES = [
    # ticker,  quality, value,  momentum, qvm     (2023-08-21, US board)
    ("CLS",    72.46,   71.84,  95.36,    76.58),
    ("STRL",   89.16,   65.28,  94.97,    79.12),
    ("CMT",    82.04,   71.01,  94.38,    80.06),
    ("IESC",   65.30,   70.38,  94.36,    72.63),
    ("KRT",    82.20,   70.71,  92.97,    79.88),
    ("GAMB",   81.03,   50.87,  91.25,    68.00),
    ("SCPL",   81.16,   92.73,  85.48,    91.68),
    ("MCEM",   86.15,   89.66,  75.60,    91.04),
    ("WSM",    85.06,   89.83,  74.55,    90.64),
    ("VASO",   87.95,   91.12,  61.38,    90.08),
]
FINTEL_OBSERVED_SOURCE = "fintel_momentum_monday"

# AMR's QVF decomposition (2023-01-04) — the only place the vendor states what each
# sub-score is COMPUTED FROM rather than what it "measures".
FINTEL_AMR_READOUT = {
    "ticker": "AMR", "qvf": 94.91,
    "quality": {"score": 97.40, "stated_input": "3 year average return on investor capital of 0.42 which has grown by 11.54%"},
    "value": {"score": 92.55, "stated_input": "3 year average EBIT/EV ratio of 0.20"},
    "fund_sentiment": {"score": 74.97, "stated_input": "13.71% growth of institutional ownership on the register"},
    "universe_note": "ranks AMR in the top 10% of 36,606 screened global securities",
    "source": "fintel_amr_qvf",
}


def _leg(key, label, vendor_definition, our_definition, substrate, fidelity,
         distortion=None, disclosed=True, ref_model=None):
    return {
        "key": key, "label": label,
        "vendor_definition": vendor_definition,   # what the vendor says (or "" if silent)
        "vendor_disclosed": disclosed,            # False => our_definition is an INFERENCE
        "our_definition": our_definition,         # what legs.py actually computes
        "substrate": substrate,                   # which store it reads
        "fidelity": fidelity,                     # faithful | proxy | absent
        "distortion": distortion,                 # REQUIRED whenever fidelity != faithful
        "ref_model": ref_model,                   # this leg IS another model's composite
    }


# ---------------------------------------------------------------------------------------
# Options dislocation legs, generated from the imported pre-registration.
# ---------------------------------------------------------------------------------------
_OD_NEUTRALISED = ("cross-sectionally residualised in RANK space against (iv30, log spot) "
                   "on its own date")

# key -> (label, our_definition, fidelity, distortion)
_OD_PRIMITIVES: dict[str, tuple] = {
    "oi_tilt": (
        "Standing positioning tilt",
        "delta-weighted call OI minus put OI over their sum, " + _OD_NEUTRALISED,
        "faithful", None),
    "ivspread": (
        "Call-put IV spread (Cremers-Weinbaum)",
        "ATM call implied vol minus ATM put implied vol, " + _OD_NEUTRALISED,
        "faithful", None),
    "skew": (
        "Downside skew (Xing-Zhang-Zhao)",
        "out-of-the-money put implied vol relative to at-the-money, " + _OD_NEUTRALISED,
        "faithful", None),
    "term_slope": (
        "Term-structure slope",
        "30-day ATM implied vol minus the 60-120d ATM implied vol, " + _OD_NEUTRALISED,
        "faithful", None),
    "d5_ivspread": (
        "Call-put IV spread, 5-observation change",
        "the IV spread differenced over the name's previous 5 ledger rows, " + _OD_NEUTRALISED,
        "proxy",
        "The difference runs over PANEL ROW ORDER, and the ledger is stamped with the "
        "collector's run date — so on the first ledger 24 of these windows spanned only 3-4 "
        "real market sessions instead of 5. Thinnest primitive on the panel: 13 dates carry "
        "enough names to neutralise, against 35 for the level measures."),
    "d5_term_slope": (
        "Term slope, 5-observation change",
        "the term slope differenced over the name's previous 5 ledger rows, " + _OD_NEUTRALISED,
        "proxy",
        "Same row-order window as the IV-spread change: some 5-observation windows span "
        "3-4 real sessions because duplicate run-date stamps sit inside them."),
    "skew_accel": (
        "Skew acceleration",
        "the 5-observation change in skew, differenced again over 5 observations, "
        + _OD_NEUTRALISED,
        "proxy",
        "A difference OF a difference, so the run-date stamping compounds: both the inner "
        "and the outer window can span fewer real sessions than they claim. 13 usable dates."),
}


def _options_dislocation_legs() -> list[dict]:
    """Build the leg list from PREREG_SIGNS + MEASURED_NULLS, refusing to drift from either."""
    missing = set(PREREG_SIGNS) - set(_OD_PRIMITIVES)
    extra = set(_OD_PRIMITIVES) - set(PREREG_SIGNS)
    if missing or extra:
        raise ValueError(
            f"options_dislocation leg table is out of step with PREREG_SIGNS: "
            f"missing {sorted(missing)}, unknown {sorted(extra)}. The pre-registration is "
            f"the source of truth — add the primitive here, do not edit the signs.")

    legs = []
    for key in PREREG_SIGNS:                       # PREREG_SIGNS order is the display order
        label, definition, fidelity, distortion = _OD_PRIMITIVES[key]
        sign = "higher is bullish" if PREREG_SIGNS[key] > 0 else "higher is bearish"
        legs.append(_leg(
            key, label,
            f"pre-registered sign: {sign}",
            definition,
            "data/options_dislocation/snapshots.parquet (pit)",
            fidelity, distortion))

    # Every measured null ships as an `absent` leg carrying its own evidence. Emitting only
    # the three entitlement-blocked ones would drop the two that were MEASURED dead, which is
    # the half of "nulls printed, not hidden" that is easiest to lose.
    for key, n in MEASURED_NULLS.items():
        legs.append(_leg(
            key, key.replace("_", " ").capitalize(),
            f"state: {n['state']}",
            "not computable on our entitlements — emitted as an explicit null",
            "none — see distortion",
            "absent",
            f"{n['why']} Substitute tested: {n['substitute_tested']}."))
        # NB: disclosed stays True. `vendor_disclosed=False` means "our_definition is an
        # INFERENCE"; these are the opposite — documented absences in a module we wrote, each
        # carrying the measurement that killed it. Nothing in this model is inferred.
    return legs


# =======================================================================================
# MODELS
# =======================================================================================
MODELS: dict[str, dict] = {

    # -----------------------------------------------------------------------------------
    "fintel_qv": {
        "name": "Quality + Value (QV / QuantSoft)",
        "name_zh": "质量＋价值",
        "vendor": "Fintel",
        "family": "fintel",
        "one_line": "Durable cash generators that have fallen out of favour.",
        "vendor_says": (
            "A six-factor model that ranks companies on their cash-generating ability and "
            "growth, with a significant value factor. Developed by Wilton Risenhoover from "
            "research at UCLA Anderson. Scored 0-100 as a percentile of a screened universe."
        ),
        "disclosure": "partial",
        "disclosure_note": (
            "Fintel names TWO of the six factors (3y average ROIC + its growth; 3y average "
            "EBIT/EV) and never names the other four, their weights, or the winsorisation. "
            "Any six-factor claim below the two named legs is OUR inference from the stated "
            "lineage ('cash-generating ability and growth' + 'significant value factor')."
        ),
        "provenance": ["fintel_amr_qvf", "fintel_momentum_monday", "fintel_qv"],
        "legs": [
            _leg("roic_3y", "3y average ROIC",
                 "3 year average return on investor capital",
                 "mean over the 3 most recent knowable FYs of NOPAT / invested capital, "
                 "NOPAT = op_income x (1 - 21%), invested capital = equity + total debt - cash",
                 "edgar fundamentals_panel (pit) + statements_quarterly.cash (pit)",
                 "proxy",
                 "Fintel does not state its tax rate, its debt definition, or whether cash is "
                 "netted. debt_lt is present for only ~49% of the panel and short-term debt is "
                 "absent entirely, so invested capital is understated for levered names -> ROIC "
                 "overstated for exactly the leveraged small caps this model targets."),
            _leg("roic_growth", "ROIC growth",
                 "...which has grown by 11.54%",
                 "ROIC(latest FY) / ROIC(FY-2) - 1, defined only when the base ROIC is positive",
                 "edgar fundamentals_panel (pit)",
                 "proxy",
                 "The vendor's growth window and base are unstated; a 3y CAGR and a 2y "
                 "point-to-point differ materially for cyclicals, which is most of the "
                 "model's published winners (coal, cement, packaging)."),
            _leg("ebit_ev_3y", "3y average EBIT/EV",
                 "3 year average EBIT/EV ratio",
                 "mean over the 3 most recent knowable FYs of op_income / enterprise value, "
                 "EV = market cap + total debt - cash, priced at the rebalance date",
                 "edgar fundamentals_panel (pit) + statements_quarterly.cash (pit) + closes",
                 "proxy",
                 "op_income is EBIT only when there are no material non-operating items; and "
                 "the vendor almost certainly re-prices EV at each historical FY, whereas we "
                 "hold market cap at the rebalance date across all three FYs. Ours is "
                 "therefore 'current EV vs 3y average EBIT', not a 3y average of the ratio."),
            _leg("gross_profitability", "Gross profitability (GP/Assets)",
                 "", "gross_profit / assets (Novy-Marx)",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "INFERRED leg — the vendor never names it. Included because 'cash-generating "
                 "ability' is the stated construct and GP/A is its canonical published form. "
                 "gross_profit covers only ~43% of the panel.", disclosed=False),
            _leg("accruals", "Low accruals",
                 "", "-(ni - cfo) / assets (Sloan) — higher is better",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "INFERRED leg. The stated construct is cash generation, and the accrual gap "
                 "between earnings and cash is its standard published test.", disclosed=False),
            _leg("fcf_to_debt", "FCF / total debt",
                 "", "(cfo - capex) / total debt",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "INFERRED leg. capex covers only ~32% of the pit panel, so this leg is "
                 "computable on roughly a third of the universe.", disclosed=False),
        ],
        "combination": {
            "rule": "unknown",
            "note": (
                "Not disclosed. Our study scores it as a re-percentiled equal-weight blend of "
                "the available legs, which is a CHOICE, not the vendor's rule."
            ),
        },
        "vendor_claims": [
            {"claim": FINTEL_QV_CLAIM, "source": "fintel_qv",
             "appraisal": (
                 "Reproduced as the vendor's claim. It is not evidence about our universe: the "
                 "window (1992-2013) predates the model's publication, the benchmark is the "
                 "Russell 2000 (small caps), the testing firm is unnamed, and no turnover, "
                 "capacity, or transaction-cost assumption is stated. Treat as marketing "
                 "provenance, not a prior."
             )},
        ],
    },

    # -----------------------------------------------------------------------------------
    "fintel_qvm": {
        "name": "Quality + Value + Momentum (QVM)",
        "name_zh": "质量＋价值＋动量",
        "vendor": "Fintel",
        "family": "fintel",
        "one_line": "QV with a light momentum tilt — the vendor's 'enhanced' board.",
        "vendor_says": (
            "Fintel's QV Score combined with the Quantitative Momentum Model (QMM). The "
            "momentum score factors the share price performance over the last 6 months."
        ),
        "disclosure": "partial",
        "disclosure_note": (
            "The momentum LOOKBACK is disclosed (6 months); the combination weights are not. "
            "We fitted them from ten published (Q, V, M, QVM) tuples — see score.py."
        ),
        "provenance": ["fintel_momentum_monday", "fintel_qvm"],
        "legs": [
            _leg("qv_composite", "QV composite", "Fintel's QV score",
                 "the fintel_qv recreation's composite percentile",
                 "engine.quant_lab (recursive)", "proxy",
                 "inherits every fintel_qv leg distortion", ref_model="fintel_qv"),
            _leg("momentum_6m", "6-month price momentum",
                 "share price performance over the last 6 months",
                 "close(t) / close(t - 126 trading days) - 1",
                 "data/yahoo close caches (pit-truncated)", "faithful"),
        ],
        "combination": {
            "rule": "blend_then_rank",
            "weights": {"quality": 0.41, "value": 0.59, "momentum": 0.11},
            "fitted": True,
            "note": (
                "FITTED, not disclosed. OLS of QVM on (Q, V, M) over the ten published tuples "
                "gives 0.410 Q + 0.588 V + 0.110 M - 5.70 with R2 = 0.998 and max residual "
                "0.60. Weights summing above 1 (1.108) with a negative intercept is the "
                "signature of a blend that is then RE-PERCENTILED: in the thin upper tail the "
                "rank map is locally linear with slope > 1. Confirmed independently — MCEM and "
                "WSM both score HIGHER on QVM than on any of their three sub-scores, which no "
                "convex weighted average can do. Read plainly: QVM is the QV score with a "
                "LIGHT momentum tilt (~11%), which matches the vendor's own framing that "
                "momentum 'slightly' adjusts the ranks. Caveat: n = 10, one date, all high "
                "scorers, so this is the TOP-DECILE local rule, not the global one."
            ),
        },
        "vendor_claims": [
            {"claim": "An enhanced quantitative model to improve on the returns of the "
                      "original Quality/Value model.",
             "source": "fintel_momentum_monday",
             "appraisal": "No separate QVM backtest statistic is published anywhere we can find."},
        ],
    },

    # -----------------------------------------------------------------------------------
    "fintel_qvo": {
        "name": "Quality + Value + Fund Sentiment (QVO / QVF)",
        "name_zh": "质量＋价值＋基金情绪",
        "vendor": "Fintel",
        "family": "fintel",
        "one_line": "QV tilted toward names institutions are accumulating.",
        "vendor_says": (
            "Adds two more factors to the Quality/Value Score — both based on measures of fund "
            "sentiment. The addition slightly increases the ranks of companies that have high "
            "accumulation by institutions."
        ),
        "disclosure": "partial",
        "disclosure_note": (
            "Two fund-sentiment factors are claimed; one is illustrated ('13.71% growth of "
            "institutional ownership on the register'). The second is never named."
        ),
        "provenance": ["fintel_amr_qvf"],
        "legs": [
            _leg("qv_composite", "QV composite", "Fintel's QV score",
                 "the fintel_qv recreation's composite percentile",
                 "engine.quant_lab (recursive)", "proxy",
                 "inherits every fintel_qv leg distortion", ref_model="fintel_qv"),
            _leg("fund_sentiment", "Institutional ownership growth",
                 "growth of institutional ownership on the register",
                 "quarter-on-quarter growth in shares held, summed across tracked funds",
                 "data/smart_money/<fund>/<period_end>.parquet", "absent",
                 "MEASURED AT 1.3% COVERAGE — effectively absent, and graded as such rather "
                 "than shipped as a working leg. Two independent reasons: Fintel reads the "
                 "full 13F register (444 owners for AMR) while we track 53 curated managers, "
                 "so the construct differs; and after CUSIP/name resolution only ~20 names "
                 "have two consecutive quarters inside our universe. A leg on 1.3% of the "
                 "panel cannot rank it, so QVO is NOT recreatable here today. Closing this "
                 "needs a full 13F aggregate feed, not a better mapper."),
        ],
        "combination": {"rule": "unknown",
                        "note": "Not disclosed; the second fund-sentiment factor is not even named."},
        "vendor_claims": [
            {"claim": "...is expected to improve returns over the long term.",
             "source": "fintel_amr_qvf",
             "appraisal": "An expectation, not a measurement. No statistic is attached to it."},
        ],
    },

    # -----------------------------------------------------------------------------------
    "quant_investing_qvm": {
        "name": "Quality-Value-Momentum screen (Quant Investing)",
        "name_zh": "质量－价值－动量筛选",
        "vendor": "Quant Investing",
        "family": "external_published",
        "one_line": "A fully specified sequential screen — the reproducible control.",
        "vendor_says": (
            "Sequential elimination: FCF-to-Debt 0-70%, Gross Margin (Marx) 0-70%, Accrual "
            "Ratio CF 30-100%; then the top 20% by earnings yield (EBIT/EV); then the top 50% "
            "by combined 3-month and 6-month Price Index; then 20 stocks ranked by Value "
            "Composite One."
        ),
        "disclosure": "full",
        "disclosure_note": (
            "This one IS fully specified, which is why the lab carries it: it is the control "
            "that separates 'the Fintel model does not work here' from 'our recreation of it "
            "is wrong'. If a fully-disclosed screen of the same construct also ranks nothing "
            "on our panel, the fault is the substrate or the universe, not the reconstruction."
        ),
        "provenance": ["quant_investing_qvm"],
        "legs": [
            _leg("fcf_to_debt", "FCF / debt screen", "retain FCF-to-Debt in the 0-70% band",
                 "(cfo - capex) / total debt, percentile-banded",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "capex coverage ~32% on the pit panel"),
            _leg("gross_margin", "Gross margin (Marx)", "retain gross margin in the 0-70% band",
                 "gross_profit / revenue, percentile-banded",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "gross_profit coverage ~43%; Novy-Marx's own construct is GP/ASSETS, not "
                 "GP/revenue — the vendor's 'Gross Margin (Marx)' label conflates the two"),
            _leg("accrual_ratio_cf", "Accrual ratio (CF)", "retain the 30-100% band",
                 "-(ni - cfo) / assets, percentile-banded",
                 "edgar fundamentals_panel (pit)", "proxy",
                 "The vendor's 'Accrual Ratio CF' scales the accrual by average NET "
                 "OPERATING ASSETS; we scale by total assets because the panel carries no "
                 "operating-asset split. Same sign, different denominator — the ordering "
                 "differs most for asset-heavy financials."),
            _leg("ebit_ev", "Earnings yield", "top 20% by EBIT to enterprise value",
                 "op_income / EV", "edgar fundamentals_panel + statements_quarterly + closes",
                 "proxy", "same EV caveats as fintel_qv"),
            _leg("momentum_3_6", "3m + 6m price index", "top 50% by combined 3m and 6m momentum",
                 "mean of the 3m and 6m return percentiles",
                 "data/yahoo close caches (pit-truncated)", "faithful"),
        ],
        "combination": {
            "rule": "sequential_screen",
            "note": "Sequential elimination, then rank the survivors. Not a score blend.",
        },
        "vendor_claims": [
            {"claim": "European equities 2001-06-29 to 2014-08-22 (13.16y), STOXX 600 TR "
                      "benchmark, 20 positions, 6-month rebalance, 0.6% cost per rebalance: "
                      "total return 1,141.8% vs 57.2%; CAGR 21.1% vs 3.5%; max drawdown -50.8% "
                      "vs -58.4%; Sharpe 1.05; annualised stdev 20.2%; win rate 66.1%.",
             "source": "quant_investing_qvm",
             "appraisal": (
                 "A different continent, a different era, and a 20-name concentrated book with "
                 "a -50.8% drawdown. The drawdown is the number that travels: this is a "
                 "high-variance construct even on its own home data."
             )},
        ],
    },

    # -----------------------------------------------------------------------------------
    "options_dislocation": {
        "name": "Options information dislocation",
        "name_zh": "期权信息错位",
        "vendor": "Macro Dashboard",
        "family": "internal",
        "one_line": "What the options surface says that the share price has not said yet.",
        "vendor_says": (
            "Ours, not a vendor's — so this row is the construction itself. Seven options-"
            "surface primitives, each cross-sectionally residualised against implied-vol LEVEL "
            "and size before it is allowed to mean anything, because run naively almost every "
            "'options information' feature is a repackaged bet on implied vol. Measured on our "
            "own panel: expected-move was ENTIRELY the vol level, and 86% of the IV-vs-realised "
            "signal was."
        ),
        "disclosure": "full",
        "disclosure_note": (
            "The only fully-disclosed model on this page, because we wrote it. That inverts "
            "the usual problem here: nothing is hidden, so the constraint is not disclosure "
            "but EVIDENCE — six weeks of one regime. It also ships in a deliberately "
            "un-rankable shape: RO-2 / Signal Commons R3 forbids a fused pre-gate composite, "
            "so there is no score to lift, only named primitives read one at a time, and the "
            "reads may only ever lower confidence in a candidate, never originate one."
        ),
        "provenance": ["options_dislocation_module", "options_dislocation_assessment"],
        # Declared, not inferred from the leg mix. Five of the twelve legs are `absent`, which
        # would trip the "cannot be rebuilt here" heuristic — but this layer is not a
        # reconstruction of somebody else's model, it is ours, it runs nightly, and the five
        # absences are a documented boundary of the data rather than a failure to rebuild.
        "buildable": True,
        "legs": _options_dislocation_legs(),
        "combination": {
            "rule": "none_categorical",
            "note": (
                "There is deliberately no composite, and its absence is the design. A fused "
                "escalating score is a FORBIDDEN shape before the gate (RO-2 / Signal Commons "
                "R3), so the multi-primitive families ship as categorical reads over named, "
                "separately-visible primitives and only genuinely single-primitive measures "
                "carry a number. Each primitive is scored on its own against its own "
                "pre-registered sign; nothing is blended into something rankable."
            ),
        },
        "vendor_claims": [
            {"claim": "Options-surface context, cross-sectionally neutralised against "
                      "implied-vol level and size so it reads as information rather than a "
                      "repackaged volatility bet. DISPLAY-ONLY: the chain panel is one short "
                      "regime, far below the history a return-predictor verdict needs.",
             "source": "options_dislocation_module",
             "appraisal": (
                 "Our own disclaimer, reproduced here because it is the claim being tested. "
                 "The lab's read agrees with it and sharpens it: on the panel as it stands, "
                 "every primitive returns `insufficient` once the overlapping 5-day windows "
                 "are counted as the ~6 independent observations they actually are. Scored "
                 "without that correction all seven would have come back as FDR survivors — "
                 "which is what a six-week single-regime panel looks like when a quarterly "
                 "harness is pointed at it unchanged."
             )},
        ],
    },
}


# =======================================================================================
# Substrate ledger — the honest inventory the page prints.
# =======================================================================================
SUBSTRATE = {
    "edgar_fundamentals_panel": {
        "path": "data/edgar/fundamentals_panel.parquet",
        "point_in_time": True,
        "pit_key": "asof_date (period_end + reporting lag; 436 distinct dates)",
        "span": "FY2009-FY2025", "tickers": 1552,
        "note": "The deep PIT spine. Lacks cash and short-term debt.",
    },
    "edgar_statements_quarterly": {
        "path": "data/edgar/statements_quarterly.parquet",
        "point_in_time": True,
        "pit_key": "filed (3,452 distinct filing dates)",
        "span": "2009Q1-2026Q2", "tickers": 1507,
        "note": "Where cash (90.6%) and net_debt (51%) come from.",
    },
    "edgar_statements": {
        "path": "data/edgar/statements.parquet",
        "point_in_time": False,
        "pit_key": "as_of is a FETCH timestamp (5 distinct, all 2026-06-15) — NOT a filing date",
        "span": "FY2020-FY2025", "tickers": 1506,
        "note": "LIVE MODE ONLY. Richest schema (cash, debt_cur, inventory, receivables) but "
                "using it in a backtest would make every row knowable at every past date.",
    },
    "smart_money": {
        "path": "data/smart_money/<fund>/<period_end>.parquet",
        "point_in_time": True, "pit_key": "filing_date",
        "span": "13F quarters", "tickers": "53 tracked funds",
        "note": "A curated manager set, NOT the 13F institutional register.",
    },
    "options_dislocation_snapshots": {
        "path": "data/options_dislocation/snapshots.parquet",
        "point_in_time": True,
        "pit_key": ("date = the chain snapshot's own stamp (41 stamps, 2026-06-15..07-31). "
                    "NOT a fetch timestamp — but it IS the collector's RUN date: 9 of the 41 "
                    "stamps repeat the prior session byte-for-byte, because weekend and Monday "
                    "runs re-read the same Friday chain. 32 distinct market sessions."),
        "span": "2026-06-15 to 2026-07-31 — six weeks, ONE regime",
        "tickers": 392,
        "note": "Safe for history tests: every row is OLDER than its stamp, so nothing leaks "
                "forward — the run-date stamping costs alignment, not hindsight. Duplicate "
                "sessions are collapsed before scoring. The first 6 stamps carry 10 names "
                "each, below the 20 the cross-sectional neutralisation needs, so their "
                "neutralised columns are empty; usable coverage runs 35 dates for the level "
                "primitives down to 13 for the changes.",
    },
    "closes": {
        "path": "data/yahoo/<ticker>.parquet + data/breadth/_closes_cache.parquet",
        "point_in_time": True, "pit_key": "trading date (truncate to asof)",
        "span": "rolling ~3y per name in-tree; deeper history is fetched, not committed",
        "tickers": 739,
        "note": "The binding constraint on how far back a momentum leg can be studied.",
    },
}

# The coverage fact that decides the whole assessment.
#
# `our_fundamentals_universe` and `published_leaders_in_our_fundamentals_panel` are
# LIVE-DERIVED at page-build time (engine/quant_lab/page.py:_live_coverage) — they were
# hardcoded at 1,552/4 and W2-A (#4688) widened the panel to ~2,826, which would have left
# the page printing a stale coverage chip and the flatly false sentence "CMT and KRT are in
# our price universe with no fundamentals at all". The values below are FALLBACKS used only
# when the panel cannot be read. `*_at_study` is the frozen historical fact — the study's IC
# numbers were computed on the 1,552-name panel and do not change when the panel grows.
UNIVERSE_GAP = {
    "our_price_universe": 2895,
    "our_price_universe_groups": {"r2000": 1994, "sp600": 633, "sp500": 509, "sp400": 412},
    "our_fundamentals_universe": 1552,
    "our_fundamentals_universe_at_study": 1552,
    "fintel_screened": 36606,
    "fintel_covered": 75000,
    "published_leaders_tested": 10,
    # EXACTLY the ten QVM leaders published 2023-08-21, so the numerator and the
    # denominator describe the same set. AMR is deliberately NOT here: it comes from the
    # separate QVF article and was previously counted INTO the numerator against this
    # denominator of 10, which is what made the stamped figure 4 rather than 3.
    "published_leaders": ["STRL", "IESC", "WSM", "CLS", "CMT",
                          "KRT", "GAMB", "SCPL", "MCEM", "VASO"],
    "published_leaders_in_our_fundamentals_panel": 3,
    # Verified against the committed pre-W2-A panel: STRL, IESC, WSM.
    "published_leaders_in_our_fundamentals_panel_at_study": 3,
    "note": (
        "Our PRICE universe reaches the Russell 2000. The EDGAR fundamentals panel — the "
        "binding universe for any QV recreation — used to stop at 1,552 names, and only 3 "
        "of the ten QVM leaders Fintel published on 2023-08-21 were inside it. W2-A widened "
        "the panel to the full tracked price universe: CMT and KRT, both previously in our "
        "price universe with no fundamentals at all, are now covered. The measurement on "
        "this page still ran on the narrower 1,552-name panel — the model is explicitly a "
        "small-cap 'multi-bagger' finder benchmarked to the Russell 2000, so its re-test on "
        "the widened panel is the read that will actually judge it, and that re-test has "
        "not run yet."
    ),
}


def model(key: str) -> dict:
    """One model spec. KeyError is intentional — a typo'd key must not silently return {}."""
    return MODELS[key]


def resolve_leg_keys(key: str, _seen: frozenset = frozenset()) -> dict[str, float]:
    """Flatten a model into CONCRETE leg keys -> weight, expanding `ref_model` legs.

    QVM's first leg is not a column, it IS the QV model. Without expansion the scorer
    silently drops it and QVM collapses to its momentum leg — which then gets reported
    under the QVM name. That happened on the first study run: `fintel_qvm` came back
    "survives FDR" on an IC identical to plain 6-month momentum. A model that reduces to
    one of its own legs is not that model.

    Weights follow the spec's fitted combination where one exists: for QVM, the fitted
    momentum share (0.11) goes to the momentum leg and the remainder is split across the
    expanded QV legs, so the blend reproduces the vendor's stated "slight" momentum tilt
    rather than giving momentum equal footing with six fundamental legs.
    """
    if key in _seen:                                   # cycle guard
        raise ValueError(f"circular ref_model chain at {key!r}")
    spec = MODELS[key]
    fitted = (spec.get("combination") or {}).get("weights") or {}
    mom_w = float(fitted.get("momentum", 0.0)) if fitted else 0.0

    refs = [x for x in spec["legs"] if x.get("ref_model")]
    plain = [x for x in spec["legs"] if not x.get("ref_model") and x["fidelity"] != "absent"]

    out: dict[str, float] = {}
    if refs and mom_w > 0 and plain:
        ref_share, own_share = 1.0 - mom_w, mom_w
    elif refs:
        ref_share = len(refs) / max(1, len(refs) + len(plain))
        own_share = 1.0 - ref_share
    else:
        ref_share, own_share = 0.0, 1.0

    for r in refs:
        sub = resolve_leg_keys(r["ref_model"], _seen | {key})
        tot = sum(sub.values()) or 1.0
        for k, w in sub.items():
            out[k] = out.get(k, 0.0) + ref_share * (w / tot) / len(refs)
    for p in plain:
        out[p["key"]] = out.get(p["key"], 0.0) + own_share / len(plain)
    return out


def leg_fidelity_summary(key: str) -> dict:
    """Counts by fidelity grade + the legs whose definition we INFERRED rather than read."""
    legs = MODELS[key]["legs"]
    return {
        "n_legs": len(legs),
        "faithful": sum(1 for x in legs if x["fidelity"] == "faithful"),
        "proxy": sum(1 for x in legs if x["fidelity"] == "proxy"),
        "absent": sum(1 for x in legs if x["fidelity"] == "absent"),
        "inferred_legs": [x["key"] for x in legs if not x["vendor_disclosed"]],
    }
