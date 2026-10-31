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
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden;color:#dce8ff;
    background:radial-gradient(ellipse at 52% 42%,#0a1730 0%,#050a14 55%,#03050a 100%);
    font-family:-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;
    -webkit-font-smoothing:antialiased}
  canvas{display:block;position:fixed;inset:0;cursor:crosshair}
  .glass{background:linear-gradient(180deg,rgba(13,26,46,.86),rgba(8,14,26,.78));
    border:1px solid rgba(70,120,180,.22);border-radius:16px;
    box-shadow:0 18px 46px rgba(0,0,0,.42), inset 0 1px 0 rgba(140,200,255,.08);
    backdrop-filter:blur(14px)}
  #top{position:fixed;left:26px;top:22px;padding:16px 20px;min-width:300px}
  #top .row1{display:flex;align-items:center;gap:10px}
  #top .logo{width:10px;height:10px;border-radius:50%;background:#59e0ff;
    box-shadow:0 0 14px #59e0ff,0 0 30px rgba(89,224,255,.5)}
  #top h1{font-size:17px;margin:0;letter-spacing:.5px;font-weight:600}
  #top .sub{margin-top:6px;font-size:12px;color:#7d95b5;letter-spacing:.4px}
  #stats{display:flex;gap:22px;margin-top:14px;padding-top:13px;
    border-top:1px solid rgba(80,130,190,.16)}
  #stats div{display:flex;flex-direction:column;gap:3px}
  #stats b{font-size:19px;font-weight:600;font-variant-numeric:tabular-nums}
  #stats span{font-size:11px;color:#6f88a8;letter-spacing:.6px}
  #stats .c1 b{color:#59e0ff} #stats .c2 b{color:#ffc861}
  #stats .c3 b{color:#b98cff} #stats .c4 b{color:#6ef3b0}
  #side{position:fixed;left:26px;top:250px;bottom:96px;width:286px;padding:14px 6px 12px 14px;
    display:flex;flex-direction:column}
  #side .h{font-size:12px;color:#7d95b5;letter-spacing:1px;margin:2px 0 10px 2px}
  #filters{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
  .chip{font-size:11px;padding:5px 10px;border-radius:20px;cursor:pointer;user-select:none;
    border:1px solid rgba(80,130,190,.3);color:#9db6d6;background:rgba(12,24,42,.5);transition:.18s}
  .chip.on{color:#04121e;font-weight:600}
  .chip[data-k="稳定"].on{background:#59e0ff;border-color:#59e0ff}
  .chip[data-k="待办"].on{background:#ffc861;border-color:#ffc861}
  .chip[data-k="归档"].on{background:#b98cff;border-color:#b98cff}
  #list{overflow-y:auto;padding-right:8px;flex:1;scrollbar-width:thin;
    scrollbar-color:rgba(90,140,200,.4) transparent}
  #list::-webkit-scrollbar{width:6px}
  #list::-webkit-scrollbar-thumb{background:rgba(90,140,200,.35);border-radius:3px}
  .item{padding:9px 10px;border-radius:10px;cursor:pointer;margin-bottom:5px;
    border:1px solid transparent;transition:.15s}
  .item:hover{background:rgba(30,60,100,.45);border-color:rgba(90,150,220,.35)}
  .item .t{font-size:12.5px;line-height:1.5;color:#cfe2ff;
    overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .item .m{display:flex;align-items:center;gap:7px;margin-top:6px;font-size:10.5px;color:#6f88a8}
  .bar{flex:1;height:3px;border-radius:2px;background:rgba(80,120,170,.2);overflow:hidden}
  .bar i{display:block;height:100%;border-radius:2px;transition:width .3s}
  #legend{position:fixed;right:26px;top:22px;padding:14px 18px;font-size:12px;color:#9db6d6;line-height:2.1}
  #legend .l{display:flex;align-items:center;gap:8px}
  #legend .d{width:8px;height:8px;border-radius:50%}
  #legend .note{margin-top:8px;padding-top:9px;border-top:1px solid rgba(80,130,190,.16);
    font-size:11px;color:#6f88a8;line-height:1.8;max-width:190px}
  #detail{position:fixed;right:26px;bottom:96px;width:300px;padding:16px 18px;display:none}
  #detail .k{font-size:11px;color:#7d95b5;letter-spacing:.6px}
  #detail .name{font-size:15px;margin:6px 0 10px;line-height:1.5}
  #detail .txt{font-size:12.5px;color:#a9c1dd;line-height:1.7;max-height:110px;overflow:auto}
  #detail .meta{display:flex;gap:16px;margin-top:12px;padding-top:11px;
    border-top:1px solid rgba(80,130,190,.16);font-size:11px;color:#6f88a8}
  #detail .meta b{color:#cfe2ff;font-weight:600;font-variant-numeric:tabular-nums}
  #bottom{position:fixed;left:26px;right:26px;bottom:22px;padding:12px 18px;
    display:flex;align-items:center;gap:14px}
  button{background:rgba(20,44,74,.85);border:1px solid rgba(90,150,220,.35);color:#bfe4ff;
    padding:8px 15px;border-radius:9px;cursor:pointer;font-size:12.5px;transition:.16s;
    font-family:inherit}
  button:hover{background:rgba(32,64,104,.95);border-color:rgba(120,190,255,.6)}
  button.primary{background:linear-gradient(180deg,#2a7fbf,#1b5a8e);border-color:#3d9fd9;color:#fff}
  button.primary:hover{background:linear-gradient(180deg,#3695db,#226aa5)}
  #bottom .lbl{font-size:11.5px;color:#7d95b5;letter-spacing:.5px}
  input[type=range]{width:140px;accent-color:#59e0ff}
  #spd{font-size:11.5px;color:#9db6d6;min-width:64px;font-variant-numeric:tabular-nums}
  #day{margin-left:auto;font-size:11.5px;color:#6f88a8;letter-spacing:.6px}
  #tip{position:fixed;padding:10px 13px;background:rgba(10,20,36,.95);
    border:1px solid rgba(90,150,220,.4);border-radius:10px;font-size:12.5px;max-width:340px;
    pointer-events:none;display:none;line-height:1.65;box-shadow:0 12px 30px rgba(0,0,0,.5)}
</style></head>
<body>
<canvas id="c"></canvas>

<div id="top" class="glass">
  <div class="row1"><span class="logo"></span><h1>记忆星图</h1></div>
  <div class="sub">memblocks · 三层记忆的可视化 · 越暗越接近遗忘</div>
  <div id="stats">
    <div class="c1"><b id="s1">0</b><span>节点</span></div>
    <div class="c2"><b id="s2">0</b><span>连线</span></div>
    <div class="c3"><b id="s3">0%</b><span>平均保持</span></div>
    <div class="c4"><b id="s4">0</b><span>快遗忘</span></div>
  </div>
</div>

<div id="side" class="glass">
  <div class="h">记忆列表</div>
  <div id="filters">
    <span class="chip on" data-k="稳定">稳定区</span>
    <span class="chip on" data-k="待办">待办</span>
    <span class="chip on" data-k="归档">归档</span>
  </div>
  <div id="list"></div>
</div>

<div id="legend" class="glass">
  <div class="l"><span class="d" style="background:#59e0ff"></span>稳定区</div>
  <div class="l"><span class="d" style="background:#ffc861"></span>待办</div>
  <div class="l"><span class="d" style="background:#b98cff"></span>归档</div>
  <div class="l"><span class="d" style="background:#ffd76a;box-shadow:0 0 8px #ffd76a"></span>恒星（永不遗忘）</div>
  <div class="note">悬停看详情 · 滚轮缩放 · 拖拽旋转<br>点星星 = 提到它，会重新变亮</div>
</div>

<div id="detail" class="glass">
  <div class="k" id="d-kind">—</div>
  <div class="name" id="d-name">—</div>
  <div class="txt" id="d-text"></div>
  <div class="meta">
    <span>权重 <b id="d-weight">—</b></span>
    <span>保持 <b id="d-ret">—</b></span>
    <span>最后想起 <b id="d-last">—</b></span>
  </div>
</div>

<div id="bottom" class="glass">
  <button class="primary" id="play">暂停时间</button>
  <span class="lbl">流速</span>
  <input id="speed" type="range" min="0.05" max="2" step="0.05" value="0.3">
  <span id="spd">0.3 天/秒</span>
  <button id="review">复习全部</button>
  <button id="reset">重置视角</button>
  <button id="orbits">轨道：开</button>
  <span id="day">已过 0.0 天</span>
</div>

<div id="tip"></div>
<script>
const DATA = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
let W=0,H=0,dpr=Math.min(2, devicePixelRatio||1);
function resize(){ W=innerWidth; H=innerHeight; cv.width=W*dpr; cv.height=H*dpr;
  cv.style.width=W+'px'; cv.style.height=H+'px'; ctx.setTransform(dpr,0,0,dpr,0,0); }
addEventListener('resize', resize); resize();

const DAY=86400000, N=DATA.nodes, L=DATA.links, byId={}, now0=Date.now();
const ARMS = 3;
// 三层轨道：稳定区在内、待办居中、归档在外
const ORBIT = {稳定:150, 待办:310, 归档:460};
const layerIdx = {稳定:0, 待办:0, 归档:0};
const layerCount = {稳定:0, 待办:0, 归档:0};
N.forEach(n=>{ layerCount[n.kind]=(layerCount[n.kind]||0)+1; });
N.forEach((n,i)=>{
  byId[n.id]=n;
  const k = n.kind, base = ORBIT[k] || 320;
  const idx = layerIdx[k]++, cnt = Math.max(1, layerCount[k]);
  const t = idx/Math.max(1,cnt);                       // 层内分布
  const arm = idx % ARMS;
  const r0 = base + (t-.5)*34 + (Math.random()-.5)*14; // 层内窄幅铺开
  n.r0 = r0;
  n.theta = arm*(Math.PI*2/ARMS) + t*2.6 + (Math.random()-.5)*.25;
  n.ecc = .05 + Math.random()*.16;                 // 轨道离心率
  n.incl = (k==='稳定'? -.22 : k==='待办'? .16 : .46); // 轨道倾角，制造 3D 层次
  n.phase = Math.random()*6.283;
  n.omega = .55/Math.pow(Math.max(60,r0), 1.15);   // 开普勒：内圈转得快
  n.trail = [];
  n.zOff = (Math.random()-.5)*90;
  n.x = Math.cos(n.theta)*r0;
  n.y = Math.sin(n.theta)*r0*0.62;
  n.z = n.zOff;
  n.flash = 0;
  n.lastMs = n.last ? Date.parse(n.last.replace(' ','T')) : now0;
  if (isNaN(n.lastMs)) n.lastMs = now0;
  if (n.permanent) { n.r0 = 52; n.theta = Math.random()*6.283; n.omega = .02; }
});

const DUST_COUNT = Math.min(1100, 260 + N.length*40);
const DUST = Array.from({length: DUST_COUNT}, (_, i) => {
  const t = i / DUST_COUNT;
  const arm = i % 3;
  const th = arm*(Math.PI*2/3) + t*5.4 + (Math.random()-.5)*.25;
  const r = 85 + t*660 + (Math.random()-.5)*70;
  return {
    th, r,
    w: .020 + .055/(1 + r/260),
    c: Math.random() < .5 ? '150,205,255' : (Math.random() < .5 ? '200,170,255' : '255,225,180'),
    s: Math.random() < .10 ? 1.9 : 1.15,
    a: .05 + Math.random()*.18,
  };
});
const CORE = Array.from({length: 320}, () => {
  const g = (Math.random()+Math.random()+Math.random()-1.5)/1.5;
  return {
    r: Math.abs(g)*120 + Math.random()*22,
    th: Math.random()*Math.PI*2,
    s: Math.random() < .12 ? 1.8 : 1.0,
    a: .10 + Math.random()*.35,
    c: Math.random() < .65 ? '255,236,190' : '190,225,255',
  };
});
const DUST_ROT0 = performance.now()/1000;
let rot=0, zoom=1.62, simDays=0, playing=true, speed=0.3, drag=false, last={x:0,y:0};
let hover=null, selected=null, showOrbits=true;
const show={稳定:true,待办:true,归档:true};

function retention(n){
  if (n.permanent) return 1;                 // 恒星：永不遗忘
  const ageDays=(now0-n.lastMs)/DAY+simDays;
  const tau=7+12*Math.max(.2,n.weight);
  return Math.exp(-Math.max(0,ageDays)/tau);
}
function hexA(hex,a){const x=parseInt(hex.slice(1),16);
  return 'rgba('+((x>>16)&255)+','+((x>>8)&255)+','+(x&255)+','+a.toFixed(3)+')';}
function project(n){const c=Math.cos(rot),s=Math.sin(rot);
  const x=n.x*c-n.z*s,z=n.x*s+n.z*c,p=900/(900+z+600)*zoom;
  return {x:W/2+x*p,y:H/2+n.y*p,p,z};}

function step(dt){
  const now = performance.now()/1000;
  for(const n of N){
    const r = retention(n);
    n.theta += n.omega * dt * (.55 + .9*r) * 60;   // 开普勒角速度
    const scale = 1 + .30*(1-r);                   // 快忘的往外飘
    const a = n.r0 * scale, b = a * (1 - n.ecc);
    const x = Math.cos(n.theta)*a;
    const y = Math.sin(n.theta)*b*0.62;
    const z = Math.sin(n.theta + n.phase)*a*n.incl*0.35;
    n.x = x; n.y = y; n.z = z + n.zOff*.25;
    n.trail.push([n.x, n.y, n.z]);
    if(n.trail.length > 26) n.trail.shift();
    if(n.flash>0) n.flash*=.94;
  }
}

function draw(){
  ctx.clearRect(0,0,W,H);
  const now = performance.now()/1000;
  const cx = W/2, cy = H/2;

  const neb = [[.30,.30,'#123f68',.55],[.72,.26,'#2a2154',.48],[.50,.78,'#0d3550',.42],[.16,.70,'#1c2e5c',.32]];
  for(const [fx,fy,col,al] of neb){
    const g = ctx.createRadialGradient(W*fx,H*fy,0,W*fx,H*fy,Math.max(W,H)*.45);
    g.addColorStop(0, hexA(col, al*.55));
    g.addColorStop(.45, hexA(col, al*.18));
    g.addColorStop(1, hexA(col, 0));
    ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  }

  let core = ctx.createRadialGradient(cx,cy,0,cx,cy,200*zoom);
  core.addColorStop(0,'rgba(255,244,214,.50)');
  core.addColorStop(.16,'rgba(170,225,255,.20)');
  core.addColorStop(.42,'rgba(95,155,235,.07)');
  core.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx,cy,200*zoom,0,7); ctx.fill();

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  const ring = ctx.createRadialGradient(cx,cy,96*zoom,cx,cy,128*zoom);
  ring.addColorStop(0,'rgba(120,200,255,0)');
  ring.addColorStop(.5,'rgba(160,225,255,.16)');
  ring.addColorStop(1,'rgba(120,200,255,0)');
  ctx.fillStyle = ring; ctx.beginPath(); ctx.arc(cx,cy,128*zoom,0,7); ctx.fill();
  ctx.restore();

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for(const s of CORE){
    const th = s.th + now*.35;
    const x = Math.cos(th)*s.r, y = Math.sin(th)*s.r*0.62, z = Math.sin(th*1.3)*16;
    const pr = 900/(900+z+600)*zoom;
    ctx.fillStyle = 'rgba(' + s.c + ',' + s.a.toFixed(3) + ')';
    ctx.beginPath(); ctx.arc(cx + x*pr, cy + y*pr, s.s, 0, 7); ctx.fill();
  }
  for(const d of DUST){
    const th = d.th + (now - DUST_ROT0)*d.w*6;
    const x = Math.cos(th)*d.r, y = Math.sin(th)*d.r*0.62;
    const z = Math.sin(th*.8)*d.r*.05;
    const pr = 900/(900+z+600)*zoom;
    const tw = .55 + .45*Math.sin(now*.7 + d.th*3);
    ctx.fillStyle = 'rgba(' + d.c + ',' + (d.a*tw).toFixed(3) + ')';
    ctx.fillRect(cx + x*pr, cy + y*pr, d.s, d.s);
  }
  ctx.restore();

  if(showOrbits){
    ctx.save();
    for(const n of N.filter(x=>show[x.kind])){
      const scale = 1 + .30*(1-retention(n));
      const a = n.r0*scale, b = a*(1-n.ecc);
      ctx.strokeStyle = n.permanent ? 'rgba(255,215,106,.16)' : hexA(n.color,.085);
      ctx.lineWidth = .8;
      ctx.beginPath();
      for(let t=0;t<=Math.PI*2+.05;t+=.12){
        const p = project({x:Math.cos(t)*a, y:Math.sin(t)*b*0.62,
                           z:Math.sin(t+n.phase)*a*n.incl*0.35 + n.zOff*.25});
        t===0 ? ctx.moveTo(p.x,p.y) : ctx.lineTo(p.x,p.y);
      }
      ctx.stroke();
    }
    ctx.restore();
  }

  for(const n of N.filter(x=>show[x.kind])){
    if(n.trail.length < 2) continue;
    ctx.beginPath();
    n.trail.forEach((pt,i)=>{
      const p = project({x:pt[0],y:pt[1],z:pt[2]});
      i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y);
    });
    ctx.strokeStyle = n.permanent ? 'rgba(255,215,106,.22)' : hexA(n.color,.15);
    ctx.lineWidth = 1.1; ctx.stroke();
  }

  for(const l of L){ const a=byId[l.s], b=byId[l.t];
    if(!a||!b||!show[a.kind]||!show[b.kind]) continue;
    const pa=project(a), pb=project(b), rr=Math.min(retention(a),retention(b));
    const mx=(pa.x+pb.x)/2, my=(pa.y+pb.y)/2;
    const qx=mx+(cx-mx)*.18, qy=my+(cy-my)*.18;
    ctx.strokeStyle='rgba(110,170,240,'+(0.05+0.30*rr*l.w).toFixed(3)+')';
    ctx.lineWidth=.5+1.2*l.w;
    ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.quadraticCurveTo(qx,qy,pb.x,pb.y); ctx.stroke();
  }

  const vis = N.filter(n=>show[n.kind]);
  const pts = vis.map(n=>({n,...project(n)})).sort((a,b)=>a.z-b.z);
  for(const it of pts){
    const n=it.n, r=retention(n);
    const col = n.permanent ? '#ffd76a' : n.color;
    let rad=(2.2+Math.min(9,n.weight)*(.45+.75*r))*it.p*(1+.35*n.flash);
    if(n.permanent) rad *= 1.7;
    const alpha=n.permanent?1:(.10+.90*r);

    ctx.save();
    ctx.shadowColor = hexA(col, .55*alpha);
    ctx.shadowBlur = n.permanent ? 26 : 14*r*it.p;
    if(r>.18){
      const g=ctx.createRadialGradient(it.x,it.y,0,it.x,it.y,rad*4.6);
      g.addColorStop(0,hexA(col,.95*alpha));g.addColorStop(.35,hexA(col,.36*alpha));
      g.addColorStop(1,hexA(col,0));
      ctx.fillStyle=g;ctx.beginPath();ctx.arc(it.x,it.y,rad*4.6,0,7);ctx.fill();
    }
    ctx.fillStyle=hexA(col,Math.max(.12,alpha));
    ctx.beginPath();ctx.arc(it.x,it.y,Math.max(1,rad),0,7);ctx.fill();
    ctx.restore();

    if(n.permanent){
      const L2=rad*6.2;
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
        const gg=ctx.createLinearGradient(it.x,it.y,it.x+dx*L2,it.y+dy*L2);
        gg.addColorStop(0,'rgba(255,238,180,.60)');gg.addColorStop(1,'rgba(255,215,106,0)');
        ctx.strokeStyle=gg;ctx.lineWidth=1.6;
        ctx.beginPath();ctx.moveTo(it.x,it.y);ctx.lineTo(it.x+dx*L2,it.y+dy*L2);ctx.stroke();
      }
    }
    if(r<.25){ ctx.strokeStyle='rgba(120,140,170,.30)'; ctx.lineWidth=.8;
      ctx.beginPath();ctx.arc(it.x,it.y,Math.max(2,rad+3),0,7);ctx.stroke(); }
    if(selected===n){ ctx.strokeStyle='#7ff3ff'; ctx.lineWidth=1.6;
      ctx.beginPath();ctx.arc(it.x,it.y,rad+9,0,7);ctx.stroke(); }
    if(it.p>.5&&r>.34){ctx.fillStyle='rgba(215,232,255,'+(.32+.5*r).toFixed(2)+')';
      ctx.font='12px "Microsoft YaHei",sans-serif';
      ctx.fillText(n.label.slice(0,22),it.x+rad+6,it.y+4);}
  }
}

function updateHud(){
  const rs=N.map(retention);
  const avg=rs.length?rs.reduce((a,b)=>a+b,0)/rs.length:0;
  document.getElementById('s1').textContent=N.length;
  document.getElementById('s2').textContent=L.length;
  document.getElementById('s3').textContent=Math.round(avg*100)+'%';
  document.getElementById('s4').textContent=rs.filter(x=>x<.25).length;
  document.getElementById('day').textContent='已过 '+simDays.toFixed(1)+' 天';
}
function buildList(){
  const box=document.getElementById('list');box.innerHTML='';
  const rows=N.filter(n=>show[n.kind])
    .map(n=>({n,r:retention(n)}))
    .sort((a,b)=>a.r-b.r);
  for(const {n,r} of rows){
    const div=document.createElement('div');div.className='item';
    div.innerHTML='<div class="t">'+n.label+'</div>'+
      '<div class="m"><span>'+(n.permanent?'恒星':n.kind)+'</span><span class="bar"><i style="width:'+
      Math.round(r*100)+'%;background:'+n.color+'"></i></span><span>'+
      Math.round(r*100)+'%</span></div>';
    div.onmouseenter=()=>{tip.style.display='block';tip.innerHTML='<b style="color:'+n.color+'">'+
      n.label+'</b><br><span style="color:#6f88a8">点一下 = 提到它</span>';};
    div.onmouseleave=()=>{tip.style.display='none';};
    div.onclick=()=>{selectNode(n);n.weight=Math.min(9,n.weight+.6);n.lastMs=now0;n.flash=1;};
    box.appendChild(div);
  }
}
function selectNode(n){
  selected=n;
  const d=document.getElementById('detail');
  d.style.display='block';
  document.getElementById('d-kind').textContent=n.kind;
  document.getElementById('d-name').textContent=n.label;
  document.getElementById('d-text').textContent=n.text;
  document.getElementById('d-weight').textContent=n.weight.toFixed(1);
  document.getElementById('d-ret').textContent=Math.round(retention(n)*100)+'%';
  document.getElementById('d-last').textContent=(n.last||'—').slice(0,10);
}
document.querySelectorAll('.chip').forEach(ch=>{
  ch.onclick=()=>{const k=ch.dataset.k;show[k]=!show[k];ch.classList.toggle('on',show[k]);buildList();};
});

let lastTs=0;
function tick(ts){
  const dt=lastTs?Math.min(.1,(ts-lastTs)/1000):0;lastTs=ts;
  if(playing) simDays+=dt*speed;
  rot+=dt*.06;step(dt);draw();
  if(ts%500<20){updateHud();buildList();}
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

cv.addEventListener('mousemove',e=>{
  const mx=e.clientX,my=e.clientY;hover=null;
  for(const n of N){const p=project(n);if(Math.hypot(p.x-mx,p.y-my)<15){hover={...p,n};break;}}
  if(hover){const n=hover.n,r=retention(n);
    tip.style.display='block';tip.style.left=(mx+16)+'px';tip.style.top=(my+14)+'px';
    tip.innerHTML='<b style="color:'+n.color+'">'+n.label+'</b><br>'+n.kind+
      ' · 权重 '+n.weight.toFixed(1)+' · 保持 '+Math.round(r*100)+'%'+
      '<br><span style="color:#6f88a8">点一下 = 提到它</span>';}
  else tip.style.display='none';
});
cv.addEventListener('click',e=>{
  for(const n of N){const p=project(n);
    if(Math.hypot(p.x-e.clientX,p.y-e.clientY)<16){
      selectNode(n);n.weight=Math.min(9,n.weight+.6);n.lastMs=now0;n.flash=1;break;}}
});
cv.addEventListener('wheel',e=>{zoom*=e.deltaY>0?.92:1.08;zoom=Math.max(.5,Math.min(3.4,zoom));},{passive:true});
cv.addEventListener('mousedown',e=>{drag=true;last={x:e.clientX,y:e.clientY};});
addEventListener('mouseup',()=>drag=false);
addEventListener('mousemove',e=>{if(!drag)return;
  rot+=(e.clientX-last.x)*.005;N.forEach(n=>n.y+=(e.clientY-last.y)*.25);
  last={x:e.clientX,y:e.clientY};});

document.getElementById('play').onclick=function(){
  playing=!playing;this.textContent=playing?'暂停时间':'继续时间';};
document.getElementById('speed').oninput=e=>{speed=parseFloat(e.target.value);
  document.getElementById('spd').textContent=speed.toFixed(2)+' 天/秒';};
document.getElementById('review').onclick=()=>{N.forEach(n=>{
  n.weight=Math.min(9,n.weight+.4);n.lastMs=now0;n.flash=1;});};
document.getElementById('reset').onclick=()=>{rot=0;zoom=1.62;simDays=0;};
document.getElementById('orbits').onclick=function(){
  showOrbits=!showOrbits;
  this.textContent='轨道：'+(showOrbits?'开':'关');};
updateHud();buildList();
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
            "permanent": bool(x.get("permanent")),
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
