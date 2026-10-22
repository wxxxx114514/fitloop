# -*- coding: utf-8 -*-
"""验证接入：kb 正常 → 带出处；kb 不可用 → 静默降级。"""
import sys
sys.path.insert(0, r"D:\project\fitloop")
sys.stdout.reconfigure(encoding="utf-8")
import app

print("1) kb 正常:")
hits = app.kb_lookup("每天奶类摄入多少")
print("   命中", len(hits), "条")
if hits:
    print("   第一条: p%s %s" % (hits[0]["page"], hits[0]["text"][:50]))

print("\n2) 带出处的回答:")
print("   " + app.with_citation("每天奶类摄入多少", "每天 300ml 左右。").replace("\n", "\n   "))

print("\n3) 降级（把 kb 路径指到不存在的地方）:")
app._KB = None
orig = app.kb_lookup
app.kb_lookup = lambda *a, **k: []
print("   回答:", app.with_citation("每天奶类摄入多少", "每天 300ml 左右。"))
