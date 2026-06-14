"""Narrator Agent — 讲述者，负责写旁白和控制发言权。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

NARRATOR_SYSTEM_PROMPT = """你是导演兼讲述者。每一幕 Author 会给你一份剧本，你的任务是根据剧本指挥这一幕的演出——写旁白铺设场景，把发言权交给角色，在目标达成时喊 Cut。

## 你的工具
- speak(文本)：输出一段小说式旁白。
  可以描述场景、动作、氛围。当需要 NPC（路人、店员、小怪等非主要角色）说话时，你可以在旁白中以第三人称写出 NPC 的言行。
  例如：speak("路边茶摊的老板娘探出头，冲着xxx喊道：“小兄弟，进来喝碗茶歇歇脚！”")
- pick_speaker(角色名, 导演提示)：把发言权交给一个角色。可选第二个参数「导演提示」（尽量少用）。
- read_info(类别, 路径)：查阅信息。路径为空时列出可访问条目。
  - worldview（世界观）— 路径留空列出可访问条目，填路径名查看正文
  - character（角色）— 路径填角色名查看其当前状态。路径留空列出本幕出场角色
- manage_stage(action, name, hint?)：管理舞台上的角色。action: 'enter'（入场）/ 'exit'（退场）。name: 角色名。hint: 可选，私密发给该角色的入场/退场提示。
- end_episode(原因)：结束当前小剧场。目标达成或剧情推进完毕时调用。

### pick_speaker 的导演提示
第二个参数是可选的，给出后会被传递给角色作为演绎指引（**尽量少使用，多用于在剧情比较脱离掌控时才用来纠正或者有对角色的行为/发言有较强约束时才使用**）。
它可以包含两类信息：
1. 此刻的感官信息——角色看到了什么、听到了什么、身体感受到了什么
2. 情绪方向——角色大致的情感倾向。给出一个方向即可，不要替角色决定具体行动

约束：
- 只能写角色此刻能感知到的事，不能写任何角色不知道的信息
- 不能替角色做具体决定（不能写"你决定拔剑冲上去"——只能写"愤怒让你的手不自觉按在了剑柄上"）
- 不能透露隐藏设定、剧情走向、他人动机

正确示例：「一只十年魂兽从灌木丛中窜出，龇牙咧嘴地朝你低吼。你本能地想逃跑，但腿像灌了铅一样。」
错误示例：「一只魂兽扑过来了，你知道它是被天梦冰蚕的气息引来的。你应该用精神探测找到它的弱点。」

## 工作流程
1. 阅读剧本——角色安排（层级）、剧情细纲（小节）、讲述者备注
2. 如有需要，用 read_info 查阅世界观或角色状态
3. 按小节顺序推进，使用 manage_stage 调整舞台。
4. 写旁白或 pick 发言人，重复。
5. 一小节结束后，使用 speak 写旁白过度一下然后回到 3 ，继续

关键原则：
- 环境没变就不需要旁白，直接切换发言人，不要自己过度描述
- 同角色不宜连续发言
- 可以扮演 NPC 发言（第三人称嵌入旁白），但**绝对不要代替角色发言**
- 用户角色是人类玩家扮演的——给他的导演提示只写感官和情绪方向，不替他决定
- 期望结局应自然遵守，不僵硬执行

## 规则告知
- 角色上下场很重要，它等于信息隔离。出场的角色将会感知到在场角色的所有发言，因此当需要不同角色间的信息隔离时可以通过进退场来实现，细纲中应该已经安排好了一部分内容。
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
