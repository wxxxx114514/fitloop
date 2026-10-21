# -*- coding: utf-8 -*-
"""接线检查：规则写了，产品里到底有没有人调用它。
单测绿不代表规则活着 —— 这个脚本专门抓『测死代码』。

三档结论：
  OK        产品代码直接调
  INDIRECT  只被别的库函数调（间接可达）
  DEAD      除了定义和测试，没有任何调用
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = ['app.py', 'graph_app.py', 'server.py']
LIB = ['core.py', 'plan_rules.py', 'trend.py', 'resolve.py']

RULES = [
    'escalate', 'load_level', 'load_snapshot', 'streak_adjust', 'classify_day',
    'combine', 'protein_suggestion', 'sleep_gate', 'weight_sane', 'minutes_sane',
    'water_weight_hint', 'deload_hint', 'distribution_hint', 'compress_day',
    'month_day', 'parse_hours', 'parse_minutes', 'find_item',
    'free_meal_plan', 'level_from_progress', 'apply_hysteresis', 'progress', 'progress_lower',
    'weigh_interval_days', 'judge', 'resolve_target',
]

def read(f):
    p = os.path.join(HERE, f)
    return open(p, encoding='utf-8').read() if os.path.exists(p) else ''

prod = {f: read(f) for f in PRODUCT}
lib = {f: read(f) for f in LIB}

def count(name, files):
    pat = re.compile(r'\b' + re.escape(name) + r'\s*\(')
    hits, where = 0, set()
    for f, txt in files.items():
        n = len(pat.findall(txt))
        if n:
            hits += n
            where.add(f)
    return hits, where

rows = []
for name in RULES:
    d, dw = count(name, prod)
    i, iw = count(name, lib)
    # 定义处本身不算调用：每个模块里都有一次 def name(
    i = max(0, i - 1) if any(re.search(r'def ' + re.escape(name) + r'\s*\(', t) for t in lib.values()) else i
    state = 'OK' if d else ('INDIRECT' if i else 'DEAD')
    rows.append((name, state, d, i, ','.join(sorted(dw or iw))))

ok = [r for r in rows if r[1] == 'OK']
ind = [r for r in rows if r[1] == 'INDIRECT']
dead = [r for r in rows if r[1] == 'DEAD']

print(f'{len(ok)} 直接接线 / {len(ind)} 间接 / {len(dead)} 死代码\n')
print(f"{'结论':<10}{'规则':<22}{'产品':<5}{'库内'}")
print('-' * 58)
for n, s, d, i, w in rows:
    print(f'{s:<10}{n:<22}{d:<5}{i}')
print()
if dead:
    print('死代码（除了定义和测试没人调）:')
    for n, s, d, i, w in dead:
        print('  -', n)
else:
    print('没有死代码：每条规则都能从产品走到。')
