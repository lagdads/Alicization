文件职责：描述 Behavior 模块的目录结构与文件职责。
简明实现逻辑：包含 GOAP 规划与动作执行。
输入输出：输入为行为层设计；输出为结构说明与职责清单。

# Behavior 模块结构

```
src/behavior/
├── __init__.py
└── goap.py           # GOAP 规划器与动作执行
```

## 关键职责

- `goap.py`: 目标导向规划与动作序列生成

## 核心逻辑说明

### GOAP 规划流程

```
意图/目标 (Goal)
    ↓
当前状态 (State)
    ↓
GOAP Planner (搜索)
    ↓
动作序列 (Plan)
```

规划要点：

- 以动作 `preconditions` 与 `effects` 在状态空间中搜索
- 输出最小代价或最先可达的一条动作链（实现可扩展）

LLM 路由建议：

- 行为层的关键决策（例如“下一步指令/意图生成”）通常配置为使用 `advanced_api`
- 具体路由见 `data/llm_config.json` 的 `routing.behavior.*`

## 接口契约

### GOAPPlanner

```
plan(current_state: dict, goal: dict) -> List[Action]
execute_plan(plan: List[Action], current_state: Optional[dict]) -> bool
```
