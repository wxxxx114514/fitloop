# -*- coding: utf-8 -*-
"""陪跑 · 最小可跑版：打一句 → 记账 → 回一句。
先不加图、不加界面。所有步骤都是一个 状态->状态 的函数，以后套 LangGraph 直接搬。"""
import sys, os, json, sqlite3, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.pylibs')
if os.path.isdir(_LIBS):
    sys.path.insert(0, _LIBS)   # 本地离线包目录，没有就跳过（别人克隆下来走 pip）

import core, resolve, trend as trend_mod
from openai import OpenAI

DB = os.path.join(HERE, "data.db")

# ---------------- 模型 ----------------
def _read_env(path):
    cfg = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="ignore"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _client():
    """key 的来源：环境变量 → fitloop/.env → 项目根 .env。仓库里不放 key。"""
    cfg = {}
    for p in (os.path.join(HERE, ".env"), os.path.join(os.path.dirname(HERE), ".env")):
        cfg.update({k: v for k, v in _read_env(p).items() if k not in cfg})
    key = os.environ.get("FITLOOP_API_KEY") or cfg.get("FITLOOP_API_KEY") or cfg.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("没找到 API key：设置环境变量 FITLOOP_API_KEY，或在 fitloop/.env 里写 FITLOOP_API_KEY=...")
    base = os.environ.get("FITLOOP_BASE_URL") or cfg.get("FITLOOP_BASE_URL") or cfg.get("OPENAI_BASE_URL") or "https://api.deepseek.com"
    return OpenAI(api_key=key, base_url=base)

def _json_call(system, user, max_tokens=400):
    return _json_msgs([{"role": "system", "content": system},
                       {"role": "user", "content": user}], max_tokens)


def _json_msgs(messages, max_tokens=400, tries=2):
    """模型返回坏 JSON 时重试一次；还不行返回 {"_error": ...}，不抛异常把请求打断。"""
    last = "未知错误"
    for _ in range(tries):
        r = _client().chat.completions.create(
            model="deepseek-chat", temperature=0, max_tokens=max_tokens,
            messages=messages, response_format={"type": "json_object"})
        raw = (r.choices[0].message.content or "").strip()
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            last = "模型返回的不是 JSON"
            continue
        if not isinstance(d, dict):
            last = "模型返回的不是对象"
            continue
        return d
    return {"_error": last}


def _history(st, limit=60):
    """当天的完整对话，按正常聊天顺序给模型。"""
    out = []
    for m in (st.get("messages") or [])[-limit:]:
        out.append({"role": "user" if m["role"] == "user" else "assistant",
                    "content": m["text"]})
    return out

PARSE_SYS = '''你是减脂记录解析器。把用户一句话解析成若干条记录，只输出 JSON。
kind 只能是: eat / train / weigh / sleep / goal / recall / special / query / end
slot 只能是: 早 / 午 / 晚 / 加餐 / 下午 / 空字符串
desc: 这一条对应的原话片段
skipped: true 表示说过但没做
needs_clarify: true 表示不给追加信息就算不准
op 只能省略或填 amend（改上一条）/ drop（删上一条）
输出: {"events":[{"kind":"eat","slot":"午","desc":"食堂两荤一素","skipped":false,"op":""}],
       "needs_clarify":false,"query_target":"","why":"一句话"}
如果用户是在纠正前面记错的东西（"不是卤蛋""刚才那个算多了""早上那个玉米饼其实是两个"），
就输出 op="amend"，desc 填纠正后的内容，target 填他在指哪一条（原话里的关键词，比如"玉米饼"）；
只说"刚才那个"就留空 target。
硬规则: 情绪/疲惫/想放弃 → special；受伤生病 → 只输出一条 special；纯提问 → query 且 query_target 填"这个"之类的原话；说睡了多久 → sleep，desc 保留原话；说要改目标体重 → goal；报体重 → weigh（weigh 永远不需要 needs_clarify）；问某一天吃过什么 → recall（desc 留日期原话）；说练了什么 → train（desc 留原话，有分钟数就带上 rpe 可省）'''

