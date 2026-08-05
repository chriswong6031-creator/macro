import sys, pandas as pd
sys.path.insert(0, ".")
from engine.china_reversal import reversal_watch
closes = pd.read_parquet("data/china_search/closes.parquet")
m = pd.read_parquet("data/china_search/members.parquet")
live=[t for t in m.index if t in closes.columns]; closes=closes[live]
sector=m["sector"].to_dict(); name=m["name"].to_dict(); zh=m["name_zh"].to_dict(); mc=m["mktcap_yi"].to_dict()
real=m[m["mktcap_yi"]>30.0].sort_values("mktcap_yi",ascending=False)
def run(cols): return reversal_watch(closes[cols],sector,name,tkr_name_zh=zh,tkr_mktcap=mc,top_n=16)
panels={}
for n in (300,400,600,800):
    cols=[t for t in real.index[:n] if t in closes.columns]; panels[len(cols)]=run(cols)
panels[len(closes.columns)]=run(list(closes.columns))
keys=sorted(panels)
base=panels[keys[0]]
print(f"{'panel_n':>8} {'screened_n':>10} {'med rev_z shift vs prev':>24} {'quintile Jaccard vs prev':>25} {'top16 overlap vs prev':>22}")
prev=None
for k in keys:
    p=panels[k]
    if prev is None:
        print(f"{k:>8} {p['n']:>10} {'—':>24} {'—':>25} {'—':>22}")
    else:
        c=sorted(set(prev['reversal_all'])&set(p['reversal_all']))
        dz=pd.Series({t:p['reversal_all'][t]['rev_z']-prev['reversal_all'][t]['rev_z'] for t in c})
        qa={t for t in c if prev['reversal_all'][t]['deepest_quintile']}
        qb={t for t in c if p['reversal_all'][t]['deepest_quintile']}
        j=len(qa&qb)/max(1,len(qa|qb))
        ov=len(set(w['ticker'] for w in prev['watch'])&set(w['ticker'] for w in p['watch']))
        print(f"{k:>8} {p['n']:>10} {dz.median():>+24.3f} {j:>25.3f} {str(ov)+'/16':>22}")
    prev=p
