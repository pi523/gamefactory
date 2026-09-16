// 托盘图标：全部用 canvas 现画，不用素材。配料 = 装着那种液体的小瓶；装饰 = 它本来的样子。
import { citrusTexture, leafTexture } from './textures.js';

const cache = new Map();
const cv = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')]; };

function bottleIcon(css) {
  const [c, g] = cv(96, 128);
  g.clearRect(0, 0, 96, 128);
  // 瓶身轮廓
  const path = () => { g.beginPath(); g.moveTo(40, 6); g.lineTo(56, 6); g.lineTo(56, 30); g.quadraticCurveTo(76, 40, 76, 62); g.lineTo(76, 116); g.quadraticCurveTo(76, 124, 68, 124); g.lineTo(28, 124); g.quadraticCurveTo(20, 124, 20, 116); g.lineTo(20, 62); g.quadraticCurveTo(20, 40, 40, 30); g.closePath(); };
  path(); g.fillStyle = 'rgba(230,238,242,.55)'; g.fill();
  // 液体
  g.save(); path(); g.clip(); g.fillStyle = css; g.fillRect(0, 48, 96, 80); g.fillStyle = 'rgba(255,255,255,.25)'; g.fillRect(0, 48, 96, 5); g.restore();
  // 标签 + 瓶盖 + 高光
  g.fillStyle = '#f3ead6'; g.fillRect(24, 70, 48, 26); g.fillStyle = css; g.fillRect(24, 80, 48, 5);
  g.fillStyle = '#2a2320'; g.fillRect(38, 2, 20, 8);
  path(); g.strokeStyle = 'rgba(60,50,40,.55)'; g.lineWidth = 2.5; g.stroke();
  g.fillStyle = 'rgba(255,255,255,.35)'; g.fillRect(26, 40, 5, 72);
  return c.toDataURL();
}
function sliceIcon(kind) {
  const src = citrusTexture(kind).image; const [c, g] = cv(128, 128);
  g.save(); g.translate(64, 64); g.rotate(-0.4); g.drawImage(src, -56, -56, 112, 112); g.restore();
  return c.toDataURL();
}
function mintIcon() {
  const src = leafTexture().image; const [c, g] = cv(128, 128);
  for (const [x, y, a] of [[64, 70, -0.5], [64, 70, 0.5], [64, 66, 0]]) { g.save(); g.translate(x, y); g.rotate(a); g.drawImage(src, -22, -60, 44, 88); g.restore(); }
  return c.toDataURL();
}
function strawIcon(css, fat) {
  const [c, g] = cv(128, 128); g.save(); g.translate(64, 64); g.rotate(0.35);
  const w = fat ? 26 : 14; g.fillStyle = fat ? '#f7f1e4' : css; g.fillRect(-w / 2, -60, w, 120);
  if (fat) { g.fillStyle = css; for (let y = -60; y < 60; y += 24) { g.beginPath(); g.moveTo(-w / 2, y); g.lineTo(w / 2, y + 10); g.lineTo(w / 2, y + 18); g.lineTo(-w / 2, y + 8); g.closePath(); g.fill(); } }
  g.fillStyle = 'rgba(0,0,0,.25)'; g.fillRect(-w / 2, -60, w, 6); g.restore();
  return c.toDataURL();
}
function crumbIcon(css, n, size) {
  const [c, g] = cv(128, 128);
  for (let i = 0; i < n; i++) { const a = Math.random() * 6.28, r = Math.sqrt(Math.random()) * 46; g.save(); g.translate(64 + Math.cos(a) * r, 70 + Math.sin(a) * r * 0.7); g.rotate(Math.random() * 3); g.fillStyle = css; g.fillRect(-size / 2, -size / 3, size, size * 0.66); g.restore(); }
  g.fillStyle = 'rgba(0,0,0,.08)'; g.beginPath(); g.ellipse(64, 74, 50, 30, 0, 0, 6.28); g.fill();
  return c.toDataURL();
}
function pearlIconColor(css, n) {
  const [c, g] = cv(128, 128);
  for (let i = 0; i < n; i++) { const a = i * 1.3, r = i ? 26 : 0; const x = 64 + Math.cos(a) * r, y = 68 + Math.sin(a) * r * 0.7; const gr = g.createRadialGradient(x - 5, y - 6, 2, x, y, 18); gr.addColorStop(0, '#ffffff'); gr.addColorStop(1, css); g.fillStyle = gr; g.beginPath(); g.arc(x, y, 17, 0, 6.28); g.fill(); }
  return c.toDataURL();
}
function pearlIcon() {
  const [c, g] = cv(128, 128);
  for (let i = 0; i < 9; i++) { const a = i * 0.7, r = i ? 30 : 0; const x = 64 + Math.cos(a) * r, y = 68 + Math.sin(a) * r * 0.7; const gr = g.createRadialGradient(x - 5, y - 6, 2, x, y, 16); gr.addColorStop(0, '#7a5030'); gr.addColorStop(1, '#2a170d'); g.fillStyle = gr; g.beginPath(); g.arc(x, y, 15, 0, 6.28); g.fill(); }
  return c.toDataURL();
}

