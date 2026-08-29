"use client";

import { useAuth } from "@/lib/auth-context";
import { api, type Citation } from "@/lib/api";

// Phase 8: quotes topic/upload date alongside filename+page when the citation carries
// them (documents ingested before Phase 8, or filed outside every configured watch
// folder, still have neither — the badge just omits what's missing).
function formatUploadDate(uploadedAt: string | null | undefined): string | null {
  if (!uploadedAt) return null;
  const date = new Date(uploadedAt);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

export function CitationBadge({ citation }: { citation: Citation }) {
  const { token } = useAuth();
  if (!token) return null;

  const uploadDate = formatUploadDate(citation.uploaded_at);
  const extra = [citation.topic_path, uploadDate ? `uploaded ${uploadDate}` : null].filter(
    Boolean,
  );

  return (
    <a
      href={api.downloadUrl(citation.document_id, token, citation.page)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-full border border-zinc-300 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-600 hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:text-zinc-50"
    >
      {citation.filename} p.{citation.page}
      {extra.length > 0 && (
        <span className="text-zinc-400 dark:text-zinc-500">, {extra.join(", ")}</span>
      )}
    </a>
  );
}
