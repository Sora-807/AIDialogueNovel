"""Session — 装配引擎运行时，以 Universe 为唯一状态中心。

数据层级：
  Universe        ← 唯一可变状态（可序列化 = 完美 checkpoint）
  StoryContext    ← 格式化逻辑（从 Universe 读取，产出 Agent prompt 文本）
  Agents          ← 运行时实例（引用 Universe，通过它读写一切）
"""
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.author import AuthorAgent
from src.agents.narrator import NarratorAgent
from src.agents.character import CharacterAgent
from src.core.universe import Universe
from src.core.context import StoryContext
from src.core.trace import RoundLogger
from src.core.logger import get_logger
from src.core.state_machine import EpisodeState
from src.core.emitter import EventEmitter
from src.config import (
    save_dir, worldview_dir, outline_dir, history_path,
    list_characters, get_user_character,
)
from src.storage.frontmatter import load_worldview_entries, load_outlines
from src.storage.state import load_json, save_json


# ═══════════════════════════════════════════════════════════════
# 加载：Story 源数据 → Universe
# ═══════════════════════════════════════════════════════════════

def _worldview_entry_to_dict(entry) -> dict:
    """WorldviewEntry → Universe 兼容 dict。"""
    return {
        "path": entry.path,
        "tags": list(entry.tags),
        "name": entry.name,
        "description": entry.description,
        "content": entry.content,
        "is_public": entry.is_public,
    }


def _outline_entry_to_dict(entry) -> dict:
    """OutlineEntry → Universe 兼容 dict。"""
    return {
        "number": entry.number,
        "chapter_name": entry.chapter_name,
        "name": entry.name,
        "description": entry.description,
        "content": entry.content,
    }


def _load_story_data(u: Universe, story_id: str):
    """从 Story 源文件加载世界观、大纲、角色信息到 Universe。"""
    # 世界观
    wv_entries = load_worldview_entries(worldview_dir(story_id))
    u.worldviews = {p: _worldview_entry_to_dict(e) for p, e in wv_entries.items()}

    # 大纲
    ol_entries = load_outlines(outline_dir(story_id))
    u.outlines = [_outline_entry_to_dict(e) for e in ol_entries]

    # 角色
    u.characters = {}
    for name in list_characters(story_id):
        profile_text, init_state_text = _load_character_texts(story_id, name)
        u.characters[name] = {
            "profile_text": profile_text,
            "initial_state_text": init_state_text,
        }
        # 角色运行时状态（如果有存档则加载，否则用初始状态）
        state_text = _load_character_saved_state(story_id, name) or init_state_text
        u.character_states[name] = state_text

    u.user_character = get_user_character(story_id) or ""


def _load_character_texts(story_id: str, name: str) -> tuple[str, str]:
    """读取角色的 profile.md 和初始 state.md。"""
    from src.config import story_dir
    base = story_dir(story_id) / "characters" / name
    profile = ""
    init_state = ""
    if (base / "profile.md").exists():
        profile = (base / "profile.md").read_text(encoding="utf-8").strip()
    if (base / "initial_state.md").exists():
        init_state = (base / "initial_state.md").read_text(encoding="utf-8").strip()
    elif not init_state:
        init_state = f"# 人物状态\n\n姓名：{name}\n（无状态信息）"
    return profile, init_state


def _load_character_saved_state(story_id: str, name: str) -> str | None:
    """读取角色在 save 中的 state.md。"""
    from src.config import character_state_path
    sp = character_state_path(story_id, name)
    if sp.exists():
        return sp.read_text(encoding="utf-8").strip()
    return None


# ═══════════════════════════════════════════════════════════════
# 恢复：从 checkpoint（保存的 Universe）恢复
# ═══════════════════════════════════════════════════════════════

def _universe_checkpoint_path(story_id: str) -> Path:
    return save_dir(story_id) / "universe.json"


def _try_restore_checkpoint(u: Universe, story_id: str, log) -> bool:
    """尝试从保存的 Universe 恢复。成功返回 True。"""
    ckpt_path = _universe_checkpoint_path(story_id)
    if not ckpt_path.exists():
        # fallback: 旧 session.json → 提取字段恢复
        return _try_restore_legacy(u, story_id, log)

    try:
        ckpt = Universe.from_dict(load_json(ckpt_path, {}))
    except Exception as e:
        log.warning("【恢复】universe.json 损坏: %s, 回退到旧格式", e)
        return _try_restore_legacy(u, story_id, log)

    # 恢复引擎状态
    u.state = ckpt.state
    u.chapter_idx = ckpt.chapter_idx
    u.episode_count = ckpt.episode_count
    u.episodes = ckpt.episodes
    u.foreshadowing = ckpt.foreshadowing
    u.short_term_plot = ckpt.short_term_plot
    u.author_notes = ckpt.author_notes
    u.author_working_sections = ckpt.author_working_sections
    u.author_working_review = ckpt.author_working_review
    u.stage = ckpt.stage
    u.worldview_grants = ckpt.worldview_grants
    u.configured_episode_id = ckpt.configured_episode_id
    u.character_states = ckpt.character_states
    u.messages = ckpt.messages
    u.read_positions = ckpt.read_positions
    u.conversations = ckpt.conversations
    u.meta = ckpt.meta
    u._msg_counter = ckpt._msg_counter

    log.info("【恢复】Universe 已恢复 | 状态=%s | 第%d章 | %d幕 | %d条消息 | %d个对话",
             u.state, u.chapter_idx + 1, u.episode_count,
             len(u.messages), len(u.conversations))
    return True


