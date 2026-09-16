#!/usr/bin/env python3
"""给一款游戏生成专属素材：1 张竖屏背景（背景即关卡布局，附 layout.json 锚点）+ PRD 里每个物件 N 张抠图，落到 games/<id>/assets/，并写游戏本地 manifest.json。
用法: .venv/bin/python factory/make_assets.py games/<id> [--force] [--only bg|props] [--variants 2]
生图走 OpenRouter（模型/模板/限额见 specs/style.json → imagegen）。物件用品红底色键抠图（factory/cutout.py）。
1024 PNG 原图存 source/generated/<id>/，游戏里用 512px WebP 副本控制包体。台账 games/<id>/assets-gen-log.jsonl。
"""
import argparse, os, base64, io, json, re, sys, time
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import llm  # noqa: E402
from cutout import chroma_key, corners_clear, pick_key, tight_square  # noqa: E402

STYLE = json.loads((ROOT / "specs/style.json").read_text(encoding="utf-8"))
IG = STYLE["imagegen"]
ANGLES = STYLE["prompt_template"]["angles"]
TRAY_ANGLE = "seen from a standing cook's viewpoint looking down at about 50 degrees (three-quarter view from above, NOT top-down, NOT eye-level), the item resting on a flat counter, its base and contact footprint visible"
WOK_ANGLE = "seen from a standing cook's viewpoint looking down into the pan at about 50 degrees (three-quarter perspective, NOT top-down, NOT side view), the food lying flat on the pan bottom with its natural elliptical footprint"


def gen_image(prompt, model, tag, ref_images=None):
    """返回 PIL.Image（RGB）。OpenRouter 图像输出在 message.images[0].image_url.url（data URL）。ref_images: 参考图路径列表（图生图/原地编辑）。"""
    content = prompt if not ref_images else ([{"type": "text", "text": prompt}] + [llm.image_part(str(r)) for r in ref_images])
    resp = llm.client().chat.completions.create(model=model, messages=[{"role": "user", "content": content}],
                                                extra_body={"modalities": ["image", "text"], "usage": {"include": True}})
    llm._log(model, resp, tag)
    m = resp.choices[0].message
    imgs = getattr(m, "images", None) or (m.model_extra or {}).get("images") or []
    if not imgs:
        raise RuntimeError(f"模型没有返回图片，文本: {(m.content or '')[:200]!r}")
    url = imgs[0]["image_url"]["url"] if isinstance(imgs[0], dict) else imgs[0].image_url.url
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def log(game, rec):
    (game / "assets-gen-log.jsonl").open("a", encoding="utf-8").write(json.dumps({**rec, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")


SCENE_TYPE_EN = {"中餐后厨": "Chinese restaurant kitchen", "西餐开放厨房": "Western open kitchen", "烧烤摊": "street BBQ stall at night",
                 "烘焙房": "artisan bakery", "日料板前": "Japanese sushi counter", "火锅店": "hot pot restaurant table", "早餐铺": "Chinese breakfast stall",
                 "咖啡吧": "coffee bar", "街头小吃车": "street food cart", "海鲜大排档": "seafood open-air eatery"}


def _json(text):
    s = text.strip()
    if s.startswith("```"): s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(s)


def verify_layout_overlay(img_path, d, lay, game):
    """独立复核：把量出的锚点画到图上，让视觉模型逐个判断是否真的落在可放食材的开口/轨道上。返回通过的子集。"""
    from PIL import ImageDraw
    im = Image.open(img_path).convert("RGB"); W, H = im.size; dr = ImageDraw.Draw(im)
    items = d.get("slots") if d.get("type") == "slots" else d.get("points")
    if not items: return d, 0
    for i, s in enumerate(items, 1):
        cx, cy = s["x"] * W, s["y"] * H; r = (s.get("r", 0.03) * W) if d.get("type") == "slots" else 0.03 * W
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 255, 120), width=5); dr.text((cx - 6, cy - 8), str(i), fill=(0, 255, 120))
    chk = ROOT / "source/generated" / game.name / f"{Path(img_path).stem}_check.png"; im.save(chk)
    q = (f"图上有 {len(items)} 个绿色编号圆圈。这张图是游戏背景，玩法要把食材放在【{lay['zh']}】上。"
         "请逐个判断：圆圈中心是否落在一个真实可放食材的位置（烤位/锅口/格子/轨道表面），而不是边框、地面、空气、桌沿、装饰。"
         "只输出 JSON：{\"ok\":[true,false,...]}（长度等于圆圈数，按编号顺序），并加 \"note\":\"一句话说明画面里实际有几个可用位置\"。宁可判 false。")
    res = _json(llm.chat_vision(q, [str(chk)], role="vision", max_tokens=3000, json_mode=True, tag=f"layoutcheck:{game.name}"))
    ok = res.get("ok", [])
    kept = [s for s, o in zip(items, ok) if o is True]
    print(f"    复核：{sum(1 for o in ok if o is True)}/{len(items)} 个锚点确认在位；{res.get('note', '')}")
    d2 = dict(d); d2["slots" if d.get("type") == "slots" else "points"] = kept; d2["verified"] = True; d2["check_image"] = str(chk.relative_to(ROOT))
    return d2, len(kept)


def extract_layout(img_path, prd, game):
    """让视觉模型从背景图里量出锚点，再用叠图独立复核，返回 (layout dict, 复核通过数)"""
    lay = prd["layout"]
    prompt = IG["layout_extract_prompt"].format(layout_zh=lay["zh"], layout_type=lay["type"], count=lay.get("count", "若干"))
    d = _json(llm.chat_vision(prompt, [str(img_path)], role="vision", max_tokens=6000, json_mode=True, tag=f"layout:{game.name}"))
    found = len(d.get("slots") or d.get("points") or [])
    print(f"    提取：{found} 个锚点")
    if found == 0: return d, 0
    return verify_layout_overlay(img_path, d, lay, game)


def detect_pool(im, slot, game=None):
    """让视觉模型量出锅底那片平的油面（食材真正躺的地方）：返回归一化 {x,y,rx,ry}（rx/ry 以图宽为单位）。亮度法会把锅壁反光当油面，所以用视觉模型。"""
    W, H = im.size
    tmp = ROOT / "source/generated" / (game.name if game else "_tmp"); tmp.mkdir(parents=True, exist_ok=True)
    pth = tmp / "pool_probe.png"; im.save(pth)
    q = ("图里有一口炒锅。请找出锅底那一片平的、有油/微亮的圆形或椭圆形区域（食材下锅后真正躺着的地方，不是锅壁、不是锅口）。"
         "只输出 JSON：{\"x0\":左, \"y0\":上, \"x1\":右, \"y1\":下}，都是 0~1 的归一化坐标（x 相对图宽，y 相对图高），给这片油面的外接框。找不到就输出 {\"x0\":null}。")
    try:
        d = _json(llm.chat_vision(q, [str(pth)], role="vision", max_tokens=400, json_mode=True, tag=f"pool:{game.name if game else 'x'}"))
        if d.get("x0") is None: return None
        x0, y0, x1, y1 = float(d["x0"]), float(d["y0"]), float(d["x1"]), float(d["y1"])
    except Exception as e:
        print("    油面识别失败:", str(e)[:80]); return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; rx = (x1 - x0) / 2; ry = (y1 - y0) / 2 * H / W     # ry 换成图宽单位
    r = slot["r"]
    ok = (abs(cx - slot["x"]) < r * 0.6) and (abs(cy * H / W - slot["y"] * H / W) < r * 0.8) and (r * 0.2 <= rx <= r * 0.85) and (ry <= rx * 1.05) and ry >= r * 0.08
    if not ok:
        print(f"    油面框不合理（cx={cx:.2f} cy={cy:.2f} rx={rx:.2f} ry={ry:.2f} vs 锅 r={r:.2f}），弃用"); return None
    return {"x": round(cx, 4), "y": round(cy, 4), "rx": round(rx, 4), "ry": round(ry, 4)}


def game_style(game):
    sp = game / "style.json"
    return json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None


def make_backgrounds(game, prd, force):
    out = game / "assets/场景"; out.mkdir(parents=True, exist_ok=True)
    dst = out / "背景_竖1.jpg"; lay_path = game / "assets/layout.json"
    scene_type = prd.get("scene_type", "中餐后厨"); lay = prd.get("layout") or {"type": "slots", "count": 0, "zh": "", "en": ""}
    if dst.exists() and lay_path.exists() and not force:
        print("  背景/布局已存在，跳过"); return {"portrait": "assets/场景/背景_竖1.jpg"}
    layout_en = lay.get("en") or lay.get("zh", "")
    best = None
    for attempt in (1, 2):
        gs = game_style(game); anchor = (gs or {}).get("style_prompt_en") or STYLE["scene"]["anchor_en"]
        tpl = IG.get("background_template_closeup", IG["background_template"]) if prd.get("workshop") == "cooking-lesson" else IG["background_template"]
        prompt = tpl.format(anchor_en=anchor, scene_type_en=SCENE_TYPE_EN.get(scene_type, scene_type),
                            title=prd["title"], scene_hint=prd.get("scene_hint", ""), layout_en=layout_en)
        if attempt == 2 and prd.get("workshop") == "cooking-lesson":
            prompt += f" CRITICAL: the wok opening must span at least {int(lay.get('min_r', 0.34) * 200)}% of the frame width and its center must be in the LEFT part of the frame (center x at most {int(lay.get('max_x', 0.45) * 100)}% of the width). Zoom in closer."
        elif attempt == 2:
            prompt += f" CRITICAL: there must be EXACTLY {lay.get('count')} separate, identical, clearly bounded units as described, each with an obvious empty opening where one food item will sit, none merged into a continuous surface, all fully visible, evenly spaced, occupying the central 70% of the width."
        prompt += " Avoid: " + STYLE["scene"]["negative_en"]
        t0 = time.time()
        try:
            im = gen_image(prompt, IG["models"]["background"], f"bg:{game.name}:{attempt}")
        except Exception as e:
            print(f"  ✗ 背景失败: {e}"); log(game, {"kind": "background", "error": str(e)[:300]}); continue
        tmp = ROOT / "source/generated" / game.name; tmp.mkdir(parents=True, exist_ok=True)
        png = tmp / f"背景_竖_try{attempt}.png"; im.save(png)
        try:
            d, found = extract_layout(png, prd, game)
        except Exception as e:
            print(f"  ✗ 布局提取失败: {e}"); d, found = None, 0
        want = lay.get("count")
        ok = d is not None and ((lay["type"] == "slots" and want and found == want) or (lay["type"] == "path" and found >= 3))
        geo = ""
        if ok and lay["type"] == "slots" and (lay.get("min_r") or lay.get("max_x")):   # 几何验收：特写要够大、要偏左给食材列留位
            s0 = (d.get("slots") or [{}])[0]; r0, x0 = float(s0.get("r", 0)), float(s0.get("x", 1))
            geo = f" 锅口 r={r0:.2f}(≥{lay.get('min_r', 0)}) x={x0:.2f}(≤{lay.get('max_x', 1)})"
            if r0 < float(lay.get("min_r", 0)) or x0 > float(lay.get("max_x", 1)) or x0 < float(lay.get("min_x", 0)): ok = False; geo += " 不合特写要求"
            if x0 - r0 < -0.12: ok = False; geo += " 锅口被画面左缘切掉太多"
        print(f"  背景第 {attempt} 次: {im.size}，识别到 {found} 个锚点（期望 {want}）{'✓' if ok else '✗'}{geo} ({time.time()-t0:.0f}s)")
        log(game, {"kind": "background", "attempt": attempt, "size": im.size, "found": found, "want": want, "prompt": prompt})
        if best is None or (ok and not best[2]) or (d and abs(found - (want or found)) < abs(best[3] - (want or best[3]))):
            best = (im, d, ok, found, png)
        if ok: break
    if best is None: return {}
    im, d, ok, found, png = best
    if not ok:
        if dst.exists() and lay_path.exists():
            print("  ⚠ 两次都没拿到合格锚点：保留原背景与原 layout.json（背景与锚点必须成对更新，不写半套）")
            return {"portrait": "assets/场景/背景_竖1.jpg"}
        print("  ⚠ 锚点数量与 PRD 不符，且没有旧版可退：按实际识别写入")
    im.save(dst, "JPEG", quality=IG["per_game_limits"]["background_jpeg_quality"], optimize=True)
    if d:
        for s in (d.get("slots") or []):
            try: pool = detect_pool(im, s, game)
            except Exception: pool = None
            if pool: s["pool"] = pool; print(f"    油面：中心({pool['x']:.2f},{pool['y']:.2f}) rx={pool['rx']:.2f} ry={pool['ry']:.2f}（图宽单位）")
        d.update({"img_w": im.size[0], "img_h": im.size[1], "expected": lay.get("count"), "found": found, "ok": ok, "source": str(dst.relative_to(game))})
        lay_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"portrait": "assets/场景/背景_竖1.jpg"}


