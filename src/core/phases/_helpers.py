"""Phase 共享工具函数。"""
import time as _time
from pathlib import Path

from src.core.emitter import InternalEvent
from src.storage.frontmatter import WorldviewEntry
from src.storage.state import append_jsonl


# ═══════════════════════════════════════════════════════════════
# 数据转换
# ═══════════════════════════════════════════════════════════════

def review_json_to_episode(data: dict) -> dict:
    """formatter JSON → engine episode dict。"""
    chars = data.get("characters", [])
    return {
        "episode_location": data.get("episode_location", ""),
        "episode_name": data.get("episode_name", ""),
        "summary": data.get("summary", ""),
        "characters": [c.get("name", "") for c in chars if c.get("name")],
        "character_setups": {
            c.get("name", ""): {
                "entry_timing": c.get("entry_timing", "episode_start"),
                "pre_episode_context": c.get("initial_state", ""),
            }
            for c in chars if c.get("name")
        },
        "desired_outcome": data.get("desired_outcome", ""),
        "detailed_outline": data.get("detailed_outline", ""),
        "worldview_grants": [{"path": p, "note": "", "content": ""}
                             for p in data.get("worldview_grants", [])],
        "author_notes": data.get("author_notes", ""),
    }


def apply_summary_json(data: dict, author_state: dict, episode_count: int):
    """formatter 总结 JSON → author_state。返回 (advance_chapter, gap)。"""
    if data.get("episode_summary"):
        episodes = author_state.setdefault("episodes", [])
        if episodes:
            episodes[-1]["summary"] = data["episode_summary"]
    if data.get("plot_update"):
        author_state["short_term_plot"] = data["plot_update"]
    advance = data.get("advance_chapter", False) if isinstance(data.get("advance_chapter"), bool) else False
    gap = data.get("gap", "")
    foreshadowing = data.get("foreshadowing", {})
    if foreshadowing:
        f_list = author_state.setdefault("long_term_foreshadowing", [])
        for content in foreshadowing.get("added", []):
            f_list.append({"id": str(len(f_list)+1), "content": content,
                           "status": "pending", "created_scene": episode_count,
                           "resolved_scene": None})
        for fid in foreshadowing.get("resolved", []):
            for item in f_list:
                if str(item.get("id")) == str(fid):
                    item["status"] = "resolved"
                    item["resolved_scene"] = episode_count
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
