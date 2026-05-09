"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n";
import type { Language } from "@/lib/types";

interface ChatInputProps {
  language: Language;
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ language, onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      className="flex items-end gap-2 p-2 rounded-2xl border"
      style={{
        backgroundColor: "var(--javva-surface)",
        borderColor: "var(--javva-border)",
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t(language, "inputPlaceholder")}
        disabled={disabled}
        rows={1}
        className="flex-1 bg-transparent border-0 outline-none resize-none px-3 py-2 text-sm"
        style={{
          color: "var(--javva-text)",
          maxHeight: "200px",
        }}
      />
      <Button
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        size="icon"
        className="rounded-xl flex-shrink-0"
        style={{
          backgroundColor: "var(--javva-primary)",
          color: "white",
        }}
      >
        <Send className="w-4 h-4" />
      </Button>
    </div>
  );
}
