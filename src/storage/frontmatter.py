"""YAML frontmatter 解析 + 世界观/大纲加载器。"""
import re
from pathlib import Path
from dataclasses import dataclass, field

import yaml


# ── 通用 frontmatter 解析 ──

def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """解析 markdown 文件的 YAML frontmatter。

    Args:
        md_text: 完整 .md 文件内容。

    Returns:
        (frontmatter_dict, body_text)
        - frontmatter_dict: frontmatter 键值对，无 frontmatter 时返回空 dict
        - body_text: frontmatter 之后的正文（去除首尾空白）
    """
    text = md_text.strip()
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return {}, parts[2].strip() if len(parts) > 2 else ""
        return fm, parts[2].strip()
    except yaml.YAMLError:
        return {}, parts[2].strip() if len(parts) > 2 else ""


# ── 世界观 ──

@dataclass
class WorldviewEntry:
    """单条世界观条目。"""
    path: str            # worldview/ 下的相对路径
    tags: list[str]      # 标签列表
    name: str            # 条目名
    description: str     # 简述
    content: str         # 正文（不含 frontmatter）
    is_public: bool = False  # 派生：tags 是否含 "public"

    def __post_init__(self):
        self.is_public = "public" in self.tags


def load_worldview_entries(worldview_dir: Path) -> dict[str, WorldviewEntry]:
    """递归加载 worldview/ 下所有 .md 文件。

    Args:
        worldview_dir: stories/{story_id}/worldview/ 目录路径。

    Returns:
        dict[relative_path, WorldviewEntry]。key 为 worldview/ 下的相对路径。
        如果目录不存在则返回空 dict。
    """
    entries: dict[str, WorldviewEntry] = {}
    if not worldview_dir.exists():
        return entries

    for md_file in worldview_dir.rglob("*.md"):
        # 路径去掉 .md 后缀，统一为 南宫家档案/法相武魂 这种形式
        rel_path_raw = str(md_file.relative_to(worldview_dir)).replace("\\", "/")
        rel_path = rel_path_raw[:-3] if rel_path_raw.endswith(".md") else rel_path_raw
        raw = md_file.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(raw)

        # 校验
        tags = fm.get("tags", [])
        if not isinstance(tags, list) or len(tags) == 0:
            print(f"[worldview WARNING] {rel_path}: tags 为空或格式错误，跳过")
            continue
        if "public" not in tags and "hidden" not in tags:
            print(f"[worldview WARNING] {rel_path}: tags 必须包含 public 或 hidden，跳过")
            continue

        name = fm.get("name", "")
        if not name:
            print(f"[worldview WARNING] {rel_path}: 缺少 name 字段，跳过")
            continue

        description = fm.get("description", "")
        if not description:
            print(f"[worldview WARNING] {rel_path}: 缺少 description 字段，跳过")
            continue

        entries[rel_path] = WorldviewEntry(
            path=rel_path,
            tags=tags,
            name=name,
            description=description,
            content=body,
        )

    return entries


# ── 大纲 ──

OUTLINE_FILENAME_RE = re.compile(r"^【(\d+)】(.*)\.md$")


@dataclass
class OutlineEntry:
    """单条大纲条目。"""
    number: int              # 数字编号
    chapter_name: str        # 章节名（来自文件名 【数字】之后的部分）
    name: str                # frontmatter name
    description: str         # frontmatter description（章节概述）
    content: str             # 正文（不含 frontmatter）
    file_path: Path          # 文件绝对路径


def load_outlines(outline_dir: Path) -> list[OutlineEntry]:
    """加载并校验 outline/ 下的大纲文件。

    - 文件名必须匹配 【数字】章节名.md
    - 数字必须从 1 开始连续
    - 每个文件应有合法的 frontmatter（name + description）

    校验不通过仅打印 warning，不阻断加载。
    只有严格匹配命名规范的文件才会被使用。
    """
    if not outline_dir.exists():
        return []

    valid: list[OutlineEntry] = []
    seen_numbers: set[int] = set()
    invalid_files: list[str] = []

    for f in sorted(outline_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix != ".md":
            invalid_files.append(f.name)
            continue

        m = OUTLINE_FILENAME_RE.match(f.name)
        if not m:
            invalid_files.append(f.name)
            continue

        number = int(m.group(1))
        chapter_name = m.group(2)

        raw = f.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(raw)

        name = fm.get("name", chapter_name)
        description = fm.get("description", "")

        if not description:
            print(f"[outline WARNING] {f.name}: 缺少 description 字段")

        seen_numbers.add(number)
        valid.append(OutlineEntry(
            number=number,
            chapter_name=chapter_name,
            name=name,
            description=description,
            content=body,
            file_path=f,
        ))

    # 报告不符合命名规范的文件
    if invalid_files:
        print(f"[outline WARNING] 以下文件不符合命名规范（应为 【数字】章节名.md）："
              f" {', '.join(invalid_files)}")

    # 检查数字连续性（从 1 开始）
    if seen_numbers:
        max_n = max(seen_numbers)
        missing = [str(i) for i in range(1, max_n + 1) if i not in seen_numbers]
        if 1 not in seen_numbers:
            print(f"[outline WARNING] 大纲编号应从 1 开始，但未找到编号 1 的文件")
        if missing:
            print(f"[outline WARNING] 大纲编号缺失: {', '.join(missing)}")

    valid.sort(key=lambda e: e.number)
    return valid


# ── 角色 profile 分章解析 ──

def split_profile_sections(md_text: str) -> dict[str, str]:
    """将 profile.md 按 markdown 一级标题拆分章节。

    第一段（标题之前的内容）在 key "" 中。
    各章节以 "# 标题名" 作为 key。

    Args:
        md_text: profile.md 完整内容。

    Returns:
        dict[章节标题, 章节内容]
    """
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []

    for line in md_text.split("\n"):
        if line.startswith("# ") and not line.startswith("## "):
            # 保存上一章节
            if current_title or current_lines:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    # 保存最后一章
    sections[current_title] = "\n".join(current_lines).strip()
    return sections


def get_self_perception(profile_text: str) -> str:
    """提取角色「初始自我认知」章节内容。

    如果 profile.md 中没有「初始自我认知」章节，则返回整个文件内容。
    """
    sections = split_profile_sections(profile_text)
    if "初始自我认知" in sections:
        return sections["初始自我认知"]
    # fallback：返回非「隐藏设定」的所有内容
    visible = []
    for title, content in sections.items():
        if title != "隐藏设定":
            visible.append(content)
    return "\n\n".join(visible).strip() or profile_text


def get_hidden_profile(profile_text: str) -> str:
    """提取角色隐藏设定（仅给 Author 看的部分）。

    返回「隐藏设定」章节及之后所有非「初始自我认知」的章节内容。
    """
    sections = split_profile_sections(profile_text)
    parts = []
    for title, content in sections.items():
        if title != "初始自我认知":
            parts.append(f"# {title}\n\n{content}" if title else content)
    return "\n\n".join(parts).strip()


def get_character_description(profile_text: str) -> str:
    """提取角色描述——渐进式披露给 Author 和 Narrator 的概要。"""
    fm, _ = parse_frontmatter(profile_text)
    if fm.get("description"):
        return fm["description"]
    # fallback：角色名
    return fm.get("name", "未知角色")
