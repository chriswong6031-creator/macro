#!/usr/bin/env python3
"""Frozen EXK/SIL event replay, research-only. SLV is nullable; no fallback."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

H=(5,10,20,40,60); A=("H0","H1","H2","H3","H4","H1B","H4B")
AUTH={"can_rank":False,"can_gate":False,"can_size":False,"can_originate_signal":False,"can_escalate":False}
ADVERSE={"adverse_plan","adverse_operational","adverse_plus_remediation","adverse_plus_plan","adverse_structural","adverse_macro","adverse_nondiscretionary","adverse_project","resolved_before_disclosure"}
RECOVERABLE={"recoverable","resolved","bounded","price_contingent"}; OPEN={"open","partially_bounded","open_unresolved","open_ended"}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for c in iter(lambda:f.read(1<<20),b""): h.update(c)
    return h.hexdigest()

def col(cols,names):
    n={str(c).lower().replace(" ","_"):c for c in cols}
    return next((n[x] for x in names if x in n),None)

def close(p):
    p=Path(p)
    if not p.exists(): raise FileNotFoundError(p)
    d=pd.read_parquet(p); dc=col(d.columns,("date","datetime","timestamp","time")); raw=d.pop(dc) if dc is not None else d.index
    d.index=pd.to_datetime(raw,errors="coerce",utc=True).tz_convert(None).normalize(); d=d.loc[~d.index.isna()]; d=d[~d.index.duplicated(keep="last")].sort_index()
    cc=col(d.columns,("adj_close","adjusted_close","close_adjusted","close"))
    if cc is None: raise ValueError(f"no close column in {p}: {list(d.columns)}")
    s=pd.to_numeric(d[cc],errors="coerce"); return s.loc[np.isfinite(s)&(s>0)]

def load_events(p):
    x=json.loads(Path(p).read_text()); e=x.get("events") or x.get("event_ledger")
    if not isinstance(e,list): raise ValueError("events[] missing")
    return e

def align(root):
    root=Path(root); paths={s:root/f"data/yahoo/{s}.parquet" for s in ("EXK","SIL","SLV")}
    f=pd.concat({s:close(paths[s]) for s in ("EXK","SIL")},axis=1,join="inner").dropna()
    if f.empty: raise ValueError("no common EXK/SIL sessions")
    slv={"symbol":"SLV","state":"UNAVAILABLE","reason":"canonical_file_absent"}
    if paths["SLV"].exists():
        z=close(paths["SLV"]); f=f.join(z.rename("SLV"),how="left"); slv={"symbol":"SLV","state":"MEASURED","sha256":sha(paths["SLV"]),"first_session":z.index.min().date().isoformat(),"last_session":z.index.max().date().isoformat(),"n_sessions":len(z)}
    else: f["SLV"]=np.nan
    f["EXK_SIL"]=f.EXK/f.SIL
    return f,{"EXK":{"path":str(paths["EXK"]),"sha256":sha(paths["EXK"])},"SIL":{"path":str(paths["SIL"]),"sha256":sha(paths["SIL"])},"SLV":slv}

def adverse(e): return e.get("event_class") in ADVERSE and e.get("study_inclusion")!="exclude"
def recoverable(e): return e.get("recoverability_at_t0") in RECOVERABLE
def open_info(e): return bool(e.get("new_adverse_information_at_t0")) and e.get("adverse_uncertainty_at_t0") in OPEN

def sess(idx,date):
    t=pd.Timestamp(date).normalize()
    if t<idx.min(): return None,"before_store_start"
    if t>idx.max(): return None,"after_store_end"
    p=int(idx.searchsorted(t,"left")); return (p,None) if p<len(idx) else (None,"after_store_end")

def breakout(f,start,n,wait):
    r=f.EXK_SIL; stop=min(len(f),start+wait+1)
    for p in range(max(start,n),stop):
        prior=r.iloc[p-n:p]
        if len(prior)==n and np.isfinite(prior).all() and r.iloc[p]>prior.max():
            return p,{"signal_date":f.index[p].date().isoformat(),"signal_ratio":float(r.iloc[p]),"prior_range_high":float(prior.max()),"prior_range_low":float(prior.min())}
    return None,{"refusal":f"no_{n}d_breakout_within_{wait}_sessions"}

def entry(e,arm,f,ep,wait):
    if arm=="H0": return ep,{"signal_date":f.index[ep].date().isoformat()}
    if arm in ("H1","H1B"):
        if not recoverable(e): return None,{"refusal":"not_recoverable_at_t0"}
        if arm=="H1B" and not open_info(e): return None,{"refusal":"no_open_adverse_information_at_t0"}
        return ep,{"signal_date":f.index[ep].date().isoformat()}
    if arm in ("H4","H4B") and not recoverable(e): return None,{"refusal":"not_recoverable_at_t0"}
    if arm=="H4B" and not open_info(e): return None,{"refusal":"no_open_adverse_information_at_t0"}
    sig,m=breakout(f,ep,10 if arm=="H2" else 20,wait)
    if sig is None: return None,m
    return (sig+1,m) if sig+1<len(f) else (None,{**m,"refusal":"next_close_unavailable"})

def metrics(f,p,m):
    x=float(f.EXK.iloc[p]); s=float(f.SIL.iloc[p]); r=float(f.EXK_SIL.iloc[p]); z=f.SLV.iloc[p]
    o={"entry_date":f.index[p].date().isoformat(),"entry_exk":x,"entry_sil":s,"entry_slv":float(z) if np.isfinite(z) else None,"entry_exk_sil":r}
    for h in H:
        q=p+h; k=f"h{h}"
        if q>=len(f): o[f"{k}_mature"]=False; continue
        w=f.iloc[p:q+1]; path=w.EXK/x-1; rel=w.EXK_SIL/r-1; pos=np.flatnonzero(path.iloc[1:].to_numpy()>0); ze=f.SLV.iloc[q]
        o.update({f"{k}_mature":True,f"{k}_end_date":f.index[q].date().isoformat(),f"{k}_exk_return":float(f.EXK.iloc[q]/x-1),f"{k}_sil_return":float(f.SIL.iloc[q]/s-1),f"{k}_slv_return":float(ze/z-1) if np.isfinite(z) and np.isfinite(ze) else None,f"{k}_exk_sil_return":float(f.EXK_SIL.iloc[q]/r-1),f"{k}_mfe_close":float(path.max()),f"{k}_mae_close":float(path.min()),f"{k}_time_to_positive":int(pos[0]+1) if len(pos) else None,f"{k}_time_underwater":int((path.iloc[1:]<0).sum()),f"{k}_min_relative_return":float(rel.min()),f"{k}_max_relative_return":float(rel.max()),f"{k}_breakout_failed":None if m.get("prior_range_low") is None else bool((w.EXK_SIL.iloc[1:]<m["prior_range_low"]).any())})
    return o

def origins(events):
    out={}
    for e in events:
        if not adverse(e) or not e.get("public_first_tradable_date"): continue
        ep=str(e.get("episode_id") or e["event_id"]); c=(pd.Timestamp(e["public_first_tradable_date"]),e["event_id"])
        if ep not in out or c<out[ep]: out[ep]=c
    return {k:v[1] for k,v in out.items()}

def run(events,f,wait=60):
    rows=[]; first=origins(events)
    for e in events:
        if not adverse(e): continue
        d=e.get("public_first_tradable_date"); ep=str(e.get("episode_id") or e["event_id"]); primary=first.get(ep)==e["event_id"]
        if not d: rows.append({"event_id":e["event_id"],"episode_id":ep,"status":"REFUSED","refusal":"no_public_date","episode_origin_for_n":primary}); continue
        p,why=sess(f.index,d)
        if p is None: rows.append({"event_id":e["event_id"],"episode_id":ep,"status":"REFUSED","refusal":why or "session_unavailable","event_public_date":d,"episode_origin_for_n":primary}); continue
        for arm in A:
            q,m=entry(e,arm,f,p,wait); b={"event_id":e["event_id"],"episode_id":ep,"study_role":e.get("study_role"),"arm":arm,"event_public_date":d,"event_session":f.index[p].date().isoformat(),"design_touched":bool(e.get("design_touched")),"episode_origin_for_n":primary}
            rows.append({**b,**m,"status":"NO_ENTRY"} if q is None else {**b,**m,**metrics(f,q,m),"status":"ENTERED","fill_convention":"first_public_tradable_close" if arm in ("H0","H1","H1B") else "next_common_session_close_after_signal"})
    return rows

def summary(rows):
    o={"n_rows":len(rows),"n_entered":sum(r.get("status")=="ENTERED" for r in rows),"distinct_event_ids":len({r.get("event_id") for r in rows}),"distinct_episode_ids":len({r.get("episode_id") for r in rows}),"refusal_counts":{},"by_arm":{}}
    for r in rows:
        if r.get("status") in ("REFUSED","NO_ENTRY"): o["refusal_counts"][r.get("refusal","unknown")]=o["refusal_counts"].get(r.get("refusal","unknown"),0)+1
    for a in A:
        ent=[r for r in rows if r.get("arm")==a and r.get("status")=="ENTERED"]; pri=[r for r in ent if r.get("episode_origin_for_n")]; con=[r for r in pri if not r.get("design_touched")]
        c={"transition_n_entered":len(ent),"episode_origin_n_entered":len(pri),"confirmatory_episode_n":len(con),"design_touched_episode_n":len(pri)-len(con)}
        for h in H:
            des=[r[f"h{h}_exk_sil_return"] for r in pri if r.get(f"h{h}_mature")]; val=[r[f"h{h}_exk_sil_return"] for r in con if r.get(f"h{h}_mature")]
            c.update({f"h{h}_descriptive_episode_n":len(des),f"h{h}_descriptive_median_relative_return":float(np.median(des)) if des else None,f"h{h}_confirmatory_n":len(val),f"h{h}_confirmatory_median_relative_return":float(np.median(val)) if val else None})
        o["by_arm"][a]=c
    return o

def selftest():
    idx=pd.bdate_range("2020-01-01",periods=180); sil=100*np.exp(np.linspace(0,.05,len(idx))); exk=10*np.exp(np.linspace(0,.05,len(idx))); p=60; exk[p:p+10]*=np.linspace(.8,.75,10); exk[p+10:]*=np.linspace(.78,1.35,len(idx)-(p+10)); f=pd.DataFrame({"EXK":exk,"SIL":sil,"SLV":np.nan},index=idx); f["EXK_SIL"]=f.EXK/f.SIL
    e={"event_id":"SYN","episode_id":"SYN1","public_first_tradable_date":idx[p].date().isoformat(),"event_class":"adverse_operational","study_inclusion":"include","recoverability_at_t0":"recoverable","adverse_uncertainty_at_t0":"open","new_adverse_information_at_t0":True,"design_touched":False}
    x=run([e],f); assert json.dumps(x,sort_keys=True)==json.dumps(run([e],f),sort_keys=True); assert all(r["entry_date"]>r["signal_date"] for r in x if r.get("status")=="ENTERED" and r.get("arm") in ("H2","H3","H4","H4B")); assert all(v["h5_confirmatory_n"]==0 for v in summary(run([{**e,"design_touched":True}],f))["by_arm"].values())
    pulse=run([e,{**e,"event_id":"SYN-PULSE","public_first_tradable_date":idx[p+5].date().isoformat()}],f); assert {r["event_id"] for r in pulse if r.get("episode_origin_for_n")}=={"SYN"}
    pre=run([{**e,"event_id":"PRE","episode_id":"PRE","public_first_tradable_date":"2019-01-01"}],f); post=run([{**e,"event_id":"POST","episode_id":"POST","public_first_tradable_date":"2030-01-01"}],f); assert pre[0]["refusal"]=="before_store_start" and post[0]["refusal"]=="after_store_end"
    print("SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=Path(".")); ap.add_argument("--events",type=Path); ap.add_argument("--out",type=Path); ap.add_argument("--max-wait",type=int,default=60); ap.add_argument("--selftest",action="store_true"); a=ap.parse_args()
    if a.selftest: selftest(); return 0
    if not a.events or not a.out: ap.error("--events and --out required unless --selftest")
    f,inputs=align(a.root.resolve()); rows=run(load_events(a.events),f,a.max_wait); out={"schema":"mastermind.exk_event_replay.v1_2","authority":AUTH,"correction":{"from":"mastermind.exk_event_replay.v1_1","reason":"hard refusal before primary store start and after primary store end","primary_logic_changed":False,"secondary_benchmark":"SLV typed UNAVAILABLE when absent","episode_counting":"all transitions retained; honest N uses first included adverse transition per episode"},"design":{"horizons_sessions":list(H),"max_confirmation_wait_sessions":a.max_wait,"primary_benchmark":"SIL","secondary_benchmark":"SLV_if_canonical_available","H0_H1_H1B_fill":"first_public_tradable_close","H2_H3_H4_H4B_fill":"next_common_session_close_after_signal_close"},"inputs":inputs,"coverage":{"first_common_session":f.index.min().date().isoformat(),"last_common_session":f.index.max().date().isoformat(),"n_common_sessions":len(f)},"summary":summary(rows),"rows":rows}; a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(out,indent=2,sort_keys=True)); print(f"wrote {a.out} ({len(rows)} rows)"); return 0
if __name__=="__main__": raise SystemExit(main())
