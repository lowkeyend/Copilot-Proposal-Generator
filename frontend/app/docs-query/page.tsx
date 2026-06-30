"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot, FileText, Search, Send } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type { ChatMessage, EvidenceChunk, KnowledgeBaseChunk } from "@/lib/types";
import { DropdownMultiSelect } from "@/components/DropdownMultiSelect";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Textarea, Label } from "@/components/ui/input";

function shortExcerpt(text: string, maxWords = 28) {
  const words = text.split(/\s+/).filter(Boolean);
  return words.length <= maxWords ? text : `${words.slice(0, maxWords).join(" ")}...`;
}

export default function DocsQueryPage() {
  const store = useProposalStore();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [answer, setAnswer] = useState("");
  const [evidence, setEvidence] = useState<EvidenceChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [docs, setDocs] = useState<string[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>(store.context.selected_documents || []);

  useEffect(() => {
    api
      .listKnowledgeChunks(500)
      .then((res) => {
        const names = Array.from(
          new Set(
            res.chunks
              .map((chunk: KnowledgeBaseChunk) => chunk.source_document || chunk.source_proposal)
              .filter(Boolean)
          )
        );
        setDocs(names);
        setSelectedDocs((current) =>
          current.length ? current.filter((doc) => names.includes(doc)) : (store.context.selected_documents || []).filter((doc) => names.includes(doc))
        );
      })
      .catch(() => setDocs([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.context.selected_documents]);

  const promptHint = useMemo(
    () =>
      selectedDocs.length
        ? `Filter active: ${selectedDocs.join(", ")}`
        : "No document filter selected. Retrieval will search the full KB.",
    [selectedDocs]
  );

  async function submit() {
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await api.queryDocs({
        question,
        history,
        document_names: selectedDocs,
        top_k: 8,
      });
      setHistory((prev) => [
        ...prev,
        { role: "user", content: question },
        { role: "assistant", content: res.answer },
      ]);
      setAnswer(res.answer);
      setEvidence(res.evidence);
      setQuestion("");
    } catch (e: any) {
      setError(e.message || "Query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[1fr_0.9fr]">
      <Card className="min-h-[76vh]">
        <CardContent className="flex h-full flex-col gap-4 pt-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold">Query from Doc</h1>
              <p className="text-xs text-muted-foreground">
                Ask directly about any uploaded document. The answer is grounded in retrieved chunks only.
              </p>
            </div>
          </div>

          <DropdownMultiSelect
            label="Filter documents"
            options={docs}
            value={selectedDocs}
            onChange={setSelectedDocs}
            placeholder="Choose documents to narrow search"
            helper={promptHint}
          />

          <div className="flex-1 space-y-2 rounded-2xl border border-border bg-muted/20 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Search className="h-4 w-4" />
              Conversation
            </div>
            <div className="max-h-[48vh] space-y-3 overflow-auto pr-1">
              {history.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Ask a question about a specific uploaded document or the full knowledge base.
                </p>
              ) : (
                history.map((msg, index) => (
                  <div
                    key={`${msg.role}-${index}`}
                    className={
                      msg.role === "user"
                        ? "ml-auto max-w-[85%] rounded-2xl bg-primary px-4 py-3 text-sm text-primary-foreground"
                        : "mr-auto max-w-[85%] rounded-2xl border border-border bg-card px-4 py-3 text-sm"
                    }
                  >
                    {msg.content}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Your question</Label>
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What does Maidaan say about implementation phases?"
              rows={4}
            />
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          <Button onClick={submit} disabled={loading || !question.trim()} className="self-start">
            {loading ? "Searching..." : "Ask from docs"}
            <Send className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              <h2 className="font-semibold">Answer</h2>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
              {answer || "The answer will appear here after retrieval."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-5">
            <details className="group space-y-3">
              <summary className="cursor-pointer list-none font-semibold">
                Evidence used {evidence.length ? `(${evidence.length})` : ""}
                <span className="ml-2 text-xs text-muted-foreground">
                  Click to inspect source snippets
                </span>
              </summary>
              <div className="mt-3 space-y-3">
                {evidence.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Source snippets will appear here after retrieval.
                  </p>
                ) : (
                  evidence.map((chunk, index) => (
                    <div key={chunk.chunk_id || index} className="rounded-2xl border border-border p-3">
                      <div className="text-sm font-medium">
                        {chunk.source_document || chunk.source_proposal || `Source ${index + 1}`}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {chunk.source_section || "Unknown section"}
                      </p>
                      <p className="mt-2 text-sm leading-6">{shortExcerpt(chunk.text, 24)}</p>
                    </div>
                  ))
                )}
              </div>
            </details>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
