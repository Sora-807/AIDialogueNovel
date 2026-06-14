"""LLM 调用 — 纯函数，只管发请求收响应。"""
import json
import time
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

from src.config import LLMConfig, save_dir

TokenCallback = Callable[[str, str], Awaitable[None]]
_provider_log = logging.getLogger("ainovel.provider")

# 抑制 httpx / openai 的 DEBUG 噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


def _build_llm(cfg: LLMConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url,
        temperature=0.8, max_tokens=2048, timeout=120,
    )


def _msg_to_dict(m: BaseMessage) -> dict:
    """LangChain message → 可 JSON 序列化的 dict，保留 tool_calls / tool_call_id。"""
    d = {"role": getattr(m, "type", "?")}
    content = getattr(m, "content", "")
    if isinstance(content, (str, list)):
        d["content"] = content
    else:
        d["content"] = str(content)

    if hasattr(m, "tool_calls") and m.tool_calls:
        d["tool_calls"] = []
        for tc in m.tool_calls:
            d["tool_calls"].append({
                "name": tc.get("name", ""),
                "args": tc.get("args", {}),
                "id": tc.get("id", ""),
            })

    if hasattr(m, "tool_call_id") and m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id

    return d


def _dump_raw(story_id: str, agent_name: str, mode: str, elapsed: float,
              input_msgs: list[BaseMessage], output_text: str,
              output_tool_calls: list | None = None):
    """每次 LLM 调用落一条 JSONL 到 saves/{story_id}/llm_raw.jsonl。
    全量保存，不截断——input 是真正的 message 列表（含 tool_calls/tool_call_id）。"""
    if not story_id or not agent_name:
        return
    try:
        inp = [_msg_to_dict(m) for m in input_msgs]
        out = {"content": output_text or ""}
        if output_tool_calls:
            out["tool_calls"] = [
                {"name": tc.get("name", ""), "args": tc.get("args", {}),
                 "id": tc.get("id", "")}
                for tc in output_tool_calls
            ]

        line = json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": agent_name,
            "mode": mode,
            "elapsed": round(elapsed, 2),
            "input_msgs": len(inp),
            "input": inp,
            "output": out,
        }, ensure_ascii=False)
        path = save_dir(story_id) / "llm_raw.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        _provider_log.warning("【LLM】_dump_raw 写入失败: %s", e)


async def stream_llm(
    llm: ChatOpenAI,
    messages: list[BaseMessage],
    on_token: TokenCallback | None = None,
    agent_name: str = "",
    story_id: str = "",
) -> tuple[str, Any]:
    """流式调用 LLM，返回 (full_text, last_chunk)。"""
    t0 = time.time()
    _provider_log.debug("【LLM】%s: astream 开始, %d msgs", agent_name, len(messages))
    text = ""
    chunk = None
    token_count = 0
    async for c in llm.astream(messages):
        if c.content:
            txt = c.content if isinstance(c.content, str) else str(c.content)
            text += txt
            token_count += len(txt)
            if on_token: await on_token(agent_name, txt)
        chunk = c
    elapsed = time.time() - t0
    _provider_log.debug("【LLM】%s: astream 完成 %.1fs, %d tokens, %d 字",
                        agent_name, elapsed, token_count, len(text))
    out_tc = getattr(chunk, "tool_calls", None) if chunk else None
    _dump_raw(story_id, agent_name, "astream", elapsed, messages, text, out_tc)
    return text, chunk


async def invoke_llm(
    llm: ChatOpenAI,
    messages: list[BaseMessage],
    on_token: TokenCallback | None = None,
    agent_name: str = "",
    story_id: str = "",
) -> tuple[str, Any]:
    """非流式调用（回退用），返回 (text, response)。"""
    t0 = time.time()
    _provider_log.debug("【LLM】%s: ainvoke 开始, %d msgs", agent_name, len(messages))
    resp = await llm.ainvoke(messages)
    elapsed = time.time() - t0
    content_len = len(resp.content or "")
    _provider_log.debug("【LLM】%s: ainvoke 完成 %.1fs, %d 字",
                        agent_name, elapsed, content_len)
    if on_token and resp.content:
        await on_token(agent_name, resp.content)
    out_tc = getattr(resp, "tool_calls", None) if resp else None
    _dump_raw(story_id, agent_name, "ainvoke", elapsed, messages,
              resp.content or "", out_tc)
    return resp.content or "", resp
