文件职责：描述 Core 模块的目录结构与文件职责。
简明实现逻辑：按模块树列出文件并概述它们的作用。
输入输出：输入为 Core 模块设计；输出为结构说明与职责清单。

# Core 模块结构

```
src/core/
├── __init__.py     # 包标识
├── event_bus.py    # 异步事件总线（发布/订阅/等待）
├── loop.py         # 双循环调度器（fast/slow tick）
└── entity.py       # ECS 实体容器（组件管理）
```

## 关键职责

- `event_bus.py`: 提供异步事件发布、订阅与等待接口
- `loop.py`: 负责双循环调度与任务注册执行
- `entity.py`: 提供 ECS 实体与组件存取能力

## 核心逻辑说明

### 双循环架构 (Dual-Loop)

将高频计算与低频认知分离，避免 LLM/检索阻塞环境更新（当前默认 CLI 模式下不启用）：

```
Fast Loop (30Hz)
  - 环境更新 / 纯计算
        ↕
     EventBus
        ↕
Slow Loop (0.1Hz 或事件驱动)
  - 认知触发 / 记忆维护 / 状态更新
```

### 事件总线 (EventBus)

采用发布/订阅模式解耦模块：

```
Publisher -> EventBus -> Subscriber(s)
```

常见事件类型（可扩展，按需启用）：

- `environment_tick`: 环境时间推进/状态变化
- `memory_consolidated`: 记忆固化完成
- `knowledge_unlocked`: 知识解锁
- `goal_achieved`: 目标达成
- `state_changed`: Agent/世界状态变化

### 实体系统 (Entity)

ECS 变体基础容器：Entity 仅负责组件的存取管理，具体行为由组件/系统决定。

## 接口契约

### EventBus

```
publish(event_type: str, data: dict) -> None
subscribe(event_type: str, handler: Callable[[Event], Any]) -> None
wait_for_event(event_type: Optional[str], timeout: Optional[float]) -> Optional[Event]
```

### WorldLoop

```
register_fast_task(task: Callable[[], Awaitable[None]]) -> None
register_slow_task(task: Callable[[Optional[Event]], Awaitable[None]]) -> None
run() -> None
stop() -> None
```
