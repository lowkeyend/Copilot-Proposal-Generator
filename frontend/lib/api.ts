import type {
  ClientContext,
  EvidenceChunk,
  KnowledgeBaseStatus,
  ProposalTemplate,
  ReviewIssue,
  SectionResult,
  TocSection,
  VersionMeta,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
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

export const api = {
  base: BASE,

  status: () => jsonFetch<KnowledgeBaseStatus>("/status"),

  models: () =>
    jsonFetch<{ models: string[]; default: string; llm_ready: boolean }>("/models"),

  generateContext: (body: {
    prompt: string;
    model?: string;
    client_name?: string;
    industry?: string;
    project_type?: string;
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
