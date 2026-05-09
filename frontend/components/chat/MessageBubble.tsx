"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ToolBadge } from "./ToolBadge";
import type { Message, Language } from "@/lib/types";

interface MessageBubbleProps {
  message: Message;
  language: Language;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
    >
      {!isUser && (
        <div className="flex items-center gap-2 mb-1">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-white"
            style={{ backgroundColor: "var(--javva-primary)" }}
          >
            J
          </div>
          <span
            className="text-xs"
            style={{ color: "var(--javva-text-secondary)" }}
          >
            Javva
          </span>
        </div>
      )}

      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
          isUser ? "rounded-tr-sm" : "rounded-tl-sm border"
        }`}
        style={{
          backgroundColor: isUser
            ? "var(--javva-user-bubble)"
            : "var(--javva-surface)",
          color: isUser ? "white" : "var(--javva-text)",
          borderColor: !isUser ? "var(--javva-border)" : undefined,
        }}
      >
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>

        {!isUser &&
          message.toolsCalled &&
          message.toolsCalled.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {message.toolsCalled.map((tool, idx) => (
                <ToolBadge
                  key={idx}
                  tool={tool}
                  durationMs={message.durationMs}
                />
              ))}
            </div>
          )}
      </div>

      <span
        className="text-xs mt-1 px-2"
        style={{ color: "var(--javva-text-secondary)" }}
      >
        {time}
      </span>
    </motion.div>
  );
}
