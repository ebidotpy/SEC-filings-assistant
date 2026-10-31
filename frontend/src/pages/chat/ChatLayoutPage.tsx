import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";

import { Brand } from "@/components/common/Brand";
import { ThreadSidebar } from "@/components/chat/ThreadSidebar";
import { UserMenu } from "@/components/chat/UserMenu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { createThread, listThreads, type ThreadSummary } from "@/lib/chat";
import { ApiError } from "@/lib/http";
import { ChatLayoutContext } from "@/pages/chat/chat-layout-context";

function ChatTopBar({ threads }: { threads: ThreadSummary[] }) {
  const { threadId } = useParams();
  const activeThread = threads.find((thread) => thread.id === threadId);

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-3">
      <SidebarTrigger />
      <div className="min-w-0 flex-1 truncate text-sm font-medium">
        {activeThread ? activeThread.title : "New conversation"}
      </div>
    </header>
  );
}

export function ChatLayoutPage() {
  const navigate = useNavigate();
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(true);
  const [threadsError, setThreadsError] = useState<string | null>(null);
  const [creatingThread, setCreatingThread] = useState(false);

  const refreshThreads = useCallback(async () => {
    setThreadsError(null);

    try {
      const nextThreads = await listThreads();
      setThreads(
        [...nextThreads].sort(
          (a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
        ),
      );
    } catch (error) {
      setThreadsError(
        error instanceof ApiError
          ? error.message
          : "Could not load conversations",
      );
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshThreads();
  }, [refreshThreads]);

  const createNewThread = useCallback(
    async (initialPrompt?: string) => {
      setCreatingThread(true);
      setThreadsError(null);

      try {
        const thread = await createThread();
        await refreshThreads();
        navigate(`/chat/${thread.id}`, {
          state: initialPrompt ? { initialPrompt } : undefined,
        });
      } catch (error) {
        setThreadsError(
          error instanceof ApiError
            ? error.message
            : "Could not create a new conversation",
        );
      } finally {
        setCreatingThread(false);
      }
    },
    [navigate, refreshThreads],
  );

  const value = useMemo(
    () => ({
      threads,
      threadsLoading,
      threadsError,
      refreshThreads,
      createNewThread,
      creatingThread,
    }),
    [
      threads,
      threadsLoading,
      threadsError,
      refreshThreads,
      createNewThread,
      creatingThread,
    ],
  );

  return (
    <ChatLayoutContext.Provider value={value}>
      <SidebarProvider>
        <Sidebar collapsible="offcanvas">
          <SidebarHeader className="px-2 py-2.5">
            <Brand />
          </SidebarHeader>
          <SidebarContent>
            <ThreadSidebar />
          </SidebarContent>
          <SidebarFooter>
            <UserMenu />
          </SidebarFooter>
          <SidebarRail />
        </Sidebar>
        <SidebarInset className="flex min-h-0 flex-col">
          <ChatTopBar threads={threads} />
          <div className="flex min-h-0 flex-1 flex-col">
            <Outlet />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </ChatLayoutContext.Provider>
  );
}
