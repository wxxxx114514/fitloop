# -*- coding: utf-8 -*-
"""页面自检：语法 + 关键元素 + 前端用到的字段后端是否都有。"""
import sys, re, json, subprocess, tempfile, os, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8790"
ok = True

html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode()
for tag in ['id="gate"', 'id="pf"', 'id="chat"', 'id="inp"', 'id="send"']:
    hit = tag in html
    ok &= hit
    print(("OK   " if hit else "MISS ") + tag)

m = re.search(r"<script>(.*)</script>", html, re.S)
js = m.group(1) if m else ""

f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
f.write(js); f.close()
r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
os.unlink(f.name)
print(("OK   " if r.returncode == 0 else "FAIL ") + "js syntax")
if r.returncode != 0:
    print(r.stderr[:600]); ok = False

state = json.loads(urllib.request.urlopen(BASE + "/api/state", timeout=20).read().decode())
used = set(re.findall(r"\bs\.([a-z_]+)", js))
missing = sorted(k for k in used if k not in state)
print(("OK   " if not missing else "MISS ") + "前端字段都能在后端找到" + ("" if not missing else " -> " + str(missing)))
ok &= not missing

print("\nRESULT:", "PASS" if ok else "FAIL")
