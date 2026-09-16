import * as THREE from 'three';

/** 蒸汽：一小群向上飘、越飘越淡越大的贴图精灵（Sprite 比 Points 稳：alpha 一定生效，不会出黑方块）。 */
export class Steam {
  constructor(scene, n = 60) {
    const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 2, 32, 32, 30); gr.addColorStop(0, 'rgba(255,255,255,.7)'); gr.addColorStop(0.5, 'rgba(255,255,255,.25)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    this.tex = new THREE.CanvasTexture(c);
    this.group = new THREE.Group(); this.group.renderOrder = 35; scene.add(this.group);
    this.items = [];
    for (let i = 0; i < n; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, transparent: true, opacity: 0, depthWrite: false, fog: false }));
      sp.visible = false; this.group.add(sp); this.items.push({ sp, life: -1, vel: [0, 0, 0] });
    }
    this.src = new THREE.Vector3(0, 3, 0); this.r = 0.5; this.intensity = 0; this.acc = 0;
  }
  set(x, y, z, r, intensity) { this.src.set(x, y, z); this.r = r; this.intensity = intensity; }
  update(dt) {
    this.acc += dt * this.intensity * 14;
    while (this.acc >= 1) {
      this.acc -= 1; const it = this.items.find((o) => o.life < 0); if (!it) break;
      const a = Math.random() * 6.28, rr = Math.sqrt(Math.random()) * this.r;
      it.sp.position.set(this.src.x + Math.cos(a) * rr, this.src.y, this.src.z + Math.sin(a) * rr); it.vel = [(Math.random() - 0.5) * 0.25, 0.5 + Math.random() * 0.45, (Math.random() - 0.5) * 0.25]; it.life = 0; it.sp.visible = true;
    }
    for (const it of this.items) {
      if (it.life < 0) continue; it.life += dt;
      if (it.life > 2.4) { it.life = -1; it.sp.visible = false; continue; }
      it.vel[0] += (Math.random() - 0.5) * 0.4 * dt; it.vel[2] += (Math.random() - 0.5) * 0.4 * dt;
      it.sp.position.x += it.vel[0] * dt; it.sp.position.y += it.vel[1] * dt; it.sp.position.z += it.vel[2] * dt;
      const k = it.life / 2.4; const s = 0.35 + k * 0.9; it.sp.scale.set(s, s, 1);
      it.sp.material.opacity = 0.55 * Math.sin(Math.min(1, k) * Math.PI) * Math.min(1, this.intensity + 0.2);
    }
  }
}

/** 沸腾的气泡：从锅底冒上来、到水面破掉的小球（Sprite），强度 = 火力 */
export class Bubbles {
  constructor(scene, n = 50) {
    const c = document.createElement('canvas'); c.width = c.height = 32; const g = c.getContext('2d');
    g.strokeStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 2.2; g.beginPath(); g.arc(16, 16, 11, 0, Math.PI * 2); g.stroke();
    g.fillStyle = 'rgba(255,255,255,.35)'; g.beginPath(); g.arc(12, 12, 4, 0, Math.PI * 2); g.fill();
    const map = new THREE.CanvasTexture(c); this.items = []; this.g = new THREE.Group(); this.g.renderOrder = 33; scene.add(this.g);
    for (let i = 0; i < n; i++) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map, transparent: true, opacity: 0, depthWrite: false })); s.scale.setScalar(0.08); this.g.add(s); this.items.push({ s, t: 2, life: 1, x: 0, z: 0, k: 1 }); }
    this.src = new THREE.Vector3(); this.r = 0.5; this.bottom = 0; this.top = 1; this.intensity = 0;
  }
  set(x, z, bottom, top, r, intensity) { this.src.set(x, 0, z); this.bottom = bottom; this.top = top; this.r = r; this.intensity = intensity; }
  update(dt) {
    for (const it of this.items) {
      it.t += dt;
      if (it.t >= it.life) { if (Math.random() < this.intensity * dt * 3) { it.t = 0; it.life = 0.5 + Math.random() * 0.6; const a = Math.random() * 6.28, rr = Math.sqrt(Math.random()) * this.r; it.x = Math.cos(a) * rr; it.z = Math.sin(a) * rr; it.k = 0.5 + Math.random() * 0.8; } else { it.s.material.opacity = 0; continue; } }
      const f = it.t / it.life; const y = this.bottom + (this.top - this.bottom) * f;
      it.s.position.set(this.src.x + it.x + Math.sin(it.t * 9 + it.k) * 0.02, y, this.src.z + it.z); it.s.scale.setScalar((0.05 + 0.06 * f) * it.k); it.s.material.opacity = f < 0.9 ? 0.55 : (1 - f) * 5.5;
    }
  }
}
