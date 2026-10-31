"""记忆星图：把稳定区、待办、归档块画成一张可交互的星图（单文件 HTML）。"""
import json
import re
from pathlib import Path

TEMPLATE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>记忆星图 · memblocks</title>
<style>
  html,body{margin:0;height:100%;background:radial-gradient(ellipse at 50% 40%,#0b1428 0%,#05070d 70%);color:#dce8ff;
    font-family:-apple-system,"Microsoft YaHei",sans-serif;overflow:hidden}
  canvas{display:block}
  #hud{position:fixed;left:24px;top:20px;font-size:13px;line-height:1.9;color:#8fa9c9;pointer-events:none}
  #hud b{color:#6fe3ff;font-size:15px;font-weight:600}
  #tip{position:fixed;padding:8px 12px;background:#0d1a2ecc;border:1px solid #2b4a72;border-radius:8px;
    font-size:13px;max-width:340px;pointer-events:none;display:none;line-height:1.6}
  #legend{position:fixed;right:24px;top:20px;font-size:12px;color:#8fa9c9;text-align:right;line-height:2}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:6px}
</style></head>
<body>
<canvas id="c"></canvas>
<div id="hud"><b>记忆星图</b><br>节点 __N__ · 连线 __E__<br>悬停查看，滚轮缩放，拖拽旋转</div>
<div id="legend">
  稳定区<span class="dot" style="background:#59e0ff"></span><br>
  待办<span class="dot" style="background:#ffc861"></span><br>
  归档<span class="dot" style="background:#b98cff"></span>
</div>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
let W = 0, H = 0, dpr = Math.min(2, devicePixelRatio || 1);
function resize(){ W = innerWidth; H = innerHeight; cv.width = W*dpr; cv.height = H*dpr;
  cv.style.width = W+'px'; cv.style.height = H+'px'; ctx.setTransform(dpr,0,0,dpr,0,0); }
addEventListener('resize', resize); resize();

const N = DATA.nodes, L = DATA.links;
const byId = {}; N.forEach(n => byId[n.id] = n);
N.forEach((n, i) => { const a = (i / N.length) * Math.PI * 2, r = 300 + Math.random()*260;
  n.x = Math.cos(a)*r; n.y = Math.sin(a)*r*0.62; n.z = (Math.random()-0.5)*200; n.vx=n.vy=n.vz=0; });

let rot = 0, zoom = 1.85, mouse = {x:0,y:0,down:false}, hover = null;

function step(){
  for (const n of N){ n.vx*=0.86; n.vy*=0.86; n.vz*=0.86; }
  for (const l of L){ const a=byId[l.s], b=byId[l.t]; if(!a||!b) continue;
    const dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z, d=Math.sqrt(dx*dx+dy*dy+dz*dz)||1;
    const f=(d-120)*0.012; const ux=dx/d*f, uy=dy/d*f, uz=dz/d*f;
    a.vx+=ux; a.vy+=uy; a.vz+=uz; b.vx-=ux; b.vy-=uy; b.vz-=uz; }
  for (const n of N){ const d=Math.hypot(n.x,n.y,n.z)||1; const f=-0.0016;
    n.vx+=n.x/d*f; n.vy+=n.y/d*f; n.vz+=n.z/d*f;
    n.x+=n.vx; n.y+=n.vy; n.z+=n.vz; }
}
function project(n){
  const c=Math.cos(rot), s=Math.sin(rot);
  const x = n.x*c - n.z*s, z = n.x*s + n.z*c;
  const p = 900/(900 + z + 600);
  return { x: W/2 + x*zoom*p, y: H/2 + n.y*zoom*p, p, z };
}
function draw(){
  ctx.clearRect(0,0,W,H);
  // 背景星尘
  for (let i=0;i<160;i++){ const x=(i*137.5)%W, y=(i*89.3)%H;
    ctx.fillStyle='rgba(140,180,255,'+(0.05+((i%7)/90))+')'; ctx.fillRect(x,y,1.4,1.4); }
  const pts = N.map(n => ({n, ...project(n)})).sort((a,b)=>a.z-b.z);
  for (const l of L){ const a=byId[l.s], b=byId[l.t]; if(!a||!b) continue;
    const pa=project(a), pb=project(b);
    ctx.strokeStyle='rgba(90,150,220,'+(0.10+0.18*l.w)+')'; ctx.lineWidth=0.7;
    ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.lineTo(pb.x,pb.y); ctx.stroke(); }
  for (const it of pts){ const n=it.n; const r=(3+Math.min(10,n.size))*it.p;
    const g=ctx.createRadialGradient(it.x,it.y,0,it.x,it.y,r*4);
    g.addColorStop(0,n.color+'ff'); g.addColorStop(0.35,n.color+'66'); g.addColorStop(1,n.color+'00');
    ctx.fillStyle=g; ctx.beginPath(); ctx.arc(it.x,it.y,r*4,0,7); ctx.fill();
    ctx.fillStyle=n.color; ctx.beginPath(); ctx.arc(it.x,it.y,r,0,7); ctx.fill();
    if (it.p > 0.55 || n.size >= 1.8){ ctx.fillStyle='rgba(215,232,255,.78)'; ctx.font='12px sans-serif';
      ctx.fillText(n.label.slice(0,22), it.x+r+6, it.y+4); }
  }
  if (hover){ const h=hover; ctx.strokeStyle='#7ff3ff'; ctx.lineWidth=1.4;
    ctx.beginPath(); ctx.arc(h.x,h.y,12,0,7); ctx.stroke(); }
}
function tick(){ rot += 0.0016; step(); draw(); requestAnimationFrame(tick); }

