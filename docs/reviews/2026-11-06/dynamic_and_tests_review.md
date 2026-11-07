# Phase 2A `dynamic` 模块与全测试体系 只读审查

> 只读审查。未修改任何被 git 跟踪文件；唯一写入为本文件。统计口径：`pytest tests -q --co` = **228 个收集用例**，`tests/` 12 个文件共 1642 行（`tests/maintenance/conftest.py` 32 行，0 用例）。
> 覆盖率说明：`pytest tests --cov=fjsp_lab --cov-report=term` 全量运行超过 10 分钟仍未结束（维护/物流组含多组 CP-SAT 与穷举，`--cov` 又显著拖慢纯 Python 循环），按"2 分钟可接受"的约定已中止（job killed），**未取得覆盖率数字，本报告不含任何覆盖率数据**。

---

## 一、dynamic 模块结论

### 1.1 事件类型与同刻排序

- 4 种事件：`MachineBreakdown` / `MachineRepair` / `JobArrival` / `ProcessingTimeChange`（`events.py:29-89`），JSON spec 解析在 `events.py:91-140`。
- `apply_events`（`state.py:184-197`）只校验**非降序**，不排序、不做同刻规范化；同刻多事件严格按**输入顺序**依次应用（`state.py:192-195`；`replay.py:68-69` 的 `groupby` 同样保序）。docstring 只写了"preserve their supplied order"（`replay.py:53-54`），没有规范序。
- 同刻语义因此**依赖书写顺序**，实测反例（toy 实例）：
  - `[Breakdown(t=5,m=0,repair=10), Repair(t=5,m=0)]` → `unavailable_until = (5,0,0)`
  - `[Repair(t=5,m=0), Breakdown(t=5,m=0,repair=10)]` → `unavailable_until = (10,0,0)`
  - 同一批事件、两种顺序 → 两种机器可用性。给定输入后结果确定、可复现，但"同刻事件定序"没有模型语义。
- `MachineRepair` 是**无条件覆盖** `unavailable[m] = event.time`（`state.py:91`），可以把已宣布的停机**缩短**：实测 breakdown(repair=9) 后 repair(t=4) → 可用时间 4。`events.py:40-41` 只校验 `repair_time >= time`，没有"repair 必须早于 breakdown.repair_time"之类的约束，也允许写出互相矛盾的事件对。
- 状态不可变、`apply_event` 返回新对象；`test_state_transitions_are_pure`（`tests/test_dynamic.py:39-51`）覆盖了纯函数性。

### 1.2 冻结语义

`frozen_records_at_time`（`snapshot.py:10-30`）：

- 已完成：`record.end <= current_time`（`:26`）；在制：`record.start < current_time < record.end`（`:27`），默认一并冻结（`include_in_process=True`），对应"不可抢占"，注释在 `snapshot.py:16-19`。
- **`start == current_time` 的工序不冻结**，会被重调度成 `start >= current_time` 的新开工点。语义自洽，但该边界无文档、无测试。
- 冻结记录复制后按 `(job_id, op_id)` 排序，确定。
- **`include_in_process=False` 是没有任何测试覆盖的 footgun**：实测 time=3 时它只冻结 `(0,0)[0,3)`，把正在加工的 `(1,0)[0,4)` 留给重调度从 t=3 重新安排。模型没有中断概念，检查器也不会报错。

### 1.3 重调度对机器不可用 / 新工件到达 / 加工时间变更的处理

