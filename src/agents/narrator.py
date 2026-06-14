"""Narrator Agent — 讲述者，负责写旁白和控制发言权。"""
from langchain_core.tools import tool

from src.agents.base import BaseAgent


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

NARRATOR_SYSTEM_PROMPT = """你是导演兼讲述者。每一幕 Author 会给你一份剧本，你的任务是根据剧本指挥这一幕的演出——写旁白铺设场景，把发言权交给角色，在目标达成时喊 Cut。

## 你的工具
- speak(文本)：输出一段小说式旁白。1-3 句，精炼有力。
  可以描述场景、动作、氛围。当需要 NPC（路人、店员、小怪等非主要角色）说话时，直接在旁白中以第三人称写出 NPC 的言行。
  例如：speak("路边茶摊的老板娘探出头，冲着你喊道：'小兄弟，进来喝碗茶歇歇脚！'")
- pick_speaker(角色名, 导演提示)：把发言权交给一个角色。可选第二个参数「导演提示」。
- read_info(类别, 路径)：查阅信息。路径为空时列出可访问条目。
  - worldview（世界观）— 路径留空列出可访问条目，填路径名查看正文
  - character（角色）— 路径填角色名查看其当前状态。路径留空列出本幕出场角色
- end_episode(原因)：结束当前小剧场。目标达成或剧情推进完毕时调用。

### pick_speaker 的导演提示
第二个参数是可选的，给出后会被传递给角色作为演绎指引。
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

收到剧本时（每次新一幕开始）：
1. 阅读剧本——期望结局、剧情细纲、备注、角色戏份层级
2. 如有需要，用 read_info 查阅世界观或角色状态
3. 确认理解后开始——写开场旁白铺设场景，或直接 pick 第一个发言人

收到最新消息时（幕中每次唤醒）：
1. 快速了解刚刚发生了什么
2. 不用重复查阅已有信息——除非首次漏了什么
3. 决定下一步：旁白推进 / 直接 pick_speaker / end_episode
4. 如果写旁白，一般紧接着 pick_speaker
5. 角色发言完毕 → 控制权回到你 → 等待下一次最新消息

关键原则：
- 环境没变就不需要旁白，直接切换发言人
- 同角色不宜连续发言
- 可以扮演 NPC 发言（第三人称嵌入旁白），但绝对不要代替角色发言
- 用户角色是人类玩家扮演的——给他的导演提示只写感官和情绪方向，不替他决定
- 期望结局应自然遵守，不僵硬执行

## 角色戏份层级

Author 在角色安排中给每个角色标注了戏份层级——你必须严格遵守：

**主线**：可以自由 pick 发言，正常分配对话轮次。

**过场**：这个角色本集只有少量戏份。Author 在角色安排中给了**台词方向**（他想表达的意思/意图），你在 pick_speaker 的导演提示中把这个方向传递给角色——让角色用自己的风格表达，不要偏离这个意思。只分配一次 pick，之后不再 pick 他。

**点缀**：这个角色存在但无台词。只能通过旁白提及（"角落里，某人在阴影中静静看着"），**绝对不能 pick_speaker**。点缀角色的任何表现都用第三人称嵌入 speak 中。

如果在角色安排中没有看到层级标注，请根据对该角色的描述自行判断并遵循以上规则。"""


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


# ═══════════════════════════════════════════════════════════════
# Agent 类
# ═══════════════════════════════════════════════════════════════

class NarratorAgent(BaseAgent):
    """讲述者 Agent。"""

    @property
    def agent_name(self) -> str:
        return "Narrator"

    def __init__(self, story_id: str):
        super().__init__(story_id)
        self._episode_char_names: list[str] = []

    @property
    def system_prompt(self) -> str:
        return NARRATOR_SYSTEM_PROMPT

    @property
    def tools(self) -> list:
        return [
            speak,
            pick_speaker,
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
            if self._episode_char_names and name not in self._episode_char_names:
                return False, f"角色「{name}」不在当前小剧场中。小剧场角色：{', '.join(self._episode_char_names)}"
        return True, ""

    def set_episode_characters(self, names: list[str]):
        self._episode_char_names = names

    # ── prompt 构建 ──

    def build_first_message(
        self,
        *,
        episode_name: str = "",
        episode_summary: str = "",
        detailed_outline: str = "",
        desired_outcome: str = "",
        author_notes: str = "",
        worldview_text: str = "",
        characters_text: str = "",
        queue_messages: str = "",
    ) -> str:
        """构建第一轮消息——剧本 + 参考信息，通过队列发给 Narrator。"""
        parts = []

        if desired_outcome:
            parts.append(f"### 期望结局\n{desired_outcome}")
        if detailed_outline:
            parts.append(f"### 剧情细纲\n{detailed_outline}")
        if author_notes:
            parts.append(f"### 导演备注\n{author_notes}")

        has_refs = characters_text or worldview_text
        if has_refs:
            parts.append("---\n以下参考信息可用 read_info 查阅：")
            if characters_text:
                parts.append(f"### 角色\n{characters_text}")
            if worldview_text:
                parts.append(f"### 世界观\n{worldview_text}")

        parts.append("\n请先了解剧本。环境没变就不需要旁白，直接选发言人即可。")
        return "\n\n".join(parts)

    def build_continue_message(self, queue_messages: str,
                                new_episode: bool = False) -> str:
        parts = []
        if new_episode:
            # 系统消息就是剧本，去掉 [系统消息] 外壳，直接展示
            script = queue_messages.replace("[系统消息]\n", "", 1)
            parts.append(f"## Author 的最新剧本\n{script}")
        else:
            parts.append(f"## 最新消息\n{queue_messages}")
        parts.append("\n请决定下一步（环境没变可直接 pick_speaker）。")
        return "\n\n".join(parts)
