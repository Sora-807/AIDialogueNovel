import type { SceneChangeData } from "../types";

export function SceneDivider({ data }: { data: SceneChangeData }) {
  const label =
    data.state === "episode_created"
      ? `[开始] ${data.episode_name || `Ep ${data.episode_id}`}`
      : `[结束] ${data.episode_name || `Ep ${data.episode_id}`}`;

  const color = data.state === "episode_created" ? "#6366f1" : "#9ca3af";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "20px 24px",
      }}
    >
      <div style={{ flex: 1, height: 1, backgroundColor: color, opacity: 0.3 }} />
      <span
        style={{
          fontSize: 13,
          fontWeight: 600,
          color,
          whiteSpace: "nowrap",
          letterSpacing: 1,
        }}
      >
        {label}
      </span>
      <div style={{ flex: 1, height: 1, backgroundColor: color, opacity: 0.3 }} />
    </div>
  );
}
