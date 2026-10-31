import { cn } from "@/lib/utils";

type MetaProps = {
  items: Array<string | null | undefined>;
  className?: string;
};

export function Meta({ items, className }: MetaProps) {
  const parts = items.filter((item): item is string => Boolean(item));
  if (parts.length === 0) {
    return null;
  }

  return (
    <span
      className={cn(
        "font-mono text-xs tracking-tight text-muted-foreground",
        className,
      )}
    >
      {parts.join(" · ")}
    </span>
  );
}
