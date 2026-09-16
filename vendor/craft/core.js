import * as THREE from 'three';
import { sfx } from './audio.js';
import { iconFor } from './icons.js';
import { checkAssembly } from '../bf-checks.js';

export const clamp = (v, a = 0, b = 100) => Math.max(a, Math.min(b, v));
export const smooth = (t) => t * t * (3 - 2 * t);
export const rangeMiss = (v, [lo, hi]) => (v < lo ? lo - v : v > hi ? v - hi : 0);

/**
 * 第二组饮品游戏的公共壳：任务卡、工序条、底部操作区、镜头、结算、庆祝、harness 自动化、穿模检验入口。
 * 每款游戏是一个模块（games/*.js），实现：init / newTask / enter / down / move / up / update / canNext / score / auto / clipping / reset。
 * 任务卡只说"要什么"，分量/时机/手法全部是隐形评分。
 */
export class Core {
  constructor(world, G) {
    this.w = world; this.G = G; this.dom = world.renderer.domElement;
    this.orderNo = 0; this.phase = G.phases[0]; this.cam = null; this.queue = []; this.aspectK = 1; this.viewName = null; this.autoCtl = null; this.hs = G.hs || 1;
    this.VIEWS = { reveal0: { pos: [0.4, 0.9, 5.2], tgt: [0, 0.7, 0] }, reveal1: { pos: [0.3, 3.1, 4.7], tgt: [0, 2.6, 0] }, serve: { pos: [0, 3.7, 8.3], tgt: [0, -0.05, 0] }, ...G.views };
    this._ui(); this._events();
    G.init(this);
    this.newTask();
    this.auto = { start: (phase, part = 'end') => { this.autoCtl = G.auto(this, phase, part) || null; if (this.autoCtl && this.autoCtl.wait != null) this.autoCtl.t = 0; }, busy: () => !!this.autoCtl, next: () => this.onNext() };
  }

