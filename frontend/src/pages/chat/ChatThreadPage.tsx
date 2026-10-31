import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";

import { ChatErrorBanner } from "@/components/chat/ChatErrorBanner";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { RunStatusBar } from "@/components/chat/RunStatusBar";
import { SourceSheet } from "@/components/chat/SourceSheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { accessToken } from "@/lib/auth-token";
import { loadThreadMessages, type ChatUIMessage } from "@/lib/chat";
import type { Citation } from "@/lib/citations";
import { env } from "@/lib/env";
import { ApiError } from "@/lib/http";
import { useChatLayout } from "@/pages/chat/chat-layout-context";

type ChatThreadViewProps = {
  threadId: string;
  initialMessages: ChatUIMessage[];
  initialPrompt?: string;
};

function streamErrorMessage(error: Error): string {
  if (error.message) {
    return error.message;
  }
  return "Something went wrong while generating a response.";
}

function historyLoadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "Your session has expired. Please sign in again.";
    }
    if (error.status === 403) {
      return "You do not have access to this conversation.";
    }
    if (error.status === 404) {
      return "This conversation could not be found.";
    }
    if (error.isNetworkError) {
      return "Could not reach the server. Check your connection and try again.";
    }
    return error.message;
  }

  return "Could not load message history.";
}

function ChatThreadView({
  threadId,
  initialMessages,
  initialPrompt,
}: ChatThreadViewProps) {
  const { refreshThreads } = useChatLayout();
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(
    null,
  );
  const autoSent = useRef(false);

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        headers: async (): Promise<Record<string, string>> => {
          const token = await accessToken();
          const headers: Record<string, string> = {};
          if (token) {
            headers.Authorization = `Bearer ${token}`;
          }
          return headers;
        },
        prepareSendMessagesRequest: ({ id, messages }) => ({
          body: { threadId: id, messages },
        }),
      }),
    [],
  );

  const { messages, sendMessage, status, error, clearError } = useChat({
    id: threadId,
    messages: initialMessages as UIMessage[],
    transport,
    onFinish: () => {
      void refreshThreads();
    },
  });

  const isBusy = status === "streaming" || status === "submitted";

  function handleSend(text: string) {
    setSelectedCitation(null);
    void sendMessage({ text });
  }

  useEffect(() => {
    if (autoSent.current || !initialPrompt || messages.length > 0) {
      return;
    }
    autoSent.current = true;
    void sendMessage({ text: initialPrompt });
  }, [initialPrompt, messages.length, sendMessage]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <MessageList
        messages={messages}
        selectedCitation={selectedCitation}
        onSelectCitation={setSelectedCitation}
      />
      <RunStatusBar messages={messages} status={status} />
      {error ? (
        <div className="px-4 pt-2 pb-2">
          <ChatErrorBanner
            message={streamErrorMessage(error)}
            onDismiss={() => clearError()}
          />
        </div>
      ) : null}
      <ChatInput onSend={handleSend} disabled={isBusy} />
      <SourceSheet
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
}

export function ChatThreadPage() {
  const { threadId } = useParams();
  const location = useLocation();
  const initialPrompt =
    typeof location.state === "object" &&
    location.state !== null &&
    "initialPrompt" in location.state &&
    typeof location.state.initialPrompt === "string"
      ? location.state.initialPrompt
      : undefined;
  const [initialMessages, setInitialMessages] = useState<
    ChatUIMessage[] | null
  >(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [authExpired, setAuthExpired] = useState(false);

  useEffect(() => {
    if (!threadId) {
      return;
    }

    let cancelled = false;
    setInitialMessages(null);
    setLoadError(null);
    setAuthExpired(false);

    loadThreadMessages(threadId)
      .then((messages) => {
        if (!cancelled) {
          setInitialMessages(messages);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(historyLoadErrorMessage(error));
          setAuthExpired(error instanceof ApiError && error.status === 401);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [threadId]);

  if (!threadId) {
    return null;
  }

  if (loadError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="text-sm text-destructive" role="alert">
          {loadError}
        </p>
        <div className="flex gap-2">
          {authExpired ? (
            <Button asChild>
              <Link to="/sign-in">Sign in</Link>
            </Button>
          ) : null}
          <Button asChild variant="outline">
            <Link to="/chat">Back to conversations</Link>
          </Button>
        </div>
      </div>
    );
  }

  if (initialMessages === null) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-4">
        <Skeleton className="h-16 w-2/3 self-end" />
        <Skeleton className="h-24 w-3/4" />
        <Skeleton className="h-16 w-2/3 self-end" />
      </div>
    );
  }

  return (
    <ChatThreadView
      key={threadId}
      threadId={threadId}
      initialMessages={initialMessages}
      initialPrompt={initialPrompt}
    />
  );
}
