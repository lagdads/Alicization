文件职责：描述 Behavior 模块的目录结构与文件职责。
简明实现逻辑：使用行为树执行每个 tick 的动作。
输入输出：输入为行为层设计；输出为结构说明与职责清单。

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

### 行为树执行流程

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

### Tick 级动作

- 行走：在世界中移动坐标
- 收集：尝试捡起可收集 Object
- 攻击：攻击其他 NPC
- 交谈：与其他 NPC 交谈，调用 LLM

### 动作拆解示例

LLM 输出（高层动作，函数签名）：

```
find_item(item_type="weapon")
pickup(object_id="$weapon_id")
```

行为层拆解逻辑：

- `find_item(...)` → 若不在视野内，拆解为多个 tick：
  - tick1..n: move_to(x=..., y=...)（接近目标区域）
  - tick n+1: scan_nearby(tag="weapon")（感知附近物体）
- `pickup(...)` → tick 执行收集动作（受持有权限限制）

## 接口契约

### BehaviorTree

```
tick(current_state: dict, goal: dict) -> Optional[Action]
update_state(result: dict) -> None
```

## 说明

- 当前仅定义行为层设计与接口语义，不与实际应用运行流程链接。
- 行为层负责校验 LLM 动作签名是否在允许列表内，并进行参数解析与拆解。
