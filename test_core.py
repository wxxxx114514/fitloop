# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import *

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1

# ---- 分档边界 ----
eq(classify_point(1199), "danger", "低于危险线")
eq(classify_point(1200), "low", "正好到危险线")
eq(classify_point(1649), "low", "低档上界")
eq(classify_point(1650), "normal", "正常下界")
eq(classify_point(1850), "normal", "正常上界")
eq(classify_point(1851), "slight", "稍微超标起点")
eq(classify_point(2072), "slight", "1.12 倍线上")
eq(classify_point(2072.1), "over", "1.12 倍线外")

# ---- 区间判档 ----
eq(classify_day(1800, 1800)["bucket"], "normal", "单点正常")
eq(classify_day(1800, 1800)["ambiguous"], False, "单点不模糊")
d = classify_day(1600, 1700)
eq((d["bucket"], d["ambiguous"], d["why"]), ("normal", True, "区间跨档，取中点"), "跨低/正常取中点")
d = classify_day(500, 1400)
eq((d["bucket"], d["why"]), ("danger", "区间下界低于危险线"), "火锅跨到危险线以下")

# ---- 负荷 ----
eq(load_level([], 240, 1), ("normal", None), "低量")
eq(load_level([{"minutes": 90, "rpe": 7}], 300, 1), ("high", None), "今日 90 分钟")
eq(load_level([{"minutes": 60, "rpe": 10}], 200, 1), ("high", None), "rpe*min=600")
eq(load_level([], 430, 1), ("excessive", "周时长超上限"), "周时长超")
eq(load_level([], 400, 3), ("excessive", "连续高负荷"), "连续三天")
eq(load_level([], 400, 1, prev_week_minutes=300), ("excessive", "周负荷增幅超 30%"), "增幅超")

# ---- 组合升级 ----
eq(escalate("low", "excessive"), ("danger", "吃少 + 练多"), "低+过量→危险")
eq(escalate("low", "high"), ("low", None), "低+高负荷不升级")
eq(escalate("over", "excessive"), ("over", None), "超标+过量不升级")

# ---- 缺口 / 剩余 ----
eq(protein_gap(120, 78), 42, "蛋白缺口")
eq(protein_gap(120, 130), 0, "超了不返回负数")
eq(remaining(900, 1000), {"left_lo": 650, "left_hi": 950}, "剩余额度")
eq(remaining(3000, 3000), {"left_lo": 0, "left_hi": 0}, "吃超了剩余为 0")

# ---- 医疗停止 ----
eq(is_medical("膝盖有点疼"), True, "疼字触发")
eq(is_medical("昨天扭了一下"), True, "扭触发")
eq(is_medical("有点发烧"), True, "发烧触发")
eq(is_medical("今天跑了5公里"), False, "正常记录不触发")
eq(is_medical("练完腿有点酸"), False, "酸不算医疗信号")
eq(allow_after_consent("eat"), True, "确认后允许记录")
eq(allow_after_consent("train"), False, "确认后不给训练")
assert "后果由你自行承担" in DISCLAIMER
assert "不是医疗建议" in MEDICAL_STOP

# ---- 区间合成 ----
c = combine([{"kcal": 750, "lo": 550, "hi": 1000}, {"kcal": 420, "lo": 320, "hi": 560}])
eq((c["kcal"], c["lo"], c["hi"]), (1170, 915.0, 1425.0), "两餐合成用平方和开方")
eq(round(c["hi"] - c["lo"], 1), 510.0, "合成后区间宽 510，不是线性相加的 690")
eq(combine([])["kcal"], 0, "空列表")
eq(combine([{"kcal": 500, "lo": 500, "hi": 500}])["lo"], 500, "无误差时区间为零")

# ---- 连续天数与蛋白建议 ----
eq(streak_adjust("danger", 1), ("low", "今天偏低（连续第 1 天），明天再看"), "单日偏低不判危险")
eq(streak_adjust("danger", 3), ("danger", None), "连续三天才是危险")
eq(streak_adjust("low", 5), ("low", None), "low 不受影响")
assert "鸡胸" in protein_suggestion(42)
eq(protein_suggestion(0), "蛋白已经够了", "够了就说够了")

# ---- 减载只是参考 ----
eq(deload_hint(), None, "完全没数据→不提")
eq(deload_hint(sessions_7d=1), None, "只练了 1 次→不判")
eq(deload_hint(sessions_7d=2, low_mood_days=1), None, "数据不足→不判")
assert "减载" in deload_hint(low_mood_days=3)
assert "RPE" in deload_hint(sessions_7d=4, rpe_now=8.5, rpe_prev=7.0)
eq(deload_hint(sessions_7d=4, rpe_now=7.3, rpe_prev=7.0), None, "RPE 没明显升→不提")
assert "加量" in deload_hint(completion=0.4)
eq(deload_hint(completion=0.9), None, "打卡正常→不提")

# ---- 按「餐」统计（条目不是一顿饭）----
eq(meal_stats([]), {"meals": 0, "total": 0, "max_ratio": 0.0}, "没吃")
eq(meal_stats([{"kcal": 1200}, {"kcal": 300}])["meals"], 1, "没有时段信息时当一顿")
s = meal_stats([{"kcal": 1200, "slot": "午", "at": "12:10"},
                {"kcal": 300, "slot": "晚", "at": "18:40"}])
