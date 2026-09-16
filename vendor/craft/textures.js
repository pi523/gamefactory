import * as THREE from 'three';

// 程序化贴图：底色 + 上千个低 alpha 随机小矩形 + 若干条正弦扰动的线（与 game-sushi 同一配方）。
// 全部 memo 共享，谁都不许 dispose 别人的 map。
function cv(w, h = w) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return [c, c.getContext('2d')];
}
function finish(canvas, repeat = 1) {
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.anisotropy = 4;
  return t;
}
const rnd = (a, b) => a + Math.random() * (b - a);
const cache = new Map();
const memo = (key, make) => { if (!cache.has(key)) cache.set(key, make()); return cache.get(key); };

// 深色吧台木面
export function barWoodTexture() { return memo('barWood', () => {
  const [c, g] = cv(1024, 1024);
  g.fillStyle = '#3a2417'; g.fillRect(0, 0, 1024, 1024);
  for (let i = 0; i < 260; i++) {
    const y = Math.random() * 1024;
    g.strokeStyle = `rgba(${rnd(14, 40) | 0},${rnd(8, 22) | 0},${rnd(4, 12) | 0},${rnd(0.06, 0.32).toFixed(2)})`;
    g.lineWidth = rnd(1, 10);
    g.beginPath(); g.moveTo(-10, y);
    for (let x = 0; x <= 1034; x += 44) g.lineTo(x, y + Math.sin(x * 0.009 + i) * rnd(2, 11));
    g.stroke();
  }
  for (let i = 0; i < 2600; i++) {
    g.fillStyle = `rgba(255,214,170,${rnd(0.01, 0.045).toFixed(3)})`;
    g.fillRect(Math.random() * 1024, Math.random() * 1024, rnd(1, 3), rnd(1, 2));
  }
  return finish(c, 1);
}); }

// 黑色石材杯垫/台面：细噪 + 淡纹
export function stoneTexture() { return memo('stone', () => {
  const [c, g] = cv(512);
  g.fillStyle = '#1c1a19'; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 6000; i++) {
    g.fillStyle = `rgba(${rnd(40, 90) | 0},${rnd(38, 80) | 0},${rnd(36, 74) | 0},${rnd(0.03, 0.14).toFixed(2)})`;
    g.fillRect(Math.random() * 512, Math.random() * 512, rnd(1, 3), rnd(1, 3));
  }
  for (let i = 0; i < 14; i++) {
    g.strokeStyle = `rgba(120,110,100,${rnd(0.03, 0.09).toFixed(2)})`; g.lineWidth = rnd(0.6, 2.2);
    const y = Math.random() * 512;
    g.beginPath(); g.moveTo(0, y);
    for (let x = 0; x <= 512; x += 24) g.lineTo(x, y + Math.sin(x * 0.03 + i * 1.7) * rnd(6, 26));
    g.stroke();
  }
  return finish(c, 1);
}); }

// 柠檬/橙片：径向瓣纹
export function citrusTexture(kind = 'lemon') { return memo('citrus:' + kind, () => {
  const [c, g] = cv(512);
  const rind = { lemon: '#f2d24a', orange: '#f28a1e', lime: '#8fc24a' }[kind] || '#f2d24a';
  const flesh = { lemon: '#fbf1a6', orange: '#ffc26b', lime: '#d8ef9a' }[kind] || '#fbf1a6';
  const pith = '#fff8dc';
  const cx = 256, cy = 256, R = 244;
  g.clearRect(0, 0, 512, 512);
  g.fillStyle = rind; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fill();
  g.fillStyle = pith; g.beginPath(); g.arc(cx, cy, R * 0.9, 0, Math.PI * 2); g.fill();
  const n = 9;
  for (let i = 0; i < n; i++) {
    const a0 = (i / n) * Math.PI * 2 + 0.05, a1 = ((i + 1) / n) * Math.PI * 2 - 0.05;
    const grad = g.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 0.86);
    grad.addColorStop(0, flesh); grad.addColorStop(1, { lemon: '#f7e27a', orange: '#ffa93e', lime: '#a9d35a' }[kind] || '#f7e27a');
    g.fillStyle = grad;
    g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R * 0.84, a0, a1); g.closePath(); g.fill();
    // 果肉纤维
    g.strokeStyle = 'rgba(255,255,255,.35)'; g.lineWidth = 1.2;
    for (let k = 0; k < 7; k++) {
      const a = a0 + (a1 - a0) * (k + 0.5) / 7;
      g.beginPath(); g.moveTo(cx + Math.cos(a) * R * 0.14, cy + Math.sin(a) * R * 0.14);
      g.lineTo(cx + Math.cos(a) * R * 0.8, cy + Math.sin(a) * R * 0.8); g.stroke();
    }
  }
  g.fillStyle = pith; g.beginPath(); g.arc(cx, cy, R * 0.09, 0, Math.PI * 2); g.fill();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}); }

