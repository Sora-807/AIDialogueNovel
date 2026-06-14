"""Agent 基类 — 拥有 ReAct 循环 + 生命周期钩子。

钩子设计：self.hooks 是一个 dict[str, list[callable]]，引擎往里塞回调，
Agent 在事件发生时遍历执行。不暴露 setter，直接操作列表。
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable

from langchain_core.tools import tool, BaseTool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from src.config import load_llm_config
from src.core.logger import get_logger
from src.llm.provider import _build_llm, stream_llm, invoke_llm

TokenCallback = Callable[[str, str], Awaitable[None]]
StepCallback = Callable[[str, int, list, str, list[dict]], Awaitable[None]]
ReaderFn = Callable[[str], str]


class BaseAgent(ABC):
    MAX_LOOP = 20

    def __init__(self, story_id: str):
        self.story_id = story_id
        self._llm_config = load_llm_config()
        self._override_exit_tool: str | list[str] | None = None
        self._astream_ok = self._llm_config.use_stream
        self._readers: dict[str, ReaderFn] = {}
        self._messages: list = []

        # ── 生命周期 ──
        self._context_version: int = 0
        self._system_prompt_extra: str = ""
        self._episode_ctx: dict = {}
        self._log_tag: str = ""

        # ── 钩子：引擎往里塞回调，Agent 在事件时遍历执行 ──
        self.hooks: dict[str, list[Callable]] = {
            "before_llm": [],         # async fn(agent_name, episode_id, step)
            "context_changed": [],    # fn(agent_name, context_version, reason)
            "episode_start": [],      # fn(agent_name, episode_id)
            "episode_end": [],        # fn(agent_name, episode_id, gap)
        }

    # ═══════════════════════════════════════════════════════════════
    # 抽象接口
    # ═══════════════════════════════════════════════════════════════

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @property
    @abstractmethod
    def tools(self) -> list[BaseTool]: ...

    @property
    @abstractmethod
    def exit_tool(self) -> str | list[str]:
        """默认 exit_tool，可通过 set_exit_tool 覆写。"""

    @property
    def agent_name(self) -> str:
        return type(self).__name__

    # ═══════════════════════════════════════════════════════════════
    # 生命周期钩子（引擎调用）
    # ═══════════════════════════════════════════════════════════════

    def inject_prompt(self, text: str):
        """注入额外的系统提示词。在 on_episode_start 之后、run() 之前调用。"""
        self._system_prompt_extra = text

    def on_episode_start(self, ctx: dict):
        """Episode 开始。ctx 包含 phase, episode_id 等。"""
        self._episode_ctx = ctx
        self._system_prompt_extra = ""
        phase = ctx.get("phase", "")
        self._log_tag = f"{self.agent_name}·{phase}" if phase else self.agent_name
        ep_id = ctx.get("episode_id", 0)
        for fn in self.hooks["episode_start"]:
            fn(self.agent_name, ep_id)

    def on_episode_end(self, gap: str):
        """Episode 结束。gap: 'small_gap' | 'big_gap'。"""
        self.manage_context(gap)
        ep_id = self._episode_ctx.get("episode_id", 0)
        self._episode_ctx = {}
        for fn in self.hooks["episode_end"]:
            fn(self.agent_name, ep_id, gap)

    def _bump_context(self, reason: str):
        """上下文版本 +1，触发 context_changed hook。"""
        self._context_version += 1
        for fn in self.hooks["context_changed"]:
            fn(self.agent_name, self._context_version, reason)

    def manage_context(self, gap: str):
        """根据 gap 决定清理 ReAct 历史。返回清理后的消息数。"""
        before = len(self._messages)

        if gap == "small_gap":
            pass
        elif gap == "big_gap":
            self._messages = []
            self._bump_context(reason=gap)

        after = len(self._messages)

        tag = self._log_tag or self.agent_name
        log = get_logger(self.story_id)
        log.info("【%s】上下文管理 | gap=%s | version %d | messages %d→%d",
                 tag, gap, self._context_version, before, after)

    # ═══════════════════════════════════════════════════════════════
    # 原有方法
    # ═══════════════════════════════════════════════════════════════

    def set_exit_tool(self, name: str | list[str]):
        self._override_exit_tool = name

    @property
    def _active_exit_tool(self) -> str | list[str]:
        if self._override_exit_tool is not None:
            return self._override_exit_tool
        return self.exit_tool

    def reset_messages(self):
        """清空对话历史。"""
        self._messages = []

    def validate_tool(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """子类覆写以校验工具参数。返回 (ok, msg)。"""
        return True, ""

    # ── reader 注册 ──

    def register_reader(self, category: str, fn: ReaderFn):
        self._readers[category] = fn

    def _make_read_info(self):
        agent = self

        @tool
        def read_info(category: str, path: str = "") -> str:
            """查阅信息。category: worldview/character/outline/history/foreshadowing。
            path 为空时列出该类别下的所有条目，非空时查阅具体内容。"""
            reader = agent._readers.get(category)
            if not reader:
                available = "、".join(agent._readers.keys()) or "（无）"
                return f"无法查阅「{category}」。可用类别：{available}"
            return reader(path)

        return read_info

    # ── ReAct 循环 ──

    async def run(
        self,
        user_message: str,
        *,
        on_token: TokenCallback | None = None,
        on_step: StepCallback | None = None,
    ) -> list[dict]:
        self._on_step = on_step
        et = self._active_exit_tool
        if isinstance(et, str): exit_tools = {et}
        elif isinstance(et, set): exit_tools = et
        else: exit_tools = set(et)
        tool_map = {t.name: t for t in self.tools}
        if self._readers:
            ri = self._make_read_info()
            tool_map[ri.name] = ri
        tools_for_llm = list(tool_map.values())
        llm = _build_llm(self._llm_config).bind_tools(tools_for_llm)

        log = get_logger(self.story_id)
        if not self._messages:
            prompt = self.system_prompt
            if self._system_prompt_extra:
                prompt += "\n\n---\n\n## 特别指示\n\n" + self._system_prompt_extra
            self._messages = [SystemMessage(prompt)]
        self._messages.append(HumanMessage(user_message))
        all_calls: list[dict] = []

        tag = self._log_tag or self.agent_name
        log.debug("【%s】ReAct 开始 | history=%d msgs | tools=%d",
                  tag, len(self._messages), len(tools_for_llm))

        for step in range(1, self.MAX_LOOP + 1):
            # 0. before_llm 钩子 — 每次 LLM 调用前
            ep_id = self._episode_ctx.get("episode_id", 0)
            for fn in self.hooks["before_llm"]:
                await fn(self.agent_name, ep_id, step)

            # 1. 调用 LLM
            log.info("【%s】step %d → LLM 调用中…", tag, step)
            if self._astream_ok:
                thinking, chunk = await stream_llm(llm, self._messages, on_token,
                                                    self.agent_name, self.story_id)
                if not self._has_tool_calls(chunk):
                    log.warning("【%s】astream 无 tool_calls, 切换到 ainvoke", tag)
                    self._astream_ok = False
                    thinking, chunk = await invoke_llm(llm, self._messages, on_token,
                                                        self.agent_name, self.story_id)
            else:
                thinking, chunk = await invoke_llm(llm, self._messages, on_token,
                                                    self.agent_name, self.story_id)

            log.info("【%s】step %d ← LLM 返回 | thinking=%d 字",
                     tag, step, len(thinking or ""))

            if not self._has_tool_calls(chunk):
                t_short = (thinking or "").replace("\n", " ")[:200]
                log.error("【%s】step %d: 无 tool_calls, thinking=%s",
                          tag, step, t_short)
                return [{"tool": "__error__", "args": {},
                         "_error": "LLM returned no tool_calls"}]

            # 2. 执行工具
            round_calls, tool_msgs = [], []
            for tc in chunk.tool_calls:
                name = tc["name"]; args = tc.get("args", {})
                record = {"tool": name, "args": args}

                if name in tool_map:
                    log.debug("【%s】step %d, 执行 %s(%s)",
                              tag, step, name,
                              str(args)[:80])
                    valid, result = await self._execute_tool(tool_map[name], args)
                    record["_result"] = result
                    if not valid: record["_invalid"] = True
                    short = str(result).replace("\n", "\\n")[:120]
                    log.debug("【%s】step %d, %s → %s",
                              tag, step, name, short)
                else:
                    record["_result"] = f"未知工具 {name}"
                    record["_invalid"] = True

                all_calls.append(record); round_calls.append(record)
                tool_msgs.append(ToolMessage(content=record["_result"], tool_call_id=tc["id"]))

            # 3. 追加对话历史（先写，确保回调能记录完整的本轮 AI/Tool 消息）
            self._messages.append(AIMessage(content=thinking, tool_calls=chunk.tool_calls))
            self._messages.extend(tool_msgs)

            # 4. trace 回调
            if on_step:
                await on_step(self.agent_name, step, list(self._messages), thinking, list(round_calls))

            # 5. 退出检查（跳过无效调用——如 done 没带 speak）
            if any(c["tool"] in exit_tools and not c.get("_invalid") for c in round_calls):
                exit_name = next(c["tool"] for c in round_calls
                                 if c["tool"] in exit_tools and not c.get("_invalid"))
                log.debug("【%s】退出 via %s | 总计 %d 次调用",
                          tag, exit_name, len(all_calls))
                return all_calls

        log.warning("【%s】达到 MAX_LOOP (%d 步)", tag, self.MAX_LOOP)
        return all_calls

    # ── helper ──

    @staticmethod
    def _has_tool_calls(chunk) -> bool:
        return hasattr(chunk, "tool_calls") and chunk.tool_calls

    async def _execute_tool(self, tool: BaseTool, args: dict) -> tuple[bool, str]:
        valid, msg = self.validate_tool(tool.name, args)
        if not valid:
            return False, msg
        try:
            result = await tool.ainvoke(args)
            return True, str(result)
        except Exception as e:
            return False, f"工具执行出错：{e}"
