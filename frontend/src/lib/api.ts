// Thin fetch wrapper around the FastAPI backend. Types mirror the Pydantic response
// models in backend/app/api/{auth,documents,chat}.py — keep them in sync by hand for now
// (no shared schema generation set up yet).

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Response body wasn't JSON — fall back to the status text.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface UserPublic {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentPublic {
  id: string;
  filename: string;
  status: DocumentStatus;
  uploaded_at: string;
}

export interface Citation {
  document_id: string;
  filename: string;
  page: number;
}

export interface ChatResponse {
  session_id: string;
  message: string;
  citations: Citation[];
}

export interface ChatSessionPublic {
  id: string;
  title: string | null;
  created_at: string;
}

export interface ChatMessagePublic {
  role: string;
  content: string | null;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSessionPublic {
  messages: ChatMessagePublic[];
}

export const api = {
  signup: (email: string, password: string) =>
    request<UserPublic>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: (token: string) => request<UserPublic>("/auth/me", {}, token),

  // Documents arrive via the folder-sync cron job (plan.md Phase 2b), not a web upload —
  // there is no uploadDocument here anymore.
  listDocuments: (token: string) =>
    request<DocumentPublic[]>("/documents", {}, token),

  deleteDocument: (token: string, id: string) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }, token),

  // Opened as a plain browser navigation (new tab), so the token travels as a query
  // param rather than an Authorization header. KNOWN SIMPLIFICATION (plan.md Phase 5
  // backlog): swap for a short-lived presigned S3 URL before production — this puts the
  // user's access token in the URL (browser history, server logs).
  downloadUrl: (id: string, token: string, page?: number) => {
    const base = `${API_BASE_URL}/documents/${id}/download?token=${encodeURIComponent(token)}`;
    return page ? `${base}#page=${page}` : base;
  },

  sendChat: (token: string, message: string, sessionId?: string | null) =>
    request<ChatResponse>(
      "/chat",
      {
        method: "POST",
        body: JSON.stringify({ message, session_id: sessionId ?? null }),
      },
      token,
    ),

  listSessions: (token: string) =>
    request<ChatSessionPublic[]>("/chat/sessions", {}, token),

  getSession: (token: string, id: string) =>
    request<ChatSessionDetail>(`/chat/sessions/${id}`, {}, token),
};
