import * as THREE from 'three';
import { Cup } from '../../vendor/craft/cup.js';
import { Steam, Bubbles } from '../../vendor/craft/fx.js';
import { sfx } from '../../vendor/craft/audio.js';
import { clamp, rangeMiss } from '../../vendor/craft/core.js';
import { noiseBumpTexture, lightWoodTexture } from '../../vendor/craft/textures.js';
import { fruitMesh } from '../../vendor/craft/fruits.js';

/**
 * 糖葫芦摊「冰糖葫芦」：串果（点果子上签）→ 熬糖（按住开火，看糖色，微焦黄时关火）→ 蘸糖（按住把签放进糖里，左右拖着滚，薄薄一层）→ 出摊（放到板上晾，糖衣发亮）。
 * 隐形标准（熬糖 150℃ 左右糖液微黄、小泡；薄裹一层最脆）：果数合订单、糖色在窗口、糖衣薄而匀、有糖翅。
 */
const FRUITS = {
  haw:        { name: '山楂', css: '#c8241e', count: [5, 6], r: 0.17 },
  strawberry: { name: '草莓', css: '#e2506a', count: [4, 5], r: 0.19 },
  tomato:     { name: '圣女果', css: '#d8301c', count: [5, 6], r: 0.16 },
};
const ORDERS = [
  { fruit: 'haw', line: '「来一串山楂的，糖别熬糊。」' },
  { fruit: 'strawberry', line: '「草莓的，糖薄一点，脆。」' },
  { fruit: 'tomato', line: '「圣女果，串大一点。」', count: [6, 6] },
];
const SUGAR_WIN = [6.2, 8.4], BURN_AT = 10.5;   // 熬糖：微焦黄的窗口（秒）；再熬就糊
const COAT = [0.72, 1.0], THICK_MAX = 0.55;      // 糖衣：覆盖度 / 厚度上限
const WOK = [0, 0.05, -2.6], STICK_LEN = 2.6;

