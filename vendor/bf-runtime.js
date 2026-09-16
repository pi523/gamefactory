/**
 * bf-runtime.js —— 黑灯工厂共享运行时（v1）。生成的游戏只写玩法，底座全在这里：
 *  - 固定手机竖屏 #stage（手机铺满、宽屏居中留黑）、canvas 100%、像素密度处理
 *  - 正交相机：1 世界单位 = 1 个 stage CSS 像素；对外一律用 stage 像素坐标（左上为原点、y 向下），运行时内部做 y 翻转
 *  - 背景 cover 铺法 + 布局锚点（slots / path）到 stage 像素的映射
 *  - 贴图面片（受光、alphaTest）+ 脚下软阴影 + 命中光斑 + 连击飘字
 *  - HUD（金色分数/命数 SVG 心形/计时）与 menu/over 面板，主题 CSS 由运行时注入
 *  - 调试契约 window.__bf：固定步长、确定性 rng、reset/start/setTimeScale/state
 * 游戏实现一个对象：{ init(rt), reset(rt, rng), step(rt, dt), onTap(rt,x,y), onDown(rt,x,y), onMove(rt,x,y,dx,dy), onUp(rt,x,y,gesture), targets(rt) }
 *   gesture = {type:'tap'|'drag'|'swipe', dx, dy, dir:'left'|'right'|'up'|'down'|null, ms}；targets 元素 {id,kind,x,y,w,h,action:'tap'|'drag'|'swipe', to:{x,y}?, dir?, anchored?}
 *   贴图可多状态：BF_ASSETS[kind] 为数组（单状态）或 {状态:[url...]}；sp.setState('金黄') 切换
 */
import * as THREE from 'three';

export const DT = 1 / 60;   // v3：新手引导（自动教每种动词）+ 情绪反馈（连击赞美/星级/纪录）
export const DESIGN_H = 844;

