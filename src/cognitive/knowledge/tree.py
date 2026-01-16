"""文件职责：知识树的加载、查询与解锁管理。
简明实现逻辑：加载 JSON 节点，按锁定状态查询，检查前置条件解锁。
输入输出：输入为文件路径与主题；输出为知识内容或解锁结果。"""

import json
import logging
import toml
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from src.cognitive.knowledge.interceptor import KnowledgeInterceptor
from src.cognitive.llm_interface import EmbeddingInterface

try:
    import chromadb
except ImportError:  # pragma: no cover - handled by runtime check
    chromadb = None
try:
    from chromadb.errors import InvalidArgumentError
except Exception:  # pragma: no cover - optional dependency
    InvalidArgumentError = None


@dataclass
class KnowledgeNode:
    """知识节点定义。"""

    node_id: str
    parent: Optional[str]
    is_locked: bool
    content: str
    prerequisites: List[str] = field(default_factory=list)
    last_accessed: float = 0.0


class ChromaKnowledgeStore:
    """基于 ChromaDB 的知识向量索引。"""

    def __init__(
        self,
        persist_path: Optional[Path],
        collection_name: str,
        embedder: Callable[[str], List[float]],
    ) -> None:
        """初始化知识向量库。"""
        if chromadb is None:
            raise RuntimeError("chromadb is required. Install it with `pip install chromadb`.")
        self.embedder = embedder
        self.collection_name = collection_name
        if persist_path:
            persist_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist_path))
        else:
            client = chromadb.Client()
        self.client = client
        self.collection = client.get_or_create_collection(name=collection_name)

    def _reset_collection(self) -> None:
        """重建集合以匹配当前 embedding 维度。"""
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def index_nodes(self, nodes: Iterable[KnowledgeNode], replace: bool = True) -> None:
        """将知识节点写入向量库。"""
        ids: List[str] = []
        documents: List[str] = []
        embeddings: List[List[float]] = []
        metadatas: List[Dict[str, str]] = []
        for node in nodes:
            doc = f"{node.node_id}: {node.content}".strip()
            ids.append(node.node_id)
            documents.append(doc)
            embeddings.append(self.embedder(doc))
            metadatas.append({"node_id": node.node_id})
        if not ids:
            return
        if replace:
            existing = self.collection.get().get("ids") or []
            existing_ids = set(existing)
            target_ids = set(ids)
            stale_ids = list(existing_ids - target_ids)
            if stale_ids:
                self.collection.delete(ids=stale_ids)
        try:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as exc:
            if InvalidArgumentError and isinstance(exc, InvalidArgumentError):
                logging.warning(
                    "Knowledge collection embedding dim mismatch; rebuilding collection."
                )
                self._reset_collection()
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
            else:
                raise

    def upsert_node(self, node: KnowledgeNode) -> None:
        """更新单个知识节点向量。"""
        self.index_nodes([node], replace=False)

    def query(self, text: str, top_k: int = 3) -> List[str]:
        """根据文本检索最相关的知识节点 id。"""
        embedding = self.embedder(text)
        data = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
        )
        ids_list = data.get("ids") or [[]]
        return list(ids_list[0])


class KnowledgeBase:
    """知识树管理器，负责加载与查询。"""

    def __init__(
        self,
        interceptor: Optional[KnowledgeInterceptor] = None,
        embedder: Optional[EmbeddingInterface] = None,
        vector_store_path: Optional[Path] = None,
    ) -> None:
        """初始化知识树与拦截器。"""
        self.tree: Dict[str, KnowledgeNode] = {}
        self.interceptor = interceptor
        self._embedder = embedder
        self._vector_store: Optional[ChromaKnowledgeStore] = None
        if embedder is not None:
            self._vector_store = ChromaKnowledgeStore(
                vector_store_path, "knowledge", embedder.embed
            )

    def load_from_json(self, filepath: str) -> None:
        """从 JSON/TOML 文件加载知识树结构。"""
        suffix = filepath.lower().rsplit(".", 1)[-1]
        if suffix == "toml":
            payload = toml.load(filepath)
        else:
            with open(filepath, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        nodes = payload.get("nodes", [])
        for node in nodes:
            knowledge_node = KnowledgeNode(
                node_id=node["id"],
                parent=node.get("parent"),
                is_locked=node.get("is_locked", True),
                content=node.get("content", ""),
                prerequisites=node.get("prerequisites", []),
            )
            self.tree[knowledge_node.node_id] = knowledge_node
        if self._vector_store:
            self._vector_store.index_nodes(self.tree.values())

    def query(self, topic: str, context: Optional[dict] = None) -> Optional[str]:
        """按主题查询知识内容，锁定时走拦截器。"""
        node = self.tree.get(topic)
        if not node:
            return None
        if node.is_locked:
            if self.interceptor:
                return self.interceptor.intercept(node.node_id, context or {})
            return None
        node.last_accessed = time.time()
        return node.content

    def semantic_query(self, text: str, context: Optional[dict] = None) -> Optional[str]:
        """按语义检索知识内容，锁定时走拦截器。"""
        if not self._vector_store:
            return None
        for node_id in self._vector_store.query(text, top_k=3):
            node = self.tree.get(node_id)
            if not node:
                continue
            if node.is_locked:
                if self.interceptor:
                    return self.interceptor.intercept(node.node_id, context or {})
                return None
            node.last_accessed = time.time()
            return node.content
        return None

    def learn(self, topic: str) -> bool:
        """解锁指定主题节点。"""
        node = self.tree.get(topic)
        if not node:
            return False
        if not node.is_locked:
            return False
        for prereq in node.prerequisites:
            prereq_node = self.tree.get(prereq)
            if prereq_node is None or prereq_node.is_locked:
                return False
        node.is_locked = False
        if self._vector_store:
            self._vector_store.upsert_node(node)
        return True
