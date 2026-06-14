import { create } from "zustand";
import type { ChatMessage, UserTurnData } from "../types";

interface ChatState {
  messages: ChatMessage[];
  isRunning: boolean;
  debug: boolean;
  storyId: string;
  userTurn: UserTurnData | null;
  /** 持久化的用户角色名（首次 user_turn 时设置） */
  userCharacter: string;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  setRunning: (v: boolean) => void;
  toggleDebug: () => void;
  setStoryId: (id: string) => void;
  setUserTurn: (data: UserTurnData | null) => void;
}

let _nextId = 0;
function nextId() {
  return `msg_${++_nextId}_${Date.now()}`;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isRunning: false,
  debug: true,
  storyId: "",
  userTurn: null,
  userCharacter: "",

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, { ...msg, id: msg.id || nextId() }] })),

  clearMessages: () => set({ messages: [] }),

  setRunning: (v) => set({ isRunning: v }),

  toggleDebug: () => set((s) => ({ debug: !s.debug })),

  setStoryId: (id) => set({ storyId: id }),

  setUserTurn: (data) => set((s) => ({
    userTurn: data,
    userCharacter: data ? data.speaker : s.userCharacter,
  })),
}));
