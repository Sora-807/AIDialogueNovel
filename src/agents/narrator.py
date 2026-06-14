"""Narrator Agent — 讲述者，负责写旁白和控制发言权。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

NARRATOR_SYSTEM_PROMPT = """你是导演兼讲述者。每一幕 Author 会给你一份剧本，你的任务是根据剧本指挥这一幕的演出——写旁白铺设场景，把发言权交给角色，在目标达成时喊 Cut。

## 旁白写作规则（speak）

speak() 输出的是**公开旁白**——舞台上的所有角色都会看到，所以必须用**第三人称上帝视角**。

- 角色用准确名字，不用”你”、”他”等指代不清的代词
- 描述场景、动作、氛围时写明角色名
- NPC 的言行也嵌入旁白，用第三人称

正确示例：
  speak(“晨雾中，史莱克城的轮廓渐渐清晰。霍雨浩站在城门前，抬头望着巍峨的城墙。”)
  speak(“路边茶摊的老板娘探出头，冲着霍雨浩喊道：”小兄弟，进来喝碗茶歇歇脚！””)

错误示例（使用了”你”）：
  speak(“你站在城门前，抬头望着巍峨的城墙。”)

---

## 你的工具

- speak(文本)：输出一段小说式旁白。第三人称，角色用准确名字。1-3 句，精炼有力。
- pick_speaker(角色名, 导演提示)：把发言权交给一个角色。可选第二个参数「导演提示」（尽量少用，详见下方）。
- read_info(类别, 路径)：查阅信息。
  - worldview（世界观）— 路径留空列出可访问条目，填路径名查看正文
  - character（角色）— 路径填角色名查看其当前状态。路径留空列出本幕出场角色
- manage_stage(action, name, hint?)：管理舞台上的角色。action: 'enter'（入场）/ 'exit'（退场）。name: 角色名。hint: 可选，私密发给该角色的入场/退场提示。
- end_episode(原因)：结束当前小剧场。

### pick_speaker 的导演提示

导演提示是**私密的**——只有被 pick 的角色能收到，所以可以使用”你”指代该角色。但提到其他角色时必须用准确名字。

第二个参数尽量少用——多用于纠正剧情偏差，或角色需要知道环境信息才能合理反应时。

导演提示可以包含：
1. 感官信息——该角色此刻看到了什么、听到了什么、身体感受到了什么
2. 情绪方向——情感倾向的暗示，只给方向不替角色决定

约束：
- 只能写该角色此刻能感知到的事，不能透露他不知道的信息
- 不能替角色做决定（不能写”你决定冲上去”——只能写”愤怒让你的手不自觉按在了剑柄上”）
- 不能透露隐藏设定、剧情走向、他人动机

正确示例（”你”指被 pick 的角色，其他角色用名字）：
  pick_speaker(“霍雨浩”, “一只十年魂兽从灌木丛中窜出，龇牙咧嘴地朝你低吼。王冬在远处惊呼了一声。你本能地想逃，但腿像灌了铅一样。”)

错误示例（透露了角色不该知道的信息）：
  “你知道它是被天梦冰蚕的气息引来的。你应该用精神探测找到它的弱点。”

---

## 工作流程
1. 阅读剧本——可出场角色、剧情细纲（小节）、讲述者备注
2. 如有需要，用 read_info 查阅世界观或角色状态
3. 按小节顺序推进，用 manage_stage 调整舞台
4. 写旁白或 pick 发言人，重复
5. 一小节结束后，用 speak 写旁白过渡，继续下一小节

关键原则：
- 环境没变就不需要旁白，直接切换发言人
- 同角色不宜连续发言
- 可扮演 NPC 发言（第三人称嵌入旁白），但**绝对不要代替主要角色发言**
- 期望结局应自然遵守，不僵硬执行

