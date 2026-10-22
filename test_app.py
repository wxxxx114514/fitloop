# -*- coding: utf-8 -*-
"""do_train / do_recall / 归档 的测试。用临时库，不碰 data.db。"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import openai  # noqa: F401
except ModuleNotFoundError:
    _LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.pylibs')
    if os.path.isdir(_LIBS):
        sys.path.insert(0, _LIBS)
import app as engine
import core

engine.DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_app.db")
if os.path.exists(engine.DB):
    os.remove(engine.DB)

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1

st = engine.load()
st["profile"].update({"height_cm": 180, "weight_kg": 98, "age": 21, "sex": "m", "start_kg": 98.0, "target_kg": 88.0})
st["plan"] = {"kcal_range": [2157, 2357], "protein_g": 157}

# --- 训练落库与负荷 ---
out = engine.do_train(st, {"desc": "练了一个半小时", "rpe": 8}, "")
today = engine.now_day()
eq(st["training"][today]["minutes"], 90, "训练分钟数进了 state")
eq(st["training"][today]["rpe"], 8, "rpe 进了 state")
assert "本周共 90 分钟" in out

# --- 时长离谱要挡 ---
out2 = engine.do_train(st, {"desc": "练了 10 小时"}, "")
assert "没收" in out2
eq(st["training"][today]["minutes"], 90, "离谱时长没有写进去")

# --- 归档 + 回查 ---
# 必须用 now_day()（按凌晨 4 点切天），不能用 date.today()——
# 否则在 00:00-04:00 之间跑，两者算出的「昨天」不是同一天
yday = (datetime.date.fromisoformat(engine.now_day()) - datetime.timedelta(days=1)).isoformat()
st["day"] = {"date": yday, "items": [{"desc": "黄焖鸡米饭", "kcal": 750, "lo": 600, "hi": 900, "protein_g": 40}],
             "sleep_h": 6.5, "sodium": 0, "kcal": 0, "lo": 0, "hi": 0, "protein": 0}
engine.save(st)
st2 = engine.load()                       # 触发跨天
eq(len(st2["day"]["items"]), 0, "新一天从空开始")
assert yday in st2["archive"]
eq(st2["archive"][yday]["sleep_h"], 6.5, "归档里留了睡眠")

rec = engine.do_recall(st2, "昨天")
assert "黄焖鸡米饭" in rec, rec
assert "6.5" in rec

# --- 太久远的只剩合计 ---
st2.setdefault("summaries", []).append({"date": "2026-01-01", "kcal": 1800, "entries": 3,
                                        "protein_g": 100, "sodium_mg": 3000, "sleep_h": 7, "bucket": "normal"})
far = engine.do_recall(st2, "2026-01-01")
assert "只有合计" in far, far

os.remove(engine.DB)
print(f"ALL PASS  ({n} assertions)")
