"""FormatterAgent — 继承 BaseAgent，用工具分步填入字段，不输出 JSON。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


# ═══════════════════════════════════════════════════════════════
# FormatterAgent
# ═══════════════════════════════════════════════════════════════

class FormatterAgent(BaseAgent):
    """填入式审查 agent——逐字段填入，不输出 JSON。"""

    @property
    def agent_name(self) -> str:
        return "Review"

    def __init__(self, story_id: str, phase: str = "planning",
                 worldview_paths: set[str] | None = None):
        super().__init__(story_id)
        self._astream_ok = False
        self._phase = phase
        self._data: dict = {}
        self._notes: list[dict] = []     # {type: "warning"|"suggestion", text: ...}
        self._parsed: bool = False
        self._scene_index: int = -1      # 当前正在填充的小节索引
        self._worldview_paths: set[str] = worldview_paths or set()

    # ── 抽象接口 ──

    @property
    def system_prompt(self) -> str:
        return _PLANNING_PROMPT if self._phase == "planning" else _SUMMARY_PROMPT

    @property
    def tools(self) -> list:
        return self._make_planning_tools() if self._phase == "planning" else self._make_summary_tools()

    @property
    def exit_tool(self) -> str:
        return "done"

    # ── 内部方法 ──

    def _fill_field(self, field: str, value: str) -> str:
        if self._phase == "planning":
            valid = {"episode_name", "outline", "author_notes"}
        else:
            valid = {"episode_summary", "plot_update"}
        if field not in valid:
            return f"未知字段：{field}。可用：{', '.join(sorted(valid))}"
        if not value.strip():
            return f"{field} 不能为空"
        self._data[field] = value
        return "OK"

    def _add_available_character(self, name: str, reason: str = "") -> str:
        """添加一个可出场角色。name 必须在角色列表中，否则硬性拒绝。"""
        character_names = self._get_character_names()
        if character_names and name not in character_names:
            return f"「{name}」不在可用角色列表中。NPC 不能列入可出场角色。可用：{'、'.join(sorted(character_names))}"
        available = self._data.setdefault("available_characters", [])
        if any(a["name"] == name for a in available):
            return f"「{name}」已在可出场角色列表中"
        available.append({"name": name, "reason": reason})
        return "OK"

    def _add_scene(self, name: str, location: str, content: str) -> str:
        if not name.strip():
            return "name（小节名称）不能为空"
        if not location.strip():
            return f"小节「{name}」的 location（地点）不能为空"
        if not content.strip():
            return f"小节「{name}」的 content（内容）不能为空"
        scenes = self._data.setdefault("scenes", [])
        scenes.append({"name": name, "location": location,
                       "enter": [], "content": content, "exit": []})
        self._scene_index = len(scenes) - 1
        return f"OK （当前共 {len(scenes)} 个小节）"

    def _add_enter(self, name: str, reason: str = "") -> str:
        scenes = self._data.get("scenes", [])
        if not scenes:
            return "请先 add_scene 再 add_enter"
        # 角色名校验
        character_names = self._get_character_names()
        if character_names and name not in character_names:
            return f"「{name}」不在可用角色列表中。如果是 NPC 请直接写在 content 中，不要列入 enter。可用：{'、'.join(sorted(character_names))}"
        scenes[-1].setdefault("enter", []).append({"name": name, "reason": reason})
        return "OK"

    def _add_exit(self, name: str, reason: str = "") -> str:
        scenes = self._data.get("scenes", [])
        if not scenes:
            return "请先 add_scene 再 add_exit"
        character_names = self._get_character_names()
        if character_names and name not in character_names:
            return f"「{name}」不在可用角色列表中。如果是 NPC 请直接写在 content 中，不要列入 exit。可用：{'、'.join(sorted(character_names))}"
        scenes[-1].setdefault("exit", []).append({"name": name, "reason": reason})
        return "OK"

    def _get_character_names(self) -> set[str]:
        """从 user message 中解析可用角色列表（缓存）。"""
        if hasattr(self, "_character_names_cache"):
            return self._character_names_cache
        names = set()
        for m in self._messages:
            content = getattr(m, "content", "")
            if isinstance(content, str) and "## 可用角色列表" in content:
                # 提取 "角色1、角色2、角色3" 格式的名字列表
                idx = content.find("## 可用角色列表")
                line = content[idx:].split("\n")[0]
                names = {n.strip() for n in line.replace("## 可用角色列表", "").split("、") if n.strip()}
                break
        self._character_names_cache = names
        return names

    def _add_worldview_grant(self, path: str) -> str:
        grants = self._data.setdefault("worldview_grants", [])
        if any(g.get("path") == path for g in grants):
            return f"路径「{path}」已授权，跳过。"
        if self._worldview_paths and path not in self._worldview_paths:
            available = '\n'.join(f"  - {p}" for p in sorted(self._worldview_paths))
            return f"世界观路径「{path}」不存在。可用路径：\n{available}"
        grants.append({"path": path})
        return "OK"

    def _add_note(self, text: str) -> str:
        """添加一条备注，自动归类为 warning 或 suggestion。"""
        self._notes.append({"text": text})
        return "OK"

    # 保留旧方法兼容
    def _add_warning(self, text: str) -> str:
        self._notes.append({"type": "warning", "text": text})
        return "OK"

    def _add_suggestion(self, text: str) -> str:
        self._notes.append({"type": "suggestion", "text": text})
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
            required = ["episode_name", "outline", "scenes"]
        else:
            required = ["episode_summary", "plot_update"]
        lines = []
        for f in required:
            filled = bool(self._data.get(f))
            lines.append(f"- {'[x]' if filled else '[ ]'} {f}")

        if self._phase == "planning":
            scenes = self._data.get("scenes", [])
            available_names = {a["name"] for a in self._data.get("available_characters", [])}

            # 小节衔接检查
            for i in range(len(scenes) - 1):
                prev_enter = {e["name"] for e in scenes[i].get("enter", [])}
                prev_exit = {e["name"] for e in scenes[i].get("exit", [])}
                next_enter = {e["name"] for e in scenes[i+1].get("enter", [])}
                for name in prev_enter:
                    if name not in prev_exit and name not in next_enter:
                        self._notes.append({"type": "warning",
                            "text": f"小节{i+1}角色「{name}」登场但小节{i+2}未延续也未退场"})

            # 交叉校验：enter/exit 中的角色是否在 available_characters 中
            if available_names:
                all_enter_exit: set[str] = set()
                for s in scenes:
                    for e in s.get("enter", []):
                        all_enter_exit.add(e["name"])
                    for e in s.get("exit", []):
                        all_enter_exit.add(e["name"])
                missing = all_enter_exit - available_names
                for name in sorted(missing):
                    self._notes.append({"type": "warning",
                        "text": f"角色「{name}」出现在入场/退场但未列入可出场角色"})

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
            """填入字段。field: episode_name/名称, outline/小剧场大纲, author_notes/备注。"""
            return agent._fill_field(field, value)

        @tool
        def add_available_character(name: str, reason: str = "") -> str:
            """添加一个可出场角色。name: 角色名（必须在可用角色列表中）, reason: 出场理由或场景位置。"""
            return agent._add_available_character(name, reason)

        @tool
        def add_scene(name: str, location: str, content: str) -> str:
            """添加一个小节。name: 小节名, location: 地点, content: 内容。
            随后用 add_enter / add_exit 逐角色添加入场和退场。"""
            return agent._add_scene(name, location, content)

        @tool
        def add_enter(name: str, reason: str = "") -> str:
            """给当前小节添加一个入场角色。name: 角色名, reason: 入场方式或状态。"""
            return agent._add_enter(name, reason)

        @tool
        def add_exit(name: str, reason: str = "") -> str:
            """给当前小节添加一个退场角色。name: 角色名, reason: 退场原因。"""
            return agent._add_exit(name, reason)

        @tool
        def add_worldview_grant(path: str) -> str:
            """添加世界观授权路径。"""
            return agent._add_worldview_grant(path)

        @tool
        def add_note(text: str) -> str:
            """添加备注（润色建议、格式问题等）。"""
            return agent._add_note(text)

        @tool
        def check_completeness() -> str:
            """列出必填项并检查小节衔接。"""
            return agent._check_completeness()

        @tool
        def done() -> str:
            """格式化完成。"""
            return agent._done()

        return [fill, add_available_character, add_scene, add_enter, add_exit,
                add_worldview_grant, add_note, check_completeness, done]

    def _make_summary_tools(self):
        agent = self

        @tool
        def fill(field: str, value: str) -> str:
            """填入字段。field: episode_summary/本幕总结, plot_update/剧情走向。"""
            return agent._fill_field(field, value)

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
        def add_note(text: str) -> str:
            """添加备注。"""
            return agent._add_note(text)

        @tool
        def check_completeness() -> str:
            """列出必填项完成状态。"""
            return agent._check_completeness()

        @tool
        def done() -> str:
            """格式化完成。"""
            return agent._done()

        return [fill, add_foreshadowing, set_advance_chapter, set_gap,
                add_note, check_completeness, done]

    # ── 结果导出 ──

    def build_result(self) -> dict:
        result = dict(self._data)

        # ── Schema 校验 ──
        schema_errors = self._validate_result(result)
        if schema_errors:
            result["error"] = "; ".join(schema_errors)

        # 将 notes 按类型分离
        warnings = []
        suggestions = []
        for n in self._notes:
            t = n.get("type", "")
            if t == "warning":
                warnings.append(n["text"])
            elif t == "suggestion":
                suggestions.append(n["text"])
            else:
                suggestions.append(n["text"])
        result["warnings"] = warnings
        result["suggestions"] = suggestions

        # 润色：轻微整理 content 文本
        for s in result.get("scenes", []):
            s["content"] = s.get("content", "").strip()

        if self._phase == "planning":
            required = ["episode_name", "outline", "scenes"]
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

    # ── Schema 校验 ──

    # 字段名 → (期望类型, 是否必填)
    _PLANNING_SCHEMA: dict[str, tuple[type, bool]] = {
        "episode_name": (str, True),
        "outline": (str, True),
        "author_notes": (str, False),
    }
    _SUMMARY_SCHEMA: dict[str, tuple[type, bool]] = {
        "episode_summary": (str, True),
        "plot_update": (str, True),
    }
    # 列表元素内的字段 schema
    _LIST_ELEMENT_SCHEMA = {
        "scenes": {"name": (str, True), "location": (str, True), "content": (str, True)},
        "available_characters": {"name": (str, True), "reason": (str, False)},
        "worldview_grants": {"path": (str, True)},
        "foreshadowing": {},
    }

    def _validate_result(self, result: dict) -> list[str]:
        """校验产出 JSON 的类型和格式。返回错误列表。"""
        errors = []
        schema = self._PLANNING_SCHEMA if self._phase == "planning" else self._SUMMARY_SCHEMA

        for field, (expected_type, required) in schema.items():
            value = result.get(field)
            if required and not value:
                errors.append(f"缺少必填字段 {field}")
            elif value is not None and not isinstance(value, expected_type):
                errors.append(f"字段 {field} 类型错误：期望 {expected_type.__name__}，实际 {type(value).__name__}")

        # 校验列表元素的内部结构
        for list_field, element_schema in self._LIST_ELEMENT_SCHEMA.items():
            items = result.get(list_field, [])
            if not isinstance(items, list):
                if items:  # 存在但不是列表
                    errors.append(f"字段 {list_field} 应为列表，实际为 {type(items).__name__}")
                continue
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{list_field}[{i}] 应为 dict，实际为 {type(item).__name__}")
                    continue
                for elem_field, (elem_type, elem_required) in element_schema.items():
                    elem_value = item.get(elem_field)
                    if elem_required and not elem_value:
                        errors.append(f"{list_field}[{i}].{elem_field} 缺失")
                    elif elem_value is not None and not isinstance(elem_value, elem_type):
                        errors.append(
                            f"{list_field}[{i}].{elem_field} 类型错误："
                            f"期望 {elem_type.__name__}，实际 {type(elem_value).__name__}")

        return errors


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

_PLANNING_PROMPT = """你是规划格式化器。提取 Author 已写的内容，并**补上遗漏**——如果 Author 在内容中写了某角色的言行但漏列入场/退场，帮它补上（该角色必须在可用角色列表中）。但不要编造 Author 从未提过的角色或授权。没写的字段留空。

