"use client";

import type { ChatSessionPublic } from "@/lib/api";

interface SessionListProps {
  sessions: ChatSessionPublic[];
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}

export function SessionList({
  sessions,
  currentSessionId,
  onSelect,
  onNewChat,
}: SessionListProps) {
  return (
    <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold tracking-wide text-zinc-500 uppercase">
          Chats
        </h2>
        <button
          onClick={onNewChat}
          className="text-xs font-medium text-zinc-900 hover:underline dark:text-zinc-50"
        >
          + New
        </button>
      </div>
      <ul className="flex flex-col gap-1">
        {sessions.length === 0 && (
          <li className="text-xs text-zinc-400">No chats yet.</li>
        )}
        {sessions.map((session) => (
          <li key={session.id}>
            <button
              onClick={() => onSelect(session.id)}
              className={`w-full truncate rounded-md px-2 py-1 text-left text-sm ${
                session.id === currentSessionId
                  ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              }`}
            >
              {session.title || "New chat"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
