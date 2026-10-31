import { useNavigate, useParams } from "react-router-dom";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  useSidebar,
} from "@/components/ui/sidebar";
import type { ThreadSummary } from "@/lib/chat";
import { useChatLayout } from "@/pages/chat/chat-layout-context";

const BUCKET_ORDER = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Older",
] as const;

type Bucket = (typeof BUCKET_ORDER)[number];

function bucketFor(dateInput: string): Bucket {
  const date = new Date(dateInput);
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const time = date.getTime();

  if (time >= startOfToday) {
    return "Today";
  }
  if (time >= startOfToday - dayMs) {
    return "Yesterday";
  }
  if (time >= startOfToday - 7 * dayMs) {
    return "Previous 7 days";
  }
  return "Older";
}

function groupThreads(
  threads: ThreadSummary[],
): Array<[Bucket, ThreadSummary[]]> {
  const groups = new Map<Bucket, ThreadSummary[]>();
  for (const thread of threads) {
    const bucket = bucketFor(thread.updatedAt);
    const existing = groups.get(bucket);
    if (existing) {
      existing.push(thread);
    } else {
      groups.set(bucket, [thread]);
    }
  }

  return BUCKET_ORDER.filter((bucket) => groups.has(bucket)).map((bucket) => [
    bucket,
    groups.get(bucket)!,
  ]);
}

export function ThreadSidebar() {
  const navigate = useNavigate();
  const { threadId } = useParams();
  const { setOpenMobile, isMobile } = useSidebar();
  const {
    threads,
    threadsLoading,
    threadsError,
    createNewThread,
    creatingThread,
  } = useChatLayout();

  function openThread(id: string) {
    navigate(`/chat/${id}`);
    if (isMobile) {
      setOpenMobile(false);
    }
  }

  const grouped = groupThreads(threads);

  return (
    <>
      <SidebarGroup>
        <Button
          className="w-full justify-start gap-2"
          onClick={() => void createNewThread()}
          disabled={creatingThread}
        >
          <Plus className="size-4" />
          {creatingThread ? "Creating…" : "New chat"}
        </Button>
      </SidebarGroup>

      {threadsError ? (
        <SidebarGroup>
          <p className="px-2 text-xs text-destructive" role="alert">
            {threadsError}
          </p>
        </SidebarGroup>
      ) : null}

      {threadsLoading ? (
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {Array.from({ length: 5 }).map((_, index) => (
                <SidebarMenuItem key={index}>
                  <SidebarMenuSkeleton />
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ) : null}

      {!threadsLoading && threads.length === 0 && !threadsError ? (
        <SidebarGroup>
          <p className="px-2 text-xs text-muted-foreground">
            No conversations yet. Start a new chat to begin.
          </p>
        </SidebarGroup>
      ) : null}

      {!threadsLoading
        ? grouped.map(([bucket, bucketThreads]) => (
            <SidebarGroup key={bucket}>
              <SidebarGroupLabel>{bucket}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {bucketThreads.map((thread) => (
                    <SidebarMenuItem key={thread.id}>
                      <SidebarMenuButton
                        isActive={thread.id === threadId}
                        onClick={() => openThread(thread.id)}
                        tooltip={thread.title}
                      >
                        <span className="truncate">{thread.title}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))
        : null}
    </>
  );
}
