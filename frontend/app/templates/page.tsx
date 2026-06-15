"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Copy,
  Save,
  RefreshCw,
  Layers,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ProposalTemplate, TemplateSection } from "@/lib/types";
import { uid } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";

export default function TemplatesPage() {
  const router = useRouter();
  const [discovered, setDiscovered] = useState<ProposalTemplate[]>([]);
  const [user, setUser] = useState<ProposalTemplate[]>([]);
  const [editing, setEditing] = useState<ProposalTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const res = await api.listTemplates();
      setDiscovered(res.discovered);
      setUser(res.user);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function rediscover() {
    setDiscovering(true);
    try {
      await api.discoverPatterns();
      await refresh();
    } finally {
      setDiscovering(false);
    }
  }

  function startNew() {
    setEditing({
      id: uid(),
      name: "New Template",
      proposal_family: "",
      origin: "user",
      support: 0,
      sections: [],
    });
  }

  function clone(t: ProposalTemplate) {
    setEditing({
      ...t,
      id: uid(),
      name: `${t.name} (copy)`,
      origin: "user",
      sections: t.sections.map((s) => ({ ...s })),
    });
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    try {
      await api.upsertTemplate(editing);
      setEditing(null);
      await refresh();
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    await api.deleteTemplate(id);
    await refresh();
  }

  function updateSection(i: number, patch: Partial<TemplateSection>) {
    if (!editing) return;
    const sections = editing.sections.map((s, idx) =>
      idx === i ? { ...s, ...patch } : s
    );
    setEditing({ ...editing, sections });
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-lg font-bold">Template Management</h1>
            <p className="text-sm text-muted-foreground">
              Patterns auto-discovered from your proposal corpus. Edit, clone, or
              create your own.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={rediscover} disabled={discovering}>
            {discovering ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
            Re-discover
          </Button>
          <Button size="sm" onClick={startNew}>
            <Plus className="h-4 w-4" /> New
          </Button>
        </div>
      </div>

      {editing && (
        <Card className="mb-6 border-accent/40">
          <CardContent className="space-y-4 pt-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Name</label>
                <Input
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">
                  Proposal Family
                </label>
                <Input
                  value={editing.proposal_family}
                  onChange={(e) =>
                    setEditing({ ...editing, proposal_family: e.target.value })
                  }
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">Sections</label>
              {editing.sections.map((s, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="w-5 text-center text-xs text-muted-foreground">
                    {i + 1}
                  </span>
                  <Input
                    value={s.title}
                    onChange={(e) => updateSection(i, { title: e.target.value })}
                    className="h-8"
                  />
                  <Input
                    value={s.keywords.join(", ")}
                    placeholder="keywords"
                    onChange={(e) =>
                      updateSection(i, {
                        keywords: e.target.value
                          .split(",")
                          .map((k) => k.trim())
                          .filter(Boolean),
                      })
                    }
                    className="h-8 max-w-[220px] text-xs"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() =>
                      setEditing({
                        ...editing,
                        sections: editing.sections.filter((_, idx) => idx !== i),
                      })
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              <Button
                variant="subtle"
                size="sm"
                onClick={() =>
                  setEditing({
                    ...editing,
                    sections: [
                      ...editing.sections,
                      { title: "New Section", keywords: [], description: "" },
                    ],
                  })
                }
              >
                <Plus className="h-4 w-4" /> Add section
              </Button>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button size="sm" onClick={save} disabled={saving}>
                {saving ? <Spinner /> : <Save className="h-4 w-4" />} Save Template
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Spinner /> Loading templates…
        </div>
      ) : (
        <div className="space-y-8">
          {user.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Your Templates
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {user.map((t) => (
                  <TemplateCard
                    key={t.id}
                    t={t}
                    onEdit={() => setEditing(t)}
                    onClone={() => clone(t)}
                    onDelete={() => remove(t.id)}
                  />
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              <Sparkles className="h-4 w-4" /> Discovered Patterns
            </h2>
            {discovered.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                No patterns yet. Attach your Qdrant DB and click Re-discover.
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {discovered.map((t) => (
                  <TemplateCard
                    key={t.id}
                    t={t}
                    onEdit={() => setEditing(t)}
                    onClone={() => clone(t)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

function TemplateCard({
  t,
  onEdit,
  onClone,
  onDelete,
}: {
  t: ProposalTemplate;
  onEdit: () => void;
  onClone: () => void;
  onDelete?: () => void;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-semibold">{t.name}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {t.proposal_family && <Badge tone="accent">{t.proposal_family}</Badge>}
              <Badge tone={t.origin === "user" ? "default" : "muted"}>
                {t.origin}
              </Badge>
              {t.origin === "discovered" && (
                <Badge tone="muted">
                  <Layers className="h-3 w-3" /> support {t.support}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <ol className="mt-3 space-y-0.5 text-xs text-foreground/80">
          {t.sections.map((s, i) => (
            <li key={i}>
              {i + 1}. {s.title}
            </li>
          ))}
        </ol>
        <div className="mt-3 flex gap-2 border-t border-border pt-3">
          <Button variant="outline" size="sm" onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" size="sm" onClick={onClone}>
            <Copy className="h-3.5 w-3.5" /> Clone
          </Button>
          {onDelete && (
            <Button variant="ghost" size="sm" onClick={onDelete}>
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
