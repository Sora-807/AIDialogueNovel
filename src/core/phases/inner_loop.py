"""Phase C — Narrator ↔ Character 内循环。"""
from src.core.session import Session
from src.core.state_machine import EpisodeState
from src.core.emitter import NarrateEvent, SpeakEvent, EpisodeChangeEvent
from src.core.context import format_queue_messages
from src.core.phases._helpers import (
    now, elapsed, log_tools, append_history, emit_internal,
    _parse_calls_from_messages,
)


def _emit_state_if_updated(sess: Session, char):
    """如果有 pending 更新，apply 后发射 state_update 事件。"""
    if char._pending_updates and sess.emitter:
        old_text = char._state_text
        char.apply_pending_updates()
        if char._state_text != old_text:
            sess.emitter.on_state_update(char.character_name, char._state_text)
        return True  # 已 apply，调用方不用再 apply
    return False


def _restore_narrator_characters(sess: Session, episode: dict):
    """重启时从 episode 恢复 Narrator 的角色池（瞬态字段不存 checkpoint）。"""
    episode_chars = set()
    for s in episode.get("scenes", []):
        for e in s.get("enter", []):
            episode_chars.add(e["name"])
        for e in s.get("exit", []):
            episode_chars.add(e["name"])
    sess.narrator._episode_character_names = list(episode_chars)
    sess.narrator._available_characters = episode.get("available_characters", [])
    sess.log.info("【内循环·恢复】角色池: episode=%d人 available=%d人",
                  len(episode_chars), len(sess.narrator._available_characters))


