"use client";

import { useEffect, useMemo, useState } from "react";
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
import type {
  ReviewIssue,
  SectionResult,
  TemplateDocumentArtifact,
  TemplateSectionNode,
} from "@/lib/types";
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
import { DropdownMultiSelect } from "@/components/DropdownMultiSelect";
import { TEMENOS_PRODUCT_OPTIONS } from "@/lib/intakeOptions";

function canonicalProductLabel(values: string[]) {
  return values.filter(Boolean).join(", ");
}

export default function WorkspacePage() {
  const router = useRouter();
  const store = useProposalStore();
  const [models] = useState([
    "openrouter/free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "deepseek/deepseek-chat-v3.1:free",
    "qwen/qwen3-32b",
    "deepseek/deepseek-chat",
  ]);

  const [busySection, setBusySection] = useState<string | null>(null);
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
  const [templateOptions, setTemplateOptions] = useState<TemplateDocumentArtifact[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [documentOptions, setDocumentOptions] = useState<string[]>([]);
  const [parsedArtifacts, setParsedArtifacts] = useState<any[]>([]);
  const [masterPrompt, setMasterPrompt] = useState(store.prompt);

  useEffect(() => {
    api.listTemplates()
      .then((res) => {
        setTemplateOptions((res.artifacts || []).sort((a, b) =>
          `${a.proposal_family} ${a.name}`.localeCompare(`${b.proposal_family} ${b.name}`)
        ));
        setParsedArtifacts(res.artifacts || []);
      })
      .catch(() => setTemplateOptions([]));
    api.listKnowledgeChunks(2000)
      .then((res) => {
        const docs = Array.from(
          new Set(
            res.chunks
              .map((chunk) => chunk.source_document || chunk.source_proposal)
              .filter((value): value is string => Boolean(value && value.trim()))
          )
        ).sort((a, b) => a.localeCompare(b));
        setDocumentOptions(docs);
      })
      .catch(() => setDocumentOptions([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const title = useMemo(
    () =>
      store.context.client_name
        ? `${store.context.client_name} — ${canonicalProductLabel(store.context.canonical_product) || "Proposal"}`
        : canonicalProductLabel(store.context.canonical_product) || "Untitled Proposal",
    [store.context]
  );

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

  function contentFromTemplate(node: TemplateSectionNode): string {
    const paragraphs = (node.paragraphs || []).map((p) => p.text).filter(Boolean);
    const body = paragraphs.join("\n\n");
    const subheads = (node.subsections || [])
      .map((s) => `## ${s.title}\n\n${contentFromTemplate(s)}`)
      .filter(Boolean);
    return [body, ...subheads].filter(Boolean).join("\n\n");
  }

  function resetWorkspace() {
    const confirmed = window.confirm(
      "Reset the workspace? This will clear the prompt, parsed RFP, TOC, generated sections, and current proposal context."
    );
    if (!confirmed) return;
    store.resetWorkspace();
    setError("");
    setBusySection(null);
    setEvidenceFor(null);
    setReviewOpen(false);
    setReviewLoading(false);
    setIssues([]);
    setReviewSummary("");
    setVersionsOpen(false);
    setExporting(false);
    setExportUrl("");
    router.push("/");
  }

  const hasContent = store.sections.some((s) => s.content);
  const selectedTemplate =
    templateOptions.find((artifact) => artifact.template_id === selectedTemplateId) ||
    templateOptions[0] ||
    null;

  useEffect(() => {
    setMasterPrompt(store.prompt);
  }, [store.prompt]);

  useEffect(() => {
    if (!selectedTemplateId && templateOptions.length > 0) {
      setSelectedTemplateId(templateOptions[0].template_id);
    }
  }, [selectedTemplateId, templateOptions]);

  useEffect(() => {
    if (!selectedTemplate) return;
    if (selectedTemplate.proposal_family) {
      store.setProposalFamily(selectedTemplate.proposal_family);
    }
    if (selectedTemplate.sections?.length) {
      store.setToc(
        selectedTemplate.sections.map((section, idx) => ({
          id: `${section.title}-${idx}`,
          title: section.title,
          keywords: section.title
            .toLowerCase()
            .split(/[^a-z0-9]+/)
            .filter((word) => word.length > 2),
          description: section.paragraphs?.[0]?.text || section.title,
        }))
      );
      store.setSections(
        selectedTemplate.sections.map((section, idx) => ({
          id: `${section.title}-${idx}`,
          title: section.title,
          content: contentFromTemplate(section),
          evidence: [],
          locked: true,
          model: "",
          generated_at: "",
        }))
      );
    }
  }, [selectedTemplateId]);

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
          <Button variant="outline" size="sm" onClick={resetWorkspace}>
            <Sparkles className="h-4 w-4" />
            Reset Workspace
          </Button>
          <KbStatus />
        </div>
      </div>

      <Card className="mb-5 border-primary/20 bg-gradient-to-r from-white via-white to-muted/30">
        <CardContent className="flex flex-wrap items-end justify-between gap-4 pt-5">
          <div className="min-w-[280px] flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
              Workspace Template
            </div>
            <h2 className="mt-1 text-lg font-semibold">Select the proposal template and source documents here</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              This is the primary control bar for the browser proposal canvas.
            </p>
          </div>
          <div className="grid min-w-[320px] gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Template
              </label>
              <Select
                value={selectedTemplate?.template_id || ""}
                onChange={(e) => {
                  setSelectedTemplateId(e.target.value);
                }}
              >
                <option value="">Select a template</option>
                {templateOptions.map((t) => (
                  <option key={t.template_id} value={t.template_id}>
                    {t.proposal_family} - {t.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Selected Documents
              </label>
              <DropdownMultiSelect
                label=""
                options={documentOptions}
                value={store.context.selected_documents}
                onChange={(next) => store.setContext({ selected_documents: next })}
                placeholder="Choose documents"
                helper="Only selected documents are used when generating sections."
              />
            </div>
          </div>
        </CardContent>
        <div className="border-t border-border px-5 py-4">
          <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Master Prompt
          </label>
          <textarea
            value={masterPrompt}
            onChange={(e) => {
              setMasterPrompt(e.target.value);
              store.setPrompt(e.target.value);
            }}
            rows={4}
            className="w-full rounded-xl border border-input bg-white px-3 py-2 text-sm outline-none ring-0 focus:border-primary"
            placeholder="Describe how you want the full proposal to adapt, what should stay static, what should change, and any version replacements..."
          />
          <p className="mt-2 text-xs text-muted-foreground">
            This prompt applies to the full proposal and is reused whenever you generate or regenerate a section.
          </p>
        </div>
      </Card>

      {parsedArtifacts.length > 0 && (
        <Card className="mb-5 border-dashed border-accent/30 bg-accent/5">
          <CardContent className="space-y-3 pt-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
                  Parsed Template
                </div>
                <h3 className="mt-1 text-sm font-semibold">Available parsed DOCX templates</h3>
              </div>
              <Badge tone="accent">{parsedArtifacts.length}</Badge>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {parsedArtifacts.map((artifact) => (
                <div key={artifact.template_id} className="rounded-xl border border-border bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">{artifact.name || "Untitled template"}</div>
                    <Badge tone="muted">{artifact.proposal_family || "General"}</Badge>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground break-all">
                    {artifact.source_file}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Badge tone="muted">{artifact.sections?.length || 0} sections</Badge>
                    <Badge tone="muted">{artifact.images?.length || 0} images</Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
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
                <DropdownMultiSelect
                  label=""
                  options={TEMENOS_PRODUCT_OPTIONS}
                  value={store.context.canonical_product}
                  onChange={(next) => store.setContext({ canonical_product: next })}
                  placeholder="Add canonical product"
                  helper="Select one or more products to guide tone and terminology."
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

              <div className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                The selected template is loaded into the canvas automatically. Use the section controls to regenerate any block with a prompt.
              </div>

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
          <Card className="border-border/70 bg-white/85 shadow-sm">
            <CardContent className="space-y-3 pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold">Browser Proposal Canvas</h2>
                  <p className="text-xs text-muted-foreground">
                    Edit the proposal directly here. Static blocks stay fixed and sections can be regenerated individually.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="muted">{store.sections.length} sections</Badge>
                  <Badge tone="muted">{store.context.selected_documents.length} docs</Badge>
                </div>
              </div>
              <div className="rounded-2xl border border-border bg-[#fbfbf7] p-4 shadow-inner">
                <div className="mx-auto max-w-[980px] rounded-[28px] bg-white px-6 py-8 shadow-[0_12px_40px_rgba(15,23,42,0.10)]">
                  <div className="border-b border-border pb-5">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
                      Proposal
                    </div>
                    <h3 className="mt-2 text-2xl font-bold text-primary">{title}</h3>
                    <div className="mt-2 text-sm text-muted-foreground">
                      Template: {selectedTemplate ? `${selectedTemplate.proposal_family} - ${selectedTemplate.name}` : "None selected"}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Date: {new Date().toLocaleDateString()}
                    </div>
                  </div>
                  <div className="mt-5 space-y-4">
                    {store.sections.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
                        Choose a template and documents, then generate sections here.
                      </div>
                    ) : (
                      store.sections.map((section, i) => (
                        <SectionCard
                          key={section.id}
                          section={section}
                          index={i}
                          total={store.sections.length}
                          busy={busySection === section.id}
                          onRegenerate={(instruction) => regenerate(section.id, instruction)}
                          onToggleLock={() => store.updateSection(section.id, { locked: !section.locked })}
                          onDelete={() => store.removeSection(section.id)}
                          onMove={(dir) => store.moveSection(section.id, dir)}
                          onEdit={(patch) => store.updateSection(section.id, patch)}
                          onShowEvidence={() => setEvidenceFor(section)}
                        />
                      ))
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {store.sections.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
                <Sparkles className="h-8 w-8 text-accent" />
                <h2 className="text-lg font-semibold">Select a parsed template</h2>
                <p className="max-w-sm text-sm text-muted-foreground">
                  The chosen parsed template will load here as the editable proposal document. Use section-level Generate controls to change any block.
                </p>
              </CardContent>
            </Card>
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

function flattenTemplateSections(nodes: TemplateSectionNode[]): TemplateSectionNode[] {
  const out: TemplateSectionNode[] = [];
  for (const node of nodes || []) {
    out.push(node);
    if (node.subsections?.length) {
      out.push(...flattenTemplateSections(node.subsections));
    }
  }
  return out;
}
