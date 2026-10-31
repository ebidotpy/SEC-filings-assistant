import type { Citation } from "@/lib/citations";
import { cn } from "@/lib/utils";

type CitationChipProps = {
  citation: Citation;
  selected?: boolean;
  onSelect: (citation: Citation) => void;
};

export function CitationChip({
  citation,
  selected = false,
  onSelect,
}: CitationChipProps) {
  const label = [citation.ticker, citation.form, citation.filingDate]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={() => onSelect(citation)}
      className={cn(
        "group inline-flex h-7 items-center gap-1.5 rounded-full border border-border pr-2.5 pl-1 text-xs transition-colors",
        selected
          ? "border-foreground bg-foreground text-background"
          : "bg-card text-muted-foreground hover:border-foreground/40 hover:text-foreground",
      )}
    >
      <span
        className={cn(
          "flex h-5 min-w-5 items-center justify-center rounded-full font-mono text-[0.65rem]",
          selected
            ? "bg-background/20 text-background"
            : "bg-muted text-foreground",
        )}
      >
        {citation.citationIndex}
      </span>
      <span className="font-mono">
        {label || `Source ${citation.citationIndex}`}
      </span>
      {citation.page ? (
        <span className="font-mono opacity-70">p.{citation.page}</span>
      ) : null}
    </button>
  );
}
