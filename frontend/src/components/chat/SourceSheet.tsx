import { useEffect, useState } from "react";

import { Meta } from "@/components/common/Meta";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { Citation } from "@/lib/citations";

type SourceSheetProps = {
  citation: Citation | null;
  onClose: () => void;
};

export function SourceSheet({ citation, onClose }: SourceSheetProps) {
  // Keep the last citation mounted so content stays visible during close.
  const [rendered, setRendered] = useState<Citation | null>(citation);

  useEffect(() => {
    if (citation) {
      setRendered(citation);
    }
  }, [citation]);

  const active = rendered;

  return (
    <Sheet
      open={citation !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="gap-1.5 border-b border-border">
          <span className="font-mono text-[0.65rem] tracking-widest text-muted-foreground uppercase">
            Source [{active?.citationIndex}]
          </span>
          <SheetTitle>{active?.companyName || active?.ticker}</SheetTitle>
          <SheetDescription asChild>
            <Meta
              items={[active?.ticker, active?.form, active?.filingDate]}
              className="text-xs"
            />
          </SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
            {active?.page ? (
              <>
                <dt className="text-muted-foreground">Page</dt>
                <dd>{active.page}</dd>
              </>
            ) : null}
            {active?.section ? (
              <>
                <dt className="text-muted-foreground">Section</dt>
                <dd className="min-w-0 break-words">{active.section}</dd>
              </>
            ) : null}
            {active?.accessionNumber ? (
              <>
                <dt className="text-muted-foreground">Accession</dt>
                <dd className="min-w-0 break-words">
                  {active.accessionNumber}
                </dd>
              </>
            ) : null}
          </dl>

          <figure className="border-l-2 border-foreground/30 bg-muted/40 px-4 py-3">
            <blockquote className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
              {active?.excerpt}
            </blockquote>
            <figcaption className="mt-3 font-mono text-[0.65rem] text-muted-foreground">
              Excerpt from the retrieved filing passage.
            </figcaption>
          </figure>
        </div>
      </SheetContent>
    </Sheet>
  );
}
