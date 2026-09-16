import * as THREE from 'three';
import { barWoodTexture, lightWoodTexture, leafTexture, citrusSkinTexture, citrusBumpTexture, noiseBumpTexture } from './textures.js';

/**
 * 陈设库：写实的店内道具（几何体 + 画布贴纸），两组饮品游戏共用。
 * 原则：每件东西都是可辨认的实物——瓶有液体和带字的标签，罐里装着东西，灯会发光并真的照亮台面，黑板上有字。
 */
const cv = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')]; };
const rnd = (a, b) => a + Math.random() * (b - a);
const tex = (c) => { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
const cache = new Map();
const memo = (k, f) => { if (!cache.has(k)) cache.set(k, f()); return cache.get(k); };

/** 带字的酒标/商标 */
export function labelTextTexture(hex, title = '', sub = '', paper = '#efe4cd') { return memo(`ltx:${hex}:${title}:${sub}:${paper}`, () => {
  const [c, g] = cv(512, 256);
  g.fillStyle = paper; g.fillRect(0, 0, 512, 256);
  for (let i = 0; i < 1600; i++) { g.fillStyle = `rgba(120,100,70,${rnd(0.02, 0.06).toFixed(3)})`; g.fillRect(Math.random() * 512, Math.random() * 256, rnd(1, 3), rnd(1, 2)); }
  g.strokeStyle = 'rgba(60,40,20,.5)'; g.lineWidth = 4; g.strokeRect(16, 16, 480, 224); g.lineWidth = 1.5; g.strokeRect(28, 28, 456, 200);
  g.fillStyle = hex; g.fillRect(40, 132, 432, 10);
  g.fillStyle = '#2a1f18'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = `bold ${title.length > 6 ? 54 : 68}px "Hiragino Sans","PingFang SC","Noto Sans CJK SC",serif`; g.fillText(title, 256, 90);
  g.font = '28px "Hiragino Sans","PingFang SC",sans-serif'; g.fillStyle = 'rgba(42,31,24,.75)'; g.fillText(sub, 256, 178);
  g.beginPath(); g.arc(256, 218, 9, 0, Math.PI * 2); g.fillStyle = hex; g.fill();
  return tex(c);
}); }

/** 黑板 / 菜单板贴图 */
export function chalkTexture(lines, bg = '#24302a', w = 640, h = 400) { return memo(`chalk:${bg}:${lines.join('|')}`, () => {
  const [c, g] = cv(w, h);
  g.fillStyle = bg; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 3000; i++) { g.fillStyle = `rgba(255,255,255,${rnd(0.01, 0.05).toFixed(3)})`; g.fillRect(Math.random() * w, Math.random() * h, rnd(1, 4), rnd(1, 2)); }
  g.textAlign = 'center'; g.textBaseline = 'middle';
  lines.forEach((t, i) => { const first = i === 0; g.font = `${first ? 'bold ' : ''}${first ? 52 : 34}px "Hiragino Sans","PingFang SC","Noto Sans CJK SC",sans-serif`; g.fillStyle = first ? 'rgba(255,246,220,.95)' : ['rgba(255,255,255,.85)', 'rgba(255,214,150,.85)', 'rgba(190,230,200,.85)'][i % 3]; g.fillText(t, w / 2, 70 + i * (first ? 82 : 56) - (i ? 20 : 0)); if (first) { g.fillStyle = 'rgba(255,246,220,.6)'; g.fillRect(w / 2 - 120, 112, 240, 3); } });
  return tex(c);
}); }

