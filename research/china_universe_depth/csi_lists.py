import sys, json, time
sys.path.insert(0, ".")
import akshare as ak
from collectors.china_universe import ChinaUniverseAdapter as A, _code_to_ticker
SP = sys.argv[1]
out = {}
for sym in ("000300", "000852", "932000"):
    for attempt in range(4):
        try:
            pairs, src = A._index_rows(ak, sym)
            if src != "csindex":
                raise RuntimeError(f"fell back to {src} (incomplete)")
            tk = sorted({t for c, _ in pairs if (t := _code_to_ticker(c))})
            out[sym] = tk
            print(f"{sym}: {len(pairs)} rows -> {len(tk)} tickers [csindex]", flush=True)
            break
        except Exception as e:
            print(f"{sym} attempt {attempt}: {type(e).__name__} {str(e)[:80]}", flush=True)
            time.sleep(5)
json.dump(out, open(f"{SP}/csi_lists.json", "w"))
print("DONE", {k: len(v) for k, v in out.items()}, flush=True)
