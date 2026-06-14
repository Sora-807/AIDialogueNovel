import React, { useRef, useEffect, useState } from "react";
import { useChatStore } from "./stores/chatStore";
import { useSSE } from "./hooks/useSSE";
import { NarrateBubble, SpeakBubble } from "./components/MessageBubble";
import { SceneDivider } from "./components/SceneDivider";
import type { NarrateData, SpeakData, EpisodeChangeData } from "./types";

interface StoryInfo {
  story_id: string;
  name: string;
  description: string;
  user_character: string;
}

export default function App() {
  const store = useChatStore();
  const { messages, isRunning, storyId, setStoryId, userTurn, userCharacter } = store;
  const { start, stop, submitSpeak } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);
  const msgContainerRef = useRef<HTMLDivElement>(null);
  const [inputText, setInputText] = useState("");
  const [stories, setStories] = useState<StoryInfo[]>([]);
  const [lastState, setLastState] = useState("");
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [cfgApiKey, setCfgApiKey] = useState("");
  const [cfgBaseUrl, setCfgBaseUrl] = useState("");
  const [cfgModel, setCfgModel] = useState("");
  const [cfgStream, setCfgStream] = useState(true);
  const [cfgNoUser, setCfgNoUser] = useState(false);

  const fetchConfig = () => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => {
        setCfgApiKey(typeof d.llm.api_key === "string" && d.llm.api_key !== "***" ? d.llm.api_key : "");
        setCfgBaseUrl(d.llm.base_url || "");
        setCfgModel(d.llm.model || "");
        setCfgStream(d.llm.use_stream !== false);
        setCfgNoUser(!!d.debug_no_user);
      });
  };

  const saveConfig = () => {
    const body: Record<string, unknown> = {
      llm: { use_stream: cfgStream },
      debug_no_user: cfgNoUser,
    };
    if (cfgApiKey) (body.llm as Record<string, unknown>).api_key = cfgApiKey;
    if (cfgBaseUrl) (body.llm as Record<string, unknown>).base_url = cfgBaseUrl;
    if (cfgModel) (body.llm as Record<string, unknown>).model = cfgModel;
    fetch("/api/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(() => { setShowSettings(false); alert("配置已保存，下次启动生效。"); });
  };

  // 每集开始时请求最新角色状态
  const fetchState = () => {
    if (!storyId || !userCharacter) return;
    fetch(`/api/state/${storyId}/${userCharacter}`)
      .then((r) => r.json())
      .then((d) => { if (d.state) setLastState(d.state); });
  };

  useEffect(() => {
    fetchConfig();
    fetch("/api/stories")
      .then((r) => r.json())
      .then((d) => {
        setStories(d.stories || []);
        if (d.stories?.length) {
          if (!d.stories.find((s: StoryInfo) => s.story_id === storyId)) {
            setStoryId(d.stories[0].story_id);
          }
        }
      });
    if (storyId) {
      useChatStore.getState().clearMessages();
      fetch(`/api/history/${storyId}`)
        .then((r) => r.json())
        .then((d) => {
          const msgs = d.messages || [];
          msgs.forEach((m: { type: string; speaker: string; content: string; timestamp: string }) => {
            useChatStore.getState().addMessage({
              id: `hist_${m.timestamp}_${Math.random()}`,
              type: m.type as "narrate" | "speak" | "episode_change",
              timestamp: new Date(m.timestamp).getTime(),
              data: { speaker: m.speaker, content: m.content,
                      episode_name: "", episode_id: 0, state: "episode_created" as const },
            });
          });
        });
    }
  }, [storyId]);

  useEffect(() => {
    if (isAtBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isAtBottom]);

  const handleMsgScroll = () => {
    const el = msgContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setIsAtBottom(atBottom);
  };

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setIsAtBottom(true);
  };

  const userChar = userCharacter;

  const renderMessage = (msg: (typeof messages)[0]) => {
    switch (msg.type) {
      case "narrate":
        return <NarrateBubble key={msg.id} data={msg.data as NarrateData} />;
      case "speak": {
        const sd = msg.data as SpeakData;
        return <SpeakBubble key={msg.id} data={sd} isUser={sd.speaker === userChar} />;
      }
      case "episode_change":
        return <SceneDivider key={msg.id} data={msg.data as EpisodeChangeData} />;
      default:
        return null;
    }
  };

  const visibleMessages = messages.filter(
    (m) => m.type === "narrate" || m.type === "speak" || m.type === "episode_change"
  );

  const handleSubmit = () => {
    if (!inputText.trim()) return;
    submitSpeak(inputText);
    setInputText("");
  };

  // 新 episode 触发状态刷新
  const epCount = messages.filter(m => m.type === "episode_change").length;
  useEffect(() => { fetchState(); }, [epCount, storyId, userCharacter]);

  // userTurn 更新时保持最新状态
  if (userTurn?.state && userTurn.state !== lastState) {
    setLastState(userTurn.state);
  }

  const hasUserTurn = !!userTurn;

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
      {/* Left Sidebar — director notes */}
      <div style={{
        width: "30%", minWidth: 240, maxWidth: 340,
        borderRight: "1px solid #e5e7eb", overflow: "auto",
        backgroundColor: "#fafafa", padding: 16, fontSize: 13,
      }}>
        <div style={{ fontWeight: 700, color: "#7c3aed", marginBottom: 8 }}>导演提示</div>
        {userTurn?.context ? (
          <div style={{ color: "#4c1d95", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
            {userTurn.context}
          </div>
        ) : (
          <div style={{ color: "#d1d5db" }}>暂未收到导演提示</div>
        )}
      </div>

      {/* Center Chat */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <div
          style={{
            padding: "12px 24px", borderBottom: "1px solid #e5e7eb",
            display: "flex", alignItems: "center", gap: 12, backgroundColor: "#fff",
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 16 }}>AIDialogueNovel</span>
          <select value={storyId} onChange={(e) => setStoryId(e.target.value)} disabled={isRunning}
            style={{ border: "1px solid #d1d5db", borderRadius: 6, padding: "4px 8px", fontSize: 13, maxWidth: 140 }}>
            {stories.map((s) => (
              <option key={s.story_id} value={s.story_id}>{s.name}</option>
            ))}
          </select>
          {!isRunning ? (
            <button onClick={start} style={btnStyle("#6366f1")}>Start</button>
          ) : (
            <button onClick={stop} style={btnStyle("#ef4444")}>Stop</button>
          )}
          <button onClick={() => { fetchConfig(); setShowSettings(true); }} style={btnStyle("#6b7280")}>⚙</button>
        </div>

        {/* Settings Modal */}
        {showSettings && (
          <div onClick={() => setShowSettings(false)} style={{
            position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", zIndex: 100,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <div onClick={(e) => e.stopPropagation()} style={{
              backgroundColor: "#fff", borderRadius: 12, padding: 24, width: 420, maxHeight: "80vh", overflow: "auto",
              boxShadow: "0 8px 30px rgba(0,0,0,0.2)",
            }}>
              <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 16 }}>⚙ 设置</div>
              <div style={labelStyle}>API Key</div>
              <input value={cfgApiKey} onChange={(e) => setCfgApiKey(e.target.value)}
                placeholder="留空则使用 .env 中的 OPENAI_API_KEY"
                style={inputStyle} type="password" />
              <div style={labelStyle}>Base URL</div>
              <input value={cfgBaseUrl} onChange={(e) => setCfgBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1" style={inputStyle} />
              <div style={labelStyle}>Model</div>
              <input value={cfgModel} onChange={(e) => setCfgModel(e.target.value)}
                placeholder="gpt-4o" style={inputStyle} />
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <input type="checkbox" checked={cfgStream} onChange={(e) => setCfgStream(e.target.checked)} id="cfgStream" />
                <label htmlFor="cfgStream" style={{ fontSize: 13 }}>Use Stream</label>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
                <input type="checkbox" checked={cfgNoUser} onChange={(e) => setCfgNoUser(e.target.checked)} id="cfgNoUser" />
                <label htmlFor="cfgNoUser" style={{ fontSize: 13 }}>无用户模式（全 AI）</label>
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button onClick={() => setShowSettings(false)} style={btnStyle("#9ca3af")}>取消</button>
                <button onClick={saveConfig} style={btnStyle("#6366f1")}>保存</button>
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div ref={msgContainerRef} onScroll={handleMsgScroll}
          style={{ flex: 1, overflow: "auto", backgroundColor: "#fff", position: "relative" }}>
          {visibleMessages.length === 0 && (
            <div style={{ textAlign: "center", color: "#d1d5db", padding: 80, fontSize: 15 }}>
              {isRunning ? "Author is planning the episode..." : 'Press "Start" to begin the story'}
            </div>
          )}
          {visibleMessages.map(renderMessage)}
          <div ref={bottomRef} />
          {!isAtBottom && (
            <button onClick={scrollToBottom}
              style={{
                position: "sticky", bottom: 16, left: "50%", transform: "translateX(-50%)",
                backgroundColor: "#6366f1", color: "#fff", border: "none",
                borderRadius: 20, padding: "8px 20px", fontSize: 13, fontWeight: 600,
                cursor: "pointer", boxShadow: "0 2px 8px rgba(99,102,241,0.4)",
                zIndex: 10,
              }}>
              ↓ 最新消息
            </button>
          )}
        </div>

        {/* User Input Bar */}
        <div style={{
          padding: "12px 24px", borderTop: `2px solid ${hasUserTurn ? "#6366f1" : "#e5e7eb"}`,
          backgroundColor: hasUserTurn ? "#f5f3ff" : "#f9fafb", display: "flex", gap: 10, alignItems: "flex-end"
        }}>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
            placeholder={hasUserTurn ? `作为 ${userTurn?.speaker} 发言...` : "等待你的回合..."}
            disabled={!hasUserTurn}
            rows={3}
            style={{
              flex: 1, borderRadius: 8, border: "1px solid #d1d5db",
              padding: "8px 12px", fontSize: 14, resize: "none",
              opacity: hasUserTurn ? 1 : 0.6,
            }}
            autoFocus={!!hasUserTurn}
          />
          <button onClick={handleSubmit}
            disabled={!hasUserTurn || !inputText.trim()}
            style={btnStyle(hasUserTurn ? "#6366f1" : "#9ca3af")}>发送</button>
        </div>
      </div>

      {/* Right Sidebar — character state */}
      <div style={{
        width: "30%", minWidth: 240, maxWidth: 340,
        borderLeft: "1px solid #e5e7eb", overflow: "auto",
        backgroundColor: "#fafafa", padding: 16, fontSize: 13,
      }}>
        <div style={{ fontWeight: 700, marginBottom: 8, color: "#374151" }}>角色状态</div>
        {lastState ? (
          <StateMarkdown state={lastState} />
        ) : (
          <div style={{ color: "#d1d5db" }}>
            {isRunning ? "等待状态更新..." : "就绪"}
          </div>
        )}
      </div>
    </div>
  );
}

function btnStyle(color: string): React.CSSProperties {
  return {
    backgroundColor: color, color: "#fff", border: "none",
    borderRadius: 6, padding: "6px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  };
}

const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 4, marginTop: 10 };
const inputStyle: React.CSSProperties = { width: "100%", padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, marginBottom: 6, boxSizing: "border-box" };

function StateMarkdown({ state }: { state: string }) {
  // 简单 Markdown 渲染
  const lines = state.split("\n");
  const elements: React.JSX.Element[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("## ")) {
      elements.push(<div key={i} style={{ fontWeight: 700, fontSize: 14, marginTop: 12, marginBottom: 4, color: "#374151" }}>{line.slice(3)}</div>);
      i++;
    } else if (line.startsWith("# ")) {
      elements.push(<div key={i} style={{ fontWeight: 700, fontSize: 16, marginBottom: 8, color: "#111827" }}>{line.slice(2)}</div>);
      i++;
    } else if (line.startsWith("- ")) {
      elements.push(<div key={i} style={{ paddingLeft: 12, color: "#4b5563", lineHeight: 1.6 }}>{line}</div>);
      i++;
    } else if (line.trim() === "") {
      elements.push(<div key={i} style={{ height: 8 }} />);
      i++;
    } else {
      elements.push(<div key={i} style={{ color: "#4b5563", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{line}</div>);
      i++;
    }
  }
  return <div style={{ fontFamily: "system-ui, sans-serif" }}>{elements}</div>;
}
