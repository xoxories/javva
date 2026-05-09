"use client";

import { motion } from "framer-motion";
import { SuggestionChips } from "./SuggestionChips";
import { t } from "@/lib/i18n";
import type { Language } from "@/lib/types";

interface WelcomeScreenProps {
  language: Language;
  onSelectSuggestion: (prompt: string) => void;
}

export function WelcomeScreen({
  language,
  onSelectSuggestion,
}: WelcomeScreenProps) {
  return (
    <motion.div
      className="flex-1 flex flex-col items-center justify-center text-center py-8"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold text-white mb-6"
        style={{ backgroundColor: "var(--javva-primary)" }}
      >
        J
      </div>

      <h1
        className="text-3xl font-bold mb-2"
        style={{ color: "var(--javva-text)" }}
      >
        {t(language, "welcome")}
      </h1>

      <p
        className="text-base mb-8"
        style={{ color: "var(--javva-text-secondary)" }}
      >
        {t(language, "subtitle")}
      </p>

      <SuggestionChips language={language} onSelect={onSelectSuggestion} />
    </motion.div>
  );
}
