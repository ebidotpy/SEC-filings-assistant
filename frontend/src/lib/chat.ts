import { api } from "@/lib/api";
import type { Citation } from "@/lib/citations";

export type ThreadSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type ChatUIMessagePart = {
  type: string;
  text?: string;
  data?: {
    citations?: Citation[];
    message?: string;
  };
};

export type ChatUIMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  parts: ChatUIMessagePart[];
};

export function listThreads(): Promise<ThreadSummary[]> {
  return api.get<ThreadSummary[]>("/chat/threads");
}

export function createThread(title?: string): Promise<ThreadSummary> {
  return api.post<ThreadSummary>(
    "/chat/threads",
    title ? { title } : undefined,
  );
}

export function loadThreadMessages(threadId: string): Promise<ChatUIMessage[]> {
  return api.get<ChatUIMessage[]>(`/chat/threads/${threadId}/messages`);
}
