"""FormatterAgent — 继承 BaseAgent，用工具分步填入字段，不输出 JSON。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


def _extract_names(text: str) -> set[str]:
    """从登场/退场文本中提取角色名。"""
    import re
    names = set()
    for m in re.finditer(r'[「]([^」]+)[」]', text):
        names.add(m.group(1))
    # 也匹配 角色名（主线）/（过场）/（入场）等
    for m in re.finditer(r'([^\s（,，、]+)[（(](?:主线|过场|已在场上|入场|退场)[^)]*[)）]', text):
        names.add(m.group(1))
    return names


# ═══════════════════════════════════════════════════════════════
# FormatterAgent
# ═══════════════════════════════════════════════════════════════

class FormatterAgent(BaseAgent):
    """填入式审查 agent——逐字段填入，不输出 JSON。"""

    @property
    def agent_name(self) -> str:
        return "Review"

    def __init__(self, story_id: str, phase: str = "planning"):
        super().__init__(story_id)
        self._astream_ok = False          # formatter 用 ainvoke 更快
        self._phase = phase
        self._data: dict = {}
        self._warnings: list[str] = []
        self._suggestions: list[str] = []
        self._parsed: bool = False

    # ── 抽象接口 ──

    @property
    def system_prompt(self) -> str:
        if self._phase == "planning":
            return _PLANNING_PROMPT
        return _SUMMARY_PROMPT

    @property
    def tools(self) -> list:
        if self._phase == "planning":
            return self._make_planning_tools()
        return self._make_summary_tools()

    @property
    def exit_tool(self) -> str:
        return "done"

    # ── 工具（内部方法） ──

    def _fill_planning(self, field: str, value: str) -> str:
        valid = {"episode_name", "summary", "detailed_outline", "author_notes"}
        if field not in valid:
            return f"未知字段：{field}。可用：{', '.join(sorted(valid))}"
        self._data[field] = value
        return "OK"

    def _add_scene(self, location: str, enters: str, content: str, exits: str = "") -> str:
        """添加一个小节。"""
        scenes = self._data.setdefault("scenes", [])
        scenes.append({
            "location": location,
            "enters": enters,
            "content": content,
            "exits": exits,
        })
        return f"OK （当前共 {len(scenes)} 个小节）"

    def _fill_summary(self, field: str, value: str) -> str:
        valid = {"episode_summary", "plot_update"}
        if field not in valid:
            return f"未知字段：{field}。可用：{', '.join(sorted(valid))}"
        self._data[field] = value
        return "OK"

    def _add_character(self, name: str, level: str = "主线",
                       direction: str = "") -> str:
        """添加角色安排。level: 主线/过场/NPC。
        主线/过场需要 cross-check。NPC 全由旁白处理，豁免校验。"""
        if level not in ("主线", "过场", "NPC"):
            return "level 必须是 主线、过场 或 NPC"
        chars = self._data.setdefault("characters", [])
        if any(c["name"] == name for c in chars):
            return f"角色「{name}」已存在，跳过。当前共 {len(chars)} 个角色。"
        chars.append({"name": name, "level": level, "direction": direction})
        return f"OK （当前共 {len(chars)} 个角色）"

    def _add_worldview_grant(self, path: str) -> str:
        grants = self._data.setdefault("worldview_grants", [])
        if path in grants:
            return f"路径「{path}」已授权，跳过。当前共 {len(grants)} 个授权。"
        grants.append(path)
        return f"OK （当前共 {len(grants)} 个授权）"

    def _add_warning(self, text: str) -> str:
        self._warnings.append(text)
        return "OK"

    def _add_suggestion(self, text: str) -> str:
        self._suggestions.append(text)
        return "OK"

    def _add_foreshadowing(self, action: str, content: str = "") -> str:
        fs = self._data.setdefault("foreshadowing", {"added": [], "resolved": []})
        if action in ("added", "resolved"):
            fs[action].append(content)
            return "OK"
        return "action 必须是 added 或 resolved"

    def _set_advance_chapter(self, value: bool) -> str:
        self._data["advance_chapter"] = value
        return "OK"

    def _set_gap(self, value: str) -> str:
        if value not in ("small_gap", "big_gap"):
            return "gap 必须是 small_gap 或 big_gap"
        self._data["gap"] = value
        return "OK"

    def _check_completeness(self) -> str:
        if self._phase == "planning":
            required = ["episode_name", "summary", "characters",
                        "scenes", "detailed_outline"]
        else:
            required = ["episode_summary", "plot_update"]
        lines = []
        for f in required:
            filled = bool(self._data.get(f))
            mark = "[x]" if filled else "[ ]"
            lines.append(f"- {mark} {f}")

        # 交叉校验：小节角色必须在角色安排中
        if self._phase == "planning":
            char_names = {c["name"] for c in self._data.get("characters", [])}
            scenes = self._data.get("scenes", [])
            for i, s in enumerate(scenes):
                # 登场角色
                for name in _extract_names(s.get("enters", "")):
                    if name not in char_names:
                        self._warnings.append(
                            f"小节{i+1}登场角色「{name}」不在角色安排中")
                # 退场角色
                for name in _extract_names(s.get("exits", "")):
                    if name not in char_names:
                        self._warnings.append(
                            f"小节{i+1}退场角色「{name}」不在角色安排中")

            # 反向：角色安排中有台词方向的过场角色，是否至少在某个小节登场
            # NPC 角色豁免所有校验
            for c in self._data.get("characters", []):
                if c.get("level") == "NPC":
                    continue
                if c.get("level") == "过场" and c.get("direction"):
                    found = any(c["name"] in _extract_names(s.get("enters", ""))
                                for s in scenes)
                    if not found:
                        self._warnings.append(
                            f"过场角色「{c['name']}」标记了台词方向但未在任何小节登场")

        self._parsed = True
        return "\n".join(lines)

    def _done(self) -> str:
        self._parsed = True
        return "OK"

    # ── 工具构建 ──

    def _make_planning_tools(self):
        agent = self

        @tool
        def fill(field: str, value: str) -> str:
            """填入字段。field: episode_name/名称, summary/概要,
            detailed_outline/细纲, author_notes/备注。"""
            return agent._fill_planning(field, value)

        @tool
        def add_character(name: str, level: str = "主线",
                           direction: str = "") -> str:
            """添加一个角色到演员表。level: 主线/过场。
            过场角色需填 direction——台词方向或意图。"""
            return agent._add_character(name, level, direction)

        @tool
        def add_scene(location: str, enters: str, content: str,
                       exits: str = "") -> str:
            """添加一个小节。location: 地点。enters: 登场角色。
            content: 本小节事件。exits: 退场角色，无退场留空。"""
            return agent._add_scene(location, enters, content, exits)

        @tool
        def add_worldview_grant(path: str) -> str:
            """添加世界观授权路径。"""
            return agent._add_worldview_grant(path)

        @tool
        def add_warning(text: str) -> str:
            """添加警告（剧透、格式问题等）。"""
            return agent._add_warning(text)

        @tool
        def add_suggestion(text: str) -> str:
            """添加改进建议。"""
            return agent._add_suggestion(text)

        @tool
        def check_completeness() -> str:
            """列出必填项完成状态，不调 LLM。"""
            return agent._check_completeness()

        @tool
        def done() -> str:
            """格式化完成。"""
            return agent._done()

        return [fill, add_character, add_scene, add_worldview_grant,
                add_warning, add_suggestion, check_completeness, done]

    def _make_summary_tools(self):
        agent = self

        @tool
        def fill(field: str, value: str) -> str:
            """填入字段。field: episode_summary/本幕总结, plot_update/剧情走向。"""
            return agent._fill_summary(field, value)

        @tool
        def add_foreshadowing(action: str, content: str = "") -> str:
            """伏笔操作。action: added/新增 或 resolved/回收。content: 描述或ID。"""
            return agent._add_foreshadowing(action, content)

        @tool
        def set_advance_chapter(value: bool) -> str:
            """设置是否推进到下一章。"""
            return agent._set_advance_chapter(value)

        @tool
        def set_gap(value: str) -> str:
            """设置场景间隔。value: small_gap/小间隔 或 big_gap/大间隔。"""
            return agent._set_gap(value)

        @tool
        def add_warning(text: str) -> str:
            return agent._add_warning(text)

        @tool
        def add_suggestion(text: str) -> str:
            return agent._add_suggestion(text)

        @tool
        def check_completeness() -> str:
            return agent._check_completeness()

        @tool
        def done() -> str:
            return agent._done()

        return [fill, add_foreshadowing, set_advance_chapter, set_gap,
                add_warning, add_suggestion, check_completeness, done]

    # ── 结果导出 ──

    def build_result(self) -> dict:
        """组装结构化结果。"""
        result = dict(self._data)
        result["warnings"] = self._warnings
        result["suggestions"] = self._suggestions

        if self._phase == "planning":
            required = ["episode_name", "summary", "characters",
                        "scenes", "detailed_outline"]
            optional = ["worldview_grants", "author_notes"]
        else:
            required = ["episode_summary", "plot_update"]
            optional = ["foreshadowing", "advance_chapter", "gap"]

        comp = {}
        for f in required:
            comp[f] = bool(result.get(f))
        for f in optional:
            comp[f] = "optional"
        result["completeness"] = comp
        return result


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

_PLANNING_PROMPT = """你是规划格式化器。逐字段填入 Author 提交的规划内容。