def _try_restore_legacy(u: Universe, story_id: str, log) -> bool:
    """从旧 session.json 恢复（兼容迁移）。"""
    from src.config import session_path, author_state_path, narrator_state_path

    sp = session_path(story_id)
    if not sp.exists():
        return False

    data = load_json(sp, {})
    author = data.get("author", {})
    narrator = data.get("narrator", {})

    u.state = data.get("state", "planning")
    u.chapter_idx = data.get("chapter_idx", 0)
    u.episode_count = data.get("episode_count", 0)
    u.episodes = author.get("episodes", [])
    u.foreshadowing = author.get("long_term_foreshadowing", [])
    u.short_term_plot = author.get("short_term_plot", "")
    u.author_notes = author.get("_notes", [])
    u.stage = narrator.get("stage_characters", [])
    u.worldview_grants = narrator.get("worldview_grants", [])
    u.configured_episode_id = narrator.get("configured_episode_id", 0)

    # 旧 agent checkpoint 恢复 conversations
    _try_restore_legacy_conversations(u, story_id, log)

    log.info("【恢复·旧格式】session.json → Universe | 状态=%s | 第%d章 | %d幕",
             u.state, u.chapter_idx + 1, u.episode_count)
    return True


def _try_restore_legacy_conversations(u: Universe, story_id: str, log):
    """从旧 checkpoint/{Agent}.json 恢复对话历史到 Universe。
    直接读 JSON 保留 dict 格式——不经过 _dict_to_msg 反序列化，
    否则 load_conversation() 会二次反序列化导致 AttributeError。"""
    import json
    from src.core.checkpoint import _ckpt_dir
    for agent_name in ["Author", "Narrator"]:
        path = _ckpt_dir(story_id) / f"{agent_name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            if msgs:
                u.conversations[agent_name] = msgs
                log.info("【恢复·旧格式】%s: %d 条消息", agent_name, len(msgs))
    for name in u.characters:
        path = _ckpt_dir(story_id) / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            msgs = data.get("messages", [])
            if msgs:
                u.conversations[name] = msgs


# ═══════════════════════════════════════════════════════════════
# Session
# ═══════════════════════════════════════════════════════════════

