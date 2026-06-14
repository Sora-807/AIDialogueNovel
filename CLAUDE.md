# AINovelInDialogue — 多 Agent 对话小说引擎

## 项目结构

```
main.py                  ← 唯一入口: Vite(5173) + 后端(8000)
src/
  agents/                ← Agent: Author, Narrator, Character
    base.py              ← BaseAgent + ReAct 循环 + 生命周期钩子
  core/
    engine.py            ← 装配器 (~86行) — Session.load → 调度 Phase
    session.py           ← Session 数据类 — 聚合所有运行时数据 + 加载/保存
    state_machine.py     ← EpisodeState + GapType 枚举
    checkpoint.py        ← 断点保存/恢复
    phases/
      planning.py        ← Phase A+B: Author 规划 + Narrator 配置
      inner_loop.py      ← Phase C: Narrator ↔ Character 内循环
      summary.py         ← Phase D+E+F: 总结 + 心里话 + 推进
      _helpers.py        ← Phase 共享工具函数
    context.py           ← StoryContext + format_queue_messages
    message_queue.py     ← 消息队列 I/O
    formatter.py         ← FormatterAgent — 工具分步填入字段
    trace.py             ← RoundLogger — Agent 每步 message trace
    logger.py            ← get_logger — 统一日志
    emitter.py           ← EventEmitter — 事件发射器接口
  llm/                   ← LLM 调用封装
  storage/               ← 文件读写（frontmatter, state）
backend/                 ← FastAPI + SSE
frontend/                ← React + TypeScript
stories/                 ← Story 源数据（不可变）
saves/                   ← 运行时存档
```

## Save 目录结构

```
saves/{story_id}/
  session.json           ← 统一引擎状态（合并 author + narrator + 状态机位置）
  history.jsonl          ← 公开叙事事件流
  checkpoints/
    engine.json          ← 断点（当前谁在说话 + 状态机位置）
  queues/                ← Agent 消息收件箱（episode 结束自动清理）
    Narrator.jsonl
    霍雨浩.jsonl
  trace/                 ← Agent 每步 message trace（调试核心）
    episode_001/Author/round_000/
  characters/             ← 角色状态 + 记忆
    霍雨浩/
      state.md
      memories/ep001.md
  llm_raw.jsonl          ← 原始 LLM 记录
  run.log                ← 运行日志
```

## Agent 生命周期

```
on_episode_start(ctx)
  ├─ 加载持久化状态
  ├─ inject_prompt(text) — 引擎注入外部提示词
  └─ 根据 gap 决定 manage_context()

┌─ run() ────────────────────────┐
│  for step in 1..MAX:           │
│    on_before_llm() ← 断点      │
│    llm.invoke()                 │
│    execute_tools()              │
└────────────────────────────────┘

on_episode_end(gap)
  ├─ manage_context(gap) — Agent 自己决定清理多少历史
  ├─ write_memory()
  └─ save_state()
```

## 引擎状态机

```
PLANNING ──(规划完成)──→ RUNNING ──(end_episode)──→ SUMMARIZING ──(总结完成)──→ DONE → PLANNING
```

- `PLANNING`: Author 规划中
- `RUNNING`: Narrator ↔ Character 内循环
- `SUMMARIZING`: Author 总结 + 心里话 + 推进
- `DONE`: 本幕完成，下次循环自动回到 PLANNING

## 日志风格

**所有 log 必须遵循此风格，保持日志 grep 友好、层次分明。**

### 标签格式

使用 `【标签】` 包裹阶段/角色标识，标签与内容之间**不加空格**：

```
log.info("【加载】世界观 %d 条 | 大纲 %d 章 | 角色 %d 人", ...)
log.info("【Author·规划】开始规划第%d幕 …", ...)
log.info("【Narrator】选择发言人 → %s", ...)
log.info("【%s】发言完成 | %d次工具调用 | 耗时 %s", char_name, ...)
log.info("【%s·用户】等待输入…", char_name)
```

### 标签命名规则

| 层级 | 格式 | 示例 |
|------|------|------|
| 引擎阶段 | `【中文】` | `【加载】【初始化】【就绪】【循环】【结束】` |
| Agent 阶段 | `【Agent·动作】` | `【Author·规划】【Author·总结】【Narrator·配置】` |
| Agent 运行时 | `【角色名】` | `【Narrator】【霍雨浩】【天梦冰蚕】` |
| 用户角色 | `【角色名·用户】` | `【霍雨浩·用户】` |
| 子系统 | `【中文】` | `【世界观】【心里话】【推进】【记忆】` |

### 日志对齐

格式化器用 `%(levelname)-8s` 固定 level 宽度为 8 字符，保证消息列对齐：

```
# logger.py 中的 formatter
"%(asctime)s [%(levelname)-8s] %(message)s"
```

效果：
```
11:32:18 [INFO    ] 【Author·规划】开始规划第1幕…
11:32:18 [DEBUG   ] 【Narrator】round 1 | 2次工具调用 | 耗时 3.2s
11:32:18 [WARNING ] 【Author·规划】过滤无效角色: ...
```

### 双通道日志

- **stderr（终端）**：换行符保留，多行展开，阅读友好
- **run.log（文件）**：换行符转义为 `\\n`，每条日志严格一行，grep 友好

`_OneLineFormatter`（`logger.py`）仅用于 FileHandler，StreamHandler 用标准 Formatter。

### 阶段日志模式

Agent 的规划/总结阶段遵循同一模式（以 Author 为例）：

```
【Author·规划】开始规划第N幕 …              ← 阶段开始
【Author·规划】prompt N 字 → LLM 调用中…   ← 调用前
【Author·规划】完成 | N 次工具调用 | 耗时 Xs  ← 调用后
【Author·规划】产出: 「幕名」| 出场 N 人 | …  ← 结果摘要
```

其他 Agent 的阶段日志也遵循此三段式：**开始 → 调用 → 完成+摘要**。

### 数值使用 `%d`/`%s` 而非 f-string

保持与 Python logging 的惰性求值一致，且 grep 时模式稳定：

```python
# ✅ 正确
log.info("【Author·规划】prompt %d 字 → LLM 调用中…", len(prompt))

# ❌ 错误
log.info(f"【Author·规划】prompt {len(prompt)} 字 → LLM 调用中…")
```

### 耗时记录

每个 LLM 调用必须记录耗时：

```python
t = _now()
calls = await agent.run(...)
log.info("【Author·规划】完成 | %d 次工具调用 | 耗时 %s", len(calls), _elapsed(t))
```

### 状态字段

状态机状态值保持英文（`episode_creating`, `summarized` 等），描述性文字用中文。
