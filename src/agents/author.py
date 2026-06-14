"""Author Agent — 创作者，负责小剧场规划、伏笔管理、剧情总结。"""
from langchain_core.tools import tool, BaseTool

from src.agents.base import BaseAgent
from src.config import load_llm_config, list_characters


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

AUTHOR_SYSTEM_PROMPT = """你是一个小说世界的创作者（Author）。你的职责是规划小剧场、管理剧情走向。你不直接叙事——叙事由 Narrator（讲述者）负责。

## 核心原则

**单场景原则**：你每次只能规划一个小剧场，必须等到这个小剧场上演完成后，拿到实际的演出效果后才能规划下一个小剧场。且每个小剧场只覆盖一个场景——一个地点、一段连续时间、一组在场角色。就像话剧的一幕戏：灯光打在一个舞台上，观众视线不能跳转到别处。角色可以进场退场，但地点不变、时间连续、视角不切。如果故事需要另一个地点——那是下一个小剧场的事。

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

**场景地点**
本小剧场所发生的具体地点和时间。一个场景对应一个地点，不能切换。
[正确] 「地点A，傍晚」
[正确] 「地点B，清晨」
[错误] 「地点A→地点B→地点C」（三个场景，应拆为三个小剧场）

**小剧场名称**
简短、有辨识度的标题。示例：「食堂风波」「开学日」「深夜的图书馆」

**概要**
一句话概括本幕剧情，纯读者视角。只描述可见的事件发展。
[正确] 「角色A在食堂偶遇角色B，两人的对话被路过的角色C打断」
[错误] 「角色A和角色B对话时角色C在暗中观察，怀疑角色A的身份」

**角色安排**
列出本幕出场的所有角色。每个角色标注：进场时机、初始状态、**戏份层级**。

戏份层级——控制该角色本集的发言自由度：
- **主线**：本集核心角色，可以自由发言、反应、推动剧情。Narrator 正常给他分配对话轮次。
- **过场**：本集有少量戏份，但到此为止。在角色安排中给出他需要表达的**台词方向或意图**（不是逐字剧本，是"Narrator引导角色说出这个意思"）。Narrator 用导演提示引导角色往这个方向发言，但角色用自己的风格表达。发言一次后不再 pick。
- **点缀**：本集存在但无台词。只通过旁白提及（"精神海中某处，XXX翻了个身"），不分配 speak 轮次。

选层级的规则：
- 细纲中只出现一句话/一个动作 → 过场
- 细纲中有多轮对话或关键行动 → 主线
- 细纲中没有具体言行，但需要氛围存在 → 点缀
- 用户角色 {user_character} 必须为主线

重要：剧情细纲中出现过具体言行（说话、动作、内心反应）的每一个角色，都必须出现在角色安排中——哪怕只有一句话。

[正确] 「角色A（主线）：开头就在食堂，正在打饭，看起来有些心不在焉。\n角色B（过场）：中途从门口探头，对A表示关心和想帮忙——引导他说出这个意思即可，说完就离开。\n角色C（点缀）：食堂角落默默吃饭，旁白带过即可。」
[错误] 「角色A：开头就在食堂，因为能力觉醒出问题而心不在焉」——未标层级
[错误] 细纲中写了"角色B在窗外喊道……"但角色安排中没有角色B → 角色B必须补上

**期望结局**
本集结束时的剧情状态，读者视角。
[正确] 「角色A和角色B交换了测试心得，对彼此产生初步好感」
[错误] 「角色C确认角色A能力异常，决定上报某组织」

**剧情细纲**
场景的流程、节奏、关键节拍。这是给 Narrator 的执行指引。
[注意]可以用暗示性语言——例如"角色C在此处应有审视角色A的微表情"，但绝不能直接写出隐藏设定的具体内容。
[正确] 「1. 食堂环境描写 2. 角色A独自打饭，若有所思 3. 角色B从训练场过来打招呼 4. 两人聊起能力测试 5. 角色C路过，停下观察——注意TA的眼神应让读者感到微妙不安 6. 角色B察觉到气氛有点怪 7. 各自散去」
[错误] 「5. 角色C用某组织秘法探测到角色A的XX能力异常，决定跟踪调查」

**世界观授权**
[注意] 授权 = 永久揭秘。被授权的世界秘闻 Narrator 将永远知晓其全部内容。请慎重。
[注意] 授权给 Narrator ≠ 所有角色都知道了——角色有独立的授权记录。Narrator 知道了不代表角色知道。
格式：用 `` ` `` 包裹完整的世界观路径。可附带简短的授权原因说明。
[正确] 「`XX体系` — 本集涉及能力测试，Narrator 需要了解等级体系以准确描述」
[正确] 「`XX体系`, `某家族档案/血脉力量` — 多个路径逐一标出」
[错误] 「XX体系：把初级到顶级的等级写在这里...」（不要把授权内容写出——授权的是路径，Narrator 自己会查）
路径必须是世界观目录中真实存在的条目。公开世界观自动可用，只需授权世界秘闻。

**讲述者备注**
给 Narrator 的表演指导。氛围基调、节奏提示、镜头感、模糊暗示。
如有过场/点缀角色，务必在此提醒 Narrator 控制戏份——"角色B的台词方向是关心A的伤势，引导他表达这个意思后即退场，不要延长"。
[正确] 「食堂场景整体偏暖色调。角色C出现时节奏微顿，像一阵冷风擦过。角色B为过场——一句台词后即退场。」
[错误] 「角色C是某个等级的高手，用精神力扫视角色A」

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
1. 先了解当前大纲位置：read_info("outline")
2. 根据需要查阅世界观、角色、历史、伏笔等信息
3. 你**只需要规划接下来的一个小剧场**（单场景）。大纲中的后续章节现在还不需要规划
4. 如果你对更远期的剧情有设想——用 note('add', '...') 记录下来，下次规划时会自动呈现给你
5. 按定义提交当前小剧场的各 section
6. 觉得差不多了 → review()
7. 根据 review 返回的结果修正
8. 确认无误 → done()

总结阶段同理——收到本幕对话记录后，用 submit 提交总结和剧情更新，review 检查，done() 完成。"""


