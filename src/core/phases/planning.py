"""Phase A+B — Author 规划 + Narrator 配置。"""
from src.core.session import Session
from src.core.state_machine import EpisodeState
from src.core.emitter import EpisodeChangeEvent
from src.core.phases._helpers import (
    now, elapsed, log_tools, append_history, emit_internal,
    build_permitted_worldview,
)


async def run_planning(sess: Session):
    """Author 规划下一个小剧场 → Narrator 配置 → 状态推进到 RUNNING。"""
    log = sess.log
    ep_num = sess.episode_count + 1

    # ═══════════ Phase A: Author 规划 ═══════════
    log.info("【Author·规划】开始规划第%d幕 (第%d章) …",
             ep_num, sess.chapter_idx + 1)
    sess.round_log.begin_episode(ep_num, "")  # name 在 Author 产出后才知道

    sess.author.on_episode_start({"phase": "planning", "episode_id": ep_num,
                                   "chapter_idx": sess.chapter_idx})
    # 不调 reset_messages() — on_episode_end 的 manage_context(gap) 已决定保留多少历史。
    # 首次运行时 _messages 本身就是空的。
    sess.author._reset_submissions()
    sess.author._phase = "planning"
    sess.author.set_exit_tool("done")
    sess.author.register_reader("history", sess.ctx.make_history_reader())
    sess.author.register_reader("foreshadowing", sess.ctx.make_foreshadowing_reader())

    view = sess.ctx.author_view(sess.chapter_idx)
    planning_prompt = sess.author.build_planning_prompt(**view)
    log.info("【Author·规划】prompt %d 字 → LLM 调用中…", len(planning_prompt))

    t = now()
    calls = await sess.author.run(planning_prompt,
                                  on_token=sess._token_cb, on_step=sess._step_cb)
    log.info("【Author·规划】完成 | %d 次工具调用 | 耗时 %s",
             len(calls), elapsed(t))
    log_tools(log, "Author", calls)
    await emit_internal(sess.emitter, "Author", calls, sess.debug)

    # Review JSON 即 episode —— 不经过中间转换，不丢字段
    review_data = sess.author.last_review_json
    episode = review_data if (review_data and not review_data.get("error")) else {}
    episode["episode_id"] = len(sess.author_state.get("episodes", [])) + 1

    sess.author_state.setdefault("episodes", []).append(episode)
    sess.author_state["_notes"] = sess.author._notes
    sess.advance_to(EpisodeState.RUNNING)

    ep_name = episode.get("episode_name", "")
    chars = episode.get("characters", [])
    log.info("【Author·规划】产出: 「%s」 | 出场 %d 人 | 授权 %d 条世界观",
             ep_name or "?", len(chars),
             len(episode.get("worldview_grants", [])))
    if ep_name:
        sess.round_log.set_episode_name(ep_name)
    append_history(sess.hist_path, "episode_change", "System",
                   f"第{episode['episode_id']}幕：{episode.get('episode_name', '')}")
    await sess.emitter.on_episode_change(EpisodeChangeEvent(
        episode_name=episode.get("episode_name", ""),
        episode_id=episode["episode_id"], state="episode_created"))
    sess.episode_count += 1

    # ═══════════ Phase B: Narrator 配置 ═══════════
    _configure_narrator(sess, episode)


def _configure_narrator(sess: Session, episode: dict):
    """Phase B — 配置 Narrator：世界观授权、角色信息、初始消息。"""
    log = sess.log
    chars_data = episode.get("characters", [])
    episode_chars = [c["name"] for c in chars_data if c.get("name")]

    log.info("【Narrator·配置】第%d幕「%s」| 出场=%s | worldview授权=%d条",
             episode["episode_id"], episode.get("episode_name", ""),
             episode_chars, len(episode.get("worldview_grants", [])))

    # 累积世界观授权
    all_grants = list(sess.narrator_state.get("worldview_grants", []))
    for g in episode.get("worldview_grants", []):
        path = g.get("path", "")
        if path and not any(old.get("path") == path for old in all_grants):
            all_grants.append(g)
            log.info("【世界观】授权: %s", path)
    sess.narrator_state["worldview_grants"] = all_grants
    sess.ctx.narrator_state = sess.narrator_state

    permitted = build_permitted_worldview(sess.worldview, all_grants)
    sess.narrator.register_reader("worldview",
                                   sess.ctx.make_narrator_worldview_reader(permitted))
    sess.narrator.register_reader("character",
                                   sess.ctx.make_narrator_character_reader(episode_chars))
    sess.narrator.set_episode_characters(episode_chars)
    sess.narrator_state["author_notes"] = episode.get("author_notes", "")
    sess.narrator_state["current_episode"] = episode["episode_id"]
    sess.save()

    nv = sess.ctx.narrator_view(episode_chars, episode)
    init_msg = sess.narrator.build_first_message(
        episode_name=episode.get("episode_name", ""),
        episode_summary=episode.get("summary", ""),
        detailed_outline=episode.get("detailed_outline", ""),
        author_notes=episode.get("author_notes", ""),
        worldview_text=nv["worldview_text"],
        characters_text=nv["characters_text"],
    )
    sess.mq.send("System", init_msg, "system", ["Narrator"],
                 episode_id=episode["episode_id"])

    sess.narrator_state["configured_episode_id"] = episode["episode_id"]
    sess.narrator.on_episode_start({"phase": "narrate", "episode_id": episode["episode_id"]})

    for name in episode_chars:
        if name in sess.characters:
            sess.characters[name].set_episode_entry(
                episode.get("episode_name", f"ep_{episode['episode_id']}"),
                "episode_start",  # 兼容旧参数
                "",
            )

    log.info("【Narrator·配置】完成, 进入内循环")
