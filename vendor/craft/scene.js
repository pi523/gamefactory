import * as THREE from 'three';
import { barWoodTexture, envTexture, lightWoodTexture, noiseBumpTexture, brickTexture, groutTileTexture, stripeTexture } from './textures.js';
import * as D from './dressing.js';
import { labelTextTexture } from './dressing.js';

/**
 * 场景 = 一家店：饺子馆 dumplinghouse / 拉面馆 noodleshop / 糖葫芦摊 tanghulustall / 煎饼车 jianbingcart / 糖画摊 tanghuastall
 * 写实清单：材质有贴图与凹凸、陈设是可辨认实物（笼屉/汤锅/糖锅/灯笼有光）、墙脚有过渡、远景压暗。
 */
export function buildScene(canvas, G) {
  const SC = {
    dumplinghouse: { bg: 0xc8b49a, fog: [15, 38], exp: 0.9, hemi: [0xffe8c8, 0x6a5040, 0.7],  key: [0xffe0b8, 1.9], fill: [0xdfe8f0, 0.6], rim: [0xffe8c0, 14], back: [0xffe0b0, 9],  wood: 'light', wall: 'plaster' },
    noodleshop:    { bg: 0xcfd6d0, fog: [16, 40], exp: 0.92, hemi: [0xf4f8ff, 0x7a8880, 0.75], key: [0xfff0d8, 1.9], fill: [0xd8e8f0, 0.7], rim: [0xffffff, 12], back: [0xf0f8ff, 8],  wood: 'steel', wall: 'whitetile' },
    tanghulustall: { bg: 0x141018, fog: [11, 28], exp: 1.12, hemi: [0xffd9b0, 0x1a1420, 0.55], key: [0xffe0b8, 2.2], fill: [0x9fb4d8, 0.7], rim: [0xffb870, 30], back: [0xff9a50, 22], wood: 'dark', wall: 'night' },
    jianbingcart:  { bg: 0xc8ced6, fog: [16, 40], exp: 0.9, hemi: [0xffefd8, 0x7a8088, 0.7], key: [0xffe4c0, 1.9], fill: [0xd8e4ff, 0.7], rim: [0xffffff, 12], back: [0xfff0d8, 8],  wood: 'steel', wall: 'street' },
    tanghuastall:  { bg: 0xd6cfc2, fog: [15, 38], exp: 0.95, hemi: [0xfff2dc, 0x8a8070, 0.75], key: [0xffe6c4, 2.0], fill: [0xdde8f0, 0.7], rim: [0xffffff, 10], back: [0xfff0d8, 6],  wood: 'light', wall: 'street' },
  }[typeof G.scene === 'string' ? G.scene : '__none'] || sceneFromSpec(G.scene);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = SC.exp;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  if ('transmissionResolutionScale' in renderer) renderer.transmissionResolutionScale = 0.5;

  const scene = new THREE.Scene(); scene.background = new THREE.Color(SC.bg); scene.fog = new THREE.Fog(SC.bg, SC.fog[0], SC.fog[1]);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 120); camera.position.set(0, 5, 7);
  const pmrem = new THREE.PMREMGenerator(renderer); pmrem.compileEquirectangularShader();
  scene.environment = pmrem.fromEquirectangular(envTexture()).texture; scene.environmentIntensity = SC.bg < 0x303030 ? 0.8 : 1.0; pmrem.dispose();

  scene.add(new THREE.HemisphereLight(...SC.hemi));
  const key = new THREE.DirectionalLight(...SC.key); key.position.set(-5.5, 12, 7); key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = -8; key.shadow.camera.right = 8; key.shadow.camera.top = 8; key.shadow.camera.bottom = -8; key.shadow.camera.near = 1; key.shadow.camera.far = 32; key.shadow.bias = -0.0006; key.shadow.normalBias = 0.03; scene.add(key);
  const fill = new THREE.DirectionalLight(...SC.fill); fill.position.set(8, 4, 5); scene.add(fill);
  const rim = new THREE.SpotLight(SC.rim[0], SC.rim[1], 30, 0.6, 0.55, 1.6); rim.position.set(1, 11, -4); scene.add(rim);
  const back = new THREE.PointLight(SC.back[0], SC.back[1], 12, 1.8); back.position.set(-1.2, 2.2, -3.2); scene.add(back);

  // ---- 台面 ----
  let tableMat;
  if (SC.wood === 'steel') tableMat = new THREE.MeshStandardMaterial({ color: 0xc8ccd0, roughness: 0.32, metalness: 0.88, bumpMap: noiseBumpTexture(), bumpScale: 0.012 });
  else { const t = SC.wood === 'dark' ? barWoodTexture() : lightWoodTexture(); t.repeat.set(2.4, 2.4); tableMat = new THREE.MeshStandardMaterial({ map: t, color: SC.wood === 'dark' ? 0x9a8068 : 0xffffff, roughness: 0.55, metalness: 0.04, bumpMap: noiseBumpTexture(), bumpScale: 0.006 }); }
  const table = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), tableMat); table.rotation.x = -Math.PI / 2; table.position.y = -0.001; table.receiveShadow = true; scene.add(table);

  // ---- 后墙 ----
  const wallMat = {
    plaster: () => new THREE.MeshStandardMaterial({ color: 0xe8dcc4, roughness: 0.98, bumpMap: noiseBumpTexture(), bumpScale: 0.03 }),
    whitetile: () => new THREE.MeshStandardMaterial({ map: groutTileTexture('#f0f2ee', '#a8a8a0'), roughness: 0.3 }),
    night: () => new THREE.MeshStandardMaterial({ map: brickTexture('#3a2a28', '#2a2024'), roughness: 0.95, bumpMap: noiseBumpTexture(), bumpScale: 0.02 }),
    street: () => new THREE.MeshStandardMaterial({ map: brickTexture('#8a8078', '#a8a09a'), roughness: 0.95, bumpMap: noiseBumpTexture(), bumpScale: 0.02 }),
    redwood: () => new THREE.MeshStandardMaterial({ map: barWoodTexture(), color: 0x7a2a22, roughness: 0.75 }),
  }[SC.wall]();
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(40, 20), wallMat); wall.position.set(0, 8, -9.5); wall.receiveShadow = true; scene.add(wall);

  const dressing = new THREE.Group(); dressing.name = 'dressing'; dressing.userData.loose = true; scene.add(dressing);   // 陈设总组是集合，不做组装检验；里面每件道具各自查
  const steel = new THREE.MeshStandardMaterial({ color: 0xcfd4d8, roughness: 0.22, metalness: 0.95 });
  const bamboo = new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xd8c08a, roughness: 0.85 });
  const steamer = (x, z, n = 3, r = 1.1) => { const g = new THREE.Group(); for (let i = 0; i < n; i++) { const ring = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.42, 40, 1, true), bamboo); ring.position.y = 0.21 + i * 0.44; ring.castShadow = true; g.add(ring); const hoop = new THREE.Mesh(new THREE.TorusGeometry(r + 0.01, 0.025, 8, 48), new THREE.MeshStandardMaterial({ color: 0x8a6a3a, roughness: 0.8 })); hoop.rotation.x = Math.PI / 2; hoop.position.y = 0.36 + i * 0.44; g.add(hoop); } const lid = new THREE.Mesh(new THREE.ConeGeometry(r + 0.05, 0.35, 40), bamboo); lid.position.y = n * 0.44 + 0.17; lid.castShadow = true; g.add(lid); g.position.set(x, 0, z); return g; };
  const lantern = (x, y, z, s = 1) => { const g = new THREE.Group(); const body = new THREE.Mesh(new THREE.SphereGeometry(0.7 * s, 24, 16), new THREE.MeshStandardMaterial({ color: 0xd8302a, emissive: 0xff6a30, emissiveIntensity: 0.9, roughness: 0.85 })); body.scale.y = 0.85; g.add(body); for (let i = 0; i < 6; i++) { const rib = new THREE.Mesh(new THREE.TorusGeometry(0.71 * s, 0.012, 6, 40), new THREE.MeshStandardMaterial({ color: 0xc9a24a, roughness: 0.5, metalness: 0.5 })); rib.rotation.y = i / 6 * Math.PI; g.add(rib); } const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.22 * s, 0.26 * s, 0.12, 16), new THREE.MeshStandardMaterial({ color: 0xc9a24a, metalness: 0.6, roughness: 0.4 })); cap.position.y = 0.62 * s; const tassel = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.1, 0.5 * s, 8), new THREE.MeshStandardMaterial({ color: 0xc9a24a, roughness: 0.9 })); tassel.position.y = -0.85 * s; g.add(cap, tassel); const l = new THREE.PointLight(0xff8a40, 8 * s, 8, 1.8); g.add(l); g.position.set(x, y, z); return g; };

  if (G.scene === 'dumplinghouse') {
    // 饺子馆：竹笼屉塔、面粉罐、擀面杖架、菜单黑板、暖灯
    dressing.add(D.backLedge({ z: -9.5, h: 1.0, depth: 0.9, tex: lightWoodTexture() }));
    dressing.add(steamer(-4.8, -4.6, 4, 1.15), steamer(4.9, -5.2, 2, 0.95));
    dressing.add(D.shelf({ w: 14, y: 3.2, z: -8.9, tex: 'light' }));
    [['面粉', 0xf6f1e6, 0xf6f1e6], ['韭菜', 0x3f7a2a, 0x3f7a2a], ['虾仁', 0xf0a080, 0xf0a080], ['香菇', 0x6a4a2a, 0x6a4a2a]].forEach(([nm, col], i) => { const j = D.jar({ r: 0.42, h: 1.2, content: col, count: 80, grain: 0.06, level: 0.7, lid: 0x8a6a4a }); j.position.set(-5 + i * 2.6, 3.27, -8.9); dressing.add(j); const tag = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.38), new THREE.MeshStandardMaterial({ map: labelTextTexture('#c1462f', nm, ''), roughness: 0.9 })); tag.position.set(-5 + i * 2.6, 3.87, -8.46); dressing.add(tag); });
    dressing.add(D.chalkboard({ x: 3.2, y: 5.9, z: -9.3, w: 4.8, h: 2.8, lines: ['手工水饺', '猪肉白菜 · 韭菜鸡蛋', '三鲜 · 牛肉大葱', '一两 6 只'], bg: '#3a2f2a' }));
    dressing.add(D.poster({ x: -4.0, y: 5.9, z: -9.3, w: 2.2, title: '饺子', sub: '现包现煮', bg: '#fff5e6', accent: '#c1462f' }));
    D.pendant(scene, { x: -1.5, y: 7.3, z: -1.6, color: 0xffd8a0, intensity: 16, shade: 'paper' }); D.pendant(scene, { x: 2.4, y: 7.5, z: -1.2, color: 0xffd8a0, intensity: 14, shade: 'paper' });
    const flourBag = new THREE.Mesh(new THREE.BoxGeometry(1.3, 1.9, 0.8), new THREE.MeshStandardMaterial({ map: labelTextTexture('#1f3a5a', '面粉', 'WHEAT FLOUR', '#f6f1e6'), roughness: 0.95 })); flourBag.position.set(4.2, 0.95, -2.6); flourBag.rotation.y = -0.4; flourBag.castShadow = true; dressing.add(flourBag);
    const pins = new THREE.Group(); for (let i = 0; i < 3; i++) { const pin = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 2.2, 14), bamboo); pin.rotation.z = Math.PI / 2; pin.rotation.y = 0.3 + i * 0.15; pin.position.set(-3.6, 0.12 + i * 0.22, 1.4 + i * 0.1); pin.castShadow = true; pins.add(pin); } dressing.add(pins);
    dressing.add(D.napkin({ x: 3.4, z: 1.6, color: 0xd8302a, rot: -0.25 }), D.plant({ x: -5.6, z: -6.2, scale: 1.1, potColor: 0x6a4a34 }));
  } else if (G.scene === 'noodleshop') {
    // 拉面馆：白瓷砖、大汤锅冒汽、面粉案台、辣椒油罐、牌匾
    dressing.add(D.backLedge({ z: -9.5, h: 1.0, depth: 0.9, color: 0x9aa0a0 }));
    // （背景大汤锅跟游戏里的锅重复，去掉——硬性规定 2）
    dressing.add(D.shelf({ w: 14, y: 3.2, z: -8.9, tex: 'light' }));
    [['辣椒油', 0xc8301a], ['蒜苗', 0x3f7a2a], ['香菜', 0x4f8a3a], ['白萝卜', 0xf0f0e6]].forEach(([nm, col], i) => { const j = D.jar({ r: 0.42, h: 1.2, content: col, count: 80, grain: 0.055, level: 0.7, lid: 0xd8dde2 }); j.position.set(-5 + i * 2.6, 3.27, -8.9); dressing.add(j); const tag = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.38), new THREE.MeshStandardMaterial({ map: labelTextTexture('#1f3a5a', nm, ''), roughness: 0.9 })); tag.position.set(-5 + i * 2.6, 3.87, -8.46); dressing.add(tag); });
    dressing.add(D.chalkboard({ x: 3.4, y: 5.9, z: -9.3, w: 4.8, h: 2.8, lines: ['牛肉面', '毛细 · 二细 · 三细', '韭叶 · 大宽', '加肉 加蛋'], bg: '#2a3a3a' }));
    const plaque = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 1.3), new THREE.MeshStandardMaterial({ map: labelTextTexture('#c9a24a', '兰州牛肉面', 'SINCE 1915', '#3a1a10'), roughness: 0.7 })); plaque.position.set(-4.0, 6.6, -9.3); dressing.add(plaque);
    D.pendant(scene, { x: 0.8, y: 7.5, z: -1.6, color: 0xffffff, intensity: 14, shade: 'dome', shadeColor: 0xe8ecf0 });
    dressing.add(D.glassStack({ x: 4.4, z: -3.4, n: 5, rTop: 1.0, rBot: 0.55, h: 0.7, step: 0.24, material: 'ceramic' }), D.napkin({ x: 3.4, z: 1.5, color: 0x1f3a5a, rot: -0.2 }));
    const flourBoard = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.08, 1.8), new THREE.MeshStandardMaterial({ color: 0xf2eee4, roughness: 0.95, bumpMap: noiseBumpTexture(), bumpScale: 0.02 })); flourBoard.position.set(-3.4, 0.04, 1.6); flourBoard.rotation.y = 0.2; flourBoard.receiveShadow = true; dressing.add(flourBoard);
  } else if (G.scene === 'tanghulustall') {
    // 糖葫芦摊：夜市、红灯笼、稻草靶子插满糖葫芦、糖锅、遮阳布
    dressing.add(D.backLedge({ z: -9.5, h: 1.2, depth: 0.9, color: 0x2a2024 }));
    dressing.add(lantern(-3.2, 6.4, -6.0, 1.0), lantern(3.4, 6.8, -7.0, 0.9), lantern(0.2, 7.2, -8.6, 0.7));
    const target = new THREE.Group(); const straw = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.6, 3.4, 24), new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xc8a860, roughness: 0.95, bumpMap: noiseBumpTexture(), bumpScale: 0.03 })); straw.position.y = 1.7; straw.castShadow = true; target.add(straw);
    const haw = new THREE.MeshPhysicalMaterial({ color: 0xc8241e, roughness: 0.2, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 1.4 });
    for (let i = 0; i < 14; i++) { const a = i / 14 * Math.PI * 2, yy = 1.2 + (i % 4) * 0.55; const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.8, 6), new THREE.MeshStandardMaterial({ color: 0xd8c090, roughness: 0.9 })); stick.position.set(Math.cos(a) * 0.9, yy + 0.3, Math.sin(a) * 0.9); stick.rotation.z = -Math.cos(a) * 0.9; stick.rotation.x = Math.sin(a) * 0.9; target.add(stick); for (let k = 0; k < 5; k++) { const b = new THREE.Mesh(new THREE.SphereGeometry(0.15, 14, 10), haw); const t = -0.5 + k * 0.28; b.position.set(Math.cos(a) * (0.9 + Math.sin(0.9) * t * 0), yy + 0.3 + t, Math.sin(a) * 0.9); b.position.add(new THREE.Vector3(Math.cos(a) * t * 0.78, 0, Math.sin(a) * t * 0.78)); target.add(b); } }
    target.position.set(4.4, 0, -4.4); dressing.add(target);
    // 夜市的一串小灯泡：黑线下垂，灯泡自发光，中间两颗真的照亮摊子
    const wire = []; for (let i = 0; i <= 40; i++) { const t = i / 40; wire.push(new THREE.Vector3(-7 + 14 * t, 5.6 - 0.9 * Math.sin(t * Math.PI), -3.0 - 0.6 * Math.sin(t * Math.PI))); }
    const wireM = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(wire), 60, 0.012, 5, false), new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 })); dressing.add(wireM);
    for (let i = 1; i < 12; i++) { const t = i / 12; const pos = new THREE.Vector3(-7 + 14 * t, 5.6 - 0.9 * Math.sin(t * Math.PI) - 0.16, -3.0 - 0.6 * Math.sin(t * Math.PI)); const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.1, 10), new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.6 })); cap.position.copy(pos).add(new THREE.Vector3(0, 0.06, 0)); dressing.add(cap); const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffe0a0, emissive: 0xffc060, emissiveIntensity: 2.6, roughness: 0.3 })); bulb.position.copy(pos); dressing.add(bulb); if (i === 4 || i === 8) { const pl = new THREE.PointLight(0xffc070, 5, 7, 1.8); pl.position.copy(pos); dressing.add(pl); } }
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 1.4), new THREE.MeshStandardMaterial({ map: labelTextTexture('#c8241e', '冰糖葫芦', '老北京 · 现蘸', '#fff5e0'), roughness: 0.8 })); sign.position.set(-3.6, 5.2, -9.3); dressing.add(sign);
    const awning = new THREE.Mesh(new THREE.PlaneGeometry(14, 3.0), new THREE.MeshStandardMaterial({ map: stripeTexture('#c8241e', '#f4f0e6'), roughness: 0.9, side: THREE.DoubleSide })); awning.position.set(0, 8.6, -6.5); awning.rotation.x = 0.5; dressing.add(awning);
    const cart = new THREE.Mesh(new THREE.BoxGeometry(6, 0.9, 2.2), new THREE.MeshStandardMaterial({ map: barWoodTexture(), color: 0x8a6a48, roughness: 0.8 })); cart.position.set(0, -0.46, -4.2); dressing.add(cart);
    const bulb = new THREE.PointLight(0xffc070, 22, 14, 1.7); bulb.position.set(0.5, 6.6, -1.2); scene.add(bulb); const bulbM = new THREE.Mesh(new THREE.SphereGeometry(0.14, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffe0a0, emissive: 0xffc060, emissiveIntensity: 3 })); bulbM.position.copy(bulb.position); dressing.add(bulbM);
    const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 5, 6), new THREE.MeshStandardMaterial({ color: 0x111111 })); cord.position.set(0.5, 9.1, -1.2); dressing.add(cord);
    dressing.add(D.napkin({ x: -3.6, z: 1.6, color: 0xc8241e, rot: 0.3 }));
  } else if (G.scene === 'jianbingcart') {
    // 煎饼车：清晨街边、不锈钢车台、酱料罐、薄脆筐、鸡蛋筐、菜单牌
    dressing.add(D.backLedge({ z: -9.5, h: 1.2, depth: 0.9, color: 0x6a6a68 }));
    const eggs = new THREE.Group(); const tray = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.2, 1.6), new THREE.MeshStandardMaterial({ color: 0xc9b89a, roughness: 0.95 })); tray.position.y = 0.1; eggs.add(tray); const eggM = new THREE.MeshStandardMaterial({ color: 0xf3e2c4, roughness: 0.6, bumpMap: noiseBumpTexture(), bumpScale: 0.005 }); for (let i = 0; i < 12; i++) { const e = new THREE.Mesh(new THREE.SphereGeometry(0.19, 16, 12), eggM); e.scale.y = 1.3; e.position.set(-0.8 + (i % 4) * 0.53, 0.38, -0.5 + Math.floor(i / 4) * 0.5); e.castShadow = true; eggs.add(e); } eggs.position.set(-4.4, 0, -3.6); eggs.rotation.y = 0.2; dressing.add(eggs);
    [['#c8301a', '辣酱', 0xc8301a], ['#6a3a1c', '甜面酱', 0x6a3a1c], ['#3f7a2a', '葱花', 0x3f7a2a], ['#c9a24a', '芝麻', 0xe8d8a0]].forEach(([hex, nm, col], i) => { const j = D.jar({ r: 0.36, h: 0.9, content: col, count: 60, grain: 0.05, level: 0.7, lid: 0xd8dde2 }); j.position.set(2.6 + i * 0.95, 0, -3.4 + (i % 2) * 0.6); dressing.add(j); });
    const basket = new THREE.Group(); const bw = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 0.8, 0.8, 32, 1, true), new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xc9a86a, roughness: 0.9, side: THREE.DoubleSide })); bw.position.y = 0.4; basket.add(bw); for (let i = 0; i < 8; i++) { const c = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.04, 0.7), new THREE.MeshStandardMaterial({ color: 0xe8b860, roughness: 0.6 })); c.position.set((i % 2) * 0.2 - 0.1, 0.45 + i * 0.06, (i % 3) * 0.1 - 0.1); c.rotation.y = i * 0.5; basket.add(c); } basket.position.set(4.6, 0, -5.4); dressing.add(basket);
    dressing.add(D.chalkboard({ x: 2.6, y: 5.6, z: -9.3, w: 4.4, h: 2.4, lines: ['煎饼果子', '加蛋 · 加薄脆', '加肠 · 加生菜', '6 元'], bg: '#2a2a2e' }));
    dressing.add(D.poster({ x: -3.6, y: 5.7, z: -9.3, w: 2.1, title: '早点', sub: '现摊现吃', bg: '#fffaf0', accent: '#e2723a' }));
    D.pendant(scene, { x: 0.6, y: 7.2, z: -1.4, color: 0xfff4e0, intensity: 12, shade: 'cone', shadeColor: 0x3a3a3e });
    const gas = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 1.6, 24), new THREE.MeshStandardMaterial({ color: 0x1f3a5a, roughness: 0.5, metalness: 0.4 })); gas.position.set(-5.6, 0.8, -6.0); gas.castShadow = true; dressing.add(gas);
  } else if (G.scene === 'tanghuastall') {
    // 糖画摊：公园门口，红白条纹遮阳篷、草靶子上插着做好的糖画、树影、小马扎、招牌
    dressing.add(D.backLedge({ z: -9.5, h: 0.9, depth: 0.9, color: 0x8a8480 }));
    const canopy = new THREE.Group(); const cloth = new THREE.Mesh(new THREE.PlaneGeometry(7.5, 3.4, 24, 8), new THREE.MeshStandardMaterial({ map: stripeTexture('#c8241e', '#f6f1e6'), roughness: 0.9, side: THREE.DoubleSide })); const cp = cloth.geometry.attributes.position; for (let i = 0; i < cp.count; i++) cp.setZ(i, Math.sin(cp.getX(i) * 2.6) * 0.06 + Math.sin(cp.getY(i) * 3) * 0.04); cloth.geometry.computeVertexNormals(); cloth.rotation.x = -Math.PI / 2 + 0.28; cloth.position.set(0, 6.4, -3.6); cloth.castShadow = true; canopy.add(cloth);
    for (const sx of [-1, 1]) { const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.07, 6.4, 12), new THREE.MeshStandardMaterial({ color: 0x9a9a98, roughness: 0.4, metalness: 0.8 })); pole.position.set(sx * 3.6, 3.2, -2.2); pole.castShadow = true; canopy.add(pole); }
    dressing.add(canopy);
    // 草靶子 + 已经画好的糖画（插在上面）
    const strawM = new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xc9a85a, roughness: 1, bumpMap: noiseBumpTexture(), bumpScale: 0.04 });
    const target = new THREE.Group(); const bundle = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.55, 1.6, 24), strawM); bundle.position.y = 0.8; bundle.castShadow = true; target.add(bundle); for (let i = 0; i < 3; i++) { const band = new THREE.Mesh(new THREE.TorusGeometry(0.52 + (i === 1 ? 0.03 : 0), 0.03, 8, 32), new THREE.MeshStandardMaterial({ color: 0xc8241e, roughness: 0.7 })); band.rotation.x = Math.PI / 2; band.position.y = 0.3 + i * 0.5; target.add(band); }
    const pieceTex = (draw) => { const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'); g.clearRect(0, 0, 256, 256); g.strokeStyle = '#c97a1e'; g.lineWidth = 9; g.lineCap = 'round'; g.lineJoin = 'round'; g.shadowColor = 'rgba(120,60,0,0.5)'; g.shadowBlur = 4; draw(g); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; };
    const draws = [
      (g) => { g.beginPath(); g.ellipse(120, 128, 78, 40, 0, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.moveTo(196, 118); g.lineTo(236, 86); g.lineTo(226, 128); g.lineTo(236, 170); g.lineTo(196, 138); g.stroke(); g.beginPath(); g.arc(70, 120, 6, 0, 7); g.stroke(); },
      (g) => { g.beginPath(); g.ellipse(128, 128, 12, 50, 0, 0, Math.PI * 2); g.stroke(); for (const sx of [-1, 1]) { g.beginPath(); g.moveTo(128 + sx * 12, 100); g.lineTo(128 + sx * 80, 40); g.lineTo(128 + sx * 110, 110); g.lineTo(128 + sx * 14, 128); g.stroke(); g.beginPath(); g.moveTo(128 + sx * 12, 140); g.lineTo(128 + sx * 80, 180); g.lineTo(128 + sx * 60, 226); g.lineTo(128 + sx * 14, 175); g.stroke(); } },
      (g) => { for (let i = 0; i < 5; i++) { const a = Math.PI / 2 + i * Math.PI * 2 / 5; g.beginPath(); g.arc(128 + Math.cos(a) * 46, 110 - Math.sin(a) * 46, 34, 0, 7); g.stroke(); } g.beginPath(); g.moveTo(128, 150); g.quadraticCurveTo(150, 200, 170, 240); g.stroke(); },
    ];
    draws.forEach((d, i) => { const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.014, 1.7, 8), new THREE.MeshStandardMaterial({ color: 0xd8c090, roughness: 0.9 })); const a = -0.5 + i * 0.5; stick.position.set(Math.sin(a) * 0.36, 1.9, Math.cos(a) * 0.36); stick.rotation.z = (i - 1) * 0.16; target.add(stick); const pic = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1), new THREE.MeshPhysicalMaterial({ map: pieceTex(d), transparent: true, roughness: 0.1, clearcoat: 1, side: THREE.DoubleSide, alphaTest: 0.2 })); pic.position.set(stick.position.x, 2.75 + Math.abs(i - 1) * 0.1, stick.position.z + 0.02); pic.rotation.z = stick.rotation.z; pic.rotation.y = (i - 1) * 0.35; target.add(pic); });
    target.position.set(-3.6, 0, -2.6); dressing.add(target);
    dressing.add(D.plant({ x: 5.2, z: -6.4, scale: 1.9, leaves: 22, potColor: 0x7a6a5a }), D.plant({ x: -6.2, z: -7.2, scale: 1.6, leaves: 18, potColor: 0x7a6a5a }));
    const sign = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 1.3), new THREE.MeshStandardMaterial({ map: labelTextTexture('#c8241e', '糖画', '转一把 · 画一幅', '#fff3e0'), roughness: 0.7 })); sign.position.set(0, 4.6, -3.9); sign.rotation.x = 0.1; dressing.add(sign);
    const stool = new THREE.Group(); const seat = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.06, 0.6), new THREE.MeshStandardMaterial({ map: lightWoodTexture(), color: 0xb08a5a, roughness: 0.8 })); seat.position.y = 0.72; stool.add(seat); for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.72, 8), seat.material); leg.position.set(sx * 0.4, 0.36, sz * 0.25); leg.rotation.z = sx * 0.12; stool.add(leg); } stool.position.set(3.9, 0, 1.2); stool.traverse((o) => { if (o.isMesh) o.castShadow = true; }); dressing.add(stool);
    dressing.add(D.chalkboard({ x: 3.0, y: 5.4, z: -9.3, w: 4.2, h: 2.4, lines: ['糖画', '龙 · 凤 · 鱼 · 兔', '转到啥画啥', '10 元'], bg: '#2a2e2a' }));
    D.pendant(scene, { x: -0.8, y: 6.0, z: -1.2, color: 0xfff0d8, intensity: 6, shade: 'cone', shadeColor: 0x3a3a3e, cordTop: 6.6 });
  }

  if (typeof G.scene === 'object' && G.scene) {
    // 通用陈设（模块自己声明一个清单，每件都是可辨认实物；背景克制，不放跟主体重复的东西）
    const S = G.scene; const items = S.dressing || [];
    const K = {
      backLedge: (o) => D.backLedge({ z: -9.5, h: 1.0, depth: 0.9, color: o.color ?? 0x6a5a48, tex: o.tex === 'light' ? lightWoodTexture() : o.tex === 'bar' ? barWoodTexture() : null }),
      shelf: (o) => D.shelf({ w: o.w ?? 14, y: o.y ?? 3.2, z: -8.9, tex: o.tex ?? 'light', led: o.led ?? null }),
      jar: (o) => { const j = D.jar({ r: o.r ?? 0.4, h: o.h ?? 1.1, content: o.content ?? 0x4a2a14, count: o.count ?? 80, grain: 0.05, level: 0.72, lid: o.lid ?? 0xd8dde2 }); j.position.set(o.x ?? 0, o.y ?? 0, o.z ?? -3.4); if (o.label) { const tag = new THREE.Mesh(new THREE.PlaneGeometry(0.66, 0.4), new THREE.MeshStandardMaterial({ map: labelTextTexture(o.hex || '#9a3a2a', o.label, ''), roughness: 0.9 })); tag.position.set(0, (o.h ?? 1.1) * 0.55, (o.r ?? 0.4) + 0.02); j.add(tag); } return j; },
      chalkboard: (o) => D.chalkboard({ x: o.x ?? 3.0, y: o.y ?? 5.6, z: -9.3, w: o.w ?? 4.4, h: o.h ?? 2.5, lines: o.lines || ['MENU'], bg: o.bg || '#24302a' }),
      poster: (o) => D.poster({ x: o.x ?? -3.6, y: o.y ?? 5.7, z: -9.3, w: o.w ?? 2.1, title: o.title || '', sub: o.sub || '', bg: o.bg, fg: o.fg, accent: o.accent }),
      sign: (o) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(o.w ?? 3.4, o.h ?? 1.3), new THREE.MeshStandardMaterial({ map: labelTextTexture(o.hex || '#c9a24a', o.title || '', o.sub || '', o.paper || '#3a1a10'), roughness: 0.7 })); m.position.set(o.x ?? -3.6, o.y ?? 6.6, o.z ?? -9.3); return m; },
      plant: (o) => D.plant({ x: o.x ?? -5.5, z: o.z ?? -5.8, scale: o.scale ?? 1.4, leaves: o.leaves ?? 18, potColor: o.potColor ?? 0x7a6a5a }),
      napkin: (o) => D.napkin({ x: o.x ?? 3.2, z: o.z ?? 1.4, color: o.color ?? 0x1f3a5a, rot: o.rot ?? -0.25 }),
      glassStack: (o) => D.glassStack({ x: o.x ?? 4.4, z: o.z ?? -3.4, n: o.n ?? 5, rTop: o.rTop ?? 1.0, rBot: o.rBot ?? 0.55, h: o.h ?? 0.7, step: o.step ?? 0.24, material: o.material ?? 'ceramic' }),
      noren: (o) => D.noren({ x: o.x ?? 0, y: o.y ?? 7.2, z: -9.2, w: o.w ?? 3.2, h: o.h ?? 2.4, color: o.color || '#1f3a5a', text: o.text || '' }),
      lantern: (o) => lantern(o.x ?? -3.2, o.y ?? 6.4, o.z ?? -6.0, o.s ?? 1.0),
      steamer: (o) => steamer(o.x ?? -4.8, o.z ?? -4.6, o.n ?? 3, o.r ?? 1.1),
      pendant: (o) => { D.pendant(scene, { x: o.x ?? 0.8, y: o.y ?? 7.4, z: o.z ?? -1.6, color: o.color ?? 0xfff0d8, intensity: o.intensity ?? 12, shade: o.shade || 'cone', shadeColor: o.shadeColor ?? 0x3a3a3e }); return null; },
      awning: (o) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(o.w ?? 14, o.h ?? 3.0), new THREE.MeshStandardMaterial({ map: stripeTexture(o.c1 || '#c8241e', o.c2 || '#f4f0e6'), roughness: 0.9, side: THREE.DoubleSide })); m.position.set(0, o.y ?? 8.6, o.z ?? -6.5); m.rotation.x = 0.5; return m; },
      stringLights: (o) => { const g = new THREE.Group(); const y0 = o.y ?? 5.6, z0 = o.z ?? -3.0; const wire = []; for (let i = 0; i <= 40; i++) { const t = i / 40; wire.push(new THREE.Vector3(-7 + 14 * t, y0 - 0.9 * Math.sin(t * Math.PI), z0 - 0.6 * Math.sin(t * Math.PI))); } g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(wire), 60, 0.012, 5, false), new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 }))); for (let i = 1; i < 12; i++) { const t = i / 12; const pos = new THREE.Vector3(-7 + 14 * t, y0 - 0.9 * Math.sin(t * Math.PI) - 0.16, z0 - 0.6 * Math.sin(t * Math.PI)); const b = new THREE.Group(); const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.1, 10), new THREE.MeshStandardMaterial({ color: 0x1a1a1a })); cap.position.y = 0.06; const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffe0a0, emissive: o.color ?? 0xffc060, emissiveIntensity: 2.6 })); b.add(cap, bulb); b.position.copy(pos); g.add(b); if (i === 4 || i === 8) { const pl = new THREE.PointLight(o.color ?? 0xffc070, 5, 7, 1.8); pl.position.copy(pos); g.add(pl); } } g.userData.loose = true; return g; },
      counterBox: (o) => { const m = new THREE.Mesh(new THREE.BoxGeometry(o.w ?? 4, o.h ?? 0.5, o.d ?? 3), new THREE.MeshStandardMaterial({ color: o.color ?? 0xc8ccd0, roughness: 0.35, metalness: o.metal ?? 0.8, bumpMap: noiseBumpTexture(), bumpScale: 0.01 })); m.position.set(o.x ?? 0, -(o.h ?? 0.5) / 2 - 0.01, o.z ?? 0); m.receiveShadow = true; return m; },
    };
    for (const it of items) { const f = K[it.kind]; if (!f) { console.warn('未知陈设', it.kind); continue; } const m = f(it); if (m) dressing.add(m); }
  }
  const keyDir = key.position.clone().normalize();
  return { renderer, scene, camera, key, keyDir, table, dressing, bg: SC.bg };
}