export default {
  id: 'tanghulu', palette: { ink: '#2a1a18', paper: '#fff3e6', deep: '#6a1a14', accent: '#c8241e', gold: '#e0a83a', ground: '#141018' }, title: '糖葫芦摊', subtitle: 'Tanghulu', unit: '串', maker: '夜市里熬了二十年糖的那位', scene: { mood: 'night', wood: 'dark', wall: 'night', dressing: [{ kind: 'backLedge', color: 0x2a2024 }, { kind: 'lantern', x: -3.2, y: 6.4, z: -6.0 }, { kind: 'lantern', x: 3.4, y: 6.8, z: -7.0, s: 0.9 }, { kind: 'stringLights' }, { kind: 'sign', title: '冰糖葫芦', sub: '老北京 · 现蘸', hex: '#c8241e', x: -3.6, y: 5.2 }, { kind: 'awning', c1: '#c8241e', c2: '#f4f0e6' }, { kind: 'plant', x: -5.8, z: -5.8 }, { kind: 'napkin', x: 3.2, z: 1.6, color: 0x8a2a1e }] }, cardTitle: '客人要', perfectText: '糖衣薄脆亮', againText: '再来一串 →',
  phases: ['skewer', 'sugar', 'coat', 'serve'], phaseNames: { skewer: '串果', sugar: '熬糖', coat: '蘸糖', serve: '出摊' },
  views: { skewer: { pos: [0.6, 3.0, 3.6], tgt: [0, 0.8, 0.2] }, sugar: { pos: [1.2, 3.6, 0.4], tgt: [0, 0.6, -2.6] }, coat: { pos: [0.4, 3.4, 0.6], tgt: [0, 0.9, -2.5] }, reveal0: { pos: [1.2, 1.5, 3.4], tgt: [0, 0.8, 0.4] }, reveal1: { pos: [-0.8, 2.6, 3.0], tgt: [0, 0.9, 0.4] }, serve: { pos: [0, 3.2, 5.8], tgt: [0, 0.6, 0.2] } },

  init(core) {
    const sc = core.w.scene, st = this.st = {};
    // 案台：石板（晾糖葫芦）
    const slab = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.12, 2.0), new THREE.MeshPhysicalMaterial({ color: 0xd8d4cc, roughness: 0.25, clearcoat: 0.6, bumpMap: noiseBumpTexture(), bumpScale: 0.01 })); slab.position.set(0, 0.06, 0.4); slab.receiveShadow = true; slab.castShadow = true; sc.add(slab); st.slab = slab;
    // 果盆
    const bowl = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.6, 0.5, 32, 1, true), new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xc9a86a, roughness: 0.9, side: THREE.DoubleSide })); bowl.position.set(-1.9, 0.25, 0.6); bowl.castShadow = true; sc.add(bowl); const bowlF = new THREE.Mesh(new THREE.CircleGeometry(0.6, 32), bowl.material); bowlF.rotation.x = -Math.PI / 2; bowlF.position.set(-1.9, 0.02, 0.6); sc.add(bowlF); st.bowlPos = new THREE.Vector3(-1.9, 0.5, 0.6);
    st.bowlFruits = new THREE.Group(); st.bowlFruits.userData.loose = true; sc.add(st.bowlFruits);
    // 签子 + 果子
    st.stick = new THREE.Group(); const stickM = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.02, STICK_LEN, 8), new THREE.MeshStandardMaterial({ color: 0xd8c090, roughness: 0.9 })); stickM.castShadow = true; st.stick.add(stickM); st.fruitG = new THREE.Group(); st.stick.add(st.fruitG); sc.add(st.stick);
    // 糖锅：铁锅（球面）+ 糖液
    const wokProf = { inner: [[0.08, 0], [0.6, 0.12], [0.95, 0.38], [1.15, 0.7]], outer: [[0, -0.02], [0.4, -0.02], [0.62, 0.1], [0.98, 0.36], [1.2, 0.72], [1.15, 0.7], [0.95, 0.38], [0.6, 0.12], [0.08, 0], [0, 0]] };
    st.wok = new Cup(sc, { ...wokProf, material: 'ceramic', pos: WOK, tint: 0x2a2a2c, liquidOpacity: 0.72 }); st.wok.shell.material.roughness = 0.45; st.wok.shell.material.clearcoat = 0.3; st.wok.shell.material.metalness = 0.6; st.wok.liqMat.roughness = 0.03; st.wok.liqMat.envMapIntensity = 1.3; st.wok.liqMat.clearcoat = 1;
    const wokHandle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.06, 1.0, 12), new THREE.MeshStandardMaterial({ color: 0x3a2a1c, roughness: 0.8 })); wokHandle.rotation.z = 1.2; wokHandle.position.set(1.6, 0.85, 0); st.wok.g.add(wokHandle);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.06, 10, 40), new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.7, metalness: 0.5 })); ring.rotation.x = Math.PI / 2; ring.position.set(WOK[0], 0.05, WOK[2]); sc.add(ring);
    st.flame = new THREE.PointLight(0xff8a30, 0, 3.5, 2); st.flame.position.set(WOK[0], 0.2, WOK[2]); sc.add(st.flame);
    st.flameM = new THREE.Mesh(new THREE.ConeGeometry(0.5, 0.5, 16, 1, true), new THREE.MeshBasicMaterial({ color: 0xff9a40, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false })); st.flameM.position.set(WOK[0], 0.2, WOK[2]); st.flameM.renderOrder = 30; sc.add(st.flameM);
    st.bubbles = new Bubbles(sc, 40); st.steam = new Steam(sc, 40);
    // 糖翅：晾的时候底下拖出的一片薄糖
    st.wing = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.9), new THREE.MeshPhysicalMaterial({ color: 0xe8b860, roughness: 0.05, transparent: true, opacity: 0.0, clearcoat: 1, transmission: 0.0, side: THREE.DoubleSide, depthWrite: false })); st.wing.rotation.x = -Math.PI / 2; st.wing.visible = false; st.wing.renderOrder = 26; sc.add(st.wing);
    this._resetState();
  },
  _fruitMesh(kind, r) {
    const st = this.st; const F = FRUITS[kind]; const g = new THREE.Group();
    if (kind === 'strawberry') { const inst = fruitMesh('strawberry', 1, r / 0.15); inst.count = 1; inst.setMatrixAt(0, new THREE.Matrix4()); inst.instanceMatrix.needsUpdate = true; inst.frustumCulled = false; g.add(inst); }
    else {
      const tex = (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d'); x.fillStyle = F.css; x.fillRect(0, 0, 128, 128); for (let i = 0; i < 500; i++) { x.fillStyle = `rgba(${kind === 'haw' ? '255,225,190' : '255,210,170'},${(Math.random() * (kind === 'haw' ? 0.28 : 0.12)).toFixed(2)})`; x.beginPath(); x.arc(Math.random() * 128, Math.random() * 128, 0.8 + Math.random() * 1.6, 0, 6.28); x.fill(); } for (let i = 0; i < 60; i++) { x.fillStyle = `rgba(90,10,10,${(Math.random() * 0.25).toFixed(2)})`; x.fillRect(Math.random() * 128, Math.random() * 128, 2, 2); } const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; })();
      const geo = new THREE.SphereGeometry(r, 28, 20); const P = geo.attributes.position; const v = new THREE.Vector3();
      for (let i = 0; i < P.count; i++) { v.fromBufferAttribute(P, i); const n = v.clone().normalize(); if (kind === 'haw') { const k = Math.max(0, n.y - 0.72) / 0.28; v.sub(n.clone().multiplyScalar(r * 0.22 * k * k)); v.y *= 0.9; } else { v.y *= 1.12; const k = Math.max(0, n.y - 0.85) / 0.15; v.sub(n.clone().multiplyScalar(r * 0.08 * k)); } P.setXYZ(i, v.x, v.y, v.z); }   // 山楂顶上有个窝，圣女果略长、蒂处微凹
      geo.computeVertexNormals();
      const body = new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({ map: tex, roughness: kind === 'haw' ? 0.42 : 0.18, clearcoat: kind === 'haw' ? 0.35 : 0.95, clearcoatRoughness: kind === 'haw' ? 0.3 : 0.08, bumpMap: noiseBumpTexture(), bumpScale: kind === 'haw' ? 0.006 : 0.002 })); body.castShadow = true; g.add(body);
      if (kind === 'haw') { const calyx = new THREE.Mesh(new THREE.CircleGeometry(r * 0.16, 5), new THREE.MeshStandardMaterial({ color: 0x3a1a10, roughness: 0.9, side: THREE.DoubleSide })); calyx.rotation.x = -Math.PI / 2; calyx.position.y = r * 0.74; g.add(calyx); }
      else { const green = new THREE.MeshStandardMaterial({ color: 0x5f9a3a, roughness: 0.7, side: THREE.DoubleSide }); const stem = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.06, r * 0.08, r * 0.35, 6), green); stem.position.y = r * 1.12 + r * 0.12; g.add(stem); for (let i = 0; i < 5; i++) { const leaf = new THREE.Mesh(new THREE.PlaneGeometry(r * 0.16, r * 0.42), green); const a = i / 5 * Math.PI * 2; leaf.position.set(Math.cos(a) * r * 0.2, r * 1.08, Math.sin(a) * r * 0.2); leaf.rotation.set(-0.9, -a + Math.PI / 2, 0, 'YXZ'); g.add(leaf); } }
      g.rotation.z = Math.PI / 2 * (0.6 + Math.random() * 0.6);   // 穿在签上：蒂朝侧面
    }
    // 糖衣壳：比果子大一圈的半透明琥珀壳，蘸得越多越实
    const shell = new THREE.Mesh(new THREE.SphereGeometry(r * 1.08, 22, 16), new THREE.MeshPhysicalMaterial({ color: 0xffdca0, roughness: 0.02, metalness: 0, transparent: true, opacity: 0, clearcoat: 1, clearcoatRoughness: 0.02, envMapIntensity: 2.6, depthWrite: false })); shell.renderOrder = 25; g.add(shell); g.userData.shell = shell; g.userData.coat = 0; g.userData.r = r;
    return g;
  },
  _resetState() {
    const st = this.st; st.n = 0; st.heat = 0; st.sugarT = 0; st.cooking = false; st.stage = 0; st.burnt = false; st.dipping = false; st.dipT = 0; st.roll = 0; st.dragging = false; st.lastX = null; st.coatT = 0; st.cooled = 0; st.thick = 0;
    while (st.fruitG.children.length) st.fruitG.remove(st.fruitG.children[0]); while (st.bowlFruits.children.length) st.bowlFruits.remove(st.bowlFruits.children[0]);
    st.wok.reset(); st.wok.add([0.94, 0.93, 0.88], 0.55); st.wok.mix(1); st.flame.intensity = 0; st.flameM.material.opacity = 0; st.bubbles.intensity = 0; st.steam.intensity = 0; st.wing.visible = false; st.wing.material.opacity = 0;
    st.stick.position.set(0.3, 1.28, 0.5); st.stick.rotation.set(0, 0, 0.35);
  },
  newTask(core, prev) {
    const st = this.st; const pool = ORDERS.filter((o) => o.line !== prev); const o = pool[(Math.random() * pool.length) | 0]; st.order = o; st.kind = o.fruit; st.count = o.count || FRUITS[o.fruit].count;
    // 果盆里摆 9 颗
    for (let i = 0; i < 9; i++) { const f = this._fruitMesh(st.kind, FRUITS[st.kind].r); const a = i * 0.8; f.position.set(st.bowlPos.x + Math.cos(a) * 0.32 * (i % 3), st.bowlPos.y - 0.2 + (i % 2) * 0.16, st.bowlPos.z + Math.sin(a) * 0.32 * (i % 3)); st.bowlFruits.add(f); }
    return { name: FRUITS[st.kind].name + '糖葫芦', line: o.line, chips: core.chip(FRUITS[st.kind].css, FRUITS[st.kind].name) + core.chip('#e8b860', '冰糖'), foot1: '', foot2: '' };
  },
  enter(core, p) {
    const st = this.st;
    if (p === 'skewer') { core.ui.hint('一串几颗，看客人'); core.ui.next('串好了 →', true); core.ui.coach('tap', '点果子上签'); st.stick.position.set(0.3, 1.28, 0.5); st.stick.rotation.set(0, 0, 0.35); }
    if (p === 'sugar') { core.ui.hint('糖色微焦黄就关火，熬糊就苦'); core.ui.next('糖好了 →', true); core.ui.coach('hold', '按住开火熬糖'); core.ui.hold('按住\n开火', () => { st.cooking = true; }, () => { st.cooking = false; }); st.stick.position.set(1.9, 1.28, 1.0); st.stick.rotation.set(0, 0, 0.35); }
    if (p === 'coat') { core.ui.hint('薄薄裹一层，滚匀'); core.ui.next('蘸好了 →', true); core.ui.coach('dragx', '按住蘸 · 左右滚'); core.ui.hold(null); st.cooking = false; st.stick.position.set(WOK[0], WOK[1] + 1.35, WOK[2] + 0.1); st.stick.rotation.set(0, 0, Math.PI / 2); st.dipK = 0; }
    if (p === 'reveal') { st.stick.position.set(0.2, 0.06 + 0.12 + FRUITS[st.kind].r * 1.15, 0.4); st.stick.rotation.set(0, 0.25, Math.PI / 2); st.cooled = 0; }
  },
  canNext(core, p) { const st = this.st; if (p === 'skewer') return st.n >= 3; if (p === 'sugar') return st.sugarT > 3; if (p === 'coat') return st.coatT > 0.3; return true; },
  leave(core, p) { const st = this.st; if (p === 'sugar') { st.cooking = false; st.doneStage = st.sugarT; } if (p === 'coat') { st.dipping = false; } },

  down(core, e) {
    const st = this.st, p = core.phase;
    if (p === 'skewer') this._skewer(core, e);
    if (p === 'coat') { st.dipping = true; st.dragging = true; st.lastX = e.clientX; }
  },
  move(core, e) { const st = this.st; if (core.phase === 'coat' && st.dragging) { const r = core.dom.getBoundingClientRect(); const dx = (e.clientX - st.lastX) / r.width; st.lastX = e.clientX; st.roll += Math.abs(dx) * 6; st.stick.rotation.x += dx * 9; } },
  up() { const st = this.st; st.dipping = false; st.dragging = false; },

  _skewer(core, e) {
    const st = this.st; if (st.n >= 6) { core.ui.hint('签子满了'); return; }
    const hit = core.screenToPlane(e, 0.4); if (!hit || Math.hypot(hit.x - st.bowlPos.x, hit.z - st.bowlPos.z) > 1.1) { core.ui.hint('点果盆里的果子'); return; }
    const r = FRUITS[st.kind].r; const f = this._fruitMesh(st.kind, r); const i = st.n; f.position.set(0, -STICK_LEN / 2 + 0.45 + i * (r * 2.0), 0); f.rotation.set(Math.random() * 0.4, Math.random() * 6.28, 0); st.fruitG.add(f); st.n++;
    if (st.bowlFruits.children.length) st.bowlFruits.remove(st.bowlFruits.children[st.bowlFruits.children.length - 1]);
    sfx.place(); core.ui.nextEnabled(st.n >= 3); if (st.n === 5) core.ui.praise('五颗一串');
  },
  _wokFloor(d) { return WOK[1] + (d < 0.6 ? 0.12 * (d / 0.6) : d < 0.95 ? 0.12 + 0.26 * ((d - 0.6) / 0.35) : 0.38 + 0.32 * Math.min(1, (d - 0.95) / 0.2)); },
  _syrupColor(t) {   // 熬糖：清 → 淡黄 → 微焦黄 → 深琥珀 → 糊
    const k = Math.min(1, t / BURN_AT); const stops = [[0.94, 0.93, 0.88], [0.95, 0.88, 0.62], [0.90, 0.72, 0.36], [0.62, 0.36, 0.12], [0.22, 0.10, 0.04]]; const x = k * 4, i = Math.min(3, Math.floor(x)), f = x - i; return stops[i].map((c, j) => c + (stops[i + 1][j] - c) * f);
  },
  update(core, dt) {
    const st = this.st, p = core.phase;
    if (p === 'sugar' && st.cooking && !st.burnt) { st.sugarT += dt; if (st.sugarT >= BURN_AT) { st.burnt = true; core.ui.hint('糖熬糊了'); sfx.bad(); } else { const t = st.sugarT; core.ui.hint(t < 2 ? '糖化开了，还清着' : t < 4.5 ? '起小泡了' : t < SUGAR_WIN[0] ? '泡密了，开始发黄' : t < SUGAR_WIN[1] ? '微焦黄 —— 差不多了' : '深琥珀，再熬就糊'); } core.ui.nextEnabled(st.sugarT > 3); }   // 火候的实时状态词（描述，不是指令）
    st.heat += (((p === 'sugar' && st.cooking) ? 1 : 0) - st.heat) * Math.min(1, dt * 5);
    const col = this._syrupColor(st.sugarT); if (st.wok.layers.length) { st.wok.layers[0].rgb = col; st.wok.dirty = true; }
    st.flame.intensity = st.heat * 7; st.flameM.material.opacity = st.heat * 0.55; st.flameM.scale.setScalar(0.8 + 0.3 * Math.sin(performance.now() / 60)); st.flameM.position.y = 0.05 + 0.2 * st.heat;
    const bubK = st.heat * (st.sugarT < 3 ? 1.2 : st.sugarT < 7 ? 0.7 : 0.35);   // 大泡 → 小泡
    st.bubbles.set(WOK[0], WOK[2], WOK[1] + 0.15, st.wok.levelY - 0.01, 0.55, bubK * 1.6); st.bubbles.update(dt); st.steam.set(WOK[0], st.wok.levelY + 0.05, WOK[2], 0.6, st.heat * 0.6 + (st.sugarT > 8 && st.burnt ? 1.2 : 0)); st.steam.update(dt);
    if (p === 'coat') {
      st.dipK += ((st.dipping ? 1 : 0) - st.dipK) * Math.min(1, dt * 7);
      const surf = st.wok.levelY; const r = FRUITS[st.kind].r;
      // 签横着：果子并排；蘸时整串沉到糖里（最深处果子底不许碰锅底斜面），滚动靠 rotation.x
      let floorMax = 0; for (const f of st.fruitG.children) { const d = Math.hypot(f.position.y * Math.cos(0) + 0.05, 0.1); const dd = Math.abs(f.position.y) + 0.05; floorMax = Math.max(floorMax, this._wokFloor(dd)); }
      const deep = Math.max(surf - r * 0.85, floorMax + r * 0.15 + 0.03); const yFull = deep + r * 1.1; const yUp = surf + r * 1.12 + 0.55;
      st.stick.position.set(WOK[0] + 0.05, yUp + (yFull - yUp) * st.dipK, WOK[2] + 0.1);
      if (st.dipping && st.dipK > 0.85) { st.coatT += dt; for (const f of st.fruitG.children) { const u = f.userData; u.coat = Math.min(1.4, u.coat + dt * 0.55); u.shell.material.opacity = Math.min(0.38, u.coat * 0.34); const bodyM = f.children[0].material; if (bodyM) { bodyM.roughness = Math.max(0.04, bodyM.roughness - dt * 0.5); bodyM.clearcoat = Math.min(1, bodyM.clearcoat + dt * 1.2); bodyM.clearcoatRoughness = Math.max(0.03, bodyM.clearcoatRoughness - dt * 0.4); bodyM.envMapIntensity = Math.min(2.2, (bodyM.envMapIntensity || 1) + dt * 1.5); } } if (Math.random() < dt * 5) sfx.drip(); }
      st.thick = Math.max(...st.fruitG.children.map((f) => f.userData.coat), 0);
      core.ui.nextEnabled(st.coatT > 0.3);
    }
    if (p === 'reveal' || p === 'score') {   // 晾：糖衣变硬发亮，底下拖出糖翅
      st.cooled = Math.min(1, st.cooled + dt * 0.6);
      for (const f of st.fruitG.children) { const u = f.userData; u.shell.material.roughness = 0.12 - 0.1 * st.cooled; u.shell.material.envMapIntensity = 1.4 + 1.2 * st.cooled; }
      if (st.thick > 0.3) { st.wing.visible = true; st.wing.material.opacity = 0.55 * st.cooled; const last = st.fruitG.children[0]; const wp = last ? last.getWorldPosition(new THREE.Vector3()) : new THREE.Vector3(0.2, 0.2, 0.4); st.wing.position.set(wp.x + 0.25, 0.125, wp.z + 0.05); st.wing.scale.set(Math.min(1.4, st.thick), 1, 1); }
    }
    st.wok.update(dt);
  },
  score() {
    const st = this.st, rows = [], tips = []; const F = FRUITS[st.kind];
    const cv = clamp(100 - rangeMiss(st.n, st.count) * 24); rows.push(['串', cv, 0.18]); if (cv < 100) tips.push(st.n < st.count[0] ? `一串要 ${st.count[0]}–${st.count[1]} 颗${F.name}，你串了 ${st.n} 颗。` : `串太多了（${st.n} 颗）。`);
    let sv = clamp(100 - rangeMiss(st.doneStage ?? st.sugarT, SUGAR_WIN) * 26); if (st.burnt) sv = Math.min(sv, 15); rows.push(['糖色', sv, 0.32]); if (sv < 90) tips.push(st.burnt ? '糖熬糊了，又苦又黑。' : (st.doneStage ?? 0) < SUGAR_WIN[0] ? '糖没熬到位，挂不住、发黏不脆。' : '糖熬过了，颜色太深发苦。');
    const coats = st.fruitG.children.map((f) => f.userData.coat); const cov = coats.length ? coats.filter((c) => c >= COAT[0]).length / coats.length : 0; const thick = Math.max(...coats, 0);
    let wv = clamp(cov * 100 - Math.max(0, thick - 1.0) * 120 - (st.roll < 2.5 ? 25 : 0)); rows.push(['糖衣', wv, 0.35]); if (wv < 90) tips.push(cov < 1 ? '有几颗没裹到糖。' : thick > 1.0 ? '蘸太久，糖衣太厚咬不动。' : '没滚匀，一面厚一面薄。');
    const wingV = st.thick > 0.3 && st.thick <= 1.0 && !st.burnt ? 100 : 60; rows.push(['糖翅', wingV, 0.15]); if (wingV < 100) tips.push('晾的时候没拖出漂亮的糖翅。');
    return { rows, tips };
  },
  strip(core, g, c) { const F = FRUITS[this.st.kind]; g.fillStyle = '#d8c090'; g.fillRect(12, 10, 4, 100); for (let i = 0; i < 5; i++) { g.fillStyle = F.css; g.beginPath(); g.arc(14, 24 + i * 18, 8, 0, 6.28); g.fill(); g.fillStyle = 'rgba(255,220,140,.55)'; g.beginPath(); g.arc(14, 24 + i * 18, 9.5, 0, 6.28); g.fill(); } },
  celebrateAt() { return [0.2, 0.8, 0.4, 1.0]; },
  reset() { this._resetState(); },
  clipping() {
    const st = this.st, out = [], r = FRUITS[st.kind].r;
    st.stick.updateMatrixWorld(true);
    for (const f of st.fruitG.children) { const wp = f.getWorldPosition(new THREE.Vector3()); const dx = wp.x - WOK[0], dz = wp.z - WOK[2], dd = Math.hypot(dx, dz);
      if (dd < 1.25 && wp.y - r * 1.1 < this._wokFloor(dd) + 0.005) out.push(`果子穿锅底：y=${wp.y.toFixed(2)}`);
      if (wp.y - r * 1.1 < 0.12 - 0.01 && Math.abs(wp.x) < 1.6 && Math.abs(wp.z - 0.4) < 1.0) out.push('果子陷进石板'); }
    const ch = st.fruitG.children; for (let i = 1; i < ch.length; i++) if (ch[i].position.y - ch[i - 1].position.y < r * 1.9) out.push('果子叠在一起');
    return out;
  },
  auto(core, phase, part) {
    const st = this.st, half = part === 'mid';
    if (phase === 'skewer') { const want = half ? 2 : Math.round((st.count[0] + st.count[1]) / 2); let acc = 0; return { step: (dt) => { acc += dt; if (acc > 0.35 && st.n < want && st.n < 6) { acc = 0; const r = FRUITS[st.kind].r; const f = this._fruitMesh(st.kind, r); const i = st.n; f.position.set(0, -STICK_LEN / 2 + 0.45 + i * (r * 2.0), 0); f.rotation.set(Math.random() * 0.4, Math.random() * 6.28, 0); st.fruitG.add(f); st.n++; if (st.bowlFruits.children.length) st.bowlFruits.remove(st.bowlFruits.children[st.bowlFruits.children.length - 1]); sfx.place(); core.ui.nextEnabled(true); } return st.n >= want; } }; }
    if (phase === 'sugar') { const until = half ? SUGAR_WIN[0] * 0.5 : (SUGAR_WIN[0] + SUGAR_WIN[1]) / 2; return { step: () => { st.cooking = st.sugarT < until; return st.sugarT >= until; } }; }
    if (phase === 'coat') { let t = 0; return { step: (dt) => { t += dt; st.dipping = true; st.roll += dt * 2; st.stick.rotation.x += dt * 3; if (half) return t > 0.9; if (st.thick >= 0.86) { st.dipping = false; return true; } return false; } }; }
    return null;
  },
};