工具：
- fill(field, value)：填入字段。field: episode_name(名称), summary(概要), detailed_outline(细纲), author_notes(备注)
- add_character(name, level, direction)：添加角色。level: 主线/过场/NPC。过场需填 direction。NPC 豁免所有校验
- add_scene(location, enters, content, exits)：添加小节。enters: 登场角色，exits: 退场（无则留空）
- add_worldview_grant(path)：添加世界观授权路径
- add_warning(text)：添加警告
- add_suggestion(text)：添加建议
- check_completeness()：列必填项 + 交叉校验（小节角色是否在演员表中、过场是否登场）
- done()：完成

流程：
1. fill 填入名称、概要、细纲、备注
2. add_character 逐个添加演员表
3. add_scene 逐个小节添加
4. add_worldview_grant 添加授权
5. check_completeness() → 有 warning 则修正 → done()

互不依赖的操作务必同一轮批量发出。section 名可能是中文变体，按语义归类。不要编造内容。"""

_SUMMARY_PROMPT = """你是总结格式化器。逐字段填入 Author 提交的总结内容。

工具：
- fill(field, value)：填入字段。field: episode_summary(本幕总结), plot_update(剧情走向)
- add_foreshadowing(action, content)：action: added(新增) / resolved(回收)
- set_advance_chapter(true/false)：是否推进到下一章
- set_gap(small_gap/big_gap)：场景间隔——small_gap 连续场景，big_gap 大跳跃
- add_warning/add_suggestion
- check_completeness()
- done()

