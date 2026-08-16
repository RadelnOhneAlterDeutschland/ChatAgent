"use client";

import type { DocumentPublic } from "@/lib/api";

interface DocumentSidebarProps {
  documents: DocumentPublic[];
  onDelete: (id: string) => Promise<void>;
}

const STATUS_STYLES: Record<string, string> = {
  ready: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  pending: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

// Documents arrive via the folder-sync cron job (plan.md Phase 2b), not a web upload —
// this list is read-only except for delete.
export function DocumentSidebar({ documents, onDelete }: DocumentSidebarProps) {
  return (
    <div className="flex flex-col gap-2 border-b border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="text-xs font-semibold tracking-wide text-zinc-500 uppercase">
        Shared documents
      </h2>

      <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto">
        {documents.length === 0 && (
          <li className="text-xs text-zinc-400">
            Nothing here yet — drop a PDF into the watched folder.
          </li>
        )}
        {documents.map((doc) => (
          <li
            key={doc.id}
            className="group flex items-center justify-between gap-2 rounded-md px-2 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <span
              className="truncate text-zinc-700 dark:text-zinc-300"
              title={doc.filename}
            >
              {doc.filename}
            </span>
            <span className="flex items-center gap-1">
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLES[doc.status] ?? ""}`}
              >
                {doc.status}
              </span>
              <button
                onClick={() => onDelete(doc.id)}
                className="hidden text-xs text-zinc-400 hover:text-red-600 group-hover:inline dark:hover:text-red-400"
                aria-label={`Delete ${doc.filename}`}
              >
                ✕
              </button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
