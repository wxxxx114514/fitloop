# -*- coding: utf-8 -*-
import sys, json
_LIBS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.pylibs')
if os.path.isdir(_LIBS):
    sys.path.insert(0, _LIBS)   # 本地离线包目录，没有就跳过（别人克隆下来走 pip）
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import _client
client = _client()

SYS = '''你是减脂记录解析器。把用户一句话解析成若干条记录，只输出 JSON。
kind 只能是: eat / train / weigh / special / query / end
slot 只能是: 早 / 午 / 晚 / 加餐 / 下午 / 空字符串（没有就空字符串，不要省略）
skipped: true 表示说过但没做（"今天没吃早饭"）
needs_clarify: true 表示不给追加信息就算不准

硬规则:
1. 一句话说多件事，输出多条，按时间顺序
2. 明确"没吃/没练"也要输出，skipped=true
3. 情绪、疲惫、想放弃、自责（"累""不想动""没忍住"）→ special，不是 query
4. 受伤、生病、疼痛 → 只输出一条 special，绝不再补一条"未练/未吃"
5. 纯提问（"能不能吃"）和与减脂无关的闲聊 → query，且 needs_clarify=false
6. 只有"内容无法估量"才 needs_clarify=true（"随便吃了点""狂吃了一顿""喝了一杯"这种没份量的）

输出: {"events":[{"kind":"...","slot":"...","skipped":false}],"needs_clarify":true,"why":"一句话"}'''

def norm(e):
    s = e.get('slot') or ''
    s = s if s in ('早','午','晚','加餐','下午') else ''
    out = e['kind'] + ('/' + s if s else '')
    return out + '(skip)' if e.get('skipped') else out

cases = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse_cases.json"), encoding='utf-8'))
cnt_ok = clar_ok = leak = extra = 0
rows = []
lines = []
for c in cases:
    r = client.chat.completions.create(model='deepseek-chat', temperature=0, max_tokens=300,
        messages=[{'role':'system','content':SYS},{'role':'user','content':c['text']}],
        response_format={'type':'json_object'})
    d = json.loads(r.choices[0].message.content)
    got = [norm(e) for e in d.get('events', [])]
    truth = c['ev']
    kinds_ok = sorted(x.split('(')[0].split('/')[0] for x in got) == sorted(x.split('(')[0].split('/')[0] for x in truth)
    same_cnt = len(got) == len(truth)
    if len(got) < len(truth): leak += 1
    if len(got) > len(truth): extra += 1
    ok = same_cnt and kinds_ok
    cnt_ok += ok
    c_ok = bool(d.get('needs_clarify')) == c['clarify']
    clar_ok += c_ok
    rows.append(ok and c_ok)
    lines.append(f"[{c['id']:>2}] {'OK  ' if ok and c_ok else 'MISS'} truth={truth} got={got} clarify={bool(d.get('needs_clarify'))}/{c['clarify']}")

n = len(rows)
print('\n'.join(lines))
print()
print(f'事件数+类型 全对: {cnt_ok}/{n}  ({cnt_ok/n*100:.0f}%)')
print(f'追问决策 正确: {clar_ok}/{n}  ({clar_ok/n*100:.0f}%)')
print(f'全对(两项都对): {sum(rows)}/{n}')
print(f'漏拆: {leak}   多拆: {extra}')