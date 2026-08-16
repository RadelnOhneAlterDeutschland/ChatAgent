"use client";

import { useAuth } from "@/lib/auth-context";
import { api, type Citation } from "@/lib/api";

export function CitationBadge({ citation }: { citation: Citation }) {
  const { token } = useAuth();
  if (!token) return null;

  return (
    <a
      href={api.downloadUrl(citation.document_id, token, citation.page)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-full border border-zinc-300 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-600 hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:text-zinc-50"
    >
      {citation.filename} p.{citation.page}
    </a>
  );
}
