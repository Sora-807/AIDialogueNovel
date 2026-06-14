export interface NarrateData {
  speaker: string;
  content: string;
}

export interface SpeakData {
  speaker: string;
  content: string;
}

export interface EpisodeChangeData {
  episode_name: string;
  episode_id: number;
  state: "episode_created" | "episode_ended";
}

export interface InternalData {
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  result: string;
  is_invalid: boolean;
}

export interface SessionEndData {
  story_id: string;
  total_scenes: number;
}

export interface ChatMessage {
  id: string;
  type: "narrate" | "speak" | "episode_change" | "internal" | "session_end" | "llm_token" | "system_prompt" | "user_message";
  timestamp: number;
  data: NarrateData | SpeakData | EpisodeChangeData | InternalData | SessionEndData | LlmTokenData | SystemPromptData | UserMessageData;
}

export interface LlmTokenData {
  agent: string;
  text: string;
}

export interface SystemPromptData {
  agent: string;
  text: string;
}
export interface UserMessageData {
  agent: string;
  text: string;
}

export interface UserTurnData {
  speaker: string;
  state: string;
  context: string;
  history: string;
}