- **不可用时段：正确。** `machine_ready_time[m] = max(current_time, unavailable_until[m])`（`reschedule.py:45-48`），候选开工 `start = max(job_ready, machine_ready)`（`:69`），故障机在 repair 前不再开工（`tests/test_dynamic.py:72` 断言）。冻结的在制记录用 `machine_ready = max(..., record.end)` 兜住（`reschedule.py:50-56`），不会与在制工序重叠。
- **新工件到达：正确。** 追加 job、释放集合加新 id、`release_times += (event.time,)`（`state.py:127-144`）；重调度 `job_ready_time = max(current_time, release_time)`（`reschedule.py:38-44`），新工件不会早于到达开工（`tests/test_dynamic.py:73` 断言）。
- **加工时间变更：**
  - 未开工工序：改实例数据后重调度用新时长（`state.py:146-166`），`test_sequential_replay_freezes_each_prefix` 端到端覆盖。
  - 已冻结（完成/在制）工序：`state.apply_event` **不拒绝**，直接改实例；随后 `reschedule_from_state` 的静态检查以 `RuntimeError: ... PT_INSTANCE_MISMATCH` 失败（实测；`tests/test_dynamic.py:157-162` 固化了该行为）。即事件先被接受、错误后置到重调度阶段，且类型是 RuntimeError 而非事件拒绝。
  - `replay_events` 会在应用前显式拒绝改冻结工序时长（`replay.py:75-76`），**保护只存在于 replay 路径**；直接调 state/reschedule 不干净。
  - 动态检查器**不交叉校验**冻结记录时长与 state.instance 是否一致：它只把结果和传入的 frozen 记录比（`feasibility.py:56-65`）。实测"旧计划 + 改时长后的 state"仍返回 `(True, [])`；补上它的是静态检查器的 `expected_instance`（`reschedule.py:94`），独立调用动态检查器时不存在。

### 1.4 动态检查器能否抓住三类违规：断言位置 + 反例

| 违规 | 代码位置 | 触发条件 |
|---|---|---|
| 冻结记录被改 | `feasibility.py:56-65`（`FROZEN_RECORD_CHANGED`）；缺失 `:50-54`（`FROZEN_RECORD_MISSING`） | 结果中同 `(job,op)` 的 machine/start/end/processing_time 任一与冻结记录不同 |
| 故障期间机器被使用 | `feasibility.py:96-104`（`MACHINE_UNAVAILABLE`） | `state.current_time <= record.start < unavailable_until[machine]` 且记录**不在冻结集合** |
| 早于到达开工 | `feasibility.py:74-83`（`JOB_BEFORE_RELEASE`） | `record.start < job_release_times[job_id]` |

**实测可骗过检查器的反例（均已在本机跑通）：**

1. **A：`start < current_time` 的未冻结记录绕过停机检查。** `feasibility.py:97` 的条件 `state.current_time <= record.start` 把"过去开工"的记录排除在检查外。把一条未冻结记录改成 `start=2`（state.current_time=3）、放到停机到 50 的 2 号机上 → `(True, [])`。内部重调度不会产生这种记录，但检查器是公开 API，这是"故障期间机器被使用"的直接漏检。
2. **B：调用方谎报 frozen 集合即可让任意记录跳过停机检查。** `feasibility.py:93-95` 对 `(job,op) ∈ frozen_by_key` 直接 `continue`。构造 `frozen_records=(假记录,)`、结果与其逐字段相同、`start=10` 落在停机 `[3,50)` 内 → `(True, [])`。检查器无法区分"真实执行留下的记录"和"调用方自称冻结的记录"，这层信任边界没有任何文档/断言。
3. **C：结果与 state 的实例不交叉校验。** 换成另一个实例的 `result` 仍 `(True, [])`；只有 `replay.py:38-39` 的 `_validate_result` 补这一条。
4. **D：到达时间没有外部真值。** 默认 `released_job_ids=None → 全部释放`、`job_release_times=None → 全 0`（`state.py:31-45`）。直接 `DynamicFJSPState.from_instance(含新 job 的实例)` 就能让"到达工件"0 时刻开工并通过；`JOB_BEFORE_RELEASE` 只能查 state 自洽性。
5. **E：越界输入抛 `IndexError` 而非违规。** `release_times[record.job_id]`（`:75`）、`unavailable_until[record.machine_id]`（`:96`）无越界保护；实测 job 99 / machine 99 都抛 `IndexError`。
6. **F：`FROZEN_RECORD_CHANGED` 本身可靠**——逐字段比较，平移 +1 必被抓（`tests/test_dynamic.py:83-87` 覆盖）。但 **`JOB_BEFORE_RELEASE` 与 `FROZEN_RECORD_MISSING` 在现有测试中没有任何负例**。

