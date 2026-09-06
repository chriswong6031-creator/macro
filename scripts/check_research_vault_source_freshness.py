"""Research Vault source-content freshness guard (stdlib only, no state)."""
from __future__ import annotations
import argparse, json, math, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

# Unconditional: an already-present root further down sys.path still loses to a
# foreign package ahead of it, so this must pin position 0 every time (see
# scripts/__init__.py).
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.research_vault.catalog import source_clock_summary  # noqa: E402

SCHEMA="research_vault.source_freshness.v1"
CLOCK_SCHEMA="research_vault.source_clock.v1"
# No limit/offset — app/research.research_catalog ignores them; preview size is
# chosen by tier via _catalog_preview. The whole-catalog source_clock lives on
# summary regardless of the truncated items list.
DEFAULT_URL="https://www.mastermind-x.com/api/research/catalog"
DEFAULT_TIMEOUT_SECONDS=20.0
DEFAULT_FUTURE_TOLERANCE_MINUTES=5.0
MAX_RESPONSE_BYTES=8*1024*1024
ALLOWED_URL_SCHEMES=frozenset({"http", "https"})

def _iso(v): return v.astimezone(timezone.utc).isoformat() if v is not None else None

def _parse_time(v):
    if not isinstance(v,str) or not v.strip(): return None
    try:
        x=datetime.fromisoformat(v.strip().replace("Z","+00:00"))
        return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError,ValueError,OverflowError): return None

def _coerce_now(v):
    x=v or datetime.now(timezone.utc)
    if x.tzinfo is None: x=x.replace(tzinfo=timezone.utc)
    return x.astimezone(timezone.utc)

def _finite_number(v,*,positive):
    if isinstance(v,bool) or not isinstance(v,(int,float)): raise ValueError("finite number required")
    x=float(v)
    if not math.isfinite(x) or (x<=0 if positive else x<0): raise ValueError("number outside accepted range")
    return x

