import { useState, useRef, useEffect, useMemo } from "react";
import { useChatStore } from "../stores/chatStore";
import type { InternalData, LlmTokenData } from "../types";

// ── status bar ──

function StatusBar() {
  const { messages, isRunning } = useChatStore();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!isRunning) { setElapsed(0); return; }
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  const internals = messages.filter((m) => m.type === "internal");
  const last = internals[internals.length - 1]?.data as InternalData | undefined;

  let status = "Idle";
  let color = "#9ca3af";

  if (isRunning) {
    if (!last) {
      if (elapsed < 3) status = "SSE connected...";
      else status = `Waiting... (${elapsed}s)`;
      color = "#f59e0b";
    } else {
      status = `${last.agent}: ${last.tool}`;
      if (last.agent === "Author") color = "#8b5cf6";
      else if (last.agent === "Narrator") color = "#6366f1";
      else color = "#10b981";
      if (last.is_invalid) { status += " [INVALID]"; color = "#ef4444"; }
    }
  }

  const episodeChanges = messages.filter((m) => m.type === "episode_change");
  const currentEpisode = episodeChanges.length > 0
    ? (episodeChanges[episodeChanges.length - 1].data as { episode_name?: string })?.episode_name
    : null;

  return (
    <div style={{ padding: "8px 16px", borderBottom: "1px solid #e5e7eb", fontSize: 12, display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: isRunning ? "#10b981" : "#d1d5db", flexShrink: 0 }} />
      <span style={{ color, fontWeight: 600 }}>{status}</span>
      {isRunning && <span style={{ color: "#9ca3af" }}>{elapsed}s</span>}
      {currentEpisode && <span style={{ color: "#9ca3af", marginLeft: "auto" }}>{currentEpisode}</span>}
    </div>
  );
}

// ── thinking stream ──

function ThinkingStream() {
  const { messages } = useChatStore();
  const tokens = messages.filter((m) => m.type === "llm_token") as { data: LlmTokenData }[];
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tokens.length]);

  if (tokens.length === 0) return null;

  // Group tokens by agent, tracking when agent changes → new paragraph
  let currentAgent = "";
  const paragraphs: { agent: string; text: string }[] = [];

  for (const t of tokens) {
    const d = t.data as LlmTokenData;
    if (d.agent !== currentAgent) {
      currentAgent = d.agent;
      paragraphs.push({ agent: d.agent, text: d.text });
    } else {
      paragraphs[paragraphs.length - 1].text += d.text;
    }
  }

  return (
    <div
      style={{
        margin: "8px 0",
        padding: "8px 10px",
        backgroundColor: "#f0f4ff",
        borderRadius: 6,
        fontSize: 11,
        fontFamily: "monospace",
        color: "#4338ca",
        whiteSpace: "pre-wrap",
        lineHeight: 1.5,
        maxHeight: 240,
        overflow: "auto",
      }}
    >
      <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>
        thinking [{paragraphs[paragraphs.length - 1]?.agent || currentAgent}]...
      </div>
      {paragraphs[paragraphs.length - 1]?.text.slice(-2000)}
      <div ref={bottomRef} />
    </div>
  );
}

// ── tool call row ──

function InternalRow({ data, index }: { data: InternalData; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const invalid = data.is_invalid;

  return (
    <div style={{ fontSize: 12, fontFamily: "monospace", borderBottom: "1px solid #e5e7eb", padding: "4px 0" }}>
      <div onClick={() => setExpanded(!expanded)} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: invalid ? "#ef4444" : "#374151" }}>
        <span style={{ color: "#9ca3af", minWidth: 20, fontSize: 11 }}>#{index}</span>
        <span style={{ backgroundColor: invalid ? "#fef2f2" : "#dbeafe", color: invalid ? "#dc2626" : "#2563eb", padding: "1px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600 }}>
          {data.agent}
        </span>
        <span style={{ fontWeight: 600, fontSize: 11 }}>{data.tool}{invalid ? " [INVALID]" : ""}</span>
      </div>
      {expanded && (
        <div style={{ marginLeft: 26, marginTop: 4, padding: 8, backgroundColor: "#f9fafb", borderRadius: 4, fontSize: 11, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
          <div style={{ color: "#6b7280", marginBottom: 4 }}>args: {JSON.stringify(data.args)}</div>
          <div style={{ color: invalid ? "#ef4444" : "#059669" }}>{data.result}</div>
        </div>
      )}
    </div>
  );
}

// ── debug panel ──

export function DebugPanel() {
  const { messages, debug } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  const allEvents = useMemo(() =>
    messages.filter((m) =>
      m.type === "internal" ||
      m.type === "session_end" || m.type === "episode_change"
    ),
    [messages]
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [allEvents.length]);

  return (
    <div style={{ width: 440, borderLeft: "1px solid #e5e7eb", backgroundColor: "#fafafa", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <StatusBar />
      <div style={{ flex: 1, overflow: "auto", padding: "6px 12px" }}>
        {/* Live thinking stream — always visible when tokens are flowing */}
        <ThinkingStream />

        {debug ? (
          allEvents.length > 0 ? (
            <>
              {allEvents.map((m, i) => {
                if (m.type === "internal") {
                  return <InternalRow key={m.id} data={m.data as InternalData} index={i + 1} />;
                }
                const data = m.data as unknown as Record<string, unknown>;
                return (
                  <div key={m.id} style={{ fontSize: 11, color: "#9ca3af", padding: "2px 0", fontFamily: "monospace" }}>
                    [{m.type}] {JSON.stringify(data)}
                  </div>
                );
              })}
            </>
          ) : (
            <div style={{ color: "#d1d5db", fontSize: 12, textAlign: "center", padding: 40 }}>
              {messages.length > 0 ? "Waiting for tool calls..." : "Press Start..."}
            </div>
          )
        ) : (
          <div style={{ color: "#9ca3af", fontSize: 11, textAlign: "center", padding: 20 }}>
            Enable Debug to see details
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