**结论：** 三类检查的主路径都在，冻结记录被改的检查可信；但 `MACHINE_UNAVAILABLE` 有两个真实漏检（过去开工、谎报 frozen），`JOB_BEFORE_RELEASE` 无负例。"故障期间机器被使用"的最强约束只写在 `replay.py:77-80`（idle-only breakdown：在制机器不能被故障）这一条路径；直接调 `reschedule_from_state` / `check_dynamic_feasibility` 时该约束不存在，也没有测试。

---

## 二、测试强/弱分类统计

分类定义：(a) 断言具体约束/数值/异常码的强测试；(b) 只断言"不抛异常/非空/能跑通"的冒烟测试；(c) 回归/确定性/可复现测试；(d) 可能自我印证（用被测链路验证被测链路、无独立真值）的弱测试。按 **228 个收集用例**计。

### 2.1 总表

| 测试文件 | 用例数 | (a) 强 | (b) 冒烟 | (c) 回归/确定性 | (d) 自我印证 |
|---|---:|---:|---:|---:|---:|
| `tests/test_dynamic.py` | 26 | 25 | 0 | 1 | 0 |
| `tests/fjsp/test_fjsp_algorithms.py` | 42 | 38 | 2 | 2 | 0 |
| `tests/fjsp/test_fjsp_feasibility.py` | 13 | 13 | 0 | 0 | 0 |
| `tests/fjsp/test_instance_and_loader.py` | 16 | 13 | 1 | 2 | 0 |
| `tests/maintenance/test_maintenance_model.py` | 16 | 9 | 0 | 7 | 0 |
| `tests/maintenance/test_maintenance_algorithms.py` | 53 | 30 | 0 | 13 | 10 |
| `tests/maintenance/test_learned_policies.py` | 11 | 4 | 4 | 3 | 0 |
| `tests/logistics/test_logistics_model.py` | 16 | 13 | 0 | 3 | 0 |
| `tests/logistics/test_logistics_algorithms.py` | 22 | 11 | 4 | 5 | 2 |
| `tests/logistics/test_logistics_policy.py` | 8 | 3 | 4 | 1 | 0 |
| `tests/logistics/test_logistics_search.py` | 5 | 3 | 0 | 2 | 0 |
| **合计** | **228** | **162 (71%)** | **15 (7%)** | **39 (17%)** | **12 (5%)** |

整体判断：**这是一个"约束导向"而非"覆盖率导向"的测试体系**——大量用例走"算法输出 → 独立检查器 → 具体违规码/数值"，比常见项目强。弱项集中在少数 `try/except ... continue`、条件断言、以及同一链路自比。

### 2.2 最有价值的 3 个测试

1. `tests/maintenance/test_learned_policies.py:51-59` `test_vectorized_features_match_their_definition_along_random_trajectories` —— 用**逐行参考实现**重算 19 维特征，在随机轨迹上 `np.array_equal` 比对向量化实现。这是全库最独立、最难自我印证的一类真值测试，向量化特征几乎不可能靠"能跑通"发现错误。
2. `tests/maintenance/test_maintenance_algorithms.py:226-236` `test_both_construction_spaces_contain_a_proven_optimum` —— 穷举 decoder 全排列 + 穷举 MDP 可达空间，与 CP-SAT 的 OPTIMAL 值三方对齐，证明"两个构造空间都包含最优解"这一强命题；对搜索/解码器语义退化极敏感。
3. `tests/logistics/test_logistics_algorithms.py:110-128` `test_cpsat_optimum_is_bracketed_by_rules_and_bounds` —— 独立下界（`route_lower_bound`）+ 规则上界 + 不同 buffer/return 设置下的单调性（`None ≤ 1 ≤ 0`）同时夹住 CP-SAT 最优值，是把"参考模型正确"钉死的测试。

