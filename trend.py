# -*- coding: utf-8 -*-
"""趋势三态：只看方向，不看快慢。纯计算，可断言。"""

NOISE = 0.10     # kg/周。低于这个幅度当噪声，不算趋势
MIN_POINTS = 3   # 少于 3 个点不判断


def fit_slope(points):
    """points = [(第几天, 体重kg)]，返回 kg/周。点少于 3 个返回 None。"""
    if not points or len(points) < MIN_POINTS:
        return None
    xs = [p[0] / 7.0 for p in points]
    ys = [float(p[1]) for p in points]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return num / den


def trend_state(slope, noise=NOISE):
    if slope is None:
        return "unknown"
    if slope < -noise:
        return "down"
    if slope > noise:
        return "up"
    return "flat"


def judge(points, noise=NOISE):
    """给一段称重记录，返回方向 + 一句话。"""
    s = fit_slope(points)
    st = trend_state(s, noise)
    text = {
        "down": "在降，方向对，继续。",
        "flat": "基本没动。连续 3 周这样再谈改计划。",
        "up": "在涨。先排除放纵餐、通宵、吃咸、大强度训练。",
        "unknown": "数据还不够（至少 3 次称重），先不下判断。",
    }[st]
    return {"state": st, "kg_per_week": None if s is None else round(s, 2), "text": text}
