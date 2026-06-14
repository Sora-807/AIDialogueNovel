"""Phase C — Narrator ↔ Character 内循环。"""
from src.core.session import Session
from src.core.state_machine import EpisodeState
from src.core.emitter import NarrateEvent, SpeakEvent, EpisodeChangeEvent
from src.core.context import format_queue_messages
from src.core.phases._helpers import now, elapsed, log_tools, append_history, emit_internal


async def run_inner_loop(sess: Session):
    """Narrator 叙述 → 选发言人 → Character 发言 → 循环，直到 end_episode。"""
    log = sess.log
    episodes = sess.author_state.get("episodes", [])
    if not episodes:
        log.error("【内循环】无 episode 数据, 退出")
        sess.advance_to(EpisodeState.SUMMARIZING)
        return

    episode = episodes[-1]

    # 重启恢复：Narrator 消息历史为空时，重新发送剧本
    if sess.is_restart:
        # trace 补 begin_episode（跳过 planning 阶段导致没调用）
        ep_name = episode.get("episode_name", "")
        sess.round_log.begin_episode(episode["episode_id"], ep_name)
        if len(sess.narrator._messages) <= 1:
            log.info("【内循环·恢复】Narrator 上下文丢失, 重新发送剧本")
            from src.core.phases.planning import _configure_narrator
            _configure_narrator(sess, episode)
    # 舞台管理：从首个小节 enter 数组提取初始角色。重启恢复用存档
    scenes = episode.get("scenes", [])
    init_stage = set()
    if scenes:
        for e in scenes[0].get("enter", []):
            init_stage.add(e["name"])
    stage = set(sess.narrator_state.get("stage_characters", init_stage))

    # 重启恢复：上次是用户等待中被中断 → 跳过 Narrator 回合
    from src.core.checkpoint import load_engine_checkpoint as _ld
    ckpt = _ld(sess.story_id)
    skip_to_user = (ckpt and ckpt.get("waiting_user") and ckpt.get("active_role")
                    and ckpt["active_role"] == sess.user_char)
    first_round = not sess.is_restart  # 重启时不算新一幕
    inner_round = 0
    episode_running = True

    while sess.state == EpisodeState.RUNNING and episode_running:
        inner_round += 1
        if skip_to_user:
            # 跳过 Narrator 回合，直接让用户发言
            skip_to_user = False
            picked_speaker = ckpt["active_role"]
            narrator_context = "（从断点恢复）"
            log.info("【内循环·恢复】跳过 Narrator，直接等待用户 %s", picked_speaker)
        else:
            # ── Narrator 回合 ──
            narrator_new = sess.mq.get_new("Narrator", sess.narrator_state.get("last_read_message_id"))
            narrator_msg = sess.narrator.build_continue_message(
                format_queue_messages(narrator_new),
                new_episode=(first_round and inner_round == 1),
                stage_names=list(stage),
            )
            t = now()
            narrator_calls = await sess.narrator.run(narrator_msg,
                                                      on_token=sess._token_cb,
                                                      on_step=sess._step_cb)
            log.debug("【Narrator】round %d | %d次工具调用 | 耗时 %s",
                      inner_round, len(narrator_calls), elapsed(t))
            log_tools(log, "Narrator", narrator_calls)
            await emit_internal(sess.emitter, "Narrator", narrator_calls, sess.debug)

            # 解析 Narrator 输出
            picked_speaker = None
            narrator_context = ""
            for c in narrator_calls:
                t_name = c["tool"]; args = c.get("args", {})
                if t_name == "__error__":
                    log.error("【Narrator】LLM 返回了 __error__, 跳过")
                    continue
                if t_name == "speak" and not c.get("_invalid"):
                    text = args.get("text", "")
                    if text:
                        sess.mq.send("Narrator", text, "narrate", list(stage),
                                     episode_id=episode["episode_id"])
                        append_history(sess.hist_path, "narrate", "Narrator", text)
                        log.info("【Narrator】旁白 (%d字) → %d人: %s", len(text), len(stage), text[:120])
                        await sess.emitter.on_narrate(NarrateEvent(content=text))
                elif t_name == "pick_speaker" and not c.get("_invalid"):
                    picked_speaker = args.get("name", "")
                    narrator_context = args.get("context", "")
                    log.info("【Narrator】选择发言人 → %s%s",
                             picked_speaker,
                             f" (导演提示 {len(narrator_context)}字)" if narrator_context else "")
                    from src.core.checkpoint import save_engine_checkpoint as _sv
                    _sv(sess.story_id, state=sess.state.value,
                        chapter_idx=sess.chapter_idx, episode_count=sess.episode_count,
                        active_role=picked_speaker, episode_id=episode["episode_id"],
                        stage_characters=list(stage),
                        waiting_user=(picked_speaker == sess.user_char))
                elif t_name == "manage_stage" and not c.get("_invalid"):
                    action = args.get("action", "")
                    name = args.get("name", "")
                    hint = args.get("hint", "")
                    if name not in sess.characters:
                        c["_invalid"] = True
                        c["_result"] = f"「{name}」不是可用角色，不能入场。可用：{'、'.join(sess.characters.keys())}"
                        log.warning("【Narrator】尝试对非角色入场: %s", name)
                        continue
                    if action == "enter":
                        stage.add(name)
                        if hint:
                            sess.mq.send("System", hint, "enter", [name],
                                         episode_id=episode["episode_id"])
                        log.info("【Narrator】入场 → %s%s", name,
                                 f" (hint={len(hint)}字)" if hint else "")
                    elif action == "exit":
                        stage.discard(name)
                        log.info("【Narrator】退场 → %s", name)
                    sess.narrator_state["stage_characters"] = list(stage)
                    c["_result"] = f"当前舞台：{'、'.join(stage)}" if stage else "舞台为空"
                elif t_name == "end_episode":
                    sess.advance_to(EpisodeState.SUMMARIZING)
                    reason = args.get("reason", "未说明")
                    narrator_gap = args.get("gap", "small_gap")
                    episode["_gap"] = narrator_gap
                    log.info("【Narrator】结束本幕 (原因: %s, gap=%s)", reason, narrator_gap)
                    await sess.emitter.on_episode_change(EpisodeChangeEvent(
                        episode_name=episode.get("episode_name", ""),
                        episode_id=episode["episode_id"], state="episode_ended"))
                    episode_running = False
                    break

            last_narrator_id = sess.mq.last_message_id("Narrator")
            if last_narrator_id:
                sess.narrator_state["last_read_message_id"] = last_narrator_id
                sess.save()
            if not episode_running:
                break

        # ── Character 回合 ──
        if picked_speaker and picked_speaker in sess.characters:
            char = sess.characters[picked_speaker]
            char_new = sess.mq.get_new(picked_speaker, char._state.get("last_read_message_id"))
            char_msg = char.build_user_message(format_queue_messages(char_new),
                                                narrator_context)
            is_user = (picked_speaker == sess.user_char)

            if is_user and sess.user_turn_callback:
                log.info("【%s·用户】等待输入…", picked_speaker)
                from src.core.checkpoint import save_engine_checkpoint as _sv
                _sv(sess.story_id, state=sess.state.value,
                    chapter_idx=sess.chapter_idx, episode_count=sess.episode_count,
                    active_role=picked_speaker, episode_id=episode["episode_id"],
                    stage_characters=list(stage), waiting_user=True)
                state_text = char.get_state_text()
                user_text = await sess.user_turn_callback(
                    picked_speaker, state_text, narrator_context,
                    format_queue_messages(char_new))
                char_calls = [{"tool": "speak", "args": {"text": user_text}, "_result": "OK"}]
                log.info("【%s·用户】回复 %d 字", picked_speaker, len(user_text))
            else:
                t_char = now()
                char_calls = await char.run(char_msg, on_token=sess._token_cb,
                                             on_step=sess._step_cb)
                log.info("【%s】发言完成 | %d次工具调用 | 耗时 %s",
                         picked_speaker, len(char_calls), elapsed(t_char))
                char.apply_pending_updates()

            log_tools(log, picked_speaker, char_calls)
            await emit_internal(sess.emitter, picked_speaker, char_calls, sess.debug)

            for cc in char_calls:
                ct = cc["tool"]; ca = cc.get("args", {})
                if ct == "__error__":
                    continue
                if ct == "speak" and not cc.get("_invalid"):
                    text = ca.get("text", "")
                    if text:
                        targets = (["Narrator"] +
                                   [n for n in stage if n != picked_speaker] +
                                   [picked_speaker])
                        sess.mq.send(picked_speaker, text, "speak", targets,
                                     episode_id=episode["episode_id"])
                        append_history(sess.hist_path, "speak", picked_speaker, text)
                        log.info("【%s】「%s」", picked_speaker, text[:150])
                        await sess.emitter.on_speak(SpeakEvent(speaker=picked_speaker, content=text))
                elif ct == "update_state" and not cc.get("_invalid"):
                    pass

            last_char_id = sess.mq.last_message_id(picked_speaker)
            if last_char_id:
                char.update_last_read(last_char_id)

            # 保存断点：角色发言完毕，控制权回到 Narrator
            from src.core.checkpoint import save_engine_checkpoint as _sv
            _sv(sess.story_id,
                state=sess.state.value,
                chapter_idx=sess.chapter_idx,
                episode_count=sess.episode_count,
                active_role="Narrator",
                episode_id=episode["episode_id"],
                stage_characters=list(stage))
