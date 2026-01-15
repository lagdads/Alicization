"""文件职责：世界观知识加载与查询。
简明实现逻辑：读取 JSON 结构，按关键词匹配世界观条目。
输入输出：输入为文本与路径；输出为世界观片段。"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class WorldviewEntry:
    """世界观条目结构。"""

    entry_id: str
    content: str
    tags: List[str] = field(default_factory=list)
    visibility: str = "npc"


def _normalize_visibility(value: object) -> str:
    """规范化可见性标识。"""
    if not isinstance(value, str):
        return "npc"
    lowered = value.strip().lower()
    if lowered in ("npc", "in_world", "diegetic", "public"):
        return "npc"
    if lowered in ("meta", "gm", "dev", "developer", "system"):
        return "meta"
    if lowered in ("all", "any"):
        return "all"
    return "npc"


def _is_visible(entry_visibility: str, viewer_visibility: str) -> bool:
    """判断条目是否对当前可见性可见。"""
    viewer = _normalize_visibility(viewer_visibility)
    entry_vis = _normalize_visibility(entry_visibility)
    if viewer == "meta":
        return True
    if entry_vis == "meta":
        return False
    return True


class WorldviewKnowledge:
    """世界观知识集合与查询。"""

    def __init__(self, default_visibility: str = "npc") -> None:
        """初始化世界观容器。"""
        self.title = ""
        self.summary = ""
        self.summary_by_visibility: Dict[str, str] = {}
        self.entries: List[WorldviewEntry] = []
        self.default_visibility = _normalize_visibility(default_visibility)

    def with_default_visibility(self, visibility: str) -> "WorldviewKnowledge":
        """复制一份并设置默认可见性。"""
        clone = WorldviewKnowledge(default_visibility=visibility)
        clone.title = self.title
        clone.summary = self.summary
        clone.summary_by_visibility = dict(self.summary_by_visibility)
        clone.entries = list(self.entries)
        return clone

    def load_from_json(self, filepath: str) -> None:
        """从 JSON 文件加载世界观内容。"""
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.title = payload.get("title", "")
        raw_summary = payload.get("summary_by_visibility")
        if raw_summary is None:
            raw_summary = payload.get("summary", "")

        self.summary_by_visibility = {}
        if isinstance(raw_summary, dict):
            for key, value in raw_summary.items():
                if isinstance(key, str) and isinstance(value, str) and value.strip():
                    normalized_key = _normalize_visibility(key)
                    self.summary_by_visibility[normalized_key] = value.strip()
            self.summary = (
                self.summary_by_visibility.get("npc")
                or self.summary_by_visibility.get("all")
                or self.summary_by_visibility.get("meta")
                or ""
            )
        else:
            self.summary = raw_summary if isinstance(raw_summary, str) else ""
            if self.summary.strip():
                self.summary_by_visibility["npc"] = self.summary.strip()
        self.entries = []
        for entry in payload.get("entries", []):
            self.entries.append(
                WorldviewEntry(
                    entry_id=entry.get("id", ""),
                    content=entry.get("content", ""),
                    tags=entry.get("tags", []),
                    visibility=_normalize_visibility(entry.get("visibility", "npc")),
                )
            )

    def _summary_for_visibility(self, visibility: str) -> str:
        """按可见性选择摘要。"""
        viewer = _normalize_visibility(visibility)
        if not self.summary_by_visibility:
            return self.summary
        if viewer == "meta":
            return (
                self.summary_by_visibility.get("meta")
                or self.summary_by_visibility.get("npc")
                or self.summary_by_visibility.get("all")
                or self.summary
            )
        return (
            self.summary_by_visibility.get("npc")
            or self.summary_by_visibility.get("all")
            or self.summary
        )

    def _visible_entries(self, visibility: str) -> List[WorldviewEntry]:
        """筛选对指定可见性可见的条目。"""
        return [
            entry
            for entry in self.entries
            if _is_visible(entry.visibility, visibility)
        ]

    def intro(self) -> str:
        """返回世界观介绍文本。"""
        summary = self._summary_for_visibility(self.default_visibility)
        if summary:
            return summary
        for entry in self._visible_entries(self.default_visibility):
            if entry.content:
                return entry.content
        return ""

    def match_entry(self, text: str) -> Optional[WorldviewEntry]:
        """在文本中匹配世界观条目或标签。"""
        if not text:
            return None
        text_lower = text.lower()
        for entry in self._visible_entries(self.default_visibility):
            if entry.entry_id and entry.entry_id.lower() in text_lower:
                return entry
            for tag in entry.tags:
                tag_lower = tag.lower()
                if tag_lower and tag_lower in text_lower:
                    return entry
        return None

    def find_relevant(self, text: str) -> str:
        """返回与文本最相关的世界观内容。"""
        matched = self.match_entry(text)
        if matched and matched.content:
            return matched.content
        return self.intro()
