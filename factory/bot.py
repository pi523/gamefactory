"""笨玩家：只通过 window.__bf 读状态，只用真实鼠标事件输入（tap/drag/swipe）。被 verify.py 调用。"""
import time


def _state(page):
    return page.evaluate("() => window.__bf.state()")


def _wait_over(page, sim_budget_s, time_scale, label):
    """等到 phase=='over'。墙钟预算 = 仿真预算 / 加速 + 余量。"""
    page.evaluate(f"() => window.__bf.setTimeScale({time_scale})")
    deadline = time.time() + sim_budget_s / time_scale + 5
    last_tick = -1; lives_prev = None; LIFE_LOG.clear()
    while time.time() < deadline:
        s = _state(page)
        if s["tick"] < last_tick:
            return s, f"{label}: tick 倒退 {last_tick}->{s['tick']}"
        last_tick = s["tick"]
        if lives_prev is not None and s["lives"] < lives_prev: LIFE_LOG.append(round(s["t"], 1))   # 掉命时间线（仿真秒）
        lives_prev = s["lives"]
        if s["phase"] == "over":
            return s, None
        if s["t"] > sim_budget_s:
            return s, f"{label}: 仿真 {sim_budget_s}s 内未结束 (t={s['t']:.1f}, lives={s['lives']})"
        page.wait_for_timeout(60)
    return _state(page), f"{label}: 墙钟超时未进入 over"


def do_action(page, t):
    """按 target 声明的动词发真实鼠标事件：tap / drag(到 t.to) / swipe(t.dir)"""
    a = t.get("action", "tap")
    if a == "drag" and t.get("to"):
        page.mouse.move(t["x"], t["y"]); page.mouse.down()
        for i in range(1, 9):                 # 慢拖（≈300ms），别被运行时判成 swipe
            page.mouse.move(t["x"] + (t["to"]["x"] - t["x"]) * i / 8, t["y"] + (t["to"]["y"] - t["y"]) * i / 8); page.wait_for_timeout(35)
        page.mouse.up()
    elif a == "swipe":
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(t.get("dir") or "right", (1, 0))
        page.mouse.move(t["x"], t["y"]); page.mouse.down()
        for i in range(1, 5):                 # 快甩（≈60ms，140px）
            page.mouse.move(t["x"] + dx * 35 * i, t["y"] + dy * 35 * i); page.wait_for_timeout(10)
        page.mouse.up()
    else:
        page.mouse.click(t["x"], t["y"])


TRACE = []   # 最近一局的 targets 快照（含 anchored/to），verify 用它做物理检查
WARMUP_S = 6.0   # 热身期：仿真前 6 秒不得掉命
LIFE_LOG = []    # 最近一次无输入对局的掉命时间线（仿真秒），verify 用来判新手节奏


def play_one(page, seed, target_score, max_wall_s, W, H):
    """点到 target_score 分后停手，等命耗尽进入 over。返回 (state, problems[])"""
    problems = []
    page.evaluate(f"() => {{ window.__bf.setTimeScale(1); window.__bf.reset({seed}); }}")
    s = _state(page)
    if s["phase"] != "menu":
        problems.append(f"reset 后 phase={s['phase']}，应为 menu")
    # menu 阶段：点任意位置应等价于 start()
    page.mouse.click(W / 2, H / 2)
    page.wait_for_timeout(50)
    s = _state(page)
    if s["phase"] != "playing":
        problems.append(f"menu 点击后 phase={s['phase']}，应为 playing")
        return s, problems

    deadline = time.time() + max_wall_s
    t_start = time.time()
    hits = 0
    prev_score = s["score"]; max_lives = s["lives"]; warm_flagged = False
    while time.time() < deadline:
        # 快速失败：点了 15 次、过了 12 秒还是 0 分，不用再等（烤制类玩法第一分要 5–8 秒：拖上去→等熟→翻→等→滑走）
        if hits >= 15 and s["score"] == 0 and time.time() - t_start > 12:
            break
        s = _state(page)
        if s["phase"] != "playing":
            break
        TRACE.extend(s["targets"])      # 游玩全程快照，供物理层检查（含拖放目的地）
        if s.get("t", 99) < WARMUP_S and s["lives"] < max_lives and not warm_flagged:
            problems.append(f"热身期掉命：仿真 t={s['t']:.1f}s 时 lives={s['lives']}（前 {WARMUP_S:.0f} 秒不得掉命，新手还没看懂就输了）"); warm_flagged = True
        if s["score"] >= target_score:
            break
        delta = s["score"] - prev_score
        if delta < 0 or delta > (100 if s.get("lesson") else 10):  # 允许连击加成，但不许倒退或离谱跳变；教学课每步准确度 ≤100 计入分数
            problems.append(f"score 异常变化 {prev_score}->{s['score']}")
        prev_score = s["score"]
        # 挑离屏幕上 35% 处最近的目标（接近抛物线顶点，移动最慢）
        cands = [t for t in s["targets"] if 0.05 * H < t["y"] < 0.9 * H and 0 < t["x"] < W]
        if not cands:
            page.wait_for_timeout(40)
            continue
        # 游戏按紧急程度排 targets；机器人按顺序取第一个可执行的动作
        t = cands[0] if any(c.get("action", "tap") != "tap" for c in cands) else min(cands, key=lambda t: abs(t["y"] - 0.35 * H))
        do_action(page, t)
        hits += 1
        page.wait_for_timeout(30)
    s = _state(page)
    if s["score"] == 0 and hits > 0:
        problems.append(f"真鼠标点击 {hits} 次，score 仍为 0（点不到 / 命中不计分）")
    # 停手，等自然结束
    s, err = _wait_over(page, 60, 4, f"seed={seed} 停手后")
    if err:
        problems.append(err)
    for k in ("score", "lives", "t"):
        if s[k] != s[k] or s[k] is None:  # NaN 检查
            problems.append(f"{k} 为 NaN/None")
    return s, problems


