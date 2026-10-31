import type { Citation } from "@/lib/citations";
import { cn } from "@/lib/utils";

type CitationMarkerProps = {
  citation: Citation;
  selected: boolean;
  onSelect: (citation: Citation) => void;
};

export function CitationMarker({
  citation,
  selected,
  onSelect,
}: CitationMarkerProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(citation)}
      aria-label={`Show source ${citation.citationIndex}`}
      className={cn(
        "mx-0.5 inline-flex h-4 min-w-4 translate-y-[-0.35em] items-center justify-center rounded-[4px] px-1 align-baseline font-mono text-[0.65rem] leading-none transition-colors",
        selected
          ? "bg-foreground text-background"
          : "bg-muted text-muted-foreground hover:bg-foreground hover:text-background",
      )}
    >
      {citation.citationIndex}
    </button>
  );
}
