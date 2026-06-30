"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Database, FileText, Pencil, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBaseChunk } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Textarea, Label } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

type DocumentGroup = {
  name: string;
  chunks: KnowledgeBaseChunk[];
  count: number;
  families: string[];
  sections: string[];
};

export default function KnowledgeBasePage() {
  const router = useRouter();
  const [chunks, setChunks] = useState<KnowledgeBaseChunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [documentFilter, setDocumentFilter] = useState("__all__");
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<KnowledgeBaseChunk | null>(null);
  const [view, setView] = useState<"browse" | "upload">("browse");
  const [files, setFiles] = useState<File[]>([]);
  const [sourceProposal, setSourceProposal] = useState("");
  const [sourceSection, setSourceSection] = useState("");
  const [proposalFamily, setProposalFamily] = useState("Uploaded Knowledge");
  const [totalPoints, setTotalPoints] = useState(0);

  async function load() {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const [status, res] = await Promise.all([api.status(), api.listKnowledgeChunks(5000)]);
      setTotalPoints(status.points || res.chunks.length);
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("view") === "upload") setView("upload");
  }, []);

  const documents = useMemo<DocumentGroup[]>(() => {
    const grouped = new Map<string, KnowledgeBaseChunk[]>();
    for (const chunk of chunks) {
      const key = chunk.source_document || "Untitled Document";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(chunk);
    }
    return Array.from(grouped.entries())
      .map(([name, items]) => ({
        name,
        chunks: items,
        count: items.length,
        families: Array.from(new Set(items.map((item) => item.proposal_family).filter(Boolean))),
        sections: Array.from(new Set(items.map((item) => item.source_section).filter(Boolean))),
      }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [chunks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return chunks.filter((chunk) => {
      const docName = chunk.source_document || "Untitled Document";
      const matchesDoc = documentFilter === "__all__" || docName === documentFilter;
      const matchesQuery =
        !q ||
        [
          chunk.summary,
          chunk.text,
          chunk.source_proposal,
          chunk.source_section,
          chunk.source_document,
          chunk.proposal_family,
          chunk.chunk_id,
        ]
          .join(" ")
          .toLowerCase()
          .includes(q);
      return matchesDoc && matchesQuery;
    });
  }, [chunks, query, documentFilter]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId("");
      setDraft(null);
      return;
    }
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
        source_document: draft.source_document,
      });
      setChunks((prev) => prev.map((c) => (c.chunk_id === updated.chunk_id ? updated : c)));
      setDraft(updated);
      setNotice("Chunk saved.");
    } catch (e: any) {
      setError(e.message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function removeChunk(chunkId: string) {
    if (!confirm("Delete this chunk from the knowledge base?")) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteKnowledgeChunk(chunkId);
      setChunks((prev) => {
        const next = prev.filter((c) => c.chunk_id !== chunkId);
        const current = next.find((c) => c.chunk_id === selectedId) || null;
        setSelectedId(current?.chunk_id || next[0]?.chunk_id || "");
        return next;
      });
      setNotice("Chunk deleted.");
    } catch (e: any) {
      setError(e.message || "Delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  async function removeDocument(documentName: string) {
    const target = chunks.filter((chunk) => (chunk.source_document || "Untitled Document") === documentName);
    if (!target.length) return;
    if (!confirm(`Delete "${documentName}" and all ${target.length} related chunks?`)) return;
    setDeleting(true);
    setError("");
    try {
      await Promise.all(target.map((chunk) => api.deleteKnowledgeChunk(chunk.chunk_id)));
      setChunks((prev) => prev.filter((chunk) => (chunk.source_document || "Untitled Document") !== documentName));
      if (documentFilter === documentName) setDocumentFilter("__all__");
      setSelectedId("");
      setDraft(null);
      setNotice(`Deleted "${documentName}" and its chunks.`);
    } catch (e: any) {
      setError(e.message || "Document delete failed.");
    } finally {
      setDeleting(false);
    }
  }

  async function uploadFiles() {
    if (files.length === 0) {
      setError("Choose at least one file to upload.");
      return;
    }
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const res = await api.uploadKnowledgeFiles(files, {
        source_proposal: sourceProposal,
        source_section: sourceSection,
        proposal_family: proposalFamily,
      });
      setNotice(`Uploaded ${res.files.length} file(s) and wrote ${res.chunks_written} chunks to ${res.collection}.`);
      setFiles([]);
      setSourceProposal("");
      setSourceSection("");
      setProposalFamily("Uploaded Knowledge");
      await load();
      setView("browse");
    } catch (e: any) {
      setError(e.message || "Upload failed.");
    } finally {
      setUploading(false);
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
              Uploaded documents first, then the chunks inside each document.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="muted">{totalPoints.toLocaleString()} total chunks</Badge>
          <Button variant="outline" onClick={load} disabled={loading}>
            {loading ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}
      {notice ? (
        <p className="mb-4 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">{notice}</p>
      ) : null}

      <div className="mb-4 flex items-center gap-2">
        <Button variant={view === "browse" ? "default" : "outline"} size="sm" onClick={() => setView("browse")}>
          <Database className="h-4 w-4" />
          Browse Documents
        </Button>
        <Button variant={view === "upload" ? "default" : "outline"} size="sm" onClick={() => setView("upload")}>
          <Upload className="h-4 w-4" />
          Add Documents
        </Button>
      </div>

      {view === "upload" ? (
        <Card>
          <CardContent className="space-y-4 pt-5">
            <div>
            <h2 className="text-sm font-semibold">Upload Knowledge Files</h2>
            <p className="text-xs text-muted-foreground">
              Upload `.docx`, `.pdf`, `.txt`, or `.md` files. They will be chunked, embedded in Qdrant Cloud, and immediately available to retrieval.
            </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Source Proposal</Label>
                <Input value={sourceProposal} onChange={(e) => setSourceProposal(e.target.value)} placeholder="Temenos delivery playbook" />
              </div>
              <div className="space-y-1.5">
                <Label>Source Section</Label>
                <Input value={sourceSection} onChange={(e) => setSourceSection(e.target.value)} placeholder="Implementation methodology" />
              </div>
              <div className="space-y-1.5">
                <Label>Proposal Family</Label>
                <Input value={proposalFamily} onChange={(e) => setProposalFamily(e.target.value)} placeholder="Uploaded Knowledge" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Files</Label>
              <Input type="file" multiple accept=".docx,.pdf,.txt,.md" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
              <p className="text-xs text-muted-foreground">
                {files.length ? `${files.length} file(s) selected.` : "No files selected yet."}
              </p>
            </div>
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Uploaded chunks are written into the live Qdrant Cloud collection.
              </p>
              <Button onClick={uploadFiles} disabled={uploading}>
                {uploading ? <Spinner /> : <Upload className="h-4 w-4" />}
                Upload to Knowledge Base
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <button
              type="button"
              onClick={() => setDocumentFilter("__all__")}
              className={`rounded-2xl border p-4 text-left transition ${
                documentFilter === "__all__" ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <FileText className="h-4 w-4" />
                  All documents
                </div>
                <Badge tone="muted">{chunks.length}</Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">Browse every uploaded chunk across the knowledge base.</p>
            </button>
            {documents.map((doc) => (
              <div
                key={doc.name}
                className={`rounded-2xl border p-4 transition ${
                  documentFilter === doc.name ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted/40"
                }`}
              >
                <button type="button" onClick={() => setDocumentFilter(doc.name)} className="w-full text-left">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <FileText className="h-4 w-4" />
                        <span className="line-clamp-2">{doc.name}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{doc.count} chunks • {doc.sections.length} sections</div>
                    </div>
                    <Badge tone="muted">{doc.families[0] || "Uploaded"}</Badge>
                  </div>
                </button>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <p className="text-[11px] text-muted-foreground">{doc.sections.slice(0, 2).join(" • ") || "No section metadata"}</p>
                  <Button variant="destructive" size="sm" onClick={() => removeDocument(doc.name)} disabled={deleting}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

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
            {documentFilter !== "__all__" ? (
              <Button variant="outline" size="sm" onClick={() => setDocumentFilter("__all__")}>
                Clear document filter
              </Button>
            ) : null}
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
                            active ? "border-accent bg-accent/5" : "border-border bg-card hover:bg-muted/40"
                          }`}
                        >
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <Badge tone="accent">{chunk.summary || "Untitled chunk"}</Badge>
                            <Badge tone="muted">{chunk.source_proposal || "Unknown source"}</Badge>
                            {chunk.source_document ? <Badge tone="muted">{chunk.source_document}</Badge> : null}
                            {chunk.source_section ? <Badge tone="muted">{chunk.source_section}</Badge> : null}
                            {chunk.proposal_family ? <Badge tone="default">{chunk.proposal_family}</Badge> : null}
                            <Badge tone="muted">score {chunk.score.toFixed(3)}</Badge>
                          </div>
                          <p className="line-clamp-3 text-sm text-foreground/85">{chunk.text || "(empty chunk)"}</p>
                          <p className="mt-2 text-[11px] text-muted-foreground">{chunk.chunk_id}</p>
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
                    <p className="text-xs text-muted-foreground">Edit fields and save back to Qdrant.</p>
                  </div>
                  {draft ? (
                    <Button variant="destructive" size="sm" onClick={() => removeChunk(draft.chunk_id)} disabled={deleting}>
                      {deleting ? <Spinner /> : <Trash2 className="h-4 w-4" />}
                      Delete Chunk
                    </Button>
                  ) : null}
                </div>

                {!draft ? (
                  <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                    Select a chunk to inspect or edit it.
                  </p>
                ) : (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label>Source Proposal</Label>
                      <Input value={draft.source_proposal} onChange={(e) => setDraft({ ...draft, source_proposal: e.target.value })} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Source Document</Label>
                      <Input value={draft.source_document} onChange={(e) => setDraft({ ...draft, source_document: e.target.value })} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Source Section</Label>
                      <Input value={draft.source_section} onChange={(e) => setDraft({ ...draft, source_section: e.target.value })} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Proposal Family</Label>
                      <Input value={draft.proposal_family} onChange={(e) => setDraft({ ...draft, proposal_family: e.target.value })} />
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
                      <p className="text-[11px] text-muted-foreground">Chunk ID: {draft.chunk_id}</p>
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
        </>
      )}
    </main>
  );
}
