"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Database,
  Download,
  FileText,
  Globe2,
  History,
  Layers3,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import type {
  ReviewIssue,
  SectionResult,
  TemplateBlock,
  TemplateDocumentArtifact,
  TemplateImage,
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

const CLOUD_BASE = "https://fawadsidd17-proposal-copilot-backend.hf.space";

function canonicalProductLabel(values: string[]) {
  return values.filter(Boolean).join(", ");
}

function isStaticSection(title: string) {
  const normalized = title.toLowerCase().trim();
  return normalized === "company profile" || normalized === "case studies";
}

function collectSectionImages(node: TemplateSectionNode): TemplateImage[] {
  return [
    ...(node.images || []),
    ...(node.subsections || []).flatMap((child) => collectSectionImages(child)),
  ];
}

function collectSectionTables(node: TemplateSectionNode): string[] {
  const current = (node.tables || [])
    .filter((table) => table.rows > 0 && table.cols > 0)
    .map((table) => {
      const lines = (table.data || []).map((row) => `| ${row.join(" | ")} |`);
      if (!lines.length) {
        return `Table (${table.rows}x${table.cols})${table.caption ? ` - ${table.caption}` : ""}`;
      }
      const header = lines[0];
      const columnCount = Math.max((table.data?.[0] || []).length, 1);
      const separator = `| ${Array.from({ length: columnCount }, () => "---").join(" | ")} |`;
      return [table.caption || "", header, separator, ...lines.slice(1)].filter(Boolean).join("\n");
    });
  return [...current, ...(node.subsections || []).flatMap((child) => collectSectionTables(child))];
}

function collectSectionTitles(node: TemplateSectionNode): string[] {
  return [node.title, ...(node.subsections || []).flatMap((child) => collectSectionTitles(child))];
}

function sectionBlocks(template: TemplateDocumentArtifact | null, node: TemplateSectionNode): TemplateBlock[] {
  if (!template) return [];
  const titles = new Set(collectSectionTitles(node).map((item) => item.trim().toLowerCase()));
  return (template.blocks || [])
    .filter((block) => {
      const blockTitle = (block.section_title || "").trim().toLowerCase();
      const blockText = (block.text || "").trim().toLowerCase();
      return titles.has(blockTitle) || (block.kind === "heading" && titles.has(blockText));
    })
    .sort((a, b) => a.order - b.order);
}

function applyWorkspaceContextToBlocks(
  blocks: TemplateBlock[],
  clientName: string,
  currentVersion: string,
  targetVersion: string
) {
  return blocks.map((block) => {
    const next: TemplateBlock = {
      ...block,
      section_title: applyWorkspaceContextToReference(
        block.section_title || "",
        clientName,
        currentVersion,
        targetVersion
      ),
      text: applyWorkspaceContextToReference(
        block.text || "",
        clientName,
        currentVersion,
        targetVersion
      ),
      items: (block.items || []).map((item) =>
        applyWorkspaceContextToReference(item, clientName, currentVersion, targetVersion)
      ),
      table_rows: (block.table_rows || []).map((row) =>
        row.map((cell) =>
          applyWorkspaceContextToReference(cell, clientName, currentVersion, targetVersion)
        )
      ),
    };
    if (block.image) {
      next.image = {
        ...block.image,
        caption: applyWorkspaceContextToReference(
          block.image.caption || "",
          clientName,
          currentVersion,
          targetVersion
        ),
        section: applyWorkspaceContextToReference(
          block.image.section || "",
          clientName,
          currentVersion,
          targetVersion
        ),
      };
    }
    return next;
  });
}

function templateBody(node: TemplateSectionNode): string {
  const paragraphs = (node.paragraphs || []).map((p) => p.text).filter(Boolean);
  const tables = collectSectionTables(node);
  const subsections = (node.subsections || [])
    .map((child) => `## ${child.title}\n\n${templateBody(child)}`)
    .filter(Boolean);
  return [...paragraphs, ...tables, ...subsections].filter(Boolean).join("\n\n");
}

function applyWorkspaceContextToReference(
  content: string,
  clientName: string,
  currentVersion: string,
  targetVersion: string
) {
  let next = content || "";
  const today = todayLabel();
  const normalizedClient = clientName.trim();
  if (normalizedClient) {
    const candidates = [
      /Alkuraimi(?:\s+Islamic)?\s+Bank/gi,
      /Al\s*Kuraimi(?:\s+Islamic)?\s+Bank/gi,
      /Bank White/gi,
      /Bank of Dubai/gi,
      /\bQIB\b/g,
    ];
    for (const pattern of candidates) {
      next = next.replace(pattern, normalizedClient);
    }
  }
  const fromVersion = currentVersion.trim();
  const toVersion = targetVersion.trim();
  if (fromVersion && toVersion && fromVersion !== toVersion) {
    next = next.replace(
      /\bfrom\s+release\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b/gi,
      `from release ${fromVersion} to ${toVersion}`
    );
    next = next.replace(
      /\bfrom\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b/gi,
      `from ${fromVersion} to ${toVersion}`
    );
  }
  next = next.replace(
    /\bDate:\s*[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s+\d{4}\b/gi,
    `Date: ${today}`
  );
  next = next.replace(
    /\bDate:\s*\d{1,2}\s+[A-Za-z]+\s+\d{4}\b/gi,
    `Date: ${today}`
  );
  return next;
}

function assetUrl(path: string) {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app")) {
    return `${CLOUD_BASE}${path}`;
  }
  return `http://localhost:8000${path}`;
}

function templateSignature(template: TemplateDocumentArtifact | null) {
  if (!template) return "";
  return `${template.template_id}:${template.updated_at || ""}:${template.sections?.length || 0}`;
}

function todayLabel() {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date());
}

