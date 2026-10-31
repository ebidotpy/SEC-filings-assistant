import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ChatInputProps = {
  onSend: (text: string) => void;
  disabled?: boolean;
};

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const text = value.trim();
    if (!text || disabled) {
      return;
    }

    onSend(text);
    setValue("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="px-4 pb-4">
      <div className="mx-auto w-full max-w-3xl">
        <div className="relative rounded-2xl border border-border bg-card shadow-sm transition-colors focus-within:border-ring">
          <Textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about SEC filings…"
            disabled={disabled}
            rows={1}
            className="max-h-48 min-h-[3.5rem] resize-none border-0 bg-transparent py-4 pr-14 pl-4 text-sm shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          <Button
            type="submit"
            size="icon"
            className="absolute right-2.5 bottom-2.5 rounded-full"
            disabled={disabled || value.trim() === ""}
          >
            <ArrowUp className="size-4" />
            <span className="sr-only">Send message</span>
          </Button>
        </div>
        <p className="mt-2 px-1 text-center font-mono text-[0.65rem] text-muted-foreground">
          Answers are grounded in retrieved filings. Verify every citation.
        </p>
      </div>
    </form>
  );
}