  // ================= UI =================
  _ui() {
    const $ = (id) => document.getElementById(id);
    this.el = { dock: $('dock'), hint: $('hint'), tray: $('tray'), meterWrap: $('meter-wrap'), meterFill: $('meter-fill'), meterVal: $('meter-val'), meterLabel: $('meter-label'),
      next: $('btn-next'), undo: $('btn-undo'), orderKind: $('order-kind'), orderNo: $('order-no'), orderName: $('order-name'), orderParts: $('order-parts'), orderLine: $('order-line'), orderSolids: $('order-solids'), orderGarnish: $('order-garnish'), praise: $('praise'), banner: $('banner'),
      pourHud: $('pour-hud'), pourTip: $('pour-tip'), pourWarn: $('pour-warn'), score: $('score'), grade: $('grade'), total: $('score-total'), scoreName: $('score-name'), lines: $('score-lines'), tips: $('tips'), again: $('btn-again'), strip: $('strip') };
    document.getElementById('steps').innerHTML = this.G.phases.map((ph, i) => `<div class="step" data-step="${ph}"><i>${i + 1}</i><span>${this.G.phaseNames[ph] || ph}</span></div>`).join('');
    this.el.steps = [...document.querySelectorAll('.step')];
    this.el.orderKind.textContent = this.G.cardTitle || '这一杯'; if (this.G.againText) this.el.again.textContent = this.G.againText;
    const E = this.el;
    this.ui = {
      hint: (t) => { E.hint.textContent = t; },
      next: (t, disabled = false) => { E.next.textContent = t; E.next.disabled = disabled; E.next.style.display = ''; },
      nextEnabled: (ok) => { E.next.disabled = !ok; },
      undo: (t) => { E.undo.classList.toggle('hidden', !t); if (t) E.undo.textContent = t; },
      tray: (items, onPick, kind = 'ingredient') => this.fillTray(items, onPick, kind),
      markTray: (k) => this.markTray(k),
      meter: (label, frac, text) => { E.meterWrap.classList.remove('hidden'); E.meterLabel.textContent = label; E.meterFill.style.width = (clamp(frac, 0, 1) * 100) + '%'; E.meterVal.textContent = text ?? ''; },
      meterOff: () => E.meterWrap.classList.add('hidden'),
      hud: (tip) => { E.pourHud.classList.toggle('hidden', !tip); if (tip) E.pourTip.textContent = tip; },
      warn: (t) => { E.pourWarn.classList.toggle('hidden', !t); if (t) E.pourWarn.textContent = t; },
      praise: (t) => this.praise(t),
      /** 教程指引：type = tap|hold|dragx|dragy|drag|circle|wait，一句话 ≤ 12 字；3 秒或碰屏即走 */
      coach: (type, text) => this.coach(type, text),
      /** 独立的「按住」大按钮：按住 = onDown，松开 = onUp；传 null 隐藏。给需要"一只手按、一只手拖"的玩法 */
      hold: (label, onDown, onUp) => { const b = document.getElementById('hold-btn'); b.classList.toggle('hidden', !label); if (!label) { this._hold = null; return; } b.textContent = label; this._hold = { onDown, onUp }; },
    };
    const hb = document.getElementById('hold-btn'); const hd = (e) => { e.preventDefault(); hb.classList.add('down'); this._hold?.onDown?.(e); }; const hu = (e) => { hb.classList.remove('down'); this._hold?.onUp?.(e); };
    hb.addEventListener('pointerdown', hd); hb.addEventListener('pointerup', hu); hb.addEventListener('pointercancel', hu); hb.addEventListener('pointerleave', hu); hb.addEventListener('contextmenu', (e) => e.preventDefault());
  }
  _events() {
    this.dom.addEventListener('pointerdown', (e) => { document.getElementById('coach').classList.add('hidden'); if (this.phase !== 'reveal' && this.phase !== 'score') this.G.down?.(this, e); });
    document.getElementById('ver').textContent = 'v0916-b';
    this.dom.addEventListener('pointermove', (e) => { if (this.phase !== 'reveal' && this.phase !== 'score') this.G.move?.(this, e); });
    window.addEventListener('pointerup', (e) => this.G.up?.(this, e));
    this.dom.addEventListener('contextmenu', (e) => e.preventDefault());
    this.el.next.addEventListener('click', () => this.onNext());
    this.el.undo.addEventListener('click', () => this.G.undo?.(this, this.phase));
    this.el.again.addEventListener('click', () => { this.el.score.classList.add('hidden'); this.reset(); });
  }
  fillTray(items, onPick, kind = 'ingredient') {
    this.el.tray.innerHTML = ''; this.trayItems = {};
    for (const [key, it] of items) {
      const d = document.createElement('div'); d.className = 'item'; d.dataset.key = key;
      d.innerHTML = `<div class="ico" style="background-image:url(${it.icon || iconFor(kind, key, it)})"></div><div class="nm">${it.name}</div>`;
      d.addEventListener('click', () => onPick(key)); this.el.tray.appendChild(d); this.trayItems[key] = d;
    }
    this.el.tray.classList.remove('hidden');
  }
  markTray(key) { Object.entries(this.trayItems || {}).forEach(([k, d]) => d.classList.toggle('sel', k === key)); }
  chip(css, text, extra = '') { return `<div class="chip ${extra}"><span class="dot" style="background:${css}"></span>${text}</div>`; }
  markChipDone(key, done = true) { this.el.orderParts.querySelectorAll(`.chip[data-key="${key}"]`).forEach((c) => c.classList.toggle('done', done)); }

  // ================= 任务 =================
  newTask() {
    this.orderNo++;
    const T = this.G.newTask(this, this.task && this.task.name); this.task = T; this.recipe = T;   // recipe 别名给打分器读 name
    const E = this.el; E.orderNo.textContent = '#' + this.orderNo; E.orderName.textContent = T.name; E.orderLine.textContent = T.line || '';
    E.orderParts.innerHTML = T.chips || ''; E.orderSolids.innerHTML = T.foot1 || ''; E.orderGarnish.innerHTML = T.foot2 || '';
    E.orderSolids.classList.toggle('hidden', !T.foot1); E.orderGarnish.classList.toggle('hidden', !T.foot2);
    this.setPhase(this.G.phases[0]);
  }

