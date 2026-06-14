"""公开消息流持久化。"""
import json
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Turn:
    turn_id: int
    type: str       # "narrate" | "speak"
    speaker: str    # "GM" | character name
    content: str


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.turns: list[Turn] = []
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        self.turns.append(Turn(**d))

    def append(self, turn: Turn):
        self.turns.append(turn)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn.__dict__, ensure_ascii=False) + "\n")

    def get_all(self) -> list[Turn]:
        return list(self.turns)

    def get_since(self, turn_id: int) -> list[Turn]:
        """获取 turn_id 之后的所有消息（不包含 turn_id 自身）。"""
        return [t for t in self.turns if t.turn_id > turn_id]

    def get_recent(self, n: int) -> list[Turn]:
        return self.turns[-n:] if len(self.turns) >= n else list(self.turns)

    def last_speak_of(self, speaker: str) -> int:
        """返回该角色最后一次发言的 turn_id，如果从未发言返回 -1。"""
        for t in reversed(self.turns):
            if t.speaker == speaker and t.type == "speak":
                return t.turn_id
        return -1

    @property
    def next_turn_id(self) -> int:
        return len(self.turns) + 1
