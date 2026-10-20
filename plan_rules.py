# -*- coding: utf-8 -*-
"""自由餐（饮食休息日）规则。纯代码，可断言。"""

NO_FREE_DAYS = 14        # 开局建基线，一次都不排
MIN_INTERVAL = 3         # 最密也只能每 3 天一次
PROGRESS_ERR = 0.015     # 进度误差，判断时取保守侧


def progress(start_kg, target_kg, current_kg):
    """进度 0~1 之外也可能为负（胖了）或 >1（超额）。"""
    if start_kg == target_kg:
        return None
    return (start_kg - current_kg) / (start_kg - target_kg)


def progress_lower(start_kg, target_kg, current_kg, err=PROGRESS_ERR):
    """保守侧：区间下界。宁可晚解锁，不要早解锁。"""
    p = progress(start_kg, target_kg, current_kg)
    return None if p is None else p - err


LEVELS = [(0.75, 3), (0.50, 2), (0.25, 1)]   # (进度下界, 档位)


def level_from_progress(p_lower):
    if p_lower is None:
        return 0
    for need, lv in LEVELS:
        if p_lower >= need:
            return lv
    return 0


def apply_hysteresis(prev_level, p_lower):
    """只升不降：已经拿到的档位不收回。"""
    return max(prev_level, level_from_progress(p_lower))


INTERVAL = {0: 7, 1: 6, 2: 5, 3: 5}


def free_meal_plan(day_index, level, carb_day=None):
    """day_index 从 1 开始算。"""
    if day_index < NO_FREE_DAYS:
        return {"interval": None, "carb_day": False,
                "why": f"开局前 {NO_FREE_DAYS} 天建基线，不排自由餐"}
    lv = max(0, min(3, level))
    interval = max(MIN_INTERVAL, INTERVAL[lv])
    use_carb = (lv == 3) if carb_day is None else carb_day
    return {"interval": interval, "carb_day": use_carb, "why": f"进度档位 {lv}"}
# ---------------- 称重频率（开局密，之后稀） ----------------

def weigh_interval_days(week_index):
    """week_index 从 1 开始。开局密一点，看清掉的是水还是脂肪。"""
    if week_index <= 3:
        return 3
    if week_index <= 10:
        return 7
    return 14


def weigh_schedule(total_weeks):
    """返回 [(第几天, 第几周, 间隔天数)]，开局 3 天一次，之后 7 天，再之后 14 天。"""
    out = []
    d = 0
    while d < total_weeks * 7:
        w = d // 7 + 1
        iv = weigh_interval_days(w)
        out.append((d, w, iv))
        d += iv
    return out
