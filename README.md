# AIDialogueNovel

多智能体对话小说引擎。三个 Agent 协同创作——Author 写剧本，Narrator 当导演，Character 做演员。

## 理念

传统 AI 写小说是单人独奏——一个模型从头写到尾。但小说不是一个人写的：作者定大纲、导演控节奏、角色有自己的性格和记忆。如果把这三个角色拆开，让它们各自专精、互相协作，会发生什么？

```
Author（创作者）         Narrator（讲述者/导演）      Character（角色）
     │                        │                        │
  看大纲、世界观              拿剧本指挥演出              有自己的设定、记忆、语癖
  规划每一幕的剧情            写旁白铺场景               用小剧场记忆保持一致性
  管理伏笔和世界观授权        决定谁说话                 第一人称发言
  不直接叙事                  用导演提示引导角色          三层结构：（动作）「内心」对话
```

**为什么三人协作？**

- **Author 不直接叙事**：它只规划"这一幕要发生什么"，不写具体句子。角色怎么说是角色的事。
- **Narrator 不替角色说话**：它写旁白、铺场景、控制发言权，但绝不替主要角色开口。
- **角色有记忆**：每个角色每幕结束后写记忆归档。以后角色被唤醒时，可以用 `recall` 搜索自己的过去。说话风格不会因为上下文切换而漂移。

## 快速开始

### 环境

- Python 3.11+
- Node.js 18+
- 一个兼容 OpenAI API 的 LLM 后端

### 安装

```bash
# 克隆
git clone <repo-url>
cd AINovelInDialogue

# Python 依赖
uv sync
# 或 pip install -r pyproject.toml

# 前端依赖
cd frontend && npm install && cd ..
```

### 配置

复制 `.env.example` 为 `.env`，填入你的 API 信息：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 必填：API Key
OPENAI_API_KEY=sk-your-key-here

# API 地址 — 支持任意兼容 OpenAI 协议的服务（如 OpenAI、Azure、本地模型等）
OPENAI_BASE_URL=https://api.openai.com/v1

# 模型名称
LLM_MODEL=gpt-4o

# 流式输出 — 推荐开启，前端会实时看到文字生成
LLM_STREAM=true
```

### 启动

```bash
python main.py
```

后端启动在 `localhost:8000`，前端 `localhost:5173`（热重载）。浏览器打开 `http://localhost:5173`。

只用后端（前端单独启动）：

```bash
python main.py --backend-only
```

### 前端使用

1. **左上角下拉框**选择故事
2. 点击 **Start** 按钮——引擎开始运行
3. 主区域看到旁白和角色对话实时流式输出
4. 当你扮演的角色（如霍雨浩）轮到发言时，底部的输入框会激活——输入你的对话，回车发送
5. **右侧面板**：轮到你的角色时会显示当前状态和导演提示
6. Debug 复选框切换内部工具调用显示

## Story 结构

一个 Story 是一个文件夹，放在 `stories/` 下。文件夹名即 story_id。

```
stories/{story_id}/
  story.json              ← 故事元信息
  worldview/              ← 世界观文件夹
    {条目名}.md
    ...
  outline/                ← 大纲文件夹
    【1】第一章名.md
    【2】第二章名.md
    ...
  characters/{角色名}/
    profile.md            ← 角色全貌设定（Author 可见全部）
    initial_state.md      ← 角色初始状态（注入给角色自己）
```

### story.json

```json
{
  "description": "故事简介",
  "user_character": "你扮演的角色名"
}
```

`user_character` 是故事中由人类玩家扮演的角色。每个小剧场中它必须出场，Narrator 只给它感官和情绪指引，不替它做决定。

### 世界观 (worldview/)

每个 `.md` 文件是一个世界观条目。frontmatter 控制可见性：

```markdown
---
tags: [public, 地点]           # public = 所有角色和 Narrator 自动知晓
                               # hidden（或没有 public）= 世界秘闻，需 Author 授权
name: 史莱克学院
description: 斗罗大陆第一魂师学院
---

# 正文（任意 Markdown）
```

Narrator 和角色只能看到 `public` 条目。世界秘闻需要 Author 在每个小剧场中**主动授权**——授权 = 永久揭露，Narrator 从此可以看到该条目。

### 大纲 (outline/)

文件夹中的每个 `.md` 是一个章节。文件名格式：`【序号】章节名.md`。序号从 1 开始。

```markdown
---
name: 章节名
description: 本章概述
---

# 正文（任意 Markdown，给 Author 参考）
```

大纲是参考而非硬性约束——Author 可以跳过或调整。

### 角色 (characters/)

每个角色一个文件夹，包含两个文件：

**profile.md** — 角色全貌设定。**只有 Author 能看到完整内容**。用于 Author 理解角色的背景、性格、秘密，从而规划合理的剧情走向。

**initial_state.md** — 角色初始状态。**注入给角色自己**，形成它的自我认知。运行时状态会保存在 `saves/{story_id}/characters/{角色名}/state.md`，后续优先读取。

```markdown
## 公开信息
外人眼中的角色。给 Narrator 看。

## 心理状态
角色当前的情绪、想法。角色自己能感知到。

## 对他人的看法
角色对其他人的态度。影响对话时的反应。

## 身体状态
角色的身体状况——受伤、疲劳、武魂状态等。
```

## 存档结构

运行时数据保存在 `saves/{story_id}/`：

```
saves/{story_id}/
  session.json            ← 引擎状态
  history.jsonl           ← 公开叙事事件流
  checkpoints/            ← 断点
  queues/                 ← Agent 消息收件箱
  trace/                  ← Agent 每步消息追踪（调试用）
  characters/{角色名}/
    state.md              ← 当前状态
    memories/ep001.md      ← 每集记忆归档
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
    formatter.py         ← Formatter Agent（Author 的审查子 agent）
  core/
    engine.py            ← 引擎装配器
    session.py           ← 会话数据 + 加载
    state_machine.py     ← 状态机
    checkpoint.py        ← 断点
    phases/              ← 引擎各阶段
    context.py           ← 上下文聚合 + 权限视图
    message_queue.py     ← 消息队列
    trace.py             ← Agent 消息追踪
    logger.py            ← 日志
    emitter.py           ← 事件发射器
  llm/                   ← LLM 调用
  storage/               ← 文件读写
backend/                 ← FastAPI + SSE
frontend/                ← React + TypeScript
```

## License

MIT