// 薄荷叶：alpha 形状 + 叶脉
export function leafTexture() { return memo('leaf', () => {
  const [c, g] = cv(256, 512);
  g.clearRect(0, 0, 256, 512);
  const grad = g.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0, '#4f8a3a'); grad.addColorStop(1, '#2f6a2a');
  g.fillStyle = grad;
  g.beginPath(); g.moveTo(128, 6);
  g.bezierCurveTo(236, 130, 226, 360, 128, 506);
  g.bezierCurveTo(30, 360, 20, 130, 128, 6);
  g.closePath(); g.fill();
  g.strokeStyle = 'rgba(210,240,180,.55)'; g.lineWidth = 3;
  g.beginPath(); g.moveTo(128, 20); g.lineTo(128, 490); g.stroke();
  g.lineWidth = 1.6;
  for (let i = 0; i < 7; i++) {
    const y = 70 + i * 58;
    g.beginPath(); g.moveTo(128, y); g.quadraticCurveTo(170, y + 20, 128 + 78 - i * 6, y + 46); g.stroke();
    g.beginPath(); g.moveTo(128, y); g.quadraticCurveTo(86, y + 20, 128 - 78 + i * 6, y + 46); g.stroke();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}); }

// 纸吸管条纹
export function strawTexture(hex = '#d94a3a') { return memo('straw:' + hex, () => {
  const [c, g] = cv(64, 256);
  g.fillStyle = '#f7f1e4'; g.fillRect(0, 0, 64, 256);
  g.fillStyle = hex;
  for (let y = -64; y < 320; y += 32) { g.beginPath(); g.moveTo(0, y); g.lineTo(64, y + 24); g.lineTo(64, y + 40); g.lineTo(0, y + 16); g.closePath(); g.fill(); }
  return finish(c, 1);
}); }

