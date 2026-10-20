# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve import resolve_target, should_ask

n = 0
def eq(got, want, msg):
    global n
    assert got == want, f"{msg}: got {got!r}, want {want!r}"
    n += 1

# 1 不是代词，原样通过
r = resolve_target("红烧肉", ["烤鸡"])
eq((r["value"], r["status"]), ("红烧肉", "ok"), "具体名字不动")

# 2 最普通的代词
r = resolve_target("这个", ["红烧肉"])
eq((r["value"], r["status"]), ("红烧肉", "ok"), "这个→最近一个")

# 3 有多个时取最近的
r = resolve_target("这个", ["黄焖鸡", "红烧肉"])
eq(r["value"], "红烧肉", "多个时取最近")

# 4 没有可指代的东西 → 必须反问
r = resolve_target("这个", [])
eq((r["value"], r["status"]), (None, "missing"), "空上下文→missing")
eq(should_ask(r), True, "missing 要反问")

# 5 更口语的代词
r = resolve_target("刚才那个", ["白灼虾"])
eq(r["value"], "白灼虾", "刚才那个→最近一个")

# 6 缺省上下文
r = resolve_target("它", [])
eq(r["status"], "missing", "它→没有指代对象")

# 7 序数，有清单（清单要显式传，不能跟"最近提到的"混）
r = resolve_target("第二个", [], candidates=["红烧肉", "烤鸡"])
eq((r["value"], r["status"]), ("烤鸡", "ok"), "第二个→清单第2个")

# 8 序数越界
r = resolve_target("第三个", [], candidates=["红烧肉", "烤鸡"])
eq((r["value"], r["status"]), (None, "missing"), "第三个但只有两个")

# 9 序数但没清单
r = resolve_target("第二个", [], candidates=None)
eq((r["value"], r["status"]), (None, "ambiguous"), "序数没有清单→ambiguous")
eq(should_ask(r), True, "ambiguous 也要反问")

# 10 空输入
r = resolve_target("", ["红烧肉"])
eq(r["status"], "missing", "空字符串")

# 11 正常对象不需要反问
eq(should_ask(resolve_target("卤肥肠", [])), False, "具体名字不反问")

print(f"ALL PASS  ({n} assertions)")
