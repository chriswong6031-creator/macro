"use strict";
(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[1736],{
11736:(e,t,l)=>{
l.r(t),l.d(t,{
default:()=>_}
);
var n=l(95155),r=l(12115),a=l(49998),s=l(36809),i=l(86816);
class o{
update(e){
this._data=e}
destroy(){
this._offscreen&&(this._offscreen.width=0,this._offscreen.height=0,this._offscreen=null),this._data=null}
draw(e,t){
let l=this._data;
l&&l.visibleRange&&e.useMediaCoordinateSpace(e=>{
let{
context:n,mediaSize:r}
=e,{
bars:a,barSpacing:s,visibleRange:i,options:o}
=l,{
from:c,to:u}
=i,h=u-c;
if(h<=0)return;
let d=1/0,m=-1/0,f=new Set;
for(let e=c;
e<u;
e++){
let t=a[e];
if(null==t?void 0:t.originalData.cells)for(let e of t.originalData.cells)f.add(e.low),f.add(e.high),e.low<d&&(d=e.low),e.high>m&&(m=e.high)}
if(d>=m)return;
let p=[...f].sort((e,t)=>e-t),g=Math.max(1,p.length-1);
try{
this._offscreen&&this._offscreen.width===h&&this._offscreen.height===g||(this._offscreen="undefined"!=typeof OffscreenCanvas?new OffscreenCanvas(h,g):document.createElement("canvas"),this._offscreen.width=h,this._offscreen.height=g)}
catch(e){
this._offscreen=document.createElement("canvas"),this._offscreen.width=h,this._offscreen.height=g}
let x=this._offscreen.getContext("2d",{
willReadFrequently:!0}
);
if(!x)return;
let v=new Map;
for(let e=0;
e<p.length;
e++)v.set(p[e],e);
let b=x.createImageData(h,g),_=b.data;
for(let e=c;
e<u;
e++){
let t=a[e];
if(!(null==t?void 0:t.originalData.cells))continue;
let l=e-c;
for(let e of t.originalData.cells){
let t=v.get(e.low);
if(void 0===t||t>=g)continue;
let n=g-1-t,[r,a,s,i]=function(e){
let t=e.match(/rgba?\((\d+),\s*(\d+),\s*(\d+),?\s*([\d.]*)\)/);
return t?[+t[1],+t[2],+t[3],Math.round((t[4]?+t[4]:1)*255)]:[0,0,0,0]}
(o.cellShader(e.amount)),c=(n*h+l)*4;
_[c]=r,_[c+1]=a,_[c+2]=s,_[c+3]=i}
}
x.putImageData(b,0,0);
let w=a[c],S=a[u-1];
if(!w||!S)return;
let y=s/2,M=w.x-y,N=S.x+y,j=t(m),C=t(d);
if(null===j||null===C)return;
let k=Math.min(j,C),D=Math.abs(C-j);
n.imageSmoothingEnabled=!0,n.imageSmoothingQuality="high",n.drawImage(this._offscreen,0,0,h,g,M,k,N-M,D)}
)}
constructor(){
this._data=null,this._offscreen=null}
}
class c{
renderer(){
return this._renderer}
update(e,t){
this._renderer.update({
bars:e.bars,barSpacing:e.barSpacing*e.conflationFactor,visibleRange:e.visibleRange,options:t}
)}
priceValueBuilder(e){
if(!e.cells||0===e.cells.length)return[0,0,0];
let t=1/0,l=-1/0;
for(let n of e.cells)n.low<t&&(t=n.low),n.high>l&&(l=n.high);
return[t,l,(t+l)/2]}
isWhitespace(e){
return!e.cells||0===e.cells.length}
defaultOptions(){
return{
...a.c8,cellShader:()=>"rgba(0,0,0,0)",cellBorderWidth:0,cellBorderColor:"transparent"}
}
destroy(){
this._renderer.destroy()}
constructor(){
this._renderer=new o}
}
function u(e,t){
return"".concat(e.toFixed(2),":").concat(t.toFixed(2))}
class h{
draw(e){
var t;
if(!this._params||0===this._segments.length)return;
let{
chart:l,series:n}
=this._params,r=l.timeScale(),a=null!=(t=this._priceSeries)?t:n,s=function(e){
if(0===e.length)return[];
let t=new Map,l=(e,l)=>{
let n=t.get(e);
n||(n=[],t.set(e,n)),n.push(l)}
,n=e.map(e=>({
seg:e,used:!1}
));
for(let e of n)l(u(e.seg.time1,e.seg.price1),e),l(u(e.seg.time2,e.seg.price2),e);
let r=[];
for(let e of n){
if(e.used)continue;
e.used=!0;
let l=[{
t:e.seg.time1,p:e.seg.price1}
,{
t:e.seg.time2,p:e.seg.price2}
];
for(let e of[1,-1]){
let n=1===e?l[l.length-1]:l[0],r=!0;
for(;
r;
){
r=!1;
let a=u(n.t,n.p),s=t.get(a);
if(!s)break;
for(let t of s){
if(t.used)continue;
t.used=!0,r=!0;
let s=u(t.seg.time1,t.seg.price1)===a?{
t:t.seg.time2,p:t.seg.price2}
:{
t:t.seg.time1,p:t.seg.price1}
;
1===e?l.push(s):l.unshift(s),n=s;
break}
}
}
l.length>=2&&r.push(l)}
return r}
(this._segments);
e.useMediaCoordinateSpace(e=>{
let{
context:t}
=e;
for(let e of(t.strokeStyle=this._color,t.lineWidth=this._lineWidth,t.lineJoin="round",t.lineCap="round",t.setLineDash([]),s)){
let l=[];
for(let t of e){
let e=r.timeToCoordinate(t.t),n=a.priceToCoordinate(t.p);
null!==e&&null!==n&&l.push({
x:e,y:n}
)}
if(!(l.length<2)){
if(2===l.length){
t.beginPath(),t.moveTo(l[0].x,l[0].y),t.lineTo(l[1].x,l[1].y),t.stroke();
continue}
t.beginPath(),t.moveTo(l[0].x,l[0].y);
for(let e=0;
e<l.length-1;
e++){
let n=l[Math.max(0,e-1)],r=l[e],a=l[e+1],s=l[Math.min(l.length-1,e+2)],i=r.x+(a.x-n.x)/6,o=r.y+(a.y-n.y)/6,c=a.x-(s.x-r.x)/6,u=a.y-(s.y-r.y)/6;
t.bezierCurveTo(i,o,c,u,a.x,a.y)}
t.stroke()}
}
}
)}
constructor(e,t,l,n,r=null){
this._segments=e,this._params=t,this._color=l,this._lineWidth=n,this._priceSeries=r}
}
class d{
zOrder(){
return"normal"}
renderer(){
return 0===this._segments.length?null:new h(this._segments,this._params,this._color,this._lineWidth,this._priceSeries)}
constructor(e,t,l,n,r=null){
this._segments=e,this._params=t,this._color=l,this._lineWidth=n,this._priceSeries=r}
}
class m{
attached(e){
this._params=e,this._requestUpdate=e.requestUpdate,this._rebuildViews()}
detached(){
this._params=null,this._requestUpdate=void 0}
updateSegments(e){
var t;
this._segments=e,this._rebuildViews(),null==(t=this._requestUpdate)||t.call(this)}
setStyle(e,t){
var l;
this._color=e,this._lineWidth=t,this._rebuildViews(),null==(l=this._requestUpdate)||l.call(this)}
setPriceSeries(e){
var t;
this._priceSeries=e,this._rebuildViews(),null==(t=this._requestUpdate)||t.call(this)}
paneViews(){
return this._paneViews}
_rebuildViews(){
this._paneViews=[new d(this._segments,this._params,this._color,this._lineWidth,this._priceSeries)]}
constructor(){
this._segments=[],this._params=null,this._paneViews=[],this._color="rgba(255,255,255,0.75)",this._lineWidth=1.5,this._priceSeries=null}
}
var f=l(72548),p=l(35064);
let g={
gamma:{
pos:[0,178,169],neg:[239,66,111]}
,vanna:{
pos:[168,85,247],neg:[251,146,60]}
,charm:{
pos:[52,211,153],neg:[244,114,182]}
,gamma_cumulative:{
pos:[0,178,169],neg:[239,66,111]}
,vanna_cumulative:{
pos:[168,85,247],neg:[251,146,60]}
,charm_cumulative:{
pos:[52,211,153],neg:[244,114,182]}
}
,x={
gamma:"Gamma",vanna:"Vanna",charm:"Charm",gamma_cumulative:"Gamma",vanna_cumulative:"Vanna",charm_cumulative:"Charm"}
;
function v(e,t){
return(0,p.ed)(e,t)}
function b(){
var e,t,l,n;
let r=new Intl.DateTimeFormat("en-US",{
timeZone:"America/New_York",hour12:!1,hour:"2-digit",minute:"2-digit"}
).formatToParts(new Date);
return(parseInt(null!=(l=null==(e=r.find(e=>"hour"===e.type))?void 0:e.value)?l:"0",10)-9)*60+(parseInt(null!=(n=null==(t=r.find(e=>"minute"===e.type))?void 0:t.value)?n:"0",10)-30)}
function _(e){
var t,l;
let{
summary:o,tsIndex:u,compact:h=!1,candles:d,dashboardTheme:p="dark",product:_="SPX",liveSpot:w,gammaColors:S,vannaColors:y,charmColors:M,defaultMetric:N="gamma",date:j}
=e,C=(0,s.Ym)(),k=(0,r.useRef)(null),D=(0,r.useRef)(null),V=(0,r.useRef)(null),E=(0,r.useRef)(null),R=(0,r.useRef)(null),[F,T]=(0,r.useState)(N);
(0,r.useEffect)(()=>{
T(N)}
,[N]);
let[I,U]=(0,r.useState)(!0),P=I?"".concat(F,"_cumulative"):F,L=e=>"gamma"===e?.8:1,[W,A]=(0,r.useState)(L(N));
(0,r.useEffect)(()=>{
A(L(F))}
,[F]);
let[q,O]=(0,r.useState)(150),[B,Y]=(0,r.useState)(!1),[Z,z]=(0,r.useState)(null),[X,$]=(0,r.useState)(()=>b()>=60?5:1),G=(0,r.useRef)(!1),H=(0,r.useCallback)(e=>{
G.current=!0,$(e)}
,[]);
(0,r.useEffect)(()=>{
if(1!==X||G.current)return;
let e=window.setInterval(()=>{
if(G.current)return void window.clearInterval(e);
b()>=60&&($(5),window.clearInterval(e))}
,3e4);
return()=>window.clearInterval(e)}
,[X]);
let J=(0,r.useRef)(null),K=(0,r.useRef)(null);
(0,r.useRef)(!1);
let Q=(0,r.useMemo)(()=>{
var e,t,l;
if(!(null==o||null==(e=o.timeline)?void 0:e.length)||null==u)return null;
let n=Math.min(u,o.timeline.length-1);
return null!=(l=null==(t=o.timeline[n])?void 0:t.ts)?l:null}
,[o,u]),ee=(0,r.useMemo)(()=>{
var e;
return null==o||null==(e=o.timeline)?void 0:e.map(e=>e.ts)}
,[null==o?void 0:o.timeline]),{
surface:et,resolvedTs:el,isLoading:en,timelineDate:er}
=(0,f.ro)("VIX"===_?"VIX":"SPX",P,Q,j,ee),ea="mono"===p;
(0,r.useEffect)(()=>()=>{
var e;
null==(e=R.current)||e.destroy(),D.current=null,V.current=null,E.current=null,R.current=null}
,[]);
let es=(0,r.useMemo)(()=>{
var e;
return null!=(e=({
gamma:S,vanna:y,charm:M}
)[F])?e:g[P]}
,[F,P,S,y,M]);
(0,r.useEffect)(()=>{
el&&(J.current=el),K.current=et}
,[el,et]);
let ei=(0,r.useMemo)(()=>{
if(!et||0===q)return et;
let e=w||et.spot,t=e-q,l=e+q,n=[];
for(let e=0;
e<et.price_levels.length;
e++)et.price_levels[e]>=t&&et.price_levels[e]<=l&&n.push(e);
return 0===n.length?et:{
...et,price_levels:n.map(e=>et.price_levels[e]),grid:n.map(e=>et.grid[e])}
}
,[et,q,w]),eo=null!=er?er:new Date().toLocaleDateString("sv-SE",{
timeZone:"America/New_York"}
),ec=(0,r.useMemo)(()=>(null==d?void 0:d.length)?function(e,t,l){
if(0===e.length)return[];
let n=60*t,r=new Map;
for(let t of e){
let e=Math.floor(function(e){
let[t,l]=e.split(":").map(Number);
return 3600*t+60*l}
(new Date(t.ts).toLocaleTimeString("en-US",{
hour12:!1,timeZone:"America/New_York",hour:"2-digit",minute:"2-digit"}
))/n)*n;
r.has(e)||r.set(e,[]),r.get(e).push(t)}
let a=[];
for(let e of[...r.keys()].sort((e,t)=>e-t)){
let t=r.get(e),n=String(Math.floor(e/3600)).padStart(2,"0"),s=String(Math.floor(e%3600/60)).padStart(2,"0");
a.push({
time:v(l,"".concat(n,":").concat(s)),open:t[0].open,high:Math.max(...t.map(e=>e.high)),low:Math.min(...t.map(e=>e.low)),close:t[t.length-1].close}
)}
return a}
(d,X,eo):[],[d,X,eo]),eu=(0,r.useCallback)(()=>{
var e;
let t=null==(e=k.current)?void 0:e.chart;
if(!t)return;
let l=new c;
R.current=l;
let n=t.addCustomSeries(l,{
cellShader:()=>"rgba(0,0,0,0)",cellBorderWidth:0,cellBorderColor:"transparent",priceLineVisible:!1,lastValueVisible:!1}
);
D.current=n;
let r=t.addSeries(a.HD,{
upColor:ea?"#a0a0a0":"#22c55e",downColor:ea?"#606060":"#ef4444",borderUpColor:ea?"#a0a0a0":"#22c55e",borderDownColor:ea?"#606060":"#ef4444",wickUpColor:ea?"#a0a0a0":"#22c55e",wickDownColor:ea?"#606060":"#ef4444",priceLineVisible:!1,lastValueVisible:!1}
);
V.current=r;
let s=new m;
r.attachPrimitive(s),s.setPriceSeries(n),E.current=s,t.subscribeCrosshairMove(e=>{
var t,l,a,s,i,o;
if(!e.point||!e.time)return void z(null);
let c=null!=(s=r.coordinateToPrice(e.point.y))?s:n.coordinateToPrice(e.point.y);
if(null===c)return void z(null);
let u=K.current;
if(!(null==u?void 0:u.price_levels)||!(null==u?void 0:u.grid))return void z(null);
let h=0,d=1/0;
for(let e=0;
e<u.price_levels.length;
e++){
let t=Math.abs(u.price_levels[e]-c);
t<d&&(d=t,h=e)}
let m=e.time,f=(null==(t=u.grid[h])?void 0:t.length)?u.grid[h].length-1:0;
if(u.time_steps){
let e=1/0;
for(let t=0;
t<u.time_steps.length;
t++){
let l=Math.abs(v(eo,u.time_steps[t])-m);
l<e&&(e=l,f=t)}
}
let p=null!=(i=null==(l=u.grid[h])?void 0:l[f])?i:0;
z({
price:c,time:null!=(o=null==(a=u.time_steps)?void 0:a[f])?o:"",value:p}
)}
);
try{
let e=v(eo,"09:30"),l=v(eo,"16:00");
t.timeScale().setVisibleRange({
from:e,to:l}
)}
catch(e){
}
Y(!0)}
,[ea,eo]);
(0,r.useEffect)(()=>{
var e;
if(!B||!ei)return;
let t=D.current,l=E.current;
if(!t)return;
let n=Math.max(Math.abs(ei.min_val),Math.abs(ei.max_val))||1,r=ei.price_levels.length>=2?ei.price_levels[1]-ei.price_levels[0]:2;
t.applyOptions({
cellShader:e=>(function(e,t,l,n,r){
let a,s,i;
if(0===t)return"rgba(30,30,35,".concat((.2*r).toFixed(3),")");
let o=Math.min(1,Math.abs(e)/t),c=e>=0?l:n;
if(o<=.6){
let e=Math.sqrt(o/.6);
a=30+e*(c[0]-30),s=30+e*(c[1]-30),i=35+e*(c[2]-35)}
else{
let e=(o-.6)/.4*.35;
a=c[0]+(255-c[0])*e,s=c[1]+(255-c[1])*e,i=c[2]+(255-c[2])*e}
let u=.2+.6799999999999999*Math.pow(o,.6);
return"rgba(".concat(Math.round(a),",").concat(Math.round(s),",").concat(Math.round(i),",").concat((u*r).toFixed(3),")")}
)(e,n,es.pos,es.neg,W)}
);
let a=ei.time_steps.map((e,t)=>({
time:v(eo,e),cells:ei.price_levels.map((e,l)=>{
var n,a;
return{
low:e-r/2,high:e+r/2,amount:null!=(a=null==(n=ei.grid[l])?void 0:n[t])?a:0}
}
)}
));
t.setData(a);
let s=null==(e=k.current)?void 0:e.chart;
if(s)try{
let e=v(eo,"09:30"),t=v(eo,"16:00");
s.timeScale().setVisibleRange({
from:e,to:t}
)}
catch(e){
}
if(l){
let e=ei.time_steps.map(e=>v(eo,e)),t=ei.timestamp?v(eo,ei.timestamp):void 0,n=function(e,t,l,n){
let r=t.length,a=l.length;
if(r<2||a<2)return[];
let s=[],i=(e,t)=>Math.abs(e)/(Math.abs(e)+Math.abs(t)+1e-12);
for(let g=0;
g<r-1;
g++)for(let r=0;
r<a-1;
r++){
var o,c,u,h,d,m,f,p;
if(void 0!==n&&l[r+1]<=n)continue;
let a=null!=(d=null==(o=e[g])?void 0:o[r])?d:0,x=null!=(m=null==(c=e[g])?void 0:c[r+1])?m:0,v=null!=(f=null==(u=e[g+1])?void 0:u[r])?f:0,b=null!=(p=null==(h=e[g+1])?void 0:h[r+1])?p:0,_=8*(v>0)|4*(b>0)|2*(x>0)|a>0;
if(0===_||15===_)continue;
let w=t[g],S=t[g+1],y=l[r],M=l[r+1],N=i(v,b),j=i(a,x),C=i(a,v),k=i(x,b),D=[y+N*(M-y),S],V=[y+j*(M-y),w],E=[y,w+C*(S-w)],R=[M,w+k*(S-w)],F=(e,t)=>{
let l=e[0],r=e[1],a=t[0],i=t[1];
if(void 0!==n){
let e=l<n,t=a<n;
if(e&&t)return;
if(e||t){
let t=a-l;
if(1e-9>Math.abs(t))return;
let s=r+(n-l)/t*(i-r);
e?(l=n,r=s):(a=n,i=s)}
}
s.push({
time1:l,price1:r,time2:a,price2:i}
)}
;
switch(_){
case 1:case 14:F(E,V);
break;
case 2:case 13:F(V,R);
break;
case 3:case 12:F(E,R);
break;
case 4:case 11:F(D,R);
break;
case 5:F(E,D),F(V,R);
break;
case 6:case 9:F(D,V);
break;
case 7:case 8:F(E,D);
break;
case 10:F(D,R),F(E,V)}
}
return s}
(ei.grid,ei.price_levels,e,t),r=ea?"rgba(200,200,200,0.8)":"rgba(255,255,255,0.75)";
l.setStyle(r,1.5),l.updateSegments(n)}
}
,[B,ei,es,W,ea,eo]);
let eh=(0,r.useRef)(0),ed=(0,r.useRef)(null),em=(0,r.useRef)(null),ef=(0,r.useRef)(null),ep=(0,r.useMemo)(()=>{
var e,t;
let l=null!=(t=null==o||null==(e=o.timeline)?void 0:e.length)?t:0;
return null!=u&&l>0&&u>=l-1}
,[u,null==o||null==(t=o.timeline)?void 0:t.length]),eg=(0,r.useMemo)(()=>!j||j===new Date().toLocaleDateString("sv-SE",{
timeZone:"America/New_York"}
),[j]),ex=(0,r.useMemo)(()=>{
if(!Q||!eo||0===ec.length||ep)return ec.length;
let e=v(eo,Q),t=ec.length;
for(let l=ec.length-1;
l>=0;
l--)if(ec[l].time<=e){
t=l+1;
break}
return Math.max(1,t)}
,[ec,Q,eo,ep]);
(0,r.useEffect)(()=>{
var e;
if(!B||!ec.length)return;
let t=V.current,l=null==(e=k.current)?void 0:e.chart;
if(!l||!t)return;
let n=ec.slice(0,ex);
t.setData(n),eh.current=n.length,ed.current=n.length>0?{
...n[n.length-1]}
:null;
try{
let e=v(eo,"09:30"),t=v(eo,"16:00");
l.timeScale().setVisibleRange({
from:e,to:t}
)}
catch(e){
}
}
,[B,ec,eo]),(0,r.useEffect)(()=>{
B&&null!=w&&eo&&ep&&eg&&(em.current=w,null==ef.current&&(ef.current=requestAnimationFrame(()=>{
var e,t,l,n;
let r;
ef.current=null;
let a=em.current;
if(em.current=null,null==a)return;
let s=V.current;
if(!s)return;
let i=new Intl.DateTimeFormat("en-US",{
timeZone:"America/New_York",hour12:!1,hour:"2-digit",minute:"2-digit"}
).formatToParts(new Date),o=parseInt(null!=(l=null==(e=i.find(e=>"hour"===e.type))?void 0:e.value)?l:"0",10),c=parseInt(null!=(n=null==(t=i.find(e=>"minute"===e.type))?void 0:t.value)?n:"0",10),u=60*X,h=3600*o+60*c;
if(h<34200||h>=57600)return;
let d=Math.floor(h/u)*u,m=Math.floor(d/3600),f=Math.floor(d%3600/60),p=v(eo,"".concat(String(m).padStart(2,"0"),":").concat(String(f).padStart(2,"0"))),g=ed.current;
if(!g||g.time<p)r={
time:p,open:a,high:a,low:a,close:a}
,eh.current+=1;
else{
if(g.time!==p)return;
r={
time:p,open:g.open,high:Math.max(g.high,a),low:Math.min(g.low,a),close:a}
}
ed.current=r,s.update(r)}
)))}
,[w,B,eo,ep,eg,X]),(0,r.useEffect)(()=>()=>{
null!=ef.current&&(cancelAnimationFrame(ef.current),ef.current=null)}
,[]),(0,r.useEffect)(()=>{
let e=V.current;
if(!B||!e||0===ec.length)return;
let t=eh.current;
if(ex>t){
for(let l=t;
l<ex;
l++)e.update(ec[l]);
eh.current=ex}
else if(ex<t){
let l=t-ex;
l>0&&(e.pop(l),eh.current=ex)}
}
,[B,ex,ec]),(0,r.useEffect)(()=>{
var e;
if(!B||!Q||!eo)return;
let t=null==(e=k.current)?void 0:e.chart,l=V.current;
if(!t||!l)return;
let n=l.data();
if(!(null==n?void 0:n.length))return void t.clearCrosshairPosition();
let r=n[n.length-1];
t.setCrosshairPosition(r.close,r.time,l)}
,[B,Q,eo,ex]),(0,r.useEffect)(()=>{
let e=V.current;
e&&e.applyOptions({
upColor:ea?"#a0a0a0":"#22c55e",downColor:ea?"#606060":"#ef4444",borderUpColor:ea?"#a0a0a0":"#22c55e",borderDownColor:ea?"#606060":"#ef4444",wickUpColor:ea?"#a0a0a0":"#22c55e",wickDownColor:ea?"#606060":"#ef4444"}
)}
,[ea]);
let ev=(0,r.useMemo)(()=>({
rightPriceScale:{
scaleMargins:{
top:.01,bottom:.01}
,autoScale:!0}
,localization:{
priceFormatter:e=>e.toLocaleString("en-US",{
maximumFractionDigits:0}
)}
,timeScale:{
timeVisible:!0,secondsVisible:!1,rightOffset:2,fixLeftEdge:!0,tickMarkFormatter:e=>{
let t=new Date(1e3*e),l=t.getUTCHours(),n=t.getUTCMinutes();
return"".concat(l.toString().padStart(2,"0"),":").concat(n.toString().padStart(2,"0"))}
}
,crosshair:{
horzLine:{
labelVisible:!0}
,vertLine:{
labelVisible:!0}
}
}
),[]),eb=[25,50,75,100,150,0],e_=eb.indexOf(q),ew=e_>=0?e_:eb.length-1;
return(0,n.jsxs)("div",{
className:"flex-1 flex flex-col min-h-0",children:[(0,n.jsxs)("div",{
className:"flex items-center gap-2 flex-wrap ".concat(h?"px-2 py-1":"px-3 py-1.5"," flex-shrink-0"),children:[(0,n.jsx)("div",{
className:"flex bg-surface-2 rounded p-0.5",children:["gamma","vanna","charm"].map(e=>{
var t;
let l="gamma"===e?S:"vanna"===e?y:M,r=l?"rgb(".concat(l.pos.join(","),")"):"rgb(".concat(g[e].pos.join(","),")");
return(0,n.jsx)("button",{
onClick:()=>T(e),className:"px-1.5 py-0.5 text-[11px] font-medium rounded transition-all ".concat(F===e?"bg-dash-accent text-dash-accent-fg":"text-dash-muted hover:text-body"),style:F===e?{
backgroundColor:r,color:"#000"}
:void 0,children:null!=(t=x[e])?t:e}
,e)}
)}
),(0,n.jsxs)("div",{
className:"flex bg-surface-2 rounded p-0.5",children:[(0,n.jsx)("button",{
onClick:()=>U(!1),className:"px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors ".concat(I?"text-dash-dim hover:text-body":"bg-dash-accent/20 text-dash-accent"),children:"0DTE"}
),(0,n.jsx)("button",{
onClick:()=>U(!0),className:"px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors ".concat(I?"bg-dash-accent/20 text-dash-accent":"text-dash-dim hover:text-body"),children:"All"}
)]}
),(0,n.jsx)("div",{
className:"flex bg-surface-2 rounded p-0.5",children:[1,5,10,15,30].map(e=>(0,n.jsxs)("button",{
onClick:()=>H(e),className:"px-1 py-0.5 text-[10px] font-medium rounded transition-colors ".concat(X===e?"bg-dash-accent/20 text-dash-accent":"text-dash-dim hover:text-body"),children:[e,"m"]}
,e))}
),(0,n.jsxs)("div",{
className:"flex items-center gap-1",children:[(0,n.jsx)("span",{
className:"text-[10px] text-dash-dim",children:"Opacity"}
),(0,n.jsx)("input",{
type:"range",min:0,max:100,step:5,value:Math.round(100*W),onChange:e=>A(parseInt(e.target.value)/100),className:"w-14 h-1 accent-dash-accent"}
),(0,n.jsxs)("span",{
className:"text-[10px] text-body tabular-nums min-w-[24px]",children:[Math.round(100*W),"%"]}
)]}
),(0,n.jsxs)("div",{
className:"flex items-center gap-1",children:[(0,n.jsx)("span",{
className:"text-[10px] text-dash-dim",children:"Range"}
),(0,n.jsx)("input",{
type:"range",min:0,max:eb.length-1,step:1,value:ew,onChange:e=>O(eb[parseInt(e.target.value)]),className:"w-14 h-1 accent-dash-accent"}
),(0,n.jsx)("span",{
className:"text-[10px] text-body tabular-nums min-w-[28px]",children:0===q?"All":"\xb1".concat(q)}
)]}
),(0,n.jsxs)("div",{
className:"flex items-center gap-2 ml-auto text-[11px]",children:[(()=>{
var e;
let t=null!=(e=x[P])?e:P;
return(0,n.jsxs)(n.Fragment,{
children:[(0,n.jsxs)("span",{
className:"flex items-center gap-1",children:[(0,n.jsx)("span",{
className:"w-3 h-2 rounded",style:{
backgroundColor:"rgb(".concat(es.pos.join(","),")")}
}
),(0,n.jsx)("span",{
className:"text-body",children:t}
)]}
),(0,n.jsxs)("span",{
className:"flex items-center gap-1",children:[(0,n.jsx)("span",{
className:"w-3 h-2 rounded",style:{
backgroundColor:"rgb(".concat(es.neg.join(","),")")}
}
),(0,n.jsxs)("span",{
className:"text-body",children:["−",t]}
)]}
)]}
)}
)(),(0,n.jsxs)("span",{
className:"flex items-center gap-1",children:[(0,n.jsx)("span",{
className:"w-3 h-0.5 rounded",style:{
background:ea?"rgba(200,200,200,0.8)":"rgba(255,255,255,0.75)"}
}
),(0,n.jsx)("span",{
className:"text-body",children:"Zero"}
)]}
),et&&(0,n.jsxs)("span",{
className:"text-dash-dim ml-1",children:[et.timestamp," ET"]}
)]}
)]}
),(0,n.jsxs)("div",{
className:"flex-1 min-h-0 relative",children:[(0,n.jsx)(i.A,{
ref:k,theme:p,options:ev,onReady:eu,locale:C,className:"w-full h-full"}
),en&&(0,n.jsx)("div",{
className:"absolute inset-0 flex items-center justify-center pointer-events-none",children:(0,n.jsx)("div",{
className:"w-5 h-5 border-2 border-dash-border border-t-dash-accent rounded-full animate-spin"}
)}
),!en&&!et&&(0,n.jsx)("div",{
className:"absolute inset-0 flex items-center justify-center text-dash-dim text-sm pointer-events-none",children:"No surface data available"}
),Z&&0!==Z.value&&(0,n.jsx)("div",{
className:"absolute top-2 left-2 z-20 bg-surface-1/90 backdrop-blur-sm rounded-lg px-3 py-1.5 text-xs pointer-events-none border border-dash-border/30",children:(0,n.jsxs)("div",{
className:"flex items-center gap-3",children:[(0,n.jsx)("span",{
className:"text-dash-dim",children:"Strike"}
),(0,n.jsx)("span",{
className:"text-body font-medium tabular-nums",children:Z.price.toFixed(0)}
),(0,n.jsx)("span",{
className:"text-dash-dim",children:(null!=(l=x[F])?l:F).toUpperCase()}
),(0,n.jsx)("span",{
className:"font-semibold tabular-nums ".concat(Z.value>=0?"gex-pos":"gex-neg"),children:(()=>{
let e=Z.value,t=Math.abs(e),l=e<0?"-":"+";
return t>=1e9?"".concat(l,"$").concat((t/1e9).toFixed(1),"B"):t>=1e6?"".concat(l,"$").concat((t/1e6).toFixed(1),"M"):t>=1e3?"".concat(l,"$").concat((t/1e3).toFixed(1),"K"):t>=1?"".concat(l,"$").concat(t.toFixed(1)):t>=.001?"".concat(l).concat(t.toFixed(4)):t>0?"".concat(l).concat(t.toExponential(1)):"0"}
)()}
)]}
)}
)]}
)]}
)}
}
}
]);
