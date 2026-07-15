"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Lock,
  Unlock,
  RefreshCw,
  Pencil,
  Trash2,
  ChevronUp,
  ChevronDown,
  BookOpen,
  Check,
  X,
} from "lucide-react";
import type { SectionResult } from "@/lib/types";
import { renderMarkdown } from "@/lib/markdown";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Input, Textarea } from "./ui/input";
import { Spinner } from "./ui/spinner";

interface Props {
  section: SectionResult;
  index: number;
  total: number;
  busy: boolean;
  onRegenerate: (instruction: string) => void;
  onToggleLock: () => void;
  onDelete: () => void;
  onMove: (dir: -1 | 1) => void;
  onEdit: (patch: Partial<SectionResult>) => void;
  onShowEvidence: () => void;
  onReplaceImage: (imageIndex: number, file: File | null) => void;
  onDeleteImage: (imageIndex: number) => void;
}

const CLOUD_BASE = "https://fawadsidd17-proposal-copilot-backend.hf.space";

function assetUrl(path: string) {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app")) {
    return `${CLOUD_BASE}${path}`;
  }
  return `http://localhost:8000${path}`;
}

export function SectionCard({
  section,
  index,
  total,
  busy,
  onRegenerate,
  onToggleLock,
  onDelete,
  onMove,
  onEdit,
  onShowEvidence,
  onReplaceImage,
  onDeleteImage,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.content);
  const [titleDraft, setTitleDraft] = useState(section.title);
  const [instruction, setInstruction] = useState("");
  const [showInstruction, setShowInstruction] = useState(false);

  function saveEdit() {
    onEdit({ content: draft, title: titleDraft });
    setEditing(false);
  }

  const renderedImages = new Map<number, number>();

  function renderBlockImage(blockImage: NonNullable<SectionResult["blocks"]>[number]["image"]) {
    if (!blockImage) return null;
    const key = blockImage.index;
    const count = renderedImages.get(key) ?? 0;
    renderedImages.set(key, count + 1);
    return (
      <div key={`image-${blockImage.index}-${count}`} className="my-4 overflow-hidden rounded-2xl border border-border bg-muted/10 p-3">
        <img
          src={assetUrl(blockImage.asset_url)}
          alt={blockImage.caption || blockImage.filename || section.title}
          className="max-h-[360px] w-full rounded-xl object-contain"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs text-muted-foreground">{blockImage.caption || blockImage.filename}</div>
          <div className="flex items-center gap-2">
            <label className="cursor-pointer rounded-md border border-border px-3 py-1 text-xs hover:bg-white">
              Replace PNG
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.gif,.webp"
                className="hidden"
                onChange={(e) => onReplaceImage(blockImage.index, e.target.files?.[0] || null)}
              />
            </label>
            <Button variant="outline" size="sm" onClick={() => onDeleteImage(blockImage.index)}>
              Delete Picture
            </Button>
          </div>
        </div>
      </div>
    );
  }

  function renderBlocks() {
    if (!section.blocks?.length) {
      return (
        <div
          className="prose-proposal max-h-[420px] overflow-y-auto scroll-thin text-sm"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(section.content) }}
        />
      );
    }
    return (
      <div className="max-h-[720px] overflow-y-auto scroll-thin text-sm">
        <div className="space-y-3">
          {section.blocks.map((block, idx) => {
            if (block.kind === "heading") {
              const Tag = block.heading_level <= 1 ? "h2" : block.heading_level === 2 ? "h3" : "h4";
              return (
                <Tag
                  key={block.block_id || `${block.kind}-${idx}`}
                  className={
                    block.heading_level <= 1
                      ? "mt-1 text-xl font-bold text-primary"
                      : block.heading_level === 2
                        ? "text-lg font-semibold text-slate-900"
                        : "text-base font-semibold text-slate-800"
                  }
                >
                  {block.text}
                </Tag>
              );
            }
            if (block.kind === "paragraph") {
              return (
                <p key={block.block_id || `${block.kind}-${idx}`} className="leading-7 text-slate-700">
                  {block.text}
                </p>
              );
            }
            if (block.kind === "list") {
              const items = block.items?.length ? block.items : block.text.split(/\n+/).filter(Boolean);
              return (
                <ul key={block.block_id || `${block.kind}-${idx}`} className="list-disc space-y-1 pl-5 text-slate-700">
                  {items.map((item, itemIndex) => (
                    <li key={`${block.block_id || idx}-${itemIndex}`}>{item}</li>
                  ))}
                </ul>
              );
            }
            if (block.kind === "table") {
              const rows = block.table_rows || [];
              if (!rows.length) return null;
              return (
                <div key={block.block_id || `${block.kind}-${idx}`} className="overflow-hidden rounded-xl border border-border">
                  <table className="w-full border-collapse text-left text-[13px]">
                    <tbody>
                      {rows.map((row, rowIndex) => (
                        <tr key={`${block.block_id || idx}-row-${rowIndex}`} className={rowIndex === 0 ? "bg-muted/40" : "bg-white"}>
                          {row.map((cell, cellIndex) => (
                            <td key={`${block.block_id || idx}-cell-${rowIndex}-${cellIndex}`} className="border border-border px-3 py-2 align-top">
                              <span className={rowIndex === 0 ? "font-semibold text-slate-900" : "text-slate-700"}>{cell}</span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            }
            if (block.kind === "image") {
              return renderBlockImage(block.image);
            }
            return null;
          })}
        </div>
      </div>
    );
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <Card className={section.locked ? "border-accent/40" : ""}>
        <div className="flex items-start justify-between gap-3 border-b border-border p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
              {index + 1}
            </span>
            <div>
              {editing ? (
                <Input
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  className="h-8 text-sm font-semibold"
                />
              ) : (
                <h3 className="font-semibold">{section.title}</h3>
              )}
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {section.locked && (
                  <Badge tone="accent">
                    <Lock className="h-3 w-3" /> Locked
                  </Badge>
                )}
                {section.evidence.length > 0 && (
                  <Badge tone="muted">{section.evidence.length} sources</Badge>
                )}
                {section.model && (
                  <Badge tone="muted">{section.model}</Badge>
                )}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              title="Move up"
              disabled={index === 0}
              onClick={() => onMove(-1)}
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Move down"
              disabled={index === total - 1}
              onClick={() => onMove(1)}
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Evidence"
              onClick={onShowEvidence}
            >
              <BookOpen className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title={section.locked ? "Unlock" : "Lock"}
              onClick={onToggleLock}
            >
              {section.locked ? (
                <Unlock className="h-4 w-4" />
              ) : (
                <Lock className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Delete"
              onClick={onDelete}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="p-4">
          {editing ? (
            <div className="space-y-2">
              <Textarea
                rows={14}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="font-mono text-xs"
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  <X className="h-4 w-4" /> Cancel
                </Button>
                <Button size="sm" onClick={saveEdit}>
                  <Check className="h-4 w-4" /> Save
                </Button>
              </div>
            </div>
          ) : busy ? (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <Spinner /> Generating…
            </div>
          ) : section.content ? (
            renderBlocks()
          ) : (
            <p className="py-6 text-sm text-muted-foreground">
              Not generated yet.
            </p>
          )}

          {!editing && (
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(true)}
                disabled={busy}
              >
                <Pencil className="h-4 w-4" /> Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={section.locked || busy}
                onClick={() => setShowInstruction((v) => !v)}
                title={section.locked ? "Unlock to generate" : "Generate"}
              >
                <RefreshCw className="h-4 w-4" /> Generate
              </Button>
            </div>
          )}

          {showInstruction && !editing && (
            <div className="mt-3 space-y-2 rounded-md border border-border bg-muted/40 p-3">
              <Input
                placeholder='Optional prompt, e.g. "change R16 to R26"'
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowInstruction(false)}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    onRegenerate(instruction);
                    setShowInstruction(false);
                    setInstruction("");
                  }}
                >
                  <RefreshCw className="h-4 w-4" /> Generate
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>
    </motion.div>
  );
}