流程：
1. 一次性 fill 总结和剧情走向（同一轮）
2. 同一轮 add_foreshadowing 逐个添加伏笔操作
3. 同一轮 set_advance_chapter + set_gap
4. check_completeness()
5. done()

你可以在一轮中同时调用多个工具。fill/add_foreshadowing/set_advance_chapter/set_gap 互不依赖——可以一次性发出。check_completeness → done 需要分步。

section 名可能是中文变体，按语义归类。不要编造内容。"""


# ═══════════════════════════════════════════════════════════════
# MD 组装（纯规则）
# ═══════════════════════════════════════════════════════════════

def _assemble_planning_md(data: dict) -> str:
    lines = ["# 规划审查\n", "## 已识别内容\n"]
    if data.get("episode_name"):
        lines.append(f"### 小剧场名称\n{data['episode_name']}\n")
    if data.get("summary"):
        lines.append(f"### 概要\n{data['summary']}\n")

    chars = data.get("characters", [])
    if chars:
        lines.append("### 角色安排\n| 角色 | 层级 | 台词方向 |")
        lines.append("|------|------|----------|")
        for c in chars:
            direction = c.get("direction", "-") or "-"
            lines.append(f"| {c.get('name','?')} | {c.get('level','?')} | {direction} |")
        lines.append("")

    scenes = data.get("scenes", [])
    if scenes:
        lines.append(f"### 小节（共{len(scenes)}个）\n")
        for i, s in enumerate(scenes):
            lines.append(f"**小节 {i+1}**")
            lines.append(f"- 地点：{s.get('location','?')}")
            lines.append(f"- 登场：{s.get('enters','?')}")
            lines.append(f"- 内容：{s.get('content','?')}")
            if s.get("exits"):
                lines.append(f"- 退场：{s.get('exits','')}")
            lines.append("")

    if data.get("detailed_outline"):
        lines.append(f"### 剧情细纲原文\n{data['detailed_outline']}\n")

    grants = data.get("worldview_grants", [])
    if grants:
        lines.append("### 世界观授权\n")
        for g in grants:
            lines.append(f"- `{g}`")
        lines.append("")

    if data.get("author_notes"):
        lines.append(f"### 讲述者备注\n{data['author_notes']}\n")

    lines.append("---\n## 完整性检查\n")
    comp = data.get("completeness", {})
    items = [("episode_name", "小剧场名称"), ("summary", "概要"),
             ("characters", "角色安排"), ("scenes", "小节"),
             ("detailed_outline", "剧情细纲"),
             ("worldview_grants", "世界观授权（可选）"), ("author_notes", "讲述者备注（可选）")]
    missing = []
    for key, label in items:
        s = comp.get(key, False)
        if s is True:
            lines.append(f"- [x] {label}")
        elif s == "optional":
            lines.append(f"- [?] {label}")
        else:
            lines.append(f"- [ ] {label}")
            missing.append(label)
    if missing:
        lines.append(f"\n[!] 缺失: {', '.join(missing)}")
    else:
        lines.append("\n[OK] 必填项已齐全，可以 done()。")

    for section, title in [("warnings", "警告"), ("suggestions", "建议")]:
        items = data.get(section, [])
        if items:
            lines.append(f"\n## {title}\n")
            for item in items:
                lines.append(f"- {item}")
    return "\n".join(lines)


def _assemble_summary_md(data: dict) -> str:
    lines = ["# 总结审查\n", "## 已识别内容\n"]
    if data.get("episode_summary"):
        lines.append(f"### 本幕总结\n{data['episode_summary']}\n")
    if data.get("plot_update"):
        lines.append(f"### 剧情走向\n{data['plot_update']}\n")
    fs = data.get("foreshadowing", {})
    if fs:
        added = fs.get("added", [])
        resolved = fs.get("resolved", [])
        if added or resolved:
            lines.append("### 伏笔操作\n")
            for a in added:
                lines.append(f"- 新增：{a}")
            for r in resolved:
                lines.append(f"- 回收：{r}")
            lines.append("")
    if data.get("advance_chapter"):
        lines.append("### 章节建议\n建议进入下一章。\n")
    if data.get("gap"):
        gap_label = "大间隔" if data["gap"] == "big_gap" else "小间隔"
        lines.append(f"### 场景间隔\n{gap_label}。\n")
    lines.append("---\n## 完整性检查\n")
    comp = data.get("completeness", {})
    items = [("episode_summary", "本幕总结"), ("plot_update", "剧情走向"),
             ("foreshadowing", "伏笔操作（可选）"), ("chapter_suggestion", "章节建议（可选）")]
    missing = []
    for key, label in items:
        s = comp.get(key, False)
        if s is True:
            lines.append(f"- [x] {label}")
        elif s == "optional":
            lines.append(f"- [?] {label}")
        else:
            lines.append(f"- [ ] {label}")
            missing.append(label)
    if missing:
        lines.append(f"\n[!] 缺失: {', '.join(missing)}")
    else:
        lines.append("\n[OK] 必填项已齐全，可以 done()。")
    for section, title in [("warnings", "警告"), ("suggestions", "建议")]:
        items = data.get(section, [])
        if items:
            lines.append(f"\n## {title}\n")
            for item in items:
                lines.append(f"- {item}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

async def format_planning(content: str, story_id: str,
                          *, on_step=None, on_token=None) -> tuple[dict, str]:
    agent = FormatterAgent(story_id, "planning")
    calls = await agent.run(content, on_step=on_step, on_token=on_token)
    data = agent.build_result()
    if data.get("error"):
        return data, f"# 规划审查\n\n[!] Formatter 出错: {data.get('error')}"
    return data, _assemble_planning_md(data)


async def format_summary(content: str, story_id: str,
                         *, on_step=None, on_token=None) -> tuple[dict, str]:
    agent = FormatterAgent(story_id, "summary")
    calls = await agent.run(content, on_step=on_step, on_token=on_token)
    data = agent.build_result()
    if data.get("error"):
        return data, f"# 总结审查\n\n[!] Formatter 出错: {data.get('error')}"
    return data, _assemble_summary_md(data)
