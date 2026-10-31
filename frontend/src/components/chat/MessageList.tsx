import { useEffect, useRef } from "react";
import type { UIMessage } from "ai";

import { CitationChip } from "@/components/chat/CitationChip";
import { CitationMarker } from "@/components/chat/CitationMarker";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  findCitationByIndex,
  getMessageCitations,
  getMessageText,
  hasInsufficientEvidence,
  type Citation,
} from "@/lib/citations";

type MessageListProps = {
  messages: UIMessage[];
  selectedCitation: Citation | null;
  onSelectCitation: (citation: Citation) => void;
};

function renderAnswerText(
  text: string,
  citations: Citation[],
  selectedCitation: Citation | null,
  onSelectCitation: (citation: Citation) => void,
) {
  const segments = text.split(/(\[\d+\])/g);

  return segments.map((segment, index) => {
    const marker = segment.match(/^\[(\d+)\]$/);
    if (!marker) {
      return <span key={index}>{segment}</span>;
    }

    const citationIndex = Number(marker[1]);
    const citation = findCitationByIndex(citations, citationIndex);
    if (!citation) {
      return <span key={index}>{segment}</span>;
    }

    return (
      <CitationMarker
        key={index}
        citation={citation}
        selected={selectedCitation?.citationIndex === citation.citationIndex}
        onSelect={onSelectCitation}
      />
    );
  });
}

type AssistantMessageProps = {
  message: UIMessage;
  selectedCitation: Citation | null;
  onSelectCitation: (citation: Citation) => void;
};

function AssistantMessage({
  message,
  selectedCitation,
  onSelectCitation,
}: AssistantMessageProps) {
  const text = getMessageText(message);
  const citations = getMessageCitations(message);
  const insufficientEvidence = hasInsufficientEvidence(message);

  const footer =
    citations.length > 0 || insufficientEvidence ? (
      <div className="flex flex-col gap-2">
        {insufficientEvidence ? (
          <p className="text-xs text-muted-foreground">
            Not enough evidence in the available filings to support a grounded
            answer.
          </p>
        ) : null}
        {citations.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {citations.map((citation) => (
              <CitationChip
                key={citation.citationIndex}
                citation={citation}
                selected={
                  selectedCitation?.citationIndex === citation.citationIndex
                }
                onSelect={onSelectCitation}
              />
            ))}
          </div>
        ) : null}
      </div>
    ) : null;

  return (
    <MessageBubble role="assistant" footer={footer}>
      {renderAnswerText(text, citations, selectedCitation, onSelectCitation)}
    </MessageBubble>
  );
}

export function MessageList({
  messages,
  selectedCitation,
  onSelectCitation,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, selectedCitation]);

  const visibleMessages = messages.filter((message) => {
    if (message.role === "assistant") {
      return (
        getMessageText(message) !== "" ||
        getMessageCitations(message).length > 0
      );
    }
    return getMessageText(message) !== "";
  });

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div
        className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6"
        role="log"
        aria-live="polite"
      >
        {visibleMessages.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Send a message to start this conversation.
          </p>
        ) : null}

        {visibleMessages.map((message) =>
          message.role === "user" ? (
            <MessageBubble key={message.id} role="user">
              {getMessageText(message)}
            </MessageBubble>
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              selectedCitation={selectedCitation}
              onSelectCitation={onSelectCitation}
            />
          ),
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