function fruitIcon(key, css) {
  const [c, g] = cv(128, 128); g.save(); g.translate(64, 66);
  if (key === 'banana') { g.rotate(-0.6); g.fillStyle = css; g.beginPath(); g.ellipse(0, 0, 54, 16, 0, 0, 6.28); g.fill(); g.fillStyle = 'rgba(90,70,20,.6)'; g.fillRect(48, -6, 10, 8); }
  else if (key === 'kiwi') { g.fillStyle = '#6b5a3a'; g.beginPath(); g.arc(0, 0, 46, 0, 6.28); g.fill(); g.fillStyle = css; g.beginPath(); g.arc(0, 0, 40, 0, 6.28); g.fill(); g.fillStyle = '#e9f3d0'; g.beginPath(); g.arc(0, 0, 12, 0, 6.28); g.fill(); g.fillStyle = '#222'; for (let i = 0; i < 18; i++) { const a = i * 0.35; g.beginPath(); g.ellipse(Math.cos(a) * 22, Math.sin(a) * 22, 3, 1.6, a, 0, 6.28); g.fill(); } }
  else if (key === 'strawberry') { g.fillStyle = css; g.beginPath(); g.moveTo(0, 48); g.bezierCurveTo(52, 20, 44, -30, 0, -24); g.bezierCurveTo(-44, -30, -52, 20, 0, 48); g.fill(); g.fillStyle = '#3f7a2a'; g.beginPath(); g.moveTo(-26, -22); g.lineTo(0, -44); g.lineTo(26, -22); g.lineTo(0, -14); g.fill(); g.fillStyle = 'rgba(255,240,200,.7)'; for (let i = 0; i < 14; i++) { g.beginPath(); g.arc((Math.random() - 0.5) * 50, (Math.random() - 0.3) * 50, 2, 0, 6.28); g.fill(); } }
  else if (key === 'blueberry') { for (const [x, y] of [[-22, 8], [20, 10], [0, -18]]) { g.fillStyle = css; g.beginPath(); g.arc(x, y, 22, 0, 6.28); g.fill(); g.fillStyle = 'rgba(255,255,255,.25)'; g.beginPath(); g.arc(x - 7, y - 8, 7, 0, 6.28); g.fill(); g.fillStyle = '#2a2450'; g.beginPath(); g.arc(x, y + 4, 6, 0, 6.28); g.fill(); } }
  else { g.fillStyle = css; g.beginPath(); g.ellipse(0, 0, 46, 34, -0.4, 0, 6.28); g.fill(); g.fillStyle = 'rgba(255,255,255,.28)'; g.beginPath(); g.ellipse(-16, -12, 14, 8, -0.4, 0, 6.28); g.fill(); }
  g.restore(); return c.toDataURL();
}
function leafIcon(css) {   // 茶叶罐
  const [c, g] = cv(128, 128); g.fillStyle = '#c9a24a'; g.fillRect(28, 26, 72, 90); g.fillStyle = css; g.fillRect(28, 50, 72, 40); g.fillStyle = '#8a6a2a'; g.fillRect(24, 18, 80, 14); g.fillStyle = 'rgba(0,0,0,.15)'; g.fillRect(90, 26, 10, 90);
  g.fillStyle = '#f3ead6'; g.fillRect(40, 58, 48, 24); g.fillStyle = css; g.fillRect(48, 66, 32, 4); g.fillRect(52, 74, 24, 3); return c.toDataURL();
}
/** kind: 'ingredient' | 'garnish' | 'fruit' | 'leaf' | 'syrup'；返回 data URL */
function foodIcon(key, css) {   // 食材：一小碟上放着那种东西的样子
  const [c, g] = cv(128, 128); g.fillStyle = '#f3ede2'; g.beginPath(); g.ellipse(64, 84, 54, 26, 0, 0, 6.28); g.fill(); g.strokeStyle = 'rgba(60,50,40,.35)'; g.lineWidth = 2; g.stroke();
  g.fillStyle = css;
  if (key === 'beef') { for (let i = 0; i < 4; i++) { g.save(); g.translate(40 + i * 16, 70 - i * 6); g.rotate(-0.4); g.fillRect(-16, -8, 34, 16); g.fillStyle = 'rgba(255,240,230,.45)'; g.fillRect(-16, -2, 34, 3); g.restore(); g.fillStyle = css; } }
  else if (key === 'radish') { for (let i = 0; i < 3; i++) { g.beginPath(); g.ellipse(44 + i * 20, 72 - i * 5, 18, 9, 0.2, 0, 6.28); g.fill(); g.strokeStyle = 'rgba(160,160,140,.5)'; g.stroke(); } }
  else if (key === 'cilantro' || key === 'garlic' || key === 'scallion') { for (let i = 0; i < 12; i++) { g.save(); g.translate(30 + Math.random() * 68, 58 + Math.random() * 26); g.rotate(Math.random() * 3); g.fillRect(-7, -2, 14, 4); g.restore(); } }
  else if (key === 'tripe') { g.beginPath(); for (let i = 0; i <= 20; i++) { const x = 24 + i * 4, y = 66 + Math.sin(i * 1.4) * 6; i ? g.lineTo(x, y) : g.moveTo(x, y); } for (let i = 20; i >= 0; i--) { g.lineTo(24 + i * 4, 84 + Math.sin(i * 1.4) * 6); } g.closePath(); g.fill(); g.fillStyle = 'rgba(0,0,0,.18)'; for (let i = 0; i < 12; i++) g.fillRect(28 + i * 7, 70, 2, 10); }
  else if (key === 'shrimp') { for (let i = 0; i < 3; i++) { g.beginPath(); g.ellipse(44 + i * 20, 70, 16, 12, 0, 0, 6.28); g.fill(); } }
  else if (key === 'potato' || key === 'lotus') { for (let i = 0; i < 3; i++) { g.beginPath(); g.ellipse(44 + i * 20, 72 - i * 4, 17, 10, 0.1, 0, 6.28); g.fill(); if (key === 'lotus') { g.fillStyle = '#f3ede2'; for (let k = 0; k < 6; k++) { const a = k / 6 * 6.28; g.beginPath(); g.ellipse(44 + i * 20 + Math.cos(a) * 8, 72 - i * 4 + Math.sin(a) * 5, 3, 2, 0, 0, 6.28); g.fill(); } g.fillStyle = css; } } }
  else if (key === 'cabbage') { for (let i = 0; i < 4; i++) { g.beginPath(); g.ellipse(40 + i * 16, 68 + (i % 2) * 8, 20, 12, i * 0.5, 0, 6.28); g.fill(); } g.fillStyle = 'rgba(255,255,255,.5)'; g.fillRect(48, 66, 40, 4); }
  else if (key === 'haw') { for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(44 + i * 20, 66, 13, 0, 6.28); g.fill(); g.fillStyle = 'rgba(255,255,255,.35)'; g.beginPath(); g.arc(40 + i * 20, 61, 4, 0, 6.28); g.fill(); g.fillStyle = css; } }
  else if (key === 'egg') { g.beginPath(); g.ellipse(64, 66, 22, 27, 0, 0, 6.28); g.fill(); }
  else if (key === 'crisp') { g.fillRect(30, 56, 68, 30); g.fillStyle = 'rgba(0,0,0,.15)'; for (let i = 0; i < 4; i++) g.fillRect(34 + i * 16, 58, 4, 26); }
  else if (key === 'sauce' || key === 'chili') { g.beginPath(); g.ellipse(64, 70, 26, 14, 0, 0, 6.28); g.fill(); g.fillStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.ellipse(56, 64, 8, 4, 0, 0, 6.28); g.fill(); }
  else { g.beginPath(); g.ellipse(64, 70, 26, 16, 0, 0, 6.28); g.fill(); }
  return c.toDataURL();
}
/** kind: 'ingredient' | 'garnish' | 'fruit' | 'leaf' | 'syrup' | 'food'；返回 data URL */
export function iconFor(kind, key, item) {
  const id = kind + ':' + key;
  if (cache.has(id)) return cache.get(id);
  let url;
  if (kind === 'food') { url = foodIcon(key, item.css); cache.set(id, url); return url; }
  if (kind === 'ingredient' || kind === 'syrup') url = bottleIcon(item.css);
  else if (kind === 'fruit') url = fruitIcon(key, item.css);
  else if (kind === 'leaf') url = leafIcon(item.css);
  else if (key === 'redbean') url = crumbIcon('#6b2a2a', 16, 12);
  else if (key === 'mangocube') url = crumbIcon('#ffb428', 8, 22);
  else if (key === 'mochi') url = pearlIconColor('#f6f1e6', 5);
  else if (key === 'strawberrytop') url = fruitIcon('strawberry', item.css);
  else if (key === 'kiwislice') url = fruitIcon('kiwi', item.css);
  else if (key === 'lemon' || key === 'orange' || key === 'lime') url = sliceIcon(key);
  else if (key === 'mint') url = mintIcon();
  else if (key === 'straw') url = strawIcon(item.css, false);
  else if (key === 'fatstraw') url = strawIcon(item.css, true);
  else if (key === 'oreo') url = crumbIcon('#2a221f', 14, 16);
  else if (key === 'coconutflake') url = crumbIcon('#eadcbf', 18, 12);
  else url = pearlIcon();
  cache.set(id, url); return url;
}