def judge_wok_state(game, name, st, rgba_master, lay, bg):
    """合理性闸门：把抠出的状态图按引擎的摆法贴回背景，让视觉模型判断"像不像真的在锅里"（大小、透视、光照、是否悬浮/溢出）。返回 (ok, why)。"""
    from PIL import Image as _I
    pool = lay["slots"][0]["pool"]; W, H = bg.size
    cx, cy = pool["x"] * W, pool["y"] * H; side = int(pool["rx"] * W * 2 * 1.35)
    comp = bg.copy(); sp = rgba_master.resize((side, side), _I.LANCZOS); comp.paste(sp, (int(cx - side / 2), int(cy - side / 2)), sp)
    r = int(pool["rx"] * W * 2.6); crop = comp.crop((max(0, int(cx - r)), max(0, int(cy - r * 0.9)), min(W, int(cx + r)), min(H, int(cy + r * 0.9))))
    chk = ROOT / "source/generated" / game.name / f"judge_{name}_{re.sub(r'[\\/:*?\"<>|\s]+', '·', st)}.jpg"; crop.save(chk, quality=85)
    q = (f"这是一款做菜游戏的画面局部：锅里应该是「{name}」在「{st}」这个阶段。请像美术总监一样严格判断这张图是否可以直接上线：食物是否真的躺在锅底（不是悬浮、不压锅沿、不超出锅口、汤汁不爬到锅壁高处），大小是否像家常一份菜（不是巨型积木、不是半锅汤），透视与光照是否与锅一致，颜色是否正常（无绿边/紫边/生硬贴纸边）。"
         "只输出 JSON {\"ok\": true/false, \"why\": \"一句话\"}。有任何一条明显不对就 false。")
    try:
        res = _json(llm.chat_vision(q, [str(chk)], role="vision", max_tokens=1500, json_mode=True, tag=f"wokjudge:{game.name}"))
        return bool(res.get("ok")), str(res.get("why", ""))[:80]
    except Exception as e:
        return True, f"判定失败放行: {str(e)[:50]}"


