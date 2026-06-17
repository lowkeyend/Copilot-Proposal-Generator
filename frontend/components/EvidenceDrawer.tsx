"use client";

import { useState } from "react";
import { FileText, Layers, Search, X } from "lucide-react";
import type { SectionResult } from "@/lib/types";
import { Drawer } from "./ui/drawer";
import { Badge } from "./ui/badge";

export function EvidenceDrawer({
  section,
  open,
  onClose,
}: {
  section: SectionResult | null;
  open: boolean;
  onClose: () => void;
}) {
  const [focused, setFocused] = useState<number | null>(null);
  const focusedChunk =
    focused !== null && section ? section.evidence[focused] : null;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={section ? `Evidence — ${section.title}` : "Evidence"}
    >
      {!section || section.evidence.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No retrieved evidence for this section.
          <br />
          <span className="text-xs">
            This means the retrieval step returned no chunks for this section,
            or the backend could not reach the knowledge base. Content was
            written from best practice.
          </span>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            {section.evidence.length} chunk(s) retrieved from your proposal
            knowledge base and used to ground this section.
          </p>
          {section.evidence.map((c, i) => (
            <div
              key={c.chunk_id || i}
              className="rounded-lg border border-border bg-background p-3"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone={c.source_type?.includes("temenos") ? "warning" : "accent"}>
                  {c.source_type?.includes("temenos") ? "Temenos web" : "Document"}
                </Badge>
                <Badge tone="default">{c.summary || `Chunk ${i + 1}`}</Badge>
                <Badge tone="accent">
                  <FileText className="h-3 w-3" />
                  {c.source_proposal || "unknown source"}
                </Badge>
                {c.source_section && (
                  <Badge tone="muted">
                    <Layers className="h-3 w-3" />
                    {c.source_section}
                  </Badge>
                )}
                <Badge tone="default">score {c.score.toFixed(3)}</Badge>
              </div>
              <p className="line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
                {c.text || "(empty chunk)"}
              </p>
              <button
                type="button"
                onClick={() => setFocused(i)}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent underline-offset-2 hover:underline"
              >
                <Search className="h-3 w-3" />
                Inspect chunk text
              </button>
            </div>
          ))}
          {focusedChunk && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
              <div className="max-h-[82vh] w-full max-w-3xl overflow-hidden rounded-lg border border-border bg-background shadow-xl">
                <div className="flex items-start justify-between gap-3 border-b border-border p-4">
                  <div>
                    <h3 className="text-sm font-semibold">
                      {focusedChunk.summary || "Evidence chunk"}
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {focusedChunk.source_proposal || "unknown source"}
                      {focusedChunk.source_section ? ` / ${focusedChunk.source_section}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setFocused(null)}
                    className="rounded-md p-2 hover:bg-muted"
                    aria-label="Close evidence preview"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="max-h-[64vh] overflow-y-auto p-4">
                  <p className="whitespace-pre-wrap text-sm leading-7 text-foreground/90">
                    {focusedChunk.text}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
