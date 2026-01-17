文件职责：说明开发规范、目录结构与实现优先级。
简明实现逻辑：给出模块规格、接口约定与实践步骤。
输入输出：输入为开发目标与约束；输出为实施指南与约定。

# Alicization World 开发文档

## 1. 项目定义与角色

### Project Name
**Alicization World (AgentOS Engine)**

### Role
你是本项目的首席后端架构师。你的目标是构建一个 AI Native 云端游戏引擎的 MVP 原型。

### Core Philosophy
**"世界即记忆"**。这是一个由 AI 生成、驱动，且拥有拟人化记忆衰减与成长机制的虚拟社会。

## 2. 技术栈约束

### Language
- Python 3.10+

### Concurrency
- asyncio (基于协程的高并发 Tick 调度)

### Data Store
- **ChromaDB** (or equivalent Vector DB interface) for Long-Term Memory
- **TOML/JSON** for Knowledge Tree & Worldview

### Architecture
- ECS (Entity-Component-System) 变体
- 双循环架构 (Dual-Loop，当前默认未启用)

## 3. 完整目录结构设计

```
仓库根目录 (Alicization):
├── src/
│   ├── core/
│   ├── cognitive/
│   ├── behavior/
│   └── world/                 # 世界层（环境/规则）
├── config/
├── data/
├── docs/
├── web/
└── main.py

逻辑结构:
alicization_world/
├── src/
│   ├── core/                  # 引擎核心
│   │   ├── loop.py            # Tick调度器 (Fast/Slow Loop，可选)
│   │   ├── event_bus.py       # 事件总线
│   │   └── entity.py          # 基础实体定义
│   ├── cognitive/             # 认知层 (你的核心创新)
│   │   ├── memory/
│   │   │   ├── garbage_collector.py # 艾宾浩斯GC算法
│   │   │   └── store.py       # 分代记忆库
│   │   ├── knowledge/
│   │   │   ├── tree.py        # 知识树结构
│   │   │   ├── interceptor.py # 知识拦截器
│   │   │   └── worldview.py   # 世界观知识
│   │   └── llm_interface.py   # RAG与Prompt构建
│   ├── behavior/              # 行为层 (原始文档要求)
│   │   ├── goap.py            # 目标导向规划
│   └── world/                 # 世界层（环境/规则）
│       ├── environment.py     # 坐标、时间、物理规则
│       └── survival_war.py    # 生存战争会话与规则
├── config/                    # 运行配置（TOML）
│   ├── app_config.toml        # 应用配置入口
│   ├── llm_config.toml        # LLM 分组配置
│   └── knowledge_graph.toml   # 知识树配置
├── data/                      # 预设数据
│   └── worlds/                # 多世界观目录
│       └── <world_id>/        # 单一世界数据
│           ├── world_lore.toml # 世界观知识
│           ├── world_config.toml # 世界配置
│           └── personas/      # NPC 人设配置（TOML）
├── web/                       # 本地 Web UI
│   ├── server.py              # 简易 Web 服务与 API
│   ├── index.html             # Web UI 页面
│   ├── app.js                 # 前端逻辑
│   └── styles.css             # 页面样式
└── main.py                    # 启动入口
```

### 3.1 模块结构文档

- Core: `docs/modules/core.md`
- Cognitive: `docs/modules/cognitive.md`
- Behavior: `docs/modules/behavior.md`
- World: `docs/modules/world.md`
- Web: `docs/modules/web.md`

### 3.2 世界选择与配置

- `config/app_config.toml` 可指定 `world_id` 与 `worlds_dir`
- 运行时可通过命令行覆盖：`--world-id`、`--worlds-dir`、`--world-config-path`
- 世界内配置存放于 `data/worlds/<world_id>/world_config.toml`

### 3.3 实现约定

- `src/` 为顶层包，运行 `python main.py` 时可直接导入 `src.*`
- 记忆向量库默认使用 ChromaDB 持久化存储（也提供内存实现用于测试/替换）
- LLM 接口提供 Stub 备用实现，可替换为真实 LLM 服务
- **注释要求**：每个函数与类必须有注释（Python 使用 docstring；JS 使用 JSDoc），在新增或修改时同步补全。

### 3.4 注释规范

- **覆盖范围**：所有函数、类都必须有注释；新增/修改代码需同步补齐。
- **语言**：统一使用中文注释。
- **形式**：
  - Python：使用三引号 docstring，置于函数/类定义后第一行。
  - JavaScript：使用 JSDoc，置于函数/类定义上一行。
