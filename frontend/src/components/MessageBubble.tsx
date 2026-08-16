import type { Citation } from "@/lib/api";
import { CitationBadge } from "./CitationBadge";

export interface ChatMessageView {
  role: string;
  content: string;
  citations?: Citation[];
}

export function MessageBubble({ message }: { message: ChatMessageView }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
            : "border border-zinc-200 bg-white text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50"
        }`}
      >
        <div>{message.content}</div>
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.citations.map((citation, index) => (
              <CitationBadge
                key={`${citation.document_id}-${citation.page}-${index}`}
                citation={citation}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
