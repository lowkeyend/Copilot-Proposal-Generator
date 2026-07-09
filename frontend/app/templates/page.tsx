"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Upload } from "lucide-react";
import { api } from "@/lib/api";
import type { TemplateDocumentArtifact } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";

export default function TemplatesPage() {
  const router = useRouter();
  const [artifacts, setArtifacts] = useState<TemplateDocumentArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [parsing, setParsing] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const res = await api.listTemplates();
      setArtifacts((res.artifacts || []).sort((a, b) =>
        `${a.proposal_family} ${a.name}`.localeCompare(`${b.proposal_family} ${b.name}`)
      ));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onParseTemplate(file: File | null) {
    if (!file) return;
    setParsing(true);
    try {
      await api.parseTemplate(file);
      await refresh();
    } finally {
      setParsing(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-lg font-bold">Template Management</h1>
            <p className="text-sm text-muted-foreground">
              Parsed DOCX templates only. These are the templates available in Workspace.
            </p>
          </div>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <Upload className="h-4 w-4" />
          {parsing ? "Parsing…" : "Parse DOCX"}
          <input
            type="file"
            accept=".docx"
            className="hidden"
            onChange={(e) => onParseTemplate(e.target.files?.[0] || null)}
          />
        </label>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Spinner /> Loading templates…
        </div>
      ) : artifacts.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {artifacts.map((artifact) => (
            <Card key={artifact.template_id} className="border-border/70">
              <CardContent className="space-y-2 pt-5">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{artifact.name || "Untitled template"}</div>
                  <Badge tone="accent">{artifact.proposal_family || "General"}</Badge>
                </div>
                <div className="text-xs text-muted-foreground break-all">
                  {artifact.source_file}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge tone="muted">{artifact.sections?.length || 0} sections</Badge>
                  <Badge tone="muted">{artifact.images?.length || 0} images</Badge>
                  <Badge tone="muted">{Number((artifact.metadata as Record<string, unknown>)?.paragraphs || 0)} paragraphs</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Use this template from Workspace to generate proposals from the parsed DOCX structure.
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No parsed templates yet. Upload a DOCX to register it.
          </CardContent>
        </Card>
      )}
    </main>
  );
}
