文件职责：描述 Behavior 模块的目录结构与文件职责。
简明实现逻辑：支持行为树执行与“LLM 动作队列”两种驱动方式。
输入输出：输入为状态/目标/动作计划；输出为 tick 级动作与执行结果。

# Behavior 模块结构

```
src/behavior/
├── __init__.py
├── behavior_tree.py  # 行为树定义与执行
└── actions.py        # 行为节点与具体动作
```

## 关键职责

- `behavior_tree.py`: 行为树构建、遍历与 tick 执行
- `actions.py`: 行走/收集/攻击/交谈等动作实现

## 核心逻辑说明

### 当前运行流程（与代码对齐）

当前 CLI 的 tick 行为主要由 `main.py` 的 `ChatAgent` 驱动：

- 队列为空时，调用 LLM 生成动作计划（函数签名字符串列表）
- 解析后写入队列并逐 tick 执行
- 由 `execute_action(action, state)` 直接更新 `state` 并返回 `ActionResult`
- `/act <goal>` 会调用同一套“动作计划生成→入队”流程
- `GOAPPlanner` 仍保留为备选规划器（主要用于 `act_once()` 的兜底分支）

`BehaviorTree` 实现仍保留为可选能力（目前未接入默认 CLI 的主流程）。

### 行为树执行流程（可选）

```
LLM 生成目标 (Goal)
    ↓
行为树构建 (Behavior Tree)
    ↓
每个 tick 选择 1 个动作 (Action)
```

执行要点：

- 行为树按 tick 运行，每次决策只输出 1 个动作
- 目标被拆解为可执行的 tick 级动作，直到目标完成或中断
- LLM 输出的动作指令需要进一步拆解为 tick 级子动作
- 当前实现会先解析 LLM 动作计划，拆解为 tick 级行动链后排入队列并逐 tick 执行
- 当行动队列为空时，每个 tick 会向 LLM 请求新的动作计划

### Tick 级动作

- 行走：在世界中移动坐标
- 扫描：扫描附近对象或标签
- 收集：尝试捡起可收集 Object
- 攻击：攻击其他 NPC
- 交谈：与其他 NPC 交谈，触发目标 NPC 生成对话回应
- 观察：观察附近 NPC 并返回状态

说明：LLM 只输出高层动作；上述 tick 级动作由行为层/世界层在执行阶段自动产生与结算。

### 动作拆解示例

LLM 输出（高层动作，函数签名）：

```
find_item(item_type="weapon")
```

行为层拆解逻辑：

- `find_item(...)` → 拆解为多个 tick（扫描/移动/拾取）：
  - tick1: scan_nearby(tag="weapon")（感知附近物体）
  - tick2: move(dx=1, dy=0)（向前探索）
  - tick3: scan_nearby(tag="weapon")
  - tick4: pickup(object_id="$weapon_id")
- 低层动作由行为层生成，LLM 仅输出高层动作
- 占位符（如 `$weapon_id`）由行为层在执行时从状态中解析

## 接口契约

### BehaviorTree

```
tick(current_state: dict, goal: dict) -> Optional[Action]
update_state(result: dict) -> None
```

### Action 计划解析

```
parse_action_plan(plan: dict, allowed_actions: Optional[dict] = None) -> List[Action]
expand_action_chain(actions: List[Action], state: dict) -> List[Action]
execute_action(action: Action, state: dict) -> ActionResult
```

## 说明

- 行为层负责校验 LLM 动作签名是否在允许列表内，并进行参数解析与拆解。
- CLI demo 会在 `respond` 与 `/act` 时生成动作计划，行动在 `/tick` 或自动 tick 中逐步执行。
