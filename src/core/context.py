"""StoryContext — 聚合 Story + Save 数据，提供带权限隔离的只读视图。"""
from dataclasses import dataclass, field
from src.storage.frontmatter import WorldviewEntry


def format_queue_messages(messages: list[dict]) -> str:
    """将消息队列条目列表格式化为 agent 可读文本。"""
    if not messages:
        return "（暂无新消息）"
    lines = []
    for m in messages:
        t = m.get("type", "")
        if t == "narrate":
            lines.append(f"【旁白】\n{m.get('content', '')}")
        elif t == "speak":
            lines.append(f"【{m.get('from', '')}】\n{m.get('content', '')}")
        elif t == "system":
            lines.append(f"[系统消息]\n{m.get('content', '')}")
        elif t == "enter":
            lines.append(f"【入场提示】\n{m.get('content', '')}")
    return "\n\n".join(lines)


@dataclass
class StoryContext:
    """持有一次 session 的全部数据，各 agent 通过 view 方法获取自己可见的切片。"""

    story_id: str
    worldview: dict[str, WorldviewEntry] = field(default_factory=dict)
    characters: dict = field(default_factory=dict)  # name → CharacterAgent
    outlines: list = field(default_factory=list)
    author_state: dict = field(default_factory=dict)
    narrator_state: dict = field(default_factory=dict)

    # ── 内部 ──

    @property
    def _granted_paths(self) -> set[str]:
        return {g.get("path", "") for g in self.narrator_state.get("worldview_grants", [])}

    @property
    def _episodes(self) -> list[dict]:
        return self.author_state.get("episodes", [])

    # ── 共享格式化 ──

    def fmt_worldview_overview(self) -> str:
        """世界观概览——分三个区块：公开世界观、已授权秘闻、未揭露秘闻。"""
        if not self.worldview:
            return "（无世界观条目）"

        public_entries = []
        granted_secrets = []
        hidden_secrets = []

        for path, e in self.worldview.items():
            line = f"- `{path}` — {e.name}：{e.description}"
            if e.is_public:
                public_entries.append(line)
            elif path in self._granted_paths:
                granted_secrets.append(line)
            else:
                hidden_secrets.append(line)

        parts = []

        if public_entries:
            parts.append("### 公开世界观\nNarrator、所有角色均自动知晓。")
            parts.extend(public_entries)
            parts.append("")

        if granted_secrets:
            parts.append("### 已授权给Narrator的世界秘闻\nNarrator 已知，但角色未必知晓——角色有独立的授权记录。")
            parts.extend(granted_secrets)
            parts.append("")

        if hidden_secrets:
            parts.append("### 仍未揭露的世界秘闻\nNarrator 不知其存在。授权需谨慎——授权 = 永久揭秘。")
            parts.extend(hidden_secrets)
            parts.append("")

        if not parts:
            return "（无世界观条目）"
        return "\n".join(parts)

    def fmt_worldview_for_narrator(self) -> str:
        """Narrator 可访问的世界观条目列表。"""
        if not self.worldview:
            return "（无可访问的世界观条目）"
        lines = ["可用世界观（用 read_worldview('路径') 查阅，留空则列出全部）：\n"]
        has_any = False
        for path, e in self.worldview.items():
            if e.is_public or path in self._granted_paths:
                lines.append(f"- `{path}` — {e.name}：{e.description}")
                has_any = True
        if not has_any:
            return "（无可访问的世界观条目）"
        return "\n".join(lines)

    def narrator_episode_context(self, episode: dict) -> str:
        """Narrator 的轻量上下文——每轮 continue 也带上。"""
        lines = []
        lines.append(f"本幕：{episode.get('episode_name', '?')}")
        chars = episode.get("characters", [])
        if chars:
            char_info = ", ".join(
                f"{c['name']}（{c.get('level', '?')}）" for c in chars if c.get("name")
            )
            lines.append(f"角色：{char_info}")
        return " | ".join(lines)

    def fmt_character_overview(self) -> str:
        """角色概览——全知版 description（给 Author）。"""
        if not self.characters:
            return "（无角色）"
        lines = []
        for name, char in self.characters.items():
            desc = char.get_profile_description()
            lines.append(f"- **{name}**：{desc}")
        return "\n".join(lines)

    def fmt_characters_intro(self, episode_chars: list[str]) -> str:
        """本幕出场角色的概览——公开描述 + 进场状态。"""
        if not episode_chars:
            return "（无角色）"
        lines = []
        for name in episode_chars:
            if name in self.characters:
                desc = self.characters[name].get_public_description()
                lines.append(f"- **{name}**：{desc}")
        return "\n".join(lines)

    def fmt_foreshadowing(self) -> str:
        """当前伏笔列表。"""
        items = self.author_state.get("long_term_foreshadowing", [])
        if not items:
            return "（暂无伏笔）"
        return "\n".join(
            f"- [{f['id']}] {'[已回收]' if f['status'] == 'resolved' else '[进行中]'} {f['content']}"
            + (f"\n  回收: {f['resolution']}" if f.get("resolution") else "")
            for f in items
        )

    def fmt_outline_progress(self, episode_index: int) -> str:
        """当前大纲进度描述。"""
        if not self.outlines:
            return "（无大纲，自由发挥）"

        lines = [f"大纲共 {len(self.outlines)} 章："]

        for o in self.outlines:
            marker = " ← 当前" if o.number == episode_index + 1 else ""
            lines.append(f"- 【{o.number}】{o.chapter_name}{marker}")

        # 当前章节概述
        if 0 <= episode_index < len(self.outlines):
            cur = self.outlines[episode_index]
            lines.append(f"\n当前位于第 {episode_index + 1} 章——{cur.chapter_name}。")
            lines.append(f"本章概述：{cur.description}")
        else:
            lines.append("\n大纲已全部完成，可以自由发挥。")

        lines.append("\n可用 read_info('outline', '章节序号或名称') 查看章节详情。")
        return "\n".join(lines)

    def fmt_transcript(self, entries: list[dict]) -> str:
        """对话记录格式化。"""
        lines = []
        for e in entries:
            if e.get("type") == "narrate":
                lines.append(f"[旁白]\n{e.get('content', '')}")
            elif e.get("type") == "speak":
                lines.append(f"[{e.get('speaker', '')}]\n{e.get('content', '')}")
        return "\n\n".join(lines)

    def prev_episode_summary(self) -> str:
        """上一幕的 summary。"""
        if self._episodes:
            return self._episodes[-1].get("summary", "")
        return ""

    # ── 视图 (供 agent prompt 构建用) ──

    def author_view(self, episode_index: int = 0) -> dict:
        """Author 的完整视图。"""
        return {
            "worldview_overview": self.fmt_worldview_overview(),
            "character_overview": self.fmt_character_overview(),
            "foreshadowing_overview": self.fmt_foreshadowing(),
            "outline_progress": self.fmt_outline_progress(episode_index),
            "prev_episode_summary": self.prev_episode_summary(),
            "total_outlines": len(self.outlines),
            "episode_index": episode_index,
        }

    def narrator_view(self, episode_chars: list[str], episode: dict | None = None) -> dict:
        """Narrator 的视图——世界观 + 角色 + 上下文。"""
        result = {
            "worldview_text": self.fmt_worldview_for_narrator(),
            "characters_text": self.fmt_characters_intro(episode_chars),
        }
        if episode:
            result["episode_context"] = self.narrator_episode_context(episode)
        return result

    # ── Reader 工厂 ──

    def make_worldview_reader(self):
        def read(path: str) -> str:
            if not path:
                return self.fmt_worldview_overview()
            entry = self.worldview.get(path)
            if entry:
                return (f"# [{path}] {entry.name}\n"
                        f"标签: {', '.join(entry.tags)}\n\n"
                        f"{entry.description}\n\n{entry.content}")
            for p, entry in self.worldview.items():
                if path in p:
                    return (f"# [{p}] {entry.name}\n"
                            f"标签: {', '.join(entry.tags)}\n\n"
                            f"{entry.description}\n\n{entry.content}")
            return f"未找到「{path}」。可用条目：\n" + "\n".join(f"  - {p}" for p in self.worldview)
        return read

    def make_character_reader(self):
        """Author 的 character reader——支持 /profile 和 /state 后缀。"""
        def read(path: str) -> str:
            if not path:
                return self.fmt_character_overview()

            # 解析路径：name/profile 或 name/state 或 name
            parts = path.split("/", 1)
            name = parts[0]
            sub = parts[1] if len(parts) > 1 else ""

            char = self.characters.get(name)
            if not char:
                return f"未找到角色「{name}」。可用角色：{', '.join(self.characters.keys())}"

            if not sub:
                return (f"read_info('character', '{name}/profile') — 全貌设定\n"
                        f"read_info('character', '{name}/state') — 当前状态")

            if sub == "profile":
                return f"# {name} 全貌设定\n\n{char.get_profile_text()}"
            elif sub == "state":
                return char.get_state_text()
            else:
                return (f"未知子路径「{sub}」。\n"
                        f"  read_info('character', '{name}/profile') — 全貌设定\n"
                        f"  read_info('character', '{name}/state') — 当前状态")
        return read

    def make_outline_reader(self):
        def read(path: str) -> str:
            if not path:
                if not self.outlines:
                    return "（无大纲）"
                return "\n".join(
                    f"- [{o.number}] {o.chapter_name} — {o.name}" for o in self.outlines)
            try:
                idx = int(path) - 1
                if 0 <= idx < len(self.outlines):
                    o = self.outlines[idx]
                    return f"# 第{o.number}章 {o.chapter_name} — {o.name}\n\n{o.content}"
            except ValueError:
                for o in self.outlines:
                    if path in o.chapter_name or path in o.name:
                        return f"# 第{o.number}章 {o.chapter_name} — {o.name}\n\n{o.content}"
            return f"未找到大纲「{path}」。"
        return read

    def make_history_reader(self):
        def read(path: str) -> str:
            episodes = self._episodes
            if not episodes:
                return "（尚无历史记录）"
            limit = 5
            if path:
                try: limit = int(path)
                except ValueError: pass
            recent = episodes[-limit:]
            lines = []
            for ep in recent:
                lines.append(
                    f"## 第{ep.get('episode_id', '?')}幕：{ep.get('episode_name', '未知')}\n"
                    f"{ep.get('summary', '（无摘要）')}")
            return "\n\n".join(lines)
        return read

    def make_foreshadowing_reader(self):
        def read(path: str) -> str:
            return self.fmt_foreshadowing()
        return read

    def make_narrator_worldview_reader(self, permitted: dict[str, WorldviewEntry]):
        """Narrator 的世界观 reader——只能看到 permitted 内的条目。"""
        def read(path: str) -> str:
            if not path:
                if not permitted:
                    return "（无可访问的世界观条目）"
                return "可访问的世界观条目：\n" + "\n".join(
                    f"  - `{p}` — {e.name}：{e.description}"
                    for p, e in permitted.items()
                )
            clean = path.lstrip("/").lstrip("\\")
            entry = permitted.get(clean)
            if entry:
                return f"# {entry.name}\n\n{entry.content}"
            available = "\n".join(f"  - {p}" for p in permitted) if permitted else "  （无）"
            return f"无权访问「{path}」。\n\n可访问条目：\n{available}"
        return read

    def make_narrator_character_reader(self, episode_chars: list[str]):
        """Narrator 的角色 reader——只列名字，查具体角色返回 state。"""
        def read(path: str) -> str:
            if not path:
                if not episode_chars:
                    return "（无出场角色）"
                lines = ["本幕出场角色："]
                for name in episode_chars:
                    if name in self.characters:
                        desc = self.characters[name].get_public_description()
                        lines.append(f"- {name} — {desc[:80]}...")
                lines.append("\n用 read_info('character', '角色名') 查看具体状态")
                return "\n".join(lines)
            if path not in episode_chars:
                return f"角色「{path}」不在本集。本集角色：{', '.join(episode_chars)}"
            char = self.characters.get(path)
            if not char:
                return f"未找到角色「{path}」。"
            return char.get_state_text()
        return read
