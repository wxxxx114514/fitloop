# -*- coding: utf-8 -*-
"""记忆的四件事：计算 / 修改 / 报警 / 隔天刷新。
用假解析，不调模型，纯验状态流转。"""
import sys, os, json, datetime
sys.path.insert(0, r"D:\project\fitloop")
sys.stdout.reconfigure(encoding="utf-8")
import app as engine
import core

HERE = r"D:\project\fitloop"
engine.DB = os.path.join(HERE, "_mem.db")
if os.path.exists(engine.DB):
    os.remove(engine.DB)

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1
def ok(cond, msg):
    global n
    assert cond, msg
    n += 1

# 假 estimate：固定给区间
def fake_estimate(desc):
    return {"kcal": 750, "lo": 550, "hi": 1000, "protein_g": 35, "carb_g": 80, "fat_g": 25, "sodium_mg": 1200}
engine.estimate = fake_estimate

st = engine.load()
st["profile"].update({"height_cm": 180, "weight_kg": 98, "age": 21, "sex": "m",
                      "start_kg": 98.0, "target_kg": 88.0})
st["plan"] = {"kcal_range": [2157, 2357], "protein_g": 157}

print("=== 一、计算 ===")
engine.do_eat(st, {"kind": "eat", "slot": "早", "desc": "两个包子"})
eq(len(st["day"]["items"]), 1, "第一顿入库")
d1 = core.combine(st["day"]["items"])
# combine 用 (hi-lo)/2 当半宽，所以单条也会规整成 750±225
eq((d1["lo"], d1["hi"]), (525.0, 975.0), "一顿的区间")

engine.do_eat(st, {"kind": "eat", "slot": "午", "desc": "食堂两荤一素"})
eq(len(st["day"]["items"]), 2, "第二顿入库")
d2 = core.combine(st["day"]["items"])
# 两餐各半宽 225，平方和开方 → 总半宽 ≈ 318，宽度 ≈ 636
eq(d2["kcal"], 1500, "两顿合计 1500")
ok(abs((d2["hi"] - d2["lo"]) - 636) <= 2, f"两段合成宽度用平方和（{d2['hi']-d2['lo']}）")
ok(d2["hi"] - d2["lo"] < 2 * (1000 - 750) * 2, "比线性相加窄")

print("=== 二、修改 ===")
out = engine.do_eat(st, {"kind": "eat", "slot": "早", "desc": "只吃了一个包子", "op": "amend", "target": "包子"})
eq(len(st["day"]["items"]), 2, "改不是加：条数不变")
ok("改掉了" in out, "回复里说明是改")
eq(st["day"]["items"][0]["desc"], "只吃了一个包子", "原地替换，顺序不变")
eq(st["day"]["items"][0]["slot"], "早", "槽位跟着保留")
# 两条记录各 1200mg，改一条后仍应是 2400（不是 3600，说明没重复累加）
eq(st["day"]["sodium"], 2400, "钠按条目重算，不重复累加")
eq(core.combine(st["day"]["items"])["kcal"], 1500, "改完总量重算")

out = engine.do_eat(st, {"kind": "eat", "op": "amend", "target": "西瓜"})
ok("没找到" in out, "改不存在的条目要说清楚")
eq(len(st["day"]["items"]), 2, "找不到时不动数据")

print("=== 三、报警 ===")
ok("医疗" in core.MEDICAL_STOP or "就医" in core.MEDICAL_STOP, "医疗有固定话术")
# 关键词表是「疼痛/受伤」类，不是药品类——这是设计边界，不是漏
ok(core.is_medical("膝盖疼还能深蹲吗"), "疼痛词命中医疗拦截")
ok(core.is_medical("昨天扭到脚了"), "受伤词命中")
ok(not core.is_medical("今天吃了鸡胸"), "正常话不误报")
ok(not core.is_medical("我吃了头孢"), "药品不在这张表里（已知边界）")

bad = engine.do_weigh(st, 5)
ok("没收" in bad, "离谱体重拒收")
eq(len(st["weights"]), 0, "拒收不写库")

bad2 = engine.do_train(st, {"desc": "练了 10 小时"}, "")
ok("没收" in bad2, "离谱时长拒收")

r = core.classify_point(900, 2157, 2357, 1200)
eq(r, "danger", "低于危险线判 danger")

print("=== 四、隔天刷新 ===")
day_before = st["day"]["date"]
engine.append_msg(st, "user", "今天吃了包子")
engine.append_msg(st, "assistant", "记下了")
ok(len(st["messages"]) >= 2, "有对话")
st["day"]["sleep_h"] = 7.5
engine.save(st)

# 模拟跨天：把 day.date 改成昨天
st2 = engine.load()
st2["day"]["date"] = (datetime.date.fromisoformat(engine.now_day()) - datetime.timedelta(days=1)).isoformat()
st2["day"]["items"] = [{"desc": "黄焖鸡", "kcal": 750, "lo": 600, "hi": 900, "protein_g": 40}]
engine.save(st2)

st3 = engine.load()                       # 触发跨天
eq(st3["day"]["items"], [], "新的一天从空开始")
eq(st3["messages"], [], "对话记忆清空")
ok(st2["day"]["date"] in st3["archive"], "昨天的明细进归档")
eq(st3["archive"][st2["day"]["date"]]["sleep_h"], 7.5, "归档里留了睡眠")
ok(len(st3["summaries"]) >= 1, "生成了摘要")

rec = engine.do_recall(st3, "昨天")
ok("黄焖鸡" in rec, "隔天还能查回昨天")

os.remove(engine.DB)
print(f"\nALL PASS  ({n} assertions)")