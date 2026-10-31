import { ArrowUpRight } from "lucide-react";

import { useChatLayout } from "@/pages/chat/chat-layout-context";
import { cn } from "@/lib/utils";

const SUGGESTIONS: Array<{ ticker: string; prompt: string }> = [
  {
    ticker: "AAPL",
    prompt:
      "How did Apple's revenue mix across iPhone, Services, Mac, iPad, and Wearables shift from 2021 to 2025?",
  },
  {
    ticker: "AMZN",
    prompt:
      "Compare AWS operating income and margin against North America and International from 2021 to 2025.",
  },
  {
    ticker: "NVDA",
    prompt:
      "What demand drivers, customer concentration, and supply constraints did NVIDIA cite for its Data Center business?",
  },
  {
    ticker: "MSFT",
    prompt:
      "How did Microsoft's description of Azure, AI infrastructure, and cloud capacity constraints change over time?",
  },
];

export function ChatEmptyPage() {
  const { createNewThread, creatingThread } = useChatLayout();

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-2xl">
        <div className="flex flex-col items-center gap-4 text-center">
          <span
            aria-hidden
            className="flex size-12 items-center justify-center rounded-xl bg-foreground font-mono text-base font-medium text-background"
          >
            [d]
          </span>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-semibold tracking-tight">
              Ask the filings.
            </h1>
            <p className="mx-auto max-w-md text-sm text-muted-foreground">
              Every answer is grounded in retrieved 10-K passages, with
              citations you can open and verify. Pick a starting point or write
              your own.
            </p>
          </div>
        </div>

        <div className="mt-8 grid gap-2.5 sm:grid-cols-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion.ticker}
              type="button"
              disabled={creatingThread}
              onClick={() => void createNewThread(suggestion.prompt)}
              className={cn(
                "group flex flex-col gap-2 rounded-xl border border-border bg-card p-4 text-left transition-colors",
                "hover:border-foreground/40 hover:bg-accent disabled:pointer-events-none disabled:opacity-60",
              )}
            >
              <span className="flex items-center justify-between">
                <span className="font-mono text-xs tracking-widest text-muted-foreground">
                  {suggestion.ticker}
                </span>
                <ArrowUpRight className="size-4 text-muted-foreground transition-colors group-hover:text-foreground" />
              </span>
              <span className="text-sm leading-snug text-card-foreground">
                {suggestion.prompt}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
