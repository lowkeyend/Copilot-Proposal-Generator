"use client";

import { ChevronUp, ChevronDown, Trash2, Plus, GripVertical } from "lucide-react";
import { useProposalStore } from "@/lib/store";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

export function TocEditor() {
  const { toc, addTocSection, updateTocSection, removeTocSection, moveTocSection } =
    useProposalStore();

  return (
    <div className="space-y-2">
      {toc.length === 0 && (
        <p className="rounded-md border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
          No sections yet. Add one to build your generation plan.
        </p>
      )}
      {toc.map((s, i) => (
        <div
          key={s.id}
          className="flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1.5"
        >
          <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="w-5 text-center text-xs text-muted-foreground">
            {i + 1}
          </span>
          <Input
            value={s.title}
            onChange={(e) => updateTocSection(s.id, { title: e.target.value })}
            className="h-8 border-transparent bg-transparent px-1 text-sm focus-visible:border-input focus-visible:bg-card"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={i === 0}
            onClick={() => moveTocSection(s.id, -1)}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={i === toc.length - 1}
            onClick={() => moveTocSection(s.id, 1)}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => removeTocSection(s.id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        variant="subtle"
        size="sm"
        className="w-full"
        onClick={() => addTocSection()}
      >
        <Plus className="h-4 w-4" /> Add Section
      </Button>
    </div>
  );
}
