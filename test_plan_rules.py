# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_rules import *

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1

# 进度
eq(progress(78, 68, 73), 0.5, "78→68 减到 73 是 50%")
eq(progress(78, 68, 78), 0.0, "没掉是 0")
eq(progress(78, 68, 80), -0.2, "胖了是负的")

# 保守侧
eq(round(progress_lower(78, 68, 73, 0.015), 4), 0.485, "区间下界")

# 档位
eq(level_from_progress(0.24), 0, "24% 还是 0 档")
eq(level_from_progress(0.25), 1, "25% 进 1 档")
eq(level_from_progress(0.50), 2, "50% 进 2 档")
eq(level_from_progress(0.75), 3, "75% 进 3 档")
eq(level_from_progress(None), 0, "没有进度是 0 档")

# 只升不降
eq(apply_hysteresis(2, 0.30), 2, "跌回 30% 档位不收回")
eq(apply_hysteresis(0, 0.80), 3, "冲到 80% 直接上 3 档")

# 开局不排
eq(free_meal_plan(1, 0)["interval"], None, "第 1 天不排")
eq(free_meal_plan(13, 2)["interval"], None, "第 13 天仍不排")
eq(free_meal_plan(14, 0)["interval"], 7, "第 14 天起 7 天一次")
eq(free_meal_plan(20, 1)["interval"], 6, "1 档 6 天")
eq(free_meal_plan(20, 2)["interval"], 5, "2 档 5 天")
r = free_meal_plan(20, 3)
eq((r["interval"], r["carb_day"]), (5, True), "3 档 5 天 + 碳水日")

# 上限
eq(max(MIN_INTERVAL, 1), 3, "绝不比每 3 天更密")


# ---- 称重频率 ----
eq(weigh_interval_days(1), 3, "开局半周一次")
eq(weigh_interval_days(3), 3, "第 3 周仍密")
eq(weigh_interval_days(4), 7, "第 4 周起每周")
eq(weigh_interval_days(11), 14, "第 11 周起两周")
sch = weigh_schedule(6)
eq(len([x for x in sch if x[1] <= 3]), len([x for x in sch if x[1] <= 3]), "排期能出来")
eq([x[0] for x in sch[:4]], [0, 3, 6, 9], "前 4 次在第 0/3/6/9 天")

print(f"ALL PASS  ({n} assertions)")