  // ================= 阶段 =================
  setPhase(p) {
    this.phase = p; const E = this.el, order = this.G.phases; const cur = order.indexOf(p === 'reveal' || p === 'score' ? 'serve' : p);
    E.steps.forEach((s) => { const i = order.indexOf(s.dataset.step); s.classList.toggle('active', i === cur); s.classList.toggle('done', cur > i || p === 'score'); });
    E.pourHud.classList.add('hidden'); E.dock.classList.toggle('hidden', p === 'reveal' || p === 'score'); document.getElementById('order').classList.toggle('mini', p === 'reveal' || p === 'score');
    E.tray.classList.add('hidden'); E.meterWrap.classList.add('hidden'); E.undo.classList.add('hidden'); E.pourWarn.classList.add('hidden'); this.ui.hold(null); this.hideCoach(); this.el.praise.classList.add('hidden'); this.praiseLeft = 0;
    E.next.style.display = ''; E.next.disabled = false;
    if (p === 'reveal') { E.next.style.display = 'none'; const rv = this.G.revealViews || ['reveal0', 'reveal1', 'serve']; this.moveCam(rv[0]); this.queue = rv.slice(1).map((v, i, a) => ({ view: v, dur: i === a.length - 1 ? 0.85 : 1.8, then: i === a.length - 1 ? 'score' : null })); this.G.enter?.(this, p); return; }
    if (p === 'score') { E.next.style.display = 'none'; this.serveT = 0; return; }
    if (this.VIEWS[this.G.phaseView?.[p] || p]) this.moveCam(this.G.phaseView?.[p] || p);
    this.G.enter(this, p);
  }
  nextPhaseOf(p) { const o = this.G.phases, n = o[o.indexOf(p) + 1]; return n === 'serve' ? 'reveal' : n; }
  onNext() {
    const p = this.phase; if (p === 'reveal' || p === 'score' || !this.G.phases.includes(p)) return;
    if (this.G.canNext && this.G.canNext(this, p) === false) return;
    this.G.leave?.(this, p); sfx.pick(); this.setPhase(this.nextPhaseOf(p));
  }

  // ================= 镜头 =================
  onResize(aspect) {
    const k = Math.max(1.15, Math.min(1.8, 1.25 / aspect)); if (Math.abs(k - this.aspectK) < 0.01) return;
    this.aspectK = k; const f = this.w.scene.fog; if (f) { if (!f.userData) f.userData = { near: f.near, far: f.far }; f.near = f.userData.near * k; f.far = f.userData.far * k; }
    if (this.viewName) this.moveCam(this.viewName, 0, true);
  }
  viewPose(name) {
    const v = this.VIEWS[name], hs = this.hs; const tgt = new THREE.Vector3(v.tgt[0], v.tgt[1] * hs, v.tgt[2]);
    const dist = 1 + (hs - 1) * 0.6; const pos = new THREE.Vector3(v.pos[0], v.pos[1] * hs, v.pos[2]).sub(tgt).multiplyScalar(this.aspectK * dist).add(tgt);
    return { pos, tgt };
  }
  moveCam(name, dur = 0.85, instant = false) {
    if (!this.VIEWS[name]) return; this.viewName = name; const { pos, tgt } = this.viewPose(name);
    if (instant) { this.cam = null; this.camTarget = tgt; this.w.camera.position.copy(pos); this.w.camera.lookAt(tgt); return; }
    this.cam = { p0: this.w.camera.position.clone(), t0: this.camTarget ? this.camTarget.clone() : new THREE.Vector3(0, 1.5, 0), p1: pos, t1: tgt, t: 0, dur: dur || 0.85 };
  }

