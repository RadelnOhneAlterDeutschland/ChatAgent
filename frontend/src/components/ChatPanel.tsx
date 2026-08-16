"use client";

import { useState, type FormEvent } from "react";
import { MessageBubble, type ChatMessageView } from "./MessageBubble";

export type { ChatMessageView };

interface ChatPanelProps {
  messages: ChatMessageView[];
  onSend: (text: string) => Promise<void>;
  sending: boolean;
}

export function ChatPanel({ messages, onSend, sending }: ChatPanelProps) {
  const [draft, setDraft] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    await onSend(text);
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <p className="m-auto text-sm text-zinc-400">
            Ask a question about your uploaded documents.
          </p>
        )}
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-400 dark:border-zinc-800 dark:bg-zinc-900">
              Thinking…
            </div>
          </div>
        )}
      </div>
      <form
        onSubmit={handleSubmit}
        className="flex gap-2 border-t border-zinc-200 p-4 dark:border-zinc-800"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Send
        </button>
      </form>
    </div>
  );
}
