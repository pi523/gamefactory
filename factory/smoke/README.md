# smoke：手作游戏每步自检（穿模 + 组装 + 倒液物理）

三套引擎各一个驾驭脚本（harness 自动跑完整局，每推进 0.1 s 调一次 `window.__game.checkClipping()`，里面已并入 `checkAssembly()` 与 `checkPhysics()`）：

```
.venv/bin/python factory/smoke/smoke.py  <bar|teashop|cafe|izakaya|teahouse|shavedice|smoothie>   # drinks/game-drink
.venv/bin/python factory/smoke/smoke2.py <beer|tehtarik|champagne|juicecolor|gongfu>              # drinks/game-drink2
.venv/bin/python factory/smoke/smoke3.py <dumpling|lamian|tanghulu|jianbing|tanghua>              # chinese-food
```

前提：本地静态服务 `python3 factory/serve.py 8765`（no-store，改完代码不用清缓存）。输出 `CLIPPING: 0` 才算过；截图落在 `reports/smoke/shots*-<game>/`（reports 不入库）。
规则出处：`specs/rules/h5-hard-rules.json` craft_sim.no_clipping / assembly_and_realism_check / physics_consistency。
