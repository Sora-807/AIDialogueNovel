"""Phase 共享工具函数。"""
import time as _time
from pathlib import Path

from src.core.emitter import InternalEvent
from src.storage.frontmatter import WorldviewEntry
from src.storage.state import append_jsonl


# ═══════════════════════════════════════════════════════════════
# 数据转换
# ═══════════════════════════════════════════════════════════════

def apply_summary_json(data: dict, universe, episode_count: int):
    """formatter 总结 JSON → Universe。返回 (advance_chapter, gap)。
    universe 可以是 Universe 对象或兼容的 dict。"""
    u = universe
    if data.get("episode_summary"):
        if u.episodes:
            u.episodes[-1]["summary"] = data["episode_summary"]
    if data.get("plot_update"):
        u.short_term_plot = data["plot_update"]
    advance = data.get("advance_chapter", False) if isinstance(data.get("advance_chapter"), bool) else False
    gap = data.get("gap", "")
    foreshadowing = data.get("foreshadowing", {})
    if foreshadowing:
        f_list = list(u.foreshadowing)
        for content in foreshadowing.get("added", []):
            f_list.append({"id": str(len(f_list)+1), "content": content,
                           "status": "pending", "created_scene": episode_count,
                           "resolved_scene": None})
        for fid in foreshadowing.get("resolved", []):
            for item in f_list:
                if str(item.get("id")) == str(fid):
                    item["status"] = "resolved"
                    item["resolved_scene"] = episode_count
        u.foreshadowing = f_list
    return advance, gap


def build_permitted_worldview(all_entries: dict[str, "WorldviewEntry"],
                               grants: list[dict]) -> dict[str, "WorldviewEntry"]:
    """public + 已授权 → Narrator 可见世界观。"""
    permitted = {p: e for p, e in all_entries.items() if e.is_public}
    for g in grants:
        p = g.get("path", "")
        if p and p in all_entries:
            permitted[p] = all_entries[p]
    return permitted


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════


def now() -> float:
    return _time.time()


def elapsed(start: float) -> str:
    return f"{now() - start:.1f}s"


def log_tools(log, agent: str, calls: list[dict]):
    """记录工具调用（debug 级别）。仅记录异常。"""
    for c in calls:
        tool = c.get("tool", "")
        args = c.get("args", {})
        result = str(c.get("_result", ""))[:200]
        if c.get("_invalid"):
            log.warning("【%s】无效调用 %s(%s) → %s", agent, tool, args, result)
        elif tool == "__error__":
            log.error("【%s】LLM 错误: %s", agent, result)


def append_history(path: Path, msg_type: str, speaker: str, content: str):
    append_jsonl(path, {"type": msg_type, "speaker": speaker, "content": content,
                        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S")})


async def emit_internal(emitter, agent, calls, debug):
    if not debug:
        return
    for c in calls:
        await emitter.on_internal(InternalEvent(
            agent=agent, tool=c.get("tool", ""), args=c.get("args", {}),
            result=c.get("_result", "")[:300], is_invalid=c.get("_invalid", False)))


def _parse_calls_from_messages(messages: list, tool_names: set[str]) -> list[dict]:
    """从消息历史末尾解析最后一次的工具调用记录。
    用于重启恢复——Agent 已退出但需要解析其 calls 来驱动后续流程。
    自动标记 _invalid=True 当 ToolMessage 包含验证错误。"""
    # 验证错误特征文本（各 Agent validate_tool 返回的错误）
    _VALIDATION_MARKERS = [
        "必须先调", "不能为空", "需要提供", "必须是", "不在可用角色列表中",
        "未知工具", "工具执行出错",
    ]

    calls = []
    # 从后往前找最后一个有 tool_calls 的 AI 消息
    ai_msg = None
    for m in reversed(messages):
        if getattr(m, "type", "") == "ai" and hasattr(m, "tool_calls") and m.tool_calls:
            ai_msg = m
            break
    if not ai_msg:
        return calls

    # 该 AI 消息之后的所有 ToolMessage
    ai_idx = messages.index(ai_msg)
    tool_msgs = {}
    for m in messages[ai_idx + 1:]:
        if getattr(m, "type", "") == "tool" and hasattr(m, "tool_call_id"):
            tool_msgs[m.tool_call_id] = getattr(m, "content", "")

    for tc in ai_msg.tool_calls:
        name = tc.get("name", "")
        args = tc.get("args", {})
        tid = tc.get("id", "")
        result = tool_msgs.get(tid, "")
        record = {"tool": name, "args": args, "_result": result,
                  "_from_checkpoint": True}  # 标记：跳过重复的副作用
        # 检测验证错误
        if any(marker in result for marker in _VALIDATION_MARKERS):
            record["_invalid"] = True
        calls.append(record)

    return calls
