import * as THREE from 'three';
import { labelTexture } from './textures.js';
import { labelTextTexture } from './dressing.js';
import { innerRadiusAt, GLASS } from './vessel.js';

const SEG = 26, RAD = 12;
const G = 4.2, V0 = 1.05;
const smooth = (t) => t * t * (3 - 2 * t);
const lerp = (a, b, t) => a + (b - a) * t;

/** 流柱：质量守恒 + 重力 → 越往下越细 r(y) = r0·√(v0/v(y))。起流 0.15s 带过冲，断流 0.25s 自上而下消失，末尾留一滴。 */
export class Stream {
  constructor(scene, onDrop, ingredients) {
    this.onDrop = onDrop; this.ING = ingredients;
    const geo = new THREE.BufferGeometry();
    const count = (SEG + 1) * RAD;
    this.pos = new Float32Array(count * 3); this.nrm = new Float32Array(count * 3);
    const idx = [];
    for (let s = 0; s < SEG; s++) for (let k = 0; k < RAD; k++) {
      const a = s * RAD + k, b = s * RAD + (k + 1) % RAD, c = a + RAD, d = b + RAD;
      idx.push(a, c, b, b, c, d);
    }
    geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(this.nrm, 3));
    geo.setIndex(idx);
    this.mat = new THREE.MeshPhysicalMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.22, roughness: 0.12, metalness: 0.0, envMapIntensity: 1.5, side: THREE.DoubleSide, clearcoat: 0.8, clearcoatRoughness: 0.08, specularIntensity: 1.1, transparent: true, opacity: 0.82, depthWrite: false });
    this.mesh = new THREE.Mesh(geo, this.mat); this.mesh.visible = false; this.mesh.renderOrder = 25; this.mesh.frustumCulled = false;
    // 飞溅：落点处的小水珠
    this.splash = new THREE.InstancedMesh(new THREE.SphereGeometry(0.028, 8, 6), this.mat, 16); this.splash.count = 0; this.splash.renderOrder = 25; this.splash.frustumCulled = false; scene.add(this.splash);
    this.drops = []; this.splashAcc = 0; this._m = new THREE.Matrix4(); this._q = new THREE.Quaternion(); this._s = new THREE.Vector3(1, 1, 1);
    scene.add(this.mesh);
    this.drop = new THREE.Mesh(new THREE.SphereGeometry(0.06, 14, 10), this.mat); this.drop.visible = false; this.drop.renderOrder = 25;
    scene.add(this.drop);
    this.start = new THREE.Vector3(); this.end = new THREE.Vector3(); this.axis = new Float32Array((SEG + 1) * 3); this.clampToSurface = false;
    this.on = false; this.ramp = 0; this.time = 0; this.r0 = 0.105; this.flow = 0;
    this.dropT = -1; this.dropFrom = new THREE.Vector3(); this.dropTo = new THREE.Vector3();
  }
  setColor(key) { const ing = this.ING[key]; const t = ing.tint; const dark = (t[0] + t[1] + t[2]) / 3 < 0.35;
    if (dark) { this.mat.color.setRGB(t[0] * 1.2, t[1] * 1.2, t[2] * 1.2); this.mat.emissive.setRGB(t[0] * 0.3, t[1] * 0.3, t[2] * 0.3); }   // 浓缩/可乐/黑糖：深色流柱
    else { const k = 0.55 + 0.45 * ing.opacity; this.mat.color.setRGB(0.42 + t[0] * k * 0.58, 0.42 + t[1] * k * 0.58, 0.42 + t[2] * k * 0.58); this.mat.emissive.setRGB(t[0], t[1], t[2]); } }
  begin() { if (!this.on) { this.on = true; } }
  /** 从某点撒一把水珠（挤柠檬）：小抛物线落进杯里 */
  burst(p, n = 5, spread = 0.35) { for (let i = 0; i < n && this.drops.length < 16; i++) { const a = Math.random() * Math.PI * 2, sp = Math.random() * spread; this.drops.push({ x: p.x, y: p.y, z: p.z, vx: Math.cos(a) * sp, vz: Math.sin(a) * sp, vy: -0.3 - Math.random() * 0.4, s: 0.7 + Math.random() * 0.8 }); } }
  release() {
    if (!this.on) return;
    this.on = false;
    this.dropT = -0.35; this.dropFrom.copy(this.start); this.dropTo.copy(this.end);   // 先在瓶口挂 0.35s 再落
  }
  get active() { return this.ramp > 0.001; }

  /** start=瓶口, dir=瓶口朝向(世界), surfaceY(x,z)=液面高度函数。流柱按抛物线落下，落点写回 this.end */
  /** 穿模检验用：流柱轴线上的点（去掉最后两段——末端本来就贴着落点表面） */
  axisPoints() { if (!this.mesh.visible) return []; const out = []; for (let s = 0; s <= SEG - 2; s++) out.push({ x: this.axis[s * 3], y: this.axis[s * 3 + 1], z: this.axis[s * 3 + 2] }); return out; }
  update(dt, start, dir, flow, surfaceY, rMax, arcScale = 1, forceEnd = null) {
    this.time += dt; this.flow = flow;
    if (this.on) { this.start.copy(start).add(dir.clone().multiplyScalar(0.06)); this.ramp = Math.min(1, this.ramp + dt / 0.15); }
    else { this.ramp = Math.max(0, this.ramp - dt / 0.25); }
    // 出口速度：沿瓶口水平方向，越倾斜越急；竖直略向下
    const hx = dir.x, hz = dir.z, hl = Math.hypot(hx, hz) || 1;
    let vx = (hx / hl) * (0.42 + 0.55 * flow) * arcScale, vz = (hz / hl) * (0.42 + 0.55 * flow) * arcScale, vy = -0.20;
    const y0 = this.start.y;
    // 落点：迭代两次解 y(t) = surface(x(t), z(t))
    let ys = surfaceY(this.start.x, this.start.z), t = Math.sqrt(Math.max(0.01, 2 * (y0 - ys) / G));
    for (let k = 0; k < 2; k++) { const x = this.start.x + vx * t, z = this.start.z + vz * t; ys = surfaceY(x, z); t = (vy + Math.sqrt(vy * vy + 2 * G * Math.max(0.01, y0 - ys))) / G; }
    let ex = this.start.x + vx * t, ez = this.start.z + vz * t;
    if (forceEnd && this.on) {   // 拉花/淋酱：手指指哪落哪 —— 由落点反推水平初速度
      ys = forceEnd.y; t = (vy + Math.sqrt(vy * vy + 2 * G * Math.max(0.01, y0 - ys))) / G; vx = (forceEnd.x - this.start.x) / t; vz = (forceEnd.z - this.start.z) / t; ex = forceEnd.x; ez = forceEnd.z;
    }
    if (!this.on && this.lastV) { vx = this.lastV.x; vz = this.lastV.z; }   // 收流时瓶子在回正，出口方向乱摆——尾流沿着断流前的方向落，不许扫到杯壁
    if (this.guardWall !== false && (!forceEnd || !this.on)) {   // 流柱在杯内那一段任何点都不许挨到内壁：精确解出把水平初速度缩到多少，越界的采样点正好落回内壁以内
      let kmin = 1; const p0x = this.start.x, p0z = this.start.z;
      for (let s = 1; s <= 12; s++) {
        const tt = t * s / 12, y = y0 + vy * tt - 0.5 * G * tt * tt; if (!(y < GLASS.innerTop && y > (this.floorY ?? -99))) continue;
        const lim = Math.max(0.05, innerRadiusAt(y) - 0.07), dx = vx * tt, dz = vz * tt; if (Math.hypot(p0x + dx, p0z + dz) <= lim) continue;
        const a = dx * dx + dz * dz, b = 2 * (p0x * dx + p0z * dz), c = p0x * p0x + p0z * p0z - lim * lim, disc = b * b - 4 * a * c;
        kmin = Math.min(kmin, a < 1e-9 || disc < 0 ? 0 : Math.max(0, (-b + Math.sqrt(disc)) / (2 * a)));
      }
      if (kmin < 1) { vx *= kmin; vz *= kmin; }
      ex = this.start.x + vx * t; ez = this.start.z + vz * t; ys = surfaceY(ex, ez);
    }
    if (this.on) this.lastV = { x: vx, z: vz };
    if (this.clampToSurface) {   // 淋在冰山这种凸面上：流柱落在抛物线第一次碰到山面的地方，不许从山肩里穿过去再落到指定点
      let lo = 0, hi = t, hit = false;
      for (let s = 1; s <= 24; s++) { const tt = t * s / 24, x = this.start.x + vx * tt, z = this.start.z + vz * tt, y = y0 + vy * tt - 0.5 * G * tt * tt; if (y < surfaceY(x, z) - 0.004) { hi = tt; lo = t * (s - 1) / 24; hit = true; break; } }
      if (hit && hi < t - 1e-3) { for (let k = 0; k < 8; k++) { const m = (lo + hi) / 2, x = this.start.x + vx * m, z = this.start.z + vz * m, y = y0 + vy * m - 0.5 * G * m * m; if (y < surfaceY(x, z)) hi = m; else lo = m; } t = hi; ex = this.start.x + vx * t; ez = this.start.z + vz * t; ys = surfaceY(ex, ez); }
    }
    const er = Math.hypot(ex, ez);
    if (!forceEnd && er > rMax) { const k = rMax / er; vx *= k; vz *= k; ex = this.start.x + vx * t; ez = this.start.z + vz * t; }   // 别倒到杯外
    this.end.set(ex, ys, ez); this.tHit = t;
    if (this.ramp <= 0.001) { this.mesh.visible = false; }
    else {
      this.mesh.visible = true;
      const rs = this.on ? (this.ramp < 0.7 ? (this.ramp / 0.7) * 1.12 : 1.12 - 0.12 * (this.ramp - 0.7) / 0.3) : Math.max(0.35, this.ramp);
      const t0 = this.on ? 0 : t * (1 - this.ramp);              // 断流：从瓶口往下收
      const wid = 0.55 + 0.45 * Math.min(1, flow * 1.4);
      for (let s = 0; s <= SEG; s++) {
        const tt = t0 + (t - t0) * (s / SEG);
        const x = this.start.x + vx * tt, z = this.start.z + vz * tt, y = y0 + vy * tt - 0.5 * G * tt * tt;
        const vyt = vy - G * tt, v = Math.hypot(vx, vz, vyt);
        this.axis[s * 3] = x; this.axis[s * 3 + 1] = y; this.axis[s * 3 + 2] = z;
        let r = this.r0 * wid * Math.sqrt(V0 / Math.max(V0, v)) * rs;
        r *= 1 + 0.10 * Math.sin(y * 21 - this.time * 36) + 0.05 * Math.sin(y * 34 + this.time * 23);
        // 细流的下半段会断成一串珠子（Plateau–Rayleigh 不稳定性）
        const frac = (tt - t0) / Math.max(1e-3, t - t0), bead = Math.max(0, frac - 0.35) / 0.65 * (1 - Math.min(1, flow / 0.75));
        if (bead > 0) r *= 1 - bead * 0.55 + bead * 0.55 * Math.pow(0.5 + 0.5 * Math.sin(y * 46 - this.time * 40), 1.6);
        if (s === 0 && this.on) r = Math.min(r * 1.25, 0.085);
        // 截面圆环垂直于速度方向
        const tx = vx / v, ty = vyt / v, tz = vz / v;
        let ax = 0, ay = 1, az = 0; if (Math.abs(ty) > 0.9) { ax = 1; ay = 0; }
        let n1x = ay * tz - az * ty, n1y = az * tx - ax * tz, n1z = ax * ty - ay * tx; const l1 = Math.hypot(n1x, n1y, n1z) || 1; n1x /= l1; n1y /= l1; n1z /= l1;
        const n2x = ty * n1z - tz * n1y, n2y = tz * n1x - tx * n1z, n2z = tx * n1y - ty * n1x;
        for (let k = 0; k < RAD; k++) {
          const a = (k / RAD) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
          const nx = n1x * ca + n2x * sa, ny = n1y * ca + n2y * sa, nz = n1z * ca + n2z * sa;
          const o = (s * RAD + k) * 3;
          this.pos[o] = x + nx * r; this.pos[o + 1] = y + ny * r; this.pos[o + 2] = z + nz * r;
          this.nrm[o] = nx; this.nrm[o + 1] = ny; this.nrm[o + 2] = nz;
        }
      }
      this.mesh.geometry.attributes.position.needsUpdate = true;
      this.mesh.geometry.attributes.normal.needsUpdate = true;
    }
    // 飞溅水珠：有流量且液面存在时，落点每 0.07s 弹出一颗，小抛物线回落到液面
    if (this.on && flow > 0.15 && this.hasLiquid) { this.splashAcc += dt; if (this.splashAcc > 0.07 && this.drops.length < 16) { this.splashAcc = 0; const a = Math.random() * Math.PI * 2, sp = 0.35 + Math.random() * 0.5 * flow; this.drops.push({ x: this.end.x, y: this.end.y, z: this.end.z, vx: Math.cos(a) * sp, vz: Math.sin(a) * sp, vy: 0.9 + Math.random() * 0.9, s: 0.6 + Math.random() * 0.8 }); } }
    for (const d of this.drops) { d.vy -= 9.8 * dt; d.x += d.vx * dt; d.y += d.vy * dt; d.z += d.vz * dt; }
    this.drops = this.drops.filter((d) => d.y > Math.min(this.end.y, this.floorY ?? this.end.y) - 0.02 || d.vy > 0);
    this.splash.count = this.drops.length;
    for (let i = 0; i < this.drops.length; i++) { const d = this.drops[i]; this._s.setScalar(d.s); this._m.compose(new THREE.Vector3(d.x, d.y, d.z), this._q, this._s); this.splash.setMatrixAt(i, this._m); }
    if (this.drops.length) this.splash.instanceMatrix.needsUpdate = true;
    // 末尾一滴
    if (this.dropT > -1) {
      this.dropT += dt;
      if (this.dropT < 0) {   // 挂在瓶口：越来越大、越来越长
        const g = 1 + this.dropT / 0.35; this.drop.visible = true; this.dropFrom.copy(this.start);
        this.drop.position.copy(this.start).add(new THREE.Vector3(0, -0.04 - 0.05 * g, 0)); this.drop.scale.set(0.45 + 0.35 * g, 0.7 + 0.9 * g, 0.45 + 0.35 * g);
      } else {
      const fallT = Math.sqrt(2 * Math.max(0.05, this.dropFrom.y - this.dropTo.y) / 9.8) * 1.15;
      const k = this.dropT / fallT;
      if (k >= 1) { this.drop.visible = false; this.dropT = -1; this.onDrop?.(this.dropTo); }
      else { this.drop.visible = true; this.drop.position.set(lerp(this.dropFrom.x, this.dropTo.x, k), lerp(this.dropFrom.y, this.dropTo.y, k * k), lerp(this.dropFrom.z, this.dropTo.z, k)); const st = 0.7 + 0.5 * (1 - k); this.drop.scale.set(0.62 * st, 1.35 * st, 0.62 * st); }
      }
    }
  }
}