- **内容要求**：说明“做什么/输入/输出/副作用”，保持简洁，不写显而易见的实现细节。

## 4. 核心模块详细规格

### Module A: 认知内核 (The Cognitive Core)

这是系统的核心，必须实现用户定义的"成长与遗忘"逻辑。

#### Memory System (Tiered Storage)

**Class**: `MemoryManager`

**位置**: `src/cognitive/memory/store.py`

**数据结构**:
```python
class MemoryManager:
    sensory_buffer: Deque[SensoryRecord]          # 感知缓冲区
    episodic_store: VectorDBInterface             # 情节记忆库
    core_persona_store: KeyValueStoreInterface    # 核心人格区
```

**核心方法**:

1. **`add_sensory_input(content: str, created_at: float, force_consolidate: bool = False)`**
   - 将感知输入写入 `sensory_buffer`
   - 缓冲区满或强制触发时执行记忆固化

2. **`consolidate() -> Optional[MemoryFragment]`** (Minor GC)
   - 汇总缓冲区内容，调用 LLM 进行摘要与重要性评分
   - 若 `importance_score < promotion_threshold` 则丢弃
   - 否则写入 `episodic_store`，初始强度为满值

3. **`apply_decay(current_time: float) -> None`** (Major GC)
   - 遍历情节记忆库
   - 应用艾宾浩斯遗忘公式：
     ```
     Strength_new = Strength_old * e^(-decay_rate * dt)
     ```
   - 若 `current_strength < forget_threshold` 则物理删除

4. **`retrieve_and_reinforce(query: str, top_k: int = 5) -> List[MemoryFragment]`**
   - 结合相似度与强度进行加权排序
   - 返回 top_k 记忆并更新 `last_accessed_at` 与 `current_strength`

**辅助类**:
```python
@dataclass
class MemoryFragment:
    id: UUID
    content: str
    created_at: float
    importance_score: float  # 0-10
    current_strength: float  # 0-100
    last_accessed_at: float
    embedding: List[float]
```

#### Knowledge System (Tree-Based)

**Class**: `KnowledgeBase`

**位置**: `src/cognitive/knowledge/tree.py`

**数据结构**:
```python
class KnowledgeBase:
    tree: Dict[str, KnowledgeNode]  # 知识树节点字典
```

**节点结构** (TOML/JSON):
```toml
id = "node_id"
parent = "parent_id"
is_locked = true
content = "知识内容或技能描述"
prerequisites = ["node_id_1", "node_id_2"]
```

**核心方法**:

1. **`load_from_json(filepath: str) -> None`**
   - 从 TOML/JSON 文件加载知识树结构

2. **`query(topic: str) -> Optional[str]`**
   - 根据 topic 查找对应的知识节点
   - 如果节点是 `Locked` 状态：
     - 返回 `None`
     - 或触发拦截信号（通过 `interceptor.py`）
   - 如果节点是 `Unlocked` 状态：
     - 返回节点的 `Content`
     - 更新节点的访问时间（用于遗忘计算）

3. **`learn(topic: str) -> bool`**
   - 解锁指定的知识节点
   - 检查前置条件（prerequisites）是否满足
   - 如果满足，将节点标记为 `is_locked = False`
   - 返回是否成功解锁

**拦截器** (`interceptor.py`):
```python
class KnowledgeInterceptor:
    """当尝试访问锁定知识时，触发拦截逻辑"""
    def intercept(self, node_id: str, context: dict) -> str:
        # 返回拦截消息，例如："你还没有学会这个技能"
        pass
```

### Module B: 行为驱动 (Behavior Engine)

#### GOAP (Goal-Oriented Action Planning)

**Class**: `GOAPPlanner`

**位置**: `src/behavior/goap.py`

**数据结构**:
```python
class GOAPPlanner:
    actions: List[Action]      # 可用动作列表
    current_state: Dict[str, Any]  # 当前世界状态
    goal: Dict[str, Any]       # 目标状态
```

**核心方法**:

1. **`plan(current_state: Dict, goal: Dict) -> List[Action]`**
   - 使用反向搜索算法（从目标状态反向推导）
   - 返回动作序列（Action Chain）
   - 如果无法达成目标，返回空列表

2. **`execute_plan(plan: List[Action]) -> bool`**
   - 按顺序执行动作序列
   - 每个动作执行后更新 `current_state`
   - 返回是否成功完成所有动作

