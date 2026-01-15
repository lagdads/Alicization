"""文件职责：锁定知识访问拦截器。
简明实现逻辑：接收被拦截节点并返回提示文本。
输入输出：输入为节点 ID 与上下文；输出为提示字符串。"""


class KnowledgeInterceptor:
    """知识访问拦截器。"""

    def intercept(self, node_id: str, context: dict) -> str:
        """返回锁定节点的提示信息。"""
        return f"Knowledge locked: {node_id}"
