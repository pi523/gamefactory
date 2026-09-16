"""色键抠图：生图时让模型把物件放在纯品红 (#FF00FF) 背景上，再按"品红度"算 alpha，边缘做反预乘去色溢。
不依赖 rembg（模型文件下载太慢）。用法：
    from cutout import chroma_key_magenta
    rgba = chroma_key_magenta(Image.open("x.png"))
    python3 factory/cutout.py in.png out.png
"""
import sys
from PIL import Image


KEYS = {"magenta": (255, 0, 255), "green": (0, 255, 0)}


def chroma_key(im, key="magenta", lo=0.15, hi=0.38):
    """按"键色度"算 alpha。magenta: d=min(R-G,B-G)/255；green: d=min(G-R,G-B)/255。
    d<=lo 前景(alpha=1)，d>=hi 背景(alpha=0)，中间线性过渡并反预乘去色溢。"""
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h))
    op = out.load()
    span = hi - lo
    kr, kg, kb = KEYS[key]
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            d = (min(r - g, b - g) if key == "magenta" else min(g - r, g - b)) / 255.0
            if d <= lo:
                op[x, y] = (r, g, b, 255)
            elif d >= hi:
                op[x, y] = (0, 0, 0, 0)
            else:
                a = 1.0 - (d - lo) / span
                fr = (r - (1 - a) * kr) / a; fg = (g - (1 - a) * kg) / a; fb = (b - (1 - a) * kb) / a
                op[x, y] = (int(max(0, min(255, fr))), int(max(0, min(255, fg))), int(max(0, min(255, fb))), int(a * 255))
    return out


def chroma_key_magenta(im, lo=0.15, hi=0.38):
    return chroma_key(im, "magenta", lo, hi)


def corners_clear(rgba, margin=6):
    """四角小块必须全透明，否则说明背景不是键色（模型没听话）"""
    a = rgba.getchannel("A"); w, h = a.size
    for box in [(0, 0, margin, margin), (w - margin, 0, w, margin), (0, h - margin, margin, h), (w - margin, h - margin, w, h)]:
        if max(a.crop(box).getdata()) > 16: return False
    return True


def pick_key(subject_en):
    """紫/粉/红紫系物件和品红太近，改绿幕；绿色物件用品红。"""
    s = subject_en.lower()
    # 半透明/油膜/酱汁类会把品红透进来，也走绿幕
    return "green" if any(k in s for k in ("purple", "eggplant", "aubergine", "red onion", "grape", "plum", "beet", "cabbage red", "pink", "magenta", "violet", "oil", "translucent", "transparent", "shimmer", "glaze", "raw chicken", "raw pork", "raw meat", "chicken breast", "pork belly", "shrimp", "salmon", "ham", "sausage", "ketchup", "red plastic", "red screw cap", "red cap", "egg", "beaten", "liquid", "yolk", "cashew", "peanut", "nut", "cream", "beige")) else "magenta"


def tight_square(rgba, size=1024, fill=0.82):
    """按 alpha 包围盒裁切、居中放到 size×size 透明方图上，主体占 fill"""
    bbox = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bbox:
        return None
    crop = rgba.crop(bbox)
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    target = int(size * fill)
    canvas = canvas.resize((target, target), Image.LANCZOS)
    final = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    final.paste(canvas, ((size - target) // 2, (size - target) // 2))
    return final


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    out = tight_square(chroma_key_magenta(Image.open(src)))
    out.save(dst); print("→", dst, out.size)
