"""FastAPI 后端 — SSE 流式推送 + 用户输入端点。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.core.engine import run_session
from src.core.emitter import EventEmitter, NarrateEvent, SpeakEvent, EpisodeChangeEvent, InternalEvent


# ═══════════════════════════════════════════════════════════════
# SSE Emitter
# ═══════════════════════════════════════════════════════════════

class SSEEmitter(EventEmitter):
    def __init__(self):
        self.queue: asyncio.Queue[dict] = asyncio.Queue()

    async def _push(self, msg_type: str, data: dict):
        await self.queue.put({"type": msg_type, "data": data})

    async def on_narrate(self, event: NarrateEvent):
        await self._push("narrate", {"speaker": event.speaker, "content": event.content})

    async def on_speak(self, event: SpeakEvent):
        await self._push("speak", {"speaker": event.speaker, "content": event.content})

    async def on_episode_change(self, event: EpisodeChangeEvent):
        await self._push("episode_change", {
            "episode_name": event.episode_name,
            "episode_id": event.episode_id,
            "state": event.state,
        })

    async def on_llm_token(self, agent: str, text: str):
        await self._push("llm_token", {"agent": agent, "text": text})

    async def on_system_prompt(self, agent: str, text: str):
        await self._push("system_prompt", {"agent": agent, "text": text[:3000]})

    async def on_user_message(self, agent: str, text: str):
        await self._push("user_message", {"agent": agent, "text": text[:3000]})

    async def on_internal(self, event: InternalEvent):
        await self._push("internal", {
            "agent": event.agent,
            "tool": event.tool,
            "args": event.args,
            "result": event.result,
            "is_invalid": event.is_invalid,
        })

    async def on_session_start(self, story_id: str):
        await self._push("session_start", {"story_id": story_id})

    async def on_session_end(self, story_id: str, total_episodes: int):
        await self._push("session_end", {"story_id": story_id, "total_episodes": total_episodes})


# ═══════════════════════════════════════════════════════════════
# 用户输入桥接
# ═══════════════════════════════════════════════════════════════

class UserTurnBridge:
    """引擎挂起 → SSE 推事件到前端 → 等待 POST 回传 → 引擎恢复。"""
    def __init__(self, emitter: SSEEmitter):
        self._emitter = emitter
        self._event: asyncio.Event | None = None
        self._result: str = ""

    async def __call__(self, speaker: str, state: str, context: str, history: str) -> str:
        """user_turn_callback 的实现。"""
        self._event = asyncio.Event()
        self._result = ""
        # 推送 user_turn 事件到前端
        await self._emitter._push("user_turn", {
            "speaker": speaker,
            "state": state,
            "context": context,
            "history": history,
        })
        # 等待前端 POST 回来
        await self._event.wait()
        return self._result

    def submit(self, text: str):
        """前端调用的提交方法。"""
        self._result = text
        if self._event:
            self._event.set()


# ═══════════════════════════════════════════════════════════════
# SSE 端点
# ═══════════════════════════════════════════════════════════════

async def stream_endpoint(story_id: str, debug: bool = False) -> StreamingResponse:
    emitter = SSEEmitter()
    bridge = UserTurnBridge(emitter)
    _active_bridges[story_id] = bridge

    async def event_generator():
        task = asyncio.create_task(
            run_session(story_id, emitter=emitter, debug=debug,
                        user_turn_callback=bridge)
        )
        try:
            while True:
                event = await emitter.queue.get()
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                if event["type"] == "session_end":
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            import traceback, logging
            logging.getLogger("ainovel.server").error(
                "【SSE】event_generator 异常: %s\n%s", e, traceback.format_exc())
            yield f"event: session_error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    import traceback, logging
                    logging.getLogger("ainovel.server").error(
                        "【SSE】run_session task 异常: %s\n%s", e, traceback.format_exc())

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════
# App
# ═══════════════════════════════════════════════════════════════

# 存储活跃的 bridge（按 story_id）
_active_bridges: dict[str, UserTurnBridge] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="AINovelInDialogue")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/stream/{story_id}")
    async def stream(story_id: str, debug: bool = Query(default=False)):
        return await stream_endpoint(story_id, debug)

    @app.post("/api/speak/{story_id}")
    async def user_speak(story_id: str, req: Request):
        """用户角色发言端点。"""
        body = await req.json()
        text = body.get("text", "")
        bridge = _active_bridges.get(story_id)
        if bridge:
            bridge.submit(text)
            return {"status": "ok"}
        return {"status": "no_active_session"}, 404

    @app.get("/api/history/{story_id}")
    async def get_history(story_id: str):
        from src.config import history_path
        from src.storage.state import load_jsonl
        hp = history_path(story_id)
        if not hp.exists():
            return {"messages": []}
        entries = load_jsonl(hp)
        msgs = []
        for e in entries:
            msgs.append({
                "type": e.get("type", ""),
                "speaker": e.get("speaker", e.get("from", "")),
                "content": e.get("content", ""),
                "timestamp": e.get("timestamp", ""),
            })
        return {"messages": msgs}

    @app.get("/api/stories")
    async def list_stories():
        import json
        from src.config import STORIES_ROOT
        stories = []
        for d in sorted(STORIES_ROOT.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            sj = d / "story.json"
            if sj.exists():
                info = json.loads(sj.read_text(encoding="utf-8"))
            else:
                info = {}
            stories.append({
                "story_id": d.name,
                "name": info.get("name", d.name),
                "description": info.get("description", ""),
                "user_character": info.get("user_character", ""),
            })
        return {"stories": stories}

    @app.get("/api/state/{story_id}/{char_name}")
    async def get_char_state(story_id: str, char_name: str):
        from src.config import char_state_path, char_initial_state_path
        path = char_state_path(story_id, char_name)
        if path.exists():
            return {"state": path.read_text(encoding="utf-8")}
        init_path = char_initial_state_path(story_id, char_name)
        if init_path.exists():
            return {"state": init_path.read_text(encoding="utf-8")}
        return {"state": ""}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:create_app", host="0.0.0.0", port=8000, reload=True, factory=True)
