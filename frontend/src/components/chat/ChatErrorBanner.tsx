import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

type ChatErrorBannerProps = {
  message: string;
  onDismiss?: () => void;
};

export function ChatErrorBanner({ message, onDismiss }: ChatErrorBannerProps) {
  return (
    <div
      className="mx-auto flex w-full max-w-3xl items-start justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      role="alert"
    >
      <p>{message}</p>
      {onDismiss ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="shrink-0 text-destructive hover:bg-destructive/10"
          onClick={onDismiss}
        >
          <X className="size-3.5" />
          <span className="sr-only">Dismiss error</span>
        </Button>
      ) : null}
    </div>
  );
}