export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const THEME_CSS = `
#stage{--bf-bg:#0d0b0a;--bf-bg-outer:#050403;--bf-panel:rgba(20,16,14,.72);--bf-panel-strong:rgba(20,16,14,.86);--bf-accent:#c9a86a;--bf-accent-dim:rgba(201,168,106,.55);--bf-text:#f3ede4;--bf-text-dim:#b8ae9f;--bf-danger:#e2574a;--bf-radius:14px;--bf-font:system-ui,-apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif}
html,body{margin:0;height:100%;overflow:hidden;background:#050403;font-family:var(--bf-font,system-ui);-webkit-user-select:none;user-select:none;color:var(--bf-text)}
#stage{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);overflow:hidden;background:var(--bf-bg)}
#bg{position:absolute;inset:0;background-size:cover;background-position:center;transition:opacity .6s ease}
#bg::after{content:"";position:absolute;inset:0;background:linear-gradient(rgba(0,0,0,.55),transparent 14%),radial-gradient(ellipse at 50% 60%,transparent 55%,rgba(0,0,0,.45))}
#stage canvas{position:absolute;left:0;top:0;width:100%;height:100%;display:block;touch-action:none}
#hud{position:absolute;inset:0;pointer-events:none;z-index:2}
.bf-panel{position:absolute;background:var(--bf-panel);border:1px solid var(--bf-accent-dim);border-radius:var(--bf-radius);padding:8px 12px;backdrop-filter:blur(6px)}
.bf-label{font-size:12px;letter-spacing:.08em;color:var(--bf-text-dim)}
.bf-num{font-size:28px;font-weight:600;color:var(--bf-accent);line-height:1.05}
#bf-score{left:12px;top:12px;min-width:64px}
#bf-timer{left:50%;top:12px;transform:translateX(-50%);text-align:center;display:none}
#bf-lives{right:68px;top:12px;display:flex;gap:6px;align-items:center;height:44px;box-sizing:border-box}
#bf-lives svg{width:22px;height:22px;transition:transform .2s}
#bf-lives svg.hit{animation:bf-shake .22s}
@keyframes bf-shake{0%{transform:translateX(0)}25%{transform:translateX(-4px)}50%{transform:translateX(4px)}75%{transform:translateX(-3px)}100%{transform:translateX(0)}}
#bf-btn{position:absolute;right:12px;top:12px;width:44px;height:44px;border-radius:50%;border:1.5px solid var(--bf-accent-dim);background:var(--bf-panel);display:flex;align-items:center;justify-content:center;color:var(--bf-accent);font-size:18px}
#overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;z-index:3;background:rgba(0,0,0,.28)}
#overlay[hidden]{display:none}
.bf-menu{display:flex;flex-direction:column;align-items:center;gap:26px}
.bf-start{width:112px;height:112px;border-radius:50%;border:2px solid var(--bf-accent);background:radial-gradient(circle at 50% 40%,rgba(60,42,28,.9),rgba(20,16,14,.9));display:flex;align-items:center;justify-content:center;color:var(--bf-accent);font-size:26px;font-weight:700;letter-spacing:.1em;box-shadow:0 0 0 0 rgba(201,168,106,.45);animation:bf-pulse 1.8s ease-out infinite}
@keyframes bf-pulse{0%{box-shadow:0 0 0 0 rgba(201,168,106,.45)}70%{box-shadow:0 0 0 22px rgba(201,168,106,0)}100%{box-shadow:0 0 0 0 rgba(201,168,106,0)}}
.bf-card{width:min(86%,340px);box-sizing:border-box;padding:26px 24px;border-radius:20px;background:var(--bf-panel-strong);border:1px solid var(--bf-accent-dim);text-align:center;backdrop-filter:blur(8px)}
.bf-title{font-size:32px;font-weight:700;color:var(--bf-accent);margin:0 0 10px}
.bf-sub{font-size:16px;color:var(--bf-text-dim);margin:0 0 6px}
.bf-big{font-size:44px;font-weight:700;color:var(--bf-text);margin:6px 0 14px}
.bf-hint{font-size:15px;color:var(--bf-text-dim);animation:bf-breathe 1.8s ease-in-out infinite}
@keyframes bf-breathe{0%,100%{opacity:.55}50%{opacity:1}}
.bf-fx{position:absolute;pointer-events:none;z-index:2;transform:translate(-50%,-50%)}
.bf-flash{width:120px;height:120px;border-radius:50%;background:radial-gradient(rgba(255,190,110,.9),rgba(255,140,50,.35) 45%,transparent 70%);animation:bf-flash .18s ease-out forwards}
@keyframes bf-flash{from{transform:translate(-50%,-50%) scale(.5);opacity:1}to{transform:translate(-50%,-50%) scale(1.6);opacity:0}}
.bf-fire{position:absolute;left:14px;bottom:15%;width:64px;padding:8px 6px 6px;border-radius:14px;background:rgba(20,24,34,.72);border:1px solid rgba(242,178,60,.35);display:flex;flex-direction:column;align-items:center;gap:5px;z-index:3;pointer-events:none}.bf-fire b{font-size:11px;color:var(--bf-accent);letter-spacing:.1em}.bf-fire i{display:block;width:40px;height:16px;border-radius:5px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}.bf-fire i.on{background:linear-gradient(#ffd67a,#ff7a1a);box-shadow:0 0 10px rgba(255,140,40,.7);border-color:transparent}.bf-fire small{font-size:11px;color:#eee}.bf-fire i.next{animation:bf-firenext .5s steps(1) infinite;border-color:var(--bf-accent)}@keyframes bf-firenext{0%{background:rgba(255,255,255,.08)}50%{background:linear-gradient(#ffd67a,#ff7a1a);box-shadow:0 0 12px rgba(255,140,40,.9)}}.bf-fire.want{border-color:var(--bf-accent);animation:bf-firewant .6s ease-in-out infinite alternate}@keyframes bf-firewant{from{box-shadow:0 0 0 0 rgba(242,178,60,.0);background:rgba(20,24,34,.72)}to{box-shadow:0 0 18px 4px rgba(242,178,60,.75);background:rgba(90,60,20,.9)}}.bf-flame{position:absolute;width:170px;height:44px;border-radius:50%;transform:translate(-50%,-50%);background:radial-gradient(ellipse at center,rgba(120,180,255,.7),rgba(255,160,70,.42) 45%,rgba(255,110,30,.18) 62%,transparent 75%);filter:blur(1.5px);mix-blend-mode:screen;pointer-events:none;transition:transform .35s,opacity .35s;animation:bf-breathe 1.1s ease-in-out infinite;z-index:1}
.bf-bubble{width:6px;height:6px;border-radius:50%;background:radial-gradient(rgba(255,240,200,.95),rgba(255,200,120,.5) 60%,transparent 75%);pointer-events:none;z-index:2;animation:bf-bubble .42s ease-out forwards}@keyframes bf-bubble{from{transform:translate(-50%,-50%) scale(.6);opacity:.9}to{transform:translate(calc(-50% + var(--bx,0px)),calc(-50% - 26px)) scale(1.4);opacity:0}}
.bf-drop{position:absolute;width:9px;height:9px;box-shadow:0 0 3px rgba(0,0,0,.35);border-radius:50%;pointer-events:none;z-index:2;animation:bf-drop .5s ease-in forwards}@keyframes bf-drop{from{transform:translate(-50%,-50%) scale(1);opacity:.95}to{transform:translate(-50%,calc(-50% + var(--fall,90px))) scale(.6);opacity:0}}
.bf-steam{width:26px;height:64px;border-radius:50%;background:linear-gradient(to top,rgba(255,255,255,0),rgba(255,255,255,.75) 35%,rgba(255,255,255,.5) 70%,rgba(255,255,255,0));filter:blur(2.2px);animation:bf-steam 2.8s ease-out forwards;pointer-events:none;opacity:0}
@keyframes bf-steam{0%{transform:translate(-50%,-50%) scaleY(.6) rotate(-4deg);opacity:0}15%{opacity:.7}60%{opacity:.4;transform:translate(-30%,-180%) scale(1.3,1.6) rotate(5deg)}100%{transform:translate(-10%,-330%) scale(1.8,2.1) rotate(-3deg);opacity:0}}
.bf-combo{font-size:22px;font-weight:600;color:var(--bf-accent);text-shadow:0 1px 3px #000;animation:bf-combo .45s ease-out forwards}
#bf-hint{position:absolute;inset:0;pointer-events:none;z-index:4}
.bf-finger{position:absolute;width:56px;height:56px;transform:translate(-50%,-50%);filter:drop-shadow(0 4px 8px rgba(0,0,0,.6))}
.bf-finger svg{width:100%;height:100%}
.bf-finger.tap{animation:bf-tap 1s ease-in-out infinite}
@keyframes bf-tap{0%,100%{transform:translate(-50%,-50%) scale(1)}50%{transform:translate(-50%,-40%) scale(.85)}}
.bf-ring{position:absolute;width:90px;height:90px;border-radius:50%;border:3px solid var(--bf-accent);transform:translate(-50%,-50%);animation:bf-ring 1.2s ease-out infinite}
@keyframes bf-ring{from{transform:translate(-50%,-50%) scale(.6);opacity:1}to{transform:translate(-50%,-50%) scale(1.5);opacity:0}}
.bf-arrow{position:absolute;height:4px;background:linear-gradient(90deg,rgba(201,168,106,.1),var(--bf-accent));transform-origin:0 50%;border-radius:2px}
.bf-arrow::after{content:"";position:absolute;right:-2px;top:-8px;border:10px solid transparent;border-left:14px solid var(--bf-accent);border-right:0}
.bf-hint-text{position:absolute;transform:translate(-50%,0);background:var(--bf-panel-strong);border:1px solid var(--bf-accent-dim);color:var(--bf-text);font-size:16px;padding:8px 14px;border-radius:12px;white-space:nowrap;animation:bf-breathe 1.6s ease-in-out infinite}
.bf-praise{position:absolute;left:50%;top:38%;transform:translate(-50%,-50%);font-size:44px;font-weight:800;color:var(--bf-accent);text-shadow:0 2px 0 #4a3a1a,0 6px 18px rgba(255,150,60,.55);pointer-events:none;z-index:4;letter-spacing:.04em;animation:bf-praise 1.1s cubic-bezier(.2,1.4,.4,1) forwards;white-space:nowrap}
@keyframes bf-praise{0%{transform:translate(-50%,-50%) scale(.3);opacity:0}25%{transform:translate(-50%,-50%) scale(1.15);opacity:1}70%{transform:translate(-50%,-50%) scale(1);opacity:1}100%{transform:translate(-50%,-70%) scale(1);opacity:0}}
.bf-glow{position:absolute;inset:0;pointer-events:none;z-index:1;background:radial-gradient(ellipse at 50% 60%,rgba(255,170,80,.28),transparent 65%);animation:bf-glow .9s ease-out forwards}
@keyframes bf-glow{from{opacity:1}to{opacity:0}}
.bf-spark{position:absolute;width:8px;height:8px;border-radius:50%;background:#ffd67a;box-shadow:0 0 8px #ffb347;pointer-events:none;z-index:4;animation:bf-spark 1s ease-out forwards}
@keyframes bf-spark{to{transform:translate(var(--dx),var(--dy)) scale(.2);opacity:0}}
.bf-stars{font-size:30px;letter-spacing:6px;margin:4px 0 2px;color:var(--bf-accent)}
.bf-recipe{width:min(88%,360px);box-sizing:border-box;padding:22px 22px 18px;border-radius:20px;background:var(--bf-panel-strong);border:1px solid var(--bf-accent-dim);text-align:left}
.bf-recipe h2{margin:0 0 12px;font-size:22px;color:var(--bf-accent);text-align:center}
.bf-recipe ol{margin:0;padding-left:22px;color:var(--bf-text);font-size:16px;line-height:1.6}
.bf-recipe .bf-hint{text-align:center;margin-top:12px}
#bf-step{position:absolute;left:50%;top:13%;transform:translateX(-50%);pointer-events:none;z-index:3;background:var(--bf-panel-strong);border:1px solid var(--bf-accent-dim);color:var(--bf-text);padding:8px 16px;border-radius:var(--bf-radius);font-size:16px;white-space:nowrap;max-width:92%;overflow:hidden;text-overflow:ellipsis}
#bf-step b{color:var(--bf-accent);margin-right:6px}
.bf-verdict{position:absolute;left:50%;top:30%;transform:translate(-50%,-50%);pointer-events:none;z-index:4;padding:12px 18px;border-radius:16px;font-size:18px;font-weight:600;max-width:86%;text-align:center;background:var(--bf-panel-strong);border:1.5px solid var(--bf-accent);color:var(--bf-text);animation:bf-verdict 2.2s ease-out forwards}
.bf-verdict.bad{border-color:var(--bf-danger)} .bf-verdict small{display:block;font-weight:400;color:var(--bf-text-dim);margin-top:4px;font-size:14px}
@keyframes bf-verdict{0%{transform:translate(-50%,-50%) scale(.7);opacity:0}12%{transform:translate(-50%,-50%) scale(1);opacity:1}80%{opacity:1}100%{opacity:0}}
.bf-learned{text-align:left;font-size:15px;color:var(--bf-text);margin:8px 0 6px;padding-left:18px;line-height:1.55}
.bf-record{font-size:15px;color:#ffd67a;font-weight:700;margin:0 0 6px}
@keyframes bf-combo{from{transform:translate(-50%,-50%) translateY(0);opacity:1}to{transform:translate(-50%,-50%) translateY(-22px);opacity:0}}
`;

