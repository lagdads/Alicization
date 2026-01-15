文件职责：描述 Cognitive 模块的目录结构与文件职责。
简明实现逻辑：按子模块拆分记忆、知识与 LLM 接口。
输入输出：输入为认知层设计；输出为结构说明与职责清单。

# Cognitive 模块结构

```
src/cognitive/
├── __init__.py
├── llm_interface.py              # LLM 接口与 Stub 实现
├── memory/
│   ├── __init__.py
│   ├── store.py                  # MemoryManager 与 MemoryFragment
│   └── garbage_collector.py      # 衰减计算工具
└── knowledge/
    ├── __init__.py
    ├── tree.py                   # 知识树加载/查询/解锁
    ├── interceptor.py            # 锁定知识拦截器
    └── worldview.py              # 世界观知识加载与查询
```

## 关键职责

- `memory/store.py`: 记忆分层存储、固化、遗忘与强化检索
- `memory/garbage_collector.py`: 艾宾浩斯衰减公式封装
- `knowledge/tree.py`: 知识节点结构与访问控制
- `knowledge/interceptor.py`: 未解锁知识访问拦截
- `knowledge/worldview.py`: 世界观知识条目与关键词匹配
- `llm_interface.py`: LLM 抽象接口与默认 Stub 实现

## 核心逻辑说明

### 记忆系统：分层存储 (MemoryManager)

三层存储模型：

```
新感知输入
    ↓
Sensory Buffer (Deque，固定容量滑动窗口)
    ↓  (触发：窗口满/对话结束/强制)
Consolidation / Minor GC
    ↓
  ├─ importance_score < promotion_threshold → 丢弃
  └─ importance_score >= promotion_threshold → Episodic Store (Vector DB)
                                    ↓
                         Ebbinghaus Decay / Major GC (低频)
                                    ↓
                        current_strength < forget_threshold → 物理删除

Core Persona (Key-Value，免疫所有 GC)
```

#### 记忆持久化 (Long-term Storage)

- 存储位置：`data/memory/<safe-name>-<hash>.json`（每个 NPC 一个文件）
- 启动时加载快照，合并到 Core Persona 与 Episodic Store
- 记忆变更后自动写回，保障跨运行保留
- 人设文件内容会写入 Core Persona 的 `persona_profile`，作为长效记忆的一部分

#### 算法一：记忆固化 (Consolidation / Minor GC)

- 触发：感知缓冲区满、或对话结束/显式 flush
- 步骤：
  - 汇总缓冲区内容
  - 调用 LLM 摘要与重要性评分
  - 低于阈值丢弃；否则写入情节记忆库并设置满强度

#### 算法二：艾宾浩斯遗忘 (Ebbinghaus Decay / Major GC)

- 触发：低频周期性触发（例如“日终”或系统空闲）
- 公式：
  - `Strength_new = Strength_old * e^(-decay_rate * dt)`
  - `dt = now - last_accessed_at`（或与上次 decay 基线取较晚者）
- 修剪：`current_strength < forget_threshold` 则物理删除

#### 算法三：检索与强化 (Retrieval & Reinforcement)

- 输入：query（环境/玩家文本）
- 排序：相似度（relevance）与强度（strength）加权排序
- 强化：对返回给 LLM 的片段：
  - 更新 `last_accessed_at = now`
  - 提升 `current_strength`（例如恢复到 100 或增加固定值）

#### 记忆更新流程（数据流视角）

```
动作执行结果
    ↓
add_sensory_input(content, created_at)
    ↓
Sensory Buffer
    ↓
Consolidation / Minor GC (对话结束或缓冲区满)
    ↓
LLM 摘要和评分
    ↓
评分 >= promotion_threshold → Episodic Store (Vector DB)
    ↓
持久化写盘（Long-term Snapshot）
    ↓
定期 Major GC (遗忘曲线)
```

### 知识系统：树形访问控制 (KnowledgeBase)

```
Knowledge Tree (JSON)
    ↓
query(topic)
  ├─ Locked → interceptor 返回拦截提示 / 或 None
  └─ Unlocked → 返回 content

learn(topic)
  ├─ 前置未满足 → False
  └─ 前置满足 → 解锁并返回 True
```

### 世界观知识层 (WorldviewKnowledge)

```
Worldview JSON
    ↓
match_entry(text)
    ↓
返回匹配条目或 summary
```

### 接口契约

#### Vector DB Interface

```
add(fragment: MemoryFragment) -> UUID
delete(fragment_id: UUID) -> None
list_all() -> List[MemoryFragment]
search(query: str, top_k: int) -> List[MemoryFragment]
```

#### LLM Interface

```
summarize_and_score(memory: str) -> Tuple[str, float]
generate_intent(context: dict, memories: List[str]) -> str
rag_query(query: str, memories: List[str]) -> str
```

### LLM 分组配置

LLM 分为三类用途：

- `embed_api`: 负责向量嵌入（RAG/检索）
- `fast_api`: 负责轻量逻辑（摘要/评分等）
- `advanced_api`: 负责关键决策（例如下一步指令）

配置文件示例：`data/llm_config.json`

模块路由可配置 `routing`，以决定不同模块使用 fast/advanced：

```
"routing": {
  "default": {
    "summarize_and_score": "fast",
    "generate_intent": "advanced"
  },
  "memory": {
    "summarize_and_score": "fast"
  },
  "behavior": {
    "generate_intent": "advanced"
  }
}
```

说明：

- `routing.<module>.<task>` 目前支持的 task：`summarize_and_score`、`generate_intent`
- `rag_query` 默认由 `embed_api` 驱动的相似度排序实现，不参与 fast/advanced 路由
