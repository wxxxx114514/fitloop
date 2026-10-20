# 陪跑 · 设计 v1.1

## 0. 命题

**把说不清的一天翻译成结构化状态，再把状态翻译回人话说给你听。**
中间那层判断是硬的（阈值、算术），两头是软的（理解、表达）。

| 层 | 谁 | 干什么 | 为什么不能换 |
|---|---|---|---|
| 语义层 | **LLM** | 口语 → 带不确定度的数（热量、营养素、动机） | 只有它能理解「加班回家煮了碗面」 |
| 口径层 | **代码** | 数 → 档位、净能量、负荷、偏差 | 边界要可断言，模型在边界上会抖 |
| 表达层 | **LLM** | 档位 → 具体动作 + 语气 | 只有它能说人话，且要随档位换语气 |

**LLM 驱动的条件边长在语义层与口径层之间**：它决定「你这句话是什么意思」，不决定「这个意思该怎么处理」。

实测（DeepSeek，8 条口语饮食）：mean |err| 6.3%，±20% 内 8/8，区间覆盖真值 7/8。
模糊输入给宽区间（「火锅随便吃了点」→ [500,1400]），具体输入给窄区间。

**铁律：分档用区间，不用点估计。** 区间整段同档才判；跨档则追问，问满 2 次取保守侧。

---

## 1. 状态

~~~python
State = {
  profile: {height, age, sex, start_kg, target_kg, bmr: 1720, tdee_base: 2400},

  plan: {version: 3, kcal_range: [1650, 1850], protein_g: 120,
         training_plan: {...}, rationale: '...'},

  # 吃进去的：不只有热量，还有三大营养素
  intake: {items: [{food: '泡面', portion: '一碗',
                    kcal: 450, protein_g: 9, carb_g: 62, fat_g: 18}],
           kcal: 450, kcal_lo: 380, kcal_hi: 520,
           protein_g: 9, carb_g: 62, fat_g: 18,
           confidence: 'low', basis: '按杯面标准份估算'},

  # 练掉的
  training: {sessions: [{type: '力量', minutes: 60, rpe: 8, kcal_out: 420}],
             today_kcal_out: 420, week_minutes: 240,
             consecutive_high_days: 2},

  # 净剩
  energy: {net_kcal: 30, net_lo: -40, net_hi: 100},

  bucket: 'low',            # over | slight | normal | low | danger
  flags: {load: 'high',     # normal | high | excessive
          safety: 'none'},
  motive: 'busy',
  daily: {...}, trend: {...}, plan_history: [...],
}
~~~

---

## 2. 流程

~~~
START
  │
  ▼
read_input         LLM    自由文本 → daily + intake.items + training.sessions
  │
  ▼
estimate           LLM    items → kcal / 三大营养素 / [lo,hi] / basis
  │
  ├─ 缺运动记录 ──► ask_training   LLM 问一句 ─► interrupt ─► 回 estimate
  │
  ▼
load_check         代码   算今日消耗、周时长、连续高负荷天数
  │
  ▼
bucket             代码   用区间判档（摄入档）
  │
  ├── 区间跨档 & 追问<2 ─► ask_portion   LLM 生成问题 ─► interrupt ─► 回 estimate
  ├── 区间跨档 & 追问≥2 ─► narrow       代码 取保守侧, confidence=low
  │
  ▼
escalate           代码   组合判危险：吃少 + 练多 → 强制 danger
  │
  ▼
motive_gate        代码   档位 ∈ {over, low, danger} 才进 motive
  │
  ├── slight ────────────────────────────────► slight
  ├── normal ────────────────────────────────► normal
  └── over / low / danger
           ▼
        motive     LLM   「聚餐？情绪性？忙忘了？在克扣自己？」
           │            Command(goto=) 只允许落在这三个节点（代码白名单）
           ├──► over
           ├──► low
           └──► danger
           ▼
     ┌──────────────┬───────────────────┐
     ▼              ▼                   ▼
   五档节点（LLM 出话 + 可能附 plan_patch / action list）
     │
     ▼
  guard_plan      代码  合法？──否──► 回该档节点（带 errors）
     │是
     ▼
  commit          代码  plan.version+1，写 plan_history
     │
     ▼
  record          代码  trend / streak / 依从率 / 负荷曲线
     │
     ▼
  report ──► interrupt（等明天）──► END
~~~

---

## 3. 阈值（全是代码，全可断言）

### 3.1 摄入档

| 档 | 条件 |
|---|---|
| danger | kcal < BMR |
| low | BMR ≤ kcal < lo |
| normal | lo ≤ kcal ≤ hi |
| slight | hi < kcal ≤ hi × 1.12 |
| over | kcal > hi × 1.12 |

### 3.2 负荷档

| 档 | 条件 |
|---|---|
| high | 今日 ≥ 90 分钟，或 rpe × minutes ≥ 600 |
| excessive | 周时长 > 420 分钟，或连续 high ≥ 3 天，或周负荷增幅 > 30% |

### 3.3 升级规则（escalate，代码，不看模型的脸色）