# ═══════════════════════════════════════════════════════════════
# 模块级工具
# ═══════════════════════════════════════════════════════════════

@tool
def submit(section: str, content: str) -> str:
    """提交一段规划/总结内容。

    规划阶段建议：场景地点、小剧场名称、概要、角色安排、期望结局、剧情细纲、世界观授权、讲述者备注
    总结阶段建议：本幕总结、剧情走向、伏笔操作
    也可自创章节名。各章节填写规范见系统提示词。
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
    fmt = format_planning if agent._phase == "planning" else format_summary
    result_json, md = await fmt(
        text, agent.story_id,
        on_step=getattr(agent, "_on_step", None),
        on_token=getattr(agent, "_on_token", None))
    agent._last_review_json = result_json
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

    def __init__(self, story_id: str):
        super().__init__(story_id)
        self._char_names = list_characters(story_id)
        self._submitted_sections: list[dict] = []
        self._phase: str = "planning"
        self._last_review_json: dict | None = None
        self._notes: list[dict] = []
        self._user_character: str = ""

    def _reset_submissions(self):
        self._submitted_sections = []
        self._last_review_json = None

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

        @tool(description="审查当前所有已提交内容。调 formatter 子 agent 输出评审报告。")
        def review() -> str:
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

    def build_planning_prompt(
        self,
        *,
        worldview_overview: str = "",
        character_overview: str = "",
        foreshadowing_overview: str = "",
        outline_progress: str = "",
        prev_episode_summary: str = "",
        **kwargs,
    ) -> str:
        """构建小剧场规划阶段的 user message。"""
        parts = []
        parts.append("# 当前阶段：规划阶段\n")
        parts.append("你需要规划**下一个小剧场**（单场景）。大纲中的后续章节现在不需要规划。")
        parts.append("如果你对更远期有设想，用 note('add', '...') 记录——下次规划时这些笔记会自动呈现。\n")
        parts.append("先用 read_info() 查阅需要的条目，再用 submit 逐步提交规划：")

        parts.append(f"## 大纲进度\n{outline_progress}")

        if worldview_overview:
            parts.append(f"## 世界观\n{worldview_overview}")
        if character_overview:
            parts.append(f"## 角色\n{character_overview}")
        if foreshadowing_overview:
            parts.append(f"## 当前伏笔\n{foreshadowing_overview}")
        if prev_episode_summary:
            parts.append(f"## 上一幕总结\n{prev_episode_summary}")

        if self._notes:
            notes_text = "\n".join(
                f"- [{n['id']}] {n['content']}" for n in self._notes)
            parts.append(f"## 你的长期笔记\n{notes_text}")

        parts.append(
            "\n建议顺序：场景地点 → 小剧场名称 → 概要 → 角色安排 → 期望结局 → 剧情细纲 → 世界观授权（如需）→ review → done。"
        )
        return "\n\n".join(parts)

    def build_summary_prompt(
        self,
        *,
        episode_transcript: str,
        worldview_overview: str = "",
        character_overview: str = "",
        foreshadowing_overview: str = "",
        outline_progress: str = "",
        **kwargs,
    ) -> str:
        """构建小剧场总结阶段的 user message。"""
        parts = []
        parts.append("# 本小剧场已结束，请进行总结\n")
        parts.append(f"## 本幕对话记录\n\n{episode_transcript}")

        parts.append(
            "\n建议顺序：本幕总结 → 剧情走向 → 伏笔操作（按需）→ 章节建议 → review → done。"
        )
        return "\n\n".join(parts)
