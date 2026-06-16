"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Database, Pencil, RefreshCw, Search, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBaseChunk } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Textarea, Label } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export default function KnowledgeBasePage() {
  const router = useRouter();
  const [chunks, setChunks] = useState<KnowledgeBaseChunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string>("");
  const [draft, setDraft] = useState<KnowledgeBaseChunk | null>(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await api.listKnowledgeChunks(500);
      setChunks(res.chunks);
      const first = res.chunks[0] || null;
      setSelectedId((prev) => prev || first?.chunk_id || "");
      setDraft((prev) => prev || first);
    } catch (e: any) {
      setError(e.message || "Failed to load knowledge base chunks.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return chunks;
    return chunks.filter((c) =>
      [
        c.text,
        c.source_proposal,
        c.source_section,
        c.proposal_family,
        c.chunk_id,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [chunks, query]);

  useEffect(() => {
    if (!filtered.length) return;
    if (!selectedId || !filtered.some((c) => c.chunk_id === selectedId)) {
      setSelectedId(filtered[0].chunk_id);
    }
  }, [filtered, selectedId]);

  useEffect(() => {
    const item = chunks.find((c) => c.chunk_id === selectedId) || null;
    setDraft(item);
  }, [chunks, selectedId]);

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateKnowledgeChunk(draft.chunk_id, {
        text: draft.text,
        source_proposal: draft.source_proposal,
        source_section: draft.source_section,
        proposal_family: draft.proposal_family,
      });
      setChunks((prev) =>
        prev.map((c) => (c.chunk_id === updated.chunk_id ? updated : c))
      );
      setDraft(updated);
    } catch (e: any) {
      setError(e.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(chunkId: string) {
    if (!confirm("Delete this chunk from the knowledge base?")) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteKnowledgeChunk(chunkId);
      setChunks((prev) => {
        const next = prev.find((c) => c.chunk_id !== chunkId) || null;
        setSelectedId(next?.chunk_id || "");
        return prev.filter((c) => c.chunk_id !== chunkId);
      });
    } catch (e: any) {
      setError(e.message || "Delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/workspace")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Database className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight">Knowledge Base</h1>
            <p className="text-xs text-muted-foreground">
              Inspect, edit, and delete Qdrant chunks.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            {loading ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mb-4 flex items-center gap-2">
        <div className="relative w-full max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by proposal, section, or chunk text..."
            className="pl-9"
          />
        </div>
        <Badge tone="muted">{filtered.length} chunks</Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardContent className="pt-5">
            <div className="space-y-3">
              {loading ? (
                <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
                  <Spinner /> Loading chunks...
                </div>
              ) : filtered.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                  No chunks match your filter.
                </p>
              ) : (
                filtered.map((chunk) => {
                  const active = chunk.chunk_id === selectedId;
                  return (
                    <button
                      key={chunk.chunk_id}
                      onClick={() => setSelectedId(chunk.chunk_id)}
                      className={`w-full rounded-xl border p-4 text-left transition ${
                        active
                          ? "border-accent bg-accent/5"
                          : "border-border bg-card hover:bg-muted/40"
                      }`}
                    >
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge tone="accent">{chunk.source_proposal || "Unknown source"}</Badge>
                        {chunk.source_section && (
                          <Badge tone="muted">{chunk.source_section}</Badge>
                        )}
                        {chunk.proposal_family && (
                          <Badge tone="default">{chunk.proposal_family}</Badge>
                        )}
                        <Badge tone="muted">score {chunk.score.toFixed(3)}</Badge>
                      </div>
                      <p className="line-clamp-3 text-sm text-foreground/85">
                        {chunk.text || "(empty chunk)"}
                      </p>
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        {chunk.chunk_id}
                      </p>
                    </button>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 pt-5">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold">Chunk Editor</h2>
                <p className="text-xs text-muted-foreground">
                  Edit fields and save back to Qdrant.
                </p>
              </div>
              {draft && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => remove(draft.chunk_id)}
                  disabled={deleting}
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              )}
            </div>

            {!draft ? (
              <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                Select a chunk to inspect or edit it.
              </p>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Source Proposal</Label>
                  <Input
                    value={draft.source_proposal}
                    onChange={(e) =>
                      setDraft({ ...draft, source_proposal: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Source Section</Label>
                  <Input
                    value={draft.source_section}
                    onChange={(e) =>
                      setDraft({ ...draft, source_section: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Proposal Family</Label>
                  <Input
                    value={draft.proposal_family}
                    onChange={(e) =>
                      setDraft({ ...draft, proposal_family: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Chunk Text</Label>
                  <Textarea
                    rows={18}
                    value={draft.text}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] text-muted-foreground">
                    Chunk ID: {draft.chunk_id}
                  </p>
                  <Button onClick={save} disabled={saving}>
                    {saving ? <Spinner /> : <Pencil className="h-4 w-4" />}
                    Save changes
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
