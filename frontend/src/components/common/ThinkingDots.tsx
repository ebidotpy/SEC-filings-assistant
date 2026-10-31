import { cn } from "@/lib/utils";

export function ThinkingDots({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1", className)}
      aria-hidden
    >
      <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-300ms]" />
      <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-150ms]" />
      <span className="size-1.5 animate-bounce rounded-full bg-current" />
    </span>
  );
}