/** 瓶子：从右侧抛物线落到位；按住时倾斜，倾角决定流量 */
export class Bottle {
  constructor(scene, ingredients) {
    this.ING = ingredients;
    this.g = new THREE.Group();
    const glass = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.05, metalness: 0, transparent: true, opacity: 0.28, envMapIntensity: 1.6, clearcoat: 1, depthWrite: false, side: THREE.DoubleSide });
    this.inner = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.26, 1.15, 40), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.25, metalness: 0.05 }));
    this.inner.position.y = -0.1;
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.30, 0.30, 1.4, 48, 1, true), glass); body.renderOrder = 15;
    const shoulder = new THREE.Mesh(new THREE.CylinderGeometry(0.095, 0.30, 0.32, 48, 1, true), glass); shoulder.position.y = 0.86; shoulder.renderOrder = 15;
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.095, 0.095, 0.5, 32, 1, true), glass); neck.position.y = 1.27; neck.renderOrder = 15;
    const lip = new THREE.Mesh(new THREE.TorusGeometry(0.095, 0.02, 8, 40), new THREE.MeshStandardMaterial({ color: 0xd8d8d8, roughness: 0.2, metalness: 0.7 })); lip.rotation.x = Math.PI / 2; lip.position.y = 1.52;
    const bottom = new THREE.Mesh(new THREE.CylinderGeometry(0.30, 0.28, 0.08, 48), glass); bottom.position.y = -0.72;
    this.label = new THREE.Mesh(new THREE.CylinderGeometry(0.305, 0.305, 0.5, 48, 1, true, Math.PI * 0.5, Math.PI), new THREE.MeshStandardMaterial({ map: labelTexture('#c1462f'), roughness: 0.85, side: THREE.DoubleSide }));
    this.label.position.y = -0.05;
    this.stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.308, 0.308, 0.12, 48, 1, true), new THREE.MeshStandardMaterial({ color: 0xc1462f, roughness: 0.6 }));
    this.stripe.position.y = -0.05;
    this.g.add(this.inner, body, shoulder, neck, lip, bottom, this.label, this.stripe);
    this.g.traverse((o) => { if (o.isMesh) o.castShadow = false; });
    this.inner.castShadow = true;
    this.g.visible = false;
    scene.add(this.g);
    this.rest = new THREE.Vector3(1.45, GLASS.innerTop + 0.30, -0.55);   // 瓶身最低点始终在杯口之上
    this.far = new THREE.Vector3(3.8, GLASS.innerTop - 0.6, 0.4);
    this.anim = null; this.tilt = 0; this.shown = false; this.aim = new THREE.Vector2(0, 0);
    this._spout = new THREE.Vector3(0, 1.54, 0); this._spout2 = new THREE.Vector3(0, 2.6, 0);
  }
  show(key) {
    const ing = this.ING[key];
    if (this.shown && this.curKey === key) return; this.curKey = key;
    this.inner.material.color.setRGB(ing.tint[0], ing.tint[1], ing.tint[2]);
    this.inner.material.transparent = ing.opacity < 0.9; this.inner.material.opacity = 0.55 + ing.opacity * 0.45;
    this.stripe.material.color.set(ing.css); this.label.material.map = labelTextTexture(ing.css, ing.name, ''); this.label.material.needsUpdate = true;
    this.g.visible = true; this.shown = true; this.tilt = 0;
    this.anim = { t: 0, dur: 0.62, from: this.far.clone(), to: this.rest.clone(), arc: 0.9 };
  }
  hide() {
    if (!this.shown) return; this.shown = false; this.curKey = null;
    this.anim = { t: 0, dur: 0.5, from: this.g.position.clone(), to: this.far.clone(), arc: 0.6, hideAtEnd: true };
  }
  setTilt(target, dt) { this.tilt += (target - this.tilt) * Math.min(1, dt * 9); }
  aimAt(x, z) { this.target = new THREE.Vector2(x, z); }
  clearAim() { this.target = null; }
  spout() { return this.g.localToWorld(this._spout.clone()); }
  spoutDir() { return this.g.localToWorld(this._spout2.clone()).sub(this.spout()).normalize(); }
  /** 瓶身轮廓截面 [局部 y, 半径]——穿模检验与抬高都用它（肩部按瓶身半径算，偏保守） */
  sections() { return Array.from({ length: 15 }, (_, i) => { const ly = -0.72 + (1.54 + 0.72) * i / 14; return [ly, ly < 0.86 ? 0.30 : ly < 1.02 ? 0.20 : 0.115]; }); }
  angle() { return 0.22 + this.tilt * 1.05; }
  samples() { this.g.updateMatrixWorld(true); const out = []; for (const [ly, lr] of this.sections()) for (let i = 0; i < 12; i++) { const a = i / 12 * Math.PI * 2; out.push(this.g.localToWorld(new THREE.Vector3(Math.cos(a) * lr, ly, Math.sin(a) * lr))); } return out; }
  /** 瓶身任何落在杯口投影内的点都必须在 topY（杯口 / 冰山顶）之上——倾斜得越狠，肩部越往下探，就得抬得越高 */
  lift() { if (this.guardWall === false) return 0; const top = (this.topY ?? GLASS.innerTop) + 0.08; let need = 0; for (const q of this.samples()) if (Math.hypot(q.x, q.z) < GLASS.rTop + GLASS.wall + 0.03 && q.y < top) need = Math.max(need, top - q.y); return need; }
  update(dt) {
    if (this.anim) {
      const a = this.anim; a.t = Math.min(a.dur, a.t + dt); const k = smooth(a.t / a.dur);
      this.g.position.lerpVectors(a.from, a.to, k);
      this.g.position.y += Math.sin(k * Math.PI) * a.arc;                 // A2 抛物线弧
      this.g.rotation.z = Math.sin(k * Math.PI) * 0.08;                    // A3 途中摆动回正
      if (a.t >= a.dur) { if (a.hideAtEnd) this.g.visible = false; this.anim = null; }
      return;
    }
    if (!this.shown) return;
    this.g.rotation.z = this.angle();
    this.g.position.set(this.rest.x - this.tilt * 0.35 + this.aim.x, this.rest.y - this.tilt * 0.30 + Math.sin(performance.now() / 700) * 0.012, this.rest.z + this.aim.y);   // A5 待机微浮；aim = 淋糖浆时跟手
    this.g.position.y += this.lift();   // 绝不探进杯子
    if (this.target) { const sp = this.spout(); this.aim.x += (this.target.x - sp.x) * Math.min(1, dt * 10); this.aim.y += (this.target.y - sp.z) * Math.min(1, dt * 10); }   // 瓶口迭代对准目标点
    else { this.aim.multiplyScalar(Math.max(0, 1 - dt * 6)); }
  }
}
