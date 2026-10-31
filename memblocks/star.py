"""记忆星图（可遗忘版）：节点按遗忘曲线变暗、缩小；点一下就"提到"，重新变亮。

生成单文件 HTML，无依赖。
"""
import json
import re
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>记忆星图 · memblocks</title>
<style>
  html,body{margin:0;height:100%;background:radial-gradient(ellipse at 50% 40%,#0b1428 0%,#04060c 72%);
    color:#dce8ff;font-family:-apple-system,"Microsoft YaHei",sans-serif;overflow:hidden}
  canvas{display:block;cursor:crosshair}
  #hud{position:fixed;left:24px;top:20px;font-size:13px;line-height:1.9;color:#8fa9c9;pointer-events:none}
  #hud b{color:#6fe3ff;font-size:15px}
  #ctl{position:fixed;left:24px;bottom:22px;display:flex;gap:10px;align-items:center;font-size:13px;color:#9fb6d4}
  button{background:#10203a;border:1px solid #2b4a72;color:#bfe4ff;padding:7px 13px;border-radius:8px;
    cursor:pointer;font-size:13px}
  button:hover{background:#17304f}
  input[type=range]{width:130px;accent-color:#59e0ff}
  #tip{position:fixed;padding:9px 13px;background:#0d1a2eeb;border:1px solid #2b4a72;border-radius:9px;
    font-size:13px;max-width:360px;pointer-events:none;display:none;line-height:1.65}
  #legend{position:fixed;right:24px;top:20px;font-size:12px;color:#8fa9c9;text-align:right;line-height:2}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:6px}
  #day{position:fixed;right:24px;bottom:24px;font-size:12px;color:#6f88a8}
</style></head>
<body>
<canvas id="c"></canvas>
<div id="hud"><b>记忆星图</b><br>节点 __N__ · 连线 __E__<br>越暗 = 越久没被想起</div>
<div id="legend">
  稳定区<span class="dot" style="background:#59e0ff"></span><br>
  待办<span class="dot" style="background:#ffc861"></span><br>
  归档<span class="dot" style="background:#b98cff"></span>
</div>
<div id="ctl">
  <button id="play">暂停时间</button>
  <span>流速</span><input id="speed" type="range" min="0.05" max="2" step="0.05" value="0.3">
  <span id="spd">0.3 天/秒</span>
  <button id="review">复习全部</button>
</div>
<div id="day"></div>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip'), dayEl = document.getElementById('day');
let W=0,H=0,dpr=Math.min(2, devicePixelRatio||1);
function resize(){ W=innerWidth; H=innerHeight; cv.width=W*dpr; cv.height=H*dpr;
  cv.style.width=W+'px'; cv.style.height=H+'px'; ctx.setTransform(dpr,0,0,dpr,0,0); }
addEventListener('resize', resize); resize();

const DAY = 86400000;
const N = DATA.nodes, L = DATA.links, byId={};
const now0 = Date.now();
N.forEach((n,i)=>{
  byId[n.id]=n;
  const a=(i/N.length)*Math.PI*2, r=300+Math.random()*280;
  n.x=Math.cos(a)*r; n.y=Math.sin(a)*r*0.62; n.z=(Math.random()-0.5)*220;
  n.vx=n.vy=n.vz=0; n.flash=0;
  n.lastMs = n.last ? Date.parse(n.last.replace(' ','T')) : now0;
  if (isNaN(n.lastMs)) n.lastMs = now0;
});

let rot=0, zoom=1.85, simDays=0, playing=true, speed=0.3, drag=false, last={x:0,y:0}, hover=null;
const playBtn=document.getElementById('play'), reviewBtn=document.getElementById('review');

function retention(n){
  const ageDays = (now0 - n.lastMs)/DAY + simDays;
  const tau = 7 + 12*Math.max(0.2, n.weight);   // 权重越高，忘得越慢
  return Math.exp(-Math.max(0,ageDays)/tau);
}
function step(){
  for(const n of N){ n.vx*=0.86; n.vy*=0.86; n.vz*=0.86; }
  for(const l of L){ const a=byId[l.s],b=byId[l.t]; if(!a||!b) continue;
    const dx=b.x-a.x,dy=b.y-a.y,dz=b.z-a.z,d=Math.hypot(dx,dy,dz)||1;
    const f=(d-130)*0.012, ux=dx/d*f, uy=dy/d*f, uz=dz/d*f;
    a.vx+=ux;a.vy+=uy;a.vz+=uz; b.vx-=ux;b.vy-=uy;b.vz-=uz; }
  for(const n of N){
    const r=retention(n);
    const pull=(1.0-r)*0.0035;                 // 快忘的往外飘
    const d=Math.hypot(n.x,n.y,n.z)||1;
    n.vx+=n.x/d*pull; n.vy+=n.y/d*pull; n.vz+=n.z/d*pull;
    n.x+=n.vx; n.y+=n.vy; n.z+=n.vz;
    if(n.flash>0) n.flash*=0.94;
  }
}
function project(n){ const c=Math.cos(rot),s=Math.sin(rot);
  const x=n.x*c-n.z*s, z=n.x*s+n.z*c, p=900/(900+z+600)*zoom;
  return {x:W/2+x*p, y:H/2+n.y*p, p, z}; }

function draw(){
  ctx.clearRect(0,0,W,H);
  for(let i=0;i<170;i++){ const x=(i*137.5)%W, y=(i*89.3)%H;
    ctx.fillStyle='rgba(140,180,255,'+(0.04+((i%7)/110))+')'; ctx.fillRect(x,y,1.3,1.3); }

  const pts=N.map(n=>({n,...project(n)})).sort((a,b)=>a.z-b.z);
  for(const l of L){ const a=byId[l.s],b=byId[l.t]; if(!a||!b) continue;
    const pa=project(a), pb=project(b);
    const ra=retention(a), rb=retention(b);
    const al=0.05+0.28*Math.min(ra,rb)*l.w;
    ctx.strokeStyle='rgba(90,150,220,'+al.toFixed(3)+')'; ctx.lineWidth=0.7;
    ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.lineTo(pb.x,pb.y); ctx.stroke(); }

  for(const it of pts){
    const n=it.n, r=retention(n);
    const rad=(2.2+Math.min(9,n.weight)*(0.45+0.75*r))*it.p*(1+0.35*n.flash);
    const alpha=0.10+0.90*r;
    const col=n.color;
    if(r>0.18){
      const g=ctx.createRadialGradient(it.x,it.y,0,it.x,it.y,rad*4.2);
      g.addColorStop(0,hexA(col,0.95*alpha)); g.addColorStop(0.35,hexA(col,0.35*alpha));
      g.addColorStop(1,hexA(col,0));
      ctx.fillStyle=g; ctx.beginPath(); ctx.arc(it.x,it.y,rad*4.2,0,7); ctx.fill();
    }
    ctx.fillStyle=hexA(col,Math.max(0.12,alpha));
    ctx.beginPath(); ctx.arc(it.x,it.y,Math.max(1,rad),0,7); ctx.fill();
    if(r<0.25){ ctx.strokeStyle='rgba(120,140,170,0.35)'; ctx.lineWidth=0.8;
      ctx.beginPath(); ctx.arc(it.x,it.y,Math.max(2,rad+3),0,7); ctx.stroke(); }

    if(it.p>0.5 && r>0.34){ ctx.fillStyle='rgba(215,232,255,'+(0.35+0.5*r).toFixed(2)+')';
      ctx.font='12px sans-serif'; ctx.fillText(n.label.slice(0,22), it.x+rad+6, it.y+4); }
  }
  dayEl.textContent = '已过 ' + simDays.toFixed(1) + ' 天';
}
function hexA(hex,a){ const n=parseInt(hex.slice(1),16);
  return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a.toFixed(3)+')'; }

let lastTs=0;
function tick(ts){
  const dt = lastTs ? Math.min(0.1, (ts-lastTs)/1000) : 0;
  lastTs = ts;
  if(playing) simDays += dt*speed;
  rot += dt*0.06; step(); draw();
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

cv.addEventListener('mousemove', e=>{
  const mx=e.clientX,my=e.clientY; hover=null;
  for(const n of N){ const p=project(n); if(Math.hypot(p.x-mx,p.y-my)<15){ hover={...p,n}; break; } }
  if(hover){ const n=hover.n, r=retention(n);
    tip.style.display='block'; tip.style.left=(mx+16)+'px'; tip.style.top=(my+14)+'px';
    tip.innerHTML='<b style="color:'+n.color+'">'+n.label+'</b><br>'+n.kind+
      ' · 权重 '+n.weight.toFixed(1)+' · 记忆保持 '+Math.round(r*100)+'%<br>'+n.text+
      '<br><span style="color:#6f88a8">点一下 = 提到它</span>'; }
  else tip.style.display='none';
});
cv.addEventListener('click', e=>{
  for(const n of N){ const p=project(n);
    if(Math.hypot(p.x-e.clientX,p.y-e.clientY)<16){
      n.weight=Math.min(9,n.weight+0.6); n.lastMs=now0; n.flash=1; break; } }
});
cv.addEventListener('wheel', e=>{ zoom*=e.deltaY>0?0.92:1.08; zoom=Math.max(0.5,Math.min(3.4,zoom)); },{passive:true});
cv.addEventListener('mousedown', e=>{ drag=true; last={x:e.clientX,y:e.clientY}; });
addEventListener('mouseup', ()=>drag=false);
addEventListener('mousemove', e=>{ if(!drag) return;
  rot+=(e.clientX-last.x)*0.005; N.forEach(n=>n.y+=(e.clientY-last.y)*0.25);
  last={x:e.clientX,y:e.clientY}; });

playBtn.onclick=()=>{ playing=!playing; playBtn.textContent=playing?'暂停时间':'继续时间'; };
document.getElementById('speed').oninput=e=>{ speed=parseFloat(e.target.value);
  document.getElementById('spd').textContent=speed.toFixed(1)+' 天/秒'; };
reviewBtn.onclick=()=>{ N.forEach(n=>{ n.weight=Math.min(9,n.weight+0.4); n.lastMs=now0; n.flash=1; }); };
</script></body></html>
"""


def _grams(text):
    t = re.sub(r"[^\w\u4e00-\u9fa5]+", "", (text or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


def build(store):
    nodes = []
    for x in store.stable_list():
        nodes.append({
            "id": "s-" + x["id"], "kind": "稳定", "color": "#59e0ff",
            "label": x["text"][:24], "text": x["text"],
            "weight": float(x.get("weight", 1.0)),
            "last": x.get("last_hit") or x.get("at", ""),
            "_g": _grams(x["text"]),
        })
    for t in store.todo_list():
        nodes.append({
            "id": "t-" + t["id"], "kind": "待办", "color": "#ffc861",
            "label": t["text"][:24],
            "text": t["text"] + (f"（截止 {t['due']}）" if t.get("due") else ""),
            "weight": 1.2, "last": t.get("at", ""), "_g": _grams(t["text"]),
        })
    for b in store.block_list():
        nodes.append({
            "id": "b-" + b["id"], "kind": "归档", "color": "#b98cff",
            "label": b.get("summary", "")[:24], "text": b.get("summary", ""),
            "weight": 1.6, "last": b.get("time", ""),
            "_g": _grams(b.get("summary", "") + " " + " ".join(map(str, b.get("tags") or []))),
        })

    links = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = nodes[i]["_g"] & nodes[j]["_g"]
            if shared:
                links.append({"s": nodes[i]["id"], "t": nodes[j]["id"],
                              "w": min(1.0, len(shared) / 6)})
    for n in nodes:
        n.pop("_g", None)
    return {"nodes": nodes, "links": links}


def render(store, out_path):
    data = build(store)
    html = (TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__N__", str(len(data["nodes"]))).replace("__E__", str(len(data["links"]))))
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return str(p)
