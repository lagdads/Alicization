文件职责：项目对外说明与使用入口文档。
简明实现逻辑：介绍定位、结构、运行方式与约定。
输入输出：输入为读者需求；输出为项目概览与操作步骤。

# Alicization World (AgentOS Engine)

## 项目概述

**Alicization World** 是一个 AI Native 云端游戏引擎的 MVP 原型。核心理念是 **"世界即记忆"** —— 一个由 AI 生成、驱动，且拥有拟人化记忆衰减与成长机制的虚拟社会。

当前版本提供可运行的最小骨架实现，默认使用 OpenAI 配置并从 `.env` 读取模型与地址，Stub 作为备用实现。

### 核心特性

- 🧠 **认知内核**：基于艾宾浩斯遗忘曲线的记忆系统
- 🌳 **知识树系统**：技能树式的知识解锁机制
- 🎯 **目标导向行为**：GOAP (Goal-Oriented Action Planning) 规划系统
- 🌌 **世界观知识层**：可配置的世界观设定与检索
- 💬 **多 Agent CLI**：命令行多 AI 对话与行动指令

## 技术栈

- **语言**: Python 3.10+
- **并发**: asyncio (基于协程的高并发 Tick 调度)
- **数据存储**:
  - ChromaDB (或等效 Vector DB 接口) - 长期记忆存储
  - JSON/Dict - 知识树与世界观
- **架构**: 认知层/行为层分层设计 + 可选扩展

## 快速开始

```bash
# 克隆项目
git clone <repository-url>
cd Alicization

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动 CLI 对话
python main.py

# 运行脚本化演示（用于 Web UI 或快速检查）
python main.py --run-seconds 5
```

默认应用配置已指向 OpenAI 版本 LLM 配置，请先设置 `OPENAI_API_KEY`（或在 `.env` 配置各 provider 的 API key）：

```bash
export OPENAI_API_KEY="your_api_key"
python main.py --app-config-path config/app_config.toml
```

模型与源地址默认从 `.env` 的 `*_MODEL`/`*_WEB` 读取（如 `FAST_MODEL`、`FAST_WEB`）。
如需硬编码，可在 `config/llm_config.openai.toml` 中补充 `model`/`base_url` 并在 `config/app_config.toml` 指向该配置。

### Web UI (配置编辑与运行)

提供一个本地 Web UI，以设置面板方式编辑配置并尝试运行 `main.py`。
运行按钮会触发脚本化演示（非交互式 CLI）。

```bash
# 方式一：通过 main.py 启动 Web UI
python main.py --webui

# 方式二：直接启动 Web UI 服务
python web/server.py
```

浏览器访问：`http://127.0.0.1:8000`（可通过 `config/app_config.toml` 或命令行参数修改）

可编辑配置：应用配置、LLM 分组、默认 Persona、Knowledge Graph 节点。

### 运行参数（CLI 覆盖）

- `--app-config-path`：应用配置路径（默认 `config/app_config.toml`）
- `--run-seconds`：覆盖应用配置中的演示秒数
- `--memory-test`：覆盖应用配置，执行记忆测试
- `--auto-tick`：在 CLI 模式中启用自动 tick 循环
- `--tick-interval`：覆盖自动 tick 间隔秒数
- `--webui`：启动本地 Web UI（不运行 demo loop）
- `--webui-host`：覆盖 Web UI 监听地址
- `--webui-port`：覆盖 Web UI 监听端口

`config/app_config.toml` 支持 `auto_tick`、`tick_interval` 与 `max_ticks`，用于配置 CLI 自动 tick 的默认行为。
默认 `auto_tick = true`，运行后会进入自动 tick 循环（自动模式不接收命令行指令）。非交互环境下会跳过输入提示，避免 EOF 退出。
`max_ticks` 默认为 30，设置为 0 或负数表示不限制。
`mode = "webui"` 可让启动时默认进入 Web UI（等效 `--webui`）。

### CLI 使用速览

- `/list` 查看 AI 列表
- `/use <name>` 切换对话对象
- `/act [name] <goal>` 规划行动并加入队列
- `/tick` 进入下一 tick 并执行行动
- `/state [name]` 查看当前状态
- `/lore [name]` 查看世界观概要
- `@<name> <message>` 对指定 AI 说话

## 项目结构

```
.
├── src/                       # 核心代码
│   ├── core/                  # 引擎核心：双循环/事件/实体
│   ├── cognitive/             # 认知层：记忆/知识/LLM 接口
│   ├── behavior/              # 行为层：GOAP
│   └── world/                 # 世界层：暂缓使用（保留）
├── config/                    # 运行配置（app/llm/knowledge）
├── data/                      # 预设数据（世界观/人设/记忆）
├── docs/                      # 设计与开发文档
├── web/                       # 本地 Web UI（配置编辑与运行）
├── main.py                    # 启动入口
└── requirements.txt           # 依赖清单
```

