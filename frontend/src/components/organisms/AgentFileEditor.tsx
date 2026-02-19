"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { customFetch } from "@/api/mutator";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type FileInfo = {
  name: string;
  path: string;
  size: number | null;
};

type FileListResponse = {
  agent_id: string;
  files: FileInfo[];
};

type FileContentResponse = {
  agent_id: string;
  path: string;
  content: string;
};

export function AgentFileEditor({ agentId }: { agentId: string }) {
  const queryClient = useQueryClient();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  const filesQuery = useQuery<FileInfo[]>({
    queryKey: ["agent-files", agentId],
    queryFn: async () => {
      const res = await customFetch<{
        data: FileListResponse;
        status: number;
      }>(`/api/v1/agents/${agentId}/files`, { method: "GET" });
      return res.data.files;
    },
    enabled: Boolean(agentId),
    retry: false,
  });

  const contentQuery = useQuery<string>({
    queryKey: ["agent-file-content", agentId, selectedPath],
    queryFn: async () => {
      const res = await customFetch<{
        data: FileContentResponse;
        status: number;
      }>(`/api/v1/agents/${agentId}/files/${selectedPath}`, {
        method: "GET",
      });
      return res.data.content;
    },
    enabled: Boolean(agentId && selectedPath),
    retry: false,
  });

  const saveMutation = useMutation({
    mutationFn: async ({ path, content }: { path: string; content: string }) =>
      customFetch<{ data: FileContentResponse; status: number }>(
        `/api/v1/agents/${agentId}/files/${path}`,
        { method: "PUT", body: JSON.stringify({ content }) },
      ),
    onSuccess: () => {
      setIsEditing(false);
      setSaveError(null);
      queryClient.invalidateQueries({
        queryKey: ["agent-file-content", agentId, selectedPath],
      });
    },
    onError: (err: Error) => {
      setSaveError(err.message || "Failed to save file.");
    },
  });

  const files = filesQuery.data ?? [];

  const handleSelectFile = (path: string) => {
    setSelectedPath(path);
    setIsEditing(false);
    setSaveError(null);
  };

  const handleEdit = () => {
    setDraft(contentQuery.data ?? "");
    setIsEditing(true);
    setSaveError(null);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setSaveError(null);
  };

  const handleSave = () => {
    if (!selectedPath) return;
    saveMutation.mutate({ path: selectedPath, content: draft });
  };

  return (
    <div className="flex gap-4 min-h-[400px]">
      <div className="w-56 flex-shrink-0 space-y-1 rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-quiet">
          Files
        </p>
        {filesQuery.isLoading ? (
          <p className="text-xs text-muted">Loading…</p>
        ) : filesQuery.error ? (
          <p className="text-xs text-red-500">
            {(filesQuery.error as Error).message || "Failed to load files."}
          </p>
        ) : files.length === 0 ? (
          <p className="text-xs text-muted">No files found.</p>
        ) : (
          files.map((file) => (
            <button
              key={file.path}
              type="button"
              onClick={() => handleSelectFile(file.path)}
              className={`w-full rounded-lg px-3 py-2 text-left text-xs transition ${
                selectedPath === file.path
                  ? "bg-[color:var(--accent)] text-white font-semibold"
                  : "text-muted hover:bg-[color:var(--surface-muted)]"
              }`}
            >
              {file.name}
            </button>
          ))
        )}
      </div>

      <div className="flex-1 rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4">
        {!selectedPath ? (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            Select a file to view its contents.
          </div>
        ) : contentQuery.isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            Loading file…
          </div>
        ) : contentQuery.error ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-sm">
            <p className="text-muted">
              {selectedPath} does not exist yet.
            </p>
            <Button
              onClick={() => {
                if (!selectedPath) return;
                setDraft("");
                saveMutation.mutate(
                  { path: selectedPath, content: " " },
                  {
                    onSuccess: () => {
                      queryClient.invalidateQueries({
                        queryKey: ["agent-file-content", agentId, selectedPath],
                      });
                      setIsEditing(true);
                      setDraft("");
                    },
                  },
                );
              }}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "Creating…" : "Create file"}
            </Button>
            {saveError ? (
              <p className="text-xs text-red-500">{saveError}</p>
            ) : null}
          </div>
        ) : (
          <div className="flex h-full flex-col gap-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-strong">
                {selectedPath}
              </p>
              <div className="flex items-center gap-2">
                {isEditing ? (
                  <>
                    <Button
                      variant="outline"
                      onClick={handleCancel}
                      disabled={saveMutation.isPending}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleSave}
                      disabled={saveMutation.isPending}
                    >
                      {saveMutation.isPending ? "Saving…" : "Save"}
                    </Button>
                  </>
                ) : (
                  <Button variant="outline" onClick={handleEdit}>
                    Edit
                  </Button>
                )}
              </div>
            </div>
            {saveError ? (
              <p className="text-xs text-red-500">{saveError}</p>
            ) : null}
            {isEditing ? (
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="flex-1 resize-none font-mono text-xs leading-relaxed"
                disabled={saveMutation.isPending}
              />
            ) : (
              <pre className="flex-1 overflow-auto whitespace-pre-wrap rounded-lg bg-[color:var(--surface-muted)] p-4 font-mono text-xs leading-relaxed text-strong">
                {contentQuery.data}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
