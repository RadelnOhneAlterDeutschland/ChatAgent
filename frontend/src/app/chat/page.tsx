"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  api,
  ApiError,
  type ChatSessionPublic,
  type DocumentPublic,
} from "@/lib/api";
import { DocumentSidebar } from "@/components/DocumentSidebar";
import { SessionList } from "@/components/SessionList";
import { ChatPanel, type ChatMessageView } from "@/components/ChatPanel";

const POLL_INTERVAL_MS = 3000;

export default function ChatPage() {
  const { token, user, loading, logout } = useAuth();
  const router = useRouter();

  const [documents, setDocuments] = useState<DocumentPublic[]>([]);
  const [sessions, setSessions] = useState<ChatSessionPublic[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !token) router.replace("/login");
  }, [loading, token, router]);

  const refreshDocuments = useCallback(async () => {
    if (!token) return;
    setDocuments(await api.listDocuments(token));
  }, [token]);

  const refreshSessions = useCallback(async () => {
    if (!token) return;
    setSessions(await api.listSessions(token));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let ignore = false;

    async function loadInitialData() {
      const [initialDocuments, initialSessions] = await Promise.all([
        api.listDocuments(token as string),
        api.listSessions(token as string),
      ]);
      if (!ignore) {
        setDocuments(initialDocuments);
        setSessions(initialSessions);
      }
    }

    loadInitialData();
    return () => {
      ignore = true;
    };
  }, [token]);

  // Upload is synchronous on the backend, so this mostly matters for a second tab
  // watching the same account process a large document.
  useEffect(() => {
    if (!token) return;
    const hasPending = documents.some(
      (doc) => doc.status === "pending" || doc.status === "processing",
    );
    if (!hasPending) return;
    const interval = setInterval(refreshDocuments, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [token, documents, refreshDocuments]);

  async function handleDeleteDocument(id: string) {
    if (!token) return;
    await api.deleteDocument(token, id);
    await refreshDocuments();
  }

  function handleNewChat() {
    setCurrentSessionId(null);
    setMessages([]);
    setError(null);
  }

  async function handleSelectSession(id: string) {
    if (!token) return;
    const detail = await api.getSession(token, id);
    setCurrentSessionId(detail.id);
    setError(null);
    setMessages(
      detail.messages
        .filter((message) => message.content !== null)
        .map((message) => ({
          role: message.role,
          content: message.content as string,
        })),
    );
  }

  async function handleSend(text: string) {
    if (!token) return;
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const response = await api.sendChat(token, text, currentSessionId);
      setCurrentSessionId(response.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.message,
          citations: response.citations,
        },
      ]);
      refreshSessions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  if (loading || !token) {
    return null;
  }

  return (
    <div className="flex flex-1">
      <aside className="flex w-64 flex-col border-r border-zinc-200 dark:border-zinc-800">
        <DocumentSidebar documents={documents} onDelete={handleDeleteDocument} />
        <SessionList
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={handleSelectSession}
          onNewChat={handleNewChat}
        />
        <div className="flex items-center justify-between border-t border-zinc-200 p-4 text-xs text-zinc-500 dark:border-zinc-800">
          <span className="truncate">{user?.email}</span>
          <button onClick={logout} className="font-medium hover:underline">
            Log out
          </button>
        </div>
      </aside>
      <main className="flex flex-1 flex-col">
        {error && (
          <p className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
        <ChatPanel messages={messages} onSend={handleSend} sending={sending} />
      </main>
    </div>
  );
}
