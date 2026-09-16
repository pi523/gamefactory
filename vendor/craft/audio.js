// 合成音效，无外部资源。注入声的基频随液位升高（真实的"瓶子装水"声学现象）。
let ctx = null;
const ensure = () => {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
};

function tone({ f = 440, f2 = f, t = 0.12, type = 'sine', gain = 0.15, delay = 0 }) {
  const c = ensure();
  const t0 = c.currentTime + delay;
  const o = c.createOscillator(); const g = c.createGain();
  o.type = type;
  o.frequency.setValueAtTime(f, t0);
  if (f2 !== f) o.frequency.exponentialRampToValueAtTime(Math.max(20, f2), t0 + t);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0008, t0 + t);
  o.connect(g).connect(c.destination);
  o.start(t0); o.stop(t0 + t + 0.02);
}

function noiseBuf(c, sec = 1.0) {
  const len = Math.ceil(c.sampleRate * sec);
  const buf = c.createBuffer(1, len, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  return buf;
}

function noise({ t = 0.18, gain = 0.12, hp = 800, lp = 6000, delay = 0 }) {
  const c = ensure();
  const t0 = c.currentTime + delay;
  const src = c.createBufferSource(); src.buffer = noiseBuf(c, t);
  const hpf = c.createBiquadFilter(); hpf.type = 'highpass'; hpf.frequency.value = hp;
  const lpf = c.createBiquadFilter(); lpf.type = 'lowpass'; lpf.frequency.value = lp;
  const g = c.createGain();
  g.gain.setValueAtTime(gain, t0);
  g.gain.exponentialRampToValueAtTime(0.0008, t0 + t);
  src.connect(hpf).connect(lpf).connect(g).connect(c.destination);
  src.start(t0);
}

// 持续注入声：带通噪声，中心频率跟液位走
let pour = null;
function pourStart() {
  const c = ensure();
  if (pour) return;
  const src = c.createBufferSource(); src.buffer = noiseBuf(c, 1.5); src.loop = true;
  const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.4; bp.frequency.value = 420;
  const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 5200;
  const g = c.createGain(); g.gain.value = 0;
  src.connect(bp).connect(lp).connect(g).connect(c.destination); src.start();
  pour = { src, bp, g };
}
function pourSet(level, flow) {          // level 0..1 液位；flow 0..1 流量
  if (!pour) return;
  const c = ensure();
  pour.bp.frequency.setTargetAtTime(320 + level * 1100, c.currentTime, 0.05);
  pour.g.gain.setTargetAtTime(flow > 0.02 ? 0.035 + flow * 0.085 : 0, c.currentTime, 0.06);
}
function pourStop() {
  if (!pour) return;
  const c = ensure(); const p = pour; pour = null;
  p.g.gain.setTargetAtTime(0, c.currentTime, 0.05);
  setTimeout(() => { try { p.src.stop(); } catch (e) { /* 已停 */ } }, 400);
}

export const sfx = {
  pourStart, pourSet, pourStop,
  drip()  { tone({ f: 1300, f2: 700, t: 0.09, type: 'sine', gain: 0.08 }); noise({ t: 0.05, gain: 0.03, hp: 2500, lp: 9000 }); },
  ice()   { tone({ f: 2100, f2: 1500, t: 0.07, type: 'triangle', gain: 0.07 }); noise({ t: 0.06, gain: 0.05, hp: 1800, lp: 9000 }); tone({ f: 900, f2: 600, t: 0.12, type: 'sine', gain: 0.04, delay: 0.02 }); },
  splash(){ noise({ t: 0.16, gain: 0.07, hp: 900, lp: 6000 }); },
  place() { tone({ f: 300, f2: 170, t: 0.1, type: 'triangle', gain: 0.12 }); },
  pick()  { tone({ f: 620, f2: 900, t: 0.06, type: 'square', gain: 0.05 }); },
  glass() { tone({ f: 2600, f2: 2400, t: 0.35, type: 'sine', gain: 0.05 }); },
  done()  { [523, 659, 784, 1046].forEach((f, i) => tone({ f, t: 0.35, type: 'triangle', gain: 0.09, delay: i * 0.09 })); },
  bad()   { tone({ f: 180, f2: 120, t: 0.25, type: 'sawtooth', gain: 0.07 }); },
};
