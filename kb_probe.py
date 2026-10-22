# -*- coding: utf-8 -*-
"""不经过 MCP 传输，直接验证数据链路：fitloop 进程能否拿到 kb 的结果。"""
import sys, os
sys.path.insert(0, r"D:\project\fitloop-kb")
sys.stdout.reconfigure(encoding="utf-8")
from kb.retrieve import BM25, load
from kb.query import expand

rows = load()
bm = BM25(rows)
print("kb 语料块数:", len(rows))

for q in ["每天奶类摄入多少", "维生素D补多少"]:
    top = bm.score(expand(q))[:3]
    print(f"\n问：{q}")
    if not top:
        print("  无结果（应拒答）")
        continue
    for s, i in top:
        r = rows[i]
        print(f"  {s:5.2f} p{r['page']} [{r['kind']}] {r['text'][:50]}")