### 2.3 最没价值的 3 个测试

1. `tests/logistics/test_logistics_algorithms.py:43-53` `test_tight_buffers_either_schedule_feasibly_or_report_deadlock` —— `except SimulationDeadlock: continue`。在 buffer=1（按同文件 `:64-65` 的构造，1 个缓冲位足以化解交集环）上若所有规则都死锁，测试仍全绿；这是名义上"要么可行要么报告死锁"、实际可完全空转的门。
2. `tests/fjsp/test_fjsp_algorithms.py:47-53` `test_cpsat_time_limited_result_is_only_labelled_feasible` —— 唯一有内容的断言在 `if result.solver_status == 'FEASIBLE':` 里；若在 0.5s 内直接 OPTIMAL，则只断言了"可行 + 状态是两种之一"，上限/标签语义一行都没测。
3. `tests/logistics/test_logistics_policy.py:87-96` `test_imitation_samples_follow_the_best_rule` —— 名字承诺"跟随最佳规则"，实际只断言 `samples` 非空且 `0 <= choice < len(features)`；没有验证样本确实来自 `best_rule` 的最优动作，属于"名字>>内容"。

补充点名（同属弱）：`tests/maintenance/test_maintenance_algorithms.py:82-91` 的 `accepted(outcome.result) == decoded_value(data, mode, outcome.sequence)` 是同一 decoder 链路自比（(d) 类的主要来源）；`tests/logistics/test_logistics_algorithms.py:121-124`、`:197-202` 的 `except SimulationDeadlock: pass` / `except DecoupledPlanInfeasible: continue` 同样可让子断言空转。

### 2.4 覆盖空洞

- **dynamic 专属空洞**：`JOB_BEFORE_RELEASE`、`FROZEN_RECORD_MISSING` 无负例；`include_in_process=False` 无测试；`_validate_released_jobs`（未释放 job 应报错）与 `_validate_frozen_records`（重复/越界/非前缀路由）在 `reschedule.py:125-161`，**零测试**；`build_case` 的两个 `ValueError` 失败分支（`perturbation.py:107,118`）未测；`load_event_specs_json` 的坏 JSON/非 list/非 object 分支（`events.py:135-139`）未测；`events_from_specs` 无直接测试；`MachineRepair` 端到端只经由 JSON 文件间接覆盖；`parse_protocol` 只测 4 个负例（schema_version/phase/protocol_id/绝对路径/重复 seed 等未覆盖）。
- **重调度没有数值回归**：26 个 dynamic 用例里没有一个断言具体 makespan/记录序列；`test_event_files_reschedule_to_feasible_plans`（9 个）只过检查器。重构重调度规则时只能靠"仍可行"兜底。
- **CP-SAT 不是"只测 smoke"**：这假设不成立——CP-SAT 是全库测得最扎实的部分（与独立枚举对拍、最优值/下界夹逼、非法参数拒绝、整数范围拒绝）。真正的空洞在 dynamic：Phase 2A 没有求解器参考，因此动态层**没有独立最优/参考值**，只有可行性。
- **非法输入拒绝整体有测**（实例 9 例、事件 spec 6 例、协议 4 例、CP-SAT 参数 4 例、物流实例 6 例），不算空洞；缺的是 dynamic 内部各 validator 的分支。

### 2.5 三个 skip 与"为通过而弱化"的痕迹

三个 skip（无 `pytest.skip()` 写在用例体内）：

