# 黑灯工厂 · HTML5 小游戏生产线

这是一条**工厂流水线**，不是某一款游戏：一句话题材进去，可玩、可检验、可终审的 HTML5（three.js）小游戏出来。仓库里只有流水线本身；生产出来的游戏、素材、截图、报告都留在本地，不入库。

```
一句话题材 → 找月亮（竞品网页/实机视频，链接核实）→ PRD（schema 校验）
→ 专属素材（生图 → 抠图 → 命名入库）→ 代码生成（驳回回灌重试）
→ 自动检验（静态 / 浏览器 / 笨玩家可玩通 / 物理 / 穿模·组装·倒液）
→ 视觉评审 + 保真比对（手作品类另有两家外部模型盲测）→ 终审页
```

## 跑起来

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
cp .env.example .env                                   # 填 OPENROUTER_API_KEY
.venv/bin/python factory/pipeline.py "一句话题材" --id <game-id>
python3 factory/serve.py 8765                           # 本地预览
```

需要 Python 3.12+，不需要 node：JS 语法自检和所有浏览器操作都走 Python playwright。竞品视频那一步用 yt-dlp 抓取，抓不到会跳过不阻塞。

## 手作模拟品类（craft）

饮品、中餐这类"按工序做一份手艺"的游戏走另一条更短的线：引擎是人写好的模板（`vendor/craft/`：任务卡/工序条/镜头/结算/教程手、杯壶与流柱物理、蒸汽气泡、陈设库、穿模/组装/倒液检验），模型只写一个 150–300 行的工序模块（契约见 `specs/craft-module-contract.md`），检验器驾驭一整局、每步查穿模，驳回回灌重试。

```bash
.venv/bin/python factory/pipeline.py "豆腐脑摊：舀豆花、浇卤、加配料" --id doufunao --genre craft
# 等价于 factory/craft_generate.py ...；成品 games/doufunao/index.html；加 --grade 跑外部模型盲测（需参考游戏）
```

## 目录

- `factory/` 流水线脚本，每个文件开头有一句说明；入口是 `pipeline.py`，检验器是 `verify.py`，手作品类盲测是 `craft_grade.py`
- `specs/` PRD schema、硬性规定（`rules/h5-hard-rules.json`）、风格、素材命名、调试契约、品类规范
- `vendor/` 游戏运行时：three.js、工厂运行时、穿模/组装/倒液检验；`vendor/craft/` 手作品类引擎模板 + 示例模块

## 不入库

`.env`、生产出来的游戏（`games/` 等）、素材与原图、检验产物与终审页。样例游戏另行打包提供。
