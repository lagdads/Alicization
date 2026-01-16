文件职责：描述系统整体架构、层次划分与模块关系。
简明实现逻辑：以分层结构、数据流与接口契约说明实现方式。
输入输出：输入为架构需求与约束；输出为设计规范与模块接口。

# Alicization World 架构设计文档

## 1. 系统架构概览

Alicization World 采用分层架构设计，核心思想是"世界即记忆"。当前系统聚焦认知层与行为层，并保留世界层扩展位。

```
┌─────────────────────────────────────────┐
│        CLI / User Input (交互层)        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      Behavior Layer (行为层)            │
│  - Behavior Tree (目标分解/执行)        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│    Cognitive Layer (认知层)             │
│  - Memory System (记忆系统)             │
│  - Knowledge System (知识系统)          │
│  - Worldview Knowledge (世界观知识层)   │
│  - LLM Interface (AI 接口)              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│        Core Layer (核心层)               │
│  - Event Bus (事件总线)                  │
│  - Entity (实体系统)                     │
│  - WorldLoop (可选扩展)                  │
└─────────────────────────────────────────┘
```

### 模块结构文档

- Core: `docs/modules/core.md`
- Cognitive: `docs/modules/cognitive.md`
- Behavior: `docs/modules/behavior.md`
- World: `docs/modules/world.md`（设计阶段）
- Web: `docs/modules/web.md`

## 2. 模块逻辑说明

各模块的逻辑说明已拆分到独立文档中，Architecture 仅保留跨模块约束与全局视角：

- Core（双循环/事件总线/实体）：`docs/modules/core.md`
- Cognitive（记忆/知识/LLM 接口）：`docs/modules/cognitive.md`
- Behavior（行为树）：`docs/modules/behavior.md`
- World（环境/时间推进，设计阶段）：`docs/modules/world.md`
- Web（本地配置编辑与运行入口）：`docs/modules/web.md`

Web UI 属于本地开发工具链，不参与引擎运行时循环，主要用于配置编辑与启动 demo。

## 3. 数据流

### 3.1 认知循环数据流

```
用户输入
    ↓
检索相关记忆 (RAG)
    ↓
检索世界观片段
    ↓
LLM 生成目标
    ↓
LLM 生成动作计划
    ↓
行为树 tick 选择动作
    ↓
执行动作
    ↓
更新记忆
```
记忆模块内的数据流与算法细节见：`docs/modules/cognitive.md`

### 3.2 世界与行为 Tick 数据流

```
世界 tick
    ↓
采集感知 (PerceptionEvent)
    ↓
行为树 tick 选择动作
    ↓
世界执行动作并更新状态
    ↓
动作结果 (ActionResult) 写入记忆
    ↓
日终触发记忆整理 (Major GC)
```

- 世界为 2D 矩阵（中心点为 0, 0），每格为陆地/海洋
- 每天 24 个 tick，每个 tick NPC 执行 1 个动作
- 当前仅为设计流程，与实际运行链路解耦

## 4. 性能设计

### 4.1 频率控制

当前默认为 CLI 驱动，不启用 Fast/Slow Loop。记忆固化与衰减仍按交互节奏触发：

| 组件 | 频率 | 说明 |
|------|------|------|
| 对话输入 | 事件驱动 | 用户输入触发 |
| Minor GC | 事件驱动 | 缓冲区满/对话结束触发 |
| Major GC | 低频 | 日终或系统空闲时触发 |
| 世界 Tick | 24/天 | 设计值，尚未接入运行 |

### 4.2 异步设计

所有 I/O 操作使用异步：
- LLM API 调用：`async def`
- Vector DB 操作：`async def`
- 事件处理：`async def`

### 4.3 缓存策略

- **记忆检索**: 使用 Vector DB 的语义缓存
- **知识查询**: 内存缓存已解锁的知识节点
- **规划结果**: 缓存常见目标的规划结果

## 5. 扩展性设计

### 5.1 接口抽象

- **Vector DB**: 抽象接口，支持替换实现
- **LLM Interface**: 抽象接口，支持不同 LLM 提供商
- **Event Bus**: 支持多种事件类型扩展

### 5.2 组件化设计

- **Entity**: 通过组件组合实现不同功能
- **Action**: 可插拔的动作系统
- **Knowledge Node**: 可扩展的知识节点类型

接口契约已拆分至模块文档（Core/Cognitive/Behavior）。

## 6. 错误处理

### 6.1 分层错误处理

```
LLM 调用失败 → 重试机制 → 降级处理
Vector DB 错误 → 日志记录 → 回退到内存
行为失败 → 返回空动作 → 使用默认行为
```

### 6.2 优雅降级

- LLM 不可用时：使用规则引擎
- Vector DB 不可用时：使用内存存储
- 行为失败时：使用预定义行为

## 7. 监控与日志

### 7.1 关键指标

- CLI 交互次数
- LLM 调用次数和延迟
- 记忆数量变化
- 知识解锁进度

### 7.2 日志级别

- **DEBUG**: 详细的执行流程
- **INFO**: 重要状态变化
- **WARNING**: 降级操作
- **ERROR**: 错误和异常

## 8. 安全考虑

1. **LLM 输入验证**: 防止注入攻击
2. **资源限制**: 限制记忆数量和大小
3. **速率限制**: 控制 LLM API 调用频率
4. **数据隔离**: 不同 Agent 的记忆隔离
