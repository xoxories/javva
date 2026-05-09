"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Header } from "@/components/layout/Header";
import { WelcomeScreen } from "./WelcomeScreen";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { TypingIndicator } from "./TypingIndicator";
import { sendMessage } from "@/lib/api";
import {
  loadSession,
  saveSession,
  clearSession,
  createMessage,
} from "@/lib/store";
import { t } from "@/lib/i18n";
import type { Message, Language } from "@/lib/types";

export function ChatContainer() {
  const [language, setLanguage] = useState<Language>("en");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (session) {
      setMessages(session.messages);
      setSessionId(session.sessionId);
    }
  }, []);

  useEffect(() => {
    if (messages.length === 0 || !sessionId) return;
    saveSession({
      sessionId,
      messages,
      createdAt: messages[0]?.timestamp ?? Date.now(),
      lastActiveAt: Date.now(),
    });
  }, [messages, sessionId]);

  const handleSend = useCallback(
    async (userMessage: string) => {
      if (!userMessage.trim() || isLoading) return;

      setError(null);
      const userMsg = createMessage("user", userMessage.trim());
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      abortControllerRef.current?.abort();
      abortControllerRef.current = new AbortController();

      try {
        const response = await sendMessage(
          { message: userMessage, session_id: sessionId },
          abortControllerRef.current.signal,
        );

        setSessionId(response.session_id);

        const assistantMsg = createMessage("assistant", response.reply, {
          toolsCalled: response.tools_called,
          durationMs: response.duration_ms,
          error: response.error,
        });

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") return;
        const errorMsg =
          e instanceof Error ? e.message : t(language, "errorGeneric");
        setError(errorMsg);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, isLoading, language],
  );

  const handleClearChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    clearSession();
  }, []);

  const isEmpty = messages.length === 0;

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--javva-bg)" }}
    >
      <Header
        language={language}
        onLanguageChange={setLanguage}
        onClearChat={handleClearChat}
        hasMessages={!isEmpty}
      />

      <main className="flex-1 flex flex-col max-w-[800px] mx-auto w-full px-4">
        {isEmpty ? (
          <WelcomeScreen
            language={language}
            onSelectSuggestion={handleSend}
          />
        ) : (
          <MessageList messages={messages} language={language} />
        )}

        {isLoading && <TypingIndicator language={language} />}

        {error && (
          <div
            className="mx-4 mb-4 p-3 rounded-lg text-sm"
            style={{
              backgroundColor: "rgb(239 68 68 / 0.1)",
              color: "rgb(239 68 68)",
            }}
          >
            {error}
          </div>
        )}
      </main>

      <div
        className="sticky bottom-0 max-w-[800px] mx-auto w-full px-4 pb-4"
        style={{ backgroundColor: "var(--javva-bg)" }}
      >
        <ChatInput
          language={language}
          onSend={handleSend}
          disabled={isLoading}
        />
      </div>
    </div>
  );
}