def play_human(page, seed, target_score, min_survive_s, reaction_ms, action_interval_ms, W, H, max_wall_s=75):
    """慢手机器人：像普通人一样反应 0.7 秒、每秒最多操作一次。要求：活过 min_survive_s 且 score ≥ target_score。返回 (state, problems)"""
    problems = []
    page.evaluate(f"() => {{ window.__bf.setTimeScale(1); window.__bf.reset({seed}); window.__bf.start(); }}")
    deadline = time.time() + max_wall_s; last_act = 0; first_seen = {}
    while time.time() < deadline:
        s = _state(page)
        if s["phase"] != "playing": break
        if s.get("lesson") is None and s["score"] >= target_score and s["t"] >= min_survive_s: break
        now = time.time()
        cands = [t for t in s["targets"] if 0.05 * H < t["y"] < 0.95 * H]
        for t in cands: first_seen.setdefault(t["id"], now)          # 看到目标的时刻
        ready = [t for t in cands if now - first_seen[t["id"]] >= reaction_ms / 1000]
        if ready and now - last_act >= action_interval_ms / 1000:
            do_action(page, ready[0]); last_act = time.time()
        page.wait_for_timeout(50)
    s = _state(page)
    if s["phase"] == "over" and s["t"] < min_survive_s:
        problems.append(f"慢手机器人（反应 {reaction_ms}ms、每 {action_interval_ms}ms 最多一次操作）在 t={s['t']:.1f}s 就输了（要求活过 {min_survive_s:.0f}s，得分 {s['score']}）：普通人跟不上这个节奏")
    elif s["score"] < target_score:
        problems.append(f"慢手机器人玩了 {s['t']:.0f}s 只得 {s['score']} 分（要求 ≥{target_score}）：操作太多或窗口太短，普通人做不成")
    return s, problems


def idle_run(page, seed, sim_budget_s, time_scale, second_loss_min_s=15.0):
    """不输入，必须能自然结束；且新手节奏：第 2 次掉命不得早于 15 秒（第 1 次不早于热身期）。返回 (state, problem|None)"""
    page.evaluate(f"() => {{ window.__bf.reset({seed}); window.__bf.start(); }}")
    s, err = _wait_over(page, sim_budget_s, time_scale, f"idle seed={seed}")
    if err: return s, err
    if LIFE_LOG and LIFE_LOG[0] < WARMUP_S:
        return s, f"idle seed={seed}: 第 1 次掉命在 t={LIFE_LOG[0]}s（热身期 {WARMUP_S:.0f} 秒内不得掉命）"
    if len(LIFE_LOG) >= 2 and LIFE_LOG[1] < second_loss_min_s:
        return s, f"idle seed={seed}: 完全不操作时第 2 次掉命在 t={LIFE_LOG[1]}s（应 ≥ {second_loss_min_s:.0f}s：新手还没看懂就连掉两命，节奏太快）掉命时间线 {LIFE_LOG[:4]}"
    return s, None


def determinism(page, seed, sim_budget_s, time_scale):
    """同种子两次 idle，over 时的 t 与 tick 必须一致。"""
    a, ea = idle_run(page, seed, sim_budget_s, time_scale)
    b, eb = idle_run(page, seed, sim_budget_s, time_scale)
    if ea or eb:
        return ea or eb
    if abs(a["t"] - b["t"]) > 1e-6:
        return f"同种子 {seed} 两局 over 时间不同：{a['t']:.4f} vs {b['t']:.4f}"
    return None
