import { cn } from "@/lib/utils";

type BrandProps = {
  showWordmark?: boolean;
  className?: string;
};

const SIZE = {
  mark: "size-7",
  glyph: "text-[0.7rem]",
};

export function Brand({ showWordmark = true, className }: BrandProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span
        aria-hidden
        className={cn(
          "flex shrink-0 items-center justify-center rounded-md bg-foreground font-mono font-medium text-background",
          SIZE.mark,
          SIZE.glyph,
        )}
      >
        [d]
      </span>
      {showWordmark ? (
        <span className="flex min-w-0 flex-col leading-none">
          <span className="truncate text-sm font-semibold tracking-tight">
            Document Copilot
          </span>
          <span className="truncate font-mono text-[0.65rem] text-muted-foreground">
            SEC filing analyst
          </span>
        </span>
      ) : null}
    </div>
  );
}
