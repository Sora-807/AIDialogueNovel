# AIDialogueNovel

多智能体对话小说引擎。三个 Agent 协同创作——Author 写剧本，Narrator 当导演，Character 做演员。

## 理念

传统 AI 写小说是单人独奏——一个模型从头写到尾。但小说不是一个人写的：作者定大纲、导演控节奏、角色有自己的性格和记忆。三者拆开，各司其职。

```
Author（创作者）         Narrator（讲述者）          Character（角色）
     │                        │                        │
  看大纲、世界观              拿剧本指挥演出              有自己的设定、记忆
  规划每一幕的剧情            写旁白铺场景               用小剧场记忆保持一致性
  管理伏笔和世界观授权        决定谁说话                 第一人称发言
  不直接叙事                  用导演提示引导角色          三层结构：（动作）「内心」对话
```

## 快速开始

### 环境

- Python 3.12+
- Node.js 18+
- 一个兼容 OpenAI API 的 LLM 后端（OpenAI / 阿里云百炼 / 本地模型等）

### 安装

```bash
git clone <repo-url>
cd AINovelInDialogue

# Python 依赖
uv sync

# 前端依赖
cd frontend && npm install && cd ..
```

### 配置

启动后在浏览器打开 `http://localhost:5173`，点击右上角 ⚙ 按钮即可配置 LLM：

- **API Key** — 留空使用 `.env` 中的 `OPENAI_API_KEY`
- **Base URL** — API 地址
- **Model** — 模型名称

配置保存在 `config.json`，下次启动自动生效。

> 也可以直接创建 `.env` 文件配置（参考 `.env.example`），优先级低于前端设置。

### 启动

```bash
# 开发模式（前端热重载）
python main.py

# 生产模式（后端服务前端静态文件，单端口 8000）
python main.py --prod
```

浏览器打开 `http://localhost:5173`（开发）或 `http://localhost:8000`（生产）。

### 使用

1. 左上角下拉框选择故事
2. 点击 **Start** —— 引擎开始创作
3. 主区域实时看到旁白和角色对话
4. 轮到你的角色时底部输入框激活，输入对话回车发送
5. 左侧面板：导演提示；右侧面板：角色状态

## 核心架构：Universe 中心化

引擎采用单一状态中心 `Universe`——所有 Agent 通过它读写数据，序列化它 = 完美 checkpoint，反序列化 = 一步恢复。

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
  │   messages[], read_positions{}, send()/poll()
  ├─ LLM 对话历史（替代各 Agent._messages）
  │   conversations: {agent → [序列化消息]}
  └─ meta（自由扩展）

Checkpoint = universe.to_dict() → universe.json（一个文件）
```

## Story 结构

```
stories/{story_id}/
  story.json              ← 故事元信息
  worldview/              ← 世界观文件夹
    {条目名}.md
  outline/                ← 大纲文件夹
    【1】第一章名.md
  characters/{角色名}/
    profile.md            ← 角色全貌设定
    initial_state.md      ← 角色初始状态
```

### story.json

```json
{
  "description": "故事简介",
  "user_character": "人类玩家扮演的角色名"
}
```

`user_character` 是你扮演的角色。每个小剧场它必须出场。无用户模式（全 AI）可在前端设置中开启。

### 世界观 (worldview/)

每个 `.md` 一个条目，frontmatter 控制可见性：

```markdown
---
tags: [public]             # public = 所有人可见；不加 = 秘闻，需 Author 授权
name: 史莱克学院
description: 斗罗大陆第一魂师学院
---

# 正文
```

### 大纲 (outline/)

文件名格式 `【序号】章节名.md`。序号从 1 开始。

```markdown
---
name: 章节名
description: 本章概述
---

# 正文（给 Author 参考）
```

### 角色 (characters/)

**profile.md** — 角色全貌设定。只有 Author 可见完整内容。

**initial_state.md** — 角色初始状态。注入给角色自身，形成自我认知。运行时会被角色通过 `update_state` 工具主动更新。

## 存档结构

```
saves/{story_id}/
  universe.json           ← 唯一 checkpoint（替代旧 session.json + checkpoints/）
  history.jsonl           ← 公开叙事事件流
  trace/                  ← Agent 每步消息追踪
  author/memories/        ← Author 每幕记忆归档
  characters/{角色名}/
    state.md              ← 角色当前状态
    memories/ep001.md      ← 角色每幕记忆归档
  llm_raw.jsonl           ← LLM 原始调用记录
  run.log                 ← 运行日志
```

## 项目结构

```
main.py                  ← 入口
src/
  agents/                ← Agent 实现
    base.py              ← BaseAgent + ReAct 循环 + 钩子系统
    author.py            ← Author Agent
    narrator.py          ← Narrator Agent
    character.py         ← Character Agent
    formatter.py         ← Formatter Agent（结构化审查子 agent）
  core/
    universe.py          ← ★ Universe — 唯一状态中心
    engine.py            ← 引擎装配器
    session.py           ← Session — 创建 Universe + 加载恢复
    state_machine.py     ← 状态机
    checkpoint.py        ← 兼容层
    phases/              ← 引擎各阶段（planning / inner_loop / summary）
    context.py           ← 上下文格式化
    trace.py             ← Agent 消息追踪
    logger.py            ← 日志
    emitter.py           ← 事件发射器
  llm/                   ← LLM 调用
  storage/               ← 文件读写
backend/                 ← FastAPI + SSE
frontend/                ← React + TypeScript
stories/                 ← Story 源数据（不可变）
saves/                   ← 运行时存档
```

## 打包发布

```bash
# 构建前端
cd frontend && npm run build && cd ..

# 打包
python build.py

# 输出: dist/AINovelInDialogue_v0.1.0.zip
```

解压后双击 `启动.bat` 即可运行。用户可自行修改 `stories/` 文件夹中的故事数据。

## License

MIT
