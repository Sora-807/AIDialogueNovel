"""Author Agent — 创作者，负责小剧场规划、伏笔管理、剧情总结。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

AUTHOR_SYSTEM_PROMPT = """你是一个小说世界的创作者（Author）。你的职责是规划小剧场、管理剧情走向。你不直接叙事——叙事由 Narrator（讲述者）负责。

## 核心原则

**战争迷雾原则**：世界观的隐秘内容是逐步揭示给 Narrator 的。未被授权的世界观条目，Narrator 完全不知道其存在。授权等于永久烧掉战争迷雾——Narrator 从此可以自由使用这些信息。如果你希望保持神秘感，就绝对不要授权，而是通过剧情细纲的暗示让 Narrator 感知到"这里有异常"。

**不剧透原则**：剧情细纲和讲述者备注只能以指引和暗示的方式描述，绝不能直接写出隐藏设定的原文。例如——可以写"角色A在此处审视角色B，似乎注意到了什么异常"，但不能写"角色A是卧底，他在监视角色B的行动"。

**读者视角原则**：小剧场名称、概要、期望结局都从读者能看到的视角描述。读者看到什么、感觉到什么——而不是幕后发生了什么。

**用户角色原则**：本故事中「{user_character}」由用户（人类玩家）扮演。每个小剧场都必须让 {user_character} 出场。剧情细纲和讲述者备注只能给 {user_character} 提供感官指引和情绪方向，绝对不能替 {user_character} 做决定——包括对话内容、行动选择、感情走向。{user_character} 的未来永远是开放的。

---

## 你的工具

- read_info(类别, 路径)：查阅信息。
  路径为空时列出该类别下的所有条目。
  可用类别：
  - worldview（世界观）— 路径填世界观文件路径，如 `魂师体系`
  - character（角色）— 路径填 `角色名`（看概览）、`角色名/profile`（全貌设定，用于规划人物未来走向）、`角色名/state`（当前状态，用于了解人物当下的故事状况）
  - outline（大纲）— 路径填章节序号或名称
  - history（历史摘要）— 路径为空看最近几集摘要
  - foreshadowing（伏笔）— 路径为空列全部伏笔
- note(操作, 内容/ID)：管理你的长期工作记忆——记录跨小剧场的设想，后续规划时自动呈现。
  - note('add', '内容')：新增一条笔记，自动分配 ID
  - note('list')：列出所有笔记（按创建顺序）
  - note('delete', 'note_xxx')：删除指定 ID 的笔记
- submit(章节, 内容)：提交一段规划或总结内容。每次只提交**一个小剧场**（一个场景）。
- review()：审查当前所有已提交内容，检查完整性。done 之前必须调用。
- done()：全部完成。调用后退出当前阶段。

---

## 规划阶段——各 Section 精确定义

**小剧场名称**
简短、有辨识度的标题。
例如：「深夜的走廊」

**可出场角色**
列出本幕可能出现的所有角色（含用户角色）。只要不违背剧情、有理由出现在此地即可——不必真的出场。Narrator 在推进时会从这里选取 NPC 或补充角色，不需要的角色可以不出现。每个角色附一句出场理由或场景位置。
格式：角色A（在学院上课，路过此处很自然）；角色B（住在附近，听到动静可能过来查看）

**小剧场大纲**
本幕的开端、发展和结局。不限字数，但需注意只能描写大致的情节发展不能直接写到细节的比如人物对话。一幕的体量可以稍微大一些类似于一集动漫，会经历可能不止一个小事件。
例如：
【开端】
傍晚，主角A为了寻找失踪的线索，潜入一座废弃的研究所。建筑内部错综复杂，到处是被破坏的痕迹。他发现了一本残破的日志，里面提到了某个实验项目。正当他准备离开时，警报突然响起——有人闯入了系统，但不是他触发的。A被迫躲进通风管道。

【发展】
通过管道移动时，A听到下方传来脚步声和对话声——是研究所的安保部队，似乎在追捕另一个入侵者。A从排风口看到B被逼到角落，即将被抓获。犹豫之后，A制造了声响引开注意，帮B争取了逃脱时间。两人在另一层意外相遇，B警惕地打量他，简短交换了名字后决定分头行动。A继续深入寻找日志缺失的页面，途中遇到越来越多的阻碍——锁死的门、失效的电力系统、以及似乎被刻意抹除的数据。与此同时，B在另一条路线上触发了隐藏机关，整栋楼的电力短暂恢复又熄灭，A趁机进入了核心实验区，但发现那里已经空了，只剩下一台仍在运转的记录设备。他启动设备，看到了某段录像——画面中出现了他自己。

