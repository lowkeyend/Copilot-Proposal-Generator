"use client";

import { useEffect, useState } from "react";
import { History, RotateCcw, Copy, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { SectionResult, VersionMeta } from "@/lib/types";
import { Drawer } from "./ui/drawer";
import { Button } from "./ui/button";
import { Spinner } from "./ui/spinner";

export function VersionPanel({
  open,
  onClose,
  proposalId,
  currentSections,
  onRestore,
}: {
  open: boolean;
  onClose: () => void;
  proposalId: string | null;
  currentSections: SectionResult[];
  onRestore: (sections: SectionResult[]) => void;
}) {
  const [versions, setVersions] = useState<VersionMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");

  async function refresh() {
    if (!proposalId) return;
    setLoading(true);
    try {
      const res = await api.listVersions(proposalId);
      setVersions(res.versions);
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, proposalId]);

  async function handleSave() {
    if (!proposalId) return;
    setBusy("save");
    try {
      await api.saveVersion(proposalId, currentSections, "Manual save");
      await refresh();
    } finally {
      setBusy("");
    }
  }

  async function handleRestore(v: VersionMeta) {
    if (!proposalId) return;
    setBusy(v.version_id);
    try {
      const full = await api.getVersion(proposalId, v.version_id);
      onRestore(full.sections);
    } finally {
      setBusy("");
    }
  }

  async function handleDuplicate(v: VersionMeta) {
    if (!proposalId) return;
    setBusy(v.version_id);
    try {
      await api.duplicateVersion(proposalId, v.version_id);
      await refresh();
    } finally {
      setBusy("");
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Version History" width="max-w-md">
      {!proposalId ? (
        <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          Generate the proposal first to start tracking versions.
        </p>
      ) : (
        <div className="space-y-3">
          <Button
            size="sm"
            className="w-full"
            onClick={handleSave}
            disabled={busy === "save"}
          >
            {busy === "save" ? <Spinner /> : <Save className="h-4 w-4" />}
            Save current as new version
          </Button>

          {loading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Spinner /> Loading versions…
            </div>
          ) : versions.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No versions yet.
            </p>
          ) : (
            versions
              .slice()
              .reverse()
              .map((v) => (
                <div
                  key={v.version_id}
                  className="rounded-lg border border-border bg-card p-3"
                >
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <History className="h-4 w-4 text-muted-foreground" />
                    {v.label}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {new Date(v.created_at).toLocaleString()} · {v.sections}{" "}
                    sections
                  </p>
                  <div className="mt-2 flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRestore(v)}
                      disabled={busy === v.version_id}
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Restore
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDuplicate(v)}
                      disabled={busy === v.version_id}
                    >
                      <Copy className="h-3.5 w-3.5" /> Duplicate
                    </Button>
                  </div>
                </div>
              ))
          )}
        </div>
      )}
    </Drawer>
  );
}
