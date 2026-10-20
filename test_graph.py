# -*- coding: utf-8 -*-
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, r'D:\project\.pylibs')
import graph_app as G

G.start("t1")
for msg in ["中午食堂两荤一素", "76.8", "这个吃合不合适"]:
    r = G.send(msg, "t1")
    print("你>", msg)
    print("它>", (r.get("reply") or "（停住了：追问）").replace("\n", " | "))
    if r.get("__interrupt__"):
        print("   [暂停]", r["__interrupt__"][0].value)
    print()
