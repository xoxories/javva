"use client";

import { motion } from "framer-motion";
import { t } from "@/lib/i18n";
import type { Language } from "@/lib/types";

interface TypingIndicatorProps {
  language: Language;
}

export function TypingIndicator({ language }: TypingIndicatorProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex items-center gap-3 py-3 px-4"
    >
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-white"
        style={{ backgroundColor: "var(--javva-primary)" }}
      >
        J
      </div>

      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: "var(--javva-primary)" }}
              animate={{ scale: [1, 1.4, 1], opacity: [0.5, 1, 0.5] }}
              transition={{
                duration: 1,
                repeat: Infinity,
                delay: i * 0.15,
              }}
            />
          ))}
        </div>
        <span
          className="text-sm"
          style={{ color: "var(--javva-text-secondary)" }}
        >
          {t(language, "thinking")}
        </span>
      </div>
    </motion.div>
  );
}