1. `tests/logistics/test_logistics_algorithms.py:141` `skipif(not (EXTERNAL/'Deroussi').is_dir())`。**合理但脆弱**：跳过的是全库唯一的"外部已发表解回放"证据，条件只检查 `Deroussi` 目录，而用例体读的是 `DeroussiNorre/*.txt` 和 `Deroussi/*.txt`；若只缺 `DeroussiNorre`，结果会是 `FileNotFoundError` 而非 skip。当前该目录存在，测试实际在跑（不是空转）。
2. `tests/maintenance/test_learned_policies.py:96` `pytest.importorskip('torch')`。**合理**：AGENTS 明确 PyTorch 在独立环境跑、主环境不重复安装；代价是主环境里这一条注意力策略端到端测试始终缺席，依赖外部环境纪律。
3. `tests/maintenance/test_learned_policies.py:147` 同类 `importorskip('torch')`。**技术上可避免**：该测试只做 NumPy 拼接/偏移断言，却因 `from ...attention_policy import StateDataset` 触发模块级 torch import 而整条跳过；把 `StateDataset` 拆到无 torch 依赖的模块即可在主环境跑。

"弱化检查"痕迹（未发现改检查器本身，问题都在测试写法）：

- 条件断言：`tests/fjsp/test_fjsp_algorithms.py:52-53`（只在 FEASIBLE 时断言 bound）。
- 宽 `except` 后 `continue/pass`：`tests/logistics/test_logistics_algorithms.py:49-53, 121-124, 197-202`。
- 冒烟式收尾：`tests/test_dynamic.py:165-167`（50 个到达事件只断言 `final_result is not None` + 最后一步过检查器）；`:117` 同类。
- 随机性：**全部固定种子**（`random.Random(5)`、`np.random.default_rng(0/7)`、`seed=` 参数、`torch.Generator().manual_seed(...)`），未发现未播种随机测试——这点是干净的。
- 用 `>=`/`<=` 的地方（如 `tests/test_dynamic.py:72-73` 的 `start >= 10`/`>= 4`）是正确方向的下界断言，不是弱化。

---

## 三、问题清单（按严重度）

### 严重

| # | 位置 | 问题 |
|---|---|---|
| S1 | `src/fjsp_lab/dynamic/feasibility.py:96-104` | `MACHINE_UNAVAILABLE` 只查 `current_time <= start`；未冻结记录若 `start < current_time` 且落在停机区间，直接漏检（反例 A，实测 `(True, [])`）。 |
| S2 | `src/fjsp_lab/dynamic/feasibility.py:93-95` | 只要 `(job,op)` 出现在调用方传入的 `frozen_records` 就 `continue`，跳过停机检查；谎报 frozen 可让未来记录在停机期间"合法"（反例 B，实测通过）。检查器没有"冻结记录必须已开始/已完成"或"与 state.current_time 一致"的校验。 |
| S3 | `src/fjsp_lab/dynamic/replay.py:75-80` | "不能改冻结工序时长""故障不能打在在制机器上"这两条最强约束**只在 replay 里**；`reschedule_from_state` / `check_dynamic_feasibility` 直接调用路径没有等价校验，也没有测试。 |

### 中