/** 模块用对象声明场景：{ mood: 'day'|'warm'|'night'|'steel', wood, wall, light?: {...覆盖}, dressing: [...] } */
function sceneFromSpec(S = {}) {
  const MOOD = {
    day:   { bg: 0xd6cfc2, fog: [15, 38], exp: 0.95, hemi: [0xfff2dc, 0x8a8070, 0.75], key: [0xffe6c4, 2.0], fill: [0xdde8f0, 0.7], rim: [0xffffff, 10], back: [0xfff0d8, 6] },
    warm:  { bg: 0xc8b49a, fog: [15, 38], exp: 0.9,  hemi: [0xffe8c8, 0x6a5040, 0.7],  key: [0xffe0b8, 1.9], fill: [0xdfe8f0, 0.6], rim: [0xffe8c0, 14], back: [0xffe0b0, 9] },
    night: { bg: 0x141018, fog: [11, 28], exp: 1.12, hemi: [0xffd9b0, 0x1a1420, 0.55], key: [0xffe0b8, 2.2], fill: [0x9fb4d8, 0.7], rim: [0xffb870, 30], back: [0xff9a50, 22] },
    steel: { bg: 0xcfd6d0, fog: [16, 40], exp: 0.92, hemi: [0xf4f8ff, 0x7a8880, 0.75], key: [0xfff0d8, 1.9], fill: [0xd8e8f0, 0.7], rim: [0xffffff, 12], back: [0xf0f8ff, 8] },
  };
  const base = MOOD[S.mood] || MOOD.warm;
  return { ...base, ...(S.light || {}), wood: S.wood || (S.mood === 'steel' ? 'steel' : S.mood === 'night' ? 'dark' : 'light'), wall: S.wall || (S.mood === 'night' ? 'night' : S.mood === 'steel' ? 'whitetile' : 'plaster') };
}
