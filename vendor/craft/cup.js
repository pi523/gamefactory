import * as THREE from 'three';
import { noiseBumpTexture } from './textures.js';
const toLin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));

/**
 * 多器皿用的简易液体杯（香槟塔 10 只、功夫茶 3 只、拉茶两只钢杯、啤酒杯、果汁杯都用它）。
 * inner = 内轮廓 [[r, y]...]（y 从内底 0 到杯口 H）；outer = 外壳轮廓（含底/脚，可到 y<0）。
 * 液体 = 按倒入顺序叠的色带 layers，可 mix() 搅匀；foam = 泡沫层厚度（啤酒/拉茶）。
 * 体积单位：fill 0..1 = 到杯口。几何只在变化时重建（dirty）。
 */
export class Cup {
  constructor(scene, { inner, outer, material = 'glass', pos = [0, 0, 0], tint = 0xf5f1ea, liquidOpacity = 0.9, foamColor = 0xfff6e6, glassColor = 0xf2f8fa }) {
    this.g = new THREE.Group(); this.g.position.set(...pos); scene.add(this.g);
    this.inner = inner; this.H = inner[inner.length - 1][1]; this.material = material;
    const N = 64; this.volTab = new Float32Array(N + 1); let acc = 0;
    for (let i = 1; i <= N; i++) { const y0 = this.H * (i - 1) / N, y1 = this.H * i / N, r0 = this.innerR(y0), r1 = this.innerR(y1); acc += Math.PI * (r0 * r0 + r0 * r1 + r1 * r1) / 3 * (y1 - y0); this.volTab[i] = acc; }
    this.capacity = acc;
    const mat = material === 'glass'
      ? new THREE.MeshPhysicalMaterial({ color: glassColor, roughness: 0.03, metalness: 0, transparent: true, opacity: 0.14, side: THREE.DoubleSide, envMapIntensity: 0.9, clearcoat: 0.6, clearcoatRoughness: 0.06, depthWrite: false })   /* 折射版在软渲染下 10 只杯要 16 分钟一帧，改回 alpha */
      : material === 'steel'
        ? new THREE.MeshStandardMaterial({ color: 0xeef2f5, roughness: 0.2, metalness: 0.85, envMapIntensity: 2.0, side: THREE.DoubleSide })
        : new THREE.MeshPhysicalMaterial({ color: tint, roughness: 0.2, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.12, envMapIntensity: 1.2, side: THREE.DoubleSide });
    this.shell = new THREE.Mesh(new THREE.LatheGeometry(outer.map(([r, y]) => new THREE.Vector2(r, y)), 64), mat);
    this.shell.castShadow = material !== 'glass'; this.shell.receiveShadow = true; this.shell.renderOrder = material === 'glass' ? 20 : 10; this.g.add(this.shell);
    if (material === 'glass') {   // 玻璃再加一层高光：黑底加色，只出反射
      const gloss = new THREE.Mesh(this.shell.geometry, new THREE.MeshPhysicalMaterial({ color: 0x000000, roughness: 0.05, metalness: 0, envMapIntensity: 0.12, clearcoat: 0.3, clearcoatRoughness: 0.08, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.FrontSide }));   /* 高光层只加一点边缘反光；双面+高 env 会把十只叠在一起的杯子加成一团白 */
      gloss.renderOrder = 30; this.g.add(gloss);
    }
    this.layers = []; this.volume = 0; this.foam = 0; this.mixK = 0; this.dirty = true; this.liquidOpacity = liquidOpacity;
    this.liqMat = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.3, metalness: 0, transparent: true, opacity: liquidOpacity, clearcoat: 0.25, clearcoatRoughness: 0.3, envMapIntensity: 0.25 });
    this.liq = new THREE.Mesh(new THREE.BufferGeometry(), this.liqMat); this.liq.renderOrder = 22; this.liq.frustumCulled = false; this.liq.visible = false; this.g.add(this.liq);
    this.top = new THREE.Mesh(new THREE.CircleGeometry(1, 56), new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.18, metalness: 0, transparent: true, opacity: Math.min(1, liquidOpacity + 0.05), clearcoat: 0.6, clearcoatRoughness: 0.15, envMapIntensity: 0.35, depthWrite: false }));
    this.top.rotation.x = -Math.PI / 2; this.top.renderOrder = 23; this.top.visible = false; this.g.add(this.top);
    this.foamMat = new THREE.MeshStandardMaterial({ color: foamColor, roughness: 0.92, metalness: 0, bumpMap: noiseBumpTexture(), bumpScale: 0.025 });
    this.foamMesh = new THREE.Mesh(new THREE.BufferGeometry(), this.foamMat); this.foamMesh.renderOrder = 24; this.foamMesh.frustumCulled = false; this.foamMesh.visible = false; this.foamMesh.castShadow = true; this.g.add(this.foamMesh);
    this.wobble = 0;   // 液面轻微晃动（倒入时）
    // 杯底接触阴影（AO）：杯子不是浮在台面上的
    const sc = document.createElement('canvas'); sc.width = sc.height = 128; const sg = sc.getContext('2d'); const gr = sg.createRadialGradient(64, 64, 10, 64, 64, 64); gr.addColorStop(0, 'rgba(0,0,0,.5)'); gr.addColorStop(0.6, 'rgba(0,0,0,.18)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); sg.fillStyle = gr; sg.fillRect(0, 0, 128, 128);
    const footR = Math.max(...outer.filter(([, y]) => y <= Math.min(...outer.map((o) => o[1])) + 0.08).map(([r]) => r)) * 1.35; const footY = Math.min(...outer.map((o) => o[1]));
    this.contact = new THREE.Mesh(new THREE.PlaneGeometry(footR * 2, footR * 2), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(sc), transparent: true, depthWrite: false })); this.contact.rotation.x = -Math.PI / 2; this.contact.position.y = footY + 0.004; this.contact.renderOrder = 2; this.g.add(this.contact);
  }
  innerR(y) { const P = this.inner; if (y <= P[0][1]) return P[0][0]; for (let i = 1; i < P.length; i++) { if (y <= P[i][1]) { const [r0, y0] = P[i - 1], [r1, y1] = P[i]; return r0 + (r1 - r0) * (y - y0) / Math.max(1e-6, y1 - y0); } } return P[P.length - 1][0]; }
  /** 内壁半径为 r 处的高度（内轮廓单调变宽时用；r 比底还小返回 0） */
  yForInnerR(r) { const P = this.inner; if (r <= P[0][0]) return 0; for (let i = 1; i < P.length; i++) { const [r0, y0] = P[i - 1], [r1, y1] = P[i]; if (r <= r1) return r1 > r0 ? y0 + (y1 - y0) * (r - r0) / (r1 - r0) : y1; } return this.H; }
  levelFor(vol) { const N = 64; if (vol <= 0) return 0; if (vol >= this.capacity) return this.H; for (let i = 1; i <= N; i++) if (this.volTab[i] >= vol) { const v0 = this.volTab[i - 1], v1 = this.volTab[i]; return this.H * ((i - 1) + (vol - v0) / Math.max(1e-9, v1 - v0)) / N; } return this.H; }
  get fill() { return this.volume / this.capacity; }
  get level() { return this.levelFor(Math.min(this.volume, this.capacity)); }
  /** 液面世界高度（含泡沫可选） */
  get levelY() { return this.g.position.y + this.level; }
  get topY() { return this.g.position.y + this.level + this.foam; }
  /** 倒入相对容量 dv 的液体；返回装不下溢出去的量（相对容量） */
  add(rgb, dv) {
    const v = dv * this.capacity; if (v <= 0) return 0;
    const room = Math.max(0, this.capacity - this.volume), put = Math.min(v, room);
    const last = this.layers[this.layers.length - 1];
    if (last && last.rgb[0] === rgb[0] && last.rgb[1] === rgb[1] && last.rgb[2] === rgb[2]) last.v += put; else this.layers.push({ rgb: [...rgb], v: put });
    this.volume += put; this.dirty = true; return (v - put) / this.capacity;
  }
  remove(dv) { const v = Math.min(this.volume, dv * this.capacity); let left = v; while (left > 1e-9 && this.layers.length) { const L = this.layers[this.layers.length - 1]; const t = Math.min(L.v, left); L.v -= t; left -= t; if (L.v <= 1e-9) this.layers.pop(); } this.volume -= v; this.dirty = true; return v / this.capacity; }
  setFoam(h) { if (Math.abs(h - this.foam) > 1e-4) this.dirty = true; this.foam = Math.max(0, h); }
  mix(k) { this.mixK = Math.min(1, this.mixK + k); this.dirty = true; }
  mean() { let r = 0, g = 0, b = 0, t = 0; for (const L of this.layers) { r += L.rgb[0] * L.v; g += L.rgb[1] * L.v; b += L.rgb[2] * L.v; t += L.v; } return t ? [r / t, g / t, b / t] : [1, 1, 1]; }
  colorAt(y) { let acc = 0; const m = this.mean(); for (const L of this.layers) { acc += L.v; if (this.levelFor(acc) >= y - 1e-6) return L.rgb.map((c, i) => c + (m[i] - c) * this.mixK); } return m; }
  reset() { this.layers = []; this.volume = 0; this.foam = 0; this.mixK = 0; this.dirty = true; }
  update(dt) { if (this.wobble > 0.001) { this.wobble *= Math.max(0, 1 - dt * 3); this.dirty = true; } if (!this.dirty) return; this.dirty = false; this._build(); }
  _build() {
    const lv = this.level, rings = 14, seg = 44;
    if (this.volume <= this.capacity * 0.002) { this.liq.visible = false; this.top.visible = false; }
    else {
      this.liq.visible = true;
      const pos = [], col = [], idx = [], nrm = [];
      for (let i = 0; i <= rings; i++) {
        const y = lv * i / rings, r = Math.max(0.001, this.innerR(y) - 0.006), c = this.colorAt(y).map(toLin);
        for (let s = 0; s < seg; s++) { const a = s / seg * Math.PI * 2; pos.push(Math.cos(a) * r, y, Math.sin(a) * r); nrm.push(Math.cos(a), 0, Math.sin(a)); col.push(c[0], c[1], c[2]); if (i < rings) { const a0 = i * seg + s, b0 = i * seg + (s + 1) % seg, c0 = a0 + seg, d0 = b0 + seg; idx.push(a0, c0, b0, b0, c0, d0); } }
      }
      const base = pos.length / 3, cb = this.colorAt(0).map(toLin); pos.push(0, 0.002, 0); nrm.push(0, -1, 0); col.push(...cb); for (let s = 0; s < seg; s++) idx.push(base, (s + 1) % seg, s);
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setAttribute('normal', new THREE.Float32BufferAttribute(nrm, 3)); geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); geo.setIndex(idx);
      this.liq.geometry.dispose(); this.liq.geometry = geo;
      const ct = this.colorAt(Math.max(0, lv - 0.001)); this.top.material.color.setRGB(Math.min(1, ct[0] * 0.92), Math.min(1, ct[1] * 0.92), Math.min(1, ct[2] * 0.92), THREE.SRGBColorSpace);
      const rt = Math.max(0.001, this.innerR(lv) - 0.006); this.top.scale.set(rt, rt, 1); this.top.position.y = lv + 0.0015 + Math.sin(performance.now() / 90) * this.wobble * 0.01;
      this.top.visible = this.foam <= 0.003;
    }
    if (this.foam > 0.003 && this.volume > 0) {   // 泡沫：从液面起、贴着内壁、顶上略鼓、可高出杯口一点
      this.foamMesh.visible = true;
      const y0 = lv, y1 = lv + this.foam, prof = [new THREE.Vector2(0.001, y0), new THREE.Vector2(Math.max(0.002, this.innerR(Math.min(this.H, y0)) - 0.004), y0)];
      const steps = 6;
      for (let i = 1; i <= steps; i++) { const y = y0 + (y1 - y0) * i / steps; const over = Math.max(0, y - this.H); const lip = this.foamLip ? Math.min(0.06, Math.max(0, over - 0.05) * 0.9) : 0; const rr = this.innerR(Math.min(this.H, y)) - 0.006 + lip - (this.foamLip ? 0 : over * 0.22) - (i === steps ? 0.05 : i === steps - 1 ? 0.015 : 0);   /* 啤酒泡可在杯口上方鼓出一圈唇（坐在杯沿上），其它杯向内收 */ prof.push(new THREE.Vector2(Math.max(0.002, rr), y)); }   /* 高出杯口的泡向内收，绝不越过杯壁 */
      prof.push(new THREE.Vector2(Math.max(0.002, this.innerR(Math.min(this.H, y1)) * 0.55), y1 + this.foam * 0.10)); prof.push(new THREE.Vector2(0.001, y1 + this.foam * 0.13));
      this.foamMesh.geometry.dispose(); const fg = new THREE.LatheGeometry(prof, 44); { const P = fg.attributes.position; for (let i = 0; i < P.count; i++) { const x = P.getX(i), y = P.getY(i), z = P.getZ(i); if (y > y0 + 0.02) { const n = 0.012 * Math.sin(x * 23 + z * 17) + 0.010 * Math.sin(x * 41 - z * 29 + y * 13) + 0.008 * Math.sin(z * 53 + y * 31); P.setXYZ(i, x * (1 + n * 0.6), y + n * (y > y1 - 0.02 ? 2.2 : 1), z * (1 + n * 0.6)); } } fg.computeVertexNormals(); } this.foamMesh.geometry = fg;   /* 泡沫不是光滑圆柱，有绵密起伏 */
    } else this.foamMesh.visible = false;
  }
}

