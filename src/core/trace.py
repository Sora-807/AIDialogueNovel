"""Agent 消息追踪 — trace/{ts}/episode_{id}_{name}/{agent}/round_{n}/。"""
import json
from pathlib import Path
from datetime import datetime


class RoundLogger:
    """trace/{timestamp}/episode_{id:03d}_{name}/{agent}/round_{n}/ 下存 step 文件。

    两个触发路径：
    1. begin_episode(id, name) → 新建 episode 目录，全部 agent 重置 round→0, cursor→0
    2. on_context_changed(agent, version, reason) → 同一 episode 目录，该 agent 的 round+1, cursor→0
    """

    def __init__(self, logs_root: Path):
        self.root = logs_root
        self.root.mkdir(parents=True, exist_ok=True)
        self._ep_dir: str = ""                    # "episode_001_食堂风波"
        self._round: dict[str, int] = {}          # agent → round 号
        self._cursor: dict[str, int] = {}         # agent → messages 游标
        self._seq: dict[str, int] = {}            # agent → 文件序号

    # ── 路径 ──

    def _agent_dir(self, agent: str) -> Path:
        r = self._round.get(agent, 0)
        return self.root / self._ep_dir / agent / f"round_{r:03d}"

    # ── episode 切换 ──

    def begin_episode(self, ep_id: int, ep_name: str):
        """新 episode → 新目录，全部 agent 重置。ep_name 后续可通过 set_episode_name 更新。"""
        safe = ep_name.replace("/", "_").replace("\\", "_")[:40] if ep_name else ""
        if safe:
            self._ep_dir = f"episode_{ep_id:03d}_{safe}"
        else:
            self._ep_dir = f"episode_{ep_id:03d}"
        self._round.clear()
        self._cursor.clear()
        self._seq.clear()

    def set_episode_name(self, ep_name: str):
        """Author 产出名称后调用，补全 episode 目录名。"""
        if not self._ep_dir:
            return
        safe = ep_name.replace("/", "_").replace("\\", "_")[:40]
        new_dir = f"{self._ep_dir}_{safe}" if safe else self._ep_dir
        old_path = self.root / self._ep_dir
        new_path = self.root / new_dir
        if old_path.exists() and old_path != new_path:
            old_path.rename(new_path)
        self._ep_dir = new_dir

    # ── 上下文变更 ──

    def on_context_changed(self, agent: str, version: int, reason: str):
        """Agent 上下文截断 → 同一 episode 目录，该 agent round+1, 游标归零。"""
        self._round[agent] = self._round.get(agent, 0) + 1
        self._cursor[agent] = 0
        self._seq[agent] = 0

    # ── 写 step ──

    def _next_seq(self, agent: str) -> int:
        self._seq[agent] = self._seq.get(agent, 0) + 1
        return self._seq[agent]

    def write_step(self, agent: str, step: int, messages: list, thinking: str,
                   calls: list[dict]):
        if not self._ep_dir:
            return  # 还没调用 begin_episode

        d = self._agent_dir(agent)
        d.mkdir(parents=True, exist_ok=True)
        cur = self._cursor.get(agent, 0)

        # 游标之后的所有消息，按类型全量写入
        for m in messages[cur:]:
            t = getattr(m, "type", "")
            text = getattr(m, "content", "") or ""

            if t in ("system", "human"):
                if not text.strip():
                    continue
                n = self._next_seq(agent)
                kind = {"system": "system", "human": "user"}.get(t, t)
                (d / f"{n:03d}_{kind}.txt").write_text(text, encoding="utf-8")
            elif t == "ai":
                n = self._next_seq(agent)
                record = {"thinking": text}
                if hasattr(m, "tool_calls") and m.tool_calls:
                    record["tool_calls"] = [
                        {"name": tc.get("name", ""), "args": tc.get("args", {}),
                         "id": tc.get("id", "")}
                        for tc in m.tool_calls
                    ]
                (d / f"{n:03d}_ai.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            elif t == "tool":
                n = self._next_seq(agent)
                record = {
                    "tool_call_id": getattr(m, "tool_call_id", ""),
                    "content": text[:2000],
                }
                (d / f"{n:03d}_tool.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        self._cursor[agent] = len(messages)

    # ── 错误 ──

    def error(self, agent: str, text: str):
        if not self._ep_dir:
            return
        d = self._agent_dir(agent)
        d.mkdir(parents=True, exist_ok=True)
        (d / "error.txt").write_text(text, encoding="utf-8")

    def fatal(self, msg: str):
        p = self.root / "errors.log"
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        p.write_text(old + f"[{datetime.now():%H:%M:%S}] {msg}\n", encoding="utf-8")
