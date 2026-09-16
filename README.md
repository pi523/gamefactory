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
python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/playwright install chromium
cp .env.example .env                                   # 填 OPENROUTER_API_KEY
.venv/bin/python factory/pipeline.py "一句话题材" --id <game-id>
python3 factory/serve.py 8765                           # 本地预览
```

不需要 node：JS 语法自检和所有浏览器操作都走 Python playwright。

## 目录

- `factory/` 流水线脚本，每个文件开头有一句说明；入口是 `pipeline.py`，检验器是 `verify.py`，手作品类盲测是 `craft_grade.py`
- `specs/` PRD schema、硬性规定（`rules/h5-hard-rules.json`）、风格、素材命名、调试契约、品类规范
- `vendor/` 游戏运行时：three.js、工厂运行时、穿模/组装/倒液检验

## 不入库

`.env`、生产出来的游戏（`games/` 等）、素材与原图、检验产物与终审页。样例游戏另行打包提供。
