# AINovelInDialogue — 多 Agent 对话小说引擎

## 核心架构：Universe 中心化

**Universe (`src/core/universe.py`) 是引擎唯一可变状态中心。** 序列化它 = 完美 checkpoint，反序列化 = 一步恢复。

```
Universe（唯一状态中心，可序列化）
  ├─ Story 源数据（从文件加载，运行时只读）
  │   worldviews, outlines, characters, user_character
  ├─ 引擎位置
  │   state, chapter_idx, episode_count
  ├─ Author 域（产出）
  │   episodes[], foreshadowing[], short_term_plot, author_notes[]
  ├─ Narrator 域（演出控制）
  │   stage[], worldview_grants[], configured_episode_id
  ├─ Character 域（运行时状态）
  │   character_states: {name → state.md 正文}
  ├─ 通信总线（替代 MessageQueue）
  │   messages[], read_positions{}, send()/poll()/get_new()/mark_read()
  ├─ LLM 对话历史（替代各 Agent._messages）
  │   conversations: {agent → [序列化消息]}
  └─ meta（自由扩展）

Checkpoint = universe.to_dict() → json.dumps → universe.json（一个文件）
恢复 = Universe.from_dict(json.load(f)) → 一步完成
```

## 数据通信规则

**所有 Agent 间数据通信都必须走 Universe：**
- 发消息 → `universe.send(from, content, type, targets)`
- 收消息 → `universe.poll(agent_name)` 或 `universe.get_new(agent_name)`
- 标记已读 → `universe.mark_read(agent_name)` 或设置 `read_positions[name]`
- 读写任何引擎/角色状态 → 直接操作 Universe 对应字段

Agent 不再持有需要持久化的内部状态——它们是 Universe 的 reader + writer。

## 项目结构

```
main.py                  ← 唯一入口: Vite(5173) + 后端(8000)
src/
  agents/                ← Agent: Author, Narrator, Character
    base.py              ← BaseAgent + ReAct 循环 + self.universe 引用
    author.py            ← AuthorAgent — 规划/总结，读 universe.episodes 等
    narrator.py          ← NarratorAgent — 控场，读 universe.stage 等
    character.py         ← CharacterAgent — 扮演，读 universe.character_states
    formatter.py         ← FormatterAgent — 结构化填入（Review 子 agent）
  core/
    universe.py          ← ★ Universe 数据类 — 唯一状态中心
    engine.py            ← 装配器 — Session.load → 调度 Phase
    session.py           ← Session — 创建 Universe，加载 Story 数据 + 恢复
    state_machine.py     ← EpisodeState + GapType 枚举
    checkpoint.py        ← 兼容层（旧 API → Universe 序列化）
    phases/
      planning.py        ← Phase A+B: Author 规划 + Narrator 配置
      inner_loop.py      ← Phase C: Narrator ↔ Character 内循环
      summary.py         ← Phase D+E+F: 总结 + 心里话 + 推进
      _helpers.py        ← Phase 共享工具函数
    context.py           ← StoryContext — 格式化逻辑（从 Universe 读数据）
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
  universe.json          ← ★ Universe 序列化 = 唯一 checkpoint
  history.jsonl          ← 公开叙事事件流
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
__init__(story_id, universe)  ← 接收 Universe 引用
load_state_from_universe()    ← 从 Universe 恢复对话历史和内部状态

on_episode_start(ctx)
  ├─ inject_prompt(text) — 引擎注入外部提示词
  └─ 根据 gap 决定 manage_context()

┌─ run() ────────────────────────────┐
│  if resume + _messages 非空:       │
│    跳过创建 SystemMessage，         │
│    跳过追加 HumanMessage，          │
│    直接继续 ReAct 循环              │
│  for step in 1..MAX:               │
│    before_llm hook → sess.save()   │
│    llm.invoke()                     │
│    execute_tools()                  │
│    _messages 追加 AI + Tool 消息    │
│    universe.save_conversation()     │  ← 每步自动同步
│    on_step callback → sess.save()   │  ← post-step 也保存
│    if exit tool called: return      │
└────────────────────────────────────┘

on_episode_end(gap)
  ├─ manage_context(gap)
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

## 断点恢复流程

```
Session.load()
  ├─ 创建 Universe + 加载 Story 源数据
  ├─ 尝试从 universe.json 恢复（Universe.from_dict）
  │   └─ fallback: 旧 session.json → 提取字段
  ├─ 创建 CharacterAgent（从 Universe.character_states 恢复状态）
  ├─ 创建 AuthorAgent/NarratorAgent（从 Universe.conversations 恢复对话）
  └─ is_restart = True（如果有恢复的数据）

引擎主循环：
  ├─ Phase 检测 is_restart → resume 模式
  │   ├─ 如果 _exit_already_called() → 跳过 run()，直接处理完工结果
  │   └─ 否则 → run(resume=True) 继续 ReAct 循环
  └─ 首次完成任意 phase → is_restart = False（后续 phase 正常执行）
```

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
| 子系统 | `【中文】` | `【世界观】【心里话】【推进】【记忆】【恢复】` |

### 日志对齐

格式化器用 `%(levelname)-8s` 固定 level 宽度为 8 字符，保证消息列对齐。

### 双通道日志

- **stderr（终端）**：换行符保留，多行展开，阅读友好
- **run.log（文件）**：换行符转义为 `\\n`，每条日志严格一行，grep 友好

### 阶段日志模式

Agent 的规划/总结阶段遵循同一模式（以 Author 为例）：

```
【Author·规划】开始规划第N幕 …              ← 阶段开始
【Author·规划】prompt N 字 → LLM 调用中…   ← 调用前
【Author·规划】完成 | N 次工具调用 | 耗时 Xs  ← 调用后
【Author·规划】产出: 「幕名」| 出场 N 人 | …  ← 结果摘要
```

### 数值使用 `%d`/`%s` 而非 f-string

```python
# ✅ 正确
log.info("【Author·规划】prompt %d 字 → LLM 调用中…", len(prompt))

# ❌ 错误
log.info(f"【Author·规划】prompt {len(prompt)} 字 → LLM 调用中…")
```

### 耗时记录

```python
t = _now()
calls = await agent.run(...)
log.info("【Author·规划】完成 | %d 次工具调用 | 耗时 %s", len(calls), _elapsed(t))
```

### 状态字段

状态机状态值保持英文（`planning`, `running`, `summarizing`, `done`），描述性文字用中文。