## 数据目录

- `config/knowledge_graph.toml`: 初始知识树定义
- `data/world_lore.toml`: 世界观知识定义
- `config/llm_config.toml`: LLM 分组配置（stub 版本）
- `config/llm_config.openai.toml`: LLM 分组配置（OpenAI/兼容 API，从 `.env` 读取）
- `data/personas/*.toml`: Agent/NPC 人设与记忆参数

## 文档索引

- 架构总览：`docs/ARCHITECTURE.md`
- 开发规范：`docs/DEVELOPMENT.md`
- Core 模块结构：`docs/modules/core.md`
- Cognitive 模块结构：`docs/modules/cognitive.md`
- Behavior 模块结构：`docs/modules/behavior.md`
- World 模块结构：`docs/modules/world.md`（暂缓）
- Web 模块结构：`docs/modules/web.md`

## 核心模块设计

详细的模块逻辑说明已拆分到 `docs/modules/*.md`，此处仅保留概要与对齐实现的关键点。

### Module A: 认知内核 (The Cognitive Core)

#### Memory System (Tiered Storage)

**类**: `MemoryManager`

**逻辑**:
- 维护 `sensory_buffer`、`episodic_store` 与 `core_persona_store`
- **Minor GC**: `consolidate()` 汇总缓冲区，LLM 摘要并打分 (Importance 0-10)
  - < `promotion_threshold`：丢弃
  - >= `promotion_threshold`：存入情节记忆库，强度设为满值
- **Major GC (The Ebbinghaus Cycle)**: `apply_decay(current_time)` 更新强度
  - `Strength_new = Strength_old * e^(-decay_rate * dt)`
  - 若 `current_strength < forget_threshold`，执行物理删除
- **检索强化**: `retrieve_and_reinforce()` 按相似度+强度排序并强化

#### Knowledge System (Tree-Based)

**类**: `KnowledgeBase`

**逻辑**:
- 加载 JSON 定义的技能树 (Nodes: ID, Parent, IsLocked, Content)
- `query(topic)` 方法：
  - 如果节点是 `Locked` 状态，返回 `None` 或拦截信号
  - 如果是 `Unlocked`，返回 `Content`
- `learn(topic)` 方法：解锁节点

### Module B: 行为驱动 (Behavior Engine)

#### GOAP (Goal-Oriented Action Planning)

- 实现简单的规划器
- 给定 `Current_State` (e.g., `has_wood=False`) 和 `Goal` (e.g., `make_fire`)
- 反向推导 `Action` 序列

#### Integration (The Brain-Body Link)

- Cognitive Core 产出 **意图 (Intent)** (e.g., "我想炸掉这个门")
- GOAP 将意图转化为 **动作链** (e.g., `Learn_Gunpowder -> Craft_Bomb -> Use_Bomb`)

### Module C: CLI 交互 (Multi-Agent Console)

- 提供多 Agent 对话与指令输入
- `/act` 规划行动并加入队列
- `/tick` 执行下一步行动
- `/state` 展示当前状态
- `/lore` 展示世界观概要

## 实现说明

- 向量库默认实现为内存检索（可替换为 ChromaDB 适配器）
- LLM 接口提供 Stub 备用实现（可替换为真实 LLM 服务）
- 人设记忆配置键：`promotion_threshold`、`decay_rate`、`forget_threshold`、`max_strength`（见 `data/personas/default.toml`）
- LLM 分组配置键：`providers.embed_api`、`providers.fast_api`、`providers.advanced_api`（见 `config/llm_config.toml`）
- 模块路由配置：`routing.<module>.<task>`，用于指定模块使用 fast/advanced（见 `config/llm_config.toml`）

## 架构设计原则

1. **分离关注点**: 认知层与行为层清晰分离
2. **事件驱动**: 使用事件总线实现模块间解耦
3. **异步优先**: 所有 I/O 操作使用 asyncio
4. **可扩展性**: 基于 ECS 架构，易于添加新组件

## 开发路线图

- [ ] Phase 1: 核心引擎框架（Loop、Event Bus、Entity）
- [ ] Phase 2: 认知内核（Memory System、Knowledge System）
- [ ] Phase 3: 行为驱动（GOAP、Behavior Tree）
- [ ] Phase 4: 世界层（暂停）
- [ ] Phase 5: 集成测试与优化
