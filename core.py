# -*- coding: utf-8 -*-
"""陪跑 · 纯代码内核：不调模型、不依赖框架，全部可单测。"""

# ---------------- 设计常量（不是医学结论，调松紧只改这里） ----------------
BMR = 1720
PLAN_LO, PLAN_HI = 1650, 1850
SLIGHT_RATIO = 1.12
DANGER_KCAL = 1200
WEEK_MINUTES_CAP = 420
HIGH_RPE_MIN = 600
HIGH_MINUTES = 90
GROWTH_CAP = 0.30

BUCKETS = ("danger", "low", "normal", "slight", "over")


def classify_point(kcal, lo=PLAN_LO, hi=PLAN_HI, danger=DANGER_KCAL):
    if kcal < danger:
        return "danger"
    if kcal < lo:
        return "low"
    if kcal <= hi:
        return "normal"
    if kcal <= hi * SLIGHT_RATIO:
        return "slight"
    return "over"


def classify_day(day_lo, day_hi, lo=PLAN_LO, hi=PLAN_HI, danger=DANGER_KCAL):
    """只在日终结算调用：入参是【全天累计】摄入的区间，不是单餐。"""
    a = classify_point(day_lo, lo, hi, danger)
    b = classify_point(day_hi, lo, hi, danger)
    if a == b:
        return {"bucket": a, "ambiguous": False, "why": None}
    if day_lo < danger:
        return {"bucket": "danger", "ambiguous": True, "why": "区间下界低于危险线"}
    mid = (day_lo + day_hi) / 2
    return {"bucket": classify_point(mid, lo, hi, danger), "ambiguous": True, "why": "区间跨档，取中点"}


def load_level(sessions, week_minutes, consecutive_high_days, prev_week_minutes=None):
    today_high = any(s["minutes"] >= HIGH_MINUTES or s["rpe"] * s["minutes"] >= HIGH_RPE_MIN
                     for s in sessions)
    if week_minutes > WEEK_MINUTES_CAP:
        return "excessive", "周时长超上限"
    if consecutive_high_days >= 3:
        return "excessive", "连续高负荷"
    if prev_week_minutes and prev_week_minutes > 0 and week_minutes / prev_week_minutes - 1 > GROWTH_CAP:
        return "excessive", "周负荷增幅超 30%"
    if today_high or week_minutes >= 300:
        return "high", None
    return "normal", None


def escalate(bucket, load):
    """吃少 + 练多 = 危险。这条必须由代码判，不能交给模型。"""
    if load == "excessive" and bucket in ("low", "danger"):
        return "danger", "吃少 + 练多"
    return bucket, None


def protein_gap(target_g, eaten_g):
    return max(0.0, target_g - eaten_g)


def remaining(day_lo, day_hi, lo=PLAN_LO, hi=PLAN_HI):
    """日内用这个，不用分档：还剩多少额度。"""
    return {"left_lo": max(0, lo - day_hi), "left_hi": max(0, hi - day_lo)}


# ============ 免责与医疗停止（字符串写死在代码里，模型无权生成） ============

MEDICAL_SIGNALS = (
    "疼", "痛", "受伤", "扭", "拉伤", "肿", "麻", "骨", "头晕", "发烧", "抻",
)

DISCLAIMER = (
    "本工具只做个人记录与估算，不是医疗建议，也不能替代医生。"
    "所有热量、运动消耗、基础代谢都是估算值。"
    "当你出现疼痛、受伤或身体不适时，本工具会停止给出建议并要求你就医。"
    "如果你在此之后仍然选择继续使用，由此产生的任何后果由你自行承担。"
)

MEDICAL_STOP = (
    "这个超出我能帮的范围了。先去看医生，好了再回来。\n"
    "今天不再给你任何训练或饮食安排。\n"
    + DISCLAIMER
)

CONTINUE_RISK = (
    "明白，我可以继续帮你记录，但训练建议不会恢复。\n"
    "继续使用的风险由你自己承担。"
)


def is_medical(text):
    """出现任何医疗信号词就直接停。宁可不分轻重，也不做判断。"""
    return any(w in text for w in MEDICAL_SIGNALS)


def allow_after_consent(kind):
    """二次确认之后：允许记录，不允许给训练安排。"""
    return kind in ("eat", "weigh", "query")

