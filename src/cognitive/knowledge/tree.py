"""文件职责：知识树的加载、查询与解锁管理。
简明实现逻辑：加载 JSON 节点，按锁定状态查询，检查前置条件解锁。
输入输出：输入为文件路径与主题；输出为知识内容或解锁结果。"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.cognitive.knowledge.interceptor import KnowledgeInterceptor


@dataclass
class KnowledgeNode:
    """知识节点定义。"""

    node_id: str
    parent: Optional[str]
    is_locked: bool
    content: str
    prerequisites: List[str] = field(default_factory=list)
    last_accessed: float = 0.0


class KnowledgeBase:
    """知识树管理器，负责加载与查询。"""

    def __init__(self, interceptor: Optional[KnowledgeInterceptor] = None) -> None:
        """初始化知识树与拦截器。"""
        self.tree: Dict[str, KnowledgeNode] = {}
        self.interceptor = interceptor

    def load_from_json(self, filepath: str) -> None:
        """从 JSON 文件加载知识树结构。"""
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
        return True
