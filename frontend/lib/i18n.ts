/**
 * Lightweight i18n. EN + ID translations.
 */

import type { Language } from "./types";

export const translations = {
  en: {
    welcome: "Hello! I'm Javva.",
    subtitle: "Your AI trading support assistant",
    inputPlaceholder: "Type your message...",
    send: "Send",
    thinking: "Javva is thinking...",
    errorGeneric: "Something went wrong. Please try again.",
    errorNetwork: "Cannot connect to server. Is the backend running?",
    clearChat: "Clear chat",
    newChat: "New chat",
    darkMode: "Dark mode",
    lightMode: "Light mode",
    suggestions: {
      withdraw: "How do I withdraw money?",
      kyc: "What is KYC?",
      balance: "Check my balance",
      help: "I need help",
    },
  },
  id: {
    welcome: "Halo! Saya Javva.",
    subtitle: "Asisten AI dukungan trading Anda",
    inputPlaceholder: "Ketik pesan Anda...",
    send: "Kirim",
    thinking: "Javva sedang berpikir...",
    errorGeneric: "Terjadi kesalahan. Silakan coba lagi.",
    errorNetwork: "Tidak dapat terhubung ke server. Apakah backend berjalan?",
    clearChat: "Bersihkan chat",
    newChat: "Chat baru",
    darkMode: "Mode gelap",
    lightMode: "Mode terang",
    suggestions: {
      withdraw: "Bagaimana cara menarik uang?",
      kyc: "Apa itu KYC?",
      balance: "Cek saldo saya",
      help: "Saya butuh bantuan",
    },
  },
} as const;

export type TranslationKey = string;

export function t(lang: Language, key: TranslationKey): string {
  const keys = key.split(".");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let result: any = translations[lang];
  for (const k of keys) {
    if (result === undefined || result === null) return key;
    result = result[k];
  }
  return typeof result === "string" ? result : key;
}
