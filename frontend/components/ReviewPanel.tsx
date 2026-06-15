"use client";

import { AlertTriangle, Info, XCircle, ShieldCheck } from "lucide-react";
import type { ReviewIssue } from "@/lib/types";
import { Drawer } from "./ui/drawer";
import { Badge } from "./ui/badge";
import { Spinner } from "./ui/spinner";

const ICONS = {
  info: <Info className="h-4 w-4 text-sky-500" />,
  warning: <AlertTriangle className="h-4 w-4 text-amber-500" />,
  error: <XCircle className="h-4 w-4 text-red-500" />,
};

export function ReviewPanel({
  open,
  onClose,
  loading,
  issues,
  summary,
}: {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  issues: ReviewIssue[];
  summary: string;
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Consistency Review" width="max-w-lg">
      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Spinner /> Reviewing client name, terminology, tone & coherence…
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-md bg-muted p-3 text-sm">
            <ShieldCheck className="h-4 w-4 text-accent" />
            {summary || "No review run yet."}
          </div>
          {issues.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              No issues found.
            </p>
          ) : (
            issues.map((issue, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {ICONS[issue.severity]}
                    {issue.category}
                  </div>
                  {issue.section_title && (
                    <Badge tone="muted">{issue.section_title}</Badge>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-foreground/80">
                  {issue.message}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </Drawer>
  );
}