// 环境贴图：暖顶光 + 暗地 + 两块灯箱（没有它玻璃和金属会是纯黑）
export function envTexture() { return memo('env', () => {
  const [c, g] = cv(512, 256);
  const sky = g.createLinearGradient(0, 0, 0, 256);
  sky.addColorStop(0.0, '#fff1d8');
  sky.addColorStop(0.32, '#d9c3a0');
  sky.addColorStop(0.5, '#6d5a47');
  sky.addColorStop(0.62, '#2a1f18');
  sky.addColorStop(1.0, '#120c08');
  g.fillStyle = sky; g.fillRect(0, 0, 512, 256);
  for (const [x, w] of [[60, 120], [290, 100], [420, 60]]) {
    const gr = g.createRadialGradient(x + w / 2, 48, 4, x + w / 2, 48, w);
    gr.addColorStop(0, 'rgba(255,255,255,.95)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(x - w, 0, w * 3, 140);
  }
  // 一条冷色窄灯带，给玻璃边缘冷高光
  const cool = g.createLinearGradient(0, 150, 0, 175);
  cool.addColorStop(0, 'rgba(120,160,255,0)'); cool.addColorStop(0.5, 'rgba(140,175,255,.55)'); cool.addColorStop(1, 'rgba(120,160,255,0)');
  g.fillStyle = cool; g.fillRect(0, 150, 512, 25);
  const t = new THREE.CanvasTexture(c);
  t.mapping = THREE.EquirectangularReflectionMapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}); }

// 酒标：纸底 + 标题块 + 几行"字" + 色带（没有真字，看起来像印刷品即可）
export function labelTexture(hex = '#8a2a1e') { return memo('label:' + hex, () => {
  const [c, g] = cv(512, 256);
  g.fillStyle = '#efe4cd'; g.fillRect(0, 0, 512, 256);
  for (let i = 0; i < 1800; i++) { g.fillStyle = `rgba(120,100,70,${rnd(0.02, 0.07).toFixed(3)})`; g.fillRect(Math.random() * 512, Math.random() * 256, rnd(1, 3), rnd(1, 2)); }
  g.strokeStyle = 'rgba(60,40,20,.55)'; g.lineWidth = 3; g.strokeRect(14, 14, 484, 228);
  g.fillStyle = hex; g.fillRect(0, 96, 512, 28);
  g.fillStyle = '#2a1f18';
  const cx = 256; g.beginPath(); g.moveTo(cx - 70, 60); g.lineTo(cx + 70, 60); g.lineTo(cx + 58, 84); g.lineTo(cx - 58, 84); g.closePath(); g.fill();
  for (let r = 0; r < 4; r++) { const w = rnd(120, 220), y = 148 + r * 20; g.fillStyle = `rgba(42,31,24,${(0.75 - r * 0.12).toFixed(2)})`; g.fillRect(cx - w / 2, y, w, 6); }
  g.beginPath(); g.arc(cx, 40, 12, 0, Math.PI * 2); g.fillStyle = hex; g.fill();
  return finish(c, 1);
}); }

// 噪声凹凸（冰块霜面 / 玻璃微瑕）
export function noiseBumpTexture() { return memo('bump', () => {
  const [c, g] = cv(256);
  g.fillStyle = '#808080'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 9000; i++) { const v = (110 + Math.random() * 60) | 0; g.fillStyle = `rgba(${v},${v},${v},${rnd(0.15, 0.5).toFixed(2)})`; g.beginPath(); g.arc(Math.random() * 256, Math.random() * 256, rnd(1, 5), 0, Math.PI * 2); g.fill(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(2, 2); return t;
}); }

// 吧台后墙：暗暖色 + 一团柔光，别是纯黑
export function wallTexture() { return memo('wall', () => {
  const [c, g] = cv(1024, 512);
  g.fillStyle = '#1a120d'; g.fillRect(0, 0, 1024, 512);
  const gr = g.createRadialGradient(560, 200, 20, 560, 200, 620);
  gr.addColorStop(0, 'rgba(255,196,130,.30)'); gr.addColorStop(0.45, 'rgba(200,140,80,.10)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 1024, 512);
  for (let i = 0; i < 5000; i++) { g.fillStyle = `rgba(255,220,180,${rnd(0.01, 0.04).toFixed(3)})`; g.fillRect(Math.random() * 1024, Math.random() * 512, rnd(1, 3), rnd(1, 3)); }
  // 一条搁板的影子线
  g.fillStyle = 'rgba(0,0,0,.35)'; g.fillRect(0, 300, 1024, 10);
  return finish(c, 1);
}); }

// 杯壁冷凝水珠（凹凸图）：大小不一的圆珠，底部略密
export function dropletTexture() { return memo('droplet', () => {
  const [c, g] = cv(512);
  g.fillStyle = '#808080'; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 520; i++) {
    const y = 512 - Math.pow(Math.random(), 0.7) * 512, x = Math.random() * 512, r = rnd(1.5, 6.5);
    const gr = g.createRadialGradient(x - r * 0.3, y - r * 0.3, 0, x, y, r);
    gr.addColorStop(0, '#d0d0d0'); gr.addColorStop(0.7, '#9a9a9a'); gr.addColorStop(1, '#808080');
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 1); return t;
}); }

// 焦散光斑：杯子透光落在台面上的那一团亮纹
export function causticTexture() { return memo('caustic', () => {
  const [c, g] = cv(256);
  g.clearRect(0, 0, 256, 256);
  const base = g.createRadialGradient(128, 128, 10, 128, 128, 120);
  base.addColorStop(0, 'rgba(255,255,255,.55)'); base.addColorStop(0.5, 'rgba(255,255,255,.22)'); base.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = base; g.beginPath(); g.arc(128, 128, 120, 0, Math.PI * 2); g.fill();
  g.strokeStyle = 'rgba(255,255,255,.55)'; g.lineWidth = 2.2;
  for (let i = 0; i < 26; i++) {
    g.beginPath(); const a0 = Math.random() * Math.PI * 2, r0 = rnd(18, 96);
    for (let k = 0; k <= 24; k++) { const a = a0 + k * 0.26; const r = r0 + Math.sin(k * 0.9 + i) * 9; const x = 128 + Math.cos(a) * r, y = 128 + Math.sin(a) * r * 0.85; k ? g.lineTo(x, y) : g.moveTo(x, y); }
    g.stroke();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}); }

// 柠檬/青柠果皮：底色 + 毛孔（凹凸也用它）
export function citrusSkinTexture(kind = 'lemon') { return memo('skin:' + kind, () => {
  const [c, g] = cv(512);
  const base = kind === 'lemon' ? '#e8c53a' : kind === 'lime' ? '#6fa33a' : '#ef8a1e';
  g.fillStyle = base; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 9000; i++) { const v = Math.random(); g.fillStyle = v > 0.5 ? `rgba(255,240,170,${rnd(0.04, 0.16).toFixed(2)})` : `rgba(90,70,10,${rnd(0.04, 0.14).toFixed(2)})`; g.beginPath(); g.arc(Math.random() * 512, Math.random() * 512, rnd(0.8, 2.6), 0, Math.PI * 2); g.fill(); }
  const t = finish(c, 1); t.repeat.set(2, 1); return t;
}); }
export function citrusBumpTexture() { return memo('skinbump', () => {
  const [c, g] = cv(256);
  g.fillStyle = '#8a8a8a'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2600; i++) { const v = (60 + Math.random() * 60) | 0; g.fillStyle = `rgba(${v},${v},${v},.7)`; g.beginPath(); g.arc(Math.random() * 256, Math.random() * 256, rnd(0.8, 2.0), 0, Math.PI * 2); g.fill(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 2); return t;
}); }

// 奶茶铺：白瓷砖墙
export function tileTexture() { return memo('tile', () => {
  const [c, g] = cv(1024, 512);
  g.fillStyle = '#d9d2c6'; g.fillRect(0, 0, 1024, 512);
  const w = 128, h = 64;
  for (let row = 0; row < 8; row++) for (let col = -1; col < 9; col++) {
    const x = col * w + (row % 2) * w / 2, y = row * h;
    const v = 240 + (Math.random() * 12 - 6) | 0;
    g.fillStyle = `rgb(${v},${v - 2},${v - 6})`; g.fillRect(x + 3, y + 3, w - 6, h - 6);
    g.fillStyle = 'rgba(255,255,255,.35)'; g.fillRect(x + 3, y + 3, w - 6, 6);
  }
  return finish(c, 1);
}); }

// 奶茶铺：浅色桦木台面
export function lightWoodTexture() { return memo('lightWood', () => {
  const [c, g] = cv(1024, 1024);
  g.fillStyle = '#d8b98a'; g.fillRect(0, 0, 1024, 1024);
  for (let i = 0; i < 220; i++) {
    const y = Math.random() * 1024;
    g.strokeStyle = `rgba(${rnd(120, 170) | 0},${rnd(80, 120) | 0},${rnd(40, 70) | 0},${rnd(0.05, 0.22).toFixed(2)})`; g.lineWidth = rnd(1, 7);
    g.beginPath(); g.moveTo(-10, y); for (let x = 0; x <= 1034; x += 46) g.lineTo(x, y + Math.sin(x * 0.01 + i) * rnd(2, 9)); g.stroke();
  }
  for (let i = 0; i < 2200; i++) { g.fillStyle = `rgba(255,245,225,${rnd(0.02, 0.06).toFixed(3)})`; g.fillRect(Math.random() * 1024, Math.random() * 1024, rnd(1, 3), rnd(1, 2)); }
  return finish(c, 1);
}); }

// 条纹（遮阳布 / 后墙）
export function stripeTexture(c1 = '#3aa6e6', c2 = '#ffffff') { return memo('stripe:' + c1 + c2, () => {
  const [c, g] = cv(512, 256);
  for (let i = 0; i < 8; i++) { g.fillStyle = i % 2 ? c1 : c2; g.fillRect(i * 64, 0, 64, 256); }
  for (let i = 0; i < 1500; i++) { g.fillStyle = `rgba(0,0,0,${rnd(0.01, 0.05).toFixed(3)})`; g.fillRect(Math.random() * 512, Math.random() * 256, rnd(1, 3), rnd(1, 3)); }
  const tt = finish(c, 1); tt.repeat.set(3, 1); return tt;
}); }

// 砖墙：错缝砌的红砖 + 灰缝 + 每块砖的色差与斑点（酒吧/精酿）
export function brickTexture(base = '#6a3a2a', mortar = '#b8a898') { return memo('brick:' + base + mortar, () => {
  const [c, g] = cv(1024, 1024);
  g.fillStyle = mortar; g.fillRect(0, 0, 1024, 1024);
  const bw = 128, bh = 60, gap = 7;
  for (let row = 0; row < 18; row++) for (let col = -1; col < 9; col++) {
    const x = col * bw + (row % 2) * bw / 2 + gap / 2, y = row * (bh + gap) + gap / 2;
    const [r0, g0, b0] = [parseInt(base.slice(1, 3), 16), parseInt(base.slice(3, 5), 16), parseInt(base.slice(5, 7), 16)];
    const k = rnd(0.78, 1.15); g.fillStyle = `rgb(${Math.min(255, r0 * k) | 0},${Math.min(255, g0 * k * rnd(0.92, 1.05)) | 0},${Math.min(255, b0 * k) | 0})`;
    g.fillRect(x, y, bw - gap, bh);
    for (let i = 0; i < 40; i++) { g.fillStyle = `rgba(${rnd(0, 60) | 0},${rnd(0, 30) | 0},${rnd(0, 20) | 0},${rnd(0.05, 0.25).toFixed(2)})`; g.fillRect(x + Math.random() * (bw - gap), y + Math.random() * bh, rnd(1, 5), rnd(1, 3)); }
    g.fillStyle = 'rgba(255,255,255,.07)'; g.fillRect(x, y, bw - gap, 3); g.fillStyle = 'rgba(0,0,0,.18)'; g.fillRect(x, y + bh - 3, bw - gap, 3);
  }
  for (let i = 0; i < 6000; i++) { g.fillStyle = `rgba(0,0,0,${rnd(0.01, 0.05).toFixed(3)})`; g.fillRect(Math.random() * 1024, Math.random() * 1024, rnd(1, 3), rnd(1, 3)); }
  const t = finish(c, 1); t.repeat.set(3, 1.5); return t;
}); }

// 带灰缝的瓷砖：比 tileTexture 更像瓷，有釿面反光斑与深色缝
export function groutTileTexture(tile = '#eef1ea', grout = '#9a9a90', cols = 8, rows = 6) { return memo(`gtile:${tile}:${grout}:${cols}x${rows}`, () => {
  const [c, g] = cv(1024, 768);
  g.fillStyle = grout; g.fillRect(0, 0, 1024, 768);
  const w = 1024 / cols, h = 768 / rows, gap = 6;
  const [r0, g0, b0] = [parseInt(tile.slice(1, 3), 16), parseInt(tile.slice(3, 5), 16), parseInt(tile.slice(5, 7), 16)];
  for (let row = 0; row < rows; row++) for (let col = -1; col <= cols; col++) {
    const x = col * w + (row % 2) * w / 2 + gap / 2, y = row * h + gap / 2; const k = rnd(0.94, 1.03);
    g.fillStyle = `rgb(${Math.min(255, r0 * k) | 0},${Math.min(255, g0 * k) | 0},${Math.min(255, b0 * k) | 0})`; g.fillRect(x, y, w - gap, h - gap);
    const gr = g.createLinearGradient(x, y, x, y + h); gr.addColorStop(0, 'rgba(255,255,255,.28)'); gr.addColorStop(0.35, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(0,0,0,.10)'); g.fillStyle = gr; g.fillRect(x, y, w - gap, h - gap);
  }
  const t = finish(c, 1); t.repeat.set(2.5, 1.6); return t;
}); }
