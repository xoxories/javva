"use client";

import { motion } from "framer-motion";
import { Wallet, ShieldCheck, BarChart3, HelpCircle } from "lucide-react";
import type { Language, SuggestionChip } from "@/lib/types";

const SUGGESTIONS: SuggestionChip[] = [
  {
    id: "withdraw",
    icon: "wallet",
    labelEn: "How do I withdraw money?",
    labelId: "Bagaimana cara menarik uang?",
    prompt: "How do I withdraw money?",
  },
  {
    id: "kyc",
    icon: "shield",
    labelEn: "What is KYC?",
    labelId: "Apa itu KYC?",
    prompt: "What is KYC and why is it required?",
  },
  {
    id: "balance",
    icon: "chart",
    labelEn: "Check my balance",
    labelId: "Cek saldo saya",
    prompt: "How can I check my account balance?",
  },
  {
    id: "help",
    icon: "help",
    labelEn: "I need help",
    labelId: "Saya butuh bantuan",
    prompt: "I need help with my account",
  },
];

const ICON_MAP = {
  wallet: Wallet,
  shield: ShieldCheck,
  chart: BarChart3,
  help: HelpCircle,
};

interface SuggestionChipsProps {
  language: Language;
  onSelect: (prompt: string) => void;
}

export function SuggestionChips({ language, onSelect }: SuggestionChipsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-md">
      {SUGGESTIONS.map((suggestion, index) => {
        const Icon = ICON_MAP[suggestion.icon as keyof typeof ICON_MAP];
        const label =
          language === "en" ? suggestion.labelEn : suggestion.labelId;

        return (
          <motion.button
            key={suggestion.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.05 }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSelect(suggestion.prompt)}
            className="flex items-center gap-3 p-4 rounded-xl border text-left text-sm transition-colors hover:border-[color:var(--javva-primary)]"
            style={{
              borderColor: "var(--javva-border)",
              backgroundColor: "var(--javva-surface)",
              color: "var(--javva-text)",
            }}
          >
            <Icon
              className="w-5 h-5 flex-shrink-0"
              style={{ color: "var(--javva-primary)" }}
            />
            <span>{label}</span>
          </motion.button>
        );
      })}
    </div>
  );
}