cv.addEventListener('mousemove', e => {
  const mx=e.clientX, my=e.clientY; hover=null;
  for (const n of N){ const p=project(n); if (Math.hypot(p.x-mx,p.y-my) < 14){ hover={...p, n}; break; } }
  if (hover){ tip.style.display='block'; tip.style.left=(mx+16)+'px'; tip.style.top=(my+14)+'px';
    tip.innerHTML = '<b style="color:'+hover.n.color+'">'+hover.n.label+'</b><br>'+
      hover.n.kind+' · 权重 '+hover.n.size.toFixed(1)+'<br>'+hover.n.text; }
  else tip.style.display='none';
});
cv.addEventListener('wheel', e => { zoom *= e.deltaY>0?0.92:1.08; zoom=Math.max(0.4,Math.min(3,zoom)); }, {passive:true});
let drag=false, last={x:0,y:0};
cv.addEventListener('mousedown', e => { drag=true; last={x:e.clientX,y:e.clientY}; });
addEventListener('mouseup', ()=>drag=false);
addEventListener('mousemove', e => { if(!drag) return; const dx=e.clientX-last.x, dy=e.clientY-last.y;
  rot += dx*0.005; N.forEach(n=>{ n.y += dy*0.25; }); last={x:e.clientX,y:e.clientY}; });

tick();
</script></body></html>
"""


def _grams(text):
    t = re.sub(r"[^\w\u4e00-\u9fa5]+", "", (text or "").lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else ({t} if t else set())


def build(store):
    nodes, gi = [], {}
    for x in store.stable_list():
        g = _grams(x["text"])
        gi[id(x)] = g
        nodes.append({"id": "s-" + x["id"], "kind": "稳定", "color": "#59e0ff",
                      "label": x["text"][:24], "text": x["text"],
                      "size": float(x.get("weight", 1.0)), "_g": g})
    for t in store.todo_list():
        g = _grams(t["text"])
        nodes.append({"id": "t-" + t["id"], "kind": "待办", "color": "#ffc861",
                      "label": t["text"][:24], "text": t["text"] + (f"（截止 {t['due']}）" if t.get("due") else ""),
                      "size": 1.2, "_g": g})
    for b in store.block_list():
        g = _grams(b.get("summary", "") + " " + " ".join(map(str, b.get("tags") or [])))
        nodes.append({"id": "b-" + b["id"], "kind": "归档", "color": "#b98cff",
                      "label": b.get("summary", "")[:24], "text": b.get("summary", ""),
                      "size": 1.6, "_g": g})

    links = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = nodes[i]["_g"] & nodes[j]["_g"]
            if len(shared) >= 1:
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