/** 直身/微收腰玻璃杯轮廓：内壁 + 带厚度的外壳（外→口→内→底），底座 baseH */
export function glassProfile(rTop, rBot, H, wall = 0.05, baseH = 0.22) {
  return {
    inner: [[rBot - wall, 0], [rTop - wall, H]],
    outer: [[0, -baseH], [rBot * 0.94, -baseH], [rBot, -baseH + 0.06], [rBot, 0], [rTop, H], [rTop - wall, H], [rBot - wall, 0], [0, 0]],
  };
}
/** 碟形香槟杯（coupe）：浅宽碗 + 细脚 + 底座；y=0 为碗内底 */
export function coupeProfile(R = 0.62, bowlH = 0.42, stem = 0.95) {
  const inner = [[0.10, 0], [R * 0.72, bowlH * 0.30], [R * 0.95, bowlH * 0.72], [R, bowlH]];
  const outer = [[0, -stem - 0.06], [R * 0.62, -stem - 0.06], [R * 0.62, -stem - 0.02], [0.07, -stem + 0.05], [0.055, -0.20], [0.10, -0.06], [R * 0.74, bowlH * 0.30 - 0.03], [R * 0.97, bowlH * 0.72 - 0.02], [R + 0.03, bowlH], [R, bowlH], [R * 0.95, bowlH * 0.72], [R * 0.72, bowlH * 0.30], [0.10, 0], [0, 0]];
  return { inner, outer };
}
/** 品茗小杯（白瓷）：外撇口 */
export function teacupProfile(rTop = 0.30, rBot = 0.20, H = 0.34, wall = 0.03) {
  return { inner: [[rBot - wall, 0], [rTop * 0.92 - wall, H * 0.75], [rTop - wall, H]], outer: [[0, -0.06], [rBot * 0.9, -0.06], [rBot, 0], [rTop * 0.92, H * 0.75], [rTop, H], [rTop - wall, H], [rTop * 0.92 - wall, H * 0.75], [rBot - wall, 0], [0, 0]] };
}
/** 拉茶钢杯：直身厚壁不锈钢 */
export function steelMugProfile(r = 0.55, H = 1.5, wall = 0.04) {
  return { inner: [[r - wall, 0], [r - wall, H]], outer: [[0, -0.05], [r, -0.05], [r, H], [r - wall, H], [r - wall, 0], [0, 0]] };
}
