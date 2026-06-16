export interface ClientContext {
  client_name: string;
  industry: string;
  project_type: string;
  tone: string;
  special_instructions: string;
}

export interface TemplateSection {
  title: string;
  keywords: string[];
  description: string;
}

export interface ProposalTemplate {
  id: string;
  name: string;
  proposal_family: string;
  sections: TemplateSection[];
  origin: "discovered" | "user";
  support: number;
  created_at?: string;
  updated_at?: string;
}

export interface TocSection {
  id: string;
  title: string;
  keywords: string[];
  description: string;
}

export interface EvidenceChunk {
  text: string;
  score: number;
  source_proposal: string;
  source_section: string;
  proposal_family: string;
  chunk_id: string;
}

export interface SectionResult {
  id: string;
  title: string;
  content: string;
  evidence: EvidenceChunk[];
  locked: boolean;
  model: string;
  generated_at: string;
}

export interface ReviewIssue {
  severity: "info" | "warning" | "error";
  category: string;
  message: string;
  section_title: string;
}

export interface KnowledgeBaseStatus {
  connected: boolean;
  collection: string;
  points: number;
  mode: string;
  embedding_ready?: boolean;
  embedding_model?: string;
  message: string;
}

export interface VersionMeta {
  version_id: string;
  label: string;
  created_at: string;
  sections: number;
}
