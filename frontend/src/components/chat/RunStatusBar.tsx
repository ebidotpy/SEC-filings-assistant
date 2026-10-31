import type { ChatStatus, UIMessage } from "ai";

import { ThinkingDots } from "@/components/common/ThinkingDots";
import { getLatestRunStatus, getMessageText } from "@/lib/citations";

type RunStatusBarProps = {
  messages: UIMessage[];
  status: ChatStatus;
};

export function RunStatusBar({ messages, status }: RunStatusBarProps) {
  if (status !== "submitted" && status !== "streaming") {
    return null;
  }

  const lastMessage = messages.at(-1);
  if (lastMessage?.role === "assistant" && getMessageText(lastMessage) !== "") {
    return null;
  }

  const statusMessage =
    lastMessage?.role === "assistant" ? getLatestRunStatus(lastMessage) : null;

  return (
    <div className="mx-auto flex w-full max-w-3xl items-center gap-3 px-4 pb-3">
      <span
        aria-hidden
        className="flex size-7 shrink-0 items-center justify-center rounded-md bg-foreground font-mono text-[0.7rem] font-medium text-background"
      >
        [d]
      </span>
      <span className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <ThinkingDots />
        {statusMessage ?? "Thinking…"}
      </span>
    </div>
  );
}