def change_mask(crop, ref_crop, ellipse_mask, thr=18):
    """自适应蒙版 v2：变化像素 → 闭运算补洞 → 取最大连通块并填实内部（食物内部一律不透明，不再有"半透明发光贴片"）→ 轮廓外 1% 羽化 → 与油面椭圆相交。"""
    import cv2, numpy as np
    from PIL import ImageChops, ImageFilter
    d = np.asarray(ImageChops.difference(crop.convert("RGB"), ref_crop.convert("RGB")).convert("L"), dtype=np.float32)
    m = (d > thr).astype(np.uint8)
    side = crop.size[0]; k = max(5, int(side * 0.03) | 1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); m = (lab == keep).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(m)
    if cnts: cv2.drawContours(filled, cnts, -1, 1, thickness=-1)        # 填实内部
    a = Image.fromarray((filled * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(side * 0.008))
    a = np.asarray(a, dtype=np.float32) / 255.0
    e_ = np.asarray(ellipse_mask, dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(a, 0, 1) * np.clip(e_ * 1.6, 0, 1) * 255).astype(np.uint8))


def pantry_cut(im, bg, box, W, H):
    """单件备料的抠图：GrabCut（以视觉模型框为初始）取物体轮廓 ∪ 强变化像素；底座下方一条窄带保留柔和接触阴影。
    返回 (RGBA 方图, 质检信息)。质检：边框上不能有 alpha（否则是方块/暗块），覆盖率 8%–60%。"""
    import cv2, numpy as np
    from PIL import ImageChops, ImageFilter
    x0, y0, x1, y1 = box; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.08; side = int(max(x1 - x0, y1 - y0) * 1.6)   # 裁方放大并下移：给底部接触阴影留位置，阴影不碰裁框
    bx, by = int(cx - side / 2), int(cy - side / 2)
    crop = im.crop((bx, by, bx + side, by + side)); bgc = bg.crop((bx, by, bx + side, by + side))
    arr = cv2.cvtColor(np.asarray(crop.convert("RGB")), cv2.COLOR_RGB2BGR)
    rect = (int(x0 - bx), int(y0 - by), int(x1 - x0), int(y1 - y0)); rect = (max(1, rect[0]), max(1, rect[1]), min(side - 2 - rect[0], rect[2]), min(side - 2 - rect[1], rect[3]))
    gc = np.zeros(arr.shape[:2], np.uint8); bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(arr, gc, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT); fg = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8)
    except Exception:
        fg = np.zeros(arr.shape[:2], np.uint8)
    d = np.asarray(ImageChops.difference(crop.convert("RGB"), bgc.convert("RGB")).convert("L"), dtype=np.float32)
    strong = (d > 48).astype(np.uint8)
    obj = cv2.morphologyEx(np.maximum(fg, strong), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)); obj = cv2.morphologyEx(obj, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    # 只留视觉模型框（外扩 8%）以内的像素——相邻的瓶罐不许混进来
    inb = np.zeros_like(obj); ex = int((x1 - x0) * 0.08); ey = int((y1 - y0) * 0.08)
    inb[max(0, rect[1] - ey): rect[1] + rect[3] + ey, max(0, rect[0] - ex): rect[0] + rect[2] + ex] = 1; obj = obj * inb
    # 再只留最大的连通块
    n, lab, stats, _ = cv2.connectedComponentsWithStats(obj, 8)
    if n > 1:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); obj = (lab == keep).astype(np.uint8)
    # 接触阴影：物体底部以下 0.18×高 的带内，弱变化像素作为半透明
    ys = np.nonzero(obj)[0]; alpha = obj.astype(np.float32)
    if ys.size:
        bottom = int(ys.max()); band = np.zeros_like(alpha); band[bottom - 4: min(side - 6, bottom + int((y1 - y0) * 0.16)), max(3, rect[0] - ex): min(side - 3, rect[0] + rect[2] + ex)] = 1
        shadow = np.clip((d - 10) / 30, 0, 1) * band * (1 - obj); alpha = np.maximum(alpha, shadow * 0.7)
    a = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    rgba = crop.convert("RGBA"); rgba.putalpha(a)
    am = np.asarray(a, dtype=np.float32) / 255
    border = float(np.concatenate([am[0], am[-1], am[:, 0], am[:, -1]]).mean()); cov = float((am > 0.5).mean())
    return rgba, {"border_alpha": round(border, 3), "coverage": round(cov, 3), "ok": border < 0.03 and 0.05 <= cov <= 0.6}