| 条件 | 动作 |
|---|---|
| load == excessive 且 bucket ∈ {low, danger} | **强制 danger** |
| bucket == danger 且 load == excessive | 同上，且动作清单必须含「今天不练」 |
| load == excessive 且 bucket ∈ {over, normal} | 档位不变，注入「减量」指令 |

**为什么必须是代码**：吃太少 + 练太多是减脂里最常见的自伤方式，而它恰好由「两个各自看起来都不太糟的数字」组成。交给模型判断等于赌。

### 3.4 净能量只做方向判断

net = kcal_in − kcal_out。运动消耗用 MET 估算，误差 20~30%，**比食物的 6% 差得多**。
所以 net 只用来判断「是不是负得离谱」，不参与精确分档，界面上必须标「粗估」。

---

## 4. 五个节点（v1.1 的改动都在 low 和 danger）

| 节点 | 核心判断 | 做什么 | 绝对不做 |
|---|---|---|---|
| over 超标 | 聚餐还是情绪性进食 | 先接住，只找**一处**可改，给明天一条具体调整 | 加倍惩罚、减餐、说教 |
| slight 稍微超标 | 是否逐日漂移 | 不改计划，只记一笔 | 当场重规划 |
| normal 正常 | 有没有兑现计划 | 强化到具体行为 | 「继续加油」 |
| **low 低** | **缺的是哪一类营养** | **按缺口给具体食物 + 份量** | 夸「自律」、只说「多吃点」 |
| **danger 危险** | **现在该干什么** | **动作清单，必须可执行** | 任何鼓励再少吃的话 |

### 4.1 low：缺口由代码算，说法由模型给

代码先算：protein_gap = 目标蛋白 − 实吃蛋白、carb_ratio、meal_count。
模型只负责变成「你还能吃的选择」，例如：

~~~
蛋白还差 42g ≈ 200g 鸡胸 / 3 个鸡蛋 + 一杯牛奶
你今天基本只有碳水，晚上补一餐蛋白就够，别空着睡
~~~

**禁止**输出「注意营养均衡」这种没有动作的句子。验收看「动作可执行率」。

### 4.2 danger：输出动作清单，不输出感慨

~~~python
{actions: [
   {when: '现在', do: '吃', amount: '两个鸡蛋 + 一杯牛奶 ≈ 300 kcal'},
   {when: '今天', do: '不训练', amount: '今天任何训练都取消'},
   {when: '明天', do: '恢复正常区间', amount: '回到 1650~1850'}
 ],
 escalate: False}
~~~

- 2~4 条，每条必须带 when + amount
- load == excessive 时，**必须**有一条是降负荷
- 出现催吐 / 泻药 / 晕厥 / 持续心悸 → escalate=true，只保留「停止 + 就医/求助」，图直接 END

---

## 5. 边表

| # | 从 | 到 | 谁决定 | 依据 |
|---|---|---|---|---|
| 4 | estimate | ask_training | 代码 | 缺运动记录 |
| 5 | ask_training / ask_portion | estimate | **人** | interrupt 拿到回答 |
| 6 | bucket | ask_portion | 代码 | 区间跨档 且 追问 < 2 |
| 7 | bucket | narrow | 代码 | 区间跨档 且 追问已满 |
| 8 | escalate | motive_gate | 代码 | 组合规则（3.3） |
| 9 | motive_gate | slight / normal | 代码 | 档位直连 |
| 10 | motive_gate | motive | 代码 | 档位 ∈ {over, low, danger} |
| **11** | **motive** | **over / low / danger** | **LLM** | Command(goto=) + 白名单 |
| 12 | 五档 | guard_plan | 代码 | 有 plan_patch |
| 13 | guard_plan | 该档节点 | 代码 | 计划不合法，带 errors 回退 |
| 14 | report | END | **人** | 等你明天再来 |

**v1 里由 LLM 决定的边只有第 11 条。**

### 之后接的

1. **要不要重规划**：代码算出连续偏离，「现在改还是再观察」是判断
2. **要不要收手**：你明显烦躁时今天别说了

---

## 6. 为什么这不能是一条 while

- 计划对象跨天活着、有版本、可回放
- 三处 interrupt：等打卡、等补运动记录、等确认新计划
- guard_plan 驳回后带 errors 回退，可多轮
- 五档策略互斥，塞一个 prompt 会互相污染；拆开才能按档单独算准确率

---

## 7. 验收

1. **分档单测**：五档边界 + escalate 组合规则，合成数据断言，不调模型
2. **负荷单测**：week_minutes / consecutive_high_days / 增幅
3. **估热量**：20 条真实饮食，目标 ±20% 内 ≥ 70%
4. **估营养素**：蛋白 / 碳水 ±30%
5. **分档混淆矩阵**：60 条评测集
6. **动作可执行率**：抽 20 条 danger/low 输出，人工判「能不能照着做」，目标 ≥ 80%
7. **14 天真实使用**：依从率、中断恢复率、回放正确率
8. **对照**：固定计划基线

---

## 8. 红线

- 不做医疗判断、不下诊断、不给药物建议
- BMR、1.12、420 分钟、rpe×minutes ≥ 600 都是**设计常量**，注释注明来源，不是医学结论
- danger 且 escalate → 只保留就医/求助，图上 END
