"use client";

import { FileText, Layers } from "lucide-react";
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
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
                {c.text || "(empty chunk)"}
              </p>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