EST_SYS = '''把这段饮食换算成热量和三大营养素，只输出 JSON。
{"kcal":整数,"lo":整数,"hi":整数,"protein_g":整数,"carb_g":整数,"fat_g":整数,"sodium_mg":整数,"basis":"依据"}
区间要诚实：份量说不清的，lo/hi 拉开。'''

QUERY_SYS = '''你是减脂陪跑。用户问某样东西能不能吃/合不合适。只输出 JSON: {"reply":"一到两句话"}
必须结合今天的剩余额度来答，不要泛泛而谈。不要说"你应该"。'''

# ---------------- 存档 ----------------
OFFSET_FILE = os.path.join(HERE, ".dayoffset")


def day_offset():
    """测试用：假装过了几天。0 表示真实日期。"""
    try:
        return int(open(OFFSET_FILE).read().strip() or "0")
    except Exception:
        return 0


def set_day_offset(n):
    open(OFFSET_FILE, "w").write(str(int(n)))


def now_day():
    """按凌晨 4 点切天，不按午夜。支持测试用的日期偏移。"""
    return core.day_key(datetime.datetime.now() + datetime.timedelta(days=day_offset()))

def init_db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
    con.commit(); con.close()

def load():
    init_db()                      # 文件被删过也能自己把表建回来
    con = sqlite3.connect(DB)
    row = con.execute("SELECT v FROM kv WHERE k='state'").fetchone()
    con.close()
    if row:
        st = json.loads(row[0])
    else:
        st = {
            "profile": {"height": 175, "age": 20, "sex": "m", "start_kg": 78.0,
                        "target_kg": 68.0, "week": 1},
            "plan": {"kcal_range": [2070, 2270], "protein_g": 125},
            "day": {},
            "weights": [],
            "sleep": [],
            "messages": [],
            "start_date": now_day(),
        }
    if st["day"].get("date") != now_day():
        old = st["day"]
        if old.get("items") or old.get("sleep_h"):
            arch = st.setdefault("archive", {})
            arch[old["date"]] = {"items": old.get("items", []),   # 明细按天留，能回查
                                 "sleep_h": old.get("sleep_h")}
            for k in list(arch)[:-120]:
                arch.pop(k, None)
            st.setdefault("summaries", []).append(core.compress_day(old))
            st["summaries"] = st["summaries"][-90:]
        st["messages"] = []          # 每天一遍新上下文，只留系统提示词
        st["day"] = {"date": now_day(), "kcal": 0, "lo": 0, "hi": 0, "protein": 0,
                     "items": [], "events": [], "sleep_h": None}
    return st

def save(st):
    con = sqlite3.connect(DB)
    con.execute("INSERT OR REPLACE INTO kv (k,v) VALUES ('state',?)", (json.dumps(st, ensure_ascii=False),))
    con.commit(); con.close()

# ---------------- 各步骤 ----------------
def digest(st):
    """喂给解析节点的不是对话原文，是今天的事实。"""
    d = core.combine(st["day"]["items"])
    lo, hi = st["plan"]["kcal_range"]
    done = "；".join((i.get("desc") or "")[:14] for i in st["day"]["items"][-6:]) or "还没记"
    convo = st.get("messages", [])[-8:]
    said = " ｜ ".join(f"{m['role']}:{m['text'][:26]}" for m in convo) or "（还没聊）"
    hist = st.get("summaries", [])[-3:]      # 更早的留在库里，需要再查，不进上下文
    past = " ｜ ".join(core.summarize_line(s) for s in hist) or "（还没有历史）"
    return (f"最近几天：{past}\n今天的对话：{said}\n"
            f"今天已吃 {d['kcal']:.0f} 大卡（额度 {lo}~{hi}），"
            f"蛋白 {d['protein_g']:.0f}/{st['plan']['protein_g']}g。已记过：{done}")


