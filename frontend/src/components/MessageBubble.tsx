import type { NarrateData, SpeakData } from "../types";

const COLORS: Record<string, string> = {
  Narrator: "#6b7280",
};

function avatarColor(name: string): string {
  return COLORS[name] || stringToColor(name);
}

function stringToColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 50%, 42%)`;
}

function Avatar({ name, isUser }: { name: string; isUser?: boolean }) {
  const color = avatarColor(name);
  const letter = name[0];
  return (
    <div
      style={{
        width: 34, height: 34, borderRadius: "50%",
        backgroundColor: color, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700, flexShrink: 0,
        border: isUser ? "2px solid #6366f1" : undefined,
      }}
    >
      {letter}
    </div>
  );
}

function NarratorBubble({ content }: { content: string }) {
  return (
    <div style={{
      display: "flex", justifyContent: "center", padding: "10px 24px",
    }}>
      <div style={{
        backgroundColor: "#f3f4f6", borderRadius: 10,
        padding: "10px 20px", fontSize: 14, lineHeight: 1.8,
        color: "#4b5563", whiteSpace: "pre-wrap",
        maxWidth: "75%", textAlign: "center",
      }}>
        {content}
      </div>
    </div>
  );
}

function CharacterBubble({ speaker, content, isUser }: { speaker: string; content: string; isUser?: boolean }) {
  const color = avatarColor(speaker);

  if (isUser) {
    return (
      <div style={{
        display: "flex", gap: 10, padding: "8px 24px",
        alignItems: "flex-start", flexDirection: "row-reverse",
      }}>
        <Avatar name={speaker} isUser />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", maxWidth: "70%" }}>
          <div style={{ fontSize: 12, color: "#6366f1", fontWeight: 600, marginBottom: 4 }}>
            {speaker}
          </div>
          <div style={{
            backgroundColor: "#eef2ff", borderRadius: "12px 0 12px 12px",
            padding: "10px 14px", fontSize: 14, lineHeight: 1.7,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: "flex", gap: 10, padding: "8px 24px", alignItems: "flex-start",
    }}>
      <Avatar name={speaker} />
      <div style={{ display: "flex", flexDirection: "column", maxWidth: "70%" }}>
        <div style={{ fontSize: 12, color, fontWeight: 600, marginBottom: 4 }}>
          {speaker}
        </div>
        <div style={{
          backgroundColor: "#f3f4f6", borderRadius: "0 12px 12px 12px",
          padding: "10px 14px", fontSize: 14, lineHeight: 1.7,
          whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>
          {content}
        </div>
      </div>
    </div>
  );
}

export function NarrateBubble({ data }: { data: NarrateData }) {
  return <NarratorBubble content={data.content} />;
}

export function SpeakBubble({ data, isUser }: { data: SpeakData; isUser?: boolean }) {
  return <CharacterBubble speaker={data.speaker} content={data.content} isUser={isUser} />;
}
