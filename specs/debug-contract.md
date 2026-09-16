# 调试契约 `window.__bf`（每个生成的游戏必须实现）

工厂只认这个接口。没有它，检验器无法读状态、无法驱动机器人，直接判 FAIL。

```ts
interface BF {
  version: 1;
  ready: boolean;                 // 资源加载完、可以接受输入后置 true
  reset(seed: number): void;      // 用种子重开一局，回到 'menu'。同种子必须完全可复现
  start(): void;                  // 'menu' → 'playing'
  setTimeScale(k: number): void;  // 仿真加速倍率，1 = 正常。机器人会用 1–4
  state(): {
    phase: 'menu' | 'playing' | 'over';
    score: number;                // 不能是 NaN
    lives: number;                // 不能是 NaN
    t: number;                    // 本局仿真时间（秒）
    tick: number;                 // 固定步长计数，只增不减
    targets: Array<{             // 当前"可以点的东西"，CSS 像素，相对 viewport
      id: string; kind: string;
      x: number; y: number; w: number; h: number;  // 中心点 + 尺寸
      action: 'tap';
    }>;
  };
  errors: string[];               // 游戏自行捕获但没抛出的逻辑异常，检验器要求为空
}
```

规则：
1. 所有游戏逻辑走固定步长（推荐 1/60 s），rAF 只负责累积时间；这样 seed + 输入序列 = 唯一结果。
2. `targets` 只在 `playing` 时非空；`menu` 时点任意位置等价于 `start()`。
3. 输入必须响应真实 `pointerdown`，机器人用真鼠标事件，不调用内部函数。
4. 不得对外发任何网络请求（除同源相对路径）。资源列表由 `assets/manifest.json` 提供，不许猜文件名导致 404。

## v2 追加：竖屏 stage 与布局锚点

- 整个游戏必须包在 `<div id="stage">` 里（内含 #bg、canvas、#hud、#overlay）。stage 固定手机竖屏比例：手机上铺满视口；宽屏上高度占满、水平居中、两侧留黑，宽高比保持在 0.5–0.6。
- `state().targets` 的 x/y 仍是**视口** CSS 像素（不是 stage 内坐标），所以要把 stage 的 getBoundingClientRect() 偏移加上；pointer 事件也要减去这个偏移再做命中。
- 注入的 `BF_ASSETS.__scene.portrait` 是背景图 URL；`BF_ASSETS.__layout` 是锚点：`{type:'slots', slots:[{x,y,r}], img_w, img_h}` 或 `{type:'path', points:[{x,y}], width, img_w, img_h}`，坐标是背景图的 0–1 归一化。背景按 cover 铺到 stage，映射公式：`s=max(SW/img_w, SH/img_h); x=(SW-img_w*s)/2+nx*img_w*s; y=(SH-img_h*s)/2+ny*img_h*s`。
- 检验器会在游玩中采样所有 target：slots 型中心必须在某锚点半径×1.6 内；path 型底边必须贴轨道线。超过 10% 采样悬空 → FAIL。
- canvas 必须 `width:100%;height:100%` 贴满 stage（替换元素不吃 inset:0）。检验器在伪装 devicePixelRatio=2/3 的视口下量 canvas CSS 尺寸是否等于 stage，并比对截图确认目标真的画在 state 声称的位置。

## v3 追加：多动词与多状态

- `targets[]` 每项带 `action: 'tap' | 'drag' | 'swipe'`；`drag` 必带 `to:{x,y}`（视口 CSS 像素，目的地），`swipe` 必带 `dir: 'left'|'right'|'up'|'down'`。机器人按数组顺序执行第一个动作，所以游戏要把最紧急的目标排在前面。
- `anchored: false` 表示该目标此刻不在布局锚点上（托盘里、手里拖着），物理层不检查它；其它目标仍必须落在锚点上。
- 贴图多状态：`BF_ASSETS[kind]` 可以是 `{"生":[...],"金黄":[...],"焦":[...]}`；运行时 `sp.setState('金黄')` 切换，缺失状态用色调兜底。
- 运行时把真实指针事件分类为 tap（位移<12px）、swipe（位移≥40px 且 ≤320ms）、drag（其余），回调 `onDown/onMove/onUp(rt,x,y,gesture)`；`onTap` 仍可用。

## v4 追加：引导与热身

- `targets[]` 可带 `hint`（一句状态化提示，如"面糊定形了，滑一下翻面"），运行时第一次教该动词时显示它，优先于通用文案。
- 运行时在引导显示期间把仿真减速到 0.45×（首次学每个动词时），每个动词做对 2 次才算学会。此减速只发生在有提示时，检验器的确定性对比在引导结束后进行。
- 热身期硬规则：开局前 6 秒（仿真时间）不得掉命；前 3 个物件的时间窗口至少放宽到正常的 2 倍；按"已完成数量"判定，不依赖真实时钟，保证可复现。

## v5 追加：教学课模式（厂房 01）

- `boot(game, { lesson: {dish, steps:[{id, craft, verb, kind, stop_cue, fail_surface, do_short}], learned_card:[...] } })` 开启教学课：首页变菜谱卡；`rt.lessonStep(i)` 顶部横幅；`rt.stepDone(i, accuracy0_100, okText?, badText?)` 即时对错反馈（默认用 stop_cue / fail_surface 原话）并计分；`rt.lessonOver()` 结束并出"你学会了"卡与星级（平均准确度 ≥85 三星、≥60 两星）。
- 教学课没有命数：不要调用 setLives 扣命；做错只影响准确度。
- `state().lesson = {step, total, results[], stars, avg, verdicts}`；检验器要求：机器人能把每步做完（results 长度 == total）、verdicts ≥ total、慢手机器人 stars ≥ 2。


## 附录 v7：静态目标（2026-09-11）
- `targets[].static = true` 表示该目标静止时就是背景照片的一部分（"照片即备料"模式的碟/瓶），拿起前不该有任何像素变化；检验的幽灵/错位检查跳过它，但仍要求它能被拖起并在锅里产生变化。
