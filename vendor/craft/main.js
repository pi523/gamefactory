import * as THREE from 'three';
import { configureGlass } from './vessel.js';
import { buildScene } from './scene.js';
import { Core } from './core.js';

const PALETTE = { ink: '#2a1e14', paper: '#fbf4e8', deep: '#5a3a2a', accent: '#c1462f', gold: '#d8a24a', ground: '#d8c8b0' };

/** 手作模拟品类的入口：一个游戏 = 一个模块 G（见 specs/craft-module-contract.md）。页面里：import G from './game.js'; boot(G); */
export function boot(G) {
  const q = new URLSearchParams(location.search);
  if (G.vessel) configureGlass(G.vessel);
  document.documentElement.dataset.theme = G.id;
  const pal = { ...PALETTE, ...(G.palette || {}) }; for (const [k, v] of Object.entries(pal)) document.documentElement.style.setProperty('--' + k, v);
  document.title = `${G.title} · ${G.subtitle || ''}`;
  const canvas = document.getElementById('stage');
  const world = buildScene(canvas, G);
  const clock = new THREE.Clock(); let game = null;
  const app = document.getElementById('app');
  function resize() { const w = app.clientWidth, h = app.clientHeight; world.renderer.setSize(w, h, false); world.camera.aspect = w / h; world.camera.updateProjectionMatrix(); game?.onResize(w / h); }
  addEventListener('resize', resize); resize();
  game = new Core(world, G); resize();
  window.__game = game; window.__world = world; window.__theme = G;
  window.__step = (dt = 1 / 60) => { game.update(dt); world.renderer.render(world.scene, world.camera); };
  const HARNESS = q.has('harness');   // ?harness=1：不跑 rAF，由自动化脚本推进与出帧
  window.__advance = (sec, dt = 1 / 60) => { let n = Math.round(sec / dt); while (n-- > 0) game.update(dt); };
  window.__render = () => world.renderer.render(world.scene, world.camera);
  function loop() { const dt = Math.min(0.05, clock.getDelta()); game.update(dt); world.renderer.render(world.scene, world.camera); requestAnimationFrame(loop); }
  const bootEl = document.getElementById('boot');
  if (HARNESS) { world.renderer.render(world.scene, world.camera); if (bootEl) { bootEl.classList.add('gone'); bootEl.style.display = 'none'; } }
  else { loop(); requestAnimationFrame(() => requestAnimationFrame(() => bootEl && bootEl.classList.add('gone'))); }
  return game;
}
