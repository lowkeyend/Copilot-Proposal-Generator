"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Sparkles,
  ShieldCheck,
  History,
  Download,
  FileText,
  Layers3,
  Database,
  Globe2,
  SlidersHorizontal,
} from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type { ReviewIssue, SectionResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { TocEditor } from "@/components/TocEditor";
import { SectionCard } from "@/components/SectionCard";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ReviewPanel } from "@/components/ReviewPanel";
import { VersionPanel } from "@/components/VersionPanel";
import { KbStatus } from "@/components/KbStatus";

export default function WorkspacePage() {
  const router = useRouter();
  const store = useProposalStore();
  const [models] = useState(["deepseek/deepseek-chat", "qwen/qwen3-32b"]);

  const [busySection, setBusySection] = useState<string | null>(null);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState("");

  // drawers
  const [evidenceFor, setEvidenceFor] = useState<SectionResult | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [issues, setIssues] = useState<ReviewIssue[]>([]);
  const [reviewSummary, setReviewSummary] = useState("");
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportUrl, setExportUrl] = useState("");

  const title = useMemo(
    () =>
      store.context.client_name
        ? `${store.context.project_type || "Proposal"} — ${store.context.client_name}`
        : store.context.project_type || "Untitled Proposal",
    [store.context]
  );

  const baseReq = () => ({
    prompt: store.prompt,
    context: store.context,
    proposal_family: store.proposalFamily,
    model: store.model,
  });

  async function genOne(tocId: string, instruction = ""): Promise<SectionResult> {
    const toc = store.toc.find((t) => t.id === tocId);
    const existing = store.sections.find((s) => s.id === tocId);
    const sectionTitle = toc?.title || existing?.title || "Section";
    const res = await api.generateSection({
      section_title: sectionTitle,
      keywords: toc?.keywords || [],
      context: store.context,
      proposal_family: store.proposalFamily,
      prompt: store.prompt,
      pattern_guidance: toc?.description || "",
      instruction,
      model: store.model,
      top_k: store.quality.top_k,
      include_temenos_official: store.quality.include_temenos_official,
      use_hybrid_retrieval: store.quality.use_hybrid_retrieval,
      detail_level: store.quality.detail_level,
      require_evidence: store.quality.require_evidence,
    });
    res.id = tocId;
    if (existing?.locked) res.locked = true;
    return res;
  }

  async function generateAll() {
    setError("");
    if (store.toc.length === 0) {
      setError("Add at least one section to the plan first.");
      return;
    }
    setGeneratingAll(true);
    const targets = store.toc.filter((t) => {
      const s = store.sections.find((x) => x.id === t.id);
      return !s?.locked;
    });
    setProgress({ done: 0, total: targets.length });

    // Seed placeholders in TOC order so cards appear immediately.
    const seeded: SectionResult[] = store.toc.map((t) => {
      const ex = store.sections.find((s) => s.id === t.id);
      return (
        ex || {
          id: t.id,
          title: t.title,
          content: "",
          evidence: [],
          locked: false,
          model: "",
          generated_at: "",
        }
      );
    });
    store.setSections(seeded);
    const generatedSections = [...seeded];

    try {
      for (let i = 0; i < targets.length; i++) {
        const t = targets[i];
        setBusySection(t.id);
        const res = await genOne(t.id);
        store.upsertSection(res);
        const existingIndex = generatedSections.findIndex((s) => s.id === res.id);
        if (existingIndex >= 0) {
          generatedSections[existingIndex] = res;
        } else {
          generatedSections.push(res);
        }
        setProgress({ done: i + 1, total: targets.length });
      }
      // persist a saved proposal + initial version
      const persisted = await api.persistProposal(
        {
          prompt: store.prompt,
          context: store.context,
          proposal_family: store.proposalFamily,
          toc: store.toc,
          model: store.model,
          top_k: store.quality.top_k,
          include_temenos_official: store.quality.include_temenos_official,
          use_hybrid_retrieval: store.quality.use_hybrid_retrieval,
          detail_level: store.quality.detail_level,
          require_evidence: store.quality.require_evidence,
        },
        generatedSections
      );
      store.setProposalId(persisted.proposal_id);
      store.setSections(persisted.sections);
    } catch (e: any) {
      setError(e.message || "Generation failed.");
    } finally {
      setBusySection(null);
      setGeneratingAll(false);
    }
  }

  async function regenerate(sectionId: string, instruction: string) {
    setError("");
    setBusySection(sectionId);
    try {
      const res = await genOne(sectionId, instruction);
      store.upsertSection(res);
    } catch (e: any) {
      setError(e.message || "Regeneration failed.");
    } finally {
      setBusySection(null);
    }
  }

  async function runReview() {
    setReviewOpen(true);
    setReviewLoading(true);
    try {
      const res = await api.reviewProposal({
        context: store.context,
        sections: store.sections,
        model: store.model,
      });
      setIssues(res.issues);
      setReviewSummary(res.summary);
    } catch (e: any) {
      setReviewSummary(e.message || "Review failed.");
      setIssues([]);
    } finally {
      setReviewLoading(false);
    }
  }

  async function exportDocx() {
    setExporting(true);
    setError("");
    try {
      const res = await api.exportDocx({
        title,
        context: store.context,
        sections: store.sections,
        proposal_id: store.proposalId,
      });
      const url = api.downloadUrl(res.filename);
      setExportUrl(url);
      window.open(url, "_blank");
    } catch (e: any) {
      setError(e.message || "Export failed.");
    } finally {
      setExporting(false);
    }
  }

  const hasContent = store.sections.some((s) => s.content);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight">{title}</h1>
            <div className="mt-0.5 flex items-center gap-2">
              {store.proposalFamily && (
                <Badge tone="accent">
                  <Layers3 className="h-3 w-3" />
                  {store.proposalFamily}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {store.context.tone} tone
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/knowledge-base")}>
            <Database className="h-4 w-4" />
            Knowledge Base
          </Button>
          <KbStatus />
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        {/* Left rail */}
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Generation Plan (TOC)</h2>
                <Badge tone="muted">{store.toc.length}</Badge>
              </div>
              <TocEditor />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Context Guardrails</h2>
                <Badge tone={store.context.client_profile === "greenfield" ? "accent" : "muted"}>
                  {store.context.client_profile || "established"}
                </Badge>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Client Profile
                </label>
                <Select
                  value={store.context.client_profile || "established"}
                  onChange={(e) =>
                    store.setContext({
                      client_profile: e.target.value as "established" | "greenfield" | "unknown",
                    })
                  }
                >
                  <option value="established">Established / modernization</option>
                  <option value="greenfield">Greenfield / new bank</option>
                  <option value="unknown">Unknown / decide from prompt</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Canonical Product
                </label>
                <input
                  value={store.context.canonical_product || "Temenos Transact"}
                  onChange={(e) =>
                    store.setContext({ canonical_product: e.target.value })
                  }
                  className="h-8 w-full rounded-md border border-input bg-card px-2 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Implementation Context
                </label>
                <textarea
                  rows={2}
                  value={
                    store.context.implementation_context ||
                    "Modernization / migration for an existing institution"
                  }
                  onChange={(e) =>
                    store.setContext({ implementation_context: e.target.value })
                  }
                  className="w-full rounded-md border border-input bg-card px-2 py-1.5 text-xs"
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <SlidersHorizontal className="h-4 w-4" />
                  Proposal Quality
                </h2>
                <Badge tone="muted">{store.quality.detail_level}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant={store.quality.include_temenos_official ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      include_temenos_official: !store.quality.include_temenos_official,
                    })
                  }
                  title="Allow official Temenos website snippets in retrieval"
                >
                  <Globe2 className="h-4 w-4" />
                  Temenos Web
                </Button>
                <Button
                  type="button"
                  variant={store.quality.use_hybrid_retrieval ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      use_hybrid_retrieval: !store.quality.use_hybrid_retrieval,
                    })
                  }
                  title="Combine vector retrieval with BM25 keyword matching"
                >
                  Hybrid RAG
                </Button>
                <Button
                  type="button"
                  variant={store.quality.require_evidence ? "default" : "outline"}
                  size="sm"
                  onClick={() =>
                    store.setQuality({
                      require_evidence: !store.quality.require_evidence,
                    })
                  }
                  title="Pause generation when no evidence is retrieved"
                >
                  Evidence Only
                </Button>
                <div className="space-y-1">
                  <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Sources
                  </label>
                  <input
                    type="number"
                    min={4}
                    max={18}
                    value={store.quality.top_k}
                    onChange={(e) =>
                      store.setQuality({
                        top_k: Math.max(4, Math.min(18, Number(e.target.value) || 10)),
                      })
                    }
                    className="h-8 w-full rounded-md border border-input bg-card px-2 text-xs"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Detail Profile
                </label>
                <Select
                  value={store.quality.detail_level}
                  onChange={(e) =>
                    store.setQuality({
                      detail_level: e.target.value as "balanced" | "corpus" | "exhaustive",
                    })
                  }
                >
                  <option value="balanced">Balanced</option>
                  <option value="corpus">Match Corpus</option>
                  <option value="exhaustive">Exhaustive</option>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Model
                </label>
                <Select
                  value={store.model}
                  onChange={(e) => store.setModel(e.target.value)}
                >
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              </div>

              <Button
                className="w-full"
                onClick={generateAll}
                disabled={generatingAll}
              >
                {generatingAll ? <Spinner /> : <Sparkles className="h-4 w-4" />}
                {hasContent ? "Regenerate All" : "Generate Proposal"}
              </Button>

              {generatingAll && (
                <div className="space-y-1">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <motion.div
                      className="h-full bg-accent"
                      animate={{
                        width: `${
                          progress.total
                            ? (progress.done / progress.total) * 100
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {progress.done}/{progress.total} sections
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={runReview}
                  disabled={!hasContent}
                >
                  <ShieldCheck className="h-4 w-4" /> Review
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setVersionsOpen(true)}
                >
                  <History className="h-4 w-4" /> Versions
                </Button>
              </div>
              <Button
                className="w-full"
                variant="default"
                onClick={exportDocx}
                disabled={!hasContent || exporting}
              >
                {exporting ? <Spinner /> : <Download className="h-4 w-4" />}
                Export Proposal (DOCX)
              </Button>
              {exportUrl && (
                <a
                  href={exportUrl}
                  target="_blank"
                  className="block text-center text-xs text-accent underline-offset-2 hover:underline"
                >
                  Download link (if it didn&apos;t open)
                </a>
              )}
            </CardContent>
          </Card>

          {store.familyRationale && (
            <Card>
              <CardContent className="pt-5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Why this family?
                </h3>
                <p className="mt-1 text-xs text-foreground/80">
                  {store.familyRationale}
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sections */}
        <div className="space-y-4">
          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {store.sections.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
                <Sparkles className="h-8 w-8 text-accent" />
                <h2 className="text-lg font-semibold">Ready to generate</h2>
                <p className="max-w-sm text-sm text-muted-foreground">
                  Review and edit the plan on the left, pick a model, then click{" "}
                  <strong>Generate Proposal</strong>. Sections are written one at
                  a time and grounded in your knowledge base.
                </p>
                <Button onClick={generateAll} disabled={generatingAll}>
                  {generatingAll ? <Spinner /> : <Sparkles className="h-4 w-4" />}
                  Generate Proposal
                </Button>
              </CardContent>
            </Card>
          ) : (
            store.sections.map((section, i) => (
              <SectionCard
                key={section.id}
                section={section}
                index={i}
                total={store.sections.length}
                busy={busySection === section.id}
                onRegenerate={(instruction) => regenerate(section.id, instruction)}
                onToggleLock={() =>
                  store.updateSection(section.id, { locked: !section.locked })
                }
                onDelete={() => store.removeSection(section.id)}
                onMove={(dir) => store.moveSection(section.id, dir)}
                onEdit={(patch) => store.updateSection(section.id, patch)}
                onShowEvidence={() => setEvidenceFor(section)}
              />
            ))
          )}
        </div>
      </div>

      <EvidenceDrawer
        section={evidenceFor}
        open={!!evidenceFor}
        onClose={() => setEvidenceFor(null)}
      />
      <ReviewPanel
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        loading={reviewLoading}
        issues={issues}
        summary={reviewSummary}
      />
      <VersionPanel
        open={versionsOpen}
        onClose={() => setVersionsOpen(false)}
        proposalId={store.proposalId}
        currentSections={store.sections}
        onRestore={(sections) => {
          store.setSections(sections);
          setVersionsOpen(false);
        }}
      />
    </main>
  );
}
