import type { NarrateData, SpeakData } from "../types";

const AVATARS: Record<string, string> = {};
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
  return `hsl(${h}, 50%, 50%)`;
}

function Avatar({ name, isUser }: { name: string; isUser?: boolean }) {
  const color = avatarColor(name);
  const letter = AVATARS[name] || name[0];
  return (
    <div
      style={{
        width: 36, height: 36, borderRadius: "50%",
        backgroundColor: color, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 600, flexShrink: 0,
        border: isUser ? "2px solid #6366f1" : undefined,
      }}
    >
      {letter}
    </div>
  );
}

function Bubble({
  speaker, content, isNarrator, isUser,
}: {
  speaker: string; content: string; isNarrator: boolean; isUser?: boolean;
}) {
  if (isNarrator) {
    return (
      <div style={{
        textAlign: "center", color: "#9ca3af", fontSize: 14,
        fontStyle: "italic", padding: "12px 60px", lineHeight: 1.8,
      }}>
        {content}
      </div>
    );
  }

  // User: right-aligned
  if (isUser) {
    return (
      <div style={{
        display: "flex", gap: 12, padding: "8px 24px",
        alignItems: "flex-start", flexDirection: "row-reverse",
      }}>
        <Avatar name={speaker} isUser />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <div style={{
            fontSize: 12, color: "#6366f1", fontWeight: 600, marginBottom: 4,
          }}>
            {speaker}
          </div>
          <div style={{
            backgroundColor: "#eef2ff", borderRadius: "12px 0 12px 12px",
            padding: "10px 16px", fontSize: 14, lineHeight: 1.7,
            whiteSpace: "pre-wrap", maxWidth: "70%",
          }}>
            {content}
          </div>
        </div>
      </div>
    );
  }

  // Others: left-aligned
  return (
    <div style={{
      display: "flex", gap: 12, padding: "8px 24px", alignItems: "flex-start",
    }}>
      <Avatar name={speaker} />
      <div style={{ flex: 1 }}>
        <div style={{
          fontSize: 12, color: avatarColor(speaker), fontWeight: 600, marginBottom: 4,
        }}>
          {speaker}
        </div>
        <div style={{
          backgroundColor: "#f3f4f6", borderRadius: "0 12px 12px 12px",
          padding: "10px 16px", fontSize: 14, lineHeight: 1.7,
          whiteSpace: "pre-wrap", maxWidth: "70%",
        }}>
          {content}
        </div>
      </div>
    </div>
  );
}

export function NarrateBubble({ data }: { data: NarrateData }) {
  return <Bubble speaker="Narrator" content={data.content} isNarrator />;
}

export function SpeakBubble({ data, isUser }: { data: SpeakData; isUser?: boolean }) {
  return <Bubble speaker={data.speaker} content={data.content} isNarrator={false} isUser={isUser} />;
}
