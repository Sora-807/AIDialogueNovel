"""Phase D+E+F — Author 总结 + 角色心里话 + 推进。"""
from src.core.session import Session
from src.core.state_machine import EpisodeState, GapType
from src.core.context import format_queue_messages
from src.core.phases._helpers import (
    now, elapsed, log_tools, emit_internal, apply_summary_json,
    _parse_calls_from_messages,
)
from src.storage.state import load_jsonl


async def run_summary(sess: Session):
    """Author 总结 → 角色写入记忆 → 推进到下一幕/章。"""
    if not sess.universe.episodes:
        sess.advance_to(EpisodeState.PLANNING)
        return

    episode = sess.universe.episodes[-1]
    log = sess.log

    # 重启恢复：trace 补 begin_episode
    if sess.is_restart:
        sess.round_log.begin_episode(episode["episode_id"],
                                      episode.get("episode_name", ""))

    # ═══════════ Phase D: Author 总结 ═══════════
    sess.author.on_episode_start({"phase": "summary", "episode_id": episode["episode_id"]})
    sess.author._phase = "summary"
    sess.author.set_exit_tool("done")

    # ── 重启恢复：Author 已有完整状态 → 继续或取结果 ──
    if sess.is_restart and sess.author.has_checkpoint():
        log.info("【Author·总结·恢复】从断点继续 | phase=%s | %d 条消息 | %d 个提交",
                 sess.author._phase, len(sess.author._messages),
                 len(sess.author._submitted_sections))

        if sess.author._exit_already_called() and sess.author._last_review_json:
            log.info("【Author·总结·恢复】done+review 已完成, 跳过 LLM 调用")
            calls = []
        else:
            log.info("【Author·总结】prompt 沿用断点 → LLM 继续中…")
            t = now()
            calls = await sess.author.run(resume=True,
                                          on_token=sess._token_cb,
                                          on_step=sess._step_cb)
            log.info("【Author·总结】完成 | %d 次工具调用 | 耗时 %s",
                     len(calls), elapsed(t))
    else:
        sess.author._reset_submissions()

        transcript = sess.ctx.fmt_transcript(load_jsonl(sess.hist_path))
        summary_prompt = sess.author.build_summary_prompt(episode_transcript=transcript)
        log.info("【Author·总结】prompt %d 字 → LLM 调用中…", len(summary_prompt))

        t = now()
        calls = await sess.author.run(summary_prompt,
                                       on_token=sess._token_cb, on_step=sess._step_cb)
        log.info("【Author·总结】完成 | %d 次工具调用 | 耗时 %s",
                 len(calls), elapsed(t))

    log_tools(log, "Author", calls)
    await emit_internal(sess.emitter, "Author", calls, sess.debug)

    review_data = sess.author.last_review_json
    advance_chapter = False
    author_gap = ""
    if review_data and not review_data.get("error"):
        advance_chapter, author_gap = apply_summary_json(review_data, sess.universe,
                                                          sess.episode_count)

    sess.universe.author_notes = sess.author._notes

    # ═══════════ Phase E: 角色心里话 ═══════════
    # 从细纲 enter/exit 数组中提取所有出场角色名
    ep_chars = set()
    for s in episode.get("scenes", []):
        for e in s.get("enter", []):
            ep_chars.add(e["name"])
        for e in s.get("exit", []):
            ep_chars.add(e["name"])
    ep_chars = list(ep_chars)
    log.info("【心里话】%d 个角色依次写入记忆…", len(ep_chars))

    # 确定 gap：Author > Narrator > 默认
    gap = author_gap or episode.get("_gap", "")
    if not gap:
        gap = "big_gap" if advance_chapter else "small_gap"
    log.info("【间隔】gap=%s (advance_chapter=%s)", gap, advance_chapter)

    for name in ep_chars:
        if name not in sess.characters:
            continue
        char = sess.characters[name]
        char.set_episode_end_info(
            episode_id=episode.get("episode_id", 0),
            episode_name=episode.get("episode_name", ""),
            hist_path=str(sess.hist_path),
        )
        char.enter_episode_end_mode()

        character_new_messages = sess.mq.get_new(name, char._state.get("last_read_message_id"))
        episode_end_msg = char.build_episode_end_message(
            format_queue_messages(character_new_messages),
            episode.get("episode_name", f"ep_{episode['episode_id']}"),
        )

        # 重启恢复：角色可能已有断点状态
        if sess.is_restart and char.has_checkpoint():
            if char._exit_already_called():
                log.info("【心里话·恢复】%s 已退出, 解析已有消息", name)
                heartfelt_calls = _parse_calls_from_messages(
                    char._messages, {"speak", "write_memory", "update_state", "done"})
            else:
                log.info("【心里话·恢复】%s resume 模式继续", name)
                t_mem = now()
                heartfelt_calls = await char.run(
                    resume=True, on_token=sess._token_cb, on_step=sess._step_cb)
                log.debug("【心里话】%s | %d次工具调用 | 耗时 %s",
                          name, len(heartfelt_calls), elapsed(t_mem))
        else:
            t_mem = now()
            heartfelt_calls = await char.run(episode_end_msg,
                                              on_token=sess._token_cb,
                                              on_step=sess._step_cb)
            log.debug("【心里话】%s | %d次工具调用 | 耗时 %s",
                      name, len(heartfelt_calls), elapsed(t_mem))
        log_tools(log, name, heartfelt_calls)
        await emit_internal(sess.emitter, name, heartfelt_calls, sess.debug)

        for hc in heartfelt_calls:
            ht = hc["tool"]; ha = hc.get("args", {})
            if ht == "write_memory" and not hc.get("_invalid"):
                log.info("【心里话】%s 记忆已写入 (ep%03d)", name, episode.get("episode_id", 0))
            elif ht == "update_state" and not hc.get("_invalid"):
                pass
        char.apply_pending_updates()

        # Agent 生命周期：episode 结束
        char.on_episode_end(gap)
        char.mark_episode_ended(episode.get("episode_name", f"ep_{episode['episode_id']}"))
        last_id = sess.mq.last_message_id(name)
        if last_id:
            char.update_last_read(last_id)

    log.info("【心里话】全部完成")

    # Author 和 Narrator 也结束本 episode
    sess.author.on_episode_end(gap)
    sess.narrator.on_episode_end(gap)

    # ═══════════ Phase F: 推进 ═══════════
    if advance_chapter:
        sess.chapter_idx += 1
        log.info("【推进】进入第%d章", sess.chapter_idx + 1)
    else:
        log.info("【推进】停留在第%d章, 进入下一幕", sess.chapter_idx + 1)

    sess.advance_to(EpisodeState.PLANNING)

    # 大纲已耗尽且推进则为自然结束
    if sess.chapter_idx >= len(sess.outlines) and advance_chapter and sess.max_episodes == 0:
        log.info("【结束】大纲已耗尽 (第%d章 ≥ 共%d章), 自然结束",
                 sess.chapter_idx + 1, len(sess.outlines))
        sess.advance_to(EpisodeState.DONE)  # 信号：下次循环退出
