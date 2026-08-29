"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { api, ApiError, type IntakeSuggestion } from "@/lib/api";

const NEW_SUBFOLDER_OPTION = "__new__";
const NO_SUBFOLDER_OPTION = "__none__";

interface IntakeUploadProps {
  onFiled: () => Promise<void> | void;
}

// Phase 8: smart intake. Picking a file gets a folder suggestion from the LLM; nothing is
// written to disk until the author explicitly confirms — the suggestion is a starting
// point, not a decision made for them.
export function IntakeUpload({ onFiled }: IntakeUploadProps) {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [suggestion, setSuggestion] = useState<IntakeSuggestion | null>(null);
  const [topic, setTopic] = useState("");
  const [subfolderChoice, setSubfolderChoice] = useState(NO_SUBFOLDER_OPTION);
  const [newSubfolderName, setNewSubfolderName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!token) return null;

  function reset() {
    setSuggestion(null);
    setTopic("");
    setSubfolderChoice(NO_SUBFOLDER_OPTION);
    setNewSubfolderName("");
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !token) return;

    setBusy(true);
    setError(null);
    try {
      const result = await api.suggestIntake(token, file);
      setSuggestion(result);
      setTopic(result.suggested_topic);
      setSubfolderChoice(result.suggested_subfolder ?? NO_SUBFOLDER_OPTION);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not suggest a placement.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!suggestion || !token) return;

    const subfolder =
      subfolderChoice === NO_SUBFOLDER_OPTION
        ? null
        : subfolderChoice === NEW_SUBFOLDER_OPTION
          ? newSubfolderName.trim() || null
          : subfolderChoice;

    setBusy(true);
    setError(null);
    try {
      await api.confirmIntake(token, suggestion.intake_id, topic, subfolder);
      reset();
      await onFiled();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not file the document.");
    } finally {
      setBusy(false);
    }
  }

  const availableSubfolders =
    suggestion?.topics.find((t) => t.name === topic)?.subfolders ?? [];

  return (
    <div className="flex flex-col gap-2 border-b border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <label className="flex w-fit cursor-pointer items-center gap-1 rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-600 hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:text-zinc-50">
        + Add document
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={busy}
          onChange={handleFileChosen}
        />
      </label>

      {busy && !suggestion && (
        <p className="text-xs text-zinc-400">Reading document and suggesting a folder…</p>
      )}

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      {suggestion && (
        <div className="flex flex-col gap-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-700">
          <p className="truncate text-xs text-zinc-500" title={suggestion.filename}>
            {suggestion.filename}
          </p>
          <p className="text-xs text-zinc-400 italic">“{suggestion.rationale}”</p>

          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Topic
            <select
              value={topic}
              onChange={(event) => {
                setTopic(event.target.value);
                setSubfolderChoice(NO_SUBFOLDER_OPTION);
              }}
              className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
            >
              {suggestion.topics.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Category (optional)
            <select
              value={subfolderChoice}
              onChange={(event) => setSubfolderChoice(event.target.value)}
              className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 dark:border-zinc-700"
            >
              <option value={NO_SUBFOLDER_OPTION}>— none —</option>
              {availableSubfolders.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
              <option value={NEW_SUBFOLDER_OPTION}>+ New category…</option>
            </select>
          </label>

          {subfolderChoice === NEW_SUBFOLDER_OPTION && (
            <input
              type="text"
              value={newSubfolderName}
              onChange={(event) => setNewSubfolderName(event.target.value)}
              placeholder="New category name"
              className="rounded border border-zinc-300 bg-transparent px-1 py-0.5 text-xs dark:border-zinc-700"
            />
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={reset}
              disabled={busy}
              className="text-xs text-zinc-500 hover:underline"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={busy}
              className="rounded bg-zinc-900 px-2 py-1 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {busy ? "Filing…" : "Confirm placement"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
