import { useRef, useEffect, useState } from "react";
import { useChatStore } from "./stores/chatStore";
import { useSSE } from "./hooks/useSSE";
import { NarrateBubble, SpeakBubble } from "./components/MessageBubble";
import { SceneDivider } from "./components/SceneDivider";
import type { NarrateData, SpeakData, SceneChangeData, InternalData } from "./types";

interface StoryInfo {
  story_id: string;
  name: string;
  description: string;
  user_character: string;
}

export default function App() {
  const { messages, isRunning, debug, toggleDebug, storyId, setStoryId, clearMessages, userTurn, userCharacter } =
    useChatStore();
  const { start, stop, submitSpeak } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [inputText, setInputText] = useState("");
  const [stories, setStories] = useState<StoryInfo[]>([]);

  useEffect(() => {
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
    // Load past history when storyId changes
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
              data: { speaker: m.speaker, content: m.content } as unknown,
            });
          });
        });
    }
  }, [storyId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
        return <SceneDivider key={msg.id} data={msg.data as SceneChangeData} />;
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

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif" }}>
      {/* Main Chat Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <div
          style={{
            padding: "12px 24px", borderBottom: "1px solid #e5e7eb",
            display: "flex", alignItems: "center", gap: 12, backgroundColor: "#fff",
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 16 }}>AINovelInDialogue</span>
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
          <button onClick={clearMessages} style={btnStyle("#6b7280")} disabled={isRunning}>Clear</button>
          <label style={{ fontSize: 13, marginLeft: "auto", cursor: "pointer", userSelect: "none" }}>
            <input type="checkbox" checked={debug} onChange={toggleDebug} style={{ marginRight: 4 }} />Debug
          </label>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflow: "auto", backgroundColor: "#fff" }}>
          {visibleMessages.length === 0 && (
            <div style={{ textAlign: "center", color: "#d1d5db", padding: 80, fontSize: 15 }}>
              {isRunning ? "Author is planning the episode..." : 'Press "Start" to begin the story'}
            </div>
          )}
          {visibleMessages.map(renderMessage)}
          <div ref={bottomRef} />
        </div>

        {/* User Input Bar — always visible */}
        <div style={{
          padding: "12px 24px", borderTop: `2px solid ${userTurn ? "#6366f1" : "#e5e7eb"}`,
          backgroundColor: userTurn ? "#f5f3ff" : "#f9fafb", display: "flex", gap: 10, alignItems: "flex-end"
        }}>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
            placeholder={userTurn ? `作为 ${userTurn.speaker} 发言...` : "等待你的回合..."}
            disabled={!userTurn}
            rows={3}
            style={{
              flex: 1, borderRadius: 8, border: "1px solid #d1d5db",
              padding: "8px 12px", fontSize: 14, resize: "none",
              opacity: userTurn ? 1 : 0.6,
            }}
            autoFocus={!!userTurn}
          />
          <button onClick={handleSubmit}
            disabled={!userTurn || !inputText.trim()}
            style={btnStyle(userTurn ? "#6366f1" : "#9ca3af")}>发送</button>
        </div>
      </div>

      {/* Right Panel: State or minimal status */}
      {userTurn && userTurn.state ? (
        <StatePanel state={userTurn.state} context={userTurn.context} />
      ) : (
        <MinimalStatus isRunning={isRunning} messages={messages} />
      )}
    </div>
  );
}

function btnStyle(color: string): React.CSSProperties {
  return {
    backgroundColor: color, color: "#fff", border: "none",
    borderRadius: 6, padding: "6px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  };
}

function MinimalStatus({ isRunning, messages }: { isRunning: boolean; messages: { type: string; data: unknown }[] }) {
  const lastInternal = [...messages].reverse().find((m) => m.type === "internal")?.data as InternalData | undefined;
  return (
    <div style={{ width: 200, borderLeft: "1px solid #e5e7eb", padding: 12, fontSize: 12, color: "#6b7280", overflow: "auto", backgroundColor: "#fafafa" }}>
      <div style={{ fontWeight: 600, marginBottom: 8, color: "#374151" }}>
        {isRunning ? "运行中..." : "就绪"}
      </div>
      {lastInternal && (
        <div style={{ lineHeight: 1.5 }}>
          <div style={{ color: "#8b5cf6" }}>{lastInternal.agent}</div>
          <div>{lastInternal.tool}</div>
        </div>
      )}
    </div>
  );
}

function StatePanel({ state, context }: { state: string; context: string }) {
  return (
    <div style={{
      width: 320, borderLeft: "1px solid #e5e7eb", overflow: "auto",
      padding: 16, backgroundColor: "#fafafa", fontSize: 13,
    }}>
      {context && (
        <div style={{
          marginBottom: 16, padding: "8px 12px",
          backgroundColor: "#ede9fe", borderRadius: 8, borderLeft: "3px solid #8b5cf6",
        }}>
          <div style={{ fontWeight: 700, color: "#7c3aed", marginBottom: 4 }}>导演提示</div>
          <div style={{ color: "#4c1d95", lineHeight: 1.5 }}>{context}</div>
        </div>
      )}
      <div style={{ fontWeight: 700, marginBottom: 8, color: "#374151" }}>当前状态</div>
      <pre style={{
        whiteSpace: "pre-wrap", fontFamily: "system-ui, sans-serif",
        lineHeight: 1.6, color: "#374151", margin: 0,
      }}>{state}</pre>
    </div>
  );
}