## 规则告知
- 角色上下场 = 信息隔离。入场登台能感知一切发言，退场断线不再知道后续。
"""


# ═══════════════════════════════════════════════════════════════
# 模块级工具
# ═══════════════════════════════════════════════════════════════

@tool
def speak(text: str) -> str:
    """输出一段小说式旁白。1-3 句，精炼有力。可嵌入 NPC 对话（第三人称）。"""
    return "OK"


@tool
def pick_speaker(name: str, context: str = "") -> str:
    """选择下一个发言的角色。可选 context（导演提示）：角色此刻感知到的环境信息和情绪方向。
    只写角色能感知到的——感官、动作、氛围——不写角色不知道的事。"""
    return "OK"


@tool
def end_episode(reason: str) -> str:
    """结束当前小剧场。reason: 结束原因。"""
    return "OK"


@tool
def manage_stage(action: str, name: str, hint: str = "") -> str:
    """管理舞台上的角色。action: 'enter'（入场）或 'exit'（退场）。
    name: 角色名。hint: 可选，私密发给该角色的入场/退场提示。切换立即生效。"""
    return "OK"


# ═══════════════════════════════════════════════════════════════
# Agent 类
# ═══════════════════════════════════════════════════════════════

class NarratorAgent(BaseAgent):
    """讲述者 Agent。"""

    @property
    def agent_name(self) -> str:
        return "Narrator"

    def __init__(self, story_id: str, universe=None):
        super().__init__(story_id, universe=universe)
        self._episode_character_names: list[str] = []
        self._available_characters: list[dict] = []  # [{name, reason}, ...]

    @property
    def system_prompt(self) -> str:
        return NARRATOR_SYSTEM_PROMPT

    @property
    def tools(self) -> list:
        return [
            speak,
            pick_speaker,
            manage_stage,
            end_episode,
        ]

    @property
    def exit_tool(self) -> list[str]:
        return ["pick_speaker", "end_episode"]

    def validate_tool(self, tool_name: str, args: dict) -> tuple[bool, str]:
        if tool_name == "speak":
            if not args.get("text", "").strip():
                return False, "speak 内容不能为空"
        elif tool_name == "pick_speaker":
            name = args.get("name", "")
            if not name.strip():
                return False, "pick_speaker 需要提供 name"
            if not self._is_valid_character(name):
                return False, f"「{name}」不在出场角色列表中。可用：{'、'.join(self._available_character_names())}"
        elif tool_name == "manage_stage":
            action = args.get("action", "")
            name = args.get("name", "")
            if action not in ("enter", "exit"):
                return False, "manage_stage 的 action 必须是 enter 或 exit"
            if not name.strip():
                return False, "manage_stage 需要提供 name"
            if not self._is_valid_character(name):
                return False, f"「{name}」不是可用角色。可用：{'、'.join(self._available_character_names())}"
        return True, ""

    def set_episode_characters(self, names: list[str]):
        self._episode_character_names = names

    def _available_character_names(self) -> list[str]:
        """pick_speaker / manage_stage 的合法角色池 = enter/exit 角色 ∪ 可出场角色。"""
        names = set(self._episode_character_names)
        for a in self._available_characters:
            names.add(a["name"])
        return list(names)

    def _is_valid_character(self, name: str) -> bool:
        return name in self._available_character_names()

    # ── prompt 构建 ──

    def build_first_message(
        self,
        *,
        episode_name: str = "",
        outline: str = "",
        scenes: list = None,
        available_characters: list = None,
        author_notes: str = "",
        worldview_text: str = "",
    ) -> str:
        """构建第一轮消息——完整剧本，通过队列发给 Narrator。"""
        parts = []

        if episode_name:
            parts.append(f"## {episode_name}")
        if available_characters:
            lines = ["### 可出场角色"]
            for a in available_characters:
                reason = f"——{a['reason']}" if a.get("reason") else ""
                lines.append(f"- {a['name']}{reason}")
            lines.append("\n以上角色只要不违背剧情均可自由安排出场（用 manage_stage 入场），不需要的角色可以不出现。")
            parts.append("\n".join(lines))
        if outline:
            parts.append(f"### 小剧场大纲\n{outline}")

        if scenes:
            parts.append(f"### 小剧场细纲\n")
            for s in scenes:
                parts.append(f"**{s.get('name', '?')}**")
                parts.append(f"- 地点：{s.get('location', '?')}")
                enter_list = s.get("enter", [])
                if enter_list:
                    parts.append("- 新入场角色：" + "、".join(
                        f"{e['name']}（{e.get('reason','')}）" for e in enter_list))
                parts.append(f"- 内容：{s.get('content', '?')}")
                exit_list = s.get("exit", [])
                if exit_list:
                    parts.append("- 退场角色：" + "、".join(
                        f"{e['name']}：{e.get('reason','')}" for e in exit_list))
                parts.append("")

        if author_notes:
            parts.append(f"### 导演备注\n{author_notes}")

        if worldview_text:
            parts.append("---\n以下世界观参考可用 read_info 查阅：")
            parts.append(worldview_text)

        parts.append("\n请先了解剧本。按小节顺序推进，用 manage_stage 管理舞台。")
        return "\n\n".join(parts)

    def build_continue_message(self, queue_messages: str,
                                new_episode: bool = False,
                                stage_names: list = None) -> str:
        parts = []
        if new_episode:
            script = queue_messages.replace("[系统消息]\n", "", 1)
            parts.append(f"## Author 的最新剧本\n{script}")
        else:
            parts.append(f"## 最新消息\n{queue_messages}")

        if stage_names:
            parts.append(f"### 当前舞台上\n{'、'.join(stage_names)}")
        parts.append("\n请决定下一步（环境没变可直接 pick_speaker）。")
        return "\n\n".join(parts)
