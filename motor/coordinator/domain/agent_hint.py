from pydantic import BaseModel, Field
from motor.common.logger import get_logger

logger = get_logger(__name__)

# 请求头回退字段名
HEADER_SESSION_ID = "X-Session-Id"
HEADER_PARENT_SESSION_ID = "X-Parent-Session-Id"
_AGENT_HINT_KNOWN_FIELDS = frozenset({
    "session_id", "parent_session_id",
    "cache_control", "context_management",
    "latency_control", "priority_control",
})


class CacheControl(BaseModel):
    """KV 缓存控制(穿刺版本实现)"""
    type: str = Field(default="ephemeral", description="缓存类型，仅支持ephemeral")
    ttl: int = Field(default=5, description="缓存过期时间，单位为分钟，默认5，最大60（1h）")


class ContextEdit(BaseModel):
    """上下文部分清理操作（仅设计）"""
    type: str = Field(..., description="操作类型，如 clear_tool_uses")
    # 后续版本可扩展更多字段


class ContextEvict(BaseModel):
    """完整上下文驱逐操作（仅设计）"""
    type: str = Field(..., description="操作类型，如 offload / evict")
    # 后续版本可扩展更多字段


class ContextManagement(BaseModel):
    """上下文管理（仅设计）"""
    edits: list[ContextEdit] = Field(default_factory=list, description="上下文部分清理操作列表")
    evicts: list[ContextEvict] = Field(default_factory=list, description="完整上下文驱逐操作列表")


class LatencyControl(BaseModel):
    """时延/SLO 提示（仅设计）"""
    latency_sensitivity: int | None = Field(default=None, description="时延敏感性提示（ms）")
    # 后续版本可扩展更多字段


class PriorityControl(BaseModel):
    """优先级提示（仅设计）"""
    priority: int | None = Field(default=None, description="优先级提示，数值越大优先级越高")
    # 后续版本可扩展更多字段


class AgentHintInfo(BaseModel):
    """
    从 OpenAI API 请求 agent_hint 解析的结构化信息
    穿刺版本仅 session_id / parent_session_id / cache_control 会被 Scheduler 使用。
    context_management / latency_control / priority_control 仅定义了数据结构，
    解析后会填充，但 Scheduler 暂不依赖这些字段做调度决策。
    """
    session_id: str | None = Field(default=None, description="会话ID，客户端传入或自动生成")
    parent_session_id: str | None = Field(default=None, description="父会话ID，一般是主 agent 对应的 session")
    cache_control: CacheControl | None = Field(default=None, description="KV 缓存控制提示")
    context_management: ContextManagement | None = Field(default=None, description="上下文管理提示（仅设计）")
    latency_control: LatencyControl | None = Field(default=None, description="时延控制提示（仅设计）")
    priority_control: PriorityControl | None = Field(default=None, description="优先级控制提示（仅设计）")
    raw_extra: dict | None = Field(default_factory=list, description="agent_hint 中未解析的扩展字段透传字典")


def _parse_context_management(data: dict) -> ContextManagement | None:
    context_management = None
    if isinstance(data, dict):
        try:
            context_management = ContextManagement(
                edits=data.get("edits"),
                evicts=data.get("evicts"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse context_management: %s", e)
    return context_management


def parse_agent_hint(
        request_json: dict,
        headers: dict | None = None,
) -> AgentHintInfo:
    """
    从请求 JSON 的 agent_hint 字段和 HTTP 请求头中解析 AgentHintInfo
    Args:
        request_json (dict): 请求 JSON 数据
        headers (dict | None): HTTP 请求头，可选，用于 session_id 回退解析
    Returns:
        AgentHintInfo: 解析后的结构化信息，任何字段缺失时使用 None/空值 填充
    """
    # 1、提取 agent_hint 子对象
    agent_hint_data = request_json.get("agent_hint", {})

    # 2、解析 session_id
    session_id = agent_hint_data.get("session_id")
    parent_session_id = agent_hint_data.get("parent_session_id")

    # 3、请求头回退（仅当 agent_hint 中缺失时）
    if headers:
        if not session_id:
            session_id = headers.get(HEADER_SESSION_ID)
        if not parent_session_id:
            parent_session_id = headers.get(HEADER_PARENT_SESSION_ID)

    # 4、解析 cache_control （穿刺实现）
    cache_control = None
    cc_data = agent_hint_data.get("cache_control")
    if isinstance(cc_data, dict):
        try:
            cache_control = CacheControl(
                type=cc_data.get("type", "ephemeral"),
                ttl=cc_data.get("ttl", 5),
            )
            if cache_control.ttl < 0 or cache_control.ttl > 60:
                logger.warning(f"Invalid cache_control ttl: %d", cache_control.ttl)
            elif cache_control.type != "ephemeral":
                logger.warning(f"Invalid cache_control type: %s", cache_control.type)
        except Exception as e:
            logger.warning(f"Failed to parse cache_control: %s", e)

    #5、解析 context_management （仅设计，解析但 Scheduler 不使用）
    context_management = _parse_context_management(agent_hint_data.get("context_management"))

    #6、解析 latency_control （仅设计）
    latency_control = None
    lc_data = agent_hint_data.get("latency_control")
    if isinstance(lc_data, dict):
        try:
            latency_control = LatencyControl(
                latency_sensitivity=lc_data.get("latency_sensitivity")
            )
        except Exception as e:
            logger.warning(f"Failed to parse latency_control: %s", e)

    #7、解析 priority_control （仅设计）
    priority_control = None
    pc_data = agent_hint_data.get("priority_control")
    if isinstance(pc_data, dict):
        try:
            priority_control = PriorityControl(
                priority=pc_data.get("priority")
            )
        except Exception as e:
            logger.warning(f"Failed to parse priority_control: %s", e)
    
    #8、收集 agent_hint 中未解析的扩展字段 raw_extra
    raw_extra = {}
    for key, value in agent_hint_data.items():
        if key not in _AGENT_HINT_KNOWN_FIELDS:
            raw_extra[key] = value

    return AgentHintInfo(
        session_id=session_id,
        parent_session_id=parent_session_id,
        cache_control=cache_control,
        context_management=context_management,
        latency_control=latency_control,
        priority_control=priority_control,
        raw_extra=raw_extra,
    )