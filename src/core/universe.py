"""Universe — 引擎唯一可变状态中心。

所有 Agent 通过 Universe 完成：
  1. 信息获取（读 worldviews / characters / outlines / episodes）
  2. 状态写入（Author 写 episodes，Narrator 改 stage，Character 更新 state）
  3. 消息通信（send / poll — 替代 MessageQueue + 各种传参）
  4. LLM 对话历史（conversations — 替代各 Agent 自己持有的 _messages）

序列化 Universe 即完美 checkpoint。恢复一步完成。
"""
import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════
# Universe
# ═══════════════════════════════════════════════════════════════

@dataclass
class Universe:
    """引擎唯一可变状态。序列化它 = checkpoint，反序列化 = 恢复。"""

    # ── Story 源数据（从文件加载，运行时只读）──
    worldviews: dict[str, dict] = field(default_factory=dict)
    #  {path: {name, description, tags[], content, is_public}}

    outlines: list[dict] = field(default_factory=list)
    #  [{num, name, description, content}]

    characters: dict[str, dict] = field(default_factory=dict)
    #  {name: {profile_text, initial_state_text}}

    user_character: str = ""

    # ── 引擎位置 ──
    state: str = "planning"          # EpisodeState 值
    chapter_idx: int = 0
    episode_count: int = 0

    # ── Author 域（产出）──
    episodes: list[dict] = field(default_factory=list)
    foreshadowing: list[dict] = field(default_factory=list)
    short_term_plot: str = ""
    author_notes: list[dict] = field(default_factory=list)   # note() 工作记忆

    # ── Narrator 域（演出控制）──
    stage: list[str] = field(default_factory=list)
    worldview_grants: list[dict] = field(default_factory=list)
    configured_episode_id: int = 0

    # ── Character 域（运行时状态）──
    character_states: dict[str, str] = field(default_factory=dict)
    #  name → state.md 正文

    # ── 通信总线（替代 MessageQueue）──
    messages: list[dict] = field(default_factory=list)
    read_positions: dict[str, str] = field(default_factory=dict)
    #  agent → 最后已读 message_id
    _msg_counter: int = field(default=0, repr=False)

    # ── LLM 对话历史（替代各 Agent._messages）──
    conversations: dict[str, list[dict]] = field(default_factory=dict)
    #  agent_name → [序列化的 LangChain message dict]

    # ── 杂项 ──
    meta: dict = field(default_factory=dict)
    #  自由扩展字段

    # ═══════════════════════════════════════════════════════════
    # 消息通信（替代 MessageQueue）
    # ═══════════════════════════════════════════════════════════

    def send(self, from_agent: str, content: str, msg_type: str,
             targets: list[str], *, episode_id: int = 0) -> str:
        """发送消息到总线。返回 message_id。"""
        self._msg_counter += 1
        mid = f"msg_{self._msg_counter:06d}"
        self.messages.append({
            "message_id": mid,
            "episode_id": episode_id,
            "from": from_agent,
            "type": msg_type,
            "content": content,
            "targets": list(targets),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return mid

    def poll(self, agent_name: str) -> list[dict]:
        """获取 agent 未读的消息。按时间顺序返回。"""
        last_id = self.read_positions.get(agent_name)
        if not last_id:
            # 首次读取：返回所有发给自己的消息
            return [m for m in self.messages if agent_name in m.get("targets", [])]
        # 增量读取：返回 last_id 之后发给自己的消息
        found_last = False
        result = []
        for m in self.messages:
            if m["message_id"] == last_id:
                found_last = True
                continue
            if found_last and agent_name in m.get("targets", []):
                result.append(m)
        return result

    def mark_read(self, agent_name: str):
        """将 agent 标记为已读到最新消息。"""
        if self.messages:
            self.read_positions[agent_name] = self.messages[-1]["message_id"]

    def last_message_id(self, agent_name: str) -> str | None:
        """通讯总线上最后一条消息的 ID（用于调用方判断是否有新消息）。"""
        # 返回最后一条 agent 是 target 的消息 ID
        for m in reversed(self.messages):
            if agent_name in m.get("targets", []):
                return m["message_id"]
        return None

    def get_new(self, agent_name: str, last_read_id: str | None = None) -> list[dict]:
        """兼容旧 MessageQueue.get_new()。"""
        effective_last = last_read_id or self.read_positions.get(agent_name)
        if not effective_last:
            return [m for m in self.messages if agent_name in m.get("targets", [])]
        found_last = False
        result = []
        for m in self.messages:
            if m["message_id"] == effective_last:
                found_last = True
                continue
            if found_last and agent_name in m.get("targets", []):
                result.append(m)
        return result

    # ═══════════════════════════════════════════════════════════
    # LLM 对话历史
    # ═══════════════════════════════════════════════════════════

    def save_conversation(self, agent_name: str, messages: list):
        """将 LangChain messages 序列化存入 Universe。"""
        self.conversations[agent_name] = [_msg_to_dict(m) for m in messages]

    def load_conversation(self, agent_name: str) -> list:
        """从 Universe 恢复 LangChain messages。"""
        raw = self.conversations.get(agent_name, [])
        return [_dict_to_msg(d) for d in raw]

    def has_conversation(self, agent_name: str) -> bool:
        """Agent 是否有对话历史。"""
        return bool(self.conversations.get(agent_name))

    # ═══════════════════════════════════════════════════════════
    # 序列化
    # ═══════════════════════════════════════════════════════════

    def to_dict(self) -> dict:
        """完整序列化为纯 Python dict。"""
        return {
            "worldviews": self.worldviews,
            "outlines": self.outlines,
            "characters": self.characters,
            "user_character": self.user_character,
            "state": self.state,
            "chapter_idx": self.chapter_idx,
            "episode_count": self.episode_count,
            "episodes": self.episodes,
            "foreshadowing": self.foreshadowing,
            "short_term_plot": self.short_term_plot,
            "author_notes": self.author_notes,
            "stage": self.stage,
            "worldview_grants": self.worldview_grants,
            "configured_episode_id": self.configured_episode_id,
            "character_states": self.character_states,
            "messages": self.messages,
            "read_positions": self.read_positions,
            "conversations": self.conversations,
            "meta": self.meta,
            "_msg_counter": self._msg_counter,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Universe":
        """从 dict 重建 Universe。缺字段用默认值。"""
        return cls(
            worldviews=d.get("worldviews", {}),
            outlines=d.get("outlines", []),
            characters=d.get("characters", {}),
            user_character=d.get("user_character", ""),
            state=d.get("state", "planning"),
            chapter_idx=d.get("chapter_idx", 0),
            episode_count=d.get("episode_count", 0),
            episodes=d.get("episodes", []),
            foreshadowing=d.get("foreshadowing", []),
            short_term_plot=d.get("short_term_plot", ""),
            author_notes=d.get("author_notes", []),
            stage=d.get("stage", []),
            worldview_grants=d.get("worldview_grants", []),
            configured_episode_id=d.get("configured_episode_id", 0),
            character_states=d.get("character_states", {}),
            messages=d.get("messages", []),
            read_positions=d.get("read_positions", {}),
            conversations=d.get("conversations", {}),
            meta=d.get("meta", {}),
            _msg_counter=d.get("_msg_counter", 0),
        )

    # ═══════════════════════════════════════════════════════════
    # 便捷查询
    # ═══════════════════════════════════════════════════════════

    def worldview_overview(self) -> str:
        """世界观概览文本（给 Agent prompt 用）。"""
        if not self.worldviews:
            return "（无）"
        lines = []
        for path, w in self.worldviews.items():
            tag = "公开" if w.get("is_public") else "秘闻"
            lines.append(f"- [{tag}] `{path}` — {w.get('description', w.get('name', ''))}")
        return "\n".join(lines)

    def character_overview(self) -> str:
        """角色概览文本（给 Agent prompt 用）。"""
        if not self.characters:
            return "（无）"
        lines = []
        for name, c in self.characters.items():
            desc = ""
            # 从 profile_text 提取 description
            profile = c.get("profile_text", "")
            from src.storage.frontmatter import parse_frontmatter
            try:
                fm, _ = parse_frontmatter(profile)
                desc = fm.get("description", "")
            except Exception:
                pass
            marker = " [用户]" if name == self.user_character else ""
            state = self.character_states.get(name, "")
            if state:
                # 取前 100 字作为状态摘要
                state_summary = state[:100].replace("\n", " ").strip()
                lines.append(f"- {name}{marker}: {desc} | 状态: {state_summary}...")
            else:
                lines.append(f"- {name}{marker}: {desc}")
        return "\n".join(lines)

    def character_names(self) -> list[str]:
        """所有角色名列表。"""
        return list(self.characters.keys())

    def public_worldviews(self) -> dict:
        """仅公开世界观。"""
        return {p: w for p, w in self.worldviews.items() if w.get("is_public")}

    def granted_worldviews(self) -> dict:
        """public + 已授权世界观。"""
        result = dict(self.public_worldviews())
        for g in self.worldview_grants:
            p = g.get("path", "")
            if p in self.worldviews:
                result[p] = self.worldviews[p]
        return result

    def episode_characters(self, episode: dict = None) -> list[str]:
        """从 episode 的 scenes.enter/exit 中提取所有出场角色名。"""
        ep = episode or (self.episodes[-1] if self.episodes else None)
        if not ep:
            return []
        names = set()
        for s in ep.get("scenes", []):
            for e in s.get("enter", []):
                names.add(e["name"])
            for e in s.get("exit", []):
                names.add(e["name"])
        return list(names)

    def outline_progress(self) -> str:
        """大纲进度文本（给 Agent prompt 用）。"""
        if not self.outlines:
            return "（无大纲，自由发挥）"
        lines = [f"大纲共 {len(self.outlines)} 章："]
        for o in self.outlines:
            marker = " ← 当前" if o.get("number", 0) == self.chapter_idx + 1 else ""
            lines.append(f"- 【{o.get('number', '?')}】{o.get('chapter_name', o.get('name', '?'))}{marker}")
        if 0 <= self.chapter_idx < len(self.outlines):
            cur = self.outlines[self.chapter_idx]
            lines.append(f"\n当前位于第 {self.chapter_idx + 1} 章——{cur.get('chapter_name', cur.get('name', ''))}。")
            lines.append(f"本章概述：{cur.get('description', '')}")
        return "\n".join(lines)

    def foreshadowing_overview(self) -> str:
        """伏笔概览文本。"""
        if not self.foreshadowing:
            return "（暂无伏笔）"
        return "\n".join(
            f"- [{f.get('id', '?')}] {'[已回收]' if f.get('status') == 'resolved' else '[进行中]'} {f.get('content', '')}"
            for f in self.foreshadowing
        )

    def prev_episode_summary(self) -> str:
        """上一幕的 summary。"""
        if self.episodes:
            return self.episodes[-1].get("summary", "")
        return ""


# ═══════════════════════════════════════════════════════════════
# LangChain message ↔ dict 序列化
# ═══════════════════════════════════════════════════════════════

def _msg_to_dict(m) -> dict:
    """LangChain message → JSON-serializable dict。"""
    d = {"role": getattr(m, "type", "?")}
    content = getattr(m, "content", "")
    d["content"] = content if isinstance(content, (str, list)) else str(content)

    if hasattr(m, "tool_calls") and m.tool_calls:
        d["tool_calls"] = [{"name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                            "id": tc.get("id", "")} for tc in m.tool_calls]
    if hasattr(m, "tool_call_id") and m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


def _dict_to_msg(d: dict):
    """JSON dict → LangChain message。"""
    from langchain_core.messages import (
        SystemMessage, HumanMessage, AIMessage, ToolMessage,
    )
    role = d.get("role", "")
    content = d.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    elif role == "human":
        return HumanMessage(content=content)
    elif role == "ai":
        msg = AIMessage(content=content)
        if d.get("tool_calls"):
            msg.tool_calls = d["tool_calls"]
        return msg
    elif role == "tool":
        return ToolMessage(content=content, tool_call_id=d.get("tool_call_id", ""))
    return HumanMessage(content=str(content))