async def run_inner_loop(sess: Session):
    """Narrator 叙述 → 选发言人 → Character 发言 → 循环，直到 end_episode。"""
    log = sess.log
    log.info("【内循环】进入, episodes=%d, stage=%s, is_restart=%s",
             len(sess.universe.episodes), sess.universe.stage, sess.is_restart)
    if not sess.universe.episodes:
        log.error("【内循环】无 episode 数据, 退出")
        sess.advance_to(EpisodeState.SUMMARIZING)
        return

    episode = sess.universe.episodes[-1]

    # 重启恢复：从 episode 恢复角色列表（瞬态字段，不存 checkpoint）
    if sess.is_restart:
        ep_name = episode.get("episode_name", "")
        sess.round_log.begin_episode(episode["episode_id"], ep_name)
        # 恢复角色池（无论 Narrator 有无消息都必须做，否则 pick_speaker 校验过不了）
        _restore_narrator_characters(sess, episode)
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
    stage = set(sess.universe.stage if sess.universe.stage else init_stage)

    # 重启恢复：上次是用户等待中被中断 → 跳过 Narrator 回合
    meta = sess.universe.meta
    skip_to_user = (meta.get("waiting_user") and meta.get("active_role")
                    and meta["active_role"] == sess.user_char)
    first_round = not sess.is_restart  # 重启时不算新一幕
    inner_round = 0
    episode_running = True

    while sess.state == EpisodeState.RUNNING and episode_running:
        inner_round += 1
        # 首轮处理完恢复后立即清除标记，后续轮次正常执行
        if sess.is_restart:
            sess.is_restart = False
            log.info("【内循环·恢复】首轮恢复完成, 进入正常循环")
        if skip_to_user:
            # 跳过 Narrator 回合，直接让用户发言
            skip_to_user = False
            picked_speaker = meta["active_role"]
            narrator_context = "（从断点恢复）"
            log.info("【内循环·恢复】跳过 Narrator，直接等待用户 %s", picked_speaker)
        else:
            # ── Narrator 回合 ──
            # 重启恢复：Narrator 已有断点状态 → 检测是否需要恢复
            if sess.is_restart and sess.narrator.has_checkpoint():
                if sess.narrator._exit_already_called():
                    # Narrator 已完成（pick_speaker 或 end_episode 已调）
                    log.info("【Narrator·恢复】检测到已退出, 跳过 LLM 调用, 解析已有消息")
                    narrator_calls = _parse_calls_from_messages(
                        sess.narrator._messages, {"speak", "pick_speaker", "manage_stage", "end_episode"})
                else:
                    # Narrator 未完成 → resume 继续 ReAct 循环
                    log.info("【Narrator·恢复】resume 模式继续 | %d 条历史消息",
                             len(sess.narrator._messages))
                    t = now()
                    narrator_calls = await sess.narrator.run(
                        resume=True, on_token=sess._token_cb, on_step=sess._step_cb)
                    log.debug("【Narrator】round %d | %d次工具调用 | 耗时 %s",
                              inner_round, len(narrator_calls), elapsed(t))
            else:
                narrator_new = sess.universe.get_new("Narrator")
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
            from_ckpt = any(c.get("_from_checkpoint") for c in narrator_calls)
            for c in narrator_calls:
                t_name = c["tool"]; args = c.get("args", {})
                if t_name == "__error__":
                    log.error("【Narrator】LLM 返回了 __error__, 跳过")
                    continue
                if t_name == "speak" and not c.get("_invalid"):
                    text = args.get("text", "")
                    if text:
                        if not from_ckpt:
                            sess.mq.send("Narrator", text, "narrate", list(stage),
                                         episode_id=episode["episode_id"])
                            append_history(sess.hist_path, "narrate", "Narrator", text)
                        log.info("【Narrator】旁白 (%d字) → %d人: %s", len(text), len(stage), text[:120])
                        if not from_ckpt:
                            await sess.emitter.on_narrate(NarrateEvent(content=text))
                elif t_name == "pick_speaker" and not c.get("_invalid"):
                    picked_speaker = args.get("name", "")
                    narrator_context = args.get("context", "")
                    log.info("【Narrator】选择发言人 → %s%s",
                             picked_speaker,
                             f" (导演提示 {len(narrator_context)}字)" if narrator_context else "")
                    if not from_ckpt:
                        sess.universe.meta.update({
                            "active_role": picked_speaker,
                            "episode_id": episode["episode_id"],
                            "waiting_user": (picked_speaker == sess.user_char),
                        })
                        sess.universe.stage = list(stage)
                        sess.save()
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
                        if hint and not from_ckpt:
                            sess.mq.send("System", hint, "enter", [name],
                                         episode_id=episode["episode_id"])
                        log.info("【Narrator】入场 → %s%s", name,
                                 f" (hint={len(hint)}字)" if hint else "")
                    elif action == "exit":
                        stage.discard(name)
                        log.info("【Narrator】退场 → %s", name)
                    sess.universe.stage = list(stage)
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

            last_narrator_id = sess.universe.last_message_id("Narrator")
            if last_narrator_id:
                sess.universe.read_positions["Narrator"] = last_narrator_id
                sess.save()
            if not episode_running:
                break

        # ── Character 回合 ──
        if picked_speaker and picked_speaker in sess.characters:
            char = sess.characters[picked_speaker]
            is_user = (picked_speaker == sess.user_char)

            if is_user and sess.user_turn_callback:
                log.info("【%s·用户】等待输入…", picked_speaker)
                character_new_messages = sess.mq.get_new(picked_speaker, char._state.get("last_read_message_id"))
                sess.universe.meta.update({
                    "active_role": picked_speaker,
                    "episode_id": episode["episode_id"],
                    "waiting_user": True,
                })
                sess.universe.stage = list(stage)
                sess.save()
                state_text = char.get_state_text()
                user_text = await sess.user_turn_callback(
                    picked_speaker, state_text, narrator_context,
                    format_queue_messages(character_new_messages))
                character_calls = [{"tool": "speak", "args": {"text": user_text}, "_result": "OK"}]
                log.info("【%s·用户】回复 %d 字", picked_speaker, len(user_text))
            elif sess.is_restart and char.has_checkpoint():
                # 重启恢复：角色已有断点状态
                if char._exit_already_called():
                    log.info("【%s·恢复】检测到已退出, 解析已有消息", picked_speaker)
                    character_calls = _parse_calls_from_messages(
                        char._messages, {"speak", "update_state", "done"})
                else:
                    log.info("【%s·恢复】resume 模式继续 | %d 条历史消息",
                             picked_speaker, len(char._messages))
                    t_char = now()
                    character_calls = await char.run(
                        resume=True, on_token=sess._token_cb, on_step=sess._step_cb)
                    log.info("【%s】发言完成 | %d次工具调用 | 耗时 %s",
                             picked_speaker, len(character_calls), elapsed(t_char))
                if not _emit_state_if_updated(sess, char):
                    char.apply_pending_updates()
            else:
                character_new_messages = sess.mq.get_new(picked_speaker, char._state.get("last_read_message_id"))
                character_message = char.build_user_message(format_queue_messages(character_new_messages),
                                                    narrator_context)
                t_char = now()
                character_calls = await char.run(character_message, on_token=sess._token_cb,
                                             on_step=sess._step_cb)
                log.info("【%s】发言完成 | %d次工具调用 | 耗时 %s",
                         picked_speaker, len(character_calls), elapsed(t_char))
                if not _emit_state_if_updated(sess, char):
                    char.apply_pending_updates()

            log_tools(log, picked_speaker, character_calls)
            await emit_internal(sess.emitter, picked_speaker, character_calls, sess.debug)

            character_from_checkpoint = any(c.get("_from_checkpoint") for c in character_calls)
            for cc in character_calls:
                ct = cc["tool"]; ca = cc.get("args", {})
                if ct == "__error__":
                    continue
                if ct == "speak" and not cc.get("_invalid"):
                    text = ca.get("text", "")
                    if text:
                        if not character_from_checkpoint:
                            targets = (["Narrator"] +
                                       [n for n in stage if n != picked_speaker] +
                                       [picked_speaker])
                            sess.mq.send(picked_speaker, text, "speak", targets,
                                         episode_id=episode["episode_id"])
                            append_history(sess.hist_path, "speak", picked_speaker, text)
                        log.info("【%s】「%s」", picked_speaker, text[:150])
                        if not character_from_checkpoint:
                            await sess.emitter.on_speak(SpeakEvent(speaker=picked_speaker, content=text))
                elif ct == "update_state" and not cc.get("_invalid"):
                    pass

            last_char_id = sess.mq.last_message_id(picked_speaker)
            if last_char_id:
                char.update_last_read(last_char_id)

            # 保存断点：角色发言完毕，控制权回到 Narrator
            sess.universe.meta.update({
                "active_role": "Narrator",
                "episode_id": episode["episode_id"],
                "waiting_user": False,
            })
            sess.universe.stage = list(stage)
            sess.save()
