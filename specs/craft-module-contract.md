# 手作模拟品类 · 游戏模块契约（craft-sim module contract）

一款手作游戏 = `games/<id>/game.js` 里 **一个默认导出对象**（下称 G）+ `games/<id>/index.html`（由 `vendor/craft/template.html` 生成，不用写）。引擎在 `vendor/craft/`（three.js r170，导入路径写 `../../vendor/craft/xxx.js`，three 用 `import * as THREE from 'three'`）。

## 必填字段

| 字段 | 说明 |
|---|---|
| `id` | 英文短 id，与目录名一致 |
| `title` / `subtitle` | 店名（中文，如「糖葫芦摊」）/ 英文 |
| `unit` / `maker` | 结算单位（串/碗/份）；这门手艺的师傅一句话（结算满分时用） |
| `cardTitle` | 任务卡抬头，如「客人要」 |
| `perfectText` / `againText` | 满分横幅四字；再来一次按钮文案 |
| `palette` | `{ink, paper, deep, accent, gold, ground}` 六个 CSS 色，跟店的气质走 |
| `scene` | 场景对象：`{ mood: 'day'|'warm'|'night'|'steel', wood: 'light'|'dark'|'steel', wall: 'plaster'|'whitetile'|'night'|'street'|'redwood', dressing: [...] }`。dressing 每件 `{kind, ...}`，kind ∈ backLedge / shelf / jar(x,z,content,lid,label) / chalkboard(lines) / poster(title,sub) / sign(title,sub,hex,x,y) / plant(x,z) / napkin(x,z,color) / glassStack / noren(text) / lantern(x,y,z) / steamer(x,z) / pendant(x,y,z) / awning(c1,c2) / stringLights / counterBox。**≤ 8 件；不放跟游戏主体同款的东西**（主体是壶就别再放壶） |
| `phases` / `phaseNames` | 工序 id 数组（**3–5 道，最后一道必须是 `'serve'`**）；每道的中文名 ≤ 3 字 |
| `views` | 每道工序一个镜头 `{pos:[x,y,z], tgt:[x,y,z]}`，另加 `reveal0`、`reveal1`、`serve`（结算镜头：成品要留在画面上半，卡片在下半） |

## 必填方法（`core` 是引擎实例）

```js
init(core)                 // 建所有 three 物件加进 core.w.scene；把状态放 this.st
newTask(core, prevName)    // 抽一个客人订单 → { name, line:'「客人一句话」', chips: core.chip(css,text)+..., foot1, foot2 }
enter(core, phase)         // 进入工序：core.ui.hint('一句话 ≤ 14 字'); core.ui.next('下一步文案 →', disabledBool); core.ui.coach(type, '≤12 字');
                           //   type ∈ tap|hold|dragx|dragy|drag|circle|wait；需要"按住"的用 core.ui.hold('按住\n出水', onDown, onUp)；需要选料的用 core.ui.tray([[key,{name,css}],...], onPick, 'food')
leave(core, phase)         // 离开工序时收尾（隐藏工具、记录时机）
canNext(core, phase)       // 这道工序能否点下一步（只按"做没做"，不按"做得好不好"）
down(core, e) / move(core, e) / up(core, e)   // 指针事件；平面拾取用 core.screenToPlane(e, y) → Vector3|null；横向归一用 core.screenX(e)
update(core, dt)           // 每帧；工序 id 在 core.phase；'reveal' 与 'score' 也会进来（结算时不要再动主体）
score(core)                // → { rows: [[名, 0–100, 权重], ...], tips: ['人话点评', ...] }  —— 这里才揭示隐形标准
strip(core, ctx, canvas)   // 结算卡上的小色条（画布 2D）
celebrateAt(core)          // → [x, y, z, r] 满分撒花的位置
reset(core)                // 回到初始状态（再来一份）
clipping(core)             // → ['中文说明', ...]：本帧任何穿模/悬空/出界；**每帧都会被检验器调用，返回非空 = 硬性 FAIL**
auto(core, phase, part)    // 自动驾驶（检验器/打分器驾驭）：part 'mid' 做到一半停在"动作进行中"，'end' 做到刚好；返回 { step(dt)→boolean(done) } 或 { wait: 秒 }
```