def parse(text, st=None):
    """正常上下文：system 带静态事实，中间是当天全部对话，最后一句是要解析的话。"""
    sys_prompt = PARSE_SYS
    if st is not None:
        sys_prompt += "\n\n【今天的事实，只作参考，不要解析它】" + digest(st)
    msgs = [{"role": "system", "content": sys_prompt}]
    if st is not None:
        msgs += _history(st)
    msgs.append({"role": "user", "content": text})
    return _json_msgs(msgs)

def estimate(desc):
    return _json_call(EST_SYS, desc)

def do_eat(st, ev):
    amended = False
    if ev.get("op") == "amend":
        idx = core.find_item(st["day"]["items"], ev.get("target"))
        if idx is None:
            rows = "\n".join(f"{i + 1}. {str(it.get('desc'))[:18]} ≈ {it.get('kcal')} 卡"
                             for i, it in enumerate(st["day"]["items"]))
            return ("今天没找到「" + str(ev.get("target") or "") + "」这条。\n今天的记录：\n" +
                    rows + "\n要改哪一条？说「第几条」就行。")
        st["day"]["items"].pop(idx)
        amended = True
    est = estimate(ev.get("desc") or ev.get("slot", ""))
    st["day"]["items"].append({"desc": ev.get("desc"), "slot": ev.get("slot") or "",
                               "at": datetime.datetime.now().strftime("%H:%M"), **est})
    d0 = st["day"]
    d0["sodium"] = d0.get("sodium", 0) + int(est.get("sodium_mg") or 0)
    st.setdefault("sodium_by_date", {})[d0["date"]] = d0["sodium"]
    d = core.combine(st["day"]["items"])
    lo, hi = st["plan"]["kcal_range"]
    rem = core.remaining(d["lo"], d["hi"], lo, hi)
    rem_lo, rem_hi = rem["left_lo"], rem["left_hi"]
    gap = core.protein_gap(st["plan"]["protein_g"], d["protein_g"])
    head = ("改掉了「" + (ev.get("target") or "上一条") + "」，现在按这个算：") if amended else "记下了："
    out = [f"{head}{ev.get('desc','')} ≈ {est['kcal']} 大卡（{est['lo']}~{est['hi']}）"]
    out.append(f"今天已吃 {d['kcal']:.0f} 卡，还剩 {rem_lo:.0f}~{rem_hi:.0f}")
    if gap > 0:
        out.append(f"蛋白还差 {gap:.0f}g → {core.protein_suggestion(gap)}")
    return "\n".join(out)

def do_weigh(st, kg):
    ref = st["weights"][-1][1] if st["weights"] else st["profile"].get("start_kg")
    ok, why = core.weight_sane(kg, ref)
    if not ok:
        return "没收这一条：" + why + "。重报一次？"
    sd = datetime.date.fromisoformat(st["start_date"])
    idx = (datetime.date.today() - sd).days
    prev = st["weights"][-1][1] if st["weights"] else None
    st["weights"].append([idx, kg])
    j = trend_mod.judge([(p[0], p[1]) for p in st["weights"]])
    line = f"记下 {kg} kg。{j['text']}"
    if j["kg_per_week"] is not None:
        line += f"（约 {j['kg_per_week']} kg/周）"
    yday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    sod = st.get("sodium_by_date", {}).get(yday)
    hint = core.water_weight_hint(None if prev is None else kg - prev, sod)
    if hint:
        line += "\n" + hint
    return line

