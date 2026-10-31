import type { UIMessage } from "ai";

export type Citation = {
  citationIndex: number;
  chunkId: string;
  excerpt: string;
  ticker: string;
  companyName: string;
  form: string;
  filingDate: string;
  page: string | null;
  section: string | null;
  accessionNumber?: string;
};

type CitationPartData = {
  citations?: Citation[];
  message?: string;
};

type MessagePart = {
  type: string;
  text?: string;
  data?: CitationPartData;
};

function isCitation(value: unknown): value is Citation {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const record = value as Record<string, unknown>;
  return (
    typeof record.citationIndex === "number" &&
    typeof record.chunkId === "string" &&
    typeof record.excerpt === "string"
  );
}

function parseCitation(value: unknown): Citation | null {
  if (!isCitation(value)) {
    return null;
  }

  const record = value as Record<string, unknown>;
  return {
    citationIndex: record.citationIndex as number,
    chunkId: record.chunkId as string,
    excerpt: record.excerpt as string,
    ticker: (record.ticker as string | undefined) ?? "",
    companyName: (record.companyName as string | undefined) ?? "",
    form: (record.form as string | undefined) ?? "",
    filingDate: (record.filingDate as string | undefined) ?? "",
    page: (record.page as string | null | undefined) ?? null,
    section: (record.section as string | null | undefined) ?? null,
    accessionNumber: record.accessionNumber as string | undefined,
  };
}

export function getMessageText(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("");
}

export function getMessageCitations(message: UIMessage): Citation[] {
  const citations: Citation[] = [];

  for (const part of message.parts as MessagePart[]) {
    if (part.type !== "data-citations" || !part.data?.citations) {
      continue;
    }

    for (const raw of part.data.citations) {
      const citation = parseCitation(raw);
      if (citation) {
        citations.push(citation);
      }
    }
  }

  return citations.sort((a, b) => a.citationIndex - b.citationIndex);
}

export function getLatestRunStatus(message: UIMessage): string | null {
  let latest: string | null = null;

  for (const part of message.parts as MessagePart[]) {
    if (part.type === "data-status" && part.data?.message) {
      latest = part.data.message;
    }
  }

  return latest;
}

export function formatCitationLabel(citation: Citation): string {
  const parts = [citation.ticker, citation.form, citation.filingDate];
  if (citation.page) {
    parts.push(`p.${citation.page}`);
  }
  return parts.filter(Boolean).join(" · ");
}

const INSUFFICIENT_EVIDENCE_PATTERNS = [
  /not enough evidence/i,
  /insufficient evidence/i,
  /cannot find enough/i,
  /no relevant passages/i,
];

export function hasInsufficientEvidence(message: UIMessage): boolean {
  const text = getMessageText(message);
  const citations = getMessageCitations(message);
  if (citations.length > 0) {
    return false;
  }
  return INSUFFICIENT_EVIDENCE_PATTERNS.some((pattern) => pattern.test(text));
}

export function findCitationByIndex(
  citations: Citation[],
  index: number,
): Citation | undefined {
  return citations.find((citation) => citation.citationIndex === index);
}
