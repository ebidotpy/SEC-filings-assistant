import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { GuestRoute, ProtectedRoute } from "@/components/ProtectedRoute";
import { AuthProvider } from "@/lib/auth";
import { ChatEmptyPage } from "@/pages/chat/ChatEmptyPage";
import { SignInPage } from "@/pages/SignInPage";
import { SignUpPage } from "@/pages/SignUpPage";

const ChatLayoutPage = lazy(() =>
  import("@/pages/chat/ChatLayoutPage").then((module) => ({
    default: module.ChatLayoutPage,
  })),
);
const ChatThreadPage = lazy(() =>
  import("@/pages/chat/ChatThreadPage").then((module) => ({
    default: module.ChatThreadPage,
  })),
);

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
              Loading…
            </div>
          }
        >
          <Routes>
            <Route
              path="/sign-in"
              element={
                <GuestRoute>
                  <SignInPage />
                </GuestRoute>
              }
            />
            <Route
              path="/sign-up"
              element={
                <GuestRoute>
                  <SignUpPage />
                </GuestRoute>
              }
            />
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route
              path="/chat"
              element={
                <ProtectedRoute>
                  <ChatLayoutPage />
                </ProtectedRoute>
              }
            >
              <Route index element={<ChatEmptyPage />} />
              <Route path=":threadId" element={<ChatThreadPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