**Action 结构**:
```python
@dataclass
class Action:
    name: str
    preconditions: Dict[str, Any]  # 前置条件
    effects: Dict[str, Any]        # 执行效果
    cost: float                    # 动作成本
```

**示例**:
```python
# 目标：make_fire
goal = {"has_fire": True}

# 当前状态：has_wood=False
current_state = {"has_wood": False, "has_fire": False}

# 规划结果：
plan = [
    Action("gather_wood", {}, {"has_wood": True}, cost=1.0),
    Action("make_fire", {"has_wood": True}, {"has_fire": True}, cost=2.0)
]
```

### Module C: 引擎调度 (Engine Core)

#### WorldLoop

**Class**: `WorldLoop`

**位置**: `src/core/loop.py`

**架构**: 双循环架构 (Dual-Loop)

**Fast Loop (Environment Tick - 30Hz, 可选)**:
- 频率: 30 FPS (每 33ms 一次)
- 职责:
  - 更新 Agent 位置
  - 更新冷却时间
  - 物理计算
  - **不调用 LLM**（纯计算）

**Slow Loop (Cognitive Tick - Event-Driven / 0.1Hz, 可选)**:
- 频率: 0.1 Hz (每 10 秒一次) 或事件驱动
- 触发条件:
  - Event Bus 收到新消息
  - Agent 内部状态 (Utility) 发生变化
- 职责:
  - 触发 LLM 思考
  - 执行记忆 GC
  - 更新认知状态

**实现示例**:
```python
class WorldLoop:
    async def fast_loop(self):
        """环境 Tick (30Hz)"""
        while True:
            await asyncio.sleep(1/30)  # 33ms
            # 更新位置、冷却时间等
            
    async def slow_loop(self):
        """认知 Tick (事件驱动)"""
        while True:
            # 等待事件或定时触发
            await self.event_bus.wait_for_event()
            # 或
            await asyncio.sleep(10)  # 10秒
            # 触发 LLM 思考
            
    async def run(self):
        """启动双循环"""
        await asyncio.gather(
            self.fast_loop(),
            self.slow_loop()
        )
```

#### Event Bus

**Class**: `EventBus`

**位置**: `src/core/event_bus.py`

**功能**:
- 发布/订阅模式
- 解耦模块间通信
- 支持异步事件处理

**核心方法**:
```python
class EventBus:
    async def publish(self, event_type: str, data: dict) -> None
    async def subscribe(self, event_type: str, handler: Callable) -> None
    async def wait_for_event(
        self, event_type: Optional[str] = None, timeout: Optional[float] = None
    ) -> Optional[Event]
```

#### Entity

**Class**: `Entity`

**位置**: `src/core/entity.py`

**ECS 架构基础**:
```python
class Entity:
    id: str
    components: Dict[str, Component]  # 组件字典
```

## 5. 数据格式规范

### Knowledge Graph TOML 格式

**文件**: `config/knowledge_graph.toml`

```toml
[[nodes]]
id = "basic_crafting"
is_locked = false
content = "基础制作技能：可以制作简单的工具和物品"
prerequisites = []

[[nodes]]
id = "gunpowder"
parent = "basic_crafting"
is_locked = true
content = "火药制作：需要硫磺、木炭和硝石"
prerequisites = ["basic_crafting"]
```

### Persona TOML 格式

**文件**: `data/worlds/<world_id>/personas/<persona_name>.toml`（或回退到 `data/personas/<persona_name>.toml`）

```toml
name = "Alice"
description = "一个好奇的冒险者"
worldview_visibility = "npc"
initial_knowledge = ["basic_crafting"]

[memory_config]
promotion_threshold = 4.0
decay_rate = 0.1
forget_threshold = 15.0
max_strength = 100.0
```

### LLM Config TOML 格式

**文件**: `config/llm_config.toml`

```toml
[providers.embed_api]
type = "stub"
embedding_dim = 12

[providers.fast_api]
type = "stub"

[providers.advanced_api]
type = "stub"

[routing.default]
summarize_and_score = "fast"
generate_intent = "advanced"
generate_reply = "advanced"
generate_actions = "advanced"

[routing.memory]
summarize_and_score = "fast"

[routing.behavior]
generate_intent = "advanced"
generate_reply = "advanced"
generate_actions = "advanced"
```

默认应用配置已指向 `config/llm_config.openai.toml`，并需要设置环境变量（模型与源地址从 `.env` 读取）：

