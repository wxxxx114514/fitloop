# -*- coding: utf-8 -*-
"""还原（resolve）：把"这个/那个/它/第二个"换成具体对象。
纯规则、纯代码，不调模型。"""

# 近指代词：指向"最近提到的那个东西"
NEAR = ("这个", "那个", "它", "这东西", "这玩意",
        "刚才那个", "上面那个", "刚才说的", "你说的那个")

# 序数：指向"刚才列出来的第几个"
ORD = {"第一个": 0, "第二个": 1, "第三个": 2, "第四个": 3, "第五个": 4}

ASK_TARGET = "你说的是哪个？举个例子或者再说一遍名字就行。"


def resolve_target(raw, recent, candidates=None):
    """返回 {value, status, why}
    status: ok 找到了 / missing 找不到 / ambiguous 不知道该数哪个清单
    """
    raw = (raw or "").strip()
    if not raw:
        return {"value": None, "status": "missing", "why": "空的"}

    if raw in NEAR:
        if not recent:
            return {"value": None, "status": "missing", "why": "代词，但前面没有可指代的东西"}
        return {"value": recent[-1], "status": "ok", "why": "代词 → 最近一个"}

    if raw in ORD:
        if not candidates:
            return {"value": None, "status": "ambiguous", "why": "序数，但不知道在数哪一份清单"}
        i = ORD[raw]
        if i >= len(candidates):
            return {"value": None, "status": "missing",
                    "why": f"要第 {i + 1} 个，但只有 {len(candidates)} 个"}
        return {"value": candidates[i], "status": "ok", "why": "按序号定位"}

    return {"value": raw, "status": "ok", "why": "本身就是具体东西"}


def should_ask(result):
    """只有这两种情况才该反问，ambiguous 也算，因为模型没猜的余地。"""
    return result["status"] in ("missing", "ambiguous")
