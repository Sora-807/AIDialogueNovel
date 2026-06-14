"""断点 — LLM 调用级持久化，记录引擎位置 + Agent 完整状态。

保存策略：
  1. before_llm 钩子 → 保存（LLM 调用前的安全点）
  2. on_step 回调 → 保存（工具执行后，确保 exit 步骤不丢失）

两个保存点互为补充：before_llm 保 LLM 调用中崩溃可重试，
on_step 保工具执行后崩溃不丢结果。
"""
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
    """保存引擎断点。"""
    path = _ckpt_dir(story_id) / "engine.json"
    path.write_text(json.dumps(kwargs, ensure_ascii=False, indent=2), encoding="utf-8")


def load_engine_checkpoint(story_id: str) -> dict | None:
    """读取上次引擎断点。不存在返回 None。"""
    path = _ckpt_dir(story_id) / "engine.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ═══════════════════════════════════════════════════════════════
# Agent 完整状态
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


def load_agent_checkpoint(story_id: str, agent_name: str) -> dict | None:
    """加载 Agent 完整状态。不存在返回 None。"""
    path = _ckpt_dir(story_id) / f"{agent_name}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    # 将 messages 反序列化为 LangChain 对象
    if "messages" in data:
        data["messages"] = [_dict_to_msg(m) for m in data["messages"]]
    return data


# ── 兼容别名（引擎迁移用） ──

def save_agent_state(story_id: str, agent_name: str, messages: list):
    """旧接口：保存消息历史。内部转为完整 checkpoint。"""
    path = _ckpt_dir(story_id) / f"{agent_name}.json"
    data = {"messages": [_msg_to_dict(m) for m in messages]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_agent_state(story_id: str, agent_name: str) -> list:
    """旧接口：仅加载消息历史。"""
    ckpt = load_agent_checkpoint(story_id, agent_name)
    if ckpt:
        return ckpt.get("messages", [])
    return []
