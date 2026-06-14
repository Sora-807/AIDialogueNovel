"""全局配置 — Story 与 Save 路径分离。"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

STORIES_ROOT = ROOT / "stories"
SAVES_ROOT = ROOT / "saves"


# ── LLM 配置 ──

from dataclasses import dataclass


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    use_stream: bool = True  # 默认流式，不支持 tool_call 的模型请设 False


_llm_config_cache: LLMConfig | None = None


def load_llm_config() -> LLMConfig:
    global _llm_config_cache
    if _llm_config_cache is None:
        _llm_config_cache = LLMConfig(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.environ.get("LLM_MODEL", "gpt-4o"),
            use_stream=os.environ.get("LLM_STREAM", "true").lower() != "false",
        )
    return _llm_config_cache


# ── Story 路径（不可变源数据） ──

def story_dir(story_id: str) -> Path:
    return STORIES_ROOT / story_id


def story_config_path(story_id: str) -> Path:
    return story_dir(story_id) / "story.json"


def worldview_dir(story_id: str) -> Path:
    return story_dir(story_id) / "worldview"


def outline_dir(story_id: str) -> Path:
    return story_dir(story_id) / "outline"


def character_profile_path(story_id: str, name: str) -> Path:
    """固定隐藏人设路径（story 中）。"""
    return story_dir(story_id) / "characters" / name / "profile.md"


def load_story_json(story_id: str) -> dict:
    """读取 story.json。"""
    import json
    path = story_config_path(story_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_user_character(story_id: str) -> str:
    """返回 story 中的 user_character 字段。"""
    return load_story_json(story_id).get("user_character", "")


def list_characters(story_id: str) -> list[str]:
    """返回故事下所有角色名（目录名即为角色名）。"""
    chars_dir = story_dir(story_id) / "characters"
    if not chars_dir.exists():
        return []
    return [
        d.name for d in chars_dir.iterdir()
        if d.is_dir() and (d / "profile.md").exists()
    ]


# ── Save 路径（运行时存档） ──

def save_dir(story_id: str) -> Path:
    return SAVES_ROOT / story_id


def author_state_path(story_id: str) -> Path:
    return save_dir(story_id) / "author.json"


def narrator_state_path(story_id: str) -> Path:
    return save_dir(story_id) / "narrator.json"


def queues_dir(story_id: str) -> Path:
    return save_dir(story_id) / "queues"


def queue_path(story_id: str, agent_name: str) -> Path:
    return queues_dir(story_id) / f"{agent_name}.jsonl"


def history_path(story_id: str) -> Path:
    return save_dir(story_id) / "history.jsonl"


def session_path(story_id: str) -> Path:
    """统一引擎状态文件（合并 author + narrator 状态）。"""
    return save_dir(story_id) / "session.json"


def checkpoint_path(story_id: str) -> Path:
    return save_dir(story_id) / "checkpoints" / "engine.json"


# ── Save 中角色运行时路径 ──

def character_save_dir(story_id: str, name: str) -> Path:
    return save_dir(story_id) / "characters" / name


def character_initial_state_path(story_id: str, name: str) -> Path:
    """Story 中的初始状态模板。运行时优先读 save 中的 state。"""
    return story_dir(story_id) / "characters" / name / "initial_state.md"


def character_state_path(story_id: str, name: str) -> Path:
    """运行时状态（save 中）。不存在时 fallback 到 story 的 initial_state。"""
    return character_save_dir(story_id, name) / "state.md"


def character_public_profile_path(story_id: str, name: str) -> Path:
    return character_save_dir(story_id, name) / "public_profile.md"


def character_scene_dir(story_id: str, name: str, scene_name: str) -> Path:
    return character_save_dir(story_id, name) / "episodes" / scene_name


def character_heartfelt_path(story_id: str, name: str, scene_name: str) -> Path:
    return character_scene_dir(story_id, name, scene_name) / "heartfelt.md"


def character_opinions_path(story_id: str, name: str) -> Path:
    return character_save_dir(story_id, name) / "opinions.json"