Author 提交的文本末尾附有「可用角色列表」——add_enter/add_exit 会自动校验角色名是否在此列表中，不在则拒绝。NPC 不列入 enter/exit，只在 content 中描述。

工具：
- fill(field, value)：填入字段。field: episode_name, outline, author_notes
- add_available_character(name, reason)：添加可出场角色（必须在可用角色列表中；NPC 不列入）
- add_scene(name, location, content)：添加一个小节
- add_enter(name, reason)：添加入场角色（必须在可用角色列表中，硬性拒绝）
- add_exit(name, reason)：添加退场角色（必须在可用角色列表中，硬性拒绝）
- add_worldview_grant(path)：添加世界观授权（仅 Author 明确写了才调）
- add_note(text)：添加备注
- check_completeness()：列必填项 + 小节衔接检查 + 交叉校验（enter/exit 角色是否在 available_characters 中）
- done()：完成

流程：fill 各字段 → add_available_character → add_scene → add_enter/add_exit → add_worldview_grant → check_completeness → done"""

_SUMMARY_PROMPT = """你是总结格式化器。逐字段填入 Author 提交的总结内容。

工具：
- fill(field, value)：填入字段。field: episode_summary(本幕总结), plot_update(剧情走向)
- add_foreshadowing(action, content)：action: added(新增) / resolved(回收)
- set_advance_chapter(true/false)：是否推进到下一章
- set_gap(small_gap/big_gap)：场景间隔
- add_note(text)：添加备注
- check_completeness()
- done()