def combine(estimates):
    """多餐的区间合成：中心相加，但误差按平方和开方，不是线性相加。
    线性相加会让一天的区间越吃越宽，最后什么都判不出来。"""
    if not estimates:
        return {"kcal": 0, "lo": 0, "hi": 0, "protein_g": 0, "carb_g": 0, "fat_g": 0}
    mean = sum(e.get("kcal", 0) for e in estimates)
    var = sum((((e.get("hi") or e.get("kcal", 0)) - (e.get("lo") or e.get("kcal", 0))) / 2.0) ** 2
              for e in estimates)
    half = var ** 0.5
    return {
        "kcal": mean,
        "lo": round(mean - half, 1),
        "hi": round(mean + half, 1),
        "protein_g": sum(e.get("protein_g", 0) for e in estimates),
        "carb_g": sum(e.get("carb_g", 0) for e in estimates),
        "fat_g": sum(e.get("fat_g", 0) for e in estimates),
    }

def streak_adjust(bucket, low_days):
    """单日吃少了不叫危险。连续多日才算。"""
    if bucket == "danger" and low_days < 3:
        return "low", f"今天偏低（连续第 {low_days} 天），明天再看"
    return bucket, None


def protein_suggestion(gap_g, meals_left=2):
    """按「这一顿该补多少」给，不是把全天缺口一次塞给你。"""
    if gap_g <= 0:
        return "蛋白已经够了"
    per = gap_g / max(1, meals_left)
    if per <= 10:
        food = "一杯牛奶"
    elif per <= 20:
        food = "一个鸡蛋 + 一杯牛奶"
    elif per <= 30:
        food = "120g 鸡胸"
    elif per <= 40:
        food = "180g 鸡胸"
    else:
        food = "250g 鸡胸"
    if meals_left <= 1:
        return food
    return f"分 {meals_left} 顿补，每顿约 {per:.0f}g：{food}"

# ---------------- 减载：只是参考，不做拦截 ----------------

def deload_hint(sessions_7d=None, rpe_now=None, rpe_prev=None,
                low_mood_days=None, completion=None):
    """疲劳只是参考。有数据才说话，没数据就不提。
    这个函数永远不改计划，只返回一句提示或 None。"""
    if sessions_7d is None and low_mood_days is None and completion is None:
        return None

    if low_mood_days is not None and low_mood_days >= 3:
        return "连续 3 天情绪低。这周建议减载：量砍一半，强度不变。"
    if (sessions_7d and sessions_7d >= 3
            and rpe_now is not None and rpe_prev is not None
            and rpe_now - rpe_prev >= 1.0):
        return "同样的量，RPE 比上周高一档多。建议这周减载。"
    if completion is not None and completion < 0.5:
        return "打卡不到一半。先别加量，可以考虑把计划缩短。"
    return None

# ---------------- 单餐占比（分布，不是总额） ----------------

def group_meals(items, gap_min=90):
    """把「记录条目」聚成「餐」。同餐=同 slot 且相隔不超过 90 分钟。
    items 每条可带 slot 与 at(HH:MM)；缺 at 的按同餐处理。"""
    def mins(a):
        if not a or ":" not in a:
            return None
        h, m = a.split(":")
        return int(h) * 60 + int(m)

    meals, cur_meal, last_key, last_t = [], None, None, None
    for it in items:
        slot = it.get("slot") or ""
        t = mins(it.get("at"))
        same = (slot == last_key) and (t is None or last_t is None or (t - last_t) <= gap_min)
        if cur_meal is not None and same:
            cur_meal["kcal"] += it["kcal"]
        else:
            cur_meal = {"kcal": it["kcal"], "slot": slot}
            meals.append(cur_meal)
        last_key, last_t = slot, t
    return meals


def meal_stats(items):
    """按「餐」统计，不是按「记录条目」。条目不是一顿饭。"""
    meals = group_meals(items)
    if not meals:
        return {"meals": 0, "total": 0, "max_ratio": 0.0}
    total = sum(m["kcal"] for m in meals)
    if total <= 0:
        return {"meals": len(meals), "total": 0, "max_ratio": 0.0}
    return {"meals": len(meals), "total": total,
            "max_ratio": max(m["kcal"] for m in meals) / total}


HINT_ON = False          # 占比提示默认关闭：判不准"这是几顿"时，硬给评价只是噪音


def distribution_hint(stats, ratio_cap=0.65):
    if not HINT_ON:
        return None
    """只提一句，不禁用任何东西。总额对了就行，分布只是提醒。"""
    if stats["meals"] < 2:      # 只有一顿时占比没意义，别吓人
        return None
    if stats["max_ratio"] >= ratio_cap:
        pct = round(stats["max_ratio"] * 100)
        return (f"有一顿占了当天的 {pct}%。如果是一次吃完的，可以分两顿——"
                f"一次吃这么多，后面容易饿，蛋白一次也吸收不完。")
    return None

