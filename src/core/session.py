"""Session — 聚合引擎所有运行时数据 + 加载/保存。"""
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.author import AuthorAgent
from src.agents.narrator import NarratorAgent
from src.agents.character import CharacterAgent
from src.core.context import StoryContext
from src.core.message_queue import MessageQueue
from src.core.trace import RoundLogger
from src.core.logger import get_logger
from src.core.state_machine import EpisodeState, GapType
from src.core.emitter import EventEmitter
from src.config import (
    save_dir, worldview_dir, outline_dir, history_path,
    session_path, author_state_path, narrator_state_path,
    list_characters, get_user_character,
)
from src.storage.frontmatter import load_worldview_entries, load_outlines
from src.storage.state import load_json, save_json


@dataclass
class Session:
    """引擎运行时全部数据。由 Session.load() 创建。"""

    story_id: str
    user_char: str
    worldview: dict
    outlines: list
    characters: dict   # name → CharacterAgent
    ctx: StoryContext
    mq: MessageQueue
    author: AuthorAgent
    narrator: NarratorAgent
    log: any
    round_log: RoundLogger
    hist_path: Path

    # 外部注入（load 时不设）
    emitter: EventEmitter = None
    debug: bool = False
    user_turn_callback: any = None
    max_episodes: int = 0
    _token_cb: any = None
    _step_cb: any = None
    is_restart: bool = False

    # 引擎状态
    state: EpisodeState = EpisodeState.PLANNING
    chapter_idx: int = 0
    episode_count: int = 0
    author_state: dict = field(default_factory=dict)
    narrator_state: dict = field(default_factory=dict)

    @classmethod
    def load(cls, story_id: str) -> "Session":
        """加载所有数据，返回就绪的 Session。"""
        log = get_logger(story_id)
        log.info("══════════════ 会话启动 ══════════════")
        log.info("【加载】读取世界观、大纲、角色…")

        worldview = load_worldview_entries(worldview_dir(story_id))
        outlines = load_outlines(outline_dir(story_id))
        char_names = list_characters(story_id)
        log.info("【加载】世界观 %d 条 | 大纲 %d 章 | 角色 %d 人",
                 len(worldview), len(outlines), len(char_names))

        log.info("【加载】创建角色 Agent…")
        characters = {name: CharacterAgent(story_id, name) for name in char_names}
        for char in characters.values():
            char.load_state()

        user_char = get_user_character(story_id)

        # ── 加载引擎状态 ──
        save_dir(story_id).mkdir(parents=True, exist_ok=True)
        session_data = _load_session_state(story_id)

        author_state = session_data.get("author", {})
        if not isinstance(author_state.get("episodes"), list):
            author_state["episodes"] = []
        narrator_state = session_data.get("narrator", {})

        chapter_idx = session_data.get("chapter_idx", 0)
        episode_count = session_data.get("episode_count", 0)
        state_raw = session_data.get("state", "episode_creating")
        try:
            state = EpisodeState(state_raw)
        except ValueError:
            state = EpisodeState.PLANNING

        # ── StoryContext ──
        ctx = StoryContext(
            story_id=story_id, worldview=worldview, characters=characters,
            outlines=outlines, author_state=author_state, narrator_state=narrator_state,
        )

        log.info("【加载】状态=%s | 第%d章 | 已写%d幕 | 用户角色=%s",
                 state.value, chapter_idx + 1, episode_count, user_char or "无")

        # ── 创建 Agent ──
        log.info("【初始化】创建消息队列、Author、Narrator…")
        mq = MessageQueue(story_id)

        author = AuthorAgent(story_id)
        author._notes = author_state.get("_notes", [])
        author._user_character = user_char
        author.register_reader("worldview", ctx.make_worldview_reader())
        author.register_reader("character", ctx.make_character_reader())
        author.register_reader("outline", ctx.make_outline_reader())

        narrator = NarratorAgent(story_id)
        hist_path = history_path(story_id)

        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        round_log = RoundLogger(save_dir(story_id) / "trace" / ts)

        # ── 恢复 Agent 消息历史（断点恢复） ──
        from src.core.checkpoint import load_agent_state
        restored = False
        for agent in [author, narrator, *characters.values()]:
            msgs = load_agent_state(story_id, agent.agent_name)
            if msgs:
                agent._messages = msgs
                log.info("【恢复】%s: %d 条历史消息", agent.agent_name, len(msgs))
                restored = True

        log.info("【初始化】完成")

        return cls(
            story_id=story_id,
            user_char=user_char,
            worldview=worldview,
            outlines=outlines,
            characters=characters,
            ctx=ctx,
            mq=mq,
            author=author,
            narrator=narrator,
            log=log,
            round_log=round_log,
            hist_path=hist_path,
            state=state,
            chapter_idx=chapter_idx,
            episode_count=episode_count,
            author_state=author_state,
            narrator_state=narrator_state,
            is_restart=restored,
        )

    def save(self):
        """持久化引擎状态到 session.json。"""
        data = {
            "state": self.state.value,
            "chapter_idx": self.chapter_idx,
            "episode_count": self.episode_count,
            "author": {
                **self.author_state,
                "_notes": getattr(self.author, "_notes", []),
            },
            "narrator": self.narrator_state,
        }
        save_json(session_path(self.story_id), data)

    def advance_to(self, new_state: EpisodeState):
        """状态转换 + 自动保存。"""
        old = self.state
        self.state = new_state
        self.log.info("【状态】%s → %s", old.value, new_state.value)
        self.save()


def _load_session_state(story_id: str) -> dict:
    """加载引擎状态。优先 session.json，fallback 到分离的 author.json + narrator.json。"""
    sp = session_path(story_id)
    if sp.exists():
        return load_json(sp, {})

    # 兼容旧格式：合并 author.json + narrator.json
    author = load_json(author_state_path(story_id), {
        "story_id": story_id, "chapter_index": 0, "episode_count": 0,
        "state": "episode_creating",
        "episodes": [], "short_term_plot": "", "long_term_foreshadowing": [],
    })
    narrator = load_json(narrator_state_path(story_id), {
        "current_episode": 1, "next_speaker": "", "last_read_message_id": None,
    })
    return {
        "state": author.get("state", "episode_creating"),
        "chapter_idx": author.get("chapter_index", 0),
        "episode_count": author.get("episode_count", 0),
        "author": author,
        "narrator": narrator,
    }