def make_pantry(game, prd, force):
    """备料台 v4「照片即备料」：让图像模型在背景右侧台面上一次摆好全部备料（同机位同光照、真实阴影），这张图直接作为显示背景——
    静止时备料就是照片的一部分，没有任何贴图。每件另外准备两张小图：拿起来时跟手的"物件抠图"，和盖住原位的"空台面补丁"（来自空背景）。
    位置写进 layout.json.pantry；全部通过（每件都被找到、互不重叠、都在台面上、合成审查通过）才写盘。"""
    import cv2, numpy as np
    from PIL import ImageChops, ImageFilter
    lay_path = game / "assets/layout.json"; bg_path = game / "assets/场景/背景_竖1.jpg"; empty_path = game / "assets/场景/背景_空1.jpg"
    if not (lay_path.exists() and bg_path.exists()): return {}
    lay = json.loads(lay_path.read_text(encoding="utf-8"))
    items = [a for a in prd.get("assets", []) if a.get("slot") == "tray" and not a.get("replaced_by")]
    if not items: return {}
    if not empty_path.exists(): (game / "assets/场景").mkdir(parents=True, exist_ok=True); Image.open(bg_path).save(empty_path, quality=92)   # 第一次：把空锅背景存为"空背景"
    bg = Image.open(empty_path).convert("RGB"); W, H = bg.size
    have = all((game / "assets" / a.get("category", "食物") / f"{a['name']}1.webp").exists() for a in items)
    if have and lay.get("pantry") and len(lay["pantry"]) == len(items) and lay.get("pantry_mode") == "photo" and not force:
        print("  备料台（照片）已存在，跳过"); return _pantry_manifest(game, items)
    master_dir = ROOT / "source/generated" / game.name; master_dir.mkdir(parents=True, exist_ok=True)
    gs = game_style(game) or {}
    if not lay.get("counter_top"):
        try:
            r_ = _json(llm.chat_vision("这张图里，右侧那片不锈钢台面的最上边缘（墙面/挡板与台面的交界线）在图高的什么位置？只输出 JSON {\"y\": 0~1 的小数}。", [str(empty_path)], role="vision", max_tokens=200, json_mode=True, tag=f"counter:{game.name}"))
            lay["counter_top"] = float(r_["y"])
        except Exception: lay["counter_top"] = 0.36
    ct = lay["counter_top"]
    desc = "; ".join(f"{i+1}) " + (("a small white ceramic bowl filled with " + re.sub(r"\b(in|served in) (one )?small white ceramic (prep )?bowl", "", re.sub(r',\s*(prepared ingredient|standing upright|straight-on|whole bottle|product photo|top-down|single bowl|no utensils|no hands)[^;]*', '', a.get('subject_en', a['name'])))) if a.get("category") != "调料" else re.sub(r',\s*(standing upright|straight-on|whole bottle|product photo|no hands)[^;]*', '', a.get('subject_en', a['name']))) for i, a in enumerate(items))
    prompt = (f"{gs.get('style_prompt_en', 'Photorealistic')}. The attached photo is the exact stove scene of a cooking game. Produce the SAME photo — identical camera, wok, stove, counter, wall and lighting — with ONE change: "
              f"on the EMPTY steel counter at the right side (x from 70% to 96% of the width, y from {int((ct+0.10)*100)}% to 90% of the height — on the counter surface well below the wall, never touching the wall), place these {len(items)} prep items in ONE vertical column from top to bottom with a clear gap of at least one item-height between neighbours (none touching), each small (about 8% of the frame width), each standing/sitting ON the counter with its natural soft contact shadow and a faint reflection on the steel: {desc}. "
              f"Loose or liquid ingredients are inside small white ceramic bowls. Nothing else changes. No hands, no text.")
    for attempt in (1, 2, 3, 4, 5, 6):
        try:
            im = gen_image(prompt if attempt == 1 else prompt + f" IMPORTANT: the TOP edge of the topmost item must be below {int((ct+0.10)*100)}% of the frame height (well under the wall/counter edge); exactly {len(items)} items in one vertical column on the right counter, evenly spaced, none overlapping, none on the wall, none near the wok.", IG["models"]["prop"], f"pantry:{game.name}:{attempt}", ref_images=[empty_path])
            if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
            probe = master_dir / "pantry_full.png"; im.save(probe)
            q = (f"这张图右侧台面上有 {len(items)} 件备料，从上到下应为：" + "；".join(f"{i+1}.{a['name']}" for i, a in enumerate(items)) +
                 "。请给每件物件本身（不含阴影）的外接框，归一化坐标（x 相对图宽，y 相对图高）。只输出 JSON {\"items\":[{\"n\":1,\"x0\":,\"y0\":,\"x1\":,\"y1\":}...]}；找不到的项不要输出。")
            res = _json(llm.chat_vision(q, [str(probe)], role="vision", max_tokens=1500, json_mode=True, tag=f"pantrybox:{game.name}"))
            boxes = {int(b["n"]): b for b in res.get("items", []) if b.get("x0") is not None}
            if len(boxes) < len(items): raise RuntimeError(f"只找到 {len(boxes)}/{len(items)} 件")
            bl = [(boxes[i + 1]["x0"], boxes[i + 1]["y0"], boxes[i + 1]["x1"], boxes[i + 1]["y1"]) for i in range(len(items))]
            for i, (x0, y0, x1, y1) in enumerate(bl):
                if x0 < 0.6 or y0 < ct - 0.04: raise RuntimeError(f"{items[i]['name']} 不在右侧台面（x0={x0:.2f} y0={y0:.2f} 台面上缘 {ct:.2f}）")
                if (x1 - x0) > 0.22 or (y1 - y0) > 0.22: raise RuntimeError(f"{items[i]['name']} 太大 {(x1-x0):.2f}x{(y1-y0):.2f}")   # 瓶子偏高，放宽到 22%
            for i in range(len(bl)):
                for j in range(i + 1, len(bl)):
                    ax0, ay0, ax1, ay1 = bl[i]; bx0_, by0_, bx1_, by1_ = bl[j]
                    iw, ih = max(0, min(ax1, bx1_) - max(ax0, bx0_)), max(0, min(ay1, by1_) - max(ay0, by0_))
                    if iw * ih > 0.35 * min((ax1 - ax0) * (ay1 - ay0), (bx1_ - bx0_) * (by1_ - by0_)): raise RuntimeError(f"{items[i]['name']} 与 {items[j]['name']} 叠在一起")   # 透视下前后件的框会部分相交，只拒绝真正压住的
            # 全图合成审查（这张就是玩家看到的静止画面）
            chk = master_dir / "pantry_check.jpg"; im.crop((int(W * 0.5), int(H * 0.15), W, int(H * 0.95))).save(chk, quality=88)
            jq = ("这是做菜游戏画面右半边的实拍风格背景：台面上摆着备料（碟装食材、调料瓶）。像美术总监一样判断这些备料是否像真的摆在台面上：散料是否装在碟里、互不重叠、边缘干净、不悬浮、阴影贴合台面、透视与台面一致。只输出 JSON {\"ok\": true/false, \"why\": \"一句话\"}。")
            jr = _json(llm.chat_vision(jq, [str(chk)], role="vision", max_tokens=800, json_mode=True, tag=f"pantryjudge:{game.name}"))
            if not jr.get("ok"): raise RuntimeError(f"备料台闸门不过：{str(jr.get('why', ''))[:80]}")
            # 每件：物件抠图（拿起时用）+ 空位补丁（盖住原位）
            manifest = {}; pantry = []; staged = []
            arr_full = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
            for i, a in enumerate(items):
                x0, y0, x1, y1 = [int(v * s) for v, s in zip(bl[i], (W, H, W, H))]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.06; side = int(max(x1 - x0, y1 - y0) * 1.5)
                bx, by = int(cx - side / 2), int(cy - side / 2); bx = max(0, min(bx, W - side)); by = max(0, min(by, H - side))
                sub = arr_full[by: by + side, bx: bx + side]; gc = np.zeros(sub.shape[:2], np.uint8)
                rect = (max(1, x0 - bx - 2), max(1, y0 - by - 2), min(side - 3, x1 - x0 + 4), min(side - 3, y1 - y0 + 4))
                cv2.grabCut(sub, gc, rect, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_RECT)
                fg = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.uint8); fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
                nl, lb, st_, _c = cv2.connectedComponentsWithStats(fg, 8)
                if nl > 1: fg = (lb == 1 + int(np.argmax(st_[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
                if fg.mean() < 0.04: raise RuntimeError(f"{a['name']} 抠图失败（区域过小）")
                # 阴影带：物件底部以下，比空背景暗的像素
                dl = np.asarray(im.convert("L"), dtype=np.float32)[by: by + side, bx: bx + side] - np.asarray(bg.convert("L"), dtype=np.float32)[by: by + side, bx: bx + side]
                band = np.zeros_like(fg, dtype=np.float32); yb = min(side - 1, y1 - by); band[yb: min(side, yb + int((y1 - y0) * 0.18)), max(0, x0 - bx - 6): min(side, x1 - bx + 6)] = 1
                alpha = np.maximum(fg.astype(np.float32), np.clip((-dl - 10) / 28, 0, 1) * band * (1 - fg) * 0.75)
                am = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
                crop = im.crop((bx, by, bx + side, by + side)).convert("RGBA"); crop.putalpha(am)
                hole = bg.crop((bx, by, bx + side, by + side)).convert("RGBA")                      # 空台面补丁：拿起后盖住原位
                staged.append((a, crop, hole)); pantry.append({"name": a["name"], "x": round((bx + side / 2) / W, 4), "y": round((by + side / 2) / H, 4), "side": round(side / W, 4)})
            # 全部通过 → 写盘：显示背景换成带备料的照片
            im.save(bg_path, "JPEG", quality=IG["per_game_limits"]["background_jpeg_quality"], optimize=True)
            for a, crop, hole in staged:
                cat = a.get("category", "食物"); out = game / "assets" / cat; out.mkdir(parents=True, exist_ok=True)
                if not (out / f"{a['name']}1.webp").exists():                                       # 拿起时的精灵：优先用 make_props 的绿幕抠图（更干净）；没有才用照片里抠的
                    crop.save(master_dir / f"{a['name']}·照片抠1.png"); crop.resize((IG["per_game_limits"]["prop_size_px"],) * 2, Image.LANCZOS).save(out / f"{a['name']}1.webp", "WEBP", quality=88, method=6)
                manifest.setdefault(cat, {})[a["name"]] = {"默认": [f"assets/{cat}/{a['name']}1.webp"]}
            lay["pantry"] = pantry; lay["pantry_mode"] = "photo"
            for cat, names in make_holes(game, items, lay, im, bg).items(): manifest.setdefault(cat, {}).update(names)   # 空位补丁：颜色匹配 + 圆角羽化
            lay_path.write_text(json.dumps(lay, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  备料台（照片）✓ {len(items)} 件在台面上：" + "、".join(f"{p['name']}@({p['x']:.2f},{p['y']:.2f})" for p in pantry))
            log(game, {"kind": "pantry", "mode": "photo", "pantry": pantry, "prompt": prompt})
            return manifest
        except Exception as e:
            print(f"  ↻ [备料台·照片] 第 {attempt} 次: {str(e)[:120]}")
    print("  ✗ 备料台照片法三次不过，保留现有备料"); return {}


def make_holes(game, items, lay, bg_display, bg_empty):
    """备料"空位补丁"：拿起某件后盖住它原位的那块空台面。取自空背景，但按显示背景（带备料那张，色调略有不同）做颜色匹配，边缘圆角羽化，避免出现方块。"""
    import numpy as np
    from PIL import ImageDraw, ImageFilter
    W, H = bg_display.size; out = {}
    for pinfo in lay.get("pantry", []):
        a = next((x for x in items if x["name"] == pinfo["name"]), None)
        if not a: continue
        side = int(pinfo["side"] * W); bx, by = int(pinfo["x"] * W - side / 2), int(pinfo["y"] * H - side / 2)
        # 补丁只需盖住物件本身+接触阴影（备料框的 1.5 倍里留了很多空），缩到 0.85，避免压到相邻的碟子
        shrink = int(side * 0.85); bx += (side - shrink) // 2; by += (side - shrink) // 2 + int(side * 0.03); side = shrink
        # 空位来源：优先显示背景里同一行、不压到任何备料也不压到锅的一块空台面（亮度天然一致）；找不到就用空背景同位置 + 外圈颜色匹配
        slot = lay["slots"][0]; boxes = [(int(q["x"] * W - q["side"] * W / 2), int(q["y"] * H - q["side"] * W / 2), int(q["side"] * W)) for q in lay.get("pantry", [])]
        def clear(sx):
            if sx < 0 or sx + side > W: return False
            for (qx, qy, qs) in boxes:
                if sx < qx + qs and sx + side > qx and by < qy + qs and by + side > qy: return False
            cx_, cy_ = sx + side / 2, by + side / 2
            return ((cx_ - slot["x"] * W) ** 2 + (cy_ - slot["y"] * H) ** 2) ** 0.5 > slot["r"] * W * 1.15 + side * 0.7
        src = None
        for k_ in (1.1, 1.6, 2.1, -1.1, -1.6):
            sx = bx - int(side * k_)
            if clear(sx): src = ("display", sx); break
        if src:
            sx = src[1]; hole = np.asarray(bg_display.crop((sx, by, sx + side, by + side)).convert("RGB"), dtype=np.float32)
            ring_s = np.asarray(bg_display.crop((sx - 8, by - 8, sx + side + 8, by + side + 8)).convert("RGB"), dtype=np.float32)
        else:
            hole = np.asarray(bg_empty.crop((bx, by, bx + side, by + side)).convert("RGB"), dtype=np.float32)
            ring_s = np.asarray(bg_empty.crop((bx - 8, by - 8, bx + side + 8, by + side + 8)).convert("RGB"), dtype=np.float32)
        ring_d = np.asarray(bg_display.crop((bx - 8, by - 8, bx + side + 8, by + side + 8)).convert("RGB"), dtype=np.float32)
        m = np.ones(ring_d.shape[:2], bool); m[8:-8, 8:-8] = False
        gain = (ring_d[m].mean(axis=0) + 1) / (ring_s[m].mean(axis=0) + 1)
        hole = np.clip(hole * gain, 0, 255).astype(np.uint8)
        am = Image.new("L", (side, side), 0); ImageDraw.Draw(am).rounded_rectangle((2, 2, side - 3, side - 3), radius=int(side * 0.18), fill=255); am = am.filter(ImageFilter.GaussianBlur(side * 0.05))
        im = Image.fromarray(hole).convert("RGBA"); im.putalpha(am)
        cat = a.get("category", "食物"); dst = game / "assets" / cat / f"{a['name']}·空位1.webp"; dst.parent.mkdir(parents=True, exist_ok=True)
        im.resize((IG["per_game_limits"]["prop_size_px"],) * 2, Image.LANCZOS).save(dst, "WEBP", quality=88, method=6)
        out.setdefault(cat, {})[f"{a['name']}·空位"] = {"默认": [f"assets/{cat}/{dst.name}"]}
    return out


def _pantry_manifest(game, items):
    return {a.get("category", "食物"): {} for a in items} and {cat: {a["name"]: {"默认": [f"assets/{cat}/{a['name']}1.webp"]} for a in items if a.get("category", "食物") == cat} for cat in {a.get("category", "食物") for a in items}}


def make_effects(game, prd, force):
    """背景变体：同一张照片原地改火苗（小/中/大）和蒸汽（无/有两帧），共 6 张；引擎按火力档与蒸汽帧交叉淡入切换整张背景。
    每张检查：变化像素必须集中在灶口/锅口区域（≥70%），否则重试。写入 manifest.__scene: fire{0,1,2}_s{0,1}。"""
    import numpy as np
    from PIL import ImageChops
    lay_path = game / "assets/layout.json"; bg_path = game / "assets/场景/背景_竖1.jpg"
    if not (lay_path.exists() and bg_path.exists()): return {}
    lay = json.loads(lay_path.read_text(encoding="utf-8")); slot = lay["slots"][0]; pool = slot.get("pool") or {"x": slot["x"], "y": slot["y"]}
    bg = Image.open(bg_path).convert("RGB"); W, H = bg.size
    out = game / "assets/场景"; scene = {"portrait": "assets/场景/背景_竖1.jpg"}
    keys = [(f"fire{lv}_s{sf}", lv, sf) for lv in (0, 1, 2) for sf in (0, 1)]
    if all((out / f"背景_{k}.jpg").exists() for k, _, _ in keys) and not force:
        for k, _, _ in keys: scene[k] = f"assets/场景/背景_{k}.jpg"
        return {"__scene": scene}
    fire_txt = {0: "the gas flame under the wok is turned down to a very small, low blue ring, barely visible under the wok", 1: None, 2: "the gas flame under the wok is turned up high: taller, vigorous BLUE gas flames (blue cones with only faint orange tips) rising from the burner ring and licking the wok bottom — still a real gas burner flame, not a fireball or glow"}
    steam_txt = {0: "a soft, thin, translucent plume of white steam rises from inside the wok, going almost straight up and slightly to the left, dissipating above the rim — the wok interior itself stays EXACTLY as in the photo (do not add or change any food)",
                 1: "a soft, thin, translucent plume of white steam rises from inside the wok, a bit taller and drifting to the right, dissipating above the rim — the wok interior itself stays EXACTLY as in the photo (do not add or change any food)"}
    # 检查区域：灶口（锅口下方）+ 锅口上方（蒸汽）
    yy, xx = np.mgrid[0:H, 0:W]
    burner = ((xx - slot["x"] * W) ** 2 / (slot["r"] * W * 1.1) ** 2 + (yy - (slot["y"] * H + slot["r"] * W * 0.85)) ** 2 / (slot["r"] * W * 0.5) ** 2) <= 1
    prx, pry = (pool.get("rx", slot["r"] * 0.5) * W), (pool.get("ry", slot["r"] * 0.3) * W)
    above = ((xx - pool["x"] * W) ** 2 / (slot["r"] * W * 0.9) ** 2 + (yy - (pool["y"] * H - pry - slot["r"] * W * 0.75)) ** 2 / (slot["r"] * W * 0.85) ** 2) <= 1
    poolm = ((xx - pool["x"] * W) ** 2 / (prx * 1.15) ** 2 + (yy - pool["y"] * H) ** 2 / (pry * 1.15) ** 2) <= 1
    above &= ~poolm                                                                          # 蒸汽区不含油面：锅里的东西一个像素都不能动
    gs = game_style(game) or {}
    for key, lv, sf in keys:
        dst = out / f"背景_{key}.jpg"
        changes = [c for c in (fire_txt[lv], steam_txt[sf]) if c]; region = (burner if lv != 1 else np.zeros_like(burner)) | above
        prompt = (f"{gs.get('style_prompt_en', 'Photorealistic')}. The attached photo is the exact stove scene of a cooking game. Produce the SAME photo — identical camera, wok, food, stove, counter, prep items and lighting — with ONLY these changes: " + "; ".join(changes) + ". Everything else stays pixel-identical. No hands, no text.")
        ok = False; err = None
        for attempt in (1, 2, 3):
            try:
                im = gen_image(prompt, IG["models"]["prop"], f"scene:{game.name}:{key}", ref_images=[bg_path])
                if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
                d = np.asarray(ImageChops.difference(im, bg).convert("L"), dtype=np.float32); ch = d > 20
                frac_in = float(ch[region].sum() / max(1, ch.sum())); total = float(ch.mean())
                if total < 0.002: raise RuntimeError("几乎没变化")
                strong = d > 45                                                                       # 合成时油面区一律用原图，这里只防"往锅里画了食物"这种大改
                if float(strong[poolm].mean()) > 0.12: raise RuntimeError(f"锅里被画了东西（油面区 {float(strong[poolm].mean()):.0%} 像素大变）")
                if frac_in < 0.7: raise RuntimeError(f"变化不集中在灶口/锅口（{frac_in:.0%} 在区域内，总变化 {total:.1%}）")
                # 只把区域内的变化贴回原图，其余像素保持与主背景一致（杜绝闪变）
                m = Image.fromarray((np.clip(region.astype(np.float32) * 255, 0, 255)).astype(np.uint8)).filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(W * 0.02))
                comp = Image.composite(im, bg, m); comp.save(dst, "JPEG", quality=IG["per_game_limits"]["background_jpeg_quality"])
                scene[key] = f"assets/场景/背景_{key}.jpg"; print(f"  [背景变体] {key}: 变化 {total:.1%}，{frac_in:.0%} 在灶口/锅口 ✓"); ok = True; break
            except Exception as e_:
                err = e_; print(f"  ↻ [背景变体] {key} 第 {attempt} 次: {str(e_)[:80]}")
        if not ok: print(f"  ✗ 背景变体 {key} 放弃（{str(err)[:60]}）→ 用主背景代替"); bg.save(dst, "JPEG", quality=IG["per_game_limits"]["background_jpeg_quality"]); scene[key] = f"assets/场景/背景_{key}.jpg"
    return {"__scene": scene}


def make_wok_states(game, prd, force):
    """锅内食材的每个状态：把背景图交给图像模型『原地加食材』（同机位、同锅、同光），再按油面椭圆（放大 1.3 倍、羽化边）抠出来当贴图。
    这样透视、光照、油面反光天然一致，不再是贴纸。输出与 make_props 同名文件，manifest 结构不变。"""
    lay_path = game / "assets/layout.json"; bg_path = game / "assets/场景/背景_竖1.jpg"
    if not (lay_path.exists() and bg_path.exists()): return {}
    lay = json.loads(lay_path.read_text(encoding="utf-8")); slots = lay.get("slots") or []
    pool = slots[0].get("pool") if slots else None
    if not pool: print("  锚点里没有油面（pool），锅内状态图退回抠图法"); return {}
    bg = Image.open(bg_path).convert("RGB"); W, H = bg.size
    cx, cy = pool["x"] * W, pool["y"] * H; rx, ry = pool["rx"] * W, pool["ry"] * W
    side = int(rx * 2 * 1.35); x0, y0 = int(cx - side / 2), int(cy - side / 2)
    # 羽化椭圆蒙版（食材可略溢出油面，边缘 ~7% 渐隐）
    from PIL import ImageDraw, ImageFilter
    mask = Image.new("L", (side, side), 0); md = ImageDraw.Draw(mask)
    ex, ey = rx * 1.28, ry * 1.32; md.ellipse((side / 2 - ex, side / 2 - ey, side / 2 + ex, side / 2 + ey), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(side * 0.035))
    gs = game_style(game) or {}; lim = IG["per_game_limits"]; manifest = {}
    master_dir = ROOT / "source/generated" / game.name; master_dir.mkdir(parents=True, exist_ok=True)
    base_crop = bg.crop((x0, y0, x0 + side, y0 + side)).convert("L")
    def compose(rgba_master):        # 把某状态贴回背景 → 下一状态的参考图（模型只改"新加的这一处"）
        comp = bg.copy(); spx = rgba_master.resize((side, side), Image.LANCZOS); comp.paste(spx, (x0, y0), spx); return comp
    for a in prd.get("assets", []):
        if a.get("slot", "wok") != "wok" or a.get("replaced_by"): continue
        cat = a.get("category", "食物"); name = a["name"]; out = game / "assets" / cat; out.mkdir(parents=True, exist_ok=True)
        if a.get("timeline"):        # 时间线：按顺序生成，每张以上一张的合成图为参考，只加/只改这一步
            ref_img = bg; prev_master = None
            for k, tl in enumerate(a["timeline"]):
                st = tl["state"]; st_safe = re.sub(r"[\\/:*?\"<>|\s]+", "·", st); fname = f"{name}_{st_safe}1.webp"; dst = out / fname; master = master_dir / fname.replace(".webp", ".png")
                if dst.exists() and master.exists() and not force:
                    manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}"); prev_master = Image.open(master).convert("RGBA"); ref_img = compose(prev_master); continue
                ref_path = master_dir / f"_ref_{k:02d}.jpg"; ref_img.save(ref_path, quality=92)
                prompt = (f"{gs.get('props_prompt_en', 'Photorealistic')}. The attached photo is the exact current frame of a cooking game: a wok on a stove{' with food already in it' if prev_master is not None else ', empty except a film of oil'}. "
                          f"Produce the SAME photo — identical camera, framing, wok, stove, counter, lighting{' and the SAME food already present' if prev_master is not None else ''} — with exactly ONE change inside the wok: {tl['change_en']}. "
                          f"Perspective: the camera looks down at about 50 degrees, so the food's footprint is an ELLIPSE matching the oil pool (never a top-down circle); show the food's thickness and its far edge foreshortened. Portion continuity: keep the SAME amount as the previous frame, only add/transform what the change describes (adding one ingredient increases volume slightly; never jump to a full wok). A modest home-cooking portion (2 eggs + 2 tomatoes scale) heaped in the CENTER of the flat bottom, covering only about 60–70% of the oil pool so a rim of bare oil stays visible around it, NOT climbing the walls, little liquid — a stir-fry, not a soup. Lighting must match the scene: warm tungsten key light from upper left, darker toward the wok wall, crisp specular highlights on oil/sauce, a thin dark contact shadow where food meets the wok. Crisp realistic edges. Nothing else changes; nothing added outside the wok. No hands, no utensils, no text.")
                t0 = time.time(); ok = False; err = None
                for attempt in (1, 2, 3):
                    try:
                        im = gen_image(prompt if attempt == 1 else prompt + " IMPORTANT: keep everything already in the wok exactly as it is and ONLY apply the described change; the food must stay inside the wok bottom.", IG["models"]["prop"], f"wok:{game.name}:{st}", ref_images=[ref_path])
                        if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
                        crop = im.crop((x0, y0, x0 + side, y0 + side))
                        from PIL import ImageChops
                        base_ref = ref_img.crop((x0, y0, x0 + side, y0 + side)).convert("L")
                        diff = ImageChops.difference(crop.convert("L"), base_ref); hist = diff.histogram(); changed = sum(hist[25:]) / max(1, sum(hist))
                        if changed < 0.04: raise RuntimeError(f"锅里几乎没变化（{changed:.0%}）")
                        if changed > 0.75 and prev_master is not None: raise RuntimeError(f"锅里变化过大（{changed:.0%}），像是重画了整锅")
                        rgba = crop.convert("RGBA"); rgba.putalpha(mask)                 # 纯油面椭圆蒙版（变化像素法会把酱汁抠成薄片）
                        okj, why = judge_wok_state(game, name, st, rgba, lay, bg)
                        if not okj: raise RuntimeError(f"美术闸门不过：{why}")
                        rgba.save(master); rgba.resize((lim["prop_size_px"], lim["prop_size_px"]), Image.LANCZOS).save(dst, "WEBP", quality=lim.get("prop_webp_quality", 85), method=6)
                        manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}")
                        print(f"  [时间线 {k+1}/{len(a['timeline'])}] {st}: 变化 {changed:.0%} · 闸门 ✓ {why[:24]} ({time.time()-t0:.0f}s)")
                        log(game, {"kind": "wok_state", "name": name, "state": st, "changed": round(changed, 3), "prompt": prompt}); ok = True; break
                    except Exception as e:
                        err = e; print(f"  ↻ [时间线] {st} 第 {attempt} 次: {str(e)[:100]}")
                if not ok:
                    print(f"  ✗ {fname}: 放弃 ({str(err)[:80]})；后续状态以上一张为参考继续"); log(game, {"kind": "wok_state", "name": name, "state": st, "error": str(err)[:300]}); continue
                prev_master = rgba; ref_img = compose(rgba)
            continue
        for st in (a.get("states") or ["默认"]):
            st_safe = re.sub(r"[\\/:*?\"<>|\s]+", "·", st); fname = f"{name}1.webp" if st == "默认" else f"{name}_{st_safe}1.webp"; dst = out / fname
            if dst.exists() and not force:
                manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}"); continue
            subj = re.sub(r",\s*(food only|no cookware|no utensils|no bowl or plate|top-down view|natural perspective as seen by the cook)[^,]*", "", a.get("subject_en", name))
            prompt = (f"{gs.get('props_prompt_en', 'Photorealistic')}. The attached photo is the exact stove scene of a cooking game. Produce the SAME photo — identical camera, framing, wok, stove, counter and lighting — with exactly ONE change: "
                      f"{subj}, at the cooking stage '{st}' ({name}), now lies in the bottom of the wok, covering the shallow oil pool with a realistic single-serving amount, "
                      f"sitting IN the oil (partly glossy with oil, contact shadows, correct perspective for this camera angle). Nothing else changes. No hands, no utensils, no steam text, no text.")
            t0 = time.time(); ok = False; err = None
            for attempt in (1, 2, 3):
                try:
                    im = gen_image(prompt if attempt == 1 else prompt + " IMPORTANT: the food must be clearly visible, realistic single-serving size, lying INSIDE the wok bottom and filling most of the oil pool area; nothing floats, nothing sticks out past the rim.", IG["models"]["prop"], f"wok:{game.name}:{name}:{st}", ref_images=[bg_path])
                    if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
                    crop = im.crop((x0, y0, x0 + side, y0 + side))
                    # 变化检查：抠出来的区域必须真的变了（模型有时原图返回）
                    from PIL import ImageChops
                    diff = ImageChops.difference(crop.convert("L"), base_crop); hist = diff.histogram(); changed = sum(hist[25:]) / max(1, sum(hist))
                    if changed < 0.12: raise RuntimeError(f"锅里几乎没变化（{changed:.0%}），模型没把食材画进去")
                    rgba = crop.convert("RGBA"); rgba.putalpha(mask)
                    okj, why = judge_wok_state(game, name, st, rgba, lay, bg)      # 合理性闸门：贴回锅里让视觉模型审一遍
                    if not okj: raise RuntimeError(f"美术闸门不过：{why}")
                    rgba.save(master_dir / fname.replace(".webp", ".png"))
                    rgba.resize((lim["prop_size_px"], lim["prop_size_px"]), Image.LANCZOS).save(dst, "WEBP", quality=lim.get("prop_webp_quality", 85), method=6)
                    manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}")
                    print(f"  [锅内原地] {fname}: 变化 {changed:.0%} · 美术闸门 ✓ {why[:30]} → {dst.stat().st_size//1024}KB ({time.time()-t0:.0f}s)")
                    log(game, {"kind": "wok_state", "name": name, "state": st, "changed": round(changed, 3), "bytes": dst.stat().st_size, "prompt": prompt}); ok = True; break
                except Exception as e:
                    err = e; print(f"  ↻ [锅内原地] {name}/{st} 第 {attempt} 次: {str(e)[:100]}")
            if not ok: print(f"  ✗ {fname}: 放弃 ({str(err)[:80]})"); log(game, {"kind": "wok_state", "name": name, "state": st, "error": str(err)[:300]})
    return manifest


def make_props(game, prd, force, variants):
    lim = IG["per_game_limits"]
    shared = json.loads((ROOT / "assets/manifest.json").read_text(encoding="utf-8"))
    shared_names = {n for cat in shared.values() for n in cat}
    # 公共库没有的（专属道具）排前面，保证包体上限内先做最缺的
    ordered = sorted(prd.get("assets", []), key=lambda x: (x["name"] in shared_names))
    assets = ordered[: lim["max_props"]]
    if len(prd.get("assets", [])) > lim["max_props"]:
        print(f"  ⚠ PRD 有 {len(prd['assets'])} 类素材，只生成前 {lim['max_props']} 类（包体限制）")
    manifest = {}
    master_dir = ROOT / "source/generated" / game.name; master_dir.mkdir(parents=True, exist_ok=True)
    STATE_EN = {"生": "raw, uncooked", "半熟": "half-cooked, lightly browned on one side", "金黄": "perfectly grilled, golden brown with glossy char marks", "焦": "burnt, blackened and charred", "切块": "chopped", "烤": "roasted"}
    if any(a.get("states") for a in assets) and variants > 1:
        print("  ⚠ 有多状态物件，每状态只生成 1 张以控制包体"); variants = 1
    lp = game / "assets/layout.json"; has_pool = lp.exists() and bool(((json.loads(lp.read_text(encoding="utf-8")).get("slots") or [{}])[0]).get("pool"))
    for a in assets:
        if has_pool and a.get("slot", "wok") == "wok": continue      # 锅内物件走原地生成（make_wok_states）
        if a.get("replaced_by"): continue                                   # 被「锅内」时间线替换的旧物件不再生图
        cat = a.get("category", "道具"); name = a["name"]
        out = game / "assets" / cat; out.mkdir(parents=True, exist_ok=True)
        for st in (a.get("states") or ["默认"]):
          for i in range(1, variants + 1):
            st_safe = re.sub(r"[\\/:*?\"<>|\s]+", "·", st)          # 状态名里的 / 等不能进文件名
            fname = f"{name}{i}.webp" if st == "默认" else f"{name}_{st_safe}{i}.webp"
            dst = out / fname
            if dst.exists() and not force:
                manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}"); continue
            key = pick_key(a.get("subject_en", ""))
            key_name = {"magenta": "pure magenta (#FF00FF)", "green": "pure chroma green (#00FF00)"}[key]
            subj = a.get("subject_en", name) + (f", {STATE_EN.get(st, st)}" if st != "默认" else "")
            gs = game_style(game)
            angle = WOK_ANGLE if a.get("slot") == "wok" else (TRAY_ANGLE if a.get("slot") == "tray" else ANGLES[0])     # 锅内/备料都按背景相机角度（约 50°）出图
            base = IG["prop_template"].format(subject_en=subj, subject_zh=name + (st if st != "默认" else ""), angle=angle).replace("pure magenta (#FF00FF)", key_name)
            if gs and gs.get("source") == "reference" and gs.get("props_prompt_en"):   # 写实参照：摄影措辞，不出现 game/asset/cartoon 引导词
                base = (f"{gs['props_prompt_en']}. Macro food photograph, DSLR 100mm lens, of a single {subj} ({name}{st if st != '默认' else ''}), {angle}, "
                        f"isolated on a solid {key_name} flat background filling the entire frame, soft warm top light, natural specular highlights, sharp focus, centered, subject fills 80% of frame, "
                        f"no shadow on background, no text, square 1:1. Props style: {gs.get('props_style', '')}.")
            elif gs and gs.get("source") == "reference":   # 卡通/手绘参照：道具造型跟参考风格走
                base = base.replace("Photorealistic studio photo of", f"{gs.get('style_prompt_en', '')}. Game asset of") + f" Props style: {gs.get('props_style', '')}."
            if st != "默认": base += " Same object, same camera angle and framing across all cooking states."
            t0 = time.time(); rgba = None; err = None
            for attempt in (1, 2):
                prompt = base + " Avoid: " + IG["prop_negative"]
                if attempt == 2:
                    prompt = base + f" IMPORTANT: the ENTIRE background must be one flat uniform {key_name} color edge to edge, like a chroma-key screen; the object floats with absolutely no shadow, glow, vignette or gradient. Avoid: " + IG["prop_negative"]
                try:
                    im = gen_image(prompt, IG["models"]["prop"], f"prop:{game.name}:{name}{i}")
                    keyed = chroma_key(im, key)
                    if not corners_clear(keyed): raise RuntimeError(f"背景不是{key}键色（四角未透明）")
                    rgba = tight_square(keyed, size=1024)
                    if rgba is None: raise RuntimeError("抠图后为空")
                    cov = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).histogram()[255] / (1024 * 1024)
                    if cov < 0.10 or cov > 0.70: raise RuntimeError(f"主体占比异常 {cov:.2f}")
                    err = None; break
                except Exception as e:
                    err = e; rgba = None; print(f"  ↻ {name}{i} 第 {attempt} 次: {e}")
            if rgba is None:
                print(f"  ✗ {fname}: 放弃 ({err})"); log(game, {"kind": "prop", "name": name, "state": st, "i": i, "error": str(err)[:300]}); continue
            rgba.save(master_dir / fname.replace(".webp", ".png"))
            rgba.resize((lim["prop_size_px"], lim["prop_size_px"]), Image.LANCZOS).save(dst, "WEBP", quality=lim.get("prop_webp_quality", 85), method=6)
            manifest.setdefault(cat, {}).setdefault(name, {}).setdefault(st, []).append(f"assets/{cat}/{dst.name}")
            print(f"  {fname}: 占比 {cov:.2f} → {dst.stat().st_size//1024}KB ({time.time()-t0:.0f}s)")
            log(game, {"kind": "prop", "name": name, "state": st, "i": i, "bytes": dst.stat().st_size, "coverage": round(cov, 3), "prompt": prompt})
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_dir"); ap.add_argument("--force", action="store_true"); ap.add_argument("--only", choices=["bg", "props", "pantry", "effects"])
    ap.add_argument("--variants", type=int, default=IG["per_game_limits"]["variants_per_prop"])
    a = ap.parse_args()
    game = Path(a.game_dir).resolve()
    prd = json.loads((game / "prd.json").read_text(encoding="utf-8"))
    mpath = game / "assets/manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    if a.only != "props":
        manifest["__scene"] = {**(manifest.get("__scene") or {}), **make_backgrounds(game, prd, a.force)}   # 合并：别把火力/蒸汽背景变体键冲掉
        lp = game / "assets/layout.json"
        if lp.exists(): manifest["__layout"] = "assets/layout.json"
    if a.only == "effects":
        fx = make_effects(game, prd, True)
        if fx.get("__scene"): manifest["__scene"] = {**(manifest.get("__scene") or {}), **fx["__scene"]}
    elif a.only == "pantry":
        pan = make_pantry(game, prd, True)
        for cat, names in pan.items(): manifest.setdefault(cat, {}).update(names)
        if pan: manifest["__pantry"] = True
    elif a.only != "bg":
        props = make_props(game, prd, a.force, a.variants)
        for cat, names in props.items(): manifest.setdefault(cat, {}).update(names)
        wok = make_wok_states(game, prd, a.force)
        for cat, names in wok.items(): manifest.setdefault(cat, {}).update(names)
        pan = make_pantry(game, prd, a.force) if os.environ.get("BF_PANTRY_PHOTO") == "1" else {}   # 照片备料默认关（用户 09-11 决定：三维贴纸 + 合理位置；照片法抠图痕迹多）
        for cat, names in pan.items(): manifest.setdefault(cat, {}).update(names)
        if pan: manifest["__pantry"] = True
        fx = make_effects(game, prd, a.force)                                   # 再做背景变体（火力 × 蒸汽），基于带备料的背景
        if fx.get("__scene"): manifest["__scene"] = {**(manifest.get("__scene") or {}), **fx["__scene"]}

        if wok: manifest["__wokcrop"] = True      # 锅内贴图是按油面抠的原地生成图：引擎按油面尺寸摆、不再羽化
        want = {(x.get("category", "道具"), x["name"]) for x in prd.get("assets", [])}
        keep_extra = lambda cat, n: cat == "效果" or n.endswith("·空位")                      # 效果层与备料空位补丁不在 PRD 里，不能当旧物件清掉
        for cat in [k for k in manifest if not k.startswith("__") and k != "效果"]:
            stale = [n for n in manifest[cat] if (cat, n) not in want and not keep_extra(cat, n)]
            for n in stale: manifest[cat].pop(n, None)
            for f in (game / "assets" / cat).glob("*.webp"):     # 清掉换菜谱后遗留的旧贴图（空位补丁除外）
                if "·空位" in f.stem: continue
                stem = re.split(r"[_\d]", f.stem, 1)[0]
                if (cat, stem) not in want and (cat, f.stem.rstrip("0123456789")) not in want: f.unlink(); stale.append(f.name)
            if stale: print(f"  清理旧物件 {cat}: {stale}")
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(p.stat().st_size for p in (game / "assets").rglob("*") if p.is_file())
    n = sum(len(v) for c, names in manifest.items() if not c.startswith("__") for s in names.values() for v in s.values())
    print(f"ASSETS: {n} 张物件 + {len(manifest.get('__scene', {}))} 张背景，共 {total/1024/1024:.2f} MB → {mpath.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
