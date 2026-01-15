"""文件职责：ECS 风格实体容器，管理组件存取。
简明实现逻辑：维护组件字典，提供增删查与存在性检查。
输入输出：输入为组件对象；输出为组件查询结果与布尔标记。"""

from typing import Any, Dict, Optional


class Entity:
    """ECS 风格实体，包含组件注册表。"""

    def __init__(self, entity_id: str) -> None:
        """使用唯一标识初始化实体。"""
        self.id = entity_id
        self.components: Dict[str, Any] = {}

    def add_component(self, name: str, component: Any) -> None:
        """为实体挂载组件。"""
        self.components[name] = component

    def remove_component(self, name: str) -> None:
        """移除指定组件（若存在）。"""
        self.components.pop(name, None)

    def get_component(self, name: str) -> Optional[Any]:
        """按名称获取组件。"""
        return self.components.get(name)

    def has_component(self, name: str) -> bool:
        """判断实体是否包含指定组件。"""
        return name in self.components
