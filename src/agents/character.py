"""Character Agent — 角色，根据新消息做出反应。"""
from pathlib import Path
from langchain_core.tools import tool

from src.agents.base import BaseAgent
from src.config import character_initial_state_path, character_state_path, character_heartfelt_path


# ═══════════════════════════════════════════════════════════════
# 系统提示词
# ═══════════════════════════════════════════════════════════════

CHARACTER_SYSTEM_PROMPT = """你是一个角色扮演 Agent。你不是在描述一个角色——你**就是这个角色**。用第一人称思考、感受、说话。

## 你的工具
- speak(文本)：输出你的发言/动作/神态/内心。
- update_state(章节, 内容)：更新你对自己的状态的记录。
- recall(关键词)：搜索记忆库。
- write_memory(总结, 关键词)：小剧场结束时归档记忆。总结关键事件、重要人物、学到的教训。关键词用逗号分隔。
- done()：结束本轮发言。

## 重要：推理与发言的边界

你的思考过程（thinking）是私密的——外界（Narrator、其他角色、读者）完全看不到它。**只有 speak() 里的内容才会被传达出去。** 如果你在 thinking 里写了一句话但没有放进 speak()，等于你没说。

## speak 的写作格式 — 三层结构
你的输出由三种元素组成，每种独立成行，用换行分隔：

1. （动作神态）—— 括号包裹。只写身体能感知到的：感官、动作、表情。
   可以连续多组，每组换行。
   例：（握紧拳头）
   例：（后背撞上树干——闷响）
   例：（大口喘气，胸口剧烈起伏）

2. 「内心独白」—— 书名号包裹。情绪反应、判断、对自己的命令。绝不超过一句。
   例：「不能停」
   例：「他在哪里……」
   例：「好痛——但还能坚持」

3. 说出口的对话 —— 无任何括号，正常说话。

### 完整示例
（狼的獠牙擦过衣袖）
（皮肤上三道血痕——火辣辣的疼）
「好痛……但是不能停下」
（眼睛捕捉到右后方——又一只！）
（翻身向左避开）
你是谁？！

### 规则
- 不是每轮都要用齐三种——有什么就写什么
- 每种独立成行，不混排在一行里
- 每对（）内只描述一件事，不超过20字
- 「」内只写内心念头，不写旁白式叙述
- **不要用第三人称写自己**——写"（握紧拳头）"，不写"祥子握紧拳头"

## 工作流程
1. 收到最新消息。如果有「入场提示」——这是 Narrator 私密发给你的，告诉你此刻看到了什么、感受到了什么。你是刚被叫上场的，用这些信息来定位自己的状态。
2. 收到「导演提示」——Narrator 给你的演绎方向。
3. 如有需要，先调用 update_state 更新对自己的记录。
4. **必须调用 speak()**——你的所有外在表现（动作、神态、对话、内心独白）全部写进 speak。thinking 只有你自己能看到，不调 speak 等于沉默。
5. 调用 done() 结束本轮。

**speak() 和 done() 都要调——只调 done 不出声，等于你没出场。**

---

【你扮演的角色信息】
{character_state}
"""

CHARACTER_USER_MESSAGE = """{new_messages_block}{narrator_context_block}"""

CHARACTER_EPISODE_END_NOTE = """小剧场「{episode_name}」已经结束。

请归档本次小剧场的记忆：
1. 如有需要，用 update_state 更新你的状态
2. 调用 write_memory(总结, 关键词列表) 写入记忆——总结本幕经历的关键事件、遇到的人、学到的东西。关键词用逗号分隔，方便以后搜索

记忆是用来以后回顾的——写清楚发生了什么，以后怎么找到它。"""


# ═══════════════════════════════════════════════════════════════
# 模块级工具
# ═══════════════════════════════════════════════════════════════

@tool
def speak(text: str) -> str:
    """发言——本轮最后一个工具。参数是全部发言内容（动作+内心+对话），不在 thinking 里写任何角色文字。"""
    return "OK"


@tool
def update_state(section: str, content: str) -> str:
    """更新自己的状态。section: 要更新的章节名（如 心理状态、对他人的看法、公开信息 等）。
    content: 新内容。"""
    return "OK"


@tool
def done() -> str:
    """本轮结束——必须在 speak 之后调用。不调用则本轮不退出。"""
    return "OK"


def _make_spoke_reset(agent):
    """创建一个 before_llm 钩子，每轮 LLM 调用前重置 spoke 标记。"""
    async def reset(agent_name: str, episode_id: int, step: int):
        agent._spoke_this_round = False
    return reset


# ═══════════════════════════════════════════════════════════════
# Agent 类
# ═══════════════════════════════════════════════════════════════