eq((s["meals"], s["total"], round(s["max_ratio"], 3)), (2, 1500, 0.8), "两顿，午占八成")
eq(distribution_hint(s), None, "占比提示已关闭（判不准几顿就不给评价）")
eq(meal_stats([{"kcal": 600, "slot": "午", "at": "11:00"},
               {"kcal": 600, "slot": "午", "at": "14:30"}])["meals"], 2, "同时段隔三小时算两顿")
eq(meal_stats([{"kcal": 600, "slot": "午", "at": "12:00"},
               {"kcal": 600, "slot": "午", "at": "12:10"}])["meals"], 1, "十分钟内算一顿")
eq(distribution_hint(meal_stats([{"kcal": 750}])), None, "只有一顿时不提占比")

# ---- 睡眠 ----
eq(parse_hours("睡了5小时"), 5.0, "阿拉伯数字")
eq(parse_hours("5.5小时"), 5.5, "小数")
eq(parse_hours("睡了五小时"), 5.0, "中文数字")
eq(parse_hours("睡了五个半小时"), 5.5, "中文+半")
eq(parse_hours("没睡好"), None, "抠不出")

eq(sleep_gate(4.5)["cap"], "none", "低于5小时不练")
eq(sleep_gate(5.5)["cap"], "light", "5-6小时只轻活动")
eq(sleep_gate(6.5)["cap"], "reduced", "6-7小时强度打折")
eq(sleep_gate(7.5)["cap"], "normal", "够7小时正常")
eq(sleep_gate(None)["cap"], "unknown", "没数据不判")
eq(sleep_gate(None, [5.0, 5.5])["cap"], "none", "连续两晚不足→不练")
eq(sleep_gate(None, [5.0, 7.0])["cap"], "unknown", "只一晚不足→不判")

# ---- 注册算计划 ----
eq(round(bmr_mifflin(78, 175, 20, "m")), 1779, "男人 BMR")
eq(round(bmr_mifflin(78, 175, 20, "f")), 1613, "女人 BMR")
p = make_plan({"weight_kg": 78, "height_cm": 175, "age": 20, "sex": "m", "activity": "中等"})
eq(p["protein_g"], 125, "蛋白 1.6g/kg")
assert abs(p["bmr"] - 1779) <= 1
eq(p["kcal_range"][1] - p["kcal_range"][0], 200, "区间宽 200")
eq(p["suggest_target_kg"], 67.4, "BMI22 的建议体重")
eq(profile_complete({"height_cm": 175}), False, "资料不全")
eq(profile_complete({"height_cm": 175, "weight_kg": 78, "age": 20, "sex": "m"}), True, "资料齐全")

# ---- 钠只解释体重 ----
assert water_weight_hint(0.8, 5200) is not None
eq(water_weight_hint(0.8, 2000), None, "钠不高就不解释")
eq(water_weight_hint(0.1, 5200), None, "只涨一点点不解释")
eq(water_weight_hint(-0.6, 5200), None, "掉了不解释")
eq(water_weight_hint(0.8, None), None, "没数据不解释")
eq(sodium_level(5200), "high", "高钠")
eq(sodium_level(3200), "medium", "中钠")
eq(sodium_level(1500), "low", "低钠")

# ---- 日压缩 ----
d = compress_day({"date": "2026-10-20", "items": [{"kcal": 800, "protein_g": 40}, {"kcal": 600, "protein_g": 30}],
                  "sodium": 4200, "sleep_h": 6.5})
eq((d["kcal"], d["entries"], d["protein_g"], d["sodium_mg"], d["sleep_h"]), (1400, 2, 70, 4200, 6.5), "压成一行")
assert "10-20" in summarize_line(d) and "1400" in summarize_line(d)
eq(compress_day({})["kcal"], 0, "空的一天")

# ---- 找今天哪一条来改 ----
items = [{"desc": "玉米饼三个加黄焖鸡"}, {"desc": "卤蛋"}, {"desc": "西瓜150g"}]
eq(find_item(items, "玉米饼"), 0, "按名字找到第一条")
eq(find_item(items, "卤蛋"), 1, "找到第二条")
eq(find_item(items, ""), 2, "不指定就改最后一条")
eq(find_item(items, "牛肉面"), None, "找不到")
eq(find_item([], "卤蛋"), None, "今天没有记录")

# ---- 体重离谱就挡 ----
eq(weight_sane(15, 98)[0], False, "15 公斤不收")
eq(weight_sane(98.2, 98)[0], True, "正常体重收")
eq(weight_sane(60, 98)[0], False, "一次掉 38 公斤不收")
eq(weight_sane(None, 98)[0], False, "没数字不收")

# ---- 用序号指定要改哪条 ----
eq(find_item(items, "第2条"), 1, "第2条")
eq(find_item(items, "2"), 1, "纯数字")
eq(find_item(items, "第9条"), None, "序号越界")

print(f"ALL PASS  ({n} assertions)")