function providerLabel(model: string) {
  if (model.startsWith("groq/")) return "Groq";
  if (model.startsWith("openrouter/")) return "OpenRouter";
  return "Custom";
}

export default function WorkspacePage() {
  const router = useRouter();
  const store = useProposalStore();
  const [busySection, setBusySection] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [templateOptions, setTemplateOptions] = useState<TemplateDocumentArtifact[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [documentOptions, setDocumentOptions] = useState<string[]>([]);
  const [masterPrompt, setMasterPrompt] = useState(store.prompt);
  const [models] = useState([
    "groq/openai/gpt-oss-20b",
    "openrouter/free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "deepseek/deepseek-chat-v3.1:free",
    "qwen/qwen3-32b",
    "deepseek/deepseek-chat",
    "groq/qwen/qwen3-32b",
  ]);

  const [evidenceFor, setEvidenceFor] = useState<SectionResult | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [issues, setIssues] = useState<ReviewIssue[]>([]);
  const [reviewSummary, setReviewSummary] = useState("");
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportUrl, setExportUrl] = useState("");
  const [loadedTemplateSignature, setLoadedTemplateSignature] = useState("");
  const activeModel = store.model || models[0];
  const activeProvider = providerLabel(activeModel);

  useEffect(() => {
    api.listTemplates()
      .then((res) => {
        const artifacts = (res.artifacts || []).sort((a, b) =>
          `${a.proposal_family} ${a.name}`.localeCompare(`${b.proposal_family} ${b.name}`)
        );
        setTemplateOptions(artifacts);
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
  }, []);

  useEffect(() => {
    setMasterPrompt(store.prompt);
  }, [store.prompt]);

  useEffect(() => {
    if (!selectedTemplateId && templateOptions.length > 0) {
      setSelectedTemplateId(templateOptions[0].template_id);
    }
  }, [selectedTemplateId, templateOptions]);

  const selectedTemplate = useMemo(
    () =>
      templateOptions.find((artifact) => artifact.template_id === selectedTemplateId) ||
      templateOptions[0] ||
      null,
    [selectedTemplateId, templateOptions]
  );

  const referenceSections = useMemo(() => {
    const map = new Map<string, TemplateSectionNode>();
    (selectedTemplate?.sections || []).forEach((section, idx) => {
      map.set(`${section.title}-${idx}`, section);
    });
    return map;
  }, [selectedTemplate]);

  useEffect(() => {
    if (!selectedTemplate) return;
    const signature = templateSignature(selectedTemplate);
    if (loadedTemplateSignature === signature && store.sections.length > 0) return;
    if (selectedTemplate.proposal_family) {
      store.setProposalFamily(selectedTemplate.proposal_family);
    }
    if (!selectedTemplate.sections?.length) {
      setLoadedTemplateSignature(signature);
      return;
    }
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
        content: applyWorkspaceContextToReference(
          templateBody(section),
          store.context.client_name,
          store.context.intake.current_version,
          store.context.intake.target_version
        ),
        blocks: applyWorkspaceContextToBlocks(
          sectionBlocks(selectedTemplate, section),
          store.context.client_name,
          store.context.intake.current_version,
          store.context.intake.target_version
        ),
        evidence: [],
        images: collectSectionImages(section),
        locked: isStaticSection(section.title),
        model: "template-preview",
        generated_at: "",
      }))
    );
    setLoadedTemplateSignature(signature);
  }, [selectedTemplate, loadedTemplateSignature, store.sections.length]);

  useEffect(() => {
    if (!selectedTemplate) return;
    store.setSections(
      store.sections.map((section) => {
        if (section.model !== "template-preview") return section;
        const referenceNode = referenceSections.get(section.id);
        if (!referenceNode) return section;
        return {
          ...section,
          title: referenceNode.title,
          content: applyWorkspaceContextToReference(
            templateBody(referenceNode),
            store.context.client_name,
            store.context.intake.current_version,
            store.context.intake.target_version
          ),
          blocks: applyWorkspaceContextToBlocks(
            sectionBlocks(selectedTemplate, referenceNode),
            store.context.client_name,
            store.context.intake.current_version,
            store.context.intake.target_version
          ),
        };
      })
    );
  }, [
    store.context.client_name,
    store.context.intake.current_version,
    store.context.intake.target_version,
    selectedTemplate,
  ]);

  const title = useMemo(
    () =>
      store.context.client_name
        ? `${store.context.client_name} - ${canonicalProductLabel(store.context.canonical_product) || "Proposal"}`
        : canonicalProductLabel(store.context.canonical_product) || "Untitled Proposal",
    [store.context]
  );

  const hasContent = store.sections.some((section) => section.content);

  async function adaptOne(sectionId: string, instruction = "") {
    setError("");
    setBusySection(sectionId);
    try {
      const existing = store.sections.find((item) => item.id === sectionId);
      const referenceNode = referenceSections.get(sectionId);
      const toc = store.toc.find((item) => item.id === sectionId);
      const title = existing?.title || referenceNode?.title || toc?.title || "Section";
      const derivedKeywords = Array.from(
        new Set(
          [
            ...(toc?.keywords || []),
            ...((referenceNode?.subsections || []).map((item) => item.title)),
            title,
          ].filter(Boolean)
        )
      );
      const res = await api.generateSection({
        section_title: title,
        keywords: derivedKeywords,
        context: store.context,
        proposal_family: store.proposalFamily,
        prompt: store.prompt,
        pattern_guidance: referenceNode
          ? `Use the selected template's section headings as guidance, but generate fresh content from the selected source documents. Preserve paragraph-based formatting.`
          : toc?.description || "",
        instruction,
        model: store.model,
        top_k: store.quality.top_k,
        include_temenos_official: store.quality.include_temenos_official,
        use_hybrid_retrieval: store.quality.use_hybrid_retrieval,
        require_evidence: store.quality.require_evidence,
        detail_level: store.quality.detail_level,
      });
      store.upsertSection({
        ...res,
        id: sectionId,
        images:
          (res.blocks || [])
            .filter((block) => block.kind === "image" && block.image)
            .map((block) => block.image!)
            .filter(Boolean) || existing?.images || [],
        locked: existing?.locked || false,
      });
    } catch (e: any) {
      setError(e.message || "Section generation failed.");
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
      setIssues([]);
      setReviewSummary(e.message || "Review failed.");
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

  function resetWorkspace() {
    const confirmed = window.confirm(
      "Reset the workspace? This clears the prompt, TOC, generated sections, and current proposal context."
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
    setLoadedTemplateSignature("");
    router.push("/");
  }

  async function replaceSectionImage(sectionId: string, imageIndex: number, file: File | null) {
    if (!file) return;
    try {
      const uploaded = await api.uploadWorkspaceImage(file);
      const section = store.sections.find((item) => item.id === sectionId);
      if (!section) return;
      const nextImages = [...(section.images || [])];
      const current = nextImages.find((image) => image.index === imageIndex);
      if (!current) return;
      const imageArrayIndex = nextImages.findIndex((image) => image.index === imageIndex);
      nextImages[imageArrayIndex] = { ...current, filename: uploaded.filename, asset_path: uploaded.asset_path, asset_url: uploaded.asset_url };
      const nextBlocks = (section.blocks || []).map((block) => {
        if (block.kind !== "image" || !block.image) return block;
        if (block.image.index !== current.index) return block;
        return {
          ...block,
          image: {
            ...block.image,
            filename: uploaded.filename,
            asset_path: uploaded.asset_path,
            asset_url: uploaded.asset_url,
          },
        };
      });
      store.updateSection(sectionId, { images: nextImages, blocks: nextBlocks });
    } catch (e: any) {
      setError(e.message || "Image upload failed.");
    }
  }

  function deleteSectionImage(sectionId: string, imageIndex: number) {
    const section = store.sections.find((item) => item.id === sectionId);
    if (!section) return;
    const nextImages = [...(section.images || [])];
    const imageArrayIndex = nextImages.findIndex((image) => image.index === imageIndex);
    if (imageArrayIndex === -1) return;
    const removed = nextImages[imageArrayIndex];
    nextImages.splice(imageArrayIndex, 1);
    const nextBlocks = (section.blocks || []).filter(
      (block) => !(block.kind === "image" && block.image && removed && block.image.index === removed.index)
    );
    store.updateSection(sectionId, { images: nextImages, blocks: nextBlocks });
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
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
              <span className="text-xs text-muted-foreground">{store.context.tone} tone</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden min-w-[240px] rounded-xl border border-primary/20 bg-white/90 px-3 py-2 text-right shadow-sm md:block">
            <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-muted-foreground">
              Active LLM
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{activeProvider}</div>
            <div className="truncate text-xs text-muted-foreground" title={activeModel}>
              {activeModel}
            </div>
          </div>
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
        <CardContent className="space-y-4 pt-5">
          <div className="rounded-xl border border-primary/15 bg-white/85 px-3 py-2 md:hidden">
            <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-muted-foreground">
              Active LLM
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{activeProvider}</div>
            <div className="truncate text-xs text-muted-foreground" title={activeModel}>
              {activeModel}
            </div>
          </div>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-[280px] flex-1">
              <div className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">
                Reference-First Workspace
              </div>
              <h2 className="mt-1 text-lg font-semibold">Select the reference proposal and the source documents</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                The system now adapts the selected reference proposal section-by-section instead of rewriting from scratch.
              </p>
            </div>
            <div className="grid min-w-[320px] gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Client Name
                </label>
                <input
                  value={store.context.client_name}
                  onChange={(e) => store.setContext({ client_name: e.target.value })}
                  className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
                  placeholder="Bank Alfalah"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Reference Template
                </label>
                <Select value={selectedTemplate?.template_id || ""} onChange={(e) => setSelectedTemplateId(e.target.value)}>
                  <option value="">Select a template</option>
                  {templateOptions.map((item) => (
                    <option key={item.template_id} value={item.template_id}>
                      {item.proposal_family} - {item.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Source Documents
                </label>
                <DropdownMultiSelect
                  label=""
                  options={documentOptions}
                  value={store.context.selected_documents}
                  onChange={(next) => store.setContext({ selected_documents: next })}
                  placeholder="Choose documents"
                  helper="Only these documents are used to extract facts for adaptation."
                />
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-4">
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
              className="w-full rounded-xl border border-input bg-white px-3 py-2 text-sm outline-none focus:border-primary"
              placeholder={`Example: Prepare a client-ready technical upgrade proposal for ${store.context.client_name || "Bank Alfalah"} using the selected reference template. Keep Company Profile unchanged. Adapt all variable sections for an established bank upgrading Temenos Transact from R20 to R26. Use only the selected source documents. Preserve the operational tone, section structure, and activity-based wording of the reference. Remove unsupported benefits language. Replace timeline assumptions with the current engagement context and update client names consistently throughout.`}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Example prompt: Prepare a technical upgrade proposal for {store.context.client_name || "Bank Alfalah"} from R20 to R26. Keep Company Profile static, preserve the reference structure, use only selected documents, and adapt Scope, Solution, Methodology, Governance, Timeline, Training, and Assumptions conservatively.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Major TOC</h2>
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
                  helper="This is used as a terminology guardrail during adaptation."
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <SlidersHorizontal className="h-4 w-4" />
                  Adaptation Controls
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
                  Model
                </label>
                <Select value={store.model} onChange={(e) => store.setModel(e.target.value)}>
                  {models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button variant="outline" size="sm" onClick={runReview} disabled={!hasContent}>
                  <ShieldCheck className="h-4 w-4" /> Review
                </Button>
                <Button variant="outline" size="sm" onClick={() => setVersionsOpen(true)}>
                  <History className="h-4 w-4" /> Versions
                </Button>
              </div>
              <Button className="w-full" variant="default" onClick={exportDocx} disabled={!hasContent || exporting}>
                {exporting ? <Spinner /> : <Download className="h-4 w-4" />}
                Export Proposal (DOCX)
              </Button>
              {exportUrl && (
                <a
                  href={exportUrl}
                  target="_blank"
                  className="block text-center text-xs text-accent underline-offset-2 hover:underline"
                >
                  Download link (if it did not open)
                </a>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="border-border/70 bg-white/85 shadow-sm">
            <CardContent className="space-y-3 pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold">Document Canvas</h2>
                  <p className="text-xs text-muted-foreground">
                    Each section starts from the parsed reference document. Generate only the sections you want to adapt.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="muted">{store.sections.length} sections</Badge>
                  <Badge tone="muted">{store.context.selected_documents.length} docs</Badge>
                  <Badge tone="muted">{selectedTemplate?.images?.length || 0} images</Badge>
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
                    <div className="mt-1 text-xs text-muted-foreground">Date: {todayLabel()}</div>
                  </div>

                  <div className="mt-5 space-y-4">
                    {store.sections.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-10 text-center text-sm text-muted-foreground">
                        Choose a parsed reference template to load the proposal canvas.
                      </div>
                    ) : (
                      store.sections.map((section, index) => {
                        return (
                          <div key={section.id} className="space-y-3">
                            <SectionCard
                              section={section}
                              index={index}
                              total={store.sections.length}
                              busy={busySection === section.id}
                              onRegenerate={(instruction) => adaptOne(section.id, instruction)}
                              onToggleLock={() => store.updateSection(section.id, { locked: !section.locked })}
                              onDelete={() => store.removeSection(section.id)}
                              onMove={(dir) => store.moveSection(section.id, dir)}
                              onEdit={(patch) => store.updateSection(section.id, patch)}
                              onShowEvidence={() => setEvidenceFor(section)}
                              onReplaceImage={(imageIndex, file) => replaceSectionImage(section.id, imageIndex, file)}
                              onDeleteImage={(imageIndex) => deleteSectionImage(section.id, imageIndex)}
                            />
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </div>
      </div>

      <EvidenceDrawer section={evidenceFor} open={!!evidenceFor} onClose={() => setEvidenceFor(null)} />
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
