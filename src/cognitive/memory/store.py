"""文件职责：短期/情节/核心人格记忆的管理与检索。
简明实现逻辑：缓冲输入→LLM 摘要打分→晋升到情节记忆→衰减/检索强化。
输入输出：输入为感知内容与查询；输出为 MemoryFragment 列表与强化结果。"""

import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Protocol, Tuple

from src.cognitive.memory.garbage_collector import apply_ebbinghaus_decay
from src.cognitive.memory.embedding import cosine_similarity, embed_text
from src.cognitive.llm_interface import EmbeddingInterface, LLMInterface


@dataclass
class MemoryFragment:
    """情节记忆片段数据结构。"""

    id: uuid.UUID
    content: str
    created_at: float
    importance_score: float
    current_strength: float
    last_accessed_at: float
    embedding: List[float]


@dataclass
class SensoryRecord:
    """短期感知记录。"""

    content: str
    created_at: float


class VectorDBInterface(Protocol):
    """向量数据库接口协议。"""

    def add(self, fragment: MemoryFragment) -> uuid.UUID:
        """新增记忆片段并返回 ID。"""
        ...

    def delete(self, fragment_id: uuid.UUID) -> None:
        """删除指定片段。"""
        ...

    def list_all(self) -> List[MemoryFragment]:
        """列出全部片段。"""
        ...

    def search(self, query: str, top_k: int) -> List[MemoryFragment]:
        """按查询内容检索片段。"""
        ...


class KeyValueStoreInterface(Protocol):
    """键值存储接口协议。"""

    def set(self, key: str, value: str) -> None:
        """设置键值对。"""
        ...

    def get(self, key: str) -> Optional[str]:
        """获取指定键值。"""
        ...

    def items(self) -> List[Tuple[str, str]]:
        """列出所有键值对。"""
        ...


class InMemoryVectorStore:
    """内存向量存储实现。"""

    def __init__(self, embedding_dim: int = 12) -> None:
        """初始化内存向量存储。"""
        self._entries: Dict[str, MemoryFragment] = {}
        self.embedding_dim = embedding_dim

    def add(self, fragment: MemoryFragment) -> uuid.UUID:
        """存储记忆片段。"""
        key = str(fragment.id)
        self._entries[key] = fragment
        return fragment.id

    def delete(self, fragment_id: uuid.UUID) -> None:
        """删除指定片段。"""
        self._entries.pop(str(fragment_id), None)

    def list_all(self) -> List[MemoryFragment]:
        """列出全部片段。"""
        return list(self._entries.values())

    def search(self, query: str, top_k: int) -> List[MemoryFragment]:
        """按语义相似度检索片段。"""
        query_embedding = embed_text(query, self.embedding_dim)
        scored: List[Tuple[float, MemoryFragment]] = []
        for fragment in self._entries.values():
            similarity = cosine_similarity(query_embedding, fragment.embedding)
            scored.append((similarity, fragment))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [fragment for score, fragment in scored[:top_k] if score > 0]


class InMemoryKeyValueStore:
    """内存键值存储实现。"""

    def __init__(self) -> None:
        """初始化内存键值存储。"""
        self._data: Dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        """设置键值对。"""
        self._data[key] = value

    def get(self, key: str) -> Optional[str]:
        """获取指定键的值。"""
        return self._data.get(key)

    def items(self) -> List[Tuple[str, str]]:
        """列出所有键值对。"""
        return list(self._data.items())


def _coerce_str_map(raw: Any) -> Dict[str, str]:
    """将任意映射转换为字符串键值对。"""
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _normalize_embedding(
    raw: Any,
    content: str,
    embedding_dim: int,
    embedder: Optional[Callable[[str], List[float]]] = None,
) -> List[float]:
    """校准或回退 embedding 向量维度。"""
    if not isinstance(raw, list) or len(raw) != embedding_dim:
        if embedder is not None:
            return embedder(content)
        return embed_text(content, embedding_dim)
    try:
        return [float(value) for value in raw]
    except (TypeError, ValueError):
        if embedder is not None:
            return embedder(content)
        return embed_text(content, embedding_dim)


