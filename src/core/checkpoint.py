"""断点 — LLM 调用级持久化，记录"当前谁在说话"。"""
import json
from pathlib import Path
from src.config import save_dir


def _ckpt_dir(story_id: str) -> Path:
    d = save_dir(story_id) / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_engine_checkpoint(story_id: str, **kwargs):
    """保存引擎断点。调用时机：每次 agent LLM 调用前。"""
    path = _ckpt_dir(story_id) / "engine.json"
    path.write_text(json.dumps(kwargs, ensure_ascii=False, indent=2), encoding="utf-8")


def load_engine_checkpoint(story_id: str) -> dict | None:
    """读取上次引擎断点。不存在返回 None。"""
    path = _ckpt_dir(story_id) / "engine.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None
