/**
 * TypeScript types for Javva chat application.
 */

export type Language = "en" | "id";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  toolsCalled?: string[];
  durationMs?: number;
  error?: string | null;
}

export interface ChatSession {
  sessionId: string;
  messages: Message[];
  createdAt: number;
  lastActiveAt: number;
}

export interface SendMessageRequest {
  message: string;
  session_id: string | null;
}

export interface SendMessageResponse {
  reply: string;
  session_id: string;
  turn_number: number;
  tools_called: string[];
  duration_ms: number;
  error: string | null;
}

export interface SuggestionChip {
  id: string;
  icon: string;
  labelEn: string;
  labelId: string;
  prompt: string;
}
