"use client";

import { Trash2 } from "lucide-react";
import { LanguageToggle } from "./LanguageToggle";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n";
import type { Language } from "@/lib/types";

interface HeaderProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
  onClearChat: () => void;
  hasMessages: boolean;
}

export function Header({
  language,
  onLanguageChange,
  onClearChat,
  hasMessages,
}: HeaderProps) {
  return (
    <header
      className="sticky top-0 z-10 border-b backdrop-blur-md"
      style={{
        backgroundColor:
          "color-mix(in srgb, var(--javva-bg) 80%, transparent)",
        borderColor: "var(--javva-border)",
      }}
    >
      <div className="max-w-[800px] mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white"
            style={{ backgroundColor: "var(--javva-primary)" }}
          >
            J
          </div>
          <h1
            className="text-lg font-semibold"
            style={{ color: "var(--javva-text)" }}
          >
            Javva
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {hasMessages && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearChat}
              title={t(language, "clearChat")}
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          )}
          <LanguageToggle language={language} onChange={onLanguageChange} />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
