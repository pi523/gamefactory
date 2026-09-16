"""读取项目根目录的 .env 到 os.environ（已存在的变量不覆盖）。所有要调 API 的脚本先 `import env`。"""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"缺少 {name}：复制 .env.example 为 .env 填入，或 export {name}=...")
    return v
