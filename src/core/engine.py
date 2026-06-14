"""小剧场大循环引擎 — 装配 Session + 调度 Phase。

状态机：PLANNING → RUNNING → SUMMARIZING → DONE → PLANNING
"""
from src.core.session import Session
from src.core.state_machine import EpisodeState
from src.core.emitter import EventEmitter
from src.core.phases import run_planning, run_inner_loop, run_summary
from src.core.phases._helpers import now, elapsed
from src.core.checkpoint import save_engine_checkpoint


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

    async def _step_cb(agent: str, step: int, msgs: list, thinking: str, calls: list[dict]):
        sess.round_log.write_step(agent, step, msgs, thinking, calls)

    sess._token_cb = _token_cb
    sess._step_cb = _step_cb

    # ── 钩子注册 ──
    async def _checkpoint_cb(agent_name: str, episode_id: int, step: int):
        save_engine_checkpoint(story_id,
                               state=sess.state.value,
                               chapter_idx=sess.chapter_idx,
                               episode_count=sess.episode_count,
                               active_role=agent_name,
                               episode_id=episode_id,
                               step=step)

    def _context_changed_cb(agent_name: str, version: int, reason: str):
        sess.round_log.on_context_changed(agent_name, version, reason)

    for agent in [sess.author, sess.narrator, *sess.characters.values()]:
        agent.hooks["before_llm"].append(_checkpoint_cb)
        agent.hooks["context_changed"].append(_context_changed_cb)

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

        if sess.state == EpisodeState.PLANNING:
            await run_planning(sess)
        elif sess.state == EpisodeState.RUNNING:
            await run_inner_loop(sess)
        elif sess.state == EpisodeState.SUMMARIZING:
            await run_summary(sess)

        sess.save()

    log.info("【结束】会话完成, 共 %d 幕, 总耗时 %s", sess.episode_count, elapsed(t0))
    await emitter.on_session_end(story_id, sess.episode_count)
