# -*- coding: utf-8 -*-
"""把已有的步骤套进 LangGraph：两个暂停点（等消息 / 追问），进度存在 checkpoint 里。
领域数据仍在 data.db，图的 checkpointer 只管「停在哪、问到第几轮」。"""
import sys, os, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r'D:\project\.pylibs')

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

import app as engine
import core, resolve

CKPT = os.path.join(HERE, "graph.db")


class S(TypedDict, total=False):
    incoming: str
    extra: str
    events: list
    asks: int
    reply: str


ASK_EPISODE = "还在理你上一条，先回答我这句："


def node_wait(state: S):
    text = interrupt({"why": "等你说话"})
    return {"incoming": str(text), "extra": "", "events": [], "reply": ""}


def node_parse(state: S):
    text = state.get("incoming", "")
    if state.get("extra"):
        text = text + "\n（补充：" + state["extra"] + "）"

    if core.is_medical(state.get("incoming", "")):
        return Command(goto="handoff")

    p = engine.parse(text, engine.load())
    ev = p.get("events", [])
    asks = state.get("asks", 0)
    need = p.get("needs_clarify") and any(e.get("kind") != "query" for e in ev) and asks < 2
    if need:
        return Command(goto="clarify", update={"events": ev, "asks": asks + 1})
    return Command(goto="handle", update={"events": ev})


def node_clarify(state: S):
    ans = interrupt({"ask": "这条我拿不准，补一句份量或数量？"})
    return {"extra": str(ans)}


def node_handle(state: S):
    st = engine.load()
    out = []
    for ev in state.get("events", []):
        kind = ev.get("kind")
        if kind == "eat":
            out.append(engine.do_eat(st, ev))
        elif kind == "weigh":
            import re
            kg = None
            for cand in (ev.get("desc"), state.get("incoming"), state.get("extra")):
                m = re.search(r"(\d+(?:\.\d+)?)", cand or "")
                if m:
                    kg = float(m.group(1))
                    break
            out.append(engine.do_weigh(st, kg) if kg else "没看到数字，再报一次体重？")
        elif kind == "train":
            gate = core.sleep_gate(st["day"].get("sleep_h"), st.get("sleep"))
            if gate["cap"] in ("none", "light"):
                out.append("今天不适合练。" + gate["text"])
            else:
                out.append("练的记下了（负荷计算还没接）。")
        elif kind == "goal":
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", state.get("incoming", ""))
            if not m:
                out.append("没听到数字。比如「目标改成 75」。")
            else:
                kg = float(m.group(1))
                st["profile"]["target_kg"] = kg
                cur = st["weights"][-1][1] if st["weights"] else st["profile"]["start_kg"]
                left = round(cur - kg, 1)
                out.append(f"目标改成 {kg:g} kg。现在 {cur:g}，还差 {left} kg。")
        elif kind == "sleep":
            h = core.parse_hours(ev.get("desc") or state.get("incoming", ""))
            if h is None:
                out.append("没听到几个小时的数字，比如「昨晚睡了五个半小时」？")
            else:
                st["day"]["sleep_h"] = h
                st.setdefault("sleep", []).append(h)
                gate = core.sleep_gate(h, st["sleep"])
                out.append(gate["text"] or ("记下 " + f"{h:g}" + " 小时，睡眠够，训练照常。"))
        elif kind == "query":
            said = (ev.get("desc") or "") + (state.get("incoming") or "")
            if any(k in said for k in ("吃了多少", "还剩", "额度", "摄入", "还能吃", "今天吃了")):
                out.append(engine.today_summary(st))
                continue
            t = resolve.resolve_target(ev.get("desc") or "这个",
                                       [i.get("desc") for i in st["day"]["items"] if i.get("desc")])
            out.append(resolve.ASK_TARGET if resolve.should_ask(t) else engine.do_query(st, t["value"]))
        elif kind == "end":
            d = core.combine(st["day"]["items"])
            r = core.classify_day(d["lo"], d["hi"], *st["plan"]["kcal_range"])
            b, why = core.streak_adjust(r["bucket"], st["day"].get("low_days", 1))
            out.append("今天结算：" + b + (f"（{why}）" if why else ""))

    d = core.combine(st["day"]["items"])
    hint = core.distribution_hint(core.meal_stats(st["day"]["items"]))
    if hint:
        out.append(hint)
    reply = "\n".join(out) if out else "没太听懂，换种说法？"
    now = __import__("datetime").datetime.now().strftime("%H:%M")
    st.setdefault("messages", []).append({"role": "user", "text": state.get("incoming", ""), "at": now})
    st["messages"].append({"role": "bot", "text": reply, "at": now})
    st["messages"] = st["messages"][-200:]
    engine.save(st)
    return {"reply": reply, "asks": 0}


def node_handoff(state: S):
    return {"reply": core.MEDICAL_STOP}


def build():
    conn = sqlite3.connect(CKPT, check_same_thread=False)
    g = StateGraph(S)
    g.add_node("wait", node_wait)
    g.add_node("parse", node_parse)
    g.add_node("clarify", node_clarify)
    g.add_node("handle", node_handle)
    g.add_node("handoff", node_handoff)
    g.add_edge(START, "wait")
    g.add_edge("wait", "parse")
    g.add_edge("clarify", "parse")
    g.add_edge("handle", "wait")
    g.add_edge("handoff", "wait")
    return g.compile(checkpointer=SqliteSaver(conn))


_graph = None
def graph():
    global _graph
    if _graph is None:
        _graph = build()
    return _graph


def start(thread="u1"):
    """进图，停在第一个暂停点。已经在里面就不重复进（否则会把空输入当成你的回复）。"""
    g = graph()
    cfg = {"configurable": {"thread_id": thread}}
    snap = g.get_state(cfg)
    if not snap.values:
        return g.invoke({}, cfg)
    return snap


def send(text, thread="u1"):
    """把一句话送进去，跑到下一个暂停点。"""
    return graph().invoke(Command(resume=text), {"configurable": {"thread_id": thread}})