class CharacterAgent(BaseAgent):
    """角色扮演 Agent。"""

    @property
    def agent_name(self) -> str:
        return self.character_name

    def __init__(self, story_id: str, character_name: str, universe=None):
        super().__init__(story_id, universe=universe)
        self.character_name = character_name
        self._in_episode_end = False
        self._state_text: str = ""          # state.md 全文
        self._pending_updates: list[dict] = []  # [(section, content)]
        self._state_meta: dict = {"last_read_message_id": None}
        self._state = self._state_meta      # engine 兼容别名
        self._spoke_this_round: bool = False
        self.hooks["before_llm"].append(_make_spoke_reset(self))

    def load_state_from_universe(self):
        """从 Universe 恢复 Character 状态。"""
        super().load_state_from_universe()
        if self.universe is None:
            return
        # 从 Universe 恢复 state text
        saved = self.universe.character_states.get(self.character_name)
        if saved:
            self._state_text = saved

    # ── state 加载 ──

    def load_state(self):
        """加载当前状态。优先 save/state.md，fallback 到 story/initial_state.md。"""
        save_path = character_state_path(self.story_id, self.character_name)
        init_path = character_initial_state_path(self.story_id, self.character_name)

        if save_path.exists():
            self._state_text = save_path.read_text(encoding="utf-8").strip()
        elif init_path.exists():
            self._state_text = init_path.read_text(encoding="utf-8").strip()
        else:
            self._state_text = f"# 人物状态\n\n姓名：{self.character_name}\n（无状态信息）"

    def save_state(self):
        """持久化状态到 save/state.md。"""
        save_path = character_state_path(self.story_id, self.character_name)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(self._state_text, encoding="utf-8")

    # ── state 更新（引擎调用） ──

    def record_update(self, section: str, content: str):
        self._pending_updates.append({"section": section, "content": content})

    def apply_pending_updates(self):
        """将 _pending_updates 合并到 _state_text 并持久化。"""
        if not self._pending_updates:
            return

        import re
        text = self._state_text

        for upd in self._pending_updates:
            section = upd["section"]
            content = upd["content"]

            # 查找并替换对应 ## section
            pattern = rf"(^## {re.escape(section)}\s*\n)(?:<!--.*?-->\n)?(.*?)(?=^## |\Z)"
            replacement = rf"\1{content}\n\n"

            if re.search(pattern, text, re.MULTILINE | re.DOTALL):
                text = re.sub(pattern, replacement, text,
                              flags=re.MULTILINE | re.DOTALL)
            else:
                # section 不存在则追加
                text += f"\n## {section}\n{content}\n"

        self._state_text = text.strip() + "\n"
        self._pending_updates = []
        self.save_state()

    def clear_pending_updates(self):
        self._pending_updates = []

    # ── 公开给引擎的方法 ──

    def get_profile_description(self) -> str:
        """返回全知版描述（从 profile.md frontmatter description）。给 Author 用。"""
        text = self.get_profile_text()
        from src.storage.frontmatter import parse_frontmatter
        fm, _ = parse_frontmatter(text)
        return fm.get("description", self.character_name)

    def get_public_description(self) -> str:
        """返回公开版描述（从 state 的 ## 公开信息 提取）。给 Narrator 用。"""
        import re
        m = re.search(r"^## 公开信息\s*\n<!--.*?-->\n(.*?)(?=^## |\Z)",
                      self._state_text or "", re.MULTILINE | re.DOTALL)
        if m:
            return m.group(1).strip()[:200]
        # fallback: 从初始 state 文件读
        init_path = character_initial_state_path(self.story_id, self.character_name)
        if init_path.exists():
            text = init_path.read_text(encoding="utf-8")
            m = re.search(r"^## 公开信息\s*\n<!--.*?-->\n(.*?)(?=^## |\Z)",
                          text, re.MULTILINE | re.DOTALL)
            if m:
                return m.group(1).strip()[:200]
        return self.character_name

    # ── profile 读取（引擎用） ──

    @property
    def profile_path(self) -> Path:
        from src.config import story_dir
        return story_dir(self.story_id) / "characters" / self.character_name / "profile.md"

    def get_profile_text(self) -> str:
        if self.profile_path.exists():
            return self.profile_path.read_text(encoding="utf-8").strip()
        return ""

    def get_state_text(self) -> str:
        return self._state_text

    def update_last_read(self, message_id: str):
        self._state_meta["last_read_message_id"] = message_id

    # ── BaseAgent 接口 ──

    @property
    def system_prompt(self) -> str:
        return CHARACTER_SYSTEM_PROMPT.format(character_state=self._state_text)

    # ── recall 自包含 ──

    def _make_recall(self):
        agent = self

        @tool(description="搜索你的记忆库。query: 关键词或角色名。")
        def recall(query: str) -> str:
            from src.config import character_save_dir
            mem_dir = character_save_dir(agent.story_id, agent.character_name) / "memories"
            if not mem_dir.exists():
                return "（尚无记忆）"

            results = []
            for f in sorted(mem_dir.glob("ep*.md")):
                text = f.read_text(encoding="utf-8")
                if query in text:
                    import re
                    m = re.search(r"## 自述总结\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
                    snippet = m.group(1).strip()[:200] if m else text[:200]
                    results.append(f"### {f.stem}\n{snippet}")

            if not results:
                return f"记忆中未找到与「{query}」相关的内容。"
            return "\n\n".join(results[:5])
        return recall

    # ── write_memory 自包含 ──

    def _make_write_memory(self):
        agent = self

        @tool(description="归档本幕记忆。summary: 本集关键经历的自述总结。keywords: 逗号分隔的检索关键词。")
        def write_memory(summary: str, keywords: str = "") -> str:
            from pathlib import Path as _Path
            from src.config import character_save_dir
            from src.storage.state import load_jsonl as _load_jsonl

            mem_dir = character_save_dir(agent.story_id, agent.character_name) / "memories"
            mem_dir.mkdir(parents=True, exist_ok=True)

            ep_info = getattr(agent, "_episode_end_info", {})
            ep_id = ep_info.get("episode_id", 0)
            ep_name = ep_info.get("episode_name", "?")
            hist_path = ep_info.get("hist_path")

            mem_file = mem_dir / f"ep{ep_id:03d}.md"
            lines = [f"# 第{ep_id}幕：{ep_name}\n",
                     f"## 自述总结\n{summary}\n"]

            if keywords:
                lines.append(f"关键词：{keywords}\n")

            if hist_path and _Path(hist_path).exists():
                transcript = []
                for e in _load_jsonl(_Path(hist_path)):
                    if e.get("speaker") == agent.character_name or e.get("type") == "narrate":
                        speaker = e.get("speaker", "Narrator")
                        transcript.append(f"[{speaker}]\n{e.get('content', '')}")
                if transcript:
                    lines.append("## 对话记录\n" + "\n\n".join(transcript))

            mem_file.write_text("\n".join(lines), encoding="utf-8")
            return f"[OK] 记忆已写入 ep{ep_id:03d}"

        return write_memory

    @property
    def tools(self) -> list:
        return [
            speak,
            update_state,
            self._make_recall(),
            done,
            self._make_write_memory(),
        ]

    @property
    def exit_tool(self) -> list[str]:
        if self._in_episode_end:
            return ["write_memory", "done"]
        return ["done"]

    def validate_tool(self, tool_name: str, args: dict) -> tuple[bool, str]:
        if tool_name == "speak":
            if not args.get("text", "").strip():
                return False, "speak 内容不能为空"
            self._spoke_this_round = True
        elif tool_name == "done":
            if not self._spoke_this_round and not self._in_episode_end:
                return False, "必须先调 speak() 再调 done()——不说话等于你没出场"
        elif tool_name == "update_state":
            section = args.get("section", "")
            content = args.get("content", "")
            if not section.strip():
                return False, "update_state 需要提供 section"
            if not content.strip():
                return False, "update_state 需要提供 content"
            self.record_update(section, content)
        elif tool_name == "write_memory":
            if not args.get("summary", "").strip():
                return False, "write_memory 需要 summary"
        return True, ""

    # ── prompt 构建 ──

    def build_user_message(self, new_messages: str, narrator_context: str = "") -> str:
        msgs_block = f"以下是最新的公开对话：\n\n{new_messages}\n" if new_messages else ""
        ctx_block = f"---\n导演提示：{narrator_context}\n" if narrator_context else ""
        return CHARACTER_USER_MESSAGE.format(
            new_messages_block=msgs_block,
            narrator_context_block=ctx_block)

    def build_episode_end_message(self, new_messages: str, episode_name: str,
                                   narrator_context: str = "") -> str:
        msgs_block = f"以下是最新的公开对话：\n\n{new_messages}\n" if new_messages else ""
        ctx_block = f"---\n导演提示：{narrator_context}\n" if narrator_context else ""
        note = CHARACTER_EPISODE_END_NOTE.format(episode_name=episode_name)
        return CHARACTER_USER_MESSAGE.format(
            new_messages_block=msgs_block,
            narrator_context_block=ctx_block) + "\n\n---\n\n" + note

    # ── 小剧场管理 ──

    def enter_episode_end_mode(self):
        self._in_episode_end = True

    def leave_episode_end_mode(self):
        self._in_episode_end = False

    def set_episode_entry(self, episode_name: str, entry_timing: str, pre_episode_context: str):
        """记录本小剧场的入场信息。"""
        self._state_meta["current_episode"] = episode_name

    def set_episode_end_info(self, episode_id: int, episode_name: str, hist_path):
        """引擎在 Phase E 前调用，供 write_memory 工具写入记忆文件。"""
        self._episode_end_info = {
            "episode_id": episode_id,
            "episode_name": episode_name,
            "hist_path": hist_path,
        }

    def mark_episode_ended(self, episode_name: str):
        """标记小剧场结束。"""
        self._state_meta["current_episode"] = ""
        self._episode_end_info = {}
