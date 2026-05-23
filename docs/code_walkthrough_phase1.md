# Phase 1 代码导读

本文档帮助理解 Phase 1 静态 FJSP 实验平台的代码结构和关键概念。

## 推荐阅读顺序

```
1. src/data/instance.py        ← 从数据结构开始
2. src/scheduling/encoding.py  ← 调度结果的数据结构
3. src/scheduling/decoding.py  ← 如何把"分配方案"变成"调度时间表"
4. src/scheduling/feasibility.py ← 如何验证调度结果是否合法
5. src/solvers/heuristics.py   ← 四种启发式规则
6. src/solvers/ortools_solver.py ← CP-SAT 精确求解器
7. src/vis/gantt.py            ← 甘特图可视化
8. experiments/exp_001_toy_instance.py ← 串联所有模块的实验脚本
```

## 每个文件负责什么

| 文件 | 职责 |
|---|---|
| `instance.py` | 定义 FJSP 实例：Job → Operation → MachineOption |
| `encoding.py` | 定义 ScheduleRecord（一条调度记录）和 ScheduleResult（完整调度方案） |
| `decoding.py` | 将机器分配方案转换为带时间的调度表（半主动解码） |
| `feasibility.py` | 校验调度方案是否满足 7 项约束 |
| `heuristics.py` | 四种调度规则：FIFO、SPT、EarliestFinishTime、Random |
| `ortools_solver.py` | OR-Tools CP-SAT 精确求解器 |
| `gantt.py` | matplotlib 甘特图可视化 |

## 初学者需要补的 Python 语法

### @dataclass

自动生成 `__init__`、`__repr__`、`__eq__` 等方法。等价于手写一个有很多属性的 class。

```python
@dataclass
class ScheduleRecord:
    job_id: int
    op_id: int
    # 自动生成: ScheduleRecord(job_id=0, op_id=1, ...)
```

### @dataclass(frozen=True)

`frozen=True` 表示创建后不可修改。用于实例数据（Operation、Job），防止意外修改已加载的 FJSP 实例。

```python
@dataclass(frozen=True)
class Operation:
    op_id: int
    # op = Operation(op_id=0, ...); op.op_id = 1  ← 会报错
```

### @property

让方法像属性一样访问，不需要加括号。

```python
class Job:
    @property
    def num_ops(self) -> int:
        return len(self.operations)

job = Job(...)
print(job.num_ops)   # 不需要写 job.num_ops()
```

### field(default_factory=list)

`@dataclass` 中不能直接写 `jobs: List[Job] = []`，因为所有实例会共享同一个列表。`default_factory=list` 每次创建新实例时都会生成一个新的空列表。

### 类型注解

```python
MachineOption = Tuple[int, int]             # (机器编号, 加工时间)
jobs: List[Job]                             # Job 的列表
result: FJSPInstance | None = None          # 可以是 FJSPInstance 或 None
def get_pt(self, job_id: int) -> int:       # 参数是 int，返回 int
```

### 异常

```python
raise ValueError(f"Machine {machine_id} not in options")  # 抛出异常，终止程序
raise RuntimeError(f"infeasible schedule: {violations}")   # 运行时错误
```

## FJSP 实例数据结构

```
FJSPInstance
  ├── num_jobs: 3
  ├── num_machines: 3
  └── jobs: [Job0, Job1, Job2]
        ├── Job0
        │     ├── job_id: 0
        │     └── operations: [Op0, Op1]
        │           ├── Op0: machine_options=((0,3), (1,5))  ← 可在M0加工3时间，或M1加工5时间
        │           └── Op1: machine_options=((1,4), (2,6))
        └── Job1
              └── ...
```

## 代码执行流程

```
create_toy_instance()
    │
    ▼
heuristic_solve(instance)  或  ortools_solve(instance)
    │                              │
    │  生成 assignment             │  CP-SAT 求解
    │  [(job,op,machine), ...]     │
    ▼                              ▼
decode_schedule(assignment, instance)
    │
    │  半主动解码: start = max(job前序完成, 机器空闲)
    ▼
check_feasibility(result)
    │
    │  校验 7 项约束
    ▼
plot_gantt(result)
    │
    ▼
保存 PNG 或显示
```

## OR-Tools / CP-SAT 基本概念

### CpModel

约束规划模型，所有变量和约束都注册在上面。

### IntVar

整数变量，值域 [lb, ub]。用于表示工序的开始时间和结束时间。

### BoolVar

布尔变量，值为 0 或 1。用于表示"是否选择某个机器"。

### OptionalIntervalVar

可选时间区间。由 `start`、`duration`、`end` 和 `presence`（BoolVar）组成。
- `presence=True`：区间生效，必须满足 start + duration == end
- `presence=False`：区间不生效，不参与 NoOverlap 约束

### AddExactlyOne

恰好一个为真。用于"每道工序恰好选择一个机器"：

```python
model.AddExactlyOne([presence_M0, presence_M1, presence_M2])
# 等价于: presence_M0 + presence_M1 + presence_M2 == 1
```

### AddNoOverlap

同一时间只能有一个区间生效。用于"同一机器上的工序不重叠"：

```python
model.AddNoOverlap([interval_J0O0, interval_J1O0, interval_J2O1])
# 这些区间在时间轴上不能重叠（只考虑 presence=True 的）
```

### OnlyEnforceIf

条件约束。只在指定 BoolVar 为真时才生效：

```python
model.Add(end_cur <= start_next).OnlyEnforceIf([p_cur, p_next])
# 只有当 p_cur 和 p_next 都为真时，才要求 end_cur <= start_next
```

### OPTIMAL vs FEASIBLE

- `OPTIMAL`：求解器证明已找到全局最优解
- `FEASIBLE`：找到可行解，但可能不是最优（可能因为时间限制提前停止）

## 各模块自测问题

### instance.py
1. `frozen=True` 和普通 `@dataclass` 有什么区别？
2. `jobs_array` 的三层嵌套结构分别代表什么？
3. 为什么 `field(default_factory=list)` 不能直接写 `= []`？

### encoding.py / decoding.py
1. `ScheduleRecord` 的 `end` 字段是计算出来的还是手动填的？
2. `decode_schedule` 中 `start = max(...)` 的两个约束分别来自哪里？
3. 什么是"半主动解码"？与"主动解码"有什么区别？

### feasibility.py
1. feasibility checker 检查了哪 7 项约束？
2. 如果 job_id 越界，checker 会崩溃还是会返回 violations？
3. `PRECEDENCE_VIOLATION` 和 `MACHINE_OVERLAP` 分别检查什么？

### heuristics.py
1. FIFO 和 SPT 的区别是什么？
2. `earliest_finish_time_solve` 的贪心策略是什么？
3. 四种启发式中，哪个需要自己管理时间状态（不依赖 decode_schedule）？

### ortools_solver.py
1. `OptionalIntervalVar` 的 `presence` 参数有什么作用？
2. `AddExactlyOne` 和 `AddNoOverlap` 分别施加什么约束？
3. `OnlyEnforceIf` 在 precedence 约束中起什么作用？
4. solver status 为 `FEASIBLE` 时，代码如何处理？

### gantt.py
1. 为什么要 `matplotlib.use("Agg")`？
2. `invert_yaxis()` 的作用是什么？
3. 每个工件的颜色是如何确定的？