const HEART = (filled) => `<svg viewBox="0 0 24 24" fill="${filled ? 'rgba(201,168,106,.9)' : 'none'}" stroke="#c9a86a" stroke-width="1.5"><path d="M12 21s-7-4.6-9.3-9.1C1 8.3 3.4 4.5 7.2 4.5c2 0 3.5 1.1 4.8 2.6 1.3-1.5 2.8-2.6 4.8-2.6 3.8 0 6.2 3.8 4.5 7.4C19 16.4 12 21 12 21z"/></svg>`;

export class Runtime {
  constructor(game, assets, opts = {}) {
    this.game = game; this.assets = assets || {}; this.opts = opts;
    this.stage = document.getElementById('stage');
    if (!this.stage) throw new Error('缺少 #stage');
    document.head.appendChild(Object.assign(document.createElement('style'), { textContent: THEME_CSS }));
    // DOM 层：#bg < canvas < #hud < #overlay
    this.bg = this.stage.querySelector('#bg') || this.stage.insertBefore(Object.assign(document.createElement('div'), { id: 'bg' }), this.stage.firstChild);
    this.canvas = this.stage.querySelector('canvas') || this.stage.appendChild(document.createElement('canvas'));
    this.hud = this.stage.querySelector('#hud') || this.stage.appendChild(Object.assign(document.createElement('div'), { id: 'hud' }));
    this.overlay = this.stage.querySelector('#overlay') || this.stage.appendChild(Object.assign(document.createElement('div'), { id: 'overlay' }));
    this.hud.innerHTML = `<div class="bf-panel" id="bf-score"><div class="bf-label">${opts.scoreLabel || '分数'}</div><div class="bf-num" id="bf-score-n">0</div></div>
      <div class="bf-panel" id="bf-timer"><div class="bf-label">${opts.timerLabel || '剩余'}</div><div class="bf-num" id="bf-timer-n">0</div></div>
      <div class="bf-panel" id="bf-lives"></div><div id="bf-btn">↻</div>`;
    const sty = this.assets.__style || {};                     // 每款游戏从参考学来的风格：配色/圆角/字体
    const pal = sty.ui_palette || {};
    const hex2rgba = (h, a) => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ''); if (!m) return null; const n = parseInt(m[1], 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };
    const setv = (k, v) => { if (v) this.stage.style.setProperty(k, v); };
    setv('--bf-bg', pal.bg); setv('--bf-bg-outer', pal.bg); setv('--bf-accent', pal.accent); setv('--bf-accent-dim', hex2rgba(pal.accent, .55));
    setv('--bf-text', pal.text); setv('--bf-danger', pal.danger); setv('--bf-panel', hex2rgba(pal.panel, .78)); setv('--bf-panel-strong', hex2rgba(pal.panel, .92));
    if (sty.ui_radius) setv('--bf-radius', sty.ui_radius); if (sty.ui_font) setv('--bf-font', sty.ui_font);
    if (this.assets.__scene && this.assets.__scene.portrait) this.bg.style.backgroundImage = `url(${this.assets.__scene.portrait})`;
    // 背景变体（火力档 × 蒸汽帧，同一张照片原地改）：第二层用于交叉淡入
    this.bg2 = this.stage.querySelector('#bg2') || this.stage.insertBefore(Object.assign(document.createElement('div'), { id: 'bg2' }), this.bg.nextSibling);
    this.bg2.style.cssText = 'position:absolute;inset:0;background-size:cover;background-position:center;opacity:0;transition:opacity .6s ease;pointer-events:none';
    this.bgCur = this.assets.__scene && this.assets.__scene.portrait; this.bgFront = false;
    if (this.assets.__scene) for (const u of Object.values(this.assets.__scene)) { const im = new Image(); im.src = u; }   // 预加载变体
    else this.bg.style.background = 'radial-gradient(ellipse at 50% 40%,#2a1d14,#0d0b0a 75%)';

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(0, 1, 1, 0, -1000, 1000); this.camera.position.z = 100;
    this.scene.add(new THREE.HemisphereLight(0xfff1dc, 0x2a1d14, 0.9));
    const sun = new THREE.DirectionalLight(0xffc27a, 1.1); sun.position.set(300, 600, 500); this.scene.add(sun);
    this.hintLayer = this.stage.appendChild(Object.assign(document.createElement('div'), { id: 'bf-hint' }));
    this.taught = {}; this.hintEl = null; this.hintAction = null; this.ui = { hintsShown: 0, praisesShown: 0 };
    this.streak = 0; this.lastScoreAt = -1e9; this.praised = {}; this.best = 0;
    this.lesson = opts.lesson || null;                       // 厂房：教学课 {dish, steps:[{id,craft,verb,kind,stop_cue,fail_surface}], learned_card:[]}
    if (this.lesson) { const lv = this.hud.querySelector('#bf-lives'); if (lv) lv.style.display = 'none'; }   // 教学课没有命数，不显示心
    this.lessonState = { step: 0, results: [], stars: 0, verdicts: 0 };
    try { this.best = Number(localStorage.getItem('bf-best-' + (opts.title || location.pathname)) || 0); } catch (e) { this.best = 0; }
    this.hints = Object.assign({ tap: '点它', drag: '拖到这里', swipe: '往这边滑' }, opts.hints || {});
    this.tutorialSlow = opts.tutorialSlow != null ? opts.tutorialSlow : 0.45;   // 引导显示期间仿真减速倍率（第一次学每个动词时）
    this.teachTimes = opts.teachTimes || 2;                                     // 每个动词做对几次才算学会
    this.taughtCount = {};
    this.praiseWords = opts.praise || { 3: '漂亮！', 5: '太棒了！', 8: '火力全开！', 12: '神级手艺！' };
    this.milestones = opts.milestones || { 1: '开张！', 5: '上手了！', 10: '越来越熟练！', 20: '摊主本色！', 40: '传奇手艺！' };   // 按分数的里程碑赞美（慢节奏玩法靠这个）
    this.streakWindow = opts.streakWindow || 4.0; this.hitMilestones = {};
    this.textures = {}; this.fx = []; this.errors = [];
    this.timeScale = 1; this.acc = 0; this.last = 0; this.ready = false; this.tweens = [];   // tweens: 状态渐变/淡入，随 timeScale 走
    this.phase = 'menu'; this.score = 0; this.lives = 3; this.maxLives = 3; this.t = 0; this.tick = 0; this.timer = null;
    this.resize(); window.addEventListener('resize', () => this.resize());
    this.canvas.addEventListener('pointerdown', (e) => this._pointer(e));
    this.canvas.addEventListener('pointermove', (e) => this._pointerMove(e));
    this.canvas.addEventListener('pointerup', (e) => this._pointerUp(e));
    this.canvas.addEventListener('pointercancel', (e) => this._pointerUp(e));
    this.game.init && this.game.init(this);
    this.reset(1);
    this._load().then(() => { this.ready = true; });
    requestAnimationFrame((t) => this._frame(t));
    window.__bf = {
      version: 1, get ready() { return rt.ready; }, reset: (s) => rt.reset(s), start: () => rt.start(),
      setTimeScale: (k) => rt.setTimeScale(k), state: () => rt.state(), get errors() { return rt.errors; },
      get __rt() { return rt; },   // 调试用：场景/精灵检查
    };
    const rt = this;
  }

  // ---------- stage / 坐标 ----------
  resize() {
    const vw = window.innerWidth, vh = window.innerHeight;
    let h = vh, w = Math.round(h * 9 / 16); if (w > vw) { w = vw; h = vh; }
    this.stage.style.width = w + 'px'; this.stage.style.height = h + 'px';
    this.SW = w; this.SH = h; this.k = h / DESIGN_H;
    this.renderer.setSize(w, h, false);
    this.camera.left = 0; this.camera.right = w; this.camera.top = h; this.camera.bottom = 0; this.camera.updateProjectionMatrix();
    this.rect = this.stage.getBoundingClientRect();
    this.game.onResize && this.game.onResize(this);
  }
  /** 背景 cover 铺满时，图内归一化坐标 → stage 像素 */
  coverMap(nx, ny) {
    const L = this.assets.__layout || {}; const iw = L.img_w || 9, ih = L.img_h || 16;
    const s = Math.max(this.SW / iw, this.SH / ih), w = iw * s, h = ih * s;
    return { x: (this.SW - w) / 2 + nx * w, y: (this.SH - h) / 2 + ny * h, pxPerImgW: s * iw };
  }
  /** 备料台锚点（原地生成的碟/瓶）→ [{name,x,y,side}] stage 像素；没有则 [] */
  pantry() {
    const L = this.assets.__layout; if (!L || !L.pantry) return [];
    return L.pantry.map((p) => { const q = this.coverMap(p.x, p.y); return { name: p.name, x: q.x, y: q.y, side: p.side * q.pxPerImgW }; });
  }
  /** 切换背景变体（__scene 里的键，如 fire0_s0）：两层交叉淡入，同一张照片只有火苗/蒸汽在变 */
  setScene(key) {
    const u = this.assets.__scene && this.assets.__scene[key]; if (!u || u === this.bgCur) return;
    const [show, hide] = this.bgFront ? [this.bg, this.bg2] : [this.bg2, this.bg];
    show.style.backgroundImage = `url(${u})`; show.style.transition = 'opacity .6s ease'; hide.style.transition = 'opacity .6s ease';
    show.style.opacity = 1; hide.style.opacity = 0; this.bgFront = !this.bgFront; this.bgCur = u;
  }
  /** 效果层锚点（原地生成的火苗/蒸汽）→ {name:{x,y,side}} stage 像素 */
  effects() {
    const L = this.assets.__layout; if (!L || !L.effects) return {};
    const out = {}; for (const [k, p] of Object.entries(L.effects)) { const q = this.coverMap(p.x, p.y); out[k] = { x: q.x, y: q.y, side: p.side * q.pxPerImgW }; } return out;
  }
  /** slots 布局 → [{x,y,r}] stage 像素；没有布局时按 fallback 网格生成 */
  anchors(fallback = { cols: 3, rows: 3 }) {
    const L = this.assets.__layout;
    if (L && L.type === 'slots' && L.slots && L.slots.length) {
      return L.slots.map((s) => { const p = this.coverMap(s.x, s.y); const a = { x: p.x, y: p.y, r: s.r * p.pxPerImgW };
        if (s.pool) { const q = this.coverMap(s.pool.x, s.pool.y); a.pool = { x: q.x, y: q.y, rx: s.pool.rx * q.pxPerImgW, ry: s.pool.ry * q.pxPerImgW }; }   // 锅底油面椭圆：食材真正躺的地方
        return a; });
    }
    const out = []; const cw = this.SW / (fallback.cols + 1), rh = this.SH * 0.35 / fallback.rows;
    for (let r = 0; r < fallback.rows; r++) for (let c = 0; c < fallback.cols; c++) out.push({ x: cw * (c + 1), y: this.SH * 0.45 + rh * r, r: Math.min(cw, rh) * 0.38 });
    return out;
  }
  /** path 布局 → {points:[{x,y}], width} stage 像素；没有布局时给一条 55% 高的横线 */
  path() {
    const L = this.assets.__layout;
    if (L && L.type === 'path' && L.points && L.points.length > 1) {
      const pts = L.points.map((p) => { const q = this.coverMap(p.x, p.y); return { x: q.x, y: q.y }; });
      return { points: pts, width: (L.width || 0.06) * this.SH };
    }
    return { points: [{ x: -40, y: this.SH * 0.55 }, { x: this.SW + 40, y: this.SH * 0.55 }], width: this.SH * 0.06 };
  }
  /** 把物件放进锅/格子：中心略高于锅心（俯视透视），阴影落在锅底。slot 来自 anchors()；k 为冒头缩放 0..1 */
  placeInSlot(sp, slot, k = 1) {
    const minSize = slot.r * 1.8;                      // 物件屏幕尺寸不得小于锚点半径×1.8，否则观察者看不清状态
    const boost = sp.size < minSize ? minSize / sp.size : 1;
    sp.setScale(k * boost); sp.setCenter(slot.x, slot.y - slot.r * 0.12);
    sp.shadow.position.y = this.SH - (slot.y + slot.r * 0.25); return sp;
  }
  /** 点是否在精灵包围盒内（给 onDown/onTap 找被按的物件） */
  hit(sp, x, y, pad = 1.2) { const b = sp.box(); return Math.abs(x - b.x) <= b.w * 0.5 * pad && Math.abs(y - b.y) <= b.h * 0.5 * pad; }
  /** 离 (x,y) 最近的锚点及距离 */
  nearestAnchor(anchors, x, y) { let best = null, bd = Infinity; for (const a of anchors) { const d = Math.hypot(a.x - x, a.y - y); if (d < bd) { bd = d; best = a; } } return { anchor: best, dist: bd }; }
  /** 沿路径按 0..1 参数取点 */
  pathAt(u) {
    const P = this.path().points; let total = 0; const segs = [];
    for (let i = 0; i < P.length - 1; i++) { const d = Math.hypot(P[i + 1].x - P[i].x, P[i + 1].y - P[i].y); segs.push(d); total += d; }
    let dist = Math.max(0, Math.min(1, u)) * total;
    for (let i = 0; i < segs.length; i++) {
      if (dist <= segs[i] || i === segs.length - 1) { const f = segs[i] ? dist / segs[i] : 0; return { x: P[i].x + (P[i + 1].x - P[i].x) * f, y: P[i].y + (P[i + 1].y - P[i].y) * f }; }
      dist -= segs[i];
    }
    return P[P.length - 1];
  }

  // ---------- 资源 ----------
  async _load() {
    const loader = new THREE.TextureLoader(); const jobs = [];
    for (const [k, val] of Object.entries(this.assets)) {
      if (k.startsWith('__')) continue;
      const states = Array.isArray(val) ? { '默认': val } : (val && typeof val === 'object' ? val : null);
      if (!states) continue;
      this.textures[k] = {};
      for (const [st, urls] of Object.entries(states)) {
        this.textures[k][st] = [];
        for (const u of (urls || [])) jobs.push(new Promise((res) => loader.load(u, (tex) => { tex.colorSpace = THREE.SRGBColorSpace; this.textures[k][st].push(tex); res(); }, undefined, () => res())));
      }
    }
    await Promise.all(jobs);
  }
  /** 贴图面片 + 阴影。size = 屏幕像素直径；无贴图时用带颜色的圆盘占位 */
  /** 接触阴影贴图：径向渐变，中心深、边缘透明（缓存一张） */
  _shadowTex() {
    if (this._shTex) return this._shTex;
    const c = document.createElement('canvas'); c.width = c.height = 128; const ctx = c.getContext('2d');
    const gr = ctx.createRadialGradient(64, 64, 4, 64, 64, 64); gr.addColorStop(0, 'rgba(0,0,0,1)'); gr.addColorStop(0.55, 'rgba(0,0,0,.55)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gr; ctx.fillRect(0, 0, 128, 128); const tex = new THREE.CanvasTexture(c); this._shTex = tex; return tex;
  }
  /** 把抠图贴图处理成"躺在锅里"的样子：轮廓羽化、边缘压暗、整体偏暖偏暗（缓存） */
  _feather(tex, strength = 1) {
    if (!tex || !tex.image || !tex.image.width) return tex;
    const key = 'feathered' + strength; if (tex.userData[key]) return tex.userData[key];
    const img = tex.image, w = img.width, h = img.height, c = document.createElement('canvas'); c.width = w; c.height = h;
    const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0); const d = ctx.getImageData(0, 0, w, h), px = d.data;
    const r = Math.max(2, Math.round(w * 0.035 * strength));             // 羽化半径 ≈ 3.5% 边长（×强度）
    const a = new Float32Array(w * h); for (let i = 0; i < w * h; i++) a[i] = px[i * 4 + 3] / 255;
    const tmp = new Float32Array(w * h), box = (src, dst, horiz) => {        // 两遍盒滤波 ≈ 高斯
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let s = 0, n = 0;
        for (let k = -r; k <= r; k++) { const xx = horiz ? x + k : x, yy = horiz ? y : y + k; if (xx >= 0 && xx < w && yy >= 0 && yy < h) { s += src[yy * w + xx]; n++; } }
        dst[y * w + x] = s / n; } };
    box(a, tmp, true); box(tmp, a, false);
    for (let i = 0; i < w * h; i++) {
      const soft = a[i], k = 1 - 0.38 * (1 - soft) * strength;   // 边缘处压暗（×强度）
      const tint = 1 - 0.1 * strength; px[i * 4] = px[i * 4] * k * (1 - 0.06 * strength); px[i * 4 + 1] = px[i * 4 + 1] * k * tint; px[i * 4 + 2] = px[i * 4 + 2] * k * (1 - 0.14 * strength);   // 暖暗调（×强度）
      px[i * 4 + 3] = Math.min(px[i * 4 + 3], soft * 255 * 1.15);      // 轮廓羽化
    }
    ctx.putImageData(d, 0, 0); const out = new THREE.CanvasTexture(c); out.colorSpace = THREE.SRGBColorSpace; tex.userData[key] = out; return out;
  }
  sprite(kind, size, opts = {}) {
    const rng = opts.rng || Math.random; const states = this.textures[kind] || {};
    const stateNames = Object.keys(states);
    const variant = rng();                                   // 同一物件各状态用同一个变体序号，切状态时形态连续
    const pick = (st) => { const l = states[st] || states['默认'] || states[stateNames[0]] || []; const tx = l.length ? l[Math.floor(variant * l.length)] : null; return (tx && opts.feather) ? this._feather(tx, opts.feather === 'light' ? 0.45 : 1) : tx; };
    let state = opts.state || (states['默认'] ? '默认' : stateNames[0]) || '默认';
    let tex = pick(state); let mesh;
    if (tex) {
      // 照片体系的贴图（锅内状态、空位补丁、备料）用无光照材质：颜色与背景照片逐像素一致，不被场景灯光提亮/压暗
      mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), opts.unlit ? new THREE.MeshBasicMaterial({ map: tex, color: 0xffffff, transparent: true, alphaTest: 0.02, depthWrite: false })
                                                              : new THREE.MeshStandardMaterial({ map: tex, color: 0xffffff, transparent: true, alphaTest: 0.05, roughness: 0.6, depthWrite: false }));
    } else {
      mesh = new THREE.Mesh(new THREE.CircleGeometry(0.5, 24), new THREE.MeshStandardMaterial({ color: opts.color || 0xc9a86a, roughness: 0.6 }));
    }
    const STATE_TINT = { '焦': 0x3a2a20, '金黄': 0xd9a25a, '生': 0xd98c8c };   // 没有该状态贴图时用色调兜底
    mesh.scale.set(size, size, 1);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: this._shadowTex(), color: 0x000000, transparent: true, opacity: 0.72, depthWrite: false }));
    shadow.scale.set(size * 0.56, size * 0.13, 1);   // 接触阴影：底座下一小圈，深而窄
    const g = new THREE.Group(); g.add(shadow); g.add(mesh); mesh.position.z = 1;
    this.scene.add(g);
    const rtRef = this; const wy = (y) => rtRef.SH - y;   // stage 像素 y（向下）→ 世界 y（向上）
    const sp = {
      kind, size, group: g, mesh, shadow, x: 0, y: 0,
      /** 底边落在 (x, groundY)：物件中心在地面上方 size*0.42 处，阴影贴地 */
      setFoot(x, groundY) { sp.x = x; sp.y = groundY - size * 0.42; g.position.set(x, 0, 0); mesh.position.y = wy(sp.y); shadow.position.y = wy(groundY); return sp; },
      /** 直接放中心 */
      setCenter(x, y) { sp.x = x; sp.y = y; g.position.set(x, 0, 0); mesh.position.y = wy(y); shadow.position.y = wy(y + size * 0.40 * (sp.k || 1)); return sp; },
      setScale(k) { sp.k = k; mesh.scale.set(size * k, size * k * (sp.sy || 1), 1); shadow.scale.set(size * 0.56 * k, size * 0.13 * k, 1); return sp; },
      setSquash(sy) { sp.sy = sy; return sp.setScale(sp.k || 1); },   // 俯视透视：纵向压扁成椭圆，食材才像躺在锅里
      setRotation(a) { mesh.rotation.z = a; return sp; },
      setVisible(v) { g.visible = v; return sp; },
      /** 切换状态贴图（生/金黄/焦…）；没有对应贴图则用色调兜底 */
      /** 切状态：默认 1.1 秒交叉渐变（食材颜色慢慢变，不跳帧）；fade=0 立即切 */
      setState(st, fade = 1.1) {
        sp.state = st; const t2 = pick(st);
        if (t2 && mesh.material.map !== undefined) {
          if (!fade || !mesh.material.map || mesh.material.map === t2) { mesh.material.map = t2; mesh.material.color.set(0xffffff); mesh.material.needsUpdate = true; return sp; }
          if (sp.overlay) { rtRef.tweens = rtRef.tweens.filter((tw) => tw.owner !== sp); g.remove(sp.overlay); sp.overlay = null; }
          const ov = new THREE.Mesh(mesh.geometry, mesh.material.clone()); ov.material.map = t2; ov.material.opacity = 0; ov.material.transparent = true; ov.material.needsUpdate = true;
          ov.position.copy(mesh.position); ov.position.z = mesh.position.z + 0.01; ov.scale.copy(mesh.scale); ov.rotation.copy(mesh.rotation); g.add(ov); sp.overlay = ov;
          rtRef.tweens.push({ owner: sp, t: 0, dur: fade, step: (u) => { ov.material.opacity = u; ov.position.copy(mesh.position); ov.position.z = mesh.position.z + 0.01; ov.scale.copy(mesh.scale); ov.rotation.copy(mesh.rotation); },
            done: () => { mesh.material.map = t2; mesh.material.color.set(0xffffff); mesh.material.needsUpdate = true; g.remove(ov); if (sp.overlay === ov) sp.overlay = null; } });
        }
        else if (STATE_TINT[st]) mesh.material.color.set(STATE_TINT[st]);
        return sp;
      },
      setOpacity(o) { mesh.material.transparent = true; mesh.material.opacity = o; shadow.material.opacity = 0; return sp; },
      /** 淡入出现（下锅、撒料） */
      fadeIn(dur = 0.7) { mesh.material.transparent = true; mesh.material.opacity = 0; shadow.material.opacity = 0; g.visible = true;
        rtRef.tweens.push({ owner: sp, t: 0, dur, step: (u) => { mesh.material.opacity = u; shadow.material.opacity = 0.22 * u; } }); return sp; },
      get state() { return state; }, set state(v) { state = v; },
      remove() { rtRef.scene.remove(g); },
      /** 供 targets() 用：stage 像素包围盒 */
      box() { return { x: sp.x, y: sp.y, w: size, h: size }; },
    };
    return sp;
  }

  // ---------- 反馈 ----------
  _spawnFx(cls, x, y, text, ms) {
    const el = document.createElement('div'); el.className = 'bf-fx ' + cls; el.style.left = x + 'px'; el.style.top = y + 'px'; if (text) el.textContent = text;
    this.stage.appendChild(el); setTimeout(() => el.remove(), ms);
  }
  hitFlash(x, y) { this._spawnFx('bf-flash', x, y, '', 200); }
  steam(x, y) { this._spawnFx('bf-steam', x, y, '', 1600); }   // 锅上冒的蒸汽，一团一团
  bubble(x, y) { this._spawnFx('bf-bubble', x, y, '', 420); }   // 翻炒时的油泡：小、亮、短命
  comboText(x, y, n) { if (n >= 3) this._spawnFx('bf-combo', x, y - 30, 'x' + n, 460); }
  loseLifeFx() { const hearts = this.hud.querySelectorAll('#bf-lives svg'); const h = hearts[this.lives]; if (h) { h.classList.add('hit'); h.style.stroke = '#e2574a'; setTimeout(() => { h.classList.remove('hit'); h.style.stroke = ''; }, 320); } }

  // ---------- HUD ----------
  setScore(n) { const d = n - this.score; this.score = n; this.hud.querySelector('#bf-score-n').textContent = n; this._onScore(d); }
  setLives(n, max) { if (max) this.maxLives = max; this.lives = n; this.hud.querySelector('#bf-lives').innerHTML = Array.from({ length: this.maxLives }, (_, i) => HEART(i < n)).join(''); }
  setTimer(sec) { this.timer = sec; const el = this.hud.querySelector('#bf-timer'); if (sec == null) { el.style.display = 'none'; return; } el.style.display = 'block'; const n = el.querySelector('.bf-num'); n.textContent = Math.ceil(sec) + 's'; n.style.color = sec <= 10 ? '#e2574a' : ''; }
  /** 首页：只有游戏名 + 一个"开始"按钮，不放任何玩法说明（教学交给进局后的自动引导） */
  showMenu(title) {
    this.overlay.hidden = false;
    if (this.lesson && this.lesson.showSteps !== false) {   // 教学课首页 = 菜谱卡（可关：用户要求首页只有开始）
      const li = this.lesson.steps.map((s, i) => `<li><b>${s.craft}</b>${s.stop_cue ? ` — ${s.stop_cue}` : ''}</li>`).join('');
      this.overlay.innerHTML = `<div class="bf-menu"><div class="bf-recipe"><h2>${this.lesson.dish || title}</h2><ol>${li}</ol><p class="bf-hint">点击开始学做</p></div><div class="bf-start"><span>开始</span></div></div>`;
      return;
    }
    this.overlay.innerHTML = `<div class="bf-menu">${title ? `<h1 class="bf-title">${title}</h1>` : ''}<div class="bf-start"><span>开始</span></div></div>`;
  }
  // ---------- 教学课 API ----------
  /** 进入第 i 步：顶部横幅显示"第 i 步 · 工艺名 · 该做什么" */
  lessonStep(i) {
    if (!this.lesson) return; this.lessonState.step = i;
    const s = this.lesson.steps[i]; if (!s) return;
    let el = this.stage.querySelector('#bf-step'); if (!el) { el = document.createElement('div'); el.id = 'bf-step'; this.stage.appendChild(el); }
    if (this.lesson.showSteps === false) { el.textContent = s.do_short || ''; return; }   // 只说现在做什么，不展示步骤
    el.innerHTML = `<b>第 ${i + 1}/${this.lesson.steps.length} 步</b>${s.craft}${s.do_short ? ` · ${s.do_short}` : ''}`;
  }
  /** 教学课：改写当前提示（如 现在放盐） */
  setPrompt(text) { const el = this.stage.querySelector('#bf-step'); if (el && el.textContent !== text) el.textContent = text; }
  /** 一步做完：accuracy 0–100；即时反馈用工艺包原话（对了→stop_cue，错了→fail_surface） */
  stepDone(i, accuracy, okText, badText) {
    if (!this.lesson) return;
    const s = this.lesson.steps[i] || {}; const acc = Math.max(0, Math.min(100, Math.round(accuracy)));
    this.lessonState.results[i] = acc;
    const good = acc >= 60;
    const el = document.createElement('div'); el.className = 'bf-verdict' + (good ? '' : ' bad');
    el.innerHTML = `${good ? '✓ ' : '✗ '}${good ? (okText || ('对了 · ' + (s.stop_cue || ''))) : (badText || ('差一点 · ' + (s.fail_surface || '')))}<small>准确度 ${acc}</small>`;
    this.stage.appendChild(el); setTimeout(() => el.remove(), 2300); this.lessonState.verdicts++;
    if (good) this.praise(acc >= 85 ? '刚刚好！' : '不错！', { sparks: acc >= 85 ? 14 : 6 });
    this.setScore(this.score + acc);
  }
  /** 课程结束：星级按平均准确度；"你学会了"卡 */
  lessonOver() {
    if (!this.lesson) return;
    const r = this.lessonState.results.filter((x) => x != null); const avg = r.length ? r.reduce((a, b) => a + b, 0) / r.length : 0;
    const stars = avg >= 85 ? 3 : avg >= 60 ? 2 : 1; this.lessonState.stars = stars; this.lessonState.avg = Math.round(avg);
    const card = (this.lesson.learned_card || []).map((l) => `<li>${l}</li>`).join('');
    const stepEl = this.stage.querySelector('#bf-step'); if (stepEl) stepEl.remove();
    this.phase = 'over'; this.game.onOver && this.game.onOver(this);
    this.overlay.hidden = false;
    this.overlay.innerHTML = `<div class="bf-card"><h1 class="bf-title">你学会了 · ${this.lesson.dish || ''}</h1><div class="bf-stars">${'★'.repeat(stars)}${'☆'.repeat(3 - stars)}</div><p class="bf-sub">平均准确度 ${Math.round(avg)}</p><ol class="bf-learned">${card}</ol><p class="bf-hint">点击任意位置再做一遍</p></div>`;
  }
  showOver(title, lines) { this.overlay.hidden = false; this.overlay.innerHTML = `<div class="bf-card"><h1 class="bf-title">${title}</h1>${(lines || []).map((l) => l.startsWith('<') ? l : `<p class="bf-sub">${l}</p>`).join('')}<div class="bf-big">${this.score}</div><p class="bf-hint">点击任意位置再来一局</p></div>`; }
  hideOverlay() { this.overlay.hidden = true; }

  // ---------- 契约 ----------
  reset(seed) {
    this.seed = seed >>> 0; this.rng = mulberry32(this.seed);
    this.phase = 'menu'; this.t = 0; this.tick = 0; this.acc = 0; this.score = 0; this.hud.querySelector('#bf-score-n').textContent = 0; this.setLives(this.maxLives);
    this.streak = 0; this.lastScoreAt = -1e9; this.praised = {}; this.hitMilestones = {}; this._clearHint();
    this.lessonState = { step: 0, results: [], stars: 0, verdicts: 0 }; const se = this.stage.querySelector('#bf-step'); if (se) se.remove();
    this.game.reset(this, this.rng);
    this.hud.style.visibility = 'hidden';                 // 首页不显示 HUD，只留游戏名 + 开始
    this.showMenu(this.opts.title || '');
  }
  start() { if (this.phase !== 'menu') return; this.phase = 'playing'; this.hideOverlay(); this.hud.style.visibility = ''; if (this.lesson) this.lessonStep(0); this.game.onStart && this.game.onStart(this); }
  gameOver(title, lines) {
    if (this.phase === 'over') return; this.phase = 'over'; this.game.onOver && this.game.onOver(this);
    const par = this.opts.par || 10; const stars = this.score >= par * 2 ? 3 : this.score >= par ? 2 : this.score > 0 ? 1 : 0;
    const extra = [`<div class="bf-stars">${'★'.repeat(stars)}${'☆'.repeat(3 - stars)}</div>`];
    if (this.score > this.best && this.score > 0) { this.best = this.score; extra.push('<div class="bf-record">新纪录！</div>'); try { localStorage.setItem('bf-best-' + (this.opts.title || location.pathname), String(this.best)); } catch (e) {} }
    this.showOver(title || (this.opts.overTitle || '结束'), (lines || []).concat(extra));
  }
  setTimeScale(k) { k = Number(k); this.timeScale = Number.isFinite(k) ? Math.max(0, Math.min(8, k)) : 1; }
  state() {
    const targets = this.phase === 'playing' ? (this.game.targets(this) || []).map((t) => ({
      id: t.id, kind: t.kind, x: this.rect.left + t.x, y: this.rect.top + t.y, w: t.w, h: t.h, action: t.action || 'tap',
      to: t.to ? { x: this.rect.left + t.to.x, y: this.rect.top + t.to.y } : undefined, dir: t.dir, anchored: t.anchored !== false, static: !!t.static,
    })) : [];
    const st = { phase: this.phase, score: this.score, lives: this.lives, t: this.t, tick: this.tick, targets, ui: { hintsShown: this.ui.hintsShown, praisesShown: this.ui.praisesShown, streak: this.streak } };
    if (this.lesson) st.lesson = { step: this.lessonState.step, total: this.lesson.steps.length, results: this.lessonState.results, stars: this.lessonState.stars, avg: this.lessonState.avg, verdicts: this.lessonState.verdicts };
    return st;
  }
  _pointer(e) {
    if (!this.ready) return;
    if (this.phase === 'menu') { this.start(); return; }
    if (this.phase === 'over') { if (this.opts.tapToRestart) { this.reset(this.seed + 1); this.start(); } return; }
    const x = e.clientX - this.rect.left, y = e.clientY - this.rect.top;
    this._ptr = { x0: x, y0: y, x, y, t0: performance.now(), moved: 0, id: e.pointerId };
    this.canvas.setPointerCapture && this.canvas.setPointerCapture(e.pointerId);
    this.game.onDown && this.game.onDown(this, x, y);
  }
  _pointerMove(e) {
    if (!this._ptr || this.phase !== 'playing') return;
    const x = e.clientX - this.rect.left, y = e.clientY - this.rect.top;
    const p = this._ptr; const dx = x - p.x, dy = y - p.y; p.x = x; p.y = y; p.moved = Math.max(p.moved, Math.hypot(x - p.x0, y - p.y0));
    this.game.onMove && this.game.onMove(this, x, y, dx, dy);
  }
  _pointerUp(e) {
    if (!this._ptr) return;
    const p = this._ptr; this._ptr = null;
    if (this.phase !== 'playing') return;
    const x = e.clientX - this.rect.left, y = e.clientY - this.rect.top;
    const dx = x - p.x0, dy = y - p.y0, ms = performance.now() - p.t0, dist = Math.hypot(dx, dy);
    let type = 'tap', dir = null;
    // 甩：位移 ≥40px 且 ≤400ms；拖：更慢或更短的位移。（机器人：甩 ≈100ms，拖 ≈450ms）
    if (dist >= 40 && ms <= 400) { type = 'swipe'; dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up'); }
    else if (dist >= 12) type = 'drag';
    const gesture = { type, dx, dy, dir, ms, x0: p.x0, y0: p.y0 };
    if (type === 'tap' && this.game.onTap) this.game.onTap(this, x, y);
    this.game.onUp && this.game.onUp(this, x, y, gesture);
    if (this.hintAction === type) this.learned(type);       // 做过一次就算学会
  }
  _frame(now) {
    requestAnimationFrame((t) => this._frame(t));
    const dtWall = this.last ? Math.min((now - this.last) / 1000, 0.1) : 0; this.last = now;
    const slow = (this.hintEl && this.opts.tutorial !== false && this.timeScale === 1) ? this.tutorialSlow : 1;   // 引导显示时放慢（仅真人正常速度下；检验加速时不减速，保证可复现与墙钟预算）
    this.acc += dtWall * this.timeScale * slow; let guard = 0;
    while (this.acc >= DT && guard++ < 240) {
      this.tick++;
      if (this.phase === 'playing') { this.t += DT; try { this.game.step(this, DT); } catch (err) { this.errors.push(String(err)); throw err; } }
      this.acc -= DT;
    }
    if (this.tweens.length) {                                     // 补间：贴图渐变、淡入（用游戏时间，检验加速时同步加速、冻结时冻结）
      const dtg = dtWall * this.timeScale; this.tweens = this.tweens.filter((tw) => { tw.t += dtg; const u = Math.min(1, tw.t / tw.dur); tw.step(u); if (u >= 1) { tw.done && tw.done(); return false; } return true; });
    }
    this.game.render && this.game.render(this);
    this._teach();
    this.renderer.render(this.scene, this.camera);
  }

  // ---------- 新手引导（纯视觉，不改模拟）----------
  _teach() {
    if (this.phase !== 'playing' || this.opts.tutorial === false) { if (this.phase !== 'playing') this._clearHint(); return; }
    const ts = (this.game.targets(this) || []);
    if (this.hintEl) {   // 正在教：被教的目标消失/动作变了/超时 → 收，下一帧按新状态重教
      const still = ts.find((t) => t.id === this.hintId && (t.action || 'tap') === this.hintAction);
      if (!still || performance.now() - this.hintAt > 6000) this._clearHint();
      else return;
    }
    for (const t of ts) {
      const a = t.action || 'tap';
      if (this.taught[a]) continue;
      this._showHint(a, t); break;
    }
  }
  _showHint(action, t) {
    const L = this.hintLayer; L.innerHTML = '';
    const finger = `<svg viewBox="0 0 64 64" fill="none" stroke="#f3ede4" stroke-width="3" stroke-linejoin="round"><path d="M24 34V14a5 5 0 0 1 10 0v16" fill="#c9a86a"/><path d="M34 30v-4a5 5 0 0 1 10 0v6M44 32v-2a5 5 0 0 1 10 0v10c0 10-6 16-16 16h-6c-6 0-9-3-13-8l-8-10a4.5 4.5 0 0 1 7-5l6 6" fill="#c9a86a"/></svg>`;
    const mk = (cls, x, y, html = '') => { const e = document.createElement('div'); e.className = cls; e.style.left = x + 'px'; e.style.top = y + 'px'; e.innerHTML = html; L.appendChild(e); return e; };
    mk('bf-ring', t.x, t.y);
    if (action === 'drag' && t.to) {
      const dx = t.to.x - t.x, dy = t.to.y - t.y, len = Math.hypot(dx, dy);
      const ar = mk('bf-arrow', t.x, t.y); ar.style.width = Math.max(0, len - 24) + 'px'; ar.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
      mk('bf-ring', t.to.x, t.to.y);
      const f = mk('bf-finger', t.x, t.y, finger); f.style.transition = 'left 1.1s ease-in-out, top 1.1s ease-in-out';
      let flip = false; this.hintTimer = setInterval(() => { flip = !flip; f.style.left = (flip ? t.to.x : t.x) + 'px'; f.style.top = (flip ? t.to.y : t.y) + 'px'; }, 1200);
    } else if (action === 'swipe') {
      const d = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }[t.dir || 'right'];
      const ar = mk('bf-arrow', t.x, t.y); ar.style.width = '90px'; ar.style.transform = `rotate(${Math.atan2(d[1], d[0])}rad)`;
      const f = mk('bf-finger', t.x, t.y, finger); f.style.transition = 'left .7s ease-in, top .7s ease-in';
      let flip = false; this.hintTimer = setInterval(() => { flip = !flip; f.style.left = (t.x + (flip ? d[0] * 90 : 0)) + 'px'; f.style.top = (t.y + (flip ? d[1] * 90 : 0)) + 'px'; }, 800);
    } else {
      mk('bf-finger tap', t.x + 14, t.y + 18, finger);
    }
    const ty = Math.min(this.SH - 60, Math.max(70, t.y - Math.max(70, (t.h || 60) * 0.9)));
    mk('bf-hint-text', Math.max(110, Math.min(this.SW - 110, t.x)), ty - 14, t.hint || this.hints[action] || '');   // 目标自带的状态提示优先（"定形了，滑一下翻面"）
    this.hintEl = L; this.hintAction = action; this.hintId = t.id; this.hintAt = performance.now(); this.ui.hintsShown++;
  }
  _clearHint() { if (!this.hintEl) return; this.hintLayer.innerHTML = ''; if (this.hintTimer) clearInterval(this.hintTimer); this.hintTimer = null; this.hintEl = null; this.hintAction = null; this.hintId = null; }
  /** 做对一次记一次；达到 teachTimes 才算学会 */
  learned(action) {
    this.taughtCount[action] = (this.taughtCount[action] || 0) + 1;
    if (this.taughtCount[action] >= this.teachTimes) this.taught[action] = true;
    if (this.hintAction === action) this._clearHint();
  }

  // ---------- 情绪价值 ----------
  /** 主动赞美：rt.praise('刚刚好！') */
  praise(text, opts = {}) {
    const el = document.createElement('div'); el.className = 'bf-praise'; el.textContent = text; this.stage.appendChild(el); setTimeout(() => el.remove(), 1150);
    const g = document.createElement('div'); g.className = 'bf-glow'; this.stage.appendChild(g); setTimeout(() => g.remove(), 950);
    const cx = opts.x != null ? opts.x : this.SW / 2, cy = opts.y != null ? opts.y : this.SH * 0.38, n = opts.sparks || 14;
    for (let i = 0; i < n; i++) {
      const s = document.createElement('div'); s.className = 'bf-spark'; const ang = (i / n) * Math.PI * 2, r = 60 + (i % 3) * 30;
      s.style.left = cx + 'px'; s.style.top = cy + 'px'; s.style.setProperty('--dx', Math.cos(ang) * r + 'px'); s.style.setProperty('--dy', Math.sin(ang) * r + 'px');
      this.stage.appendChild(s); setTimeout(() => s.remove(), 1000);
    }
    this.ui.praisesShown++;
  }
  _onScore(delta) {
    if (delta <= 0) return;
    if (this.lesson) return;                              // 教学课：只用 stepDone 的即时反馈，不叠加连击/里程碑赞美
    const now = this.t;                                   // 用仿真时间判连击，与真实时钟无关
    this.streak = (now - this.lastScoreAt <= this.streakWindow) ? this.streak + 1 : 1; this.lastScoreAt = now;
    const w = this.praiseWords[this.streak];
    if (w && !this.praised[this.streak]) { this.praised[this.streak] = true; this.praise(w); return; }
    for (const k of Object.keys(this.milestones).map(Number).sort((a, b) => a - b)) {   // 里程碑：跨过某分数线弹一次
      if (this.score >= k && !this.hitMilestones[k]) { this.hitMilestones[k] = true; this.praise(this.milestones[k], { sparks: 10 }); break; }
    }
  }
}

/** 一行启动：import { boot } from '../../vendor/bf-runtime.js'; boot(game, {title:'…'}) */
export function boot(game, opts) { return new Runtime(game, window.BF_ASSETS || {}, opts); }
