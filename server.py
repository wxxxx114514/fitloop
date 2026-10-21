# -*- coding: utf-8 -*-
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.pylibs')
if os.path.isdir(_LIBS):
    sys.path.insert(0, _LIBS)   # 本地离线包目录，没有就跳过（别人克隆下来走 pip）

import app as engine
import graph_app as G
import core, plan_rules
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

api = FastAPI()
HTML = os.path.join(HERE, "static", "index.html")


def snapshot():
    st = engine.load()
    p = st["profile"]
    d = core.combine(st["day"]["items"])
    cur = st["weights"][-1][1] if st["weights"] else p["start_kg"]
    prog = plan_rules.progress(p["start_kg"], p["target_kg"], cur)
    import datetime
    sd = datetime.date.fromisoformat(st["start_date"])
    week = (datetime.date.today() - sd).days // 7 + 1
    lo, hi = st["plan"]["kcal_range"]
    gap = core.protein_gap(st["plan"]["protein_g"], d["protein_g"])
    return {
        "week": week,
        "start_kg": p["start_kg"], "target_kg": p["target_kg"], "current_kg": round(cur, 1),
        "remain_kg": round(cur - p["target_kg"], 1),
        "progress": None if prog is None else max(0.0, min(1.0, prog)),
        "eaten": round(d["kcal"]), "kcal_lo": lo, "kcal_hi": hi,
        "remaining_lo": round(max(0, lo - d["hi"])), "remaining_hi": round(max(0, hi - d["lo"])),
        "protein": round(d["protein_g"]), "protein_target": st["plan"]["protein_g"],
        "protein_gap": round(gap),
        "weigh_interval": plan_rules.weigh_interval_days(week),
        "weighs": len(st["weights"]),
        "profile_complete": core.profile_complete(p),
        "unit": p.get("unit", "公斤"),
        "messages": st.get("messages", [])[-60:],
        "bmr": st["plan"].get("bmr"),
        "tdee": st["plan"].get("tdee"),
    }


class ChatIn(BaseModel):
    text: str


class ProfileIn(BaseModel):
    height_cm: float
    weight_kg: float
    age: int
    sex: str = "m"
    activity: str = "轻度"
    days_per_week: str = "3-4"
    workout_way: str = ""
    unit: str = "公斤"
    target_kg: float | None = None


@api.post("/api/profile")
def profile(body: ProfileIn):
    st = engine.load()
    p = st["profile"]
    p.update({"height_cm": body.height_cm, "weight_kg": body.weight_kg,
              "age": body.age, "sex": body.sex, "activity": body.activity,
              "days_per_week": body.days_per_week, "workout_way": body.workout_way,
              "unit": body.unit})
    plan = core.make_plan(p)
    st["plan"]["kcal_range"] = plan["kcal_range"]
    st["plan"]["protein_g"] = plan["protein_g"]
    st["plan"]["bmr"] = plan["bmr"]
    st["plan"]["tdee"] = plan["tdee"]
    p["start_kg"] = body.weight_kg
    p["target_kg"] = body.target_kg or plan["suggest_target_kg"]
    engine.save(st)
    return {"ok": True, "state": snapshot()}


@api.get("/", response_class=HTMLResponse)
def index():
    with open(HTML, encoding="utf-8") as f:
        html = f.read()
    # 注册浮层由服务端决定是否显示：已注册的人刷新时不会再闪一下
    st = engine.load()
    cls = "" if core.profile_complete(st["profile"]) else " on"
    return HTMLResponse(html.replace("__GATE__", cls))


@api.get("/api/debug/advance")
def debug_advance(days: int = 1):
    """测试用：假装过了 days 天，下次打开就会触发跨天（压缩 + 清空对话）。"""
    engine.set_day_offset(engine.day_offset() + days)
    return {"offset": engine.day_offset(), "today": engine.now_day(), "state": snapshot()}


@api.get("/api/debug/reset_clock")
def debug_reset_clock():
    engine.set_day_offset(0)
    return {"offset": 0, "today": engine.now_day(), "state": snapshot()}


@api.get("/api/state")
def state():
    return snapshot()


@api.post("/api/chat")
def chat(body: ChatIn):
    G.start()
    r = G.send(body.text)
    reply = r.get("reply") or ""
    for it in (r.get("__interrupt__") or []):
        iv = it.value or {}
        if iv.get("ask"):
            reply = iv["ask"]          # 追问：把问题交给前端
    if not reply:
        reply = "记下了。"
    return {"reply": reply, "state": snapshot()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("FITLOOP_PORT", "8791"))
    uvicorn.run(api, host="127.0.0.1", port=port, log_level="warning")