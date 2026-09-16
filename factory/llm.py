"""工厂统一 LLM 客户端：走 OpenRouter（OpenAI 兼容接口）。
用法:
    import llm
    text = llm.chat([{"role": "user", "content": "..."}], role="code")
    text = llm.chat_vision("这张截图里有什么问题？", ["reports/x/mobile-playing.png"], role="vision")
    python3 factory/llm.py --ping     # 不花钱：检查 key 是否加载、配置的模型 ID 是否存在
    python3 factory/llm.py --hello    # 花几分钱：真实调用一次
模型由 .env 决定（BF_MODEL_CODE / BF_MODEL_VISION / BF_MODEL_CHEAP），每次调用的 token 用量追加到 reports/llm-usage.jsonl。
"""
import base64, json, mimetypes, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env  # noqa: E402,F401  加载 .env

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://openrouter.ai/api/v1"
DEFAULTS = {
    "code": os.environ.get("BF_MODEL_CODE", "anthropic/claude-opus-5"),
    "vision": os.environ.get("BF_MODEL_VISION", "anthropic/claude-opus-5"),
    "cheap": os.environ.get("BF_MODEL_CHEAP", "anthropic/claude-sonnet-5"),
    "web": os.environ.get("BF_MODEL_WEB", "google/gemini-3.5-flash-lite"),   # 联网检索会塞入几十万 token 网页，必须用便宜模型
}
USAGE_LOG = ROOT / "reports/llm-usage.jsonl"
_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(base_url=BASE_URL, api_key=env.require("OPENROUTER_API_KEY"),
                         default_headers={"HTTP-Referer": "https://github.com/blackfactory", "X-Title": "blackfactory"},
                         timeout=420, max_retries=1)
    return _client


def _log(model, resp, tag):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    u = getattr(resp, "usage", None)
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": model, "tag": tag,
                            "prompt_tokens": getattr(u, "prompt_tokens", None), "completion_tokens": getattr(u, "completion_tokens", None),
                            "cost": (getattr(u, "cost", None) if u is not None else None)}, ensure_ascii=False) + "\n")


def chat(messages, role="code", model=None, max_tokens=16000, temperature=0.2, json_mode=False, tag="", grow=True, extra=None):
    """返回 assistant 文本。json_mode=True 时要求模型只输出 JSON 对象。"""
    model = model or DEFAULTS[role]
    kw = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
          "extra_body": {"usage": {"include": True}, **(extra or {})}}   # extra: OpenRouter 额外参数，如 {"reasoning": {"effort": "low"}}
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    if kw["max_tokens"] >= 8000:                     # 长输出走流式，避免 HTTP 超时；逐块累积
        return _chat_stream(kw, model, tag, grow)
    try:
        resp = client().chat.completions.create(**kw)
    except Exception as e:
        raise RuntimeError(f"模型请求失败（{type(e).__name__}）: {str(e)[:160]}")
    _log(model, resp, tag)
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        if grow and max_tokens < 32000:   # 截断先自救一次：预算翻倍重试（JSON 类输出常被低估）
            kw["max_tokens"] = min(32000, max_tokens * 2)
            resp = client().chat.completions.create(**kw); _log(model, resp, tag + ":grow")
            choice = resp.choices[0]
            if choice.finish_reason != "length":
                return choice.message.content or ""
        raise RuntimeError(f"输出被 max_tokens={kw['max_tokens']} 截断，调大或拆分任务")
    return choice.message.content or ""


def chat_web(prompt, role="web", model=None, max_results=3, max_tokens=4000, tag="web"):
    """带联网检索的一次问答（OpenRouter web 插件）。返回 (text, citations[{title,url}])。"""
    model = model or DEFAULTS[role]
    resp = client().chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, temperature=0.2,
                                            extra_body={"plugins": [{"id": "web", "max_results": max_results}], "usage": {"include": True}})
    _log(model, resp, tag)
    m = resp.choices[0].message
    cites = []
    for a in (getattr(m, "annotations", None) or []):
        d = a.model_dump() if hasattr(a, "model_dump") else dict(a)
        u = d.get("url_citation") or {}
        if u.get("url"): cites.append({"title": u.get("title", ""), "url": u["url"]})
    return m.content or "", cites


def _chat_stream(kw, model, tag, grow):
    """流式调用：累计 content，取 finish_reason 与 usage；网络/超时异常统一成 RuntimeError。"""
    import types
    kw = dict(kw); kw["stream"] = True; kw.setdefault("stream_options", {"include_usage": True})
    for attempt in (1, 2):
        text, finish, usage = [], None, None
        try:
            with client().chat.completions.create(**kw) as stream:
                for chunk in stream:
                    if getattr(chunk, "usage", None): usage = chunk.usage
                    if not chunk.choices: continue
                    d = chunk.choices[0]
                    if d.delta and d.delta.content: text.append(d.delta.content)
                    if d.finish_reason: finish = d.finish_reason
        except Exception as e:
            if attempt == 1: continue
            raise RuntimeError(f"模型流式请求失败（{type(e).__name__}）: {str(e)[:160]}")
        fake = types.SimpleNamespace(usage=usage)
        _log(model, fake, tag)
        out = "".join(text)
        if finish == "length":
            if grow and kw["max_tokens"] < 32000: kw["max_tokens"] = min(32000, kw["max_tokens"] * 2); continue
            raise RuntimeError(f"输出被 max_tokens={kw['max_tokens']} 截断，调大或拆分任务")
        return out
    raise RuntimeError("模型流式请求两次失败")


def chat_json(messages, **kw):
    """chat 的 JSON 版：解析失败时抛错并附原文前 300 字，不做“合理猜测”。"""
    text = chat(messages, json_mode=True, **kw)
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"模型没有返回合法 JSON: {e}; 原文开头: {text[:300]!r}")


def image_part(path):
    p = Path(path); mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"}}


def chat_vision(prompt, image_paths, role="vision", system=None, **kw):
    content = [{"type": "text", "text": prompt}] + [image_part(p) for p in image_paths]
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    return chat(msgs, role=role, **kw)


def ping():
    import urllib.request
    key = os.environ.get("OPENROUTER_API_KEY")
    print("OPENROUTER_API_KEY:", "已加载" if key else "未设置（复制 .env.example 为 .env 填入）")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/models", timeout=30) as r:
            ids = {m["id"]: m for m in json.load(r)["data"]}
    except Exception as e:
        print("拉取模型列表失败:", e); return 1
    ok = True
    for role, mid in DEFAULTS.items():
        m = ids.get(mid)
        if not m:
            ok = False; print(f"  {role:7} {mid:40} ✗ 不存在"); continue
        p = m.get("pricing", {}); img = "image" in m.get("architecture", {}).get("input_modalities", [])
        print(f"  {role:7} {mid:40} ✓ ctx={m.get('context_length')} in=${float(p.get('prompt', 0))*1e6:.2f}/M out=${float(p.get('completion', 0))*1e6:.2f}/M {'看图✓' if img else '看图✗'}")
        if role == "vision" and not img: ok = False; print("    vision 角色的模型必须支持图片输入")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--ping" in sys.argv:
        sys.exit(ping())
    if "--hello" in sys.argv:
        print(chat([{"role": "user", "content": "用一句话回答：你是什么模型？"}], role="cheap", max_tokens=100, tag="hello"))
    else:
        print(__doc__)
