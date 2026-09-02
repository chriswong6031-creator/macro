import functools,http.server,socketserver,threading,json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
SITE=Path(__file__).resolve().parents[3]/"site"
A="3f6de652.css"
SUBS={".pv-zn{display:flex;align-items:center;gap:5px;":".pv-zn{display:flex;flex-wrap:wrap;align-items:center;gap:2px 5px;",
".pv-znm{color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis}":".pv-znm{color:var(--muted);flex:none;max-width:100%;overflow:hidden;text-overflow:ellipsis}",
".pv-added{margin-left:auto;color:var(--muted);flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;font-size:9.5px;padding-left:5px}":".pv-added{margin-left:auto;color:var(--muted);flex:0 0 auto;font-size:9.5px;line-height:1.3}",
".pv-added{max-width:32%}":""}
css=(SITE/"assets/css"/A).read_text()
for a,b in SUBS.items():
    assert css.count(a)==1; css=css.replace(a,b)
P=r"""
()=>{
 const px=(c)=>{ if(c.startsWith('color(')){const m=c.match(/[-\d.]+/g).map(Number);return [m[0],m[1],m[2]];}
   const m=c.match(/[\d.]+/g).map(Number); return [m[0]/255,m[1]/255,m[2]/255]; };
 const lum=(c)=>{const [r,g,b]=px(c);const f=v=>v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);
   return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);};
 const ratio=(a,b)=>{const [x,y]=[lum(a),lum(b)].sort((p,q)=>q-p);return (x+0.05)/(y+0.05);};
 const hex=(c)=>{const [r,g,b]=px(c);const h=v=>Math.round(v*255).toString(16).padStart(2,'0');return '#'+h(r)+h(g)+h(b);};
 const out=[];
 for(const card of document.querySelectorAll('a.pvcard')){
  if(card.offsetParent===null) continue;
  const zn=card.querySelector('.pv-zn'); if(!zn) continue;
  const add=card.querySelector('.pv-added'); if(!add) continue;
  const val=zn.querySelector('.pv-znr')||zn.querySelector('.pv-znm');
  const cz=getComputedStyle(zn), cc=getComputedStyle(card), ca=getComputedStyle(add), cv=getComputedStyle(val);
  const bg=document.body, cb=getComputedStyle(document.documentElement).backgroundColor;
  out.push({tk:card.querySelector('.pv-tk').textContent,
    canvas:hex(cb), lumCanvas:+lum(cb).toFixed(4),
    card:hex(cc.backgroundColor), lumCard:+lum(cc.backgroundColor).toFixed(4),
    shelf:hex(cz.backgroundColor), lumShelf:+lum(cz.backgroundColor).toFixed(4),
    step:+(lum(cz.backgroundColor)-lum(cc.backgroundColor)).toFixed(4),
    chipInk:hex(ca.color), chipPx:ca.fontSize, chipW:ca.fontWeight,
    chipRatio:+ratio(ca.color,cz.backgroundColor).toFixed(2),
    valInk:hex(cv.color), valW:cv.fontWeight, valCls:val.className,
    valRatio:+ratio(cv.color,cz.backgroundColor).toFixed(2),
    subord:+(ratio(cv.color,cz.backgroundColor)/ratio(ca.color,cz.backgroundColor)).toFixed(2),
    shelfH:+zn.getBoundingClientRect().height.toFixed(1)});
  if(out.length>=3) break; }
 return out;}
"""
h=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(SITE))
class Q(socketserver.TCPServer):
    allow_reuse_address=True
    def handle_error(self,*a): pass
s=Q(("127.0.0.1",0),h); threading.Thread(target=s.serve_forever,daemon=True).start(); port=s.server_address[1]
res={}
with sync_playwright() as p:
    br=p.chromium.launch()
    for board,swap in (("us_stocks",True),("canada_stocks",False)):
        for th in ("dark","light"):
            for vw in (1440,390):
                ctx=br.new_context(viewport={"width":vw,"height":1000})
                ctx.add_init_script("try{localStorage.setItem('theme','%s');localStorage.setItem('lang','en')}catch(e){}"%th)
                pg=ctx.new_page()
                if swap: pg.route("**/"+A+"*",lambda r: r.fulfill(status=200,content_type="text/css",body=css))
                pg.goto(f"http://127.0.0.1:{port}/{board}.html",wait_until="networkidle"); pg.wait_for_timeout(1600)
                res[f"{board}_{th}_{vw}"]=pg.evaluate(P); ctx.close()
    br.close()
s.shutdown()
for k,v in res.items():
    print("==",k)
    for r in v: print("  ",json.dumps(r))
