"""原子化 JSON/JSONL 持久化工具。"""
import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any = None) -> Any:
    """安全加载 JSON 文件。缺失或损坏时返回 default。"""
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any):
    """原子写入 JSON：先写 .tmp 再 rename。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_jsonl(path: Path) -> list[dict]:
    """加载 JSONL 文件为 dict 列表。缺失或空文件返回 []。"""
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def append_jsonl(path: Path, entry: dict):
    """追加一行到 JSONL 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def atomic_append_jsonl(path: Path, entry: dict):
    """原子追加：写入临时文件后 append 到正式文件。

    适用于需要确保写入完整性的场景。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # 追加模式合并
    with open(tmp, "r", encoding="utf-8") as src:
        with open(path, "a", encoding="utf-8") as dst:
            dst.write(src.read())
    tmp.unlink(missing_ok=True)
