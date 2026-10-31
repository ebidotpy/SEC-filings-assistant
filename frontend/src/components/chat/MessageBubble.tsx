import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type MessageBubbleProps = {
  role: "user" | "assistant";
  children: ReactNode;
  footer?: ReactNode;
};

function AssistantMark() {
  return (
    <span
      aria-hidden
      className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-foreground font-mono text-[0.7rem] font-medium text-background"
    >
      [d]
    </span>
  );
}

export function MessageBubble({ role, children, footer }: MessageBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <AssistantMark />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div
          className={cn(
            "max-w-full rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3",
            "text-sm leading-relaxed whitespace-pre-wrap text-card-foreground",
          )}
        >
          {children}
        </div>
        {footer}
      </div>
    </div>
  );
}
