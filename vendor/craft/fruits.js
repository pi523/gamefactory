import * as THREE from 'three';

/**
 * 果昔的水果块：每种水果一份真实形状 + 画布贴图（不是上了色的方块）。
 * 所有形状都装进半径 0.165 的包围球里——Solids 的预排位置与穿模检查按 size/2 = 0.17 算，换形状不改判据。
 */
function cv(w, h = w) { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')]; }
function tex(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; }
const rnd = (a, b) => a + Math.random() * (b - a);

// ---- 贴图 ----
function strawberrySkin() {
  const [c, g] = cv(256, 256);
  const gr = g.createLinearGradient(0, 256, 0, 0); gr.addColorStop(0, '#c0243c'); gr.addColorStop(0.55, '#de3d52'); gr.addColorStop(0.82, '#ec6f6e'); gr.addColorStop(0.86, '#f3b9a0'); gr.addColorStop(1, '#f5d9c0');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);                                                   // v=0 尖端深红 → 靛头发白
  for (let row = 0; row < 9; row++) for (let i = 0; i < 12; i++) {                                // 交错的籽坑
    const x = (i + (row % 2) * 0.5) / 12 * 256, y = 236 - row * 24 - Math.random() * 4;
    g.fillStyle = 'rgba(120,20,30,.45)'; g.beginPath(); g.ellipse(x, y + 1.5, 4.2, 5.5, 0, 0, 6.28); g.fill();
    g.fillStyle = '#f2df8c'; g.beginPath(); g.ellipse(x, y, 2.6, 3.8, 0, 0, 6.28); g.fill();
  }
  g.fillStyle = '#3c7f2b'; g.fillRect(0, 0, 256, 34);                                             // 顶部 13%：绿蒂
  g.fillStyle = '#2b5d1e'; for (let i = 0; i < 9; i++) { g.beginPath(); g.moveTo(i / 9 * 256, 0); g.lineTo(i / 9 * 256 + 14, 0); g.lineTo(i / 9 * 256 + 7, 44); g.closePath(); g.fill(); }
  return tex(c);
}
function bananaCap() {
  const [c, g] = cv(256, 256);
  const gr = g.createRadialGradient(128, 128, 8, 128, 128, 128); gr.addColorStop(0, '#e6d38f'); gr.addColorStop(0.5, '#f4e8b8'); gr.addColorStop(0.92, '#f6ecc4'); gr.addColorStop(1, '#e9d79a');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  g.strokeStyle = 'rgba(190,160,80,.35)'; g.lineWidth = 3; g.beginPath(); g.arc(128, 128, 62, 0, 6.28); g.stroke();       // 果心环
  g.fillStyle = 'rgba(90,60,20,.7)'; for (const a of [0, 2.1, 4.2]) { g.beginPath(); g.ellipse(128 + Math.cos(a) * 12, 128 + Math.sin(a) * 12, 3.5, 2.2, a, 0, 6.28); g.fill(); }   // 三颗小籽
  for (let i = 0; i < 40; i++) { g.strokeStyle = 'rgba(200,175,100,.18)'; g.lineWidth = 1; const a = rnd(0, 6.28); g.beginPath(); g.moveTo(128 + Math.cos(a) * 30, 128 + Math.sin(a) * 30); g.lineTo(128 + Math.cos(a) * 118, 128 + Math.sin(a) * 118); g.stroke(); }
  return tex(c);
}
function bananaSide() { const [c, g] = cv(64, 32); g.fillStyle = '#efdd9d'; g.fillRect(0, 0, 64, 32); for (let i = 0; i < 60; i++) { g.fillStyle = `rgba(200,170,90,${rnd(.05, .2).toFixed(2)})`; g.fillRect(rnd(0, 64), rnd(0, 32), 1, rnd(2, 8)); } return tex(c); }
function mangoSkin() {
  const [c, g] = cv(256, 256);
  const gr = g.createLinearGradient(0, 0, 256, 256); gr.addColorStop(0, '#ffc23a'); gr.addColorStop(0.5, '#ffa920'); gr.addColorStop(1, '#f28a12');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 90; i++) { g.strokeStyle = `rgba(255,235,150,${rnd(.08, .22).toFixed(2)})`; g.lineWidth = rnd(.6, 1.8); const y = rnd(0, 256); g.beginPath(); g.moveTo(0, y); for (let x = 0; x <= 256; x += 32) g.lineTo(x, y + Math.sin(x * 0.03 + i) * 6); g.stroke(); }   // 纤维
  for (let i = 0; i < 40; i++) { g.strokeStyle = `rgba(200,110,20,${rnd(.06, .16).toFixed(2)})`; g.lineWidth = rnd(.6, 1.4); const y = rnd(0, 256); g.beginPath(); g.moveTo(0, y); for (let x = 0; x <= 256; x += 32) g.lineTo(x, y + Math.sin(x * 0.04 + i) * 5); g.stroke(); }
  return tex(c);
}
function blueberrySkin() {
  const [c, g] = cv(256, 256);
  g.fillStyle = '#3a2f6e'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(150,160,210,${rnd(.04, .16).toFixed(2)})`; g.fillRect(rnd(0, 256), rnd(0, 256), rnd(1, 3), rnd(1, 3)); }   // 果粉
  g.fillStyle = '#1d1738'; g.beginPath(); for (let i = 0; i < 10; i++) { const a = i / 10 * 6.28 - 1.57, r = i % 2 ? 9 : 22; g.lineTo(128 + Math.cos(a) * r, 22 + Math.sin(a) * r * 0.55); } g.closePath(); g.fill();   // 顶端五角冠（球顶 v≈1）
  g.fillStyle = '#2a2350'; g.fillRect(0, 0, 256, 6);
  return tex(c);
}
function kiwiCap() {
  const [c, g] = cv(256, 256);
  const gr = g.createRadialGradient(128, 128, 20, 128, 128, 128); gr.addColorStop(0, '#c8dc8a'); gr.addColorStop(0.35, '#9cc94e'); gr.addColorStop(0.95, '#7fb43c'); gr.addColorStop(1, '#6a5238');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 120; i++) { const a = i / 120 * 6.28; g.strokeStyle = 'rgba(235,245,200,.35)'; g.lineWidth = 1; g.beginPath(); g.moveTo(128 + Math.cos(a) * 34, 128 + Math.sin(a) * 34); g.lineTo(128 + Math.cos(a) * 118, 128 + Math.sin(a) * 118); g.stroke(); }
  g.fillStyle = '#eef3d2'; g.beginPath(); g.ellipse(128, 128, 30, 24, 0.3, 0, 6.28); g.fill();                      // 白心
  g.fillStyle = '#1a1a14'; for (let i = 0; i < 34; i++) { const a = i / 34 * 6.28 + rnd(-.05, .05), r = rnd(38, 56); g.beginPath(); g.ellipse(128 + Math.cos(a) * r, 128 + Math.sin(a) * r, 3.2, 1.8, a, 0, 6.28); g.fill(); }
  return tex(c);
}
function kiwiSide() { const [c, g] = cv(128, 32); g.fillStyle = '#7a6242'; g.fillRect(0, 0, 128, 32); for (let i = 0; i < 700; i++) { g.fillStyle = `rgba(${rnd(60, 120) | 0},${rnd(45, 90) | 0},${rnd(25, 55) | 0},.7)`; g.fillRect(rnd(0, 128), rnd(0, 32), 1, rnd(1, 3)); } return tex(c); }

const wet = (extra) => new THREE.MeshPhysicalMaterial({ roughness: 0.32, metalness: 0, clearcoat: 0.55, clearcoatRoughness: 0.25, envMapIntensity: 0.9, ...extra });

// ---- 形状（都装进半径 0.165 的球里）----
function makeGeometry(key) {
  if (key === 'strawberry') {
    const prof = [[0.0, -0.15], [0.045, -0.12], [0.085, -0.06], [0.112, 0.02], [0.108, 0.08], [0.085, 0.125], [0.03, 0.15], [0.0, 0.15]].map(([r, y]) => new THREE.Vector2(r, y));
    return [new THREE.LatheGeometry(prof, 28), wet({ map: strawberrySkin() })];
  }
  if (key === 'banana') return [new THREE.CylinderGeometry(0.155, 0.150, 0.075, 30), [wet({ map: bananaSide(), roughness: 0.45 }), wet({ map: bananaCap(), roughness: 0.4, clearcoat: 0.35 }), wet({ map: bananaCap(), roughness: 0.4, clearcoat: 0.35 })]];
  if (key === 'kiwi') return [new THREE.CylinderGeometry(0.155, 0.155, 0.07, 30), [new THREE.MeshStandardMaterial({ map: kiwiSide(), roughness: 0.95 }), wet({ map: kiwiCap(), roughness: 0.3 }), wet({ map: kiwiCap(), roughness: 0.3 })]];
  if (key === 'blueberry') { const g = new THREE.SphereGeometry(0.125, 22, 16); g.scale(1, 0.88, 1); return [g, new THREE.MeshPhysicalMaterial({ map: blueberrySkin(), roughness: 0.62, metalness: 0, clearcoat: 0.12, clearcoatRoughness: 0.6, envMapIntensity: 0.6 })]; }
  // 芒果：真就是切成块的，但块要圆角、微不规则、有纤维
  let geo = new THREE.BoxGeometry(0.2, 0.2, 0.2, 4, 4, 4); const p = geo.attributes.position, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) { v.set(p.getX(i), p.getY(i), p.getZ(i)); const sph = v.clone().normalize().multiplyScalar(0.124); v.lerp(sph, 0.35); v.multiplyScalar(1 + (Math.random() - 0.5) * 0.04); p.setXYZ(i, v.x, v.y, v.z); }
  geo.computeVertexNormals();
  return [geo, wet({ map: mangoSkin(), roughness: 0.28, clearcoat: 0.7 })];
}

/** 一种水果一份 InstancedMesh（多材质用 geometry groups，InstancedMesh 支持） */
export function fruitMesh(key, max, k = 1) {
  const [geo, mat] = makeGeometry(key); if (k !== 1) geo.scale(k, k, k);
  const m = new THREE.InstancedMesh(geo, mat, max); m.count = 0; m.renderOrder = 24; m.castShadow = true; m.frustumCulled = false;
  return m;
}
