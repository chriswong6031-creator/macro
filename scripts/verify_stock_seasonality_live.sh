#!/usr/bin/env bash
# Live verification for the Stock Seasonality tranche.
# Run AFTER #4235 merges (+~3 min for the VPS pull) and again after the first nightly.
# Every check prints PASS/FAIL and what it actually observed — curl status alone is theater.
set -uo pipefail
BASE="https://www.mastermind-x.com"
pass=0; fail=0; warn=0
ok(){ printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1)); }
no(){ printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }
wa(){ printf '  \033[33mWARN\033[0m %s\n' "$1"; warn=$((warn+1)); }

hdr(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

code(){ curl -sS -o /dev/null -w '%{http_code}' --max-time 25 "$1" 2>/dev/null || echo 000; }
body(){ curl -sS --max-time 25 "$1" 2>/dev/null; }

hdr "1 · Public serving boundary (was 401/302 before this tranche)"
for p in /seasonalitydata/methodology.json /seasonalitydata/index.json \
         /seasonalitydata/entities/SPY.json /stock_seasonality.html \
         /stock_seasonality.css /stock_seasonality.js; do
  c=$(code "$BASE$p")
  [ "$c" = "200" ] && ok "$p -> $c" || no "$p -> $c (expected 200)"
done

hdr "2 · index.json shape + the program-level honesty numbers"
IDX=$(body "$BASE/seasonalitydata/index.json")
if [ -z "$IDX" ]; then no "index.json body empty"; else
  python3 - "$IDX" <<'PY' || true
import json,sys
try: d=json.loads(sys.argv[1])
except Exception as e: print(f"  \033[31mFAIL\033[0m index.json not JSON: {e}"); raise SystemExit
def ok(m): print(f"  \033[32mPASS\033[0m {m}")
def no(m): print(f"  \033[31mFAIL\033[0m {m}")
ok(f"schema={d.get('schema')} as_of={d.get('as_of')} n_entities={d.get('n_entities')}") \
    if d.get('schema')=='biopharma_seasonality.index.v1' else no(f"schema={d.get('schema')}")
n=d.get('n_entities') or 0
(ok if n>=100 else no)(f"n_entities={n} (expect ~220)")
pr=d.get('program_rates') or {}
if pr:
    raw=(pr.get('raw') or {}); mn=(pr.get('market_neutral') or {})
    ok(f"program_rates raw={raw.get('n_clearing')}/{raw.get('n_symbols')} "
       f"({100*(raw.get('share') or 0):.1f}%) neutral={mn.get('n_clearing')}/{mn.get('n_symbols')} "
       f"({100*(mn.get('share') or 0):.1f}%) vs chance {100*(pr.get('chance_expectation_share') or 0):.0f}%")
else: no("program_rates missing — the honesty strip has nothing to print")
ents=d.get('entities') or []
named=[e for e in ents if e.get('name') and e['name']!=e['symbol']]
share=100*len(named)/max(len(ents),1)
(ok if share>=80 else no)(f"labels resolved: {len(named)}/{len(ents)} ({share:.0f}%) have a real name (floor 80%)")
sect=[e for e in ents if e.get('sector')]
(ok if len(sect)>=0.7*len(ents) else no)(f"sector present on {len(sect)}/{len(ents)}")
PY
fi

hdr "3 · The committed default entity (SSR first paint + SEO)"
SPY=$(body "$BASE/seasonalitydata/entities/SPY.json")
if [ -z "$SPY" ]; then no "SPY.json empty"; else
  python3 - "$SPY" <<'PY' || true
import json,sys
d=json.loads(sys.argv[1])
def ok(m): print(f"  \033[32mPASS\033[0m {m}")
def no(m): print(f"  \033[31mFAIL\033[0m {m}")
cal=d.get('calendar') or {}; fam=d.get('family') or {}; dw=d.get('default_window') or {}
(ok if cal.get('n_slots')==365 else no)(f"calendar.n_slots={cal.get('n_slots')} (expect 365)")
(ok if cal.get('cum_encoding') else no)(f"cum_encoding={cal.get('cum_encoding')} scale={cal.get('cum_scale')}")
(ok if fam.get('n_candidates')==2645 else no)(f"family.n_candidates={fam.get('n_candidates')} (expect 2645)")
nul=(fam.get('null') or {})
(ok if nul.get('method')=='independent_circular_year_shift' else no)(f"null.method={nul.get('method')}")
(ok if nul.get('B') else no)(f"null B={nul.get('B')} q95={(nul.get('max_abs_t_quantiles') or {}).get('0.95')}")
(ok if dw.get('state') in ('own','market','fails','thin') else no)(
    f"default_window state={dw.get('state')} |t|={dw.get('abs_t')} exceed={dw.get('null_max_exceedance_pct')}% "
    f"stability.survives={(dw.get('stability') or {}).get('survives')}")
yrs=d.get('years') or []
first=(yrs[0].get('cum') or []) if yrs else []
(ok if yrs and len(first)==365 else no)(f"years={len(yrs)} first cum len={len(first)}")
(ok if first and all(isinstance(v,int) for v in first[:20]) else no)("cum values are integers (1e-5 units)")
PY
fi

hdr "4 · R2 plane — THE HIGHEST RISK (non-default symbols come from DATA_BASE, not the VPS)"
DB=$(body "$BASE/data_base.js" | grep -oE 'https?://[^"'"'"']+' | head -1)
if [ -z "$DB" ]; then wa "could not read DATA_BASE from /data_base.js — check the page's fetch base by hand"; else
  echo "  DATA_BASE=$DB"
  for s in XBI IBB XLV MU; do
    u="${DB%/}/seasonalitydata/entities/$s.json"
    c=$(code "$u")
    if [ "$c" = "200" ]; then ok "R2 $s.json -> 200"
    else no "R2 $s.json -> $c  ($u)"; fi
  done
fi

hdr "5 · methodology.json is no longer frozen"
M=$(body "$BASE/seasonalitydata/methodology.json")
echo "$M" | python3 -c "
import json,sys
d=json.load(sys.stdin); a=d.get('availability',{})
print(f\"  as_of={d.get('as_of')} status={d.get('status')}\")
print(f\"  live_forecasts={a.get('live_forecasts')} live_screener={a.get('live_screener')} live_event_graph={a.get('live_event_graph')}\")
auth=d.get('authority',{})
bad=[k for k,v in auth.items() if k.startswith('may_') and k not in ('may_explain','may_flag_attention') and v]
print('  \033[31mFAIL\033[0m authority booleans leaked: '+str(bad) if bad else '  \033[32mPASS\033[0m authority ceiling intact (context-only)')
" 2>/dev/null || no "methodology.json unreadable"

hdr "Summary"
printf '  %d passed, %d failed, %d warnings\n' "$pass" "$fail" "$warn"
[ "$fail" -eq 0 ] || echo "  -> a FAIL here means the tranche is live but wrong; do not report it as shipped."
