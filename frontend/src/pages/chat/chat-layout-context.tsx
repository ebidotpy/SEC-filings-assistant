import { createContext, useContext } from "react";

import type { ThreadSummary } from "@/lib/chat";

export type ChatLayoutContextValue = {
  threads: ThreadSummary[];
  threadsLoading: boolean;
  threadsError: string | null;
  refreshThreads: () => Promise<void>;
  createNewThread: (initialPrompt?: string) => Promise<void>;
  creatingThread: boolean;
};

export const ChatLayoutContext = createContext<ChatLayoutContextValue | null>(
  null,
);

export function useChatLayout(): ChatLayoutContextValue {
  const context = useContext(ChatLayoutContext);

  if (!context) {
    throw new Error("useChatLayout must be used within ChatLayoutPage");
  }

  return context;
}
