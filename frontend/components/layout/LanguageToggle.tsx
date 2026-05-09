"use client";

import { Button } from "@/components/ui/button";
import type { Language } from "@/lib/types";

interface LanguageToggleProps {
  language: Language;
  onChange: (lang: Language) => void;
}

export function LanguageToggle({ language, onChange }: LanguageToggleProps) {
  return (
    <div
      className="flex rounded-md border"
      style={{ borderColor: "var(--javva-border)" }}
    >
      <Button
        variant={language === "en" ? "default" : "ghost"}
        size="sm"
        onClick={() => onChange("en")}
        className="rounded-r-none px-3 text-xs"
        style={
          language === "en"
            ? { backgroundColor: "var(--javva-primary)", color: "white" }
            : {}
        }
      >
        EN
      </Button>
      <Button
        variant={language === "id" ? "default" : "ghost"}
        size="sm"
        onClick={() => onChange("id")}
        className="rounded-l-none px-3 text-xs"
        style={
          language === "id"
            ? { backgroundColor: "var(--javva-primary)", color: "white" }
            : {}
        }
      >
        ID
      </Button>
    </div>
  );
}
