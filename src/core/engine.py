"""小剧场大循环引擎 — 装配 Session + 调度 Phase。

状态机：PLANNING → RUNNING → SUMMARIZING → DONE → PLANNING
"""
from src.core.session import Session
from src.core.state_machine import EpisodeState
from src.core.emitter import EventEmitter
from src.core.phases import run_planning, run_inner_loop, run_summary
from src.core.phases._helpers import now, elapsed
# Universe 是唯一 checkpoint 数据源，不再需要分散的 checkpoint 保存


async def run_session(story_id: str, *, emitter: EventEmitter,
                      max_episodes: int = 0, debug: bool = False,
                      user_turn_callback=None):
    """主循环 — 加载数据 → 按状态机调度 → 结束。"""
    t0 = now()
    sess = Session.load(story_id)

    # ── 注入外部依赖 ──
    sess.emitter = emitter
    sess.debug = debug
    sess.user_turn_callback = user_turn_callback
    sess.max_episodes = max_episodes

    log = sess.log

    # ── run() 参数回调 ──
    async def _token_cb(agent: str, text: str):
        await emitter.on_llm_token(agent, text)

    sess._token_cb = _token_cb

    # ── 钩子注册 ──
    # agent 名 → 实例的快速查找
    _agent_lookup = {a.agent_name: a for a in [sess.author, sess.narrator, *sess.characters.values()]}

    async def _checkpoint_cb(agent_name: str, episode_id: int, step: int):
        """LLM 调用前保存：Universe 已包含所有状态，直接序列化。"""
        # 引擎位置快照（Universe 外的瞬态信息）
        sess.universe.meta["last_active_role"] = agent_name
        sess.universe.meta["last_episode_id"] = episode_id
        sess.universe.meta["last_step"] = step
        # 保存 Universe（= 完美 checkpoint）
        sess.save()

    def _context_changed_cb(agent_name: str, version: int, reason: str):
        sess.round_log.on_context_changed(agent_name, version, reason)

    for agent in [sess.author, sess.narrator, *sess.characters.values()]:
        agent.hooks["before_llm"].append(_checkpoint_cb)
        agent.hooks["context_changed"].append(_context_changed_cb)

    # ── 步骤回调：同时写 trace + 保存 checkpoint（确保 exit 步骤不丢） ──
    async def _step_and_checkpoint_cb(agent: str, step: int, msgs: list,
                                       thinking: str, calls: list[dict]):
        """trace + post-step checkpoint：工具执行后保存，补 before_llm 的盲区。"""
        sess.round_log.write_step(agent, step, msgs, thinking, calls)
        # Universe 在 run() 内已自动同步 conversations，这里只需落盘
        sess.save()

    sess._step_cb = _step_and_checkpoint_cb

    await emitter.on_session_start(story_id)
    log.info("【初始化】完成, 耗时 %s", elapsed(t0))
    log.info("【就绪】进入主循环 (状态=%s 章节=%d 幕数=%d)",
             sess.state.value, sess.chapter_idx + 1, sess.episode_count + 1)

    # ═══════════════════════════════════════════════════════════════
    # 主循环
    # ═══════════════════════════════════════════════════════════════
    while True:
        if sess.max_episodes > 0 and sess.episode_count >= sess.max_episodes:
            log.info("【结束】达到最大幕数 %d, 退出", sess.max_episodes)
            break

        if sess.state == EpisodeState.DONE:
            break

        log.info("─" * 60)
        log.info("【循环】状态=%s | 第%d章 | 第%d幕",
                 sess.state.value, sess.chapter_idx + 1, sess.episode_count + 1)

        try:
            if sess.state == EpisodeState.PLANNING:
                log.info("【引擎】→ 进入 planning")
                await run_planning(sess)
                log.info("【引擎】← planning 完成, 状态=%s", sess.state.value)
            elif sess.state == EpisodeState.RUNNING:
                log.info("【引擎】→ 进入 inner_loop")
                await run_inner_loop(sess)
                log.info("【引擎】← inner_loop 完成, 状态=%s", sess.state.value)
            elif sess.state == EpisodeState.SUMMARIZING:
                log.info("【引擎】→ 进入 summary")
                await run_summary(sess)
                log.info("【引擎】← summary 完成, 状态=%s", sess.state.value)
        except Exception as e:
            log.exception("【引擎·致命】phase 执行异常: %s", e)
            await emitter.on_session_end(story_id, sess.episode_count)
            raise

        # 首次完成任意 phase 后清除重启标记
        if sess.is_restart:
            sess.is_restart = False
            log.info("【恢复】断点恢复完成, 后续 phase 正常执行")

        sess.save()

    log.info("【结束】会话完成, 共 %d 幕, 总耗时 %s", sess.episode_count, elapsed(t0))
    await emitter.on_session_end(story_id, sess.episode_count)
