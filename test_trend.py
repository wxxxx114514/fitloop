# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trend import fit_slope, trend_state, judge, MIN_POINTS

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1

# 稳定下降：每周 -0.5kg，共 4 周
pts = [(0, 78.0), (7, 77.5), (14, 77.0), (21, 76.5)]
eq(round(fit_slope(pts), 3), -0.5, "每周掉 0.5")
eq(trend_state(fit_slope(pts)), "down", "下降")

# 上涨
pts_up = [(0, 78.0), (7, 78.3), (14, 78.6)]
eq(trend_state(fit_slope(pts_up)), "up", "上涨")

# 平稳但有噪声（±0.15 抖动）
pts_flat = [(0, 78.0), (7, 78.1), (14, 77.9), (21, 78.05)]
eq(trend_state(fit_slope(pts_flat)), "flat", "噪声内算持平")

# 点数不够
eq(fit_slope([(0, 78.0), (7, 77.0)]), None, "两点不判断")
eq(trend_state(None), "unknown", "unknown")
eq(judge([(0, 78.0)])["state"], "unknown", "一点不判断")

# 轻微下降但在噪声内（-0.05/周）→ 算持平，不算"在降"
pts_slow = [(0, 78.0), (7, 77.95), (14, 77.9)]
eq(trend_state(fit_slope(pts_slow)), "flat", "降得太慢算持平")

# 说的话
eq(judge(pts)["text"], "在降，方向对，继续。", "下降时的说法")
eq(judge(pts)["kg_per_week"], -0.5, "数值回显")

# 全部同一体重（den=0 的极端情况：不能用"同一天"两点，改用正常数据）
pts_same_day = [(0, 78.0), (0, 78.0), (0, 78.0)]
eq(fit_slope(pts_same_day), None, "同一天多个点无法拟合")

print(f"ALL PASS  ({n} assertions)")