def do_train(st, ev, text=""):
    """训练记录必须落到 state，否则 escalate 永远是死代码。"""
    src = (ev.get("desc") or "") + " " + (text or "")
    mins = core.parse_minutes(src)
    ok, why = core.minutes_sane(mins)
    if not ok:
        return f"没收这一条训练：{why}。重报一次？"
    tr = st.setdefault("training", {})
    today = now_day()
    cur = dict(tr.get(today) or {"minutes": 0, "rpe": 6})
    if mins:
        cur["minutes"] += mins
    try:
        cur["rpe"] = int(ev.get("rpe") or cur.get("rpe") or 6)
    except (TypeError, ValueError):
        pass
    tr[today] = cur

    sessions, week, streak = core.load_snapshot(tr, today)
    lvl, why = core.load_level(sessions, week, streak)
    out = [f"记下训练 {cur['minutes']} 分钟（今天）。本周共 {week} 分钟。"]
    if lvl == "high":
        out.append("负荷偏高，注意恢复。")
    elif lvl == "excessive":
        out.append(f"负荷过量（{why}）。这周别再加了，安排一天完全休息。")
    else:
        out.append("负荷正常。")
    return "\n".join(out)


def do_special(st, ev):
    """情绪类输入要接住，不能落到「没太听懂」。"""
    said = (ev.get("desc") or "") + (ev.get("why") or "")
    low = ("累", "烦", "不想", "没忍住", "放弃", "崩溃", "失败")
    if any(w in said for w in low):
        st["day"]["mood"] = "low"
        return ("先不聊计划。\n今天能记多少记多少，明天重新开始，不用补昨天的账。")
    return "记下了。今天按原计划走，别加码。"


def do_recall(st, text):
    """查某一天的记录。明细在 archive 里，老数据只剩摘要。"""
    import datetime as _dt
    today = _dt.date.fromisoformat(now_day())
    d = core.month_day(text, today)
    if not d:
        return "没听出是哪天。说个日期，比如「10月18日」或「昨天」。"
    rec = (st.get("archive") or {}).get(d)
    if isinstance(rec, list):            # 兼容早期只存列表的格式
        rec = {"items": rec, "sleep_h": None}
    if rec and rec.get("items"):
        rows = "\n".join(f"- {i.get('desc')} ≈ {i.get('kcal')} 卡" for i in rec["items"])
        extra = f"\n（那晚睡 {rec['sleep_h']:g} 小时）" if rec.get("sleep_h") else ""
        return f"{d} 记的：\n{rows}{extra}"
    summ = [x for x in st.get("summaries", []) if x.get("date") == d]
    if summ:
        s = summ[0]
        return f"{d}：吃 {s['kcal']} 卡，{s['entries']} 条。那天的明细没留，只有合计。"
    return f"{d} 这天没有记录。"


def today_summary(st):
    """问"我吃了多少"这种，直接查数，别让模型猜。"""
    d = core.combine(st["day"]["items"])
    lo, hi = st["plan"]["kcal_range"]
    rem = core.remaining(d["lo"], d["hi"], lo, hi)
    rem_lo, rem_hi = rem["left_lo"], rem["left_hi"]
    gap = core.protein_gap(st["plan"]["protein_g"], d["protein_g"])
    n = len(st["day"]["items"])
    line = f"今天记了 {n} 条，合计约 {d['kcal']:.0f} 大卡（区间 {d['lo']:.0f}~{d['hi']:.0f}）。\n"
    line += f"额度 {lo}~{hi}，还剩 {rem_lo:.0f}~{rem_hi:.0f}。"
    if gap > 0:
        line += f"\n蛋白还差 {gap:.0f}g → {core.protein_suggestion(gap)}"
    return line


def do_query(st, target):
    d = core.combine(st["day"]["items"])
    lo, hi = st["plan"]["kcal_range"]
    rem = core.remaining(d["lo"], d["hi"], lo, hi)
    rem_lo, rem_hi = rem["left_lo"], rem["left_hi"]
    gap = core.protein_gap(st["plan"]["protein_g"], d["protein_g"])
    facts = (f"目标对象：{target}；今天已吃 {d['kcal']:.0f} 卡；"
             f"剩余额度 {rem_lo:.0f}~{rem_hi:.0f}；蛋白还差 {gap:.0f}g")
    msgs = [{"role": "system", "content": QUERY_SYS + "\n\n【事实】" + facts}]
    msgs += _history(st)
    msgs.append({"role": "user", "content": facts})
    r = _json_msgs(msgs, max_tokens=200)
    return r.get("reply", "")

