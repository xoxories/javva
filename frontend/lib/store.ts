/**
 * Conversation history persistence via localStorage.
 */

import type { ChatSession, Message } from "./types";

const STORAGE_KEY = "javva_chat_session";
const TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

export function loadSession(): ChatSession | null {
  if (typeof window === "undefined") return null;
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return null;
    const session = JSON.parse(data) as ChatSession;
    if (Date.now() - session.lastActiveAt > TTL_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(session: ChatSession): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch (e) {
    console.error("Failed to save session:", e);
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

export function createMessage(
  role: "user" | "assistant",
  content: string,
  extras?: Partial<Message>,
): Message {
  return {
    id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
    role,
    content,
    timestamp: Date.now(),
    ...extras,
  };
}