| # | 位置 | 问题 |
|---|---|---|
| M1 | `src/fjsp_lab/dynamic/state.py:192-195`；`replay.py:68-69` | 同刻事件按输入顺序应用，无规范序/优先级；实测 breakdown+repair 两种顺序得到两种停机窗口。多事件 JSON 文件顺序因此是隐式语义。 |
| M2 | `src/fjsp_lab/dynamic/state.py:91` | `MachineRepair` 无条件把可用时间设为 `event.time`，可缩短已宣布的 `repair_time`；没有与之前 breakdown 的一致性校验。`tests/test_dynamic.py:43` 把这个语义当规范固化了。 |
| M3 | `src/fjsp_lab/dynamic/feasibility.py:75,96` | 越界 job_id/machine_id 抛 `IndexError`（实测），而不是返回违规；公开检查器对坏输入不防御。 |
| M4 | `src/fjsp_lab/dynamic/feasibility.py:20-36` | 不校验 `result.instance == state.instance`（反例 C）；`replay.py:38-39` 补了，独立调用不补。 |
| M5 | `src/fjsp_lab/dynamic/state.py:31-45` | 默认全释放/全 0 释放时间，使 `JOB_BEFORE_RELEASE` 只能自证、无法对"到达"做外部验证（反例 D）。 |
| M6 | `src/fjsp_lab/dynamic/reschedule.py:94-96` | 改冻结工序时长 → 先接受事件、后由静态检查抛 `RuntimeError: PT_INSTANCE_MISMATCH`；应改为在 state/replay 边界拒绝（replay 已这么做）。`tests/test_dynamic.py:157-162` 固化了当前行为。 |
| M7 | `src/fjsp_lab/dynamic/snapshot.py:13` | `include_in_process=False` 无测试、无使用场景，会把在制工序当未开工重排且检查器不报错；属于危险 API 面。 |
| M8 | `src/fjsp_lab/dynamic/reschedule.py:125-161` | `_validate_released_jobs` / `_validate_frozen_records`（重复、越界、非前缀路由）零测试，重构时无回归保护。 |

### 轻

| # | 位置 | 问题 |
|---|---|---|
| L1 | `tests/test_dynamic.py` 全文件 | 没有一条断言具体 makespan/记录的数值回归；9 个 `event_files` 用例只过检查器。 |
| L2 | `src/fjsp_lab/dynamic/perturbation.py:81-82` | `_unique` 先于类型校验，seeds 含不可哈希值时抛 `TypeError` 而非 `ValueError`；`parse_protocol` 负例仅 4 个。 |
| L3 | `src/fjsp_lab/dynamic/events.py:157-178` | `job_arrival` 的 machine options 未拒绝重复机器（随后由 `FJSPInstance.from_jobs_array` 兜底）；错误信息不指向事件字段。 |
| L4 | `src/fjsp_lab/dynamic/feasibility.py:28-31` | 冻结记录按 key 建 dict，重复冻结记录被静默去重；重调度侧有重复校验（`reschedule.py:149-150`），检查器侧没有。 |
| L5 | `src/fjsp_lab/dynamic/reschedule.py:58-61` | `_validate_released_jobs` 已强制全部释放，`while any(...)` 上的 `released_job_ids` 过滤是冗余防御；不影响正确性。 |
| L6 | `tests/logistics/test_logistics_algorithms.py:141` | skip 守卫检查 `Deroussi`，用例体读 `DeroussiNorre`，目录部分缺失时行为是 error 不是 skip（当前目录完整，测试在跑）。 |

---

## 四、总体判断

这是一个质量明显高于平均水平的"可行性优先"测试体系：检查器逐违规码断言、算法输出统一过独立检查器、CP-SAT 与独立枚举对拍、特征向量有参考实现，228 例里约 71% 是具体约束断言，只有约 7% 冒烟；固定种子执行得干净，没有发现过宽的 `skip` 或内嵌 `pytest.skip`。Phase 2A 的 dynamic 层作为"最小动态底座"是能用的：重调度对停机、到达、时长变更的主路径正确，冻结语义清晰且确定，`FROZEN_RECORD_CHANGED` 可靠。但它本质上是"在输入自洽的前提下做检查"：动态检查器有两个真实绕过口（过去开工、谎报 frozen），到达时间没有外部真值，同刻事件顺序是未文档化的隐式语义，最强的动态约束（改冻结时长、故障不打断在制）只存在于 replay 一条路径。测试层面的主要风险不是"弱测试多"，而是**该模块缺少数值回归**和**若干负例完全缺失**——将来重调度规则或检查器改动，只有"仍可行"兜底，无法发现排序/语义漂移。