def handle(text, st):
    if core.is_medical(text):
        return core.MEDICAL_STOP

    p = parse(text)
    if p.get("_error"):
        return f"我这条没解析出来（{p['_error']}），换个说法再来一次？"
    out = []
    events = p.get("events", [])
    if p.get("needs_clarify") and any(e.get("kind") != "query" for e in events):
        out.append("（这条我拿不太准，先按下面算，你可以补一句份量）")

    for ev in p.get("events", []):
        kind = ev.get("kind")
        if kind == "eat":
            out.append(do_eat(st, ev))
        elif kind == "weigh":
            m = ev.get("desc") or ""
            digits = "".join(ch if (ch.isdigit() or ch == ".") else "" for ch in text)
            kg = float(digits) if digits else None
            if kg:
                out.append(do_weigh(st, kg))
            else:
                out.append("没看到数字，再报一次体重？")
        elif kind == "train":
            out.append(do_train(st, ev, text))
        elif kind == "recall":
            out.append(do_recall(st, (ev.get("desc") or "") + " " + text))
        elif kind == "sleep":
            h = core.parse_hours(ev.get("desc") or text)
            if h is None:
                out.append("没听到几个小时，比如「昨晚睡了五个半小时」？")
            else:
                st["day"]["sleep_h"] = h
                st.setdefault("sleep", []).append(h)
                gate = core.sleep_gate(h, st["sleep"])
                out.append(gate["text"] or f"记下 {h:g} 小时，睡眠够，训练照常。")
        elif kind == "goal":
            import re as _re
            m = _re.search(r"(\d+(?:\.\d+)?)", text)
            if not m:
                out.append("没听到数字，比如「目标改成 75」。")
            else:
                kg = float(m.group(1))
                st["profile"]["target_kg"] = kg
                cur = st["weights"][-1][1] if st["weights"] else st["profile"].get("start_kg")
                out.append(f"目标改成 {kg:g} kg。现在 {cur:g}，还差 {round(cur - kg, 1)} kg。")
        elif kind == "special":
            out.append(do_special(st, ev))
        elif kind == "query":
            t = resolve.resolve_target(ev.get("desc") or "这个", [i["desc"] for i in st["day"]["items"] if i.get("desc")])
            if resolve.should_ask(t):
                out.append(resolve.ASK_TARGET)
            else:
                out.append(do_query(st, t["value"]))
        elif kind == "end":
            d = core.combine(st["day"]["items"])
            r = core.classify_day(d["lo"], d["hi"], *st["plan"]["kcal_range"])
            b, why = core.streak_adjust(r["bucket"], st["day"].get("low_days", 1))
            st["day"]["low_days"] = st["day"].get("low_days", 1) + (1 if b == "low" else 0)
            sessions, week, streak = core.load_snapshot(st.get("training", {}), now_day())
            lvl, why_lvl = core.load_level(sessions, week, streak)
            b, why2 = core.escalate(b, lvl)
            out.append(f"今天结算：{b}" + (f"（{why2 or why or r.get('why') or ''}）" if (why2 or why or r.get("why")) else ""))
    return "\n".join(out) if out else "没太听懂，换种说法？"

def main():
    init_db()
    if len(sys.argv) > 1:
        st = load()
        print(handle(" ".join(sys.argv[1:]), st))
        save(st)
        return
    print("陪跑 v0（输入 exit 退出）")
    st = load()
    while True:
        try:
            text = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("exit", "quit", "退出"):
            break
        if not text:
            continue
        print(handle(text, st))
        save(st)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()