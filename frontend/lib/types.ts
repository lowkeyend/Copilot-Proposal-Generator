export interface ClientContext {
  client_name: string;
  industry: string;
  project_type: string;
  client_profile: "established" | "greenfield" | "unknown";
  implementation_context: string;
  canonical_product: string;
  intake: IntakeProfile;
  tone: string;
  special_instructions: string;
}

export interface IntakeProfile {
  launch_segments: string[];
  phase_1_products: string[];
  phase_2_products: string[];
  regulatory_interfaces_phase_1: string[];
  regulatory_interfaces_phase_2: string[];
  channels_phase_1: string[];
  channels_phase_2: string[];
  middleware_platform: string;
  reporting_platform: string;
  database_platform: string;
  hosting_model: string;
  container_platform: string;
  data_warehouse_platform: string;
  implementation_methodology: string;
  delivery_model: string;
  target_customers_year_1: string;
  target_customers_year_2: string;
  target_customers_year_3: string;
  target_accounts_year_1: string;
  target_accounts_year_2: string;
  target_accounts_year_3: string;
  launch_plan: string;
  questionnaire_notes: string;
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
  summary: string;
  source_proposal: string;
  source_section: string;
  proposal_family: string;
  chunk_id: string;
  source_type: string;
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
  embedding_provider?: string;
  embedding_model?: string;
  message: string;
}

export interface KnowledgeBaseChunk {
  chunk_id: string;
  summary: string;
  text: string;
  source_proposal: string;
  source_section: string;
  proposal_family: string;
  score: number;
  payload: Record<string, unknown>;
}

export interface KnowledgeBaseChunkUpdate {
  text?: string;
  source_proposal?: string;
  source_section?: string;
  proposal_family?: string;
}

export interface KnowledgeBaseUploadResponse {
  files: string[];
  chunks_written: number;
  collection: string;
  detail: string;
}

export interface ProposalQualitySettings {
  include_temenos_official: boolean;
  use_hybrid_retrieval: boolean;
  require_evidence: boolean;
  detail_level: "balanced" | "corpus" | "exhaustive";
  top_k: number;
}

export interface VersionMeta {
  version_id: string;
  label: string;
  created_at: string;
  sections: number;
}
