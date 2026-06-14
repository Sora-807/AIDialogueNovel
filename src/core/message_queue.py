"""消息队列系统 — 每个 agent 独立的消息投递与读取。"""
import uuid
from pathlib import Path

from src.config import queue_path, queues_dir
from src.storage.state import load_jsonl, append_jsonl


class MessageQueue:
    """管理所有 agent 的消息队列。

    每个 agent 有一个 .jsonl 文件，存储投递给它的消息。
    """

    def __init__(self, story_id: str):
        self._story_id = story_id
        self._dir = queues_dir(story_id)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _queue_path(self, agent_name: str) -> Path:
        return queue_path(self._story_id, agent_name)

    def _gen_message_id(self) -> str:
        return f"msg_{uuid.uuid4().hex[:8]}"

    def send(
        self,
        from_agent: str,
        content: str,
        msg_type: str,
        target_agents: list[str],
        episode_id: int = 0,
    ) -> list[str]:
        """向目标 agent 队列投递消息。

        Args:
            from_agent: 消息来源（"Narrator"、角色名、或 "System"）
            content: 消息内容
            msg_type: 消息类型（"narrate", "speak", "system"）
            target_agents: 投递目标 agent 名列表
            episode_id: 当前场景编号

        Returns:
            生成的 message_id 列表（每个目标一条，相同内容但不同 id）
        """
        ids = []
        for agent_name in target_agents:
            mid = self._gen_message_id()
            append_jsonl(self._queue_path(agent_name), {
                "message_id": mid,
                "episode_id": episode_id,
                "from": from_agent,
                "type": msg_type,
                "content": content,
            })
            ids.append(mid)
        return ids

    def get_new(
        self,
        agent_name: str,
        since_message_id: str | None,
    ) -> list[dict]:
        """获取 agent 在 since_message_id 之后的新消息。

        Args:
            agent_name: agent 名
            since_message_id: 上次已读的最后一条 message_id。
                              None 表示读取全部。

        Returns:
            新消息列表（按写入顺序）。
        """
        all_entries = load_jsonl(self._queue_path(agent_name))
        if since_message_id is None:
            return all_entries

        found = False
        result = []
        for entry in all_entries:
            if found:
                result.append(entry)
            elif entry.get("message_id") == since_message_id:
                found = True
        return result

    def get_all(self, agent_name: str) -> list[dict]:
        """获取 agent 的全部消息。"""
        return load_jsonl(self._queue_path(agent_name))

    def last_message_id(self, agent_name: str) -> str | None:
        """获取 agent 队列中最后一条消息的 id。没有消息则返回 None。"""
        entries = load_jsonl(self._queue_path(agent_name))
        if entries:
            return entries[-1].get("message_id")
        return None