【结局】
录像内容让A陷入混乱。就在这时，B也赶到了核心区，两人对峙。A质问B的真实身份和目的，B没有正面回答，而是将一把钥匙扔给他，说了一句“你来的地方还有答案”。外面的安保部队开始强攻大门。两人被迫从紧急通道撤离，在建筑外的旧停车场分道扬镳。A拿着钥匙，回头望了一眼燃烧中的研究所，脑海中反复回放那段录像的画面。夜色中，他走向下一个目的地。


**小剧场细纲**
小剧场由**小节**组成，小节之间情节紧凑、情绪连贯。先写地点和内容，出入场另填。

格式：
### 小节名称
- 地点：xxx
- 内容：本小节的事件发展。不能写具体的人物对话，留下开放性。每个小节要有明确的开端和结局，对过程只做大致的预设。

示例：
### 小节 1
- 地点：走廊，深夜
- 内容：深夜的走廊寂静无人，月光从窗外铺洒进来。A在走廊里徘徊等人，注意力被月色吸引，有些出神。就在这时，B从拐角后走出，两人都未曾留意，差点撞上。短暂的目光交汇后，B神色平静地侧身离开。A的目光不自觉地追随了她的背影片刻，直到他真正在等的人的脚步声从身后响起，才将他的注意力拉回。

### 小节 2
- 地点：走廊拐角处
- 内容：C或许是拍了拍A的肩膀，或许是轻声唤了他的名字，将A从刚才的短暂失神中拉回。两人在窗边开始交谈，对话的氛围与月色一样，表面平静，但或许暗藏一些不为人知的紧张。他们的对话提到了今晚真正要处理的事情。而就在他们的对话即将结束时，A的眼角余光可能瞥见了拐角处，那个B消失的方向，似乎有个人影一闪而过，也可能只是错觉。


**出入场**
格式：
### 小节 1
入场：角色A（一直在走廊徘徊），角色B（从拐角出来，差点撞上A）
退场：角色B（撞完人慌慌张张的走了）

### 小节 2
入场：角色C（刚处理完事情看到了角色A在等自己）
退场：无

提示：
- 根据细纲中的剧情，为每个小节填完入场和退场角色。
- 后面的小节继承前面小节的人物登场状态，并且最初舞台为空，所以第一小节的入场角色就是第一小节中的所有登场角色，没有退场的角色后续不用重复入场。
- 填入入场和退场的角色必须是用户提供的**角色总览**中的角色，细纲中提到的 NPC 不列入入场和退场名单。

下面列几种特殊的出入场要使用的场景：
1. 某些角色在偷听。这种角色会获得本小节入场角色的所有对话，但是他可能完全不说法，这种特定的只倾听的场景需要让角色入场，等到偷听结束再让他退场。
2. 某些角色戏份少/发言少。有某些情况可能是比如主角身上寄宿了一个灵魂体，它有时沉睡有时清醒，有些剧情会要求它出来说句话然后继续沉睡，那么只要是涉及它说话的情节，就必须让它入场，沉睡之后再退场。如果是沉睡但需要感知到信息那就和情况 1 一样，需要入场。
3. 某些角色只是被提及。有时角色会讨论某些人物，这种情况角色完全不在场也不会感知到信息，那就不能让他入场。
关键原则：出入场控制信息边界——入场即登台能感知到一切发言，退场即断线不再知道后续。