def source_deadline(published_at,override=None):
    """Fixed deadline: 48 UTC weekday hours; weekends excluded, holidays not modeled."""
    cur=_coerce_now(published_at)
    if override is not None: return cur+timedelta(hours=_finite_number(override,positive=True))
    left=timedelta(hours=48)
    while left:
        if cur.weekday()>=5:
            cur=(cur+timedelta(days=7-cur.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        midnight=(cur+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
        span=midnight-cur
        if left<=span: return cur+left
        left-=span; cur=midnight
    return cur

def source_limit_hours(published_at,override=None):
    x=_coerce_now(published_at); return (source_deadline(x,override)-x).total_seconds()/3600

def _report(status,*,ok,now,source,reason,generated_at=None,latest_report_at=None,
            source_deadline_at=None,age_hours=None,limit_hours=None,count=None,
            observed_items=None,invalid_published_at=0,served_stale=False):
    return {"schema":SCHEMA,"status":status,"ok":ok,"reason":reason,"source":source,
            "now":_iso(now),"generated_at":_iso(generated_at),"latest_report_at":_iso(latest_report_at),
            "source_deadline_at":_iso(source_deadline_at),
            "age_hours":round(age_hours,3) if age_hours is not None else None,
            "limit_hours":float(limit_hours) if limit_hours is not None else None,
            "count":count,"observed_items":observed_items,"invalid_published_at":invalid_published_at,
            "served_stale":bool(served_stale)}

def evaluate(payload:Mapping[str,Any],*,now=None,source="catalog",max_age_hours=None,
             future_tolerance_minutes=DEFAULT_FUTURE_TOLERANCE_MINUTES):
    try: current=_coerce_now(now)
    except (TypeError,ValueError,OverflowError,AttributeError):
        return _report("CATALOG_UNAVAILABLE",ok=False,now=datetime.now(timezone.utc),source=source,reason="invalid evaluation clock")
    common={"now":current,"source":source}
    def refuse(status,reason): return _report(status,ok=False,reason=reason,**common)
    try:
        if max_age_hours is not None: _finite_number(max_age_hours,positive=True)
        tolerance=timedelta(minutes=_finite_number(future_tolerance_minutes,positive=False))
        if not isinstance(payload,Mapping): return refuse("CATALOG_UNAVAILABLE","catalog root is not an object")
        rows=payload.get("items")
        if not isinstance(rows,list): return refuse("CATALOG_UNAVAILABLE","catalog items is missing or not a list")
        common["observed_items"]=len(rows)
        count=payload.get("count",len(rows))
        if type(count) is not int or count<0: return refuse("CATALOG_UNAVAILABLE","catalog count is not a nonnegative integer")
        common["count"]=count
        generated=_parse_time(payload.get("generated_at")); health=payload.get("catalog_health")
        if generated is None and isinstance(health,Mapping): generated=_parse_time(health.get("generated_at"))
        common["generated_at"]=generated
        served_stale=payload.get("stale") is True
        common["served_stale"]=served_stale
        preview=payload.get("preview",False)
        if type(preview) is not bool: return refuse("CATALOG_UNAVAILABLE","catalog preview flag is invalid")
        if preview:
            summary=payload.get("summary"); clock=summary.get("source_clock") if isinstance(summary,Mapping) else None
        else:
            if count!=len(rows): return refuse("CATALOG_UNAVAILABLE","whole-catalog completeness cannot be established")
            clock=source_clock_summary(dict(payload))
        if not isinstance(clock,Mapping): return refuse("CATALOG_UNAVAILABLE","whole-catalog source-clock aggregate is missing")
        if clock.get("schema")!=CLOCK_SCHEMA or clock.get("complete") is not True:
            return refuse("CATALOG_UNAVAILABLE","whole-catalog source-clock aggregate is incomplete or unsupported")
        counts=[clock.get(k) for k in ("report_count","valid_clock_count","invalid_clock_count")]
        if any(type(v) is not int or v<0 for v in counts): return refuse("CATALOG_UNAVAILABLE","source-clock aggregate counts are invalid")
        total,valid,invalid=counts
        if total!=count or valid+invalid!=total or len(rows)>total:
            return refuse("CATALOG_UNAVAILABLE","source-clock aggregate counts are inconsistent")
        common["invalid_published_at"]=invalid
        raw=clock.get("latest_report_published_at"); latest=_parse_time(raw)
        if (valid>0 and latest is None) or (valid==0 and raw is not None):
            return refuse("CATALOG_UNAVAILABLE","source-clock aggregate latest timestamp is inconsistent")
        if count==0: return refuse("NO_REPORTS","catalog contains no report rows")
        common["latest_report_at"]=latest
        # One dirty published_at must not replace PRODUCER_STALE: when any valid
        # clock exists, grade the newest valid stamp and keep invalid_published_at
        # as a side signal (emitted as a warning annotation).
        if latest is None:
            return refuse("LATEST_REPORT_INVALID","one or more admitted reports have an unusable published_at clock")
        age=(current-latest).total_seconds()/3600; common["age_hours"]=age
        if latest-current>tolerance: return refuse("FUTURE_REPORT_CLOCK","newest report exceeds the accepted future-clock tolerance")
        deadline=source_deadline(latest,max_age_hours); limit=(deadline-latest).total_seconds()/3600
        common.update(source_deadline_at=deadline,limit_hours=limit,age_hours=max(0.0,age))
        if current>deadline:
            return refuse("PRODUCER_STALE",f"newest admitted report is {age:.1f}h old (source-anchored limit {limit:.1f}h)")
        return _report("SOURCE_FRESH",ok=True,reason="newest admitted report is inside its fixed source-content deadline",**common)
    except (TypeError,ValueError,OverflowError,RecursionError):
        return refuse("CATALOG_UNAVAILABLE","source-clock input or configuration is invalid or outside supported bounds")

def _reject_json_constant(v): raise ValueError(f"non-finite JSON constant: {v}")
def _decode(raw,label):
    x=json.loads(raw,parse_constant=_reject_json_constant)
    if not isinstance(x,dict): raise ValueError(f"{label} root must be an object")
    return x

def _load_local(path):
    with path.open("rb") as f: raw=f.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES: raise ValueError("catalog exceeds bounded read limit")
    return _decode(raw,"catalog")

def _load_url(url,timeout_seconds):
    timeout=_finite_number(timeout_seconds,positive=True)
    if not isinstance(url,str) or not url.strip():
        raise ValueError("URL must be a non-empty http(s) string")
    scheme=(urlparse(url.strip()).scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme must be http or https, got {scheme!r}")
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"MastermindX-research-source-health/1"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        try: announced=int(r.headers.get("Content-Length")) if r.headers.get("Content-Length") else None
        except (TypeError,ValueError): announced=None
        if announced is not None and announced>MAX_RESPONSE_BYTES: raise ValueError("catalog response exceeds bounded read limit")
        raw=r.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES: raise ValueError("catalog response exceeds bounded read limit")
    return _decode(raw,"catalog response")

def _annotation_text(v): return str(v).replace("%","%25").replace("\r","%0D").replace("\n","%0A")
def _emit(report):
    print(json.dumps(dict(report),sort_keys=True,allow_nan=False))
    invalid=report.get("invalid_published_at") or 0
    if type(invalid) is int and invalid>0:
        print("::warning title=research-vault-source::"+_annotation_text(
            f"{invalid} admitted report(s) have an unusable published_at; graded newest valid clock"))
    if report.get("ok") is not True:
        print("::error title=research-vault-source::"+_annotation_text(f"{report.get('status')}: {report.get('reason')}"))

def _selftest():
    """Run 44 hermetic contract checks."""
    import contextlib, copy, io, tempfile
    from unittest.mock import patch
    from engine.research_vault import catalog as catalog_mod
    now=datetime(2026,9,5,4,tzinfo=timezone.utc); failures=[]; passed=0
    def req(x,d="failed"):
        if not x: raise AssertionError(d)
    def check(name,fn):
        nonlocal passed
        try: fn(); passed+=1
        except Exception as e: failures.append(f"{name}: {type(e).__name__}: {e}")
    def cat(stamp="2026-09-04T18:00:00Z",count=1):
        n=count if type(count) is int and count>=0 else 1
        return {"schema":"research_vault.catalog.v1","generated_at":now.isoformat(),"count":count,
                "items":[{"id":f"report-{i}","published_at":stamp} for i in range(n)]}
    def expect(payload,wanted,at=now,**kw):
        r=evaluate(payload,now=at,**kw); req(r["status"]==wanted,r); json.dumps(r,allow_nan=False)
    basic=[
      (cat("2026-08-25T16:47:24Z",1843),"PRODUCER_STALE",now,{}),(cat(),"SOURCE_FRESH",now,{}),
      (cat("2026-09-04T17:00:00Z"),"SOURCE_FRESH",datetime(2026,9,7,12,tzinfo=timezone.utc),{}),
      (cat("2026-09-04T17:00:00Z"),"PRODUCER_STALE",datetime(2026,9,9,12,tzinfo=timezone.utc),{}),
      (cat(count=0),"NO_REPORTS",now,{}),(cat("bad"),"LATEST_REPORT_INVALID",now,{}),
      (cat("2026-09-05T04:10:01Z"),"FUTURE_REPORT_CLOCK",now,{}),({"items":"bad"},"CATALOG_UNAVAILABLE",now,{}),
      (dict(cat(),stale=True),"SOURCE_FRESH",now,{}),
      (dict(cat("2026-08-25T16:47:24Z",1843),stale=True),"PRODUCER_STALE",now,{}),
      (cat("2026-09-04T00:00:00Z"),"PRODUCER_STALE",now,{"max_age_hours":24})]
    for i,(p,w,t,k) in enumerate(basic): check(f"basic-{i}",lambda p=p,w=w,t=t,k=k: expect(p,w,t,**k))
    for v in (float("nan"),float("inf"),-float("inf"),0,-1): check(f"age-{v}",lambda v=v: expect(cat(),"CATALOG_UNAVAILABLE",max_age_hours=v))
    for v in (float("nan"),float("inf"),-1): check(f"tol-{v}",lambda v=v: expect(cat(),"CATALOG_UNAVAILABLE",future_tolerance_minutes=v))
    for v in (float("inf"),float("nan"),True,1.5,"1",-1): check(f"count-{v!r}",lambda v=v: expect(dict(cat(),count=v),"CATALOG_UNAVAILABLE"))
    for v in ("0001-01-01T00:00:00+01:00","9999-12-31T23:59:59-01:00","bad",None): check(f"stamp-{v}",lambda v=v: expect(cat(v),"LATEST_REPORT_INVALID"))
    extras=[lambda:(lambda r: (req(r["status"]=="SOURCE_FRESH",r), req(r["invalid_published_at"]==1,r)))(
                evaluate(dict(cat(),count=2,items=cat()["items"]+[{"id":"bad","published_at":"bad"}]),now=now)),
            lambda:expect(dict(cat(),count=100),"CATALOG_UNAVAILABLE"),lambda:expect(dict(cat(),preview=True),"CATALOG_UNAVAILABLE"),
            lambda:expect(dict(cat(),preview="yes"),"CATALOG_UNAVAILABLE"),lambda:req(evaluate(cat(),now="bad")["status"]=="CATALOG_UNAVAILABLE")]
    for i,fn in enumerate(extras): check(f"extra-{i}",fn)
    def partial_stale():
        p=dict(cat("2026-08-25T16:47:24Z"),count=2,
               items=[{"id":"old","published_at":"2026-08-25T16:47:24Z"},{"id":"bad","published_at":"nope"}])
        r=evaluate(p,now=now); req(r["status"]=="PRODUCER_STALE" and r["invalid_published_at"]==1,r)
    check("partial-stale",partial_stale)
    def schemes():
        for bad in ("file:///etc/passwd","ftp://example.com/x","data:application/json,{}","","   "):
            try: _load_url(bad,1.0)
            except ValueError: continue
            raise AssertionError(bad)
    check("schemes",schemes)
    def aggregate():
        p=cat(); p["items"][0].update(title="PRIVATE",pdf_key="PRIVATE"); before=copy.deepcopy(p); c=catalog_mod.public_summary(p,now=now)["source_clock"]
        req(set(c)=={"schema","complete","report_count","valid_clock_count","invalid_clock_count","latest_report_published_at"},c); req("PRIVATE" not in json.dumps(c) and p==before,c)
    check("aggregate",aggregate)
    def parity():
        p=cat(); p["items"] += [{"id":str(i),"published_at":"2026-08-25T12:00:00Z","summary_points":["ready"]} for i in range(3)]; p["count"]=4
        s=catalog_mod.public_summary(p,now=now); q=dict(p,items=p["items"][1:],summary=s,preview=True); a,b=evaluate(p,now=now),evaluate(q,now=now)
        req(all(a.get(k)==b.get(k) for k in ("status","latest_report_at","source_deadline_at","count","invalid_published_at")),(a,b))
    check("parity",parity)
    def badagg():
        p=cat(); c=catalog_mod.public_summary(p,now=now)["source_clock"]
        for u in ({"complete":False},{"report_count":True},{"valid_clock_count":2},{"invalid_clock_count":-1},{"schema":"bad"},{"latest_report_published_at":None}): expect(dict(p,preview=True,summary={"source_clock":dict(c,**u)}),"CATALOG_UNAVAILABLE")
    check("badagg",badagg)
    def annotation():
        o=io.StringIO()
        with contextlib.redirect_stdout(o): _emit({"ok":False,"status":"BAD","reason":"x%\r\n::error::forged","invalid_published_at":2})
        text=o.getvalue(); lines=[x for x in text.splitlines() if x.startswith("::error")]; warn=[x for x in text.splitlines() if x.startswith("::warning")]
        req(len(lines)==1 and all(x in lines[0] for x in ("%25","%0D","%0A")),lines)
        req(len(warn)==1 and "2 admitted" in warn[0],warn)
    check("annotation",annotation)
    def bounded():
        class R:
            def __enter__(s): return s
            def __exit__(s,*_): return False
            def read(s,n=-1): req(n==MAX_RESPONSE_BYTES+1,n); return b"x"*n
        class P:
            def read_bytes(s): raise AssertionError("unbounded")
            def open(s,m): req(m=="rb",m); return R()
        try: _load_local(P())
        except ValueError: return
        raise AssertionError("oversized accepted")
    check("bounded",bounded)
    def timeout():
        for v in (float("nan"),float("inf"),0,-1):
            with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
                try: _load_url(DEFAULT_URL,v)
                except ValueError: continue
                raise AssertionError(v)
    check("timeout",timeout)
    def badjson():
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x"; p.write_text('{"count": NaN, "items": []}')
            try: _load_local(p)
            except ValueError: return
            raise AssertionError("NaN accepted")
    check("json",badjson)
    def monotonic():
        for weekday in range(7):
            start=datetime(2026,8,31,12,tzinfo=timezone.utc)+timedelta(days=weekday); stale=False
            for step in range(337):
                r=evaluate(cat(start.isoformat()),now=start+timedelta(minutes=30*step)); req(not(stale and r["ok"]),(start,step,r)); stale=stale or r["status"]=="PRODUCER_STALE"
            req(stale,start)
    check("monotonic",monotonic)
    if passed!=44: failures.append(f"accounting {passed}/44")
    if failures:
        for f in failures: print(f"SELFTEST FAILURE: {f}",file=sys.stderr)
        return 1
    print("research-vault source-freshness selftest: 44 passed"); return 0

def build_parser():
    p=argparse.ArgumentParser(description="Grade source-content freshness separately from publication freshness.")
    g=p.add_mutually_exclusive_group(); g.add_argument("--catalog",type=Path); g.add_argument("--url")
    p.add_argument("--now"); p.add_argument("--max-age-hours",type=float)
    p.add_argument("--future-tolerance-minutes",type=float,default=DEFAULT_FUTURE_TOLERANCE_MINUTES)
    p.add_argument("--timeout-seconds",type=float,default=DEFAULT_TIMEOUT_SECONDS); p.add_argument("--selftest",action="store_true")
    return p

def main(argv:Sequence[str]|None=None):
    a=build_parser().parse_args(argv)
    if a.selftest: return _selftest()
    current=datetime.now(timezone.utc)
    if a.now is not None:
        parsed=_parse_time(a.now)
        if parsed is None:
            _emit(_report("CATALOG_UNAVAILABLE",ok=False,now=current,source="arguments",reason=f"invalid --now value: {a.now!r}")); return 1
        current=parsed
    source=str(a.catalog) if a.catalog is not None else (a.url or DEFAULT_URL)
    try:
        payload=_load_local(a.catalog) if a.catalog is not None else _load_url(source,a.timeout_seconds)
        report=evaluate(payload,now=current,source=source,max_age_hours=a.max_age_hours,future_tolerance_minutes=a.future_tolerance_minutes)
    except (OSError,ValueError,TypeError,json.JSONDecodeError,urllib.error.URLError,OverflowError,RecursionError) as e:
        report=_report("CATALOG_UNAVAILABLE",ok=False,now=current,source=source,reason=f"catalog read failed ({type(e).__name__})")
    _emit(report); return 0 if report.get("ok") is True else 1

if __name__=="__main__": raise SystemExit(main())