```bash
export OPENAI_API_KEY="your_api_key"
```

配置示例（节选，TOML）：

```toml
[providers.embed_api]
type = "openai"
model_env = "EMBEDDING_MODEL"
api_key_env = "EMBEDDING_API_KEY"
base_url_env = "EMBEDDING_WEB"
```

## 6. LLM 接口规范

**Class**: `LLMInterface`

**位置**: `src/cognitive/llm_interface.py`

**核心方法**:

1. **`summarize_and_score(memory: str) -> Tuple[str, float]`**
   - 输入: 原始记忆内容
   - 输出: (摘要, 重要性评分 0-10)

2. **`generate_intent(context: dict, memories: List[str]) -> str`**
   - 输入: 当前上下文和检索到的记忆
   - 输出: 意图描述（自然语言）

3. **`generate_reply(context: dict, memories: List[str]) -> str`**
   - 输入: 当前上下文和检索到的记忆
   - 输出: NPC 对话回应文本

4. **`rag_query(query: str, memories: List[str]) -> str`**
   - 输入: 查询和记忆列表
   - 输出: 基于 RAG 的回答

## 7. 开发优先级

### Phase 1: 核心框架
1. Entity 系统
2. Event Bus
3. WorldLoop 双循环架构

### Phase 2: 认知内核
1. Memory System (Minor GC)
2. Knowledge System (基础查询)
3. LLM Interface (基础接口)

### Phase 3: 行为驱动
1. GOAP Planner (简单规划)
2. Behavior Tree (基础节点)

### Phase 4: 集成与优化
1. Major GC (艾宾浩斯遗忘)
2. 知识拦截器
3. 完整集成测试

## 8. 测试策略

- **单元测试**: 每个模块独立测试
- **集成测试**: 模块间交互测试
- **性能测试**: Tick 频率、内存使用

## 9. 注意事项

1. **异步优先**: 网络/LLM 调用使用 `async/await`；文件读写目前为同步 I/O
2. **错误处理**: 完善的异常处理和日志记录
3. **可配置性**: 关键参数（衰减率、阈值等）应可配置
4. **扩展性**: 基于接口编程，便于替换实现（如 Vector DB）
5. **文件头说明**: 每个文件开头用中文写明文件职责、简明实现逻辑、输入输出
6. **LLM 分组与路由**: 关键决策优先使用 `advanced_api`，轻量任务使用 `fast_api`，RAG/相似度使用 `embed_api`；按模块路由在 `config/llm_config.toml` 的 `routing` 配置

## 10. 运行参数与配置

`main.py` 支持以下参数（均为可选），主要通过应用配置文件驱动：

- `--app-config-path`: 应用配置路径（默认 `config/app_config.toml`）
- `--run-seconds`: 覆盖应用配置中的示例运行时长
- `--memory-test`: 覆盖应用配置，执行记忆测试
- `--auto-tick`: 在 CLI 模式中启用自动 tick 循环
- `--tick-interval`: 覆盖自动 tick 间隔秒数
- `--max-ticks`: 覆盖自动 tick 最大次数（0 表示不限制）
- `--webui`: 启动本地 Web UI（不运行 demo loop）
- `--webui-host`: 覆盖 Web UI 监听地址
- `--webui-port`: 覆盖 Web UI 监听端口
- `--world-id`: 选择世界目录（对应 `data/worlds/<world_id>`）
- `--worlds-dir`: 覆盖世界目录根路径
- `--world-config-path`: 覆盖世界配置文件路径

应用配置 `config/app_config.toml` 可设置 `auto_tick`、`tick_interval` 与 `max_ticks` 作为默认自动 tick 行为。
默认 `auto_tick = true`，CLI 启动后会进入自动 tick 循环（自动模式不接收命令行指令）。非交互环境下会跳过输入提示。
`max_ticks` 默认为 30，设置为 0 或负数表示不限制。
`mode = "webui"` 可让启动时默认进入 Web UI（等效 `--webui`）。

运行结束后会自动写入一次“运行日志（控制台输出副本）”到 `data/worlds/<world_id>/saves/`（或回退到 `data/saves/`）。

### 10.1 Web UI 使用说明

- 启动：`python main.py --webui`
- 访问：`http://127.0.0.1:8000`
- 说明：
  - Web UI 以设置面板方式编辑白名单内的配置
  - 运行入口使用 `main.py --run-seconds` 并有时间/输出限制
