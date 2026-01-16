"""文件职责：LLM 抽象接口、分组路由与 Stub 实现。
简明实现逻辑：按用途选择不同 API（embedding/fast/advanced）驱动逻辑。
输入输出：输入为文本与上下文；输出为摘要、意图、回答与向量。"""

import abc
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.cognitive.memory.embedding import cosine_similarity, embed_text


class EmbeddingInterface(abc.ABC):
    """向量化接口抽象。"""

    @abc.abstractmethod
    def embed(self, text: str) -> List[float]:
        """将文本转换为向量。"""
        raise NotImplementedError


class LLMInterface(abc.ABC):
    """LLM 接口抽象。"""

    @abc.abstractmethod
    async def summarize_and_score(self, memory: str) -> Tuple[str, float]:
        """生成摘要并返回重要性分数。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_intent(self, context: dict, memories: List[str]) -> str:
        """根据上下文与记忆生成意图文本。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def rag_query(self, query: str, memories: List[str]) -> str:
        """根据检索记忆回答问题。"""
        raise NotImplementedError

    @abc.abstractmethod
    async def generate_actions(self, context: dict, memories: List[str]) -> Dict[str, Any]:
        """根据上下文生成动作计划。"""
        raise NotImplementedError


class LLMGroup(LLMInterface):
    """LLM 分组路由器，按任务选择 API。"""

    def __init__(
        self,
        embed_api: EmbeddingInterface,
        fast_api: LLMInterface,
        advanced_api: LLMInterface,
        routing: Optional[Dict[str, Dict[str, str]]] = None,
        default_module: str = "default",
    ) -> None:
        """初始化分组路由与模型接口。"""
        self.embed_api = embed_api
        self.fast_api = fast_api
        self.advanced_api = advanced_api
        self.routing = routing or {}
        self.default_module = default_module

    def for_module(self, module_name: str) -> LLMInterface:
        """为指定模块返回代理接口。"""
        return LLMModuleProxy(self, module_name)

    async def summarize_and_score(self, memory: str) -> Tuple[str, float]:
        """路由到对应 API 进行摘要与评分。"""
        api = self._select_api("summarize_and_score", self.default_module)
        return await api.summarize_and_score(memory)

    async def generate_intent(self, context: dict, memories: List[str]) -> str:
        """路由到对应 API 生成意图。"""
        api = self._select_api("generate_intent", self.default_module)
        return await api.generate_intent(context, memories)

    async def rag_query(self, query: str, memories: List[str]) -> str:
        """使用 embedding 进行记忆检索并返回文本。"""
        if not memories:
            return "No relevant memories found"
        query_embedding = self.embed_api.embed(query)
        scored: List[Tuple[float, str]] = []
        for memory in memories:
            memory_embedding = self.embed_api.embed(memory)
            similarity = cosine_similarity(query_embedding, memory_embedding)
            scored.append((similarity, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [memory for score, memory in scored if score > 0][:3]
        if not selected:
            return "No relevant memories found"
        return "\n".join(selected)

    def _select_api(self, task: str, module_name: str) -> LLMInterface:
        """根据路由配置选择 fast/advanced API。"""
        module_routes = self.routing.get(module_name, {})
        default_routes = self.routing.get(self.default_module, {})
        api_name = module_routes.get(task) or default_routes.get(task)
        if api_name == "advanced":
            return self.advanced_api
        return self.fast_api

    async def generate_actions(self, context: dict, memories: List[str]) -> Dict[str, Any]:
        """路由到对应 API 生成动作计划。"""
        api = self._select_api("generate_actions", self.default_module)
        return await api.generate_actions(context, memories)


class LLMModuleProxy(LLMInterface):
    """按模块代理到 LLMGroup 的路由选择。"""

    def __init__(self, group: LLMGroup, module_name: str) -> None:
        """初始化模块代理。"""
        self.group = group
        self.module_name = module_name

    async def summarize_and_score(self, memory: str) -> Tuple[str, float]:
        """模块内摘要与评分。"""
        api = self.group._select_api("summarize_and_score", self.module_name)
        return await api.summarize_and_score(memory)

    async def generate_intent(self, context: dict, memories: List[str]) -> str:
        """模块内意图生成。"""
        api = self.group._select_api("generate_intent", self.module_name)
        return await api.generate_intent(context, memories)

    async def rag_query(self, query: str, memories: List[str]) -> str:
        """模块内 RAG 查询。"""
        return await self.group.rag_query(query, memories)

    async def generate_actions(self, context: dict, memories: List[str]) -> Dict[str, Any]:
        """模块内动作计划生成。"""
        api = self.group._select_api("generate_actions", self.module_name)
        return await api.generate_actions(context, memories)


def _stub_summarize_and_score(memory: str) -> Tuple[str, float]:
    """用于离线场景的摘要与评分 stub。"""
    summary = memory.strip().replace("\n", " ")
    if len(summary) > 120:
        summary = summary[:117] + "..."
    length_score = min(10.0, max(1.0, len(summary) / 12.0))
    emphasis = 1.0 if re.search(r"[!！?？]", memory) else 0.0
    return summary, min(10.0, length_score + emphasis)


class StubEmbedding(EmbeddingInterface):
    """基于简单哈希的 embedding stub。"""

    def __init__(self, embedding_dim: int = 12) -> None:
        """初始化 stub embedding 维度。"""
        self.embedding_dim = embedding_dim

    def embed(self, text: str) -> List[float]:
        """生成文本向量。"""
        return embed_text(text, self.embedding_dim)


class StubLLM(LLMInterface):
    """纯逻辑 LLM stub 实现。"""

    async def summarize_and_score(self, memory: str) -> Tuple[str, float]:
        """返回基于长度的摘要与评分。"""
        return _stub_summarize_and_score(memory)

    async def generate_intent(self, context: dict, memories: List[str]) -> str:
        """根据简单规则生成意图。"""
        goal = context.get("goal")
        if goal:
            return f"Advance goal: {goal}"
        if memories:
            return f"Explore based on memory: {memories[0]}"
        return "Explore environment and record new memories"

    async def rag_query(self, query: str, memories: List[str]) -> str:
        """返回截断后的记忆列表。"""
        if not memories:
            return "No relevant memories found"
        return "\n".join(memories[:3])

    async def generate_actions(self, context: dict, memories: List[str]) -> Dict[str, Any]:
        """使用规则返回简单动作计划。"""
        message = str(context.get("message", ""))
        goal = str(context.get("goal", ""))
        action = "wait(ticks=1)"
        if "移动" in message or "走" in message:
            action = "move_to(x=0, y=0)"
        elif "等待" in message or "休息" in message:
            action = "wait(ticks=1)"
        elif "攻击" in message:
            action = "attack(target_id=\"$enemy_id\")"
        elif "交谈" in message or "对话" in message:
            action = "talk(target_id=\"$npc_id\", topic=\"greeting\")"
        elif "拾取" in message or "拿起" in message:
            action = "pickup(object_id=\"$object_id\")"
        elif "寻找" in message or "扫描" in message:
            action = "scan_nearby(tag=\"item\")"
        elif "采集" in message or "收集" in message:
            action = "gather(resource_id=\"wood\")"
        elif "火" in message and "木" in message:
            action = "gather(resource_id=\"wood\")"
        goal_text = goal or "回应"
        return {"goal": goal_text, "actions": [action]}


def _load_openai_clients() -> Tuple[Any, Any]:
    """延迟加载 OpenAI SDK 客户端类型。"""
    try:
        from openai import AsyncOpenAI, OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI SDK not installed. Add 'openai' to requirements.txt."
        ) from exc
    return AsyncOpenAI, OpenAI


def _load_dotenv() -> None:
    """加载 .env 环境变量（若存在）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _resolve_env_value(
    config: Dict[str, Any], key: str, default: Optional[Any] = None
) -> Optional[Any]:
    """读取配置项，支持 *_env 覆盖。"""
    env_key = config.get(f"{key}_env")
    if env_key:
        env_value = os.getenv(str(env_key))
        if env_value is not None and env_value != "":
            return env_value
    value = config.get(key)
    if value is None or value == "":
        return default
    return value


def _openai_client_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """构建 OpenAI 客户端初始化参数。"""
    api_key = config.get("api_key")
    api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
    if not api_key:
        api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"OpenAI API key not configured. Set {api_key_env} or providers.*.api_key."
        )
    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    base_url = _resolve_env_value(config, "base_url")
    if base_url:
        client_kwargs["base_url"] = base_url
    for key in ("organization", "project", "max_retries"):
        value = config.get(key)
        if value is not None:
            client_kwargs[key] = value
    timeout = _resolve_env_value(config, "timeout")
    if timeout is None:
        timeout = 30
    try:
        client_kwargs["timeout"] = float(timeout)
    except (TypeError, ValueError):
        client_kwargs["timeout"] = 30
    return client_kwargs


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """从文本中提取第一个 JSON 对象。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _clamp(value: float, min_value: float, max_value: float) -> float:
    """将数值限制在指定范围内。"""
    return max(min_value, min(value, max_value))


def _parse_summary_and_score(text: str, fallback_memory: str) -> Tuple[str, float]:
    """解析 LLM 返回的摘要与重要性分数。"""
    fallback_summary, fallback_score = _stub_summarize_and_score(fallback_memory)
    summary = fallback_summary
    importance = fallback_score
    data = _extract_json_block(text)
    if isinstance(data, dict):
        raw_summary = data.get("summary")
        if isinstance(raw_summary, str) and raw_summary.strip():
            summary = raw_summary.strip()
        raw_score = data.get("importance", data.get("score"))
        if raw_score is not None:
            try:
                importance = float(raw_score)
            except (TypeError, ValueError):
                importance = fallback_score
    if len(summary) > 120:
        summary = summary[:117] + "..."
    importance = _clamp(importance, 0.0, 10.0)
    return summary, importance


def _clean_intent_response(text: str) -> str:
    """清理意图响应文本，提取核心内容。"""
    raw = text.strip()
    if not raw:
        return ""
    data = _extract_json_block(raw)
    if isinstance(data, dict):
        intent = data.get("intent")
        if isinstance(intent, str) and intent.strip():
            raw = intent.strip()
    for separator in ("|", "\n", "\r"):
        if separator in raw:
            raw = raw.split(separator, 1)[0].strip()
    raw = re.sub(r"^(意图|intent)\s*[:：]\s*", "", raw, flags=re.IGNORECASE)
    for marker in ("记忆:", "记忆：", "Memory:", "memory:", "Memories:", "memories:"):
        if marker in raw:
            raw = raw.split(marker, 1)[0].strip()
    raw = raw.strip().strip("\"'“”‘’")
    match = re.search(r"[。！？.!?]", raw)
    if match:
        raw = raw[: match.end()].strip()
    return raw


def _intent_is_valid(text: str) -> bool:
    """过滤不合规或含外部信息的意图文本。"""
    if not text:
        return False
    if re.search(r"[A-Za-z]", text):
        return False
    lowered = text.lower()
    if "http" in lowered or "www" in lowered:
        return False
    for token in (
        "助手",
        "政策",
        "免责声明",
        "模型",
        "游戏",
        "玩家",
        "作品",
    ):
        if token in text:
            return False
    return True


def _fallback_intent(context: dict, memories: List[str]) -> str:
    """在生成失败时返回兜底意图。"""
    goal = context.get("goal")
    if goal == "respond":
        return "回应用户"
    if goal:
        return f"推进目标：{goal}"
    if memories:
        return "根据记忆继续探索"
    return "探索并记录见闻"


def _summary_is_valid(summary: str) -> bool:
    """检查摘要文本是否合规。"""
    if not summary:
        return False
    for token in (
        "助手",
        "政策",
        "免责声明",
        "游戏",
        "玩家",
        "作品",
        "原神",
        "提瓦特",
        "蒙德",
        "西风骑士团",
        "可莉",
    ):
        if token in summary:
            return False
    return True


def _normalize_action_plan(raw: Dict[str, Any], fallback_goal: str) -> Dict[str, Any]:
    """规范化动作计划结构。"""
    goal = fallback_goal
    actions: List[str] = []
    if isinstance(raw, dict):
        raw_goal = raw.get("goal")
        if isinstance(raw_goal, str) and raw_goal.strip():
            goal = raw_goal.strip()
        raw_actions = raw.get("actions")
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if isinstance(item, str) and item.strip():
                    actions.append(item.strip())
    return {"goal": goal, "actions": actions}


class OpenAIEmbedding(EmbeddingInterface):
    """OpenAI Embedding 接口封装。"""

    def __init__(self, model: str, config: Dict[str, Any]) -> None:
        """初始化 OpenAI embedding 客户端。"""
        _, OpenAI = _load_openai_clients()
        self.client = OpenAI(**_openai_client_kwargs(config))
        self.model = model
        self.dimensions = config.get("dimensions")
        self.fallback_dim = int(config.get("fallback_dim", 12))
        self.logger = logging.getLogger("alicization.llm")

    def embed(self, text: str) -> List[float]:
        """调用 OpenAI 生成向量，失败时回退。"""
        params: Dict[str, Any] = {"model": self.model, "input": text}
        if self.dimensions:
            params["dimensions"] = int(self.dimensions)
        try:
            response = self.client.embeddings.create(**params)
            return list(response.data[0].embedding)
        except Exception as exc:
            self.logger.warning("OpenAI embedding failed: %s", exc)
        return embed_text(text, self.fallback_dim)


class OpenAILLM(LLMInterface):
    """OpenAI LLM 接口封装。"""

    def __init__(self, model: str, config: Dict[str, Any]) -> None:
        """初始化 OpenAI LLM 客户端。"""
        AsyncOpenAI, _ = _load_openai_clients()
        self.client = AsyncOpenAI(**_openai_client_kwargs(config))
        self.model = model
        self.temperature = float(config.get("temperature", 0.2))
        self.max_tokens = int(config.get("max_tokens", 256))
        self.request_timeout = float(
            _resolve_env_value(config, "request_timeout", 30)
        )
        self.logger = logging.getLogger("alicization.llm")
        self.fallback = StubLLM()

    async def _chat_messages(self, messages: List[Dict[str, str]]) -> str:
        """发送 chat 请求并返回文本。"""
        request = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        try:
            if self.request_timeout and self.request_timeout > 0:
                response = await asyncio.wait_for(request, self.request_timeout)
            else:
                response = await request
        except asyncio.TimeoutError as exc:
            raise RuntimeError("OpenAI request timed out") from exc
        content = response.choices[0].message.content
        return content.strip() if content else ""

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """使用 system/user 提示词进行一次对话。"""
        return await self._chat_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

    def _format_context(self, context: dict) -> str:
        """格式化上下文为文本块。"""
        try:
            return json.dumps(context, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(context)

    def _build_memory_block(self, memories: List[str]) -> str:
        """格式化记忆列表为文本块。"""
        if not memories:
            return "(none)"
        return "\n".join(f"- {item}" for item in memories)

    async def summarize_and_score(self, memory: str) -> Tuple[str, float]:
        """调用 OpenAI 生成摘要并解析重要性分数。"""
        system_prompt = (
            "Summarize the observed dialogue/action strictly as factual memory. "
            "Do not invent new names, places, or franchises. "
            "Never mention being an AI/assistant or policies. "
            "Do not mention games, players, or works. "
            "Return JSON only: {\"summary\": \"...\", \"importance\": 0-10}. "
            "Use Chinese, keep summary short and grounded in the input."
        )
        try:
            reply = await self._chat(system_prompt, memory)
        except Exception as exc:
            self.logger.warning("OpenAI summarize failed: %s", exc)
            return await self.fallback.summarize_and_score(memory)
        summary, importance = _parse_summary_and_score(reply, memory)
        if not _summary_is_valid(summary):
            return _stub_summarize_and_score(memory)
        return summary, importance

    async def generate_intent(self, context: dict, memories: List[str]) -> str:
        """生成中文意图文本并做清洗校验。"""
        system_prompt = (
            "You are an in-world NPC in a fantasy game. "
            "Decide the NPC's next intent based on the given context and memories. "
            "Stay within this game's world; do not reference other IPs or real-world brands. "
            "Do not invent new lore or place names. If details are missing, ask a clarifying question. "
            "Return JSON only: {\"intent\": \"...\"}. "
            "Use Chinese. No quotes, no links, no markdown. "
            "Address the user as an adventurer or traveler. "
            "Do not mention games, players, or works. "
            "No meta commentary, no policy/safety text, no mention of being an AI."
        )
        context_block = self._format_context(context)
        memory_block = self._build_memory_block(memories)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_block}"},
            {"role": "user", "content": f"Memories:\n{memory_block}"},
            {"role": "user", "content": "Task: Return only the JSON object."},
        ]
        try:
            reply = await self._chat_messages(messages)
        except Exception as exc:
            self.logger.warning("OpenAI intent failed: %s", exc)
            return _fallback_intent(context, memories)
        cleaned = _clean_intent_response(reply)
        if _intent_is_valid(cleaned):
            return cleaned
        return _fallback_intent(context, memories)

    async def rag_query(self, query: str, memories: List[str]) -> str:
        """基于记忆块回答查询问题。"""
        if not memories:
            return "No relevant memories found"
        system_prompt = (
            "Answer the query using only the provided memories. "
            "If they are insufficient, say you do not know."
        )
        memory_block = "\n".join(f"- {item}" for item in memories)
        user_prompt = f"Query: {query}\nMemories:\n{memory_block}"
        try:
            reply = await self._chat(system_prompt, user_prompt)
        except Exception as exc:
            self.logger.warning("OpenAI rag query failed: %s", exc)
            return await self.fallback.rag_query(query, memories)
        return reply or await self.fallback.rag_query(query, memories)

    async def generate_actions(self, context: dict, memories: List[str]) -> Dict[str, Any]:
        """生成动作计划并解析 JSON 输出。"""
        system_prompt = (
            "You are a game NPC planner. "
            "Return a JSON object only: {\"goal\": \"...\", \"actions\": [\"...\"]}. "
            "Each action must be a function signature string from the allowed list: "
            "move_to(x=0, y=0), scan_nearby(tag=\"\"), find_item(item_type=\"\"), "
            "pickup(object_id=\"\"), attack(target_id=\"\"), talk(target_id=\"\", topic=\"\"), "
            "gather(resource_id=\"\"), wait(ticks=1). "
            "Use Chinese for goal, but keep actions in function signature format."
        )
        context_block = self._format_context(context)
        memory_block = self._build_memory_block(memories)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_block}"},
            {"role": "user", "content": f"Memories:\n{memory_block}"},
            {"role": "user", "content": "Task: Return only the JSON object."},
        ]
        try:
            reply = await self._chat_messages(messages)
        except Exception as exc:
            self.logger.warning("OpenAI actions failed: %s", exc)
            return await self.fallback.generate_actions(context, memories)
        data = _extract_json_block(reply) or {}
        plan = _normalize_action_plan(data, str(context.get("goal", "")))
        if plan["actions"]:
            return plan
        return await self.fallback.generate_actions(context, memories)


