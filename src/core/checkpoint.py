"""断点 — LLM 调用级持久化，记录引擎位置 + Agent 消息历史。"""
import json
from pathlib import Path
from src.config import save_dir


def _ckpt_dir(story_id: str) -> Path:
    d = save_dir(story_id) / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════════════
# 引擎位置
# ═══════════════════════════════════════════════════════════════

def save_engine_checkpoint(story_id: str, **kwargs):
    """保存引擎断点。调用时机：每次 agent LLM 调用前。"""
    path = _ckpt_dir(story_id) / "engine.json"
    path.write_text(json.dumps(kwargs, ensure_ascii=False, indent=2), encoding="utf-8")


def load_engine_checkpoint(story_id: str) -> dict | None:
    """读取上次引擎断点。不存在返回 None。"""
    path = _ckpt_dir(story_id) / "engine.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ═══════════════════════════════════════════════════════════════
# Agent 消息历史
# ═══════════════════════════════════════════════════════════════

def _msg_to_dict(m) -> dict:
    """LangChain message → JSON dict。"""
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


def save_agent_state(story_id: str, agent_name: str, messages: list):
    """保存 Agent 的消息历史。排除末尾的 HumanMessage（恢复时会重新发出）。"""
    msgs = list(messages)
    if msgs and getattr(msgs[-1], "type", "") == "human":
        msgs = msgs[:-1]
    path = _ckpt_dir(story_id) / f"{agent_name}.json"
    data = {"messages": [_msg_to_dict(m) for m in msgs]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_agent_state(story_id: str, agent_name: str) -> list:
    """加载 Agent 的消息历史。不存在返回空列表。"""
    path = _ckpt_dir(story_id) / f"{agent_name}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return [_dict_to_msg(m) for m in data.get("messages", [])]
    return []
