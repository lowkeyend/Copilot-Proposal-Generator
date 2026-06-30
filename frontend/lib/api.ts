import type {
  ClientContext,
  EvidenceChunk,
  IntakeProfile,
  KnowledgeBaseChunk,
  KnowledgeBaseChunkUpdate,
  ChatMessage,
  DocumentQueryResponse,
  InsightResponse,
  KnowledgeBaseStatus,
  KnowledgeBaseUploadResponse,
  ParsedField,
  OpenRouterSettingsStatus,
  OpenRouterSettingsUpdate,
  OpenRouterSettingsCheckResponse,
  ProposalTemplate,
  PlannerResponse,
  RfpParseResponse,
  ReviewIssue,
  SectionResult,
  TocSection,
  VersionMeta,
} from "./types";

const CLOUD_BASE = "https://fawadsidd17-proposal-copilot-backend.hf.space";
const isVercelHost =
  typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app");

const BASE = isVercelHost ? CLOUD_BASE : "http://localhost:8000";

function getOpenRouterKey(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("proposal-copilot-openrouter-key") || "";
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const openrouterKey = getOpenRouterKey();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(openrouterKey ? { "X-OpenRouter-Api-Key": openrouterKey } : {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function uploadFetch<T>(path: string, form: FormData): Promise<T> {
  const openrouterKey = getOpenRouterKey();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: openrouterKey ? { "X-OpenRouter-Api-Key": openrouterKey } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,

  status: () => jsonFetch<KnowledgeBaseStatus>("/status"),

  models: () =>
    jsonFetch<{ models: string[]; default: string; llm_ready: boolean }>("/models"),

  getOpenRouterSettings: () =>
    jsonFetch<OpenRouterSettingsStatus>("/settings/llm"),

  saveOpenRouterSettings: (body: OpenRouterSettingsUpdate) =>
    jsonFetch<OpenRouterSettingsStatus>("/settings/llm", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  checkOpenRouterSettings: (body: OpenRouterSettingsUpdate) =>
    jsonFetch<OpenRouterSettingsCheckResponse>("/settings/llm/check", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listKnowledgeChunks: (limit = 200) =>
    jsonFetch<{ chunks: KnowledgeBaseChunk[]; count: number }>(
      `/knowledge-base/chunks?limit=${limit}`
    ),

  uploadKnowledgeFiles: (
    files: File[],
    body: {
      source_proposal?: string;
      source_section?: string;
      proposal_family?: string;
    }
  ) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    if (body.source_proposal) form.append("source_proposal", body.source_proposal);
    if (body.source_section) form.append("source_section", body.source_section);
    if (body.proposal_family) form.append("proposal_family", body.proposal_family);
    return uploadFetch<KnowledgeBaseUploadResponse>("/knowledge-base/upload", form);
  },

  updateKnowledgeChunk: (chunkId: string, body: KnowledgeBaseChunkUpdate) =>
    jsonFetch<KnowledgeBaseChunk>(`/knowledge-base/chunks/${chunkId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteKnowledgeChunk: (chunkId: string) =>
    jsonFetch<{ ok: boolean; detail: string }>(
      `/knowledge-base/chunks/${chunkId}`,
      { method: "DELETE" }
    ),

  queryDocs: (body: {
    question: string;
    history?: ChatMessage[];
    document_names?: string[];
    model?: string;
    top_k?: number;
  }) =>
    jsonFetch<DocumentQueryResponse>("/query-docs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  parseRfp: (files: File[], model?: string) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    if (model) form.append("model", model);
    return uploadFetch<RfpParseResponse>("/parse-rfp", form);
  },

  planNextSteps: (body: {
    context: ClientContext;
    parsed_rfp?: RfpParseResponse | null;
    model?: string;
  }) =>
    jsonFetch<PlannerResponse>("/plan-next-steps", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  analyzeInsights: (body: {
    context: ClientContext;
    parsed_rfp?: RfpParseResponse | null;
    mode?: "agent" | "web";
    focus_areas?: string[];
    model?: string;
  }) =>
    jsonFetch<InsightResponse>("/insight-studio/analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  generateContext: (body: {
    prompt: string;
    model?: string;
    client_name?: string;
    industry?: string;
    client_profile?: "established" | "greenfield" | "unknown";
    canonical_product?: string;
    selected_documents?: string[];
    intake?: IntakeProfile;
  }) =>
    jsonFetch<{
      context: ClientContext;
      proposal_family: string;
      family_confidence: number;
      family_rationale: string;
    }>("/generate-context", { method: "POST", body: JSON.stringify(body) }),

  suggestTemplate: (body: {
    prompt: string;
    context: ClientContext;
    proposal_family: string;
    model?: string;
  }) =>
    jsonFetch<{ suggested: ProposalTemplate; alternatives: ProposalTemplate[] }>(
      "/suggest-template",
      { method: "POST", body: JSON.stringify(body) }
    ),

  buildToc: (body: {
    prompt: string;
    context: ClientContext;
    proposal_family: string;
    template?: ProposalTemplate | null;
    model?: string;
  }) =>
    jsonFetch<{ toc: TocSection[] }>("/build-toc", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  generateSection: (body: {
    section_title: string;
    keywords: string[];
    context: ClientContext;
    proposal_family: string;
    prompt?: string;
    pattern_guidance?: string;
    instruction?: string;
    model?: string;
    top_k?: number;
    include_temenos_official?: boolean;
    use_hybrid_retrieval?: boolean;
    detail_level?: "balanced" | "corpus" | "exhaustive";
    require_evidence?: boolean;
  }) =>
    jsonFetch<SectionResult>("/generate-section", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  persistProposal: (
    req: {
      prompt: string;
      context: ClientContext;
      proposal_family: string;
      toc: TocSection[];
      model?: string;
      top_k?: number;
      include_temenos_official?: boolean;
      use_hybrid_retrieval?: boolean;
      detail_level?: "balanced" | "corpus" | "exhaustive";
      require_evidence?: boolean;
    },
    sections: SectionResult[]
  ) =>
    jsonFetch<{ proposal_id: string; version_id: string; sections: SectionResult[] }>(
      "/proposals/persist",
      { method: "POST", body: JSON.stringify({ req, sections }) }
    ),

  reviewProposal: (body: {
    context: ClientContext;
    sections: SectionResult[];
    model?: string;
  }) =>
    jsonFetch<{ issues: ReviewIssue[]; summary: string }>("/review-proposal", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  exportDocx: (body: {
    title: string;
    context: ClientContext;
    sections: SectionResult[];
    proposal_id?: string | null;
  }) =>
    jsonFetch<{ filename: string; download_url: string }>("/export-docx", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listTemplates: () =>
    jsonFetch<{ user: ProposalTemplate[]; discovered: ProposalTemplate[] }>(
      "/templates"
    ),

  upsertTemplate: (t: ProposalTemplate) =>
    jsonFetch<ProposalTemplate>("/templates", {
      method: "POST",
      body: JSON.stringify(t),
    }),

  deleteTemplate: (id: string) =>
    jsonFetch<{ ok: boolean }>(`/templates/${id}`, { method: "DELETE" }),

  discoverPatterns: () =>
    jsonFetch<{ count: number; patterns: ProposalTemplate[] }>(
      "/discover-patterns",
      { method: "POST" }
    ),

  listVersions: (proposalId: string) =>
    jsonFetch<{ proposal_id: string; versions: VersionMeta[] }>(
      `/versions?proposal_id=${encodeURIComponent(proposalId)}`
    ),

  getVersion: (proposalId: string, versionId: string) =>
    jsonFetch<{ version_id: string; label: string; sections: SectionResult[] }>(
      `/versions/${proposalId}/${versionId}`
    ),

  duplicateVersion: (proposalId: string, versionId: string) =>
    jsonFetch<{ version_id: string; label: string; sections: SectionResult[] }>(
      `/versions/${proposalId}/${versionId}/duplicate`,
      { method: "POST" }
    ),

  saveVersion: (proposalId: string, sections: SectionResult[], label = "") =>
    jsonFetch<{ version_id: string; label: string }>(
      `/proposals/${proposalId}/save-version?label=${encodeURIComponent(label)}`,
      { method: "POST", body: JSON.stringify(sections) }
    ),

  downloadUrl: (filename: string) => `${BASE}/files/${filename}`,
};

export type { EvidenceChunk };