  // ================= 指针工具 =================
  ndc(e) { const r = this.dom.getBoundingClientRect(); return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1); }
  screenToPlane(e, y) { const ray = new THREE.Raycaster(); ray.setFromCamera(this.ndc(e), this.w.camera); const hit = new THREE.Vector3(); return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -y), hit) ? hit : null; }
  /** 屏幕 x 归一到 -1..1（相对手机容器） */
  screenX(e) { const r = this.dom.getBoundingClientRect(); return ((e.clientX - r.left) / r.width) * 2 - 1; }
  screenY(e) { const r = this.dom.getBoundingClientRect(); return ((e.clientY - r.top) / r.height) * 2 - 1; }

  // ================= 穿模检验（硬性条件） =================
  checkClipping() { return [...(this.G.clipping ? this.G.clipping(this) : []), ...this.checkAssembly(), ...this.checkPhysics()]; }
  /** 组装检验：部件不能散开/悬空（硬性规定 1） */
  checkAssembly() { return checkAssembly(this.w.scene); }
  /** 倒液物理（硬性规定 3）：各游戏实现 physics(core) */
  checkPhysics() { return this.G.physics ? this.G.physics(this) : []; }

  // ================= 结算 =================
  computeScore() {
    const { rows, tips } = this.G.score(this); let total = 0, wsum = 0;
    for (const r of rows) { r[1] = clamp(r[1]); total += r[1] * (r[2] ?? 1); wsum += (r[2] ?? 1); }
    const score = Math.round(total / Math.max(1e-6, wsum));
    const grade = score >= 93 ? 'S' : score >= 83 ? 'A' : score >= 71 ? 'B' : score >= 56 ? 'C' : 'D';
    if (!tips.length) tips.push(`无可挑剔 —— ${this.G.maker}。`);
    return { rows: rows.map((r) => [r[0], r[1]]), score, grade, tips };
  }
  showScore() {
    const s = this.computeScore(); this.setPhase('score'); const E = this.el;
    E.grade.textContent = s.grade; E.total.textContent = s.score + ' 分'; E.scoreName.textContent = `${this.task.name} · 第 ${this.orderNo} ${this.G.unit}`;
    E.lines.innerHTML = s.rows.map(([n, v]) => `<li><span>${n}</span><span class="bar"><i style="width:${v.toFixed(0)}%"></i></span><b>${v.toFixed(0)}</b></li>`).join('');
    E.tips.innerHTML = s.tips.map((t) => `<div>${t}</div>`).join('');
    const c = E.strip, g = c.getContext('2d'); g.clearRect(0, 0, c.width, c.height); g.fillStyle = '#efe7d8'; g.fillRect(0, 0, c.width, c.height); this.G.strip?.(this, g, c);
    E.score.classList.remove('hidden'); E.score.querySelector('.score-card').classList.toggle('perfect', s.grade === 'S');
    if (s.grade === 'S') this.celebrate(this.G.perfectText || '完美出品'); else if (s.grade === 'A') this.celebrate('漂亮', 0.45);
    s.score >= 71 ? sfx.done() : sfx.bad();
  }
  coach(type, text) { if (this.phase === 'reveal' || this.phase === 'score') return; const c = document.getElementById('coach'); c.className = type; c.querySelector('.txt').textContent = text; c.classList.remove('hidden'); this.coachLeft = 3.2; }
  hideCoach() { document.getElementById('coach').classList.add('hidden'); this.coachLeft = 0; }
  praise(text) { if (this.phase === 'reveal' || this.phase === 'score') return; const el = this.el.praise; el.textContent = text; el.classList.remove('hidden'); el.style.animation = 'none'; void el.offsetWidth; el.style.animation = ''; sfx.glass(); this.praiseLeft = 1.7; }
  celebrate(text, strength = 1) {
    const B = this.el.banner; B.querySelector('span').textContent = text; B.classList.remove('hidden'); const sp = B.querySelector('span'); sp.style.animation = 'none'; void sp.offsetWidth; sp.style.animation = '';
    clearTimeout(this._bannerT); this._bannerT = setTimeout(() => B.classList.add('hidden'), 2500);
    const [cx, cy, cz, rr] = this.G.celebrateAt ? this.G.celebrateAt(this) : [0, 3, 0, 1];
    const n = Math.round(140 * strength), pos = new Float32Array(n * 3), vel = [];
    for (let i = 0; i < n; i++) { const a = Math.random() * Math.PI * 2, r = rr * (0.6 + Math.random() * 0.6); pos[i * 3] = cx + Math.cos(a) * r; pos[i * 3 + 1] = cy + 0.1; pos[i * 3 + 2] = cz + Math.sin(a) * r; vel.push([Math.cos(a) * (0.6 + Math.random() * 1.4), 2.2 + Math.random() * 2.6, Math.sin(a) * (0.6 + Math.random() * 1.4)]); }
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    if (!this._sparkTex) { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'); const gr = g.createRadialGradient(32, 32, 2, 32, 32, 30); gr.addColorStop(0, 'rgba(255,240,200,1)'); gr.addColorStop(0.4, 'rgba(255,210,120,0.7)'); gr.addColorStop(1, 'rgba(255,200,100,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64); this._sparkTex = new THREE.CanvasTexture(c); }
    const pts = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffd27a, size: 0.16, map: this._sparkTex, transparent: true, opacity: 1, blending: THREE.AdditiveBlending, depthWrite: false }));   // 圆润的光点，不是方块 pts.renderOrder = 40; this.w.scene.add(pts);
    this.sparks = { pts, vel, t: 0, life: 2.4 }; sfx.done();
  }
  reset() { this.G.reset(this); this.newTask(); }

  // ================= 每帧 =================
  update(dt) {
    if (this.autoCtl) { const c = this.autoCtl; c.t = (c.t || 0) + dt; const done = c.wait != null ? c.t >= c.wait : c.step(dt); if (done) this.autoCtl = null; }
    if (this.cam) {
      const c = this.cam; c.t = Math.min(c.dur, c.t + dt); const k = smooth(c.t / c.dur);
      this.w.camera.position.lerpVectors(c.p0, c.p1, k); this.camTarget = new THREE.Vector3().lerpVectors(c.t0, c.t1, k); this.w.camera.lookAt(this.camTarget);
      if (c.t >= c.dur) { this.cam = null; const nx = this.queue.shift(); if (nx) { this.moveCam(nx.view, nx.dur); if (nx.then === 'score') this.pendingScore = true; } else if (this.pendingScore) { this.pendingScore = false; setTimeout(() => this.showScore(), 420); } }
    } else if (this.camTarget) {
      if (this.phase === 'score') { this.serveT += dt; const damp = Math.max(0, 1 - this.serveT / 8); const a = 0.21 * Math.sin(this.serveT * 0.55) * damp; const { pos } = this.viewPose('serve'); const r = Math.hypot(pos.x, pos.z); const a0 = Math.atan2(pos.x, pos.z); this.w.camera.position.set(Math.sin(a0 + a) * r, pos.y, Math.cos(a0 + a) * r); }
      this.w.camera.lookAt(this.camTarget);
    }
    if (this.coachLeft > 0) { this.coachLeft -= dt; if (this.coachLeft <= 0) this.hideCoach(); }
    if (this.praiseLeft > 0) { this.praiseLeft -= dt; if (this.praiseLeft <= 0) this.el.praise.classList.add('hidden'); }
    this.G.update(this, dt);
    if (this.sparks) { const S = this.sparks; S.t += dt; const pa = S.pts.geometry.attributes.position; for (let i = 0; i < S.vel.length; i++) { const v = S.vel[i]; v[1] -= 4.5 * dt; pa.array[i * 3] += v[0] * dt; pa.array[i * 3 + 1] += v[1] * dt; pa.array[i * 3 + 2] += v[2] * dt; } pa.needsUpdate = true; S.pts.material.opacity = Math.max(0, 1 - S.t / S.life); if (S.t >= S.life) { this.w.scene.remove(S.pts); this.sparks = null; } }
  }
}