def build_llm_group(config: Dict[str, Any]) -> LLMGroup:
    """根据配置构建 LLMGroup 实例。"""
    _load_dotenv()
    providers = config.get("providers", {})
    embed_config = providers.get("embed_api", {})
    embed_type = str(embed_config.get("type", "stub")).lower()
    if embed_type == "openai":
        embed_model = str(
            _resolve_env_value(embed_config, "model", "text-embedding-3-small")
        )
        embed_api = OpenAIEmbedding(model=embed_model, config=embed_config)
    elif embed_type == "stub":
        embedding_dim = int(embed_config.get("embedding_dim", 12))
        embed_api = StubEmbedding(embedding_dim=embedding_dim)
    else:
        raise ValueError(f"Unknown embed_api type: {embed_type}")

    def build_llm(provider_config: Dict[str, Any], default_model: str) -> LLMInterface:
        """按提供方配置构建 LLM 实例。"""
        provider_type = str(provider_config.get("type", "stub")).lower()
        if provider_type == "openai":
            model = str(_resolve_env_value(provider_config, "model", default_model))
            return OpenAILLM(model=model, config=provider_config)
        if provider_type == "stub":
            return StubLLM()
        raise ValueError(f"Unknown LLM provider type: {provider_type}")

    fast_api = build_llm(providers.get("fast_api", {}), "gpt-4o-mini")
    advanced_api = build_llm(providers.get("advanced_api", {}), "gpt-4o")
    routing = config.get("routing", {})

    return LLMGroup(
        embed_api=embed_api,
        fast_api=fast_api,
        advanced_api=advanced_api,
        routing=routing,
    )