# ---------------- 睡眠：不够就别练，这是硬规则 ----------------

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def parse_hours(text):
    """从「睡了五个半小时」「不到6小时」里抠出小时数。抠不出返回 None。"""
    if not text:
        return None
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(?:小时|h|H)", text)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        v = float(m.group(1))
        return v if 0 < v <= 24 else None
    for k, v in _CN.items():
        if k in text and "小时" in text:
            return float(v) + (0.5 if "半" in text else 0.0)
    return None


def sleep_gate(hours, recent=None):
    """睡眠不足时降低或取消训练。宁可少练一天，不要赌。"""
    recent = [h for h in (recent or []) if h is not None]
    if hours is None:
        if len(recent) >= 2 and recent[-1] < 6 and recent[-2] < 6:
            return {"cap": "none", "text": "连续两晚睡不到 6 小时。今天不安排训练，散步就行。"}
        return {"cap": "unknown", "text": None}
    if hours < 5:
        return {"cap": "none", "text": f"睡 {hours:g} 小时。今天不练，只散步。"}
    if hours < 6:
        return {"cap": "light", "text": f"睡 {hours:g} 小时。今天只做轻活动：走路、拉伸。"}
    if hours < 7:
        return {"cap": "reduced", "text": f"睡 {hours:g} 小时。强度打七折，组数少一组。"}
    return {"cap": "normal", "text": None}

# ---------------- 注册：把资料算成计划 ----------------

ACTIVITY = {"久坐": 1.2, "轻度": 1.375, "中等": 1.55, "很活跃": 1.725}


def bmr_mifflin(kg, cm, age, sex):
    base = 10 * kg + 6.25 * cm - 5 * age
    return base + (5 if sex == "m" else -161)


def make_plan(profile, deficit=500):
    """按资料算出热量区间、蛋白目标、建议目标体重。"""
    kg = float(profile["weight_kg"])
    cm = float(profile["height_cm"])
    age = int(profile["age"])
    sex = profile.get("sex", "m")
    bmr = bmr_mifflin(kg, cm, age, sex)
    act = ACTIVITY.get(profile.get("activity", "轻度"), 1.375)
    tdee = bmr * act
    target_kcal = max(DANGER_KCAL * 1.15, tdee - deficit)
    lo = int(round(target_kcal - 100))
    hi = int(round(target_kcal + 100))
    protein = int(round(1.6 * kg))
    suggest = round(22 * (cm / 100) ** 2, 1)
    return {
        "kcal_range": [lo, hi],
        "protein_g": protein,
        "bmr": int(round(bmr)),
        "tdee": int(round(tdee)),
        "suggest_target_kg": suggest,
    }


def profile_complete(profile):
    return all(profile.get(k) for k in ("height_cm", "weight_kg", "age", "sex"))

# ---------------- 钠：不拿来管你，只拿来解释体重 ----------------

SODIUM_HIGH = 4000      # mg。中国推荐 <2000，实际平均 4000 上下


def water_weight_hint(delta_kg, sodium_mg, high=SODIUM_HIGH):
    """体重涨了，且昨天钠偏高 → 告诉你是水，不是脂肪。不改任何判定。"""
    if delta_kg is None or sodium_mg is None:
        return None
    if delta_kg <= 0.3:
        return None
    if sodium_mg < high:
        return None
    return (f"昨天钠大约 {sodium_mg} mg（偏高），体重涨的这 {delta_kg:.1f} kg "
            f"多半是水，三五天会自己回去，别拿它改计划。")


def sodium_level(sodium_mg):
    if sodium_mg is None:
        return "unknown"
    if sodium_mg >= 5000:
        return "high"
    if sodium_mg >= 3000:
        return "medium"
    return "low"

# ---------------- 日压缩：一天压成一行 ----------------

def compress_day(day):
    """把一天的明细压成一行硬事实。原始记录不删，这里只是给模型看的摘要。"""
    items = day.get("items") or []
    return {
        "date": day.get("date"),
        "kcal": round(sum(i.get("kcal", 0) for i in items)),
        "entries": len(items),
        "protein_g": round(sum(i.get("protein_g", 0) for i in items)),
        "sodium_mg": int(day.get("sodium") or 0),
        "sleep_h": day.get("sleep_h"),
        "bucket": day.get("bucket"),
    }