def _fragment_to_dict(fragment: MemoryFragment) -> Dict[str, Any]:
    """将记忆片段转换为可序列化字典。"""
    return {
        "id": str(fragment.id),
        "content": fragment.content,
        "created_at": fragment.created_at,
        "importance_score": fragment.importance_score,
        "current_strength": fragment.current_strength,
        "last_accessed_at": fragment.last_accessed_at,
        "embedding": fragment.embedding,
    }


def _fragment_from_dict(
    data: Dict[str, Any],
    embedding_dim: int,
    embedder: Optional[Callable[[str], List[float]]] = None,
) -> MemoryFragment:
    """从字典构建记忆片段。"""
    raw_id = data.get("id")
    try:
        fragment_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        fragment_id = uuid.uuid4()
    content = str(data.get("content", ""))
    created_at = float(data.get("created_at", time.time()))
    importance_score = float(data.get("importance_score", 0.0))
    current_strength = float(data.get("current_strength", 0.0))
    last_accessed_at = float(data.get("last_accessed_at", created_at))
    embedding = _normalize_embedding(
        data.get("embedding"), content, embedding_dim, embedder
    )
    return MemoryFragment(
        id=fragment_id,
        content=content,
        created_at=created_at,
        importance_score=importance_score,
        current_strength=current_strength,
        last_accessed_at=last_accessed_at,
        embedding=embedding,
    )