流程：填入、备注、检查、done。互不依赖的同一轮发出。"""


# ═══════════════════════════════════════════════════════════════
# MD 组装
# ═══════════════════════════════════════════════════════════════

def _assemble_planning_md(data: dict) -> str:
    lines = ["# 规划审查\n",
             "\n> 已帮你润色如下。如需修改某一小节，重新提交该小节即可。\n"]

    if data.get("episode_name"):
        lines.append(f"### 小剧场名称\n{data['episode_name']}\n")
    available = data.get("available_characters", [])
    if available:
        lines.append("### 可出场角色\n")
        for a in available:
            reason = f"——{a['reason']}" if a.get("reason") else ""
            lines.append(f"- {a['name']}{reason}")
        lines.append("")
    if data.get("outline"):
        lines.append(f"### 小剧场大纲\n{data['outline']}\n")

    scenes = data.get("scenes", [])
    if scenes:
        lines.append(f"### 小节（共{len(scenes)}个）\n")
        for s in scenes:
            lines.append(f"**{s.get('name','?')}**")
            lines.append(f"- 地点：{s.get('location','?')}")
            enter_list = s.get("enter", [])
            if enter_list:
                lines.append("- 入场：" + "、".join(
                    f"{e['name']}（{e.get('reason','')}）" for e in enter_list))
            lines.append(f"- 内容：{s.get('content','?')}")
            exit_list = s.get("exit", [])
            if exit_list:
                lines.append("- 退场：" + "、".join(
                    f"{e['name']}（{e.get('reason','')}）" for e in exit_list))
            lines.append("")

    grants = data.get("worldview_grants", [])
    if grants:
        lines.append("### 世界观授权\n" + "\n".join(f"- `{g.get('path', g)}`" for g in grants) + "\n")

    if data.get("author_notes"):
        lines.append(f"### 讲述者备注\n{data['author_notes']}\n")

    lines.append("---\n## 完整性检查\n")
    comp = data.get("completeness", {})
    items = [("episode_name", "小剧场名称"), ("outline", "小剧场大纲"),
             ("scenes", "小节")]
    missing = []
    for key, label in items:
        s = comp.get(key)
        lines.append(f"- {'[x]' if s is True else '[?]' if s == 'optional' else '[ ]'} {label}")
        if not s:
            missing.append(label)
    if missing:
        lines.append(f"\n[!] 缺失: {', '.join(missing)}")
    else:
        lines.append("\n[OK] 必填项已齐全")

    for title, key in [("备注", "suggestions"), ("警告", "warnings")]:
        items = data.get(key, [])
        if items:
            lines.append(f"\n## {title}\n")
            for item in items:
                lines.append(f"- {item}")
    return "\n".join(lines)


def _assemble_summary_md(data: dict) -> str:
    lines = ["# 总结审查\n"]
    if data.get("episode_summary"):
        lines.append(f"### 本幕总结\n{data['episode_summary']}\n")
    if data.get("plot_update"):
        lines.append(f"### 剧情走向\n{data['plot_update']}\n")
    fs = data.get("foreshadowing", {})
    if fs.get("added") or fs.get("resolved"):
        lines.append("### 伏笔操作")
        for a in fs.get("added", []):
            lines.append(f"- 新增：{a}")
        for r in fs.get("resolved", []):
            lines.append(f"- 回收：{r}")
        lines.append("")
    if data.get("advance_chapter"):
        lines.append("### 章节建议\n建议进入下一章。\n")
    if data.get("gap"):
        lines.append(f"### 场景间隔\n{'大间隔' if data['gap'] == 'big_gap' else '小间隔'}\n")

    lines.append("---\n## 完整性检查\n")
    comp = data.get("completeness", {})
    items = [("episode_summary", "本幕总结"), ("plot_update", "剧情走向")]
    missing = []
    for key, label in items:
        s = comp.get(key)
        lines.append(f"- {'[x]' if s else '[ ]'} {label}")
        if not s: missing.append(label)
    if missing:
        lines.append(f"\n[!] 缺失: {', '.join(missing)}")
    else:
        lines.append("\n[OK]")

    for title, key in [("备注", "suggestions"), ("警告", "warnings")]:
        items = data.get(key, [])
        if items:
            lines.append(f"\n## {title}\n")
            for item in items:
                lines.append(f"- {item}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

async def format_planning(content: str, story_id: str,
                          *, on_step=None, on_token=None,
                          worldview_paths: set[str] | None = None) -> tuple[dict, str]:
    agent = FormatterAgent(story_id, "planning", worldview_paths=worldview_paths)
    await agent.run(content, on_step=on_step, on_token=on_token)
    data = agent.build_result()
    if data.get("error"):
        return data, f"# 规划审查\n\n[!] Formatter 出错: {data.get('error')}"
    return data, _assemble_planning_md(data)


async def format_summary(content: str, story_id: str,
                         *, on_step=None, on_token=None,
                         worldview_paths: set[str] | None = None) -> tuple[dict, str]:
    agent = FormatterAgent(story_id, "summary", worldview_paths=worldview_paths)
    await agent.run(content, on_step=on_step, on_token=on_token)
    data = agent.build_result()
    if data.get("error"):
        return data, f"# 总结审查\n\n[!] Formatter 出错: {data.get('error')}"
    return data, _assemble_summary_md(data)
