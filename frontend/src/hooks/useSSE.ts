import { useEffect, useRef } from "react";
import { useChatStore } from "../stores/chatStore";
import type { ChatMessage, UserTurnData } from "../types";

export function useSSE() {
  const { storyId, addMessage, setRunning, isRunning, setUserTurn } = useChatStore();
  const sourceRef = useRef<EventSource | null>(null);

  const start = (userCharacter?: string) => {
    if (sourceRef.current) return;

    let url = `/api/stream/${storyId}?debug=true`;
    url += `&user_character=${encodeURIComponent(userCharacter || "__none__")}`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("session_start", () => {
      setRunning(true);
    });

    const eventTypes = ["narrate", "speak", "episode_change", "internal", "session_end", "llm_token", "system_prompt", "user_message"];

    eventTypes.forEach((type) => {
      es.addEventListener(type, (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        const msg: ChatMessage = {
          id: "",
          type: type as ChatMessage["type"],
          timestamp: Date.now(),
          data,
        };
        addMessage(msg);

        if (type === "session_end") {
          setRunning(false);
          es.close();
          sourceRef.current = null;
        }
      });
    });

    // 用户回合
    es.addEventListener("user_turn", (e: MessageEvent) => {
      const data = JSON.parse(e.data) as UserTurnData;
      setUserTurn(data);
    });

    es.onerror = () => {
      setRunning(false);
      es.close();
      sourceRef.current = null;
    };
  };

  const stop = () => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setRunning(false);
  };

  const submitSpeak = async (text: string) => {
    await fetch(`/api/speak/${storyId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    setUserTurn(null);
  };

  useEffect(() => {
    return () => {
      sourceRef.current?.close();
    };
  }, []);

  return { start, stop, isRunning, submitSpeak };
}
