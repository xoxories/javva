"use client";

import {
  Search,
  User,
  Receipt,
  ShieldCheck,
  AlertCircle,
  type LucideIcon,
} from "lucide-react";

const TOOL_META: Record<string, { icon: LucideIcon; label: string }> = {
  search_faqs_tool: { icon: Search, label: "FAQ Search" },
  lookup_account_tool: { icon: User, label: "Account Lookup" },
  list_transactions_tool: { icon: Receipt, label: "Transactions" },
  check_kyc_status_tool: { icon: ShieldCheck, label: "KYC Check" },
  escalate_to_human_tool: { icon: AlertCircle, label: "Escalation" },
};

interface ToolBadgeProps {
  tool: string;
  durationMs?: number;
}

export function ToolBadge({ tool, durationMs }: ToolBadgeProps) {
  const meta = TOOL_META[tool] ?? { icon: Search, label: tool };
  const Icon = meta.icon;

  return (
    <div
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs"
      style={{
        backgroundColor:
          "color-mix(in srgb, var(--javva-primary) 15%, transparent)",
        color: "var(--javva-primary)",
        border:
          "1px solid color-mix(in srgb, var(--javva-primary) 30%, transparent)",
      }}
    >
      <Icon className="w-3 h-3" />
      <span className="font-medium">{meta.label}</span>
      {durationMs && (
        <span style={{ color: "var(--javva-text-secondary)" }}>
          · {(durationMs / 1000).toFixed(1)}s
        </span>
      )}
    </div>
  );
}
