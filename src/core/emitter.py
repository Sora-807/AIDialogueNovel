"""事件发射器 — 解耦引擎输出与前端消费。

引擎通过 Emitter 接口发出事件，前端（CLI / SSE / WebSocket）各自实现。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════
# 事件类型
# ═══════════════════════════════════════════════════════════════

@dataclass
class NarrateEvent:
    """旁白事件（公开）。"""
    speaker: str = "Narrator"
    content: str = ""


@dataclass
class SpeakEvent:
    """角色发言事件（公开）。"""
    speaker: str
    content: str


@dataclass
class EpisodeChangeEvent:
    """小剧场状态变更（公开）。"""
    episode_name: str = ""
    episode_id: int = 0
    state: str = ""  # episode_created | episode_ended


@dataclass
class InternalEvent:
    """内部调试事件（仅 debug 模式）。"""
    agent: str               # "Author" | "Narrator" | character name
    tool: str                # 工具名
    args: dict = field(default_factory=dict)
    result: str = ""
    is_invalid: bool = False


# ═══════════════════════════════════════════════════════════════
# EventEmitter 基类
# ═══════════════════════════════════════════════════════════════

class EventEmitter(ABC):
    """引擎事件发射器接口。CLI / HTTP 各自实现。"""

    @abstractmethod
    async def on_narrate(self, event: NarrateEvent):
        """旁白输出。"""
        ...

    @abstractmethod
    async def on_speak(self, event: SpeakEvent):
        """角色发言。"""
        ...

    @abstractmethod
    async def on_episode_change(self, event: EpisodeChangeEvent):
        """小剧场状态变更。"""
        ...

    @abstractmethod
    async def on_llm_token(self, agent: str, text: str):
        """LLM 流式输出 token（调试用）。"""
        ...

    @abstractmethod
    async def on_system_prompt(self, agent: str, text: str):
        """Agent 系统提示词。"""
        ...

    @abstractmethod
    async def on_user_message(self, agent: str, text: str):
        """发给 Agent 的用户消息。"""
        ...

    @abstractmethod
    async def on_internal(self, event: InternalEvent):
        """内部调试事件（仅 debug 模式触发）。"""
        ...

    async def on_session_start(self, story_id: str):
        """会话开始。"""
        pass

    async def on_session_end(self, story_id: str, total_episodes: int):
        """会话结束。"""
        pass