可选：`physics(core)` → 倒液物理违规列表（用 `pourPhysics(stream, 壶嘴世界坐标, 壶盖/后沿世界坐标, 名字)`）。

## 引擎里能用的东西

- `core.ui`：`hint / next / nextEnabled / undo(label) / tray / markTray / meter(label, 0–1, text) / meterOff / hud / warn / praise('≤4 字') / coach / hold`
- `core.chip(css, text)`（任务卡上的配料点）、`core.el.orderName`、`core.task`
- `../../vendor/craft/core.js`：`clamp(v, lo=0, hi=100)`、`rangeMiss(v, [lo, hi])`（落在区间外多少）、`smooth(t)`
- `../../vendor/craft/cup.js`：`Cup(scene, {…profile, material:'glass'|'ceramic'|'steel', pos, tint, liquidOpacity})`，方法 `add(rgb, vol) / remove / mix(1) / setFoam / levelY / topY / innerR(y) / yForInnerR(r) / wobble / update(dt) / reset()`；profile 工厂 `glassProfile / coupeProfile / teacupProfile / steelMugProfile(r, H, wall)`，或自己给 `{inner:[[r,y]...], outer:[[r,y]...]}`
- `../../vendor/craft/pour.js`：`Stream(scene, onDrop, ING)`（`update(dt, start, dir, flow, surfaceY(x,z), rMax, arcScale, forceEnd)`, `begin() / release() / setColor(key)`），`Bottle(scene, ING)`（`show(key) / hide / setTilt / spout() / spoutDir() / samples() / update(dt)`）
- `../../vendor/craft/fx.js`：`Steam(scene, n)`、`Bubbles(scene, n)`（`set(x,y,z,r,intensity)`, `update(dt)`）
- `../../vendor/craft/textures.js`：`noiseBumpTexture / lightWoodTexture / barWoodTexture / stoneTexture / leafTexture / brickTexture / groutTileTexture / stripeTexture / citrusTexture`；画布贴图自己画（`CanvasTexture`，记得 `colorSpace = THREE.SRGBColorSpace`）
- `../../vendor/craft/fruits.js`：`fruitMesh(key, max, scale)`（strawberry / banana / mango / blueberry / kiwi …）
- `../../vendor/craft/audio.js`：`sfx.place / pick / splash / drip / ice / glass / done / bad / pourSet(level, flow)`
- `../../vendor/craft/dressing.js`：`labelTextTexture(hex, title, sub, paper)` 等（陈设优先用 `scene.dressing` 声明）

## 硬性规定（检验器逐条查，违反即 FAIL）

1. **不告诉玩家加多少**：任务卡与提示只说"客人要什么"，不出现目标数值/目标线/进度百分比；分量、时机、手法是 `score()` 里的隐形评分，结算才用人话揭示。
2. **每帧不穿模、不悬空**：工具不探进容器，食材不叠、不出容器，道具部件（壶嘴/把手/盖）长在主体上；`clipping()` 要真的检查这些（几何判据，不是返回 []）；集合类 Group 标 `userData.loose = true`。
3. **符合物理**：液体只从壶嘴出、倾倒方向对、东西落在支撑面上，不悬在半空。
4. **写实**：道具是几何体勾形 + 贴图/凹凸（画布贴图、bumpMap），不是光溜溜的纯色几何；顶点色写线性值（sRGB→linear）。
5. **背景克制**：陈设 ≤ 8 件，不放跟主体同款的东西；远景压暗。
6. **文本少**：hint ≤ 14 字，coach ≤ 12 字，praise ≤ 4 字；不出现长段说明。
7. **手机 9:16**：镜头按竖屏构图，主体占画面中部，结算镜头把成品留在卡片上方。
8. `auto()` 每道工序都要能自动做到 mid 与 end，且 end 之后 `canNext` 为 true；工序里没有真人输入也能被驾驭跑通。
9. 对象字面量方法之间别漏逗号；别在行尾用 `//` 注释接代码（会吞掉同行后面的代码），用 `/* */`。

## 写法参考

`vendor/craft/examples/tanghulu.js`（糖葫芦：串果 → 熬糖看色 → 蘸糖滚匀 → 出摊；165 行，含 Cup 糖锅、Bubbles/Steam、clipping、auto）。新模块的体量 150–300 行，结构照它。