def _load_memory_snapshot(
    path: Path,
    embedding_dim: int,
    embedder: Optional[Callable[[str], List[float]]] = None,
) -> Dict[str, Any]:
    """从磁盘加载记忆快照。"""
    logger = logging.getLogger("alicization.memory")
    if not path.exists():
        return {"core_persona": {}, "episodic": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load memory file %s: %s", path, exc)
        return {"core_persona": {}, "episodic": []}
    core_persona = _coerce_str_map(data.get("core_persona", {}))
    episodic: List[MemoryFragment] = []
    for item in data.get("episodic", []) or []:
        if not isinstance(item, dict):
            continue
        episodic.append(_fragment_from_dict(item, embedding_dim, embedder))
    return {"core_persona": core_persona, "episodic": episodic}


def _save_memory_snapshot(
    path: Path,
    core_persona: Dict[str, str],
    episodic: List[MemoryFragment],
) -> None:
    """将记忆快照写入磁盘。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": 1,
        "saved_at": time.time(),
        "core_persona": dict(sorted(core_persona.items())),
        "episodic": [
            _fragment_to_dict(fragment)
            for fragment in sorted(episodic, key=lambda frag: frag.created_at)
        ],
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


class MemoryManager:
    """记忆管理器，维护缓冲区、检索与衰减。"""

    def __init__(
        self,
        llm_interface: LLMInterface,
        embedding_api: Optional[EmbeddingInterface] = None,
        vector_store: Optional[VectorDBInterface] = None,
        core_persona_store: Optional[KeyValueStoreInterface] = None,
        memory_path: Optional[str | Path] = None,
        buffer_limit: int = 20,
        promotion_threshold: float = 4.0,
        decay_rate: float = 0.1,
        forget_threshold: float = 15.0,
        max_strength: float = 100.0,
        embedding_dim: int = 12,
        weight_relevance: float = 0.7,
        weight_strength: float = 0.3,
        reinforce_strength: float = 100.0,
    ) -> None:
        """初始化记忆管理器与配置参数。"""
        self.sensory_buffer: Deque[SensoryRecord] = deque()
        self.episodic_store: VectorDBInterface = vector_store or InMemoryVectorStore(
            embedding_dim=embedding_dim
        )
        self.core_persona_store = core_persona_store or InMemoryKeyValueStore()
        self.llm_interface = llm_interface
        self.embedding_api = embedding_api
        self.buffer_limit = buffer_limit
        self.promotion_threshold = promotion_threshold
        self.decay_rate = decay_rate
        self.forget_threshold = forget_threshold
        self.max_strength = max_strength
        self.embedding_dim = embedding_dim
        self.weight_relevance = weight_relevance
        self.weight_strength = weight_strength
        self.reinforce_strength = reinforce_strength
        self._last_decay_at: Dict[str, float] = {}
        self._memory_path = Path(memory_path) if memory_path else None
        if self._memory_path:
            snapshot = _load_memory_snapshot(
                self._memory_path, self.embedding_dim, self._get_embedding
            )
            for key, value in snapshot["core_persona"].items():
                self.core_persona_store.set(key, value)
            for fragment in snapshot["episodic"]:
                self.episodic_store.add(fragment)

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本向量（优先使用外部 embedding API）。"""
        if self.embedding_api is not None:
            return self.embedding_api.embed(text)
        return embed_text(text, self.embedding_dim)

    async def add_sensory_input(
        self,
        content: str,
        created_at: Optional[float] = None,
        force_consolidate: bool = False,
    ) -> Optional[MemoryFragment]:
        """写入感知缓冲区，必要时触发固化。"""
        record = SensoryRecord(content=content, created_at=created_at or time.time())
        self.sensory_buffer.append(record)
        if force_consolidate or len(self.sensory_buffer) >= self.buffer_limit:
            return await self.consolidate()
        return None

    async def consolidate(self) -> Optional[MemoryFragment]:
        """将缓冲区内容汇总为情节记忆。"""
        if not self.sensory_buffer:
            return None
        combined = "\n".join(record.content for record in self.sensory_buffer)
        created_at = self.sensory_buffer[-1].created_at
        summary, importance = await self.llm_interface.summarize_and_score(combined)
        self.sensory_buffer.clear()
        if importance < self.promotion_threshold:
            return None
        fragment = MemoryFragment(
            id=uuid.uuid4(),
            content=summary,
            created_at=created_at,
            importance_score=importance,
            current_strength=self.max_strength,
            last_accessed_at=created_at,
            embedding=self._get_embedding(summary),
        )
        self.episodic_store.add(fragment)
        self._persist()
        return fragment

    def apply_decay(self, current_time: Optional[float] = None) -> None:
        """对情节记忆执行强度衰减。"""
        now = current_time or time.time()
        dirty = False
        for fragment in list(self.episodic_store.list_all()):
            fragment_key = str(fragment.id)
            last_decay = self._last_decay_at.get(fragment_key)
            baseline = fragment.last_accessed_at
            if last_decay is not None and last_decay > baseline:
                baseline = last_decay
            dt = max(0.0, now - baseline)
            if dt <= 0:
                continue
            fragment.current_strength = apply_ebbinghaus_decay(
                fragment.current_strength, self.decay_rate, dt
            )
            self._last_decay_at[fragment_key] = now
            dirty = True
            if fragment.current_strength < self.forget_threshold:
                self.episodic_store.delete(fragment.id)
                self._last_decay_at.pop(fragment_key, None)
                dirty = True
        if dirty:
            self._persist()

    def retrieve_and_reinforce(self, query: str, top_k: int = 5) -> List[MemoryFragment]:
        """检索记忆并强化命中片段强度。"""
        query_embedding = self._get_embedding(query)
        scored: List[Tuple[float, MemoryFragment]] = []
        for fragment in self.episodic_store.list_all():
            similarity = cosine_similarity(query_embedding, fragment.embedding)
            strength_score = (
                fragment.current_strength / self.max_strength
                if self.max_strength > 0
                else 0.0
            )
            score = self.weight_relevance * similarity + self.weight_strength * strength_score
            scored.append((score, fragment))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [fragment for score, fragment in scored[:top_k] if score > 0]
        now = time.time()
        for fragment in selected:
            fragment.last_accessed_at = now
            fragment.current_strength = max(fragment.current_strength, self.reinforce_strength)
            if fragment.current_strength > self.max_strength:
                fragment.current_strength = self.max_strength
        if selected:
            self._persist()
        return selected

    def set_core_persona(self, key: str, value: str) -> None:
        """设置核心人格键值。"""
        existing = self.core_persona_store.get(key)
        self.core_persona_store.set(key, value)
        if existing != value:
            self._persist()

    def get_core_persona(self, key: str) -> Optional[str]:
        """获取核心人格键值。"""
        return self.core_persona_store.get(key)

    def list_core_persona(self) -> List[Tuple[str, str]]:
        """列出核心人格全部键值对。"""
        return self.core_persona_store.items()

    def _persist(self) -> None:
        """持久化当前记忆状态。"""
        if not self._memory_path:
            return
        _save_memory_snapshot(
            self._memory_path,
            dict(self.core_persona_store.items()),
            list(self.episodic_store.list_all()),
        )