/** 海报 / 挂画贴图 */
export function posterTexture(title, sub, bg = '#f3ead6', fg = '#2a1f18', accent = '#c1462f') { return memo(`poster:${title}:${sub}:${bg}`, () => {
  const [c, g] = cv(512, 704);
  g.fillStyle = bg; g.fillRect(0, 0, 512, 704);
  for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(0,0,0,${rnd(0.01, 0.04).toFixed(3)})`; g.fillRect(Math.random() * 512, Math.random() * 704, rnd(1, 3), rnd(1, 3)); }
  g.fillStyle = accent; g.beginPath(); g.arc(256, 280, 150, 0, Math.PI * 2); g.fill();
  g.fillStyle = 'rgba(255,255,255,.22)'; g.beginPath(); g.arc(210, 230, 60, 0, Math.PI * 2); g.fill();
  g.fillStyle = fg; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = 'bold 70px "Hiragino Sans","PingFang SC","Noto Sans CJK SC",serif'; g.fillText(title, 256, 520);
  g.font = '30px "Hiragino Sans","PingFang SC",sans-serif'; g.fillStyle = 'rgba(0,0,0,.6)'; g.fillText(sub, 256, 590);
  g.strokeStyle = 'rgba(0,0,0,.35)'; g.lineWidth = 6; g.strokeRect(22, 22, 468, 660);
  return tex(c);
}); }

const glassMat = (color = 0x2c4626, opacity = 0.55) => new THREE.MeshPhysicalMaterial({ color, roughness: 0.05, metalness: 0.0, transparent: true, opacity, envMapIntensity: 2.0, clearcoat: 1.0, clearcoatRoughness: 0.03, depthWrite: false, side: THREE.DoubleSide });
const capMat = new THREE.MeshStandardMaterial({ color: 0x2a2320, roughness: 0.5, metalness: 0.3 });

/**
 * 酒瓶/糖浆瓶：瓶身（透光玻璃）+ 里面的液体 + 带字标签 + 瓶盖。
 * opts: h 高, r 半径, glass 玻璃色, liquid 液体色, level 0..1, label {hex,title,sub}, cap 颜色, shape 'wine'|'round'|'square'
 */
export function bottle({ h = 2.6, r = 0.4, glass = 0x2c4626, glassOpacity = 0.55, liquid = 0x7a3a12, level = 0.7, label = { hex: '#8a2a1e', title: '', sub: '' }, cap = 0x2a2320, shape = 'wine' } = {}) {
  const g = new THREE.Group();
  const prof = shape === 'round'
    ? [[0, 0], [r * 0.9, 0], [r, 0.1], [r, h * 0.55], [r * 0.9, h * 0.72], [r * 0.4, h * 0.86], [r * 0.3, h * 0.92], [r * 0.3, h * 1.14], [r * 0.34, h * 1.15], [r * 0.34, h * 1.2], [0, h * 1.2]]
    : [[0, 0], [r * 0.9, 0], [r, 0.12], [r, h * 0.72], [r * 0.88, h * 0.80], [r * 0.34, h * 0.92], [r * 0.3, h * 1.02], [r * 0.3, h * 1.16], [r * 0.34, h * 1.17], [r * 0.34, h * 1.22], [0, h * 1.22]];
  const body = new THREE.Mesh(new THREE.LatheGeometry(prof.map(([rr, yy]) => new THREE.Vector2(rr, yy)), 40), glassMat(glass, glassOpacity)); body.castShadow = true; body.renderOrder = 12;
  const lp = prof.filter(([, yy]) => yy <= h * 0.72 * level + 0.001).map(([rr, yy]) => new THREE.Vector2(Math.max(0, rr - 0.03), yy)); lp.push(new THREE.Vector2(Math.max(0.01, (lp[lp.length - 1]?.x ?? r) - 0.0), h * 0.72 * level), new THREE.Vector2(0, h * 0.72 * level));
  const liq = new THREE.Mesh(new THREE.LatheGeometry(lp, 40), new THREE.MeshPhysicalMaterial({ color: liquid, roughness: 0.15, metalness: 0, transparent: true, opacity: 0.92, clearcoat: 0.4 })); liq.renderOrder = 11;
  const capM = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.37, r * 0.37, 0.24, 24), new THREE.MeshStandardMaterial({ color: cap, roughness: 0.45, metalness: 0.5 })); capM.position.y = h * 1.16;
  const lab = new THREE.Mesh(new THREE.CylinderGeometry(r * 1.012, r * 1.012, h * 0.30, 40, 1, true, -0.9, 1.8), new THREE.MeshStandardMaterial({ map: labelTextTexture(label.hex, label.title, label.sub), roughness: 0.85, side: THREE.DoubleSide })); lab.position.y = h * 0.40; lab.rotation.y = -Math.PI / 2 - 0.9 + 0.9;
  g.add(body, liq, capM, lab); return g;
}

/** 玻璃罐：装着豆子/茶叶/糖/珍珠的储物罐 */
export function jar({ r = 0.36, h = 1.0, content = 0x4a2a14, count = 60, grain = 0.06, level = 0.72, lid = 0x8a6a4a } = {}) {
  const g = new THREE.Group();
  const glass = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 28, 1, true), glassMat(0xf2f6f8, 0.28)); glass.position.y = h / 2; glass.renderOrder = 12;
  const bottom = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.04, 28), glassMat(0xf2f6f8, 0.5)); bottom.position.y = 0.02;
  const inst = new THREE.InstancedMesh(new THREE.SphereGeometry(grain, 8, 6), new THREE.MeshStandardMaterial({ color: content, roughness: 0.6 }), count);
  const m = new THREE.Matrix4(); for (let i = 0; i < count; i++) { const a = Math.random() * 6.28, rr = Math.sqrt(Math.random()) * (r - grain - 0.02), y = grain + Math.random() * (h * level - grain * 2); m.makeRotationY(a); m.setPosition(Math.cos(a) * rr, y, Math.sin(a) * rr); inst.setMatrixAt(i, m); }
  inst.renderOrder = 11;
  const fillM = new THREE.Mesh(new THREE.CylinderGeometry(r - 0.03, r - 0.03, h * level, 28), new THREE.MeshStandardMaterial({ color: content, roughness: 0.8, transparent: true, opacity: 0.55 })); fillM.position.y = h * level / 2; fillM.renderOrder = 10;
  const lidM = new THREE.Mesh(new THREE.CylinderGeometry(r * 1.05, r * 1.05, 0.1, 28), new THREE.MeshStandardMaterial({ color: lid, roughness: 0.6 })); lidM.position.y = h + 0.05;
  g.add(glass, bottom, inst, fillM, lidM); g.traverse((o) => { if (o.isMesh) o.castShadow = true; }); return g;
}

/** 搁板：木板 + 底下一条暗光带（酒吧那种） */
export function shelf({ w = 16, y = 3.3, z = -8.9, depth = 1.1, tex = 'bar', led = null } = {}) {
  const g = new THREE.Group();
  const board = new THREE.Mesh(new THREE.BoxGeometry(w, 0.14, depth), new THREE.MeshStandardMaterial({ map: tex === 'light' ? lightWoodTexture() : barWoodTexture(), roughness: 0.6 })); board.castShadow = true; board.receiveShadow = true; g.add(board);
  const bracketM = new THREE.MeshStandardMaterial({ color: 0x2a2320, roughness: 0.5, metalness: 0.6 });
  for (const x of [-w / 2 + 0.6, 0, w / 2 - 0.6]) { const br = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.5, depth * 0.8), bracketM); br.position.set(x, -0.32, 0); g.add(br); }
  if (led) { const strip = new THREE.Mesh(new THREE.BoxGeometry(w * 0.96, 0.03, 0.08), new THREE.MeshStandardMaterial({ color: led, emissive: led, emissiveIntensity: 2.2 })); strip.position.set(0, -0.09, depth / 2 - 0.1); g.add(strip); const l = new THREE.RectAreaLight ? null : null; void l; }
  g.position.set(0, y, z); return g;
}

/** 黑板/菜单板（带木框、有字） */
export function chalkboard({ x = 2.8, y = 5.6, z = -9.3, w = 4.6, h = 2.8, lines = ['MENU'], bg = '#24302a' } = {}) {
  const g = new THREE.Group();
  const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.08), new THREE.MeshStandardMaterial({ map: chalkTexture(lines, bg), roughness: 0.95 })); b.position.z = 0.02;
  const f = new THREE.Mesh(new THREE.BoxGeometry(w + 0.3, h + 0.3, 0.1), new THREE.MeshStandardMaterial({ map: barWoodTexture(), roughness: 0.7 })); f.position.z = -0.04;
  g.add(f, b); g.position.set(x, y, z); return g;
}

/** 挂画 / 海报（带框） */
export function poster({ x = -3, y = 5.8, z = -9.3, w = 2.0, title = '', sub = '', bg, fg, accent } = {}) {
  const g = new THREE.Group(); const h = w * 1.375;
  const p = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: posterTexture(title, sub, bg, fg, accent), roughness: 0.9 })); p.position.z = 0.045;   // 比画框正面凸出一点，别共面闪
  const f = new THREE.Mesh(new THREE.BoxGeometry(w + 0.16, h + 0.16, 0.06), new THREE.MeshStandardMaterial({ color: 0x2a2320, roughness: 0.6 }));
  g.add(f, p); g.position.set(x, y, z); return g;
}

/** 吊灯：灯罩 + 发光灯泡 + 真正照亮台面的点光 + 吊线 */
export function pendant(scene, { x = 0, y = 7.4, z = -1.5, color = 0xffb860, intensity = 22, shade = 'cone', shadeColor = 0x2a2320, cordTop = 12 } = {}) {
  const g = new THREE.Group();
  const shadeM = new THREE.MeshStandardMaterial({ color: shadeColor, roughness: 0.5, metalness: shade === 'cone' ? 0.5 : 0.0, side: THREE.DoubleSide });
  const sh = shade === 'cone' ? new THREE.Mesh(new THREE.ConeGeometry(0.75, 0.7, 28, 1, true), shadeM) : shade === 'paper' ? new THREE.Mesh(new THREE.SphereGeometry(0.75, 24, 16), new THREE.MeshStandardMaterial({ color: 0xfff0d8, emissive: color, emissiveIntensity: 0.6, roughness: 1, transparent: true, opacity: 0.92 })) : new THREE.Mesh(new THREE.SphereGeometry(0.7, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), shadeM);
  sh.position.y = shade === 'paper' ? 0 : 0.3; g.add(sh);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffe0a0, emissive: color, emissiveIntensity: 3.5 })); bulb.position.y = shade === 'paper' ? 0 : -0.05; g.add(bulb);
  const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, cordTop - y, 6), new THREE.MeshStandardMaterial({ color: 0x111111 })); cord.position.y = (cordTop - y) / 2 + 0.3; g.add(cord);
  const socket = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.04, 0.32, 10), new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.6 })); socket.position.y = 0.16; g.add(socket);   // 灯座：把线和灯泡接上，灯泡不悬空
  const light = new THREE.PointLight(color, intensity, 16, 1.7); light.position.y = -0.15; g.add(light);
  // 光晕
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTexture(), color, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending })); halo.scale.set(1.6, 1.6, 1); halo.position.y = -0.05; g.add(halo);
  g.position.set(x, y, z); scene.add(g); return g;
}
function haloTexture() { return memo('halo', () => { const [c, g] = cv(128, 128); const gr = g.createRadialGradient(64, 64, 4, 64, 64, 64); gr.addColorStop(0, 'rgba(255,255,255,.9)'); gr.addColorStop(0.3, 'rgba(255,240,200,.35)'); gr.addColorStop(1, 'rgba(255,220,160,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return tex(c); }); }

/** 盆栽：花盆 + 一丛叶片贴图（双面平面），不是绿球 */
export function plant({ x = -5, z = -5.5, scale = 1, leaves = 14, potColor = 0xd9c8a8 } = {}) {
  const g = new THREE.Group();
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.45, 0.9, 24), new THREE.MeshStandardMaterial({ color: potColor, roughness: 0.85, bumpMap: noiseBumpTexture(), bumpScale: 0.01 })); pot.position.y = 0.45; pot.castShadow = true; g.add(pot);
  const soil = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.06, 24), new THREE.MeshStandardMaterial({ color: 0x2a1c12, roughness: 1 })); soil.position.y = 0.9; g.add(soil);
  const lm = new THREE.MeshStandardMaterial({ map: leafTexture(), color: 0xc8e8a0, emissive: 0x2a4a1a, emissiveIntensity: 0.35, roughness: 0.6, side: THREE.DoubleSide, transparent: true, alphaTest: 0.4 });
  for (let i = 0; i < leaves; i++) { const lf = new THREE.Mesh(new THREE.PlaneGeometry(0.55, 1.2), lm); const a = i / leaves * Math.PI * 2 + rnd(-0.2, 0.2), tilt = rnd(0.5, 1.1); lf.position.set(Math.cos(a) * 0.18, 0.95, Math.sin(a) * 0.18); lf.rotation.set(0, -a + Math.PI / 2, 0); lf.rotateX(-tilt); lf.translateY(0.55); lf.castShadow = true; g.add(lf); }
  g.position.set(x, 0, z); g.scale.setScalar(scale); return g;
}

/** 一叠杯子 */
export function glassStack({ x = 4.2, z = -3.6, n = 5, rTop = 0.62, rBot = 0.5, h = 2.4, step = 0.3, material = 'glass' } = {}) {
  const g = new THREE.Group();
  const m = material === 'ceramic' ? new THREE.MeshStandardMaterial({ color: 0xf5f1ea, roughness: 0.35, side: THREE.DoubleSide }) : glassMat(0xf2f8fa, 0.28);
  for (let i = 0; i < n; i++) { const c = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBot, h, 32, 1, true), m); c.position.set(x + rnd(-0.01, 0.01), h / 2 + i * step, z + rnd(-0.01, 0.01)); c.castShadow = material === 'ceramic'; g.add(c); }
  return g;
}

/** 水果碟：柠檬/橙子/青柠（果皮贴图 + 毛孔凹凸） */
export function citrusDish({ x = -3.2, z = 1.6, kinds = ['lemon', 'lemon', 'lime', 'orange'], plateColor = 0x2b3a46 } = {}) {
  const dish = new THREE.Group();
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 0.85, 0.16, 48), new THREE.MeshStandardMaterial({ color: plateColor, roughness: 0.3 })); plate.castShadow = true; plate.receiveShadow = true; dish.add(plate);
  const geo = new THREE.SphereGeometry(0.28, 32, 24); { const p = geo.attributes.position; for (let i = 0; i < p.count; i++) { const y = p.getY(i); p.setY(i, y * (1 + 0.35 * Math.pow(Math.abs(y) / 0.28, 4))); } geo.computeVertexNormals(); }
  kinds.forEach((k, i) => { const mat = new THREE.MeshStandardMaterial({ map: citrusSkinTexture(k === 'orange' ? 'lemon' : k), color: k === 'orange' ? 0xff9a2a : 0xffffff, bumpMap: citrusBumpTexture(), bumpScale: 0.012, roughness: 0.5 }); const f = new THREE.Mesh(k === 'orange' ? new THREE.SphereGeometry(0.34, 28, 20) : geo, mat); const a = i * 1.7; f.position.set(Math.cos(a) * 0.35, 0.36 + (i === 3 ? 0.28 : 0), Math.sin(a) * 0.35); f.rotation.set(rnd(0, 0.6), a, Math.PI / 2 - 0.3 + rnd(0, 0.6)); f.castShadow = true; dish.add(f); });
  dish.position.set(x, 0, z); return dish;
}

/** 台面上的小东西：杯垫、餐巾、吸管筒 */
export function coasters({ x = -3.4, z = 1.2, n = 3, color = 0x8a6a4a } = {}) { const g = new THREE.Group(); for (let i = 0; i < n; i++) { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, 0.05, 32), new THREE.MeshStandardMaterial({ color, roughness: 0.95 })); c.position.set(x + i * 0.12, 0.03 + i * 0.05, z + i * 0.08); c.receiveShadow = true; c.castShadow = true; g.add(c); } return g; }
export function napkin({ x = 3.2, z = 1.2, color = 0x1f3a5a, rot = -0.3 } = {}) { const m = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.06, 1.3), new THREE.MeshStandardMaterial({ color, roughness: 0.95, bumpMap: noiseBumpTexture(), bumpScale: 0.01 })); m.position.set(x, 0.03, z); m.rotation.y = rot; m.receiveShadow = true; return m; }
export function strawCup({ x = 4.6, z = 1.0, color = 0xd94a3a, n = 9 } = {}) { const g = new THREE.Group(); const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.3, 1.1, 24, 1, true), new THREE.MeshStandardMaterial({ color: 0xd8dde2, roughness: 0.25, metalness: 0.9, side: THREE.DoubleSide })); cup.position.y = 0.55; g.add(cup); for (let i = 0; i < n; i++) { const s = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 2.2, 8), new THREE.MeshStandardMaterial({ color: i % 3 ? color : 0xffffff, roughness: 0.5 })); const a = i / n * 6.28; s.position.set(Math.cos(a) * 0.16, 1.2, Math.sin(a) * 0.16); s.rotation.set(rnd(-0.12, 0.12), 0, rnd(-0.12, 0.12)); g.add(s); } g.position.set(x, 0, z); return g; }

/** 墙脚的踢脚/后吧台底座：让墙与台面之间有个过渡，不是一块平板直接插进桌子 */
export function backLedge({ z = -9.3, h = 1.0, depth = 0.8, color = 0x2a1f18, tex = null } = {}) { const m = new THREE.Mesh(new THREE.BoxGeometry(40, h, depth), tex ? new THREE.MeshStandardMaterial({ map: tex, roughness: 0.7 }) : new THREE.MeshStandardMaterial({ color, roughness: 0.8 })); m.position.set(0, h / 2, z + depth / 2); m.receiveShadow = true; m.castShadow = true; return m; }

/** 布帘/门帘（居酒屋 noren） */
export function noren({ x = 0, y = 7.2, z = -9.2, w = 3.2, h = 2.4, color = '#1f3a5a', text = '酒' } = {}) {
  const [c, g] = cv(512, 384); g.fillStyle = color; g.fillRect(0, 0, 512, 384); for (let i = 0; i < 3000; i++) { g.fillStyle = `rgba(255,255,255,${rnd(0.01, 0.05).toFixed(3)})`; g.fillRect(Math.random() * 512, Math.random() * 384, rnd(1, 3), rnd(1, 2)); }
  g.fillStyle = 'rgba(255,255,255,.92)'; g.font = 'bold 200px "Hiragino Sans","PingFang SC",serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, 256, 200);
  const t = tex(c); const grp = new THREE.Group(); const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h, 8, 1), new THREE.MeshStandardMaterial({ map: t, roughness: 1, side: THREE.DoubleSide })); const p = m.geometry.attributes.position; for (let i = 0; i < p.count; i++) p.setZ(i, Math.sin(p.getX(i) * 3) * 0.06); m.geometry.computeVertexNormals(); grp.add(m);
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, w + 0.6, 10), new THREE.MeshStandardMaterial({ color: 0x4a3020, roughness: 0.6 })); rod.rotation.z = Math.PI / 2; rod.position.y = h / 2 + 0.05; grp.add(rod);
  grp.position.set(x, y, z); return grp;
}