**世界观授权**
用 `` ` `` 包裹路径。公开世界观自动可用，只授权世界秘闻。
[正确] 「`XX体系` — 本集涉及能力测试」
[错误] 「XX体系：把等级写在这里...」（只授权路径）

**讲述者备注**
氛围基调、节奏提示、镜头感。
[正确] 「走廊冷色调。A脚步偏慢。B出场时节奏突然加快。」
[错误] 「角色C是高手，用精神力扫视A」

---

## 总结阶段——各 Section 精确定义

**本幕总结**
本幕实际发生的事，读者视角的剧情概述。

**剧情走向**
更新短期剧情安排，后续几集的剧情走向描述。

**伏笔操作**
新增或回收伏笔。描述伏笔内容及其状态变化。

**章节建议**
建议是否推进到下一章。本章内容已经充分展开、需要新的舞台时建议进入下一章；如果当前章还有更多场景可以挖掘则建议不进入。
[正确] 「建议进入下一章——本章的森林场景已充分展开，霍雨浩需要新的舞台。」
[正确] 「暂不进入下一章，本章还可以围绕史莱克入学展开更多场景。」

**场景间隔（gap）**
判断本幕与下一幕之间的叙事间隔——影响 Agent 是否保留上下文历史。
- **small_gap**：这是本章的常规连续场景。时间接续、地点相近或角色重叠。Author/Narrator/Character 应保留上下文继续。
- **big_gap**：发生了时间跳跃、地点完全切换、章节推进，或剧情需要"另起一段"。Agent 可清空上下文重新开始。
选择 big_gap 的场景：章节推进、时间跨越数天以上、切换到完全无关的地点和角色群。
没有特殊情况默认 small_gap。
[正确] 「small_gap——下一幕继续在同一校园内，时间紧接着。」

---

## 工作流程

规划阶段建议思考顺序：
1. read_info 了解大纲位置、角色状态、世界观
2. submit("小剧场名称", "...") + submit("可出场角色", "...")
3. submit("小剧场大纲", "...")
4. 按照小剧场大纲拆分小节 → submit("小剧场细纲", "...")
5. 根据小剧场细纲内容逐小节填出入场 → submit("出入场", "...")
6. submit("世界观授权", "...") + submit("讲述者备注", "...")
7. review 检查 → 修正 → done()

总结阶段同理——收到对话记录后，依次提交总结各 section，review，done()。

可以在同一轮中同时调用多个工具。只要互不依赖就可批量发出。"""


# ═══════════════════════════════════════════════════════════════
# 模块级工具
# ═══════════════════════════════════════════════════════════════

@tool
def submit(section: str, content: str) -> str:
    """提交一段规划/总结内容。

    规划阶段建议：小剧场名称、可出场角色、小剧场大纲、小剧场细纲、出入场、世界观授权、讲述者备注
    总结阶段建议：本幕总结、剧情走向、伏笔操作、章节建议、场景间隔
    """
    return "OK"


@tool
def done() -> str:
    """规划/总结全部完成。调用后退出当前阶段。"""
    return "OK"


# ═══════════════════════════════════════════════════════════════
# 模块级辅助函数
# ═══════════════════════════════════════════════════════════════

async def _do_review(agent, text: str) -> str:
    """Author._make_review 的工具函数——调用 formatter 子 agent 输出评审报告。"""
    from src.agents.formatter import format_planning, format_summary
    from src.core.logger import get_logger
    review_log = get_logger(agent.story_id)
    review_log.info("【Author·Review】%d 个 section, %d 字 → formatter 审查中…",
                    len(agent._submitted_sections), len(text))

    # 将角色名列表附加到审查文本中，供 formatter 校验
    character_names = "、".join(agent._character_names)
    full_text = text + (f"\n\n---\n## 可用角色列表\n{character_names}" if character_names else "")

    worldview_paths = set(agent.universe.worldviews.keys()) if agent.universe else None
    fmt = format_planning if agent._phase == "planning" else format_summary
    result_json, md = await fmt(
        full_text, agent.story_id,
        on_step=getattr(agent, "_on_step", None),
        on_token=getattr(agent, "_on_token", None),
        worldview_paths=worldview_paths)
    agent._last_review_json = result_json
    # review 成功后，用 formatter 输出替换旧提交，保持与 JSON 一致
    agent._apply_review_result(result_json)
    if result_json.get("error"):
        review_log.warning("【Author·Review】formatter 出错: %s", result_json.get("error"))
    else:
        comp = result_json.get("completeness", {})
        filled = sum(1 for v in comp.values() if v is True)
        total = len(comp)
        wcount = len(result_json.get("warnings", []))
        review_log.info("【Author·Review】OK | md=%d 字 | %d/%d 完成 | %d 条警告",
                        len(md), filled, total, wcount)
    return md


# ═══════════════════════════════════════════════════════════════
# Agent 类
# ═══════════════════════════════════════════════════════════════

class AuthorAgent(BaseAgent):
    """创作者 Agent。"""

    @property
    def agent_name(self) -> str:
        return "Author"

    def __init__(self, story_id: str, universe=None):
        super().__init__(story_id, universe=universe)
        self._submitted_sections: list[dict] = []
        self._phase: str = "planning"
        self._last_review_json: dict | None = None

    @property
    def _character_names(self) -> list[str]:
        if self.universe:
            return self.universe.character_names()
        from src.config import list_characters
        return list_characters(self.story_id)

    @property
    def _notes(self) -> list[dict]:
        if self.universe:
            return self.universe.author_notes
        return []

    @_notes.setter
    def _notes(self, v):
        if self.universe:
            self.universe.author_notes = v

    @property
    def _user_character(self) -> str:
        if self.universe:
            return self.universe.user_character
        return ""

    def load_state_from_universe(self):
        """从 Universe 恢复 Author 完整状态。"""
        super().load_state_from_universe()
        if self.universe is None:
            return
        # _submitted_sections 和 _last_review_json 是瞬态，不需要恢复
        # _notes 和 _user_character 通过 property 自动从 universe 读取

    def _reset_submissions(self):
        self._submitted_sections = []
        self._last_review_json = None

    def _apply_review_result(self, result: dict):
        """用 formatter 输出替换旧提交，保持与 JSON 一致。"""
        if self._phase != "planning":
            return
        self._submitted_sections = []
        if result.get("episode_name"):
            self._submitted_sections.append({"section": "小剧场名称", "content": result["episode_name"]})
        available = result.get("available_characters", [])
        if available:
            text = "；".join(f"{a['name']}（{a.get('reason','')}）" for a in available)
            self._submitted_sections.append({"section": "可出场角色", "content": text})
        if result.get("outline"):
            self._submitted_sections.append({"section": "小剧场大纲", "content": result["outline"]})
        # 将 scenes 数组格式化成文本：细纲（地点+内容）+ 出入场
        scenes = result.get("scenes", [])
        if scenes:
            outline_lines = []
            entry_lines = []
            for s in scenes:
                outline_lines.append(f"### {s.get('name','?')}")
                outline_lines.append(f"- 地点：{s.get('location','?')}")
                outline_lines.append(f"- 内容：{s.get('content','?')}")
                outline_lines.append("")
            for s in scenes:
                entry_lines.append(f"### {s.get('name','?')}")
                enter_list = s.get("enter", [])
                entry_lines.append("入场：" + ("、".join(
                    f"{e['name']}（{e.get('reason','')}）" for e in enter_list) if enter_list else "（无）"))
                exit_list = s.get("exit", [])
                entry_lines.append("退场：" + ("、".join(
                    f"{e['name']}（{e.get('reason','')}）" for e in exit_list) if exit_list else "（无）"))
                entry_lines.append("")
            self._submitted_sections.append({"section": "小剧场细纲", "content": "\n".join(outline_lines)})
            self._submitted_sections.append({"section": "出入场", "content": "\n".join(entry_lines)})
        if result.get("worldview_grants"):
            paths = [g.get("path", g) if isinstance(g, dict) else g for g in result["worldview_grants"]]
            self._submitted_sections.append({"section": "世界观授权", "content": "、".join(paths)})
        if result.get("author_notes"):
            self._submitted_sections.append({"section": "讲述者备注", "content": result["author_notes"]})

    def _record_submit(self, section: str, content: str):
        self._submitted_sections.append({"section": section, "content": content})

    def _build_sections_text(self) -> str:
        """拼接所有已提交内容为一段 markdown。"""
        if not self._submitted_sections:
            return ""
        return "\n\n".join(
            f"## {s['section']}\n\n{s['content']}"
            for s in self._submitted_sections
        )

    @property
    def last_review_json(self) -> dict | None:
        """引擎用：最近一次 review 产出的结构化 JSON。"""
        return self._last_review_json

    def _valid_section_names(self) -> list[str]:
        if self._phase == "planning":
            return ["小剧场名称", "可出场角色", "小剧场大纲", "小剧场细纲", "出入场", "世界观授权", "讲述者备注"]
        return ["本幕总结", "剧情走向", "伏笔操作", "章节建议", "场景间隔"]

    # ── BaseAgent 接口 ──

    @property
    def system_prompt(self) -> str:
        return AUTHOR_SYSTEM_PROMPT.format(user_character=self._user_character or "（未设定）")

    @property
    def tools(self) -> list:
        return [
            self._make_note(),
            submit,
            self._make_review(),
            done,
        ]

    @property
    def exit_tool(self) -> str:
        return "done"

    def validate_tool(self, tool_name: str, args: dict) -> tuple[bool, str]:
        if tool_name == "submit":
            section = args.get("section", "")
            content = args.get("content", "")
            if not section.strip():
                return False, "submit 需要提供 section（章节名）"
            if not content.strip():
                return False, "submit 需要提供 content（内容）"
            valid_sections = self._valid_section_names()
            if section not in valid_sections:
                return False, f"未知 section「{section}」。可用：{'、'.join(valid_sections)}"
            self._record_submit(section, content)
        elif tool_name == "note":
            action = args.get("action", "")
            content = args.get("content", "")
            if action not in ("add", "list", "delete"):
                return False, "note 的 action 必须是 add / list / delete"
            if action in ("add", "delete") and not content.strip():
                return False, f"note {action} 需要提供 content"
        return True, ""

    # ── review 子 agent ──

    def _make_review(self):
        import asyncio
        agent = self

        @tool
        def review() -> str:
            """审查当前所有已提交内容。调 formatter 子 agent 输出评审报告。"""
            text = agent._build_sections_text()
            if not text.strip():
                return "# 审查\n\n尚未提交任何内容。"
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(_do_review(agent, text))
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(_do_review(agent, text), loop)
            return future.result(timeout=120)

        return review

    # ── note 工作记忆 ──

    def _make_note(self):
        import uuid
        agent = self

        @tool(description="管理长期工作记忆。action: add（新增）/ list（列出）/ delete（删除）。")
        def note(action: str, content: str = "") -> str:
            if action == "add":
                nid = "note_" + uuid.uuid4().hex[:6]
                agent._notes.append({"id": nid, "content": content})
                return f"[OK] 已添加 {nid}"
            elif action == "list":
                if not agent._notes:
                    return "（暂无笔记）"
                return "\n".join(
                    f"  [{n['id']}] {n['content'][:120]}" for n in agent._notes)
            elif action == "delete":
                before = len(agent._notes)
                agent._notes = [n for n in agent._notes if n["id"] != content]
                if len(agent._notes) < before:
                    return f"[OK] 已删除 {content}"
                return f"未找到 {content}"
            return "未知操作。可用：add / list / delete"
        return note

    # ── prompt 构建 ──

    def build_planning_prompt(self) -> str:
        """构建小剧场规划阶段的 user message。从 Universe 自取数据。"""
        u = self.universe
        parts = []
        parts.append("# 当前阶段：规划阶段\n")
        parts.append("你需要规划**下一个小剧场**。大纲中的后续章节现在不需要规划。")
        parts.append("如果你对更远期有设想，用 note('add', '...') 记录——下次规划时这些笔记会自动呈现。\n")
        parts.append("先用 read_info() 查阅需要的条目，再用 submit 逐步提交规划：")

        parts.append(f"## 大纲进度\n{u.outline_progress()}")
        parts.append(f"## 世界观\n{u.worldview_overview()}")
        parts.append(f"## 角色总览\n{u.character_overview()}")
        parts.append(f"## 当前伏笔\n{u.foreshadowing_overview()}")

        prev = u.prev_episode_summary()
        if prev:
            parts.append(f"## 上一幕总结\n{prev}")

        if self._notes:
            notes_text = "\n".join(
                f"- [{n['id']}] {n['content']}" for n in self._notes)
            parts.append(f"## 你的长期笔记\n{notes_text}")

        parts.append(
            "\n建议顺序：场景地点 → 小剧场名称 → 概要 → 角色安排 → 期望结局 → 剧情细纲 → 世界观授权（如需）→ review → done。"
        )
        return "\n\n".join(parts)

    def build_summary_prompt(self, *, episode_transcript: str) -> str:
        """构建小剧场总结阶段的 user message。"""
        parts = []
        parts.append("# 本小剧场已结束，请进行总结\n")
        parts.append(f"## 本幕对话记录\n\n{episode_transcript}")

        parts.append(
            "\n建议顺序：本幕总结 → 剧情走向 → 伏笔操作（按需）→ 章节建议 → review → done。"
        )
        return "\n\n".join(parts)