def summarize_line(s):
    parts = [f"{s['date'][5:]} 吃{s['kcal']}卡/{s['entries']}条"]
    if s.get("protein_g"):
        parts.append(f"蛋白{s['protein_g']}g")
    if s.get("sleep_h"):
        parts.append(f"睡{s['sleep_h']:g}h")
    if s.get("bucket"):
        parts.append(s["bucket"])
    return " ".join(parts)

def find_item(items, target):
    """在今天的记录里找一条来改。target 空 = 改最后一条；找不到返回 None。"""
    if not items:
        return None
    t = (target or "").strip()
    if not t:
        return len(items) - 1
    import re
    m = re.match(r"^第?\s*(\d+)\s*条?$", t)
    if m:
        i = int(m.group(1)) - 1
        return i if 0 <= i < len(items) else None
    for i in range(len(items) - 1, -1, -1):
        if t in (items[i].get("desc") or ""):
            return i
    return None

def weight_sane(kg, ref_kg):
    """离谱的体重直接挡掉。15 公斤不可能是成年人，涨跌 40% 以内才收。"""
    if kg is None:
        return False, "没读到数字"
    if kg < 30 or kg > 300:
        return False, f"{kg:g} kg 不像人体重，是不是打错了"
    if ref_kg and abs(kg - ref_kg) > 0.25 * ref_kg:
        return False, f"和上次 {ref_kg:g} kg 差了 {abs(kg - ref_kg):.1f} kg，一次称重不该差这么多，确认一下"
    return True, None

def day_key(dt, start_hour=4):
    """「一天」的边界不放在午夜，放在凌晨 4 点。
    凌晨 3 点吃的那顿算昨天，不会被当成新一天的第一顿饭。"""
    import datetime as _dt
    if dt.hour < start_hour:
        dt = dt - _dt.timedelta(days=1)
    return dt.date().isoformat()

# ---------------- 训练负荷：真正接上 escalate 的那条链 ----------------

MINUTES_CAP = 300          # 单次训练上限，超过就不像真的了


def minutes_sane(v):
    if v is None:
        return True, None
    if v <= 0:
        return False, "时长是 0"
    if v > MINUTES_CAP:
        return False, f"{v} 分钟太长了，超过 {MINUTES_CAP} 分钟不像单次训练"
    return True, None


def parse_minutes(text):
    """从「跑了30分钟」「练了一个半小时」「1.5小时」里抠出分钟数。"""
    import re
    t = text or ""
    if "半小时" in t:
        m = re.search(r"(\d+)\s*个半小时", t)
        if m:
            return int(m.group(1)) * 60 + 30
        for cn, v in (("两", 2), ("二", 2), ("三", 3), ("一", 1)):
            if cn + "个半小时" in t:
                return v * 60 + 30
        return 30
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", t)
    if m:
        return int(round(float(m.group(1)) * 60))
    m = re.search(r"(\d+)\s*分钟", t)
    if m:
        return int(m.group(1))
    return None


def load_snapshot(days, today, lookback=7):
    """days: {iso日期: {'minutes':int,'rpe':int}}，today 可以是 date 或 iso 字符串。
    返回 (今天的训练列表, 近 7 天总分钟, 连续高负荷天数)。"""
    import datetime as _dt
    tday = _dt.date.fromisoformat(today) if isinstance(today, str) else today

    d0 = days.get(tday.isoformat())
    sessions = [{"minutes": d0.get("minutes", 0), "rpe": d0.get("rpe", 6)}] if d0 else []

    total = 0
    for i in range(lookback):
        v = days.get((tday - _dt.timedelta(days=i)).isoformat())
        if v:
            total += int(v.get("minutes", 0))

    streak = 0
    for i in range(lookback):
        v = days.get((tday - _dt.timedelta(days=i)).isoformat())
        if not v:
            break
        mins = int(v.get("minutes", 0))
        rpe = int(v.get("rpe", 6))
        if mins >= HIGH_MINUTES or rpe * mins >= HIGH_RPE_MIN:
            streak += 1
        else:
            break
    return sessions, total, streak


def month_day(text, today):
    """把「昨天」「10月18日」「2026-10-18」变成 iso 日期，认不出返回 None。"""
    import re
    import datetime as _dt
    t = (text or "").strip()
    if "前天" in t:
        return (today - _dt.timedelta(days=2)).isoformat()
    if "昨天" in t or "昨日" in t:
        return (today - _dt.timedelta(days=1)).isoformat()
    if "今天" in t or "今日" in t:
        return today.isoformat()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", t)
    if m:
        return f"{today.year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None