@dataclass
class Session:
    """引擎运行时全部数据。Universe 是唯一可变状态中心。"""

    story_id: str
    universe: Universe           # ← 唯一状态中心
    characters: dict             # name → CharacterAgent（运行时实例）
    author: AuthorAgent
    narrator: NarratorAgent
    log: any
    round_log: RoundLogger
    hist_path: Path

    # 外部注入
    emitter: EventEmitter = None
    debug: bool = False
    user_turn_callback: any = None
    max_episodes: int = 0
    _token_cb: any = None
    _step_cb: any = None
    is_restart: bool = False

    @classmethod
    def load(cls, story_id: str) -> "Session":
        """加载所有数据，返回就绪的 Session。"""
        log = get_logger(story_id)
        log.info("══════════════ 会话启动 ══════════════")

        # 1. 创建 Universe + 加载 Story 源数据
        u = Universe()
        _load_story_data(u, story_id)
        log.info("【加载】世界观 %d 条 | 大纲 %d 章 | 角色 %d 人",
                 len(u.worldviews), len(u.outlines), len(u.characters))

        # 2. 尝试恢复 checkpoint
        save_dir(story_id).mkdir(parents=True, exist_ok=True)
        restored = _try_restore_checkpoint(u, story_id, log)

        user_char = u.user_character

        try:
            state = EpisodeState(u.state)
        except ValueError:
            state = EpisodeState.PLANNING

        log.info("【加载】状态=%s | 第%d章 | 已写%d幕 | 用户角色=%s",
                 state.value, u.chapter_idx + 1, u.episode_count, user_char or "无")

        # 3. 创建运行时 Agent 实例
        log.info("【初始化】创建角色 Agent…")
        characters = _create_characters(story_id, u, log)

        log.info("【初始化】创建 Author、Narrator…")
        author = AuthorAgent(story_id, universe=u)
        author.load_state_from_universe()

        # Author 的 reader 注册（需要 StoryContext 提供格式化逻辑）
        ctx = StoryContext(
            story_id=story_id,
            worldview=Session._make_worldview_entries(u),
            characters=characters,
            outlines=Session._make_outline_entries(u),
            author_state=Session._make_author_state(u),
            narrator_state=Session._make_narrator_state(u),
        )
        author.register_reader("worldview", ctx.make_worldview_reader())
        author.register_reader("character", ctx.make_character_reader())
        author.register_reader("outline", ctx.make_outline_reader())

        narrator = NarratorAgent(story_id, universe=u)
        narrator.load_state_from_universe()

        # DEBUG: 无用户角色模式，由环境变量 DEBUG_NO_USER=1 控制
        import os
        if os.environ.get("DEBUG_NO_USER") == "1":
            u.user_character = ""
            log.info("【调试】DEBUG_NO_USER=1，用户角色已禁用，全 AI 模式")

        hist_path = history_path(story_id)

        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        round_log = RoundLogger(save_dir(story_id) / "trace" / ts)

        log.info("【初始化】完成")

        return cls(
            story_id=story_id,
            universe=u,
            characters=characters,
            author=author,
            narrator=narrator,
            log=log,
            round_log=round_log,
            hist_path=hist_path,
            is_restart=restored,
        )

    # ── 静态转换方法（classmethod 中也用到） ──

    @staticmethod
    def _make_worldview_entries(u: Universe) -> dict:
        from src.storage.frontmatter import WorldviewEntry
        return {
            p: WorldviewEntry(
                path=p, tags=w.get("tags", []),
                name=w.get("name", ""), description=w.get("description", ""),
                content=w.get("content", ""), is_public=w.get("is_public", True),
            )
            for p, w in u.worldviews.items()
        }

    @staticmethod
    def _make_outline_entries(u: Universe) -> list:
        from src.storage.frontmatter import OutlineEntry
        return [
            OutlineEntry(
                number=o.get("number", 0), chapter_name=o.get("chapter_name", ""),
                name=o.get("name", ""), description=o.get("description", ""),
                content=o.get("content", ""), file_path=Path(),
            )
            for o in u.outlines
        ]

    @staticmethod
    def _make_author_state(u: Universe) -> dict:
        return {
            "episodes": u.episodes,
            "long_term_foreshadowing": u.foreshadowing,
            "short_term_plot": u.short_term_plot,
            "_notes": u.author_notes,
        }

    @staticmethod
    def _make_narrator_state(u: Universe) -> dict:
        return {
            "stage_characters": u.stage,
            "worldview_grants": u.worldview_grants,
            "configured_episode_id": u.configured_episode_id,
        }

    # ── 便捷属性（兼容旧代码，逐步迁移） ──

    @property
    def user_char(self) -> str:
        return self.universe.user_character

    @property
    def state(self) -> EpisodeState:
        try:
            return EpisodeState(self.universe.state)
        except ValueError:
            return EpisodeState.PLANNING

    @state.setter
    def state(self, v: EpisodeState):
        self.universe.state = v.value

    @property
    def chapter_idx(self) -> int:
        return self.universe.chapter_idx

    @chapter_idx.setter
    def chapter_idx(self, v: int):
        self.universe.chapter_idx = v

    @property
    def episode_count(self) -> int:
        return self.universe.episode_count

    @episode_count.setter
    def episode_count(self, v: int):
        self.universe.episode_count = v

    @property
    def author_state(self) -> dict:
        return self._make_author_state(self.universe)

    @property
    def narrator_state(self) -> dict:
        return self._make_narrator_state(self.universe)

    # ── 数据访问（旧代码兼容） ──

    @property
    def worldview(self) -> dict:
        return self._make_worldview_entries(self.universe)

    @property
    def outlines(self) -> list:
        return self._make_outline_entries(self.universe)

    @property
    def ctx(self) -> StoryContext:
        """兼容旧代码：基于 Universe 创建 StoryContext。"""
        return StoryContext(
            story_id=self.story_id,
            worldview=self.worldview,
            characters=self.characters,
            outlines=self.outlines,
            author_state=self.author_state,
            narrator_state=self.narrator_state,
        )

    @property
    def mq(self):
        """兼容旧代码：返回 Universe 本身（它有 send/poll/get_new/mark_read）。"""
        return self.universe

    # ── 持久化 ──

    def save(self):
        """持久化 Universe 到 universe.json。"""
        path = _universe_checkpoint_path(self.story_id)
        save_json(path, self.universe.to_dict())
        # 同步保存各角色 state.md
        for char in self.characters.values():
            char.save_state()

    def advance_to(self, new_state: EpisodeState):
        """状态转换 + 自动保存。"""
        old = self.state
        self.state = new_state
        self.log.info("【状态】%s → %s", old.value, new_state.value)
        self.save()


# ═══════════════════════════════════════════════════════════════
# 角色 Agent 创建
# ═══════════════════════════════════════════════════════════════

def _create_characters(story_id: str, u: Universe, log) -> dict:
    """创建所有 CharacterAgent 实例，从 Universe 恢复状态。"""
    characters = {}
    for name in u.characters:
        char = CharacterAgent(story_id, name, universe=u)
        char.load_state()
        # 从 Universe 恢复对话历史
        char.load_state_from_universe()
        characters[name] = char
        if u.has_conversation(name):
            log.info("【恢复】%s: %d 条历史消息", name,
                     len(u.conversations.get(name, [])))
    return characters
