/* GENERATED from engine/cycle_ontology.py
   version 1.1.0
   DO NOT EDIT — regenerate: python -m scripts.gen_ontology_js */

(function (root) {
  var payload = {
  "version": "1.1.0",
  "detector_version": 2,
  "phases": {
    "Trough": {
      "label": "Trough",
      "short": "Bottoming",
      "hue": "#5b9bf0",
      "label_zh": "底部",
      "short_zh": "筑底"
    },
    "Recovery": {
      "label": "Recovery",
      "short": "Prime entry",
      "hue": "#2dd4bf",
      "label_zh": "复苏",
      "short_zh": "入场"
    },
    "Expansion": {
      "label": "Expansion",
      "short": "Trending",
      "hue": "#45b873",
      "label_zh": "扩张",
      "short_zh": "扩张"
    },
    "Peak": {
      "label": "Peak",
      "short": "Topping",
      "hue": "#e0a030",
      "label_zh": "顶部",
      "short_zh": "做顶"
    },
    "Downturn": {
      "label": "Downturn",
      "short": "Rolling over",
      "hue": "#e0556b",
      "label_zh": "下行",
      "short_zh": "下行"
    }
  },
  "zones": [
    {
      "lo": 84.0,
      "hi": 100.0,
      "word": "Stretched",
      "word_zh": "超涨"
    },
    {
      "lo": 68.0,
      "hi": 84.0,
      "word": "Elevated",
      "word_zh": "偏高"
    },
    {
      "lo": 32.0,
      "hi": 68.0,
      "word": "Mid-range",
      "word_zh": "中位"
    },
    {
      "lo": 16.0,
      "hi": 32.0,
      "word": "Depressed",
      "word_zh": "偏低"
    },
    {
      "lo": 0.0,
      "hi": 16.0,
      "word": "Washed out",
      "word_zh": "超跌"
    }
  ],
  "stances": {
    "AVOID": {
      "en": "Avoid",
      "zh": "回避",
      "tone": "bearish"
    },
    "WAIT": {
      "en": "Wait",
      "zh": "观望",
      "tone": "neutral"
    },
    "GET READY": {
      "en": "Get Ready",
      "zh": "准备",
      "tone": "anticipatory"
    },
    "BUY": {
      "en": "Buy",
      "zh": "买入",
      "tone": "bullish"
    },
    "HOLD": {
      "en": "Hold",
      "zh": "持有",
      "tone": "bullish"
    },
    "TRIM": {
      "en": "Trim",
      "zh": "减仓",
      "tone": "caution"
    },
    "SELL": {
      "en": "Sell",
      "zh": "卖出",
      "tone": "bearish"
    },
    "COUNTERTREND ONLY": {
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "tone": "caution"
    },
    "HIGH-RISK BOUNCE": {
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "tone": "caution"
    }
  },
  "ladder": [
    "DECLINE",
    "BOTTOM WATCH",
    "TURN SIGNALED",
    "FRESH BUY",
    "RALLY ON",
    "TOP WATCH",
    "ROLLING OVER",
    "COUNTERTREND BOUNCE",
    "CONFIRMING TURN"
  ],
  "ladder_dir": {
    "DECLINE": -1,
    "BOTTOM WATCH": -1,
    "TURN SIGNALED": 1,
    "FRESH BUY": 1,
    "RALLY ON": 1,
    "TOP WATCH": 0,
    "ROLLING OVER": -1,
    "COUNTERTREND BOUNCE": 0,
    "CONFIRMING TURN": 0
  },
  "crosswalk": {
    "Trough|DECLINE": {
      "stance": "AVOID",
      "divergence": false,
      "tone": "bearish",
      "en": "Avoid",
      "zh": "回避",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|DECLINE": {
      "stance": "AVOID",
      "divergence": true,
      "tone": "bearish",
      "en": "Avoid",
      "zh": "回避",
      "note_en": "The broader phase suggests recovery, but the daily cycle has failed. Phase confidence is low; treat as bottoming rather than confirmed entry.",
      "note_zh": "更大级别阶段显示复苏，但日线周期已失败。阶段置信度低；视为筑底而非确认入场。"
    },
    "Expansion|DECLINE": {
      "stance": "WAIT",
      "divergence": true,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "The trend phase is Expansion but the daily cycle is in Decline. Tactical caution warranted; wait for daily recovery confirmation.",
      "note_zh": "趋势阶段为扩张，但日线周期处于下行。需战术谨慎；等待日线周期恢复确认。"
    },
    "Peak|DECLINE": {
      "stance": "TRIM",
      "divergence": false,
      "tone": "caution",
      "en": "Trim",
      "zh": "减仓",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|DECLINE": {
      "stance": "AVOID",
      "divergence": false,
      "tone": "bearish",
      "en": "Avoid",
      "zh": "回避",
      "note_en": "",
      "note_zh": ""
    },
    "Trough|BOTTOM WATCH": {
      "stance": "GET READY",
      "divergence": false,
      "tone": "anticipatory",
      "en": "Get Ready",
      "zh": "准备",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|BOTTOM WATCH": {
      "stance": "GET READY",
      "divergence": false,
      "tone": "anticipatory",
      "en": "Get Ready",
      "zh": "准备",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|BOTTOM WATCH": {
      "stance": "WAIT",
      "divergence": false,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|BOTTOM WATCH": {
      "stance": "COUNTERTREND ONLY",
      "divergence": true,
      "tone": "caution",
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "note_en": "Cycle read is Topping; the daily timing ladder is hunting a short-term low. Any buy here is countertrend only.",
      "note_zh": "周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。"
    },
    "Downturn|BOTTOM WATCH": {
      "stance": "WAIT",
      "divergence": false,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "",
      "note_zh": ""
    },
    "Trough|TURN SIGNALED": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|TURN SIGNALED": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|TURN SIGNALED": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|TURN SIGNALED": {
      "stance": "COUNTERTREND ONLY",
      "divergence": true,
      "tone": "caution",
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "note_en": "Cycle read is Topping; the daily timing ladder is hunting a short-term low. Any buy here is countertrend only.",
      "note_zh": "周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。"
    },
    "Trough|FRESH BUY": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|FRESH BUY": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|FRESH BUY": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|FRESH BUY": {
      "stance": "COUNTERTREND ONLY",
      "divergence": true,
      "tone": "caution",
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "note_en": "Cycle read is Topping; the daily timing ladder is hunting a short-term low. Any buy here is countertrend only.",
      "note_zh": "周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。"
    },
    "Trough|RALLY ON": {
      "stance": "HOLD",
      "divergence": true,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "Cycle read is washed out / bottoming; daily sell signals are late-downleg noise. Stance is Wait — the sell opportunity has passed.",
      "note_zh": "周期读数为超跌/筑底阶段；日线卖出信号属下行尾段噪音。立场观望——卖出时机已过。"
    },
    "Recovery|RALLY ON": {
      "stance": "HOLD",
      "divergence": false,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|RALLY ON": {
      "stance": "HOLD",
      "divergence": false,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|RALLY ON": {
      "stance": "HOLD",
      "divergence": false,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|RALLY ON": {
      "stance": "HOLD",
      "divergence": true,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "The cycle is in Downturn but the daily ladder shows a rallying structure. Hold, but trim into strength — the larger trend is down.",
      "note_zh": "周期处于下行阶段，但日线阶梯显示反弹结构。持有，但逢强减仓——更大趋势向下。"
    },
    "Trough|TOP WATCH": {
      "stance": "WAIT",
      "divergence": true,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "Cycle read is washed out / bottoming; daily sell signals are late-downleg noise. Stance is Wait — the sell opportunity has passed.",
      "note_zh": "周期读数为超跌/筑底阶段；日线卖出信号属下行尾段噪音。立场观望——卖出时机已过。"
    },
    "Recovery|TOP WATCH": {
      "stance": "HOLD",
      "divergence": false,
      "tone": "bullish",
      "en": "Hold",
      "zh": "持有",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|TOP WATCH": {
      "stance": "TRIM",
      "divergence": false,
      "tone": "caution",
      "en": "Trim",
      "zh": "减仓",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|TOP WATCH": {
      "stance": "TRIM",
      "divergence": false,
      "tone": "caution",
      "en": "Trim",
      "zh": "减仓",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|TOP WATCH": {
      "stance": "TRIM",
      "divergence": false,
      "tone": "caution",
      "en": "Trim",
      "zh": "减仓",
      "note_en": "",
      "note_zh": ""
    },
    "Trough|ROLLING OVER": {
      "stance": "WAIT",
      "divergence": true,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "Cycle read is washed out / bottoming; daily sell signals are late-downleg noise. Stance is Wait — the sell opportunity has passed.",
      "note_zh": "周期读数为超跌/筑底阶段；日线卖出信号属下行尾段噪音。立场观望——卖出时机已过。"
    },
    "Recovery|ROLLING OVER": {
      "stance": "WAIT",
      "divergence": true,
      "tone": "neutral",
      "en": "Wait",
      "zh": "观望",
      "note_en": "The broader phase suggests recovery, but the daily cycle has failed. Phase confidence is low; treat as bottoming rather than confirmed entry.",
      "note_zh": "更大级别阶段显示复苏，但日线周期已失败。阶段置信度低；视为筑底而非确认入场。"
    },
    "Expansion|ROLLING OVER": {
      "stance": "TRIM",
      "divergence": false,
      "tone": "caution",
      "en": "Trim",
      "zh": "减仓",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|ROLLING OVER": {
      "stance": "SELL",
      "divergence": false,
      "tone": "bearish",
      "en": "Sell",
      "zh": "卖出",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|ROLLING OVER": {
      "stance": "SELL",
      "divergence": false,
      "tone": "bearish",
      "en": "Sell",
      "zh": "卖出",
      "note_en": "",
      "note_zh": ""
    },
    "Trough|COUNTERTREND BOUNCE": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|COUNTERTREND BOUNCE": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|COUNTERTREND BOUNCE": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|COUNTERTREND BOUNCE": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|COUNTERTREND BOUNCE": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Trough|CONFIRMING TURN": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Recovery|CONFIRMING TURN": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Expansion|CONFIRMING TURN": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Peak|CONFIRMING TURN": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|CONFIRMING TURN": {
      "stance": "HIGH-RISK BOUNCE",
      "divergence": false,
      "tone": "caution",
      "en": "High-Risk Bounce",
      "zh": "高风险反弹",
      "note_en": "",
      "note_zh": ""
    },
    "Downturn|TURN SIGNALED|pos>=55": {
      "stance": "COUNTERTREND ONLY",
      "divergence": true,
      "tone": "caution",
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "note_en": "Position is elevated in a Downturn phase. Daily buy signal is countertrend — the larger cycle suggests the rebound will fail.",
      "note_zh": "下行阶段中位置偏高。日线买入信号属逆势——更大级别周期暗示反弹将失败。",
      "pos_gate": ">=55"
    },
    "Downturn|TURN SIGNALED|pos<55": {
      "stance": "GET READY",
      "divergence": false,
      "tone": "anticipatory",
      "en": "Get Ready",
      "zh": "准备",
      "note_en": "",
      "note_zh": "",
      "pos_gate": "<55"
    },
    "Downturn|FRESH BUY|pos>=55": {
      "stance": "COUNTERTREND ONLY",
      "divergence": true,
      "tone": "caution",
      "en": "Countertrend Only",
      "zh": "仅限逆势短线",
      "note_en": "Position is elevated in a Downturn phase. Daily buy signal is countertrend — the larger cycle suggests the rebound will fail.",
      "note_zh": "下行阶段中位置偏高。日线买入信号属逆势——更大级别周期暗示反弹将失败。",
      "pos_gate": ">=55"
    },
    "Downturn|FRESH BUY|pos<55": {
      "stance": "BUY",
      "divergence": false,
      "tone": "bullish",
      "en": "Buy",
      "zh": "买入",
      "note_en": "",
      "note_zh": "",
      "pos_gate": "<55"
    }
  },
  "divergence_notes": {
    "peak_buy_signal": {
      "en": "Cycle read is Topping; the daily timing ladder is hunting a short-term low. Any buy here is countertrend only.",
      "zh": "周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。"
    },
    "extended_uptrend": {
      "en": "Position is stretched above trend, but the 200-day trend and momentum are still up — a late-stage continuation, not a fresh entry. Don't chase; this is NOT a topping or countertrend signal.",
      "zh": "位置已高于趋势并偏拉伸，但200日趋势与动量仍向上——属晚段延续，而非新入场点。不宜追高；这并非见顶或逆势信号。"
    },
    "decline_recovery": {
      "en": "The broader phase suggests recovery, but the daily cycle has failed. Phase confidence is low; treat as bottoming rather than confirmed entry.",
      "zh": "更大级别阶段显示复苏，但日线周期已失败。阶段置信度低；视为筑底而非确认入场。"
    },
    "decline_expansion": {
      "en": "The trend phase is Expansion but the daily cycle is in Decline. Tactical caution warranted; wait for daily recovery confirmation.",
      "zh": "趋势阶段为扩张，但日线周期处于下行。需战术谨慎；等待日线周期恢复确认。"
    },
    "sell_in_trough": {
      "en": "Cycle read is washed out / bottoming; daily sell signals are late-downleg noise. Stance is Wait — the sell opportunity has passed.",
      "zh": "周期读数为超跌/筑底阶段；日线卖出信号属下行尾段噪音。立场观望——卖出时机已过。"
    },
    "sell_in_downturn": {
      "en": "The cycle is in Downturn but the daily ladder shows a rallying structure. Hold, but trim into strength — the larger trend is down.",
      "zh": "周期处于下行阶段，但日线阶梯显示反弹结构。持有，但逢强减仓——更大趋势向下。"
    },
    "countertrend_downturn_high": {
      "en": "Position is elevated in a Downturn phase. Daily buy signal is countertrend — the larger cycle suggests the rebound will fail.",
      "zh": "下行阶段中位置偏高。日线买入信号属逆势——更大级别周期暗示反弹将失败。"
    },
    "none": {
      "en": "",
      "zh": ""
    }
  },
  "position_params": {
    "D": {
      "trend_span": 252,
      "smooth_span": 10,
      "min_bars": 200,
      "vol_floor_frac": 0.25,
      "note": "ETFs, sectors, baskets, daily FRED tapes"
    },
    "W": {
      "trend_span": 52,
      "smooth_span": 2,
      "min_bars": 40,
      "vol_floor_frac": 0.25,
      "note": "weekly resamples"
    },
    "M": {
      "trend_span": 36,
      "smooth_span": 2,
      "min_bars": 24,
      "vol_floor_frac": 0.25,
      "note": "monthly macro tapes: Case-Shiller, DRAM ASP, ISM"
    }
  },
  "turn_detector_defaults": {
    "pct_sector": 14.0,
    "pct_country": 14.0,
    "pct_cn": 18.0,
    "pct_basket_vol_scaled": true,
    "version": 2
  },
  "signal_ttl_bars": 10,
  "zone_hi": 84.0,
  "zone_ehi": 68.0,
  "zone_elo": 32.0,
  "zone_lo": 16.0
};

  /**
   * Tiny lookup helpers — data lookups ONLY.
   * classify_phase / resolve_state / canonical_position run in Python only.
   */

  /**
   * zoneWord(pos, lang) → zone word string for a 0–100 position.
   * @param {number} pos  0–100 canonical position.
   * @param {string} lang 'en' | 'zh'.
   * @returns {string}
   */
  payload.zoneWord = function(pos, lang) {
    var zones = payload.zones;
    var field = (lang === 'zh') ? 'word_zh' : 'word';
    for (var i = 0; i < zones.length; i++) {
      if (pos >= zones[i].lo) return zones[i][field];
    }
    return zones[zones.length - 1][field];
  };

  /**
   * phaseMeta(phase) → {label, short, label_zh, short_zh, hue}.
   * @param {string} phase  One of the 5 phase keys.
   * @returns {Object}
   */
  payload.phaseMeta = function(phase) {
    return payload.phases[phase] || null;
  };

  /**
   * stanceMeta(stance) → {en, zh, tone}.
   * @param {string} stance  One of the 9 stance keys.
   * @returns {Object}
   */
  payload.stanceMeta = function(stance) {
    return payload.stances[stance] || null;
  };

  /**
   * crosswalkLookup(phase, ladder) → {stance, divergence, tone, en, zh, ...}.
   * For the pos-gated Downturn cells, pos must be supplied.
   * @param {string} phase
   * @param {string} ladder
   * @param {number} [pos]  optional position for gated cells
   * @returns {Object|null}
   */
  payload.crosswalkLookup = function(phase, ladder, pos) {
    if (phase === 'Downturn' && (ladder === 'TURN SIGNALED' || ladder === 'FRESH BUY')) {
      var gate = (typeof pos === 'number' && pos >= 55) ? '>=55' : '<55';
      return payload.crosswalk[phase + '|' + ladder + '|pos' + gate] || null;
    }
    return payload.crosswalk[phase + '|' + ladder] || null;
  };

  root.CYCLE_ONTOLOGY = payload;
}(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this)));
