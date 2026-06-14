"""全局配置 — Story 与 Save 路径分离。"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

STORIES_ROOT = ROOT / "stories"
SAVES_ROOT = ROOT / "saves"
CONFIG_PATH = ROOT / "config.json"


# ── 应用配置（可通过前端修改，持久化到 config.json）──

def _load_app_config() -> dict:
    """加载 config.json。不存在返回空 dict。"""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_app_config(data: dict):
    """保存到 config.json。"""
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_app_config() -> dict:
    """返回完整应用配置（API 用）。"""
    cfg = _load_app_config()
    llm = cfg.get("llm", {})
    return {
        "llm": {
            "api_key": "*** (已配置)" if llm.get("api_key") else "",
            "base_url": llm.get("base_url", os.environ.get("OPENAI_BASE_URL", "")),
            "model": llm.get("model", os.environ.get("LLM_MODEL", "")),
            "use_stream": llm.get("use_stream", True),
        },
    }


def save_app_config(data: dict):
    """保存应用配置（API 用）。api_key 为 '' 时不覆盖。"""
    cfg = _load_app_config()
    if "llm" in data:
        llm = dict(data["llm"])
        key = llm.get("api_key", "")
        if not key or key.startswith("***") or key == "(from .env)":
            llm.pop("api_key", None)  # 拒绝状态提示字符串
        cfg.setdefault("llm", {}).update(llm)
    _save_app_config(cfg)
    clear_llm_config_cache()


# ── LLM 配置 ──

from dataclasses import dataclass


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    use_stream: bool = True


_llm_config_cache: LLMConfig | None = None


def clear_llm_config_cache():
    global _llm_config_cache
    _llm_config_cache = None


def load_llm_config() -> LLMConfig:
    global _llm_config_cache
    if _llm_config_cache is None:
        app = _load_app_config().get("llm", {})
        app_key = app.get("api_key", "")
        env_key = os.environ.get("OPENAI_API_KEY", "")
        key = app_key or env_key
        if not key:
            raise RuntimeError(
                "未配置 API Key。请在网页 ⚙ 设置中填写，或在 .env 中设置 OPENAI_API_KEY")
        import logging
        logging.getLogger("ainovel.config").info(
            "【配置】LLM: model=%s base=%s key=%s (from %s)",
            app.get("model") or os.environ.get("LLM_MODEL", "gpt-4o"),
            app.get("base_url") or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            key[:8] + "***" if len(key) > 8 else "***",
            "config.json" if app_key else ".env",
        )
        _llm_config_cache = LLMConfig(
            api_key=key,
            base_url=app.get("base_url") or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=app.get("model") or os.environ.get("LLM_MODEL", "gpt-4o"),
            use_stream=app.get("use_stream", True),